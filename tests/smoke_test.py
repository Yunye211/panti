"""功能回归测试：登录、页面访问、判题五态、教师录入题目与发布作业。

运行：python tests/smoke_test.py
"""
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Classroom, Homework, Problem, Submission, homework_problems  # noqa: E402

PASSED, FAILED = [], []


def ok(name, detail=""):
    PASSED.append(name)
    print("  [PASS] %-42s %s" % (name, detail))


def fail(name, detail=""):
    FAILED.append(name)
    print("  [FAIL] %-42s %s" % (name, detail))


def token(cli, url="/auth/login"):
    html = cli.get(url).get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1) if m else ""


def check(cli, url, expect=200):
    r = cli.get(url)
    if r.status_code == expect:
        ok("GET %s" % url, str(r.status_code))
    else:
        fail("GET %s" % url, "%s (expect %s)" % (r.status_code, expect))
    return r


def main():
    app = create_app()
    student = app.test_client()
    teacher = app.test_client()

    print("\n[1] 学生端")
    st = token(student)
    r = student.post("/auth/login", data={"username": "student", "password": "123456", "csrf_token": st}, follow_redirects=False)
    ok("学生登录", str(r.status_code)) if r.status_code == 302 else fail("学生登录", str(r.status_code))

    for url in ["/", "/problems/", "/problems/1", "/problems/practice/setup",
                "/homeworks/", "/homeworks/1", "/homeworks/1/problems/2",
                "/problems/submissions/", "/profile"]:
        check(student, url)

    r = student.post("/problems/practice/setup", data={"difficulty": "easy", "count": "3", "csrf_token": st}, follow_redirects=False)
    ok("开始专项练习", str(r.status_code)) if r.status_code == 302 else fail("开始专项练习", str(r.status_code))
    check(student, "/problems/practice/1")

    print("\n[2] 判题结果")
    with app.app_context():
        pid = Problem.query.filter_by(title="A + B 问题").first().id

    for name, code, expect in [
        ("正确代码", "a, b = map(int, input().split())\nprint(a + b)", "AC"),
        ("答案错误", "a, b = map(int, input().split())\nprint(a - b)", "WA"),
        ("语法错误", "print('hello'\n", "CE"),
        ("运行时错误", "x = 1 / 0\n", "RE"),
        ("运行超时", "while True:\n    pass\n", "TLE"),
    ]:
        r = student.post("/api/judge", json={"problem_id": pid, "code": code, "source": "free"},
                         headers={"X-CSRF-Token": st})
        data = r.get_json() or {}
        if data.get("status") == expect:
            ok(name, "%s (%s/%s)" % (expect, data.get("passed"), data.get("total")))
        else:
            fail(name, "期望 %s 实得 %s" % (expect, data.get("status")))

    r = student.post("/api/run", json={"code": "s=input()\nprint(s.upper())", "stdin": "abc"},
                     headers={"X-CSRF-Token": st})
    data = r.get_json() or {}
    ok("自定义输入运行", data.get("stdout", "").strip()) if data.get("stdout", "").strip() == "ABC" else fail("自定义输入运行", str(data))

    print("\n[3] 教师端")
    tc = token(teacher)
    teacher.post("/auth/login", data={"username": "teacher", "password": "123456", "csrf_token": tc})
    for url in ["/", "/teacher/problems", "/teacher/problems/new", "/teacher/problems/1/edit",
                "/teacher/problems/1/preview", "/teacher/classes", "/teacher/classes/1",
                "/teacher/homeworks", "/teacher/homeworks/1", "/teacher/stats", "/teacher/submissions"]:
        check(teacher, url)

    print("\n[4] 写入流程")
    with app.app_context():
        room_id = Classroom.query.first().id

    r = teacher.post("/teacher/problems/new", data={
        "csrf_token": tc, "title": "回归测试题目", "description": "输出乘积",
        "difficulty": "easy", "new_tags": "数学运算",
        "starter_code": "a, b = map(int, input().split())\n",
        "reference_code": "a, b = map(int, input().split())\nprint(a * b)",
        "tc_input": ["2 3", "4 5"], "tc_output": ["6", "20"], "tc_sample": ["0"],
    }, follow_redirects=False)
    ok("录入题目", str(r.status_code)) if r.status_code == 302 else fail("录入题目", str(r.status_code))

    with app.app_context():
        p = Problem.query.filter_by(title="回归测试题目").first()
        new_pid = p.id
        ok("测试用例与知识点", "%d 个测试点 / %s" % (len(p.test_cases), [t.name for t in p.tags]))

    r = teacher.post("/api/judge", json={"problem_id": new_pid, "code": "a, b = map(int, input().split())\nprint(a * b)", "save": False},
                     headers={"X-CSRF-Token": tc})
    ok("教师试做验证", (r.get_json() or {}).get("status", "")) if (r.get_json() or {}).get("status") == "AC" else fail("教师试做验证", str(r.get_json()))

    r = teacher.post("/teacher/homeworks", data={
        "csrf_token": tc, "title": "回归测试作业", "classroom_id": room_id,
        "due_at": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
        "problems": [new_pid],
    }, follow_redirects=False)
    ok("发布作业", str(r.status_code)) if r.status_code == 302 else fail("发布作业", str(r.status_code))

    with app.app_context():
        hw_id = Homework.query.filter_by(title="回归测试作业").first().id

    r = student.post("/api/judge", json={
        "problem_id": new_pid, "homework_id": hw_id,
        "code": "a, b = map(int, input().split())\nprint(a * b)", "source": "homework"},
        headers={"X-CSRF-Token": st})
    data = r.get_json() or {}
    ok("学生提交作业并入库", "submission_id=%s" % data.get("submission_id")) if data.get("submission_id") else fail("学生提交作业并入库", str(data))

    check(teacher, "/teacher/homeworks/%d" % hw_id)
    check(student, "/homeworks/%d" % hw_id)

    # 清理
    with app.app_context():
        Submission.query.filter_by(homework_id=hw_id).delete()
        db.session.execute(homework_problems.delete().where(homework_problems.c.homework_id == hw_id))
        hw = db.session.get(Homework, hw_id)
        if hw:
            db.session.delete(hw)
        p = db.session.get(Problem, new_pid)
        if p:
            db.session.delete(p)
        db.session.commit()

    print("\n" + "=" * 66)
    print("功能回归：通过 %d 项，失败 %d 项" % (len(PASSED), len(FAILED)))
    for name in FAILED:
        print("  - %s" % name)
    print("=" * 66)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
