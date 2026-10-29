"""自动判题：把学生代码与题目的测试用例逐一比对。"""
from .models import STATUS_LABELS
from .sandbox import check_syntax, run_code


def normalize(text):
    """忽略行尾空格与末尾多余空行后比较。"""
    lines = [line.rstrip() for line in (text or "").replace("\r\n", "\n").strip().split("\n")]
    return "\n".join(lines).strip()


def judge(code, test_cases, time_limit=2, total_limit=15, memory_mb=256):
    """返回判题结果字典。

    status: AC 通过 / WA 答案错误 / RE 运行时错误 / CE 语法错误 / TLE 运行超时
    """
    code = code or ""
    if not code.strip():
        return {
            "status": "CE",
            "status_label": STATUS_LABELS["CE"],
            "passed": 0,
            "total": len(test_cases),
            "max_time_ms": 0,
            "message": "代码不能为空。",
            "cases": [],
        }

    ok, msg = check_syntax(code)
    if not ok:
        return {
            "status": "CE",
            "status_label": STATUS_LABELS["CE"],
            "passed": 0,
            "total": len(test_cases),
            "max_time_ms": 0,
            "message": msg,
            "cases": [],
        }

    if not test_cases:
        result = run_code(code, "", time_limit=time_limit, memory_mb=memory_mb)
        return {
            "status": "AC" if result.status == "OK" else ("TLE" if result.status == "TLE" else "RE"),
            "status_label": STATUS_LABELS.get("AC"),
            "passed": 1 if result.status == "OK" else 0,
            "total": 1,
            "max_time_ms": result.time_ms,
            "message": "" if result.status == "OK" else result.stderr,
            "cases": [{
                "index": 1,
                "ok": result.status == "OK",
                "input": "",
                "expected": "",
                "actual": result.stdout[:2000],
                "error": result.stderr,
                "time_ms": result.time_ms,
            }],
        }

    cases = []
    passed = 0
    status = "AC"
    message = ""
    max_time = 0
    total_used = 0.0

    for idx, case in enumerate(test_cases, start=1):
        remain = total_limit - total_used
        if remain <= 0.2:
            cases.append({
                "index": idx, "ok": False, "input": case.input_data,
                "expected": case.expected_output, "actual": "",
                "error": "总运行时间超出限制，后续测试点未执行。", "time_ms": 0,
            })
            continue
        limit = min(time_limit, remain)
        result = run_code(code, case.input_data or "", time_limit=limit, memory_mb=memory_mb)
        total_used += max(result.time_ms, 0) / 1000.0
        max_time = max(max_time, result.time_ms)
        ok_case = result.status == "OK" and normalize(result.stdout) == normalize(case.expected_output)
        if ok_case:
            passed += 1
        else:
            if result.status == "TLE":
                status = "TLE"
            elif result.status == "RE":
                status = status if status == "TLE" else "RE"
            else:
                status = status if status in ("TLE", "RE") else "WA"
            if not message:
                message = result.stderr or ("第 %d 个测试点输出不一致。" % idx)

        cases.append({
            "index": idx,
            "ok": ok_case,
            "input": case.input_data or "",
            "expected": case.expected_output or "",
            "actual": result.stdout[:2000],
            "error": result.stderr,
            "time_ms": result.time_ms,
        })

    return {
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "passed": passed,
        "total": len(test_cases),
        "max_time_ms": max_time,
        "message": message,
        "cases": cases,
    }
