# -*- coding: utf-8 -*-
"""页面级冒烟测试 + 安全响应头 + 静态资源缓存 + 错误页。"""
from conftest import login


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
