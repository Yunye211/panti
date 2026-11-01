# -*- coding: utf-8 -*-
"""客观题（选择题 / 判断题 / 填空题）：创建、展示、作答与自动评分。"""
from conftest import login, post_form, post_json

DANGEROUS_CODE = "import os\nos.system('echo hacked')\nprint(1)"


def create_problem(client, qtype, title, **fields):
    """教师端创建题目，返回题目 id。"""
    data = {
        "title": title,
        "description": "客观题自动化测试",
        "difficulty": "easy",
        "type": qtype,
        "subject": "信息技术",
        "stage": "初中",
    }
    data.update(fields)
    resp = post_form(client, "/teacher/problems/new", data)
    assert resp.status_code == 302
    return int([p for p in resp.headers["Location"].split("/") if p.isdigit()][-1])


def answer(client, problem_id, payload, code=""):
    body = {"problem_id": problem_id, "answer": payload}
    if code:
        body["code"] = code
    return post_json(client, "/api/judge", body)


# ----------------------------- 选择题 -----------------------------


def test_choice_page_shows_options(client, app):
    login(client, "teacher", "123456")
    pid = create_problem(
        client, "choice", "Python 保留字",
        option_content=["print", "for", "if"], option_correct=["B"],
    )
    body = client.get("/problems/%d" % pid).get_data(as_text=True)
    assert body  # 详情页渲染成功
    assert "print" in body and "for" in body and "if" in body


def test_choice_correct_and_wrong(client, app):
    login(client, "teacher", "123456")
    pid = create_problem(
        client, "choice", "循环关键字",
        option_content=["print", "for", "if"], option_correct=["B"],
    )

    stu = app.test_client()
    login(stu, "student", "123456")
    ok = answer(stu, pid, {"choices": ["B"]})
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["status"] == "AC" and body["score"] == 100

    bad = answer(stu, pid, {"choices": ["A"]}).get_json()
    assert bad["status"] == "WA" and bad["score"] == 0


def test_choice_multi_answer(client, app):
    login(client, "teacher", "123456")
    pid = create_problem(
        client, "choice", "多选：哪些是容器类型",
        option_content=["list", "int", "dict"], option_correct=["A", "C"],
    )
    stu = app.test_client()
    login(stu, "student", "123456")
    assert answer(stu, pid, {"choices": ["A", "C"]}).get_json()["status"] == "AC"
    assert answer(stu, pid, {"choices": ["A"]}).get_json()["status"] == "WA"


# ----------------------------- 判断题 -----------------------------


def test_judge_question(client, app):
    login(client, "teacher", "123456")
    pid = create_problem(client, "judge", "Python 是解释型语言", judge_correct="T")

    stu = app.test_client()
    login(stu, "student", "123456")
    assert answer(stu, pid, {"judge": "对"}).get_json()["status"] == "AC"
    assert answer(stu, pid, {"judge": "false"}).get_json()["status"] == "WA"


# ----------------------------- 填空题 -----------------------------


def test_fill_question(client, app):
    login(client, "teacher", "123456")
    pid = create_problem(
        client, "fill", "填空：圆周率与语言名",
        blank_answer=["3.14", "Python"],
    )
    stu = app.test_client()
    login(stu, "student", "123456")

    full = answer(stu, pid, {"answers": ["3.14", "Python"]}).get_json()
    assert full["status"] == "AC" and full["score"] == 100

    partial = answer(stu, pid, {"answers": ["3.14", "Java"]}).get_json()
    assert partial["status"] == "WA" and partial["score"] == 50
    assert partial["passed_count"] == 1 and partial["total_count"] == 2


# ----------------------------- 安全：客观题不进沙箱 -----------------------------


def test_objective_answer_never_runs_code(client, app):
    login(client, "teacher", "123456")
    pid = create_problem(client, "judge", "列表可变吗", judge_correct="T")

    stu = app.test_client()
    login(stu, "student", "123456")
    body = answer(stu, pid, {"judge": "对"}, code=DANGEROUS_CODE).get_json()
    # 客观题只比对答案，不启动判题子进程（耗时始终为 0）
    assert body["max_time_ms"] == 0
    assert body["status"] == "AC"
