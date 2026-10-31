# -*- coding: utf-8 -*-
"""API 判题/运行接口：鉴权、AC 判题入库、代码长度限制。"""
from conftest import login, post_json

GOOD_CODE = "a, b = map(int, input().split())\nprint(a + b)"


def test_api_judge_requires_login(client):
    resp = post_json(client, "/api/judge", {"problem_id": 1, "code": GOOD_CODE})
    assert resp.status_code == 302  # 未登录被重定向到登录页


def test_api_judge_ac_saves_submission(client, app):
    login(client, "student", "123456")
    resp = post_json(client, "/api/judge", {"problem_id": 1, "code": GOOD_CODE})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "AC"
    assert body["passed"] == 2
    assert body.get("submission_id") is not None

    from app.extensions import db
    from app.models import Submission

    with app.app_context():
        sub = db.session.get(Submission, body["submission_id"])
        assert sub is not None
        assert sub.status == "AC"
        assert sub.passed_count == 2


def test_api_judge_wa(client, app):
    login(client, "student", "123456")
    resp = post_json(client, "/api/judge", {"problem_id": 1, "code": "a, b = map(int, input().split())\nprint(a - b)"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "WA"
    assert body["passed"] == 0
    assert body.get("submission_id") is not None


def test_api_judge_unknown_problem(client):
    login(client, "student", "123456")
    resp = post_json(client, "/api/judge", {"problem_id": 999, "code": GOOD_CODE})
    assert resp.status_code == 404


def test_api_judge_code_too_long(client, tmp_path):
    from app import create_app

    db_path = tmp_path / "len.db"
    small = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "t",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///%s" % db_path,
            "MAX_CODE_LENGTH": 20,
        }
    )
    with small.app_context():
        from app.extensions import db
        from app.models import Problem, TestCase, User

        t = User(username="t1", role="teacher")
        t.set_password("123456")
        db.session.add(t)
        db.session.flush()
        p = Problem(title="P", description="d", author_id=t.id)
        db.session.add(p)
        db.session.flush()
        db.session.add(TestCase(problem_id=p.id, input_data="", expected_output=""))
        db.session.commit()

    c = small.test_client()
    from conftest import post_form

    post_form(c, "/auth/login", {"username": "t1", "password": "123456"})  # 表单登录
    resp = post_json(c, "/api/judge", {"problem_id": 1, "code": GOOD_CODE})
    assert resp.status_code == 400


def test_api_run_custom_input(client):
    login(client, "student", "123456")
    resp = post_json(client, "/api/run", {"code": "print(input().upper())", "stdin": "hi"})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "OK"
    assert body["stdout"].strip() == "HI"
