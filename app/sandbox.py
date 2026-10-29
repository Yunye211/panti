"""轻量代码沙箱：在独立子进程中执行用户提交的 Python 代码。

安全策略（教学场景适用，生产环境建议再配合 Docker / 受限系统用户使用）：
1. 独立临时目录：进程 cwd、sys.path、stdin 均在该目录内，文件写入只允许落在该目录；
2. 模块级拦截：审计钩子拦截 import 事件，网络/进程/系统命令等危险模块无法导入
   （配合 sys.modules 置 None，可防止 del sys.modules[...] 之类的绕过）；
3. 文件审计：open / os.open / os.listdir 只允许访问临时目录与 Python 安装目录，
   任何写操作（含 os.open 的写标志）只允许落在临时目录；
4. 资源限制：类 Unix 使用 resource 限制内存/CPU/文件大小，Windows 使用 Job Object
   限制进程内存与子进程数量；
5. 时间限制：单测试点超时即 kill；
6. 输出限制：stdout/stderr 直接写入临时文件，父进程只读取前 N 字节，
   避免 `while True: print(...)` 拖垮判题服务内存；
7. 环境变量最小化：子进程不继承服务端环境变量（避免 SECRET_KEY 等泄露）；
8. 并发闸门：限制同时运行的判题进程数量，防止批量提交耗尽 CPU。
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

MAX_OUTPUT = 64 * 1024  # 单测试点最多读取的输出字节数
MAX_CONCURRENCY = int(os.environ.get("JUDGE_MAX_CONCURRENCY", "4"))
_WAIT_SLOT_TIMEOUT = 30

# 限制同时判题的进程数，避免多用户同时提交把 CPU 打满
_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)

# 顶层模块黑名单（含底层私有实现，防止 _socket / _ctypes 之类绕过）
BLOCKED_MODULES = [
    "socket", "_socket", "ssl", "_ssl", "socketserver",
    "subprocess", "_subprocess", "_posixsubprocess", "shutil", "pty",
    "requests", "urllib", "urllib.request", "http", "http.client",
    "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "webbrowser",
    "multiprocessing", "_multiprocessing", "concurrent", "ctypes", "_ctypes",
    "termios", "fcntl", "resource", "sysconfig", "distutils", "asyncio",
    "pickle", "shelve", "sqlite3", "dbm",
    "_winapi", "msvcrt",
]

# 说明：不禁用 importlib 顶层（解释器内部依赖 importlib.machinery，
# 任何 import 都会先触发父包事件），真正的安全边界是“目标模块”被拦截：
# importlib.import_module('socket') 仍会触发 socket 的 import 事件而被拒绝。
# 这里仅禁用 importlib.util，堵住 find_spec + module_from_spec + exec_module 这条绕过链。
BLOCKED_EXACT = {"importlib.util"}

BLOCKED_AUDIT_EVENTS = {
    "subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn",
    "os.fork", "os.forkpty", "os.putenv", "os.startfile", "os.kill", "os.killpg",
    "socket.connect", "socket.bind", "socket.getaddrinfo", "shutil.rmtree",
    "os.remove", "os.rename", "os.replace", "os.rmdir", "os.removedirs",
    "os.mkdir", "os.makedirs", "os.chmod", "os.chown", "os.link",
    "os.symlink", "os.truncate", "os.utime",
}

RUNNER_TEMPLATE = textwrap.dedent(
    '''
    import os
    import sys

    TMP_DIR = os.path.dirname(os.path.abspath(__file__))
    os.chdir(TMP_DIR)
    sys.path.insert(0, TMP_DIR)

    BLOCKED = set({blocked!r})
    BLOCKED_EXACT = set({exact!r})
    BLOCKED_TOP = {{m.split(".")[0] for m in BLOCKED}}
    for _m in list(sys.modules):
        if _m in BLOCKED or _m.split(".")[0] in BLOCKED_TOP:
            sys.modules[_m] = None
    for _m in BLOCKED:
        sys.modules[_m] = None

    def _inside(path, root):
        try:
            return os.path.commonpath([os.path.abspath(str(path)), root]) == root
        except Exception:
            return False

    READABLE_DIRS = [TMP_DIR, os.path.abspath(sys.prefix), os.path.abspath(sys.base_prefix)]
    WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def _audit(event, args):
        if event in {events!r}:
            raise PermissionError("沙箱禁止该操作：" + event)

        if event == "import":
            name = str(args[0]) if args else ""
            if name in BLOCKED_EXACT or name in BLOCKED or name.split(".")[0] in BLOCKED_TOP:
                raise ImportError("沙箱安全限制：禁止导入模块 " + name)
            return

        if event == "open":
            try:
                path, mode = str(args[0]), str(args[1] or "r")
            except Exception:
                return
            if _inside(path, TMP_DIR):
                return
            if any(ch in mode for ch in "wax+"):
                raise PermissionError("沙箱只允许在临时目录中写文件")
            if not any(_inside(path, d) for d in READABLE_DIRS):
                raise PermissionError("沙箱禁止读取该文件：" + path)
            return

        if event == "os.open":
            try:
                path, flags = str(args[0]), int(args[1])
            except Exception:
                return
            if _inside(path, TMP_DIR):
                return
            if flags & WRITE_FLAGS:
                raise PermissionError("沙箱只允许在临时目录中写文件")
            if not any(_inside(path, d) for d in READABLE_DIRS):
                raise PermissionError("沙箱禁止读取该文件：" + path)
            return

        if event in ("os.listdir", "os.scandir", "os.chdir"):
            try:
                path = str(args[0] or ".")
            except Exception:
                return
            if not (_inside(path, TMP_DIR) or any(_inside(path, d) for d in READABLE_DIRS)):
                raise PermissionError("沙箱禁止访问该目录：" + path)

    # 先导入运行期必需的模块：安装审计钩子后 importlib.util 将被禁止再次导入
    import io
    import runpy
    import importlib.util

    def _deny(*_a, **_k):
        raise PermissionError("沙箱禁止动态加载外部模块")

    try:
        importlib.util.module_from_spec = _deny
        importlib.util.spec_from_file_location = _deny
    except Exception:
        pass

    try:
        sys.addaudithook(_audit)
    except Exception:
        pass

    sys.stdin = io.TextIOWrapper(io.BytesIO({stdin!r}), encoding="utf-8", newline="\\n")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", newline="\\n")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", newline="\\n")

    try:
        runpy.run_path(os.path.join(TMP_DIR, "solution.py"), run_name="__main__")
    except SystemExit:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
    '''
)


class RunResult:
    def __init__(self, status, stdout="", stderr="", time_ms=0):
        self.status = status  # OK / RE / TLE
        self.stdout = stdout
        self.stderr = stderr
        self.time_ms = time_ms


def check_syntax(code):
    """编译检查，返回 (ok, message)"""
    try:
        compile(code, "solution.py", "exec")
        return True, ""
    except SyntaxError as exc:
        msg = exc.msg or "语法错误"
        return False, "第 %s 行：%s" % (exc.lineno, msg)
    except ValueError as exc:  # 例如源码含空字节
        return False, str(exc)


# ----------------------------- 资源限制 -----------------------------


def _limits_unix(memory_mb, cpu_seconds):
    if os.name == "nt":  # Windows 无 resource 模块，改用 Job Object
        return {}
    try:
        import resource

        def _apply():
            mem = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))

        return {"preexec_fn": _apply}
    except Exception:
        return {}


class _WinJobObject:
    """Windows 下用 Job Object 限制子进程内存与可创建的子进程数。"""

    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    PROCESS_ALL_ACCESS = 0x001F0FFF

    def __init__(self, memory_mb):
        self.job = None
        self.kernel32 = None
        if os.name != "nt":
            return
        try:
            import ctypes

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(name, ctypes.c_uint64) for name in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
                )]

            class BASIC_LIMIT(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_uint32),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", ctypes.c_uint32),
                    ("SchedulingClass", ctypes.c_uint32),
                ]

            class EXTENDED_LIMIT(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BASIC_LIMIT),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateJobObjectW.restype = ctypes.c_void_p
            kernel32.OpenProcess.restype = ctypes.c_void_p
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return

            info = EXTENDED_LIMIT()
            info.BasicLimitInformation.LimitFlags = (
                self.JOB_OBJECT_LIMIT_PROCESS_MEMORY
                | self.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                | self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            info.BasicLimitInformation.ActiveProcessLimit = 1
            info.ProcessMemoryLimit = int(memory_mb) * 1024 * 1024
            ok = kernel32.SetInformationJobObject(
                ctypes.c_void_p(job),
                self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not ok:
                kernel32.CloseHandle(ctypes.c_void_p(job))
                return
            self.job = job
            self.kernel32 = kernel32
        except Exception:
            self.job = None

    def assign(self, pid):
        if not self.job:
            return False
        try:
            import ctypes

            handle = self.kernel32.OpenProcess(self.PROCESS_ALL_ACCESS, False, pid)
            if not handle:
                return False
            ok = self.kernel32.AssignProcessToJobObject(
                ctypes.c_void_p(self.job), ctypes.c_void_p(handle)
            )
            self.kernel32.CloseHandle(ctypes.c_void_p(handle))
            return bool(ok)
        except Exception:
            return False

    def close(self):
        if not self.job:
            return
        try:
            import ctypes

            self.kernel32.CloseHandle(ctypes.c_void_p(self.job))
        except Exception:
            pass
        self.job = None


def _minimal_env():
    """子进程只保留必要的环境变量，避免泄露服务端配置。"""
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
    }
    if os.name == "nt":
        for key in ("SystemRoot", "SYSTEMDRIVE", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT"):
            if os.environ.get(key):
                env[key] = os.environ[key]
    else:
        for key in ("PATH", "LANG", "LC_ALL", "HOME"):
            if os.environ.get(key):
                env[key] = os.environ[key]
    return env


def _read_capped(path, limit=MAX_OUTPUT):
    """只读前 limit 字节，避免超大输出撑爆判题进程内存。"""
    try:
        with open(path, "rb") as f:
            data = f.read(limit + 1)
    except OSError:
        return ""
    truncated = len(data) > limit
    text = data[:limit].decode("utf-8", "replace")
    if truncated:
        text += "\n...(输出过长，已截断显示)..."
    return text


def run_code(code, stdin_data="", time_limit=2, memory_mb=256):
    """在沙箱中运行用户代码，返回 RunResult。"""
    runner = RUNNER_TEMPLATE.format(
        blocked=BLOCKED_MODULES,
        exact=sorted(BLOCKED_EXACT),
        events=BLOCKED_AUDIT_EVENTS,
        stdin=stdin_data.encode("utf-8"),
    )

    if not _slots.acquire(timeout=_WAIT_SLOT_TIMEOUT):
        return RunResult("RE", stderr="判题服务繁忙，请稍后重试。")

    start = time.time()
    job = None
    try:
        with tempfile.TemporaryDirectory(prefix="pyjudge_") as tmp:
            with open(os.path.join(tmp, "solution.py"), "w", encoding="utf-8", newline="\n") as f:
                f.write(code)
            with open(os.path.join(tmp, "_runner.py"), "w", encoding="utf-8", newline="\n") as f:
                f.write(runner)

            out_path = os.path.join(tmp, "stdout.bin")
            err_path = os.path.join(tmp, "stderr.bin")

            try:
                with open(out_path, "wb") as fo, open(err_path, "wb") as fe:
                    proc = subprocess.Popen(
                        [sys.executable, "-I", "-S", "_runner.py"],
                        cwd=tmp,
                        stdin=subprocess.DEVNULL,
                        stdout=fo,
                        stderr=fe,
                        env=_minimal_env(),
                        **_limits_unix(memory_mb, time_limit + 1),
                    )
                    if os.name == "nt":
                        job = _WinJobObject(memory_mb)
                        job.assign(proc.pid)
                    try:
                        proc.wait(timeout=time_limit)
                        timed_out = False
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                        timed_out = True
            except Exception as exc:  # 极少发生
                return RunResult("RE", stderr="无法启动沙箱进程：%s" % exc)

            out = _read_capped(out_path)
            err = _read_capped(err_path)
            elapsed = int((time.time() - start) * 1000)

            if timed_out:
                return RunResult(
                    "TLE",
                    out,
                    "运行超时：程序在 %s 秒内未结束（可能存在死循环）。" % time_limit,
                    elapsed,
                )
            if proc.returncode == 0:
                return RunResult("OK", out, err, elapsed)
            message = _clean_traceback(err) or "程序异常退出，返回码 %s" % proc.returncode
            return RunResult("RE", out, _friendly_error(message), elapsed)
    finally:
        if job:
            job.close()
        _slots.release()


def _friendly_error(text):
    """把被沙箱屏蔽的模块导入转换为友好提示。"""
    for name in BLOCKED_MODULES:
        if "No module named '%s'" % name in text:
            return "沙箱安全限制：禁止导入模块 %s" % name
    return text


def _clean_traceback(text):
    """去掉沙箱 runner 自身的栈帧，只保留用户代码相关的错误信息。"""
    out = []
    skip = False
    for ln in text.splitlines():
        stripped = ln.strip()
        if stripped.startswith('File "'):
            skip = "solution.py" not in ln
            if not skip:
                out.append(ln)
            continue
        if stripped and not ln.startswith(" "):
            # Traceback 头 / 异常类型行，始终保留
            skip = False
            out.append(ln)
            continue
        if not skip:
            out.append(ln)
    cleaned = "\n".join(out).strip()
    if len(cleaned) > 3000:
        cleaned = cleaned[:1500] + "\n...(已截断)...\n" + cleaned[-1000:]
    return cleaned
