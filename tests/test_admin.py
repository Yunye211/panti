# -*- coding: utf-8 -*-
"""管理员：账号管理（登录、列表、新增、编辑、重置密码、停用、删除、越权）。"""
from conftest import login, post_form, post_json

GOOD_CODE = "a, b = map(int, input().split())\nprint(a + b)"

ADMIN = ("admin", "admin123")


def make_admin(app, username=ADMIN[0], password=ADMIN[1]):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(username=username, display_name="管理员", role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def make_student(app, username="stu_x", display_name="同学甲"):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        user = User(username=username, display_name=display_name, role="student")
        user.set_password("123456")
        db.session.add(user)
        db.session.commit()
        return user.id


def get_user(app, user_id):
    from app.extensions import db
    from app.models import User

    with app.app_context():
        return db.session.get(User, user_id)


def test_admin_login_and_dashboard(client, app):
    make_admin(app)
    resp = login(client, *ADMIN)
    assert resp.status_code == 302
    assert client.get("/admin/").status_code == 200
    # 管理员登录后首页直接进控制台
    assert client.get("/").status_code == 302


def test_admin_users_page_lists_accounts(client, app):
    make_admin(app)
    login(client, *ADMIN)
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "student" in body and "teacher" in body


def test_admin_creates_teacher_account(client, app):
    make_admin(app)
    login(client, *ADMIN)
    resp = post_form(client, "/admin/users/new", {
        "username": "tea_new", "display_name": "新教师", "role": "teacher", "password": "123456",
    })
    assert resp.status_code == 302
    with app.app_context():
        from app.models import User

        created = User.query.filter_by(username="tea_new").first()
        assert created is not None and created.role == "teacher"
    # 新账号可正常登录
    other = app.test_client()
    assert login(other, "tea_new", "123456").status_code == 302


def test_admin_edits_user(client, app):
    make_admin(app)
    uid = make_student(app)
    login(client, *ADMIN)
    resp = post_form(client, "/admin/users/%d/edit" % uid, {
        "username": "stu_x", "display_name": "已改名", "role": "teacher",
    })
    assert resp.status_code == 302
    user = get_user(app, uid)
    assert user.display_name == "已改名"
    assert user.role == "teacher"


def test_admin_resets_password(client, app):
    make_admin(app)
    uid = make_student(app)
    login(client, *ADMIN)
    resp = post_form(client, "/admin/users/%d/reset-password" % uid)
    assert resp.status_code == 302
    other = app.test_client()
    assert login(other, "stu_x", "123456").status_code == 302


def test_admin_deactivate_blocks_login(client, app):
    make_admin(app)
    uid = make_student(app)
    login(client, *ADMIN)
    assert post_form(client, "/admin/users/%d/toggle-active" % uid).status_code == 302
    assert get_user(app, uid).is_active is False

    other = app.test_client()
    resp = login(other, "stu_x", "123456")
    assert resp.status_code == 200
    assert "该账号已被停用" in resp.get_data(as_text=True)


def test_admin_deletes_user(client, app):
    make_admin(app)
    uid = make_student(app)
    login(client, *ADMIN)
    assert post_form(client, "/admin/users/%d/delete" % uid).status_code == 302
    assert get_user(app, uid) is None


def test_admin_keeps_last_admin(client, app):
    uid = make_admin(app)
    login(client, *ADMIN)
    resp = post_form(client, "/admin/users/%d/delete" % uid)
    assert resp.status_code == 302
    assert get_user(app, uid) is not None  # 最后一个管理员不能被删除


def test_non_admin_cannot_manage_users(client, app):
    make_admin(app)
    login(client, "student", "123456")
    assert client.get("/admin/users").status_code == 302
    assert client.get("/admin/").status_code == 302


def test_admin_can_use_teacher_pages(client, app):
    make_admin(app)
    login(client, *ADMIN)
    assert client.get("/teacher/problems").status_code == 200


def test_admin_can_view_any_submission(client, app):
    make_admin(app)
    login(client, "student", "123456")
    resp = post_json(client, "/api/judge", {"problem_id": 1, "code": GOOD_CODE})
    sub_id = resp.get_json()["submission_id"]

    adm = app.test_client()
    login(adm, *ADMIN)
    assert adm.get("/problems/submissions/%d" % sub_id).status_code == 200


def test_disabled_user_loses_active_session(client, app):
    make_admin(app)
    uid = make_student(app)

    stu = app.test_client()
    assert login(stu, "stu_x", "123456").status_code == 302
    assert stu.get("/").status_code == 200

    adm = app.test_client()
    login(adm, *ADMIN)
    assert post_form(adm, "/admin/users/%d/toggle-active" % uid).status_code == 302

    # 已登录会话在停用后立即失效
    resp = stu.get("/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_dashboard_warns_default_admin_password(client, app):
    make_admin(app)
    login(client, *ADMIN)
    body = client.get("/admin/").get_data(as_text=True)
    assert "初始密码" in body


def test_register_cannot_elevate_to_admin(client, app):
    resp = post_form(client, "/auth/register", {
        "username": "hacker", "password": "123456", "confirm": "123456", "role": "admin",
    })
    assert resp.status_code == 302
    with app.app_context():
        from app.models import User

        user = User.query.filter_by(username="hacker").first()
        assert user is not None and user.role == "student"
