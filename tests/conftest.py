# -*- coding: utf-8 -*-
"""pytest 公共夹具：独立 SQLite 测试库 + 最小种子数据 + CSRF 感知的测试客户端。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app import create_app

TEST_CSRF = "test-csrf-token"


def _seed(app):
    from app.extensions import db
    from app.models import KnowledgePoint, Problem, TestCase, User

    teacher = User(username="teacher", display_name="教师", role="teacher")
    teacher.set_password("123456")
    student = User(username="student", display_name="学生", role="student")
    student.set_password("123456")
    db.session.add_all([teacher, student])
    db.session.flush()

    kp = KnowledgePoint(name="入门", description="基础题目")
    db.session.add(kp)
    db.session.flush()

    p = Problem(
        title="A+B 问题",
        description="输入两个整数，输出它们的和",
        difficulty="easy",
        author_id=teacher.id,
        starter_code="",
        reference_code="",
    )
    db.session.add(p)
    db.session.flush()
    db.session.add_all(
        [
            TestCase(problem_id=p.id, input_data="1 2", expected_output="3", is_sample=True),
            TestCase(problem_id=p.id, input_data="10 20", expected_output="30", is_sample=False),
        ]
    )
    p.tags.append(kp)
    db.session.commit()


@pytest.fixture()
def app(tmp_path):
    """每个测试独立的 SQLite 文件库，互不干扰、不碰线上数据库。"""
    db_path = tmp_path / "test.db"
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///%s" % db_path,
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "JUDGE_TIME_LIMIT": 2,
            "JUDGE_TOTAL_TIME": 15,
            "MAX_CODE_LENGTH": 20000,
        }
    )
    with application.app_context():
        _seed(application)
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


def set_csrf(client):
    """把已知的 CSRF token 注入会话，便于表单/接口测试。"""
    with client.session_transaction() as sess:
        sess["csrf_token"] = TEST_CSRF


def post_form(client, url, data=None, **kwargs):
    """带 CSRF token 的表单 POST。"""
    set_csrf(client)
    data = dict(data or {})
    data.setdefault("csrf_token", TEST_CSRF)
    return client.post(url, data=data, **kwargs)


def post_json(client, url, payload, **kwargs):
    """带 CSRF token 的 JSON POST。"""
    set_csrf(client)
    return client.post(
        url, json=payload, headers={"X-CSRF-Token": TEST_CSRF}, **kwargs
    )


def login(client, username="student", password="123456"):
    return post_form(client, "/auth/login", {"username": username, "password": password})
