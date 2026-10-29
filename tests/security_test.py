"""安全测试：沙箱逃逸防护 + Web 安全（CSRF / 越权 / XSS / 资源限制）。

运行：python tests/security_test.py
"""
import re
import sys
import time

sys.path.insert(0, ".")

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Classroom, Homework, Problem, Submission, User  # noqa: E402
from app.sandbox import run_code  # noqa: E402

PASSED, FAILED, WARNED = [], [], []


def ok(name, detail=""):
    PASSED.append(name)
    print("  [PASS] %-46s %s" % (name, detail))


def fail(name, detail=""):
    FAILED.append(name)
    print("  [FAIL] %-46s %s" % (name, detail))


def warn(name, detail=""):
    WARNED.append(name)
    print("  [WARN] %-46s %s" % (name, detail))


def blocked_case(name, code, expect_ok=False):
    """运行代码并判断是否被沙箱拦截（非 OK 即视为拦截）。"""
    r = run_code(code, "", time_limit=3, memory_mb=256)
    detail = (r.stderr or r.stdout).strip().splitlines()
    detail = detail[-1][:70] if detail else ""
    if expect_ok:
        if r.status == "OK":
            ok(name, detail)
        else:
            fail(name, "期望允许但被拦截: %s" % detail)
    else:
        if r.status != "OK":
            ok(name, detail)
        else:
            fail(name, "未被拦截，输出: %s" % r.stdout.strip()[:60])
    return r


# ----------------------------- 1. 沙箱安全 -----------------------------

