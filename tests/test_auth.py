# -*- coding: utf-8 -*-
"""注册 / 登录 / 登出 / 开放重定向 / 登录限流。"""
from conftest import login, post_form, set_csrf


def test_register_page(client):
    resp = client.get("/auth/register")
    assert resp.status_code == 200


def test_register_success(client, app):
    resp = post_form(
        client,
        "/auth/register",
        {"username": "newbie", "display_name": "新人", "password": "pass123", "confirm": "pass123", "role": "student"},
    )
    assert resp.status_code == 302
    from app.models import User

    with app.app_context():
        assert User.query.filter_by(username="newbie").one().role == "student"


def test_register_duplicate_username(client):
    resp = post_form(
        client,
        "/auth/register",
        {"username": "student", "display_name": "x", "password": "pass123", "confirm": "pass123", "role": "student"},
    )
    assert "该用户名已被注册" in resp.get_data(as_text=True)


def test_register_weak_password(client):
    resp = post_form(
        client,
        "/auth/register",
        {"username": "weak", "display_name": "x", "password": "123", "confirm": "123", "role": "student"},
    )
    assert resp.status_code == 200  # 未重定向即未创建


def test_register_teacher_wrong_invite(client):
    resp = post_form(
        client,
        "/auth/register",
        {"username": "fake_teacher", "display_name": "x", "password": "pass123", "confirm": "pass123", "role": "teacher", "invite_code": "wrong"},
    )
    assert resp.status_code == 200
    assert "教师注册码不正确" in resp.get_data(as_text=True)


def test_login_success_redirects_home(client):
    resp = login(client, "student", "123456")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_login_wrong_password(client):
    resp = post_form(client, "/auth/login", {"username": "nobody", "password": "bad"})
    assert resp.status_code == 200
    assert "用户名或密码错误" in resp.get_data(as_text=True)


def test_login_lockout_after_5_fails(client):
    for _ in range(5):
        post_form(client, "/auth/login", {"username": "lockuser", "password": "bad"})
    resp = post_form(client, "/auth/login", {"username": "lockuser", "password": "bad"})
    assert "登录失败次数过多" in resp.get_data(as_text=True)


def test_logout(client):
    login(client)
    resp = client.get("/auth/logout")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_no_open_redirect(client):
    resp = post_form(
        client,
        "/auth/login?next=//evil.com",
        {"username": "student", "password": "123456"},
    )
    assert resp.status_code == 302
    assert "evil.com" not in resp.headers["Location"]


def test_csrf_rejects_missing_token(client):
    resp = client.post("/auth/login", data={"username": "student", "password": "123456"})
    assert resp.status_code == 400
