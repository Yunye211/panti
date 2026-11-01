"""自动判题：把学生代码与题目的测试用例逐一比对。"""
import json

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


def grade_objective(problem, user_answer):
    """客观题判题（choice / judge / fill）。

    参数:
        problem: Problem 实例，需提供 type 与 standard_answer 属性
        user_answer: dict，按题型不同：
            choice -> {"choices": ["A"]} 或 {"choices": ["A", "C"]}
            judge  -> {"judge": "true"/"false"/"对"/"错"/"T"/"F"}
            fill   -> {"answers": ["3.14", "python"]}

    返回与 judge() 对齐的结构：
        {"status": "AC"|"WA", "passed": n, "total": m,
         "passed_count": n, "total_count": m,
         "score": 0|100, "message": str, "detail": dict}
    """
    qtype = problem.type or "code"
    std_raw = problem.standard_answer

    if not std_raw:
        return _obj_fail("标准答案格式异常")

    try:
        std = json.loads(std_raw)
    except (ValueError, TypeError):
        return _obj_fail("标准答案格式异常")

    try:
        if qtype == "choice":
            return _obj_choice(std, user_answer)
        if qtype == "judge":
            return _obj_judge(std, user_answer)
        if qtype == "fill":
            return _obj_fill(std, user_answer)
    except Exception as exc:
        return _obj_fail("判题异常：%s" % exc)

    return _obj_fail("未知题型：%s" % qtype)


def _obj_fail(message):
    return {
        "status": "WA",
        "score": 0,
        "passed_count": 0,
        "total_count": 1,
        "passed": 0,
        "total": 1,
        "message": message,
        "detail": {},
    }


def _obj_choice(std, user_answer):
    if not isinstance(std, dict) or "correct" not in std:
        return _obj_fail("标准答案格式异常")

    is_multi = bool(std.get("multi", False))
    correct = set(str(c).strip().upper() for c in std.get("correct", []))
    picked = set(str(c).strip().upper() for c in (user_answer or {}).get("choices", []))

    if not correct:
        return _obj_fail("标准答案格式异常")

    matched = picked == correct
    return _obj_build(matched, 1, 100, "选择题" + ("（多选）" if is_multi else ""))


def _obj_judge(std, user_answer):
    if not isinstance(std, dict) or "correct" not in std:
        return _obj_fail("标准答案格式异常")

    correct_raw = str(std["correct"][0]).strip().lower() if std["correct"] else ""
    correct_norm = correct_raw in ("true", "t", "对", "1", "yes")

    user_raw = str((user_answer or {}).get("judge", "")).strip().lower()
    user_norm = user_raw in ("true", "t", "对", "1", "yes")

    matched = correct_norm == user_norm and user_raw != ""
    return _obj_build(matched, 1, 100, "判断题")


def _obj_fill(std, user_answer):
    if not isinstance(std, list) or len(std) == 0:
        return _obj_fail("标准答案格式异常")

    normalized = []
    for item in std:
        if isinstance(item, list):
            normalized.append({normalize(str(a)) for a in item})
        else:
            normalized.append({normalize(str(item))})

    answers = (user_answer or {}).get("answers", [])
    if not isinstance(answers, list):
        return _obj_fail("标准答案格式异常")

    total = len(normalized)
    passed = 0
    for i, accept_set in enumerate(normalized):
        got_norm = normalize(str(answers[i])) if i < len(answers) else ""
        if got_norm and got_norm in accept_set:
            passed += 1

    full = passed == total
    score = round(passed * 100 / total) if total else 0
    return {
        "status": "AC" if full else "WA",
        "score": score,
        "passed_count": passed,
        "total_count": total,
        "passed": passed,
        "total": total,
        "message": "填空题 %d/%d 空正确" % (passed, total),
        "detail": {"passed": passed, "total": total},
    }


def _obj_build(matched, total, score_full, label):
    return {
        "status": "AC" if matched else "WA",
        "score": score_full if matched else 0,
        "passed_count": total if matched else 0,
        "total_count": total,
        "passed": total if matched else 0,
        "total": total,
        "message": "%s判题结果：%s" % (label, "正确" if matched else "错误"),
        "detail": {},
    }