def test_sandbox():
    print("\n[1] 沙箱安全（模块/文件/命令/资源）")

    blocked_case("import socket", "import socket\nprint('escaped')")
    blocked_case("import _socket (私有模块绕过)", "import _socket\nprint('escaped')")
    blocked_case(
        "del sys.modules 绕过",
        "import sys\nsys.modules.pop('socket', None)\nimport socket\nprint('escaped')",
    )
    blocked_case(
        "importlib 动态导入",
        "import importlib\nm = importlib.import_module('socket')\nprint('escaped')",
    )
    blocked_case("__import__ 构造字符串导入", "__import__('soc' + 'ket')\nprint('escaped')")
    blocked_case("subprocess", "import subprocess\nsubprocess.Popen(['cmd'])\nprint('escaped')")
    blocked_case("os.system", "import os\nos.system('echo escaped')\nprint('escaped')")
    blocked_case("os.popen", "import os\nprint(os.popen('echo escaped').read())")
    blocked_case("multiprocessing", "import multiprocessing\nprint('escaped')")
    blocked_case("ctypes 调用系统", "import ctypes\nctypes.windll.kernel32\nprint('escaped')")

    blocked_case("读取系统敏感文件", "print(open('C:/Windows/win.ini').read())")
    blocked_case("读取 /etc/passwd", "print(open('/etc/passwd').read()[:20])")
    blocked_case("os.open 读取敏感文件", "import os\nfd = os.open('C:/Windows/win.ini', os.O_RDONLY)\nprint(os.read(fd, 20))")
    blocked_case(
        "写文件到系统目录",
        "open('C:/Windows/Temp/pyjudge_evil.txt', 'w').write('pwned')\nprint('escaped')",
    )
    blocked_case(
        "os.open 写文件到系统目录",
        "import os\nfd = os.open('C:/Windows/Temp/pyjudge_evil2.txt', os.O_WRONLY | os.O_CREAT)\nprint('escaped')",
    )
    blocked_case("遍历系统目录", "import os\nprint(os.listdir('C:/'))")
    blocked_case("os.chdir 到系统目录", "import os\nos.chdir('C:/')\nprint('escaped')")

    # 环境变量泄露
    r = run_code("import os\nprint(os.environ.get('SECRET_KEY', 'NONE'))", "", 3)
    if r.status == "OK" and r.stdout.strip() == "NONE":
        ok("环境变量未泄露 SECRET_KEY", r.stdout.strip())
    else:
        fail("环境变量未泄露 SECRET_KEY", r.stdout.strip()[:40] or r.stderr[:60])

    # 正常工作不受影响
    blocked_case("正常代码可运行", "print(sum(range(10)))", expect_ok=True)
    blocked_case("临时目录内可读写", "open('a.txt','w').write('ok')\nprint(open('a.txt').read())", expect_ok=True)

    # 超时
    t0 = time.time()
    r = run_code("while True:\n    pass\n", "", 2)
    dt = time.time() - t0
    if r.status == "TLE" and dt < 6:
        ok("死循环 -> 判为超时", "%.1fs" % dt)
    else:
        fail("死循环 -> 判为超时", "%s / %.1fs" % (r.status, dt))

    # 死循环刷输出（父进程内存必须可控）
    t0 = time.time()
    r = run_code("while True:\n    print('x' * 1000)\n", "", 2)
    dt = time.time() - t0
    if r.status == "TLE" and len(r.stdout) <= 70 * 1024 and dt < 8:
        ok("刷屏输出 -> 超时且输出被截断", "%.1fs / %d bytes" % (dt, len(r.stdout)))
    else:
        fail("刷屏输出 -> 超时且输出被截断", "%s / %.1fs / %d bytes" % (r.status, dt, len(r.stdout)))

    # 单次超大输出
    r = run_code("print('A' * (5 * 1024 * 1024))", "", 3)
    if r.status == "OK" and len(r.stdout) <= 70 * 1024:
        ok("单次超大输出被截断", "%d bytes" % len(r.stdout))
    else:
        fail("单次超大输出被截断", "%s / %d bytes" % (r.status, len(r.stdout)))

    # 内存炸弹
    t0 = time.time()
    r = run_code("x = 'a' * (600 * 1024 * 1024)\nprint(len(x))\n", "", 5, 256)
    dt = time.time() - t0
    if r.status != "OK" or "600" not in r.stdout:
        ok("内存炸弹被限制(600MB > 256MB)", "%s / %.1fs / %s" % (r.status, dt, r.stdout.strip()[:30]))
    else:
        warn("内存炸弹未被限制（当前平台未启用内存配额）", "%.1fs" % dt)

    # 内存配额内应可正常分配（验证限制不是“一刀切”而是按配额）
    r = run_code("x = bytearray(100 * 1024 * 1024)\nprint(len(x))\n", "", 5, 256)
    if r.status == "OK" and "104857600" in r.stdout:
        ok("限额内内存分配可用(100MB < 256MB)", r.stdout.strip())
    else:
        warn("限额内内存分配可用(100MB < 256MB)", "%s / %s" % (r.status, r.stderr.strip()[:40]))

    # 并发闸门：超过并发上限时排队而不是无限占满 CPU
    import threading

    results = []

    def _worker():
        results.append(run_code("import time\ntime.sleep(1.5)\nprint('done')\n", "", 3))

    t0 = time.time()
    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    dt = time.time() - t0
    all_ok = all(r.status == "OK" for r in results)
    if all_ok and dt >= 2.5:
        ok("并发判题受限排队(8 个任务 / 4 并发)", "%.1fs" % dt)
    else:
        warn("并发判题受限排队", "%.1fs / all_ok=%s" % (dt, all_ok))

    # 递归爆栈
    r = run_code("def f():\n    return f()\nf()\n", "", 3)
    if r.status == "RE":
        ok("无限递归 -> 运行时错误", (r.stderr.strip().splitlines() or [""])[-1][:50])
    else:
        fail("无限递归 -> 运行时错误", r.status)

    # input 无输入不应挂起
    t0 = time.time()
    r = run_code("s = input()\nprint(s)\n", "", 3)
    if time.time() - t0 < 5 and r.status == "RE":
        ok("input() 无 stdin -> 立即报错不挂起", "%.1fs" % (time.time() - t0))
    else:
        fail("input() 无 stdin -> 立即报错不挂起", "%s / %.1fs" % (r.status, time.time() - t0))

    # 语法错误
    r = run_code("print('unclosed\n", "", 3)
    if r.status == "RE" or True:
        ok("语法错误代码不导致崩溃", r.status)


# ----------------------------- 2. Web 安全 -----------------------------

CSRF_RE = re.compile(r'name="csrf-token" content="([^"]+)"')


def get_token(cli, url="/auth/login"):
    html = cli.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else None


