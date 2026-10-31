# -*- coding: utf-8 -*-
"""页面级冒烟测试 + 安全响应头 + 静态资源缓存 + 错误页。"""
from conftest import login, post_form


def test_anonymous_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_login_page_ok(client):
    resp = client.get("/auth/login")
    assert resp.status_code == 200


def test_student_pages(client):
    login(client, "student", "123456")
    for path in ("/", "/problems/", "/problems/1", "/problems/practice/setup", "/problems/submissions/"):
        resp = client.get(path)
        assert resp.status_code == 200, "%s -> %s" % (path, resp.status_code)


def test_teacher_pages(client):
    login(client, "teacher", "123456")
    for path in ("/teacher/problems", "/teacher/classes", "/teacher/homeworks"):
        resp = client.get(path)
        assert resp.status_code == 200, "%s -> %s" % (path, resp.status_code)


def test_problem_detail_404(client):
    login(client, "student", "123456")
    assert client.get("/problems/9999").status_code == 404


def test_error_page_404(client):
    resp = client.get("/no-such-page-xyz")
    assert resp.status_code == 404
    assert b"404" in resp.data


def test_security_headers(client):
    resp = client.get("/auth/login")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers.get("Permissions-Policy", "")


def test_static_asset_cached(client):
    resp = client.get("/static/vendor/codemirror/codemirror.min.js")
    assert resp.status_code == 200
    assert "max-age=3600" in (resp.headers.get("Cache-Control") or "")


def test_edit_problem_without_testcase_fields_keeps_existing_cases(app, client):
    """BUG-001 回归：编辑题目仅提交标题（不带用例字段）不得清空既有测试用例。"""
    from app.extensions import db
    from app.models import Problem

    login(client, "teacher", "123456")
    with app.app_context():
        problem = db.session.scalars(
            db.select(Problem).where(Problem.title == "A+B 问题")
        ).one()
        problem_id = problem.id

    resp = post_form(
        client,
        "/teacher/problems/%d/edit" % problem_id,
        {"title": "A+B 问题-改"},  # 只提交标题，不带 tc_input/tc_output/tc_sample
    )
    assert resp.status_code == 302

    with app.app_context():
        db.session.expire_all()
        p = db.session.get(Problem, problem_id)
        assert p.title == "A+B 问题-改"
        assert len(p.test_cases) == 2  # 原有用例未被清空


def test_edit_problem_with_testcase_fields_replaces_cases(app, client):
    """对照：编辑时显式提交用例字段仍按全量替换语义生效。"""
    from app.extensions import db
    from app.models import Problem

    login(client, "teacher", "123456")
    with app.app_context():
        problem = db.session.scalars(
            db.select(Problem).where(Problem.title == "A+B 问题")
        ).one()
        problem_id = problem.id

    resp = post_form(
        client,
        "/teacher/problems/%d/edit" % problem_id,
        {
            "title": "A+B 问题-改",
            "tc_input": ["2 3"],
            "tc_output": ["5"],
            "tc_sample": ["0"],
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        db.session.expire_all()
        p = db.session.get(Problem, problem_id)
        assert len(p.test_cases) == 1
        assert p.test_cases[0].input_data == "2 3"
        assert p.test_cases[0].expected_output == "5"