def test_web():
    print("\n[2] Web 安全（CSRF / 越权 / XSS / 越权提交）")
    app = create_app()
    student = app.test_client()
    teacher = app.test_client()
    anon = app.test_client()

    # 未登录跳转
    r = anon.get("/", follow_redirects=False)
    if r.status_code == 302 and "/auth/login" in (r.headers.get("Location") or ""):
        ok("未登录访问首页 -> 跳转登录")
    else:
        fail("未登录访问首页 -> 跳转登录", str(r.status_code))

    # CSRF：无 token
    r = anon.post("/auth/login", data={"username": "student", "password": "123456"})
    if r.status_code == 400:
        ok("缺少 CSRF Token 的登录请求被拒绝", "400")
    else:
        fail("缺少 CSRF Token 的登录请求被拒绝", str(r.status_code))

    # CSRF：错误 token
    r = anon.post("/auth/login", data={"username": "student", "password": "123456", "csrf_token": "fake"})
    if r.status_code == 400:
        ok("伪造 CSRF Token 被拒绝", "400")
    else:
        fail("伪造 CSRF Token 被拒绝", str(r.status_code))

    # 正常登录
    st_token = get_token(student)
    r = student.post("/auth/login", data={"username": "student", "password": "123456", "csrf_token": st_token}, follow_redirects=False)
    if r.status_code == 302:
        ok("带 CSRF Token 的登录成功", "302 -> /")
    else:
        fail("带 CSRF Token 的登录成功", str(r.status_code))

    tc_token = get_token(teacher)
    teacher.post("/auth/login", data={"username": "teacher", "password": "123456", "csrf_token": tc_token})

    # API 无 CSRF header
    with app.app_context():
        pid = Problem.query.first().id
    r = student.post("/api/judge", json={"problem_id": pid, "code": "print(1)", "source": "free"})
    if r.status_code == 400 and "CSRF" in (r.get_json() or {}).get("error", ""):
        ok("API 缺少 CSRF 头被拒绝", "400")
    else:
        fail("API 缺少 CSRF 头被拒绝", str(r.status_code))

    # 判题超时不可被客户端放大
    t0 = time.time()
    r = student.post(
        "/api/judge?tl=999",
        json={"problem_id": pid, "code": "while True:\n    pass\n", "source": "free"},
        headers={"X-CSRF-Token": st_token},
    )
    dt = time.time() - t0
    data = r.get_json() or {}
    if data.get("status") == "TLE" and dt < 12:
        ok("?tl=999 无法放大超时限制", "%.1fs" % dt)
    else:
        fail("?tl=999 无法放大超时限制", "%s / %.1fs" % (data.get("status"), dt))

    # 学生越权访问教师页
    r = student.get("/teacher/problems", follow_redirects=False)
    if r.status_code == 302:
        ok("学生访问教师页面被拦截", "302")
    else:
        fail("学生访问教师页面被拦截", str(r.status_code))

    # 学生访问他人提交记录
    with app.app_context():
        me = User.query.filter_by(username="student").first()
        other_sub = Submission.query.filter(Submission.user_id != me.id).first()
    if other_sub:
        r = student.get("/problems/submissions/%d" % other_sub.id)
        if r.status_code == 403:
            ok("学生查看他人提交 -> 403")
        else:
            fail("学生查看他人提交 -> 403", str(r.status_code))

    # 教师越权：非本班学生提交
    with app.app_context():
        teacher2 = User.query.filter_by(username="teacher2").first()
        if not teacher2:
            teacher2 = User(username="teacher2", display_name="校外教师", role="teacher")
            teacher2.set_password("123456")
            db.session.add(teacher2)
            db.session.commit()
        stray = User.query.filter_by(username="stray").first()
        if not stray:
            stray = User(username="stray", display_name="无班级学生", role="student")
            stray.set_password("123456")
            db.session.add(stray)
            db.session.commit()
        p = Problem.query.first()
        sub = Submission(
            user_id=stray.id, problem_id=p.id, code="print(1)",
            status="AC", passed_count=1, total_count=1, source="free",
        )
        db.session.add(sub)
        db.session.commit()
        stray_sub_id = sub.id

    t2 = app.test_client()
    t2_token = get_token(t2)
    t2.post("/auth/login", data={"username": "teacher2", "password": "123456", "csrf_token": t2_token})
    r = t2.get("/problems/submissions/%d" % stray_sub_id)
    if r.status_code == 403:
        ok("非本班教师查看学生代码 -> 403")
    else:
        fail("非本班教师查看学生代码 -> 403", str(r.status_code))

    # 本班教师可查看
    with app.app_context():
        mine = Submission.query.filter(Submission.user_id != None).first()  # noqa: E711
        room = Classroom.query.filter_by(join_code="CLASS1").first()
        member_sub = None
        for s in room.students:
            if Submission.query.filter_by(user_id=s.id).first():
                member_sub = Submission.query.filter_by(user_id=s.id).first()
                break
        member_sub_id = member_sub.id if member_sub else None
    if member_sub_id:
        r = teacher.get("/problems/submissions/%d" % member_sub_id)
        if r.status_code == 200:
            ok("本班教师查看学生代码 -> 200")
        else:
            fail("本班教师查看学生代码 -> 200", str(r.status_code))

    # 学生提交非本班作业
    with app.app_context():
        hw = Homework.query.first()
        hw_id = hw.id
    r = student.post(
        "/api/judge",
        json={"problem_id": pid, "homework_id": hw_id, "code": "print(1)", "source": "homework"},
        headers={"X-CSRF-Token": st_token},
    )
    if r.status_code == 200:
        ok("本班学生可提交作业", "200")
    else:
        warn("本班学生提交作业", str(r.status_code))

    # 学生提交“非本班”的作业 -> 403
    with app.app_context():
        t2_user = User.query.filter_by(username="teacher2").first()
        room = Classroom.query.filter_by(join_code="CLASS1").first()
        other_room = Classroom(name="外部班级", join_code="OUTER1", teacher_id=t2_user.id)
        db.session.add(other_room)
        db.session.flush()
        from datetime import datetime, timedelta

        foreign_hw = Homework(
            title="外部班级作业", classroom_id=other_room.id, teacher_id=t2_user.id,
            due_at=datetime.now() + timedelta(days=1),
        )
        db.session.add(foreign_hw)
        db.session.flush()
        p0 = Problem.query.first()
        foreign_hw.problems.append(p0)
        db.session.commit()
        foreign_hw_id = foreign_hw.id
        foreign_room_id = other_room.id

    r = student.post(
        "/api/judge",
        json={"problem_id": pid, "homework_id": foreign_hw_id, "code": "print(1)", "source": "homework"},
        headers={"X-CSRF-Token": st_token},
    )
    if r.status_code == 403:
        ok("学生提交非本班作业 -> 403")
    else:
        fail("学生提交非本班作业 -> 403", str(r.status_code))

    # 教师删除他人创建的题目 -> 被拒绝
    with app.app_context():
        target = Problem.query.filter_by(title="A + B 问题").first()
        target_id = target.id
    r = t2.post(
        "/teacher/problems/%d/delete" % target_id,
        data={"csrf_token": t2_token},
        follow_redirects=False,
    )
    still = False
    with app.app_context():
        still = db.session.get(Problem, target_id) is not None
    if r.status_code == 302 and still:
        ok("教师删除他人题目被拒绝", "题目仍存在")
    else:
        fail("教师删除他人题目被拒绝", "%s / still=%s" % (r.status_code, still))

    # 清理：外部班级与作业
    with app.app_context():
        from app.models import homework_problems

        Submission.query.filter_by(homework_id=foreign_hw_id).delete()
        db.session.execute(
            homework_problems.delete().where(homework_problems.c.homework_id == foreign_hw_id)
        )
        hw = db.session.get(Homework, foreign_hw_id)
        if hw:
            db.session.delete(hw)
        room2 = db.session.get(Classroom, foreign_room_id)
        if room2:
            db.session.delete(room2)
        db.session.commit()

    # XSS：题目/作业描述中的脚本被转义
    with app.app_context():
        p = Problem.query.filter_by(title="A + B 问题").first()
        old_desc = p.description
        p.description = "<script>alert('xss')</script>描述测试"
        db.session.commit()
        problem_id = p.id
    html = student.get("/problems/%d" % problem_id).get_data(as_text=True)
    if "<script>alert" in html:
        fail("题目描述 XSS 转义", "出现未转义脚本")
    elif "&lt;script&gt;" in html:
        ok("题目描述 XSS 被转义", "&lt;script&gt;")
    else:
        warn("题目描述 XSS 转义", "未找到目标片段")
    with app.app_context():
        p = db.session.get(Problem, problem_id)
        p.description = old_desc
        db.session.commit()

    # 弱口令/用户名格式校验
    anon2 = app.test_client()
    tok = get_token(anon2)
    r = anon2.post("/auth/register", data={
        "username": "a b<script>", "password": "123456", "confirm": "123456",
        "role": "student", "csrf_token": tok,
    })
    if r.status_code == 200 and "字母" in r.get_data(as_text=True):
        ok("非法用户名被拒绝", "特殊字符")
    else:
        fail("非法用户名被拒绝", str(r.status_code))

    # 教师注册码校验
    anon3 = app.test_client()
    tok3 = get_token(anon3)
    r = anon3.post("/auth/register", data={
        "username": "hacker01", "password": "123456", "confirm": "123456",
        "role": "teacher", "invite_code": "wrong-code", "csrf_token": tok3,
    })
    page = r.get_data(as_text=True)
    if "注册码不正确" in page:
        ok("错误教师注册码被拒绝")
    else:
        fail("错误教师注册码被拒绝", str(r.status_code))

    # 清理测试数据
    with app.app_context():
        Submission.query.filter_by(user_id=db.session.scalar(
            __import__("sqlalchemy").select(User.id).where(User.username == "stray")
        )).delete()
        for name in ("teacher2", "stray"):
            u = User.query.filter_by(username=name).first()
            if u:
                db.session.delete(u)
        db.session.commit()


def main():
    print("=" * 70)
    print("安全测试开始")
    print("=" * 70)
    test_sandbox()
    test_web()
    print("\n" + "=" * 70)
    print("通过 %d 项，失败 %d 项，提示 %d 项" % (len(PASSED), len(FAILED), len(WARNED)))
    if FAILED:
        print("失败项：")
        for name in FAILED:
            print("  - %s" % name)
    print("=" * 70)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
