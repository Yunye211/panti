# -*- coding: utf-8 -*-
"""本轮优化点的单元测试：LIKE 转义 / ensure_owner 权限 / purge() 级联清理。"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.decorators import ensure_owner, like


# ============================================================
# 1. like() 通配符转义（纯函数，无需数据库）
# ============================================================


class TestLikeEscape:
    def test_plain_keyword(self):
        pat, esc = like("hello")
        assert pat == "%hello%"
        assert esc == "\\"

    def test_escape_percent(self):
        pat, esc = like("100%")
        assert pat == "%100\\%%"
        assert esc == "\\"

    def test_escape_underscore(self):
        pat, esc = like("a_b")
        assert pat == "%a\\_b%"

    def test_escape_backslash(self):
        pat, esc = like("path\\to")
        assert pat == "%path\\\\to%"

    def test_escape_all_metachars(self):
        pat, esc = like("%_\\mix")
        assert pat == "%\\%\\_\\\\mix%"

    def test_empty_string(self):
        pat, esc = like("")
        assert pat == "%%"

    def test_only_wildcards(self):
        pat, esc = like("%__%")
        assert pat == "%\\%\\_\\_\\%%"


# ============================================================
# 2. ensure_owner 权限检查
# ============================================================


class TestEnsureOwner:
    def test_matching_owner_passes(self, app, client):
        from app.extensions import db
        from app.models import User

        with app.app_context():
            u = db.session.get(User, 1)
        with client.session_transaction() as sess:
            sess["_user_id"] = str(u.id)
        with app.test_request_context():
            from flask_login import login_user
            login_user(u)

            class Fake:
                teacher_id = u.id

            ensure_owner(Fake())

    def test_non_owner_aborts_403(self, app, client):
        from app.extensions import db
        from app.models import User

        with app.app_context():
            u = db.session.get(User, 1)
        with app.test_request_context():
            from flask_login import login_user
            login_user(u)

            class Fake:
                teacher_id = 99999

            with pytest.raises(Exception) as exc_info:
                ensure_owner(Fake())
            assert getattr(exc_info.value, "code", None) == 403

    def test_none_object_skipped(self, app, client):
        from app.extensions import db
        from app.models import User

        with app.app_context():
            u = db.session.get(User, 1)
        with app.test_request_context():
            from flask_login import login_user
            login_user(u)
            ensure_owner(None)

    def test_custom_attr_author_id(self, app, client):
        from app.extensions import db
        from app.models import User

        with app.app_context():
            u = db.session.get(User, 1)
        with app.test_request_context():
            from flask_login import login_user
            login_user(u)

            class Fake:
                author_id = u.id

            ensure_owner(Fake(), attr="author_id")


# ============================================================
# 3. Model.purge() 级联清理
# ============================================================


def _make_seeded_fixture(app):
    """创建完整的关联数据链：teacher → classroom → homework → problem → submission。"""
    from app.extensions import db
    from app.models import (
        Classroom,
        Homework,
        Problem,
        Submission,
        TestCase,
        User,
        homework_problems,
    )

    with app.app_context():
        teacher = User(username="t_purge", display_name="T", role="teacher")
        teacher.set_password("123456")
        stu_a = User(username="s_purge_a", display_name="SA", role="student")
        stu_a.set_password("123456")
        stu_b = User(username="s_purge_b", display_name="SB", role="student")
        stu_b.set_password("123456")
        db.session.add_all([teacher, stu_a, stu_b])
        db.session.flush()

        room = Classroom(
            name="Purge班", join_code="PURGE01", teacher_id=teacher.id
        )
        room.students.extend([stu_a, stu_b])
        db.session.add(room)
        db.session.flush()

        prob = Problem(
            title="Purge题",
            description="用于测试清理",
            difficulty="easy",
            author_id=teacher.id,
        )
        db.session.add(prob)
        db.session.flush()
        db.session.add(TestCase(problem_id=prob.id, input_data="1", expected_output="1"))

        hw = Homework(
            title="Purge作业",
            description="",
            classroom_id=room.id,
            teacher_id=teacher.id,
            due_at=datetime.now() + timedelta(days=7),
        )
        hw.problems.append(prob)
        db.session.add(hw)
        db.session.flush()

        sub_a = Submission(
            user_id=stu_a.id,
            problem_id=prob.id,
            homework_id=hw.id,
            code="print(1)",
            status="AC",
            source="homework",
        )
        sub_b = Submission(
            user_id=stu_b.id,
            problem_id=prob.id,
            code="print(2)",
            status="WA",
            source="practice",
        )
        db.session.add_all([sub_a, sub_b])
        db.session.commit()

        return {
            "teacher_id": teacher.id,
            "stu_a_id": stu_a.id,
            "stu_b_id": stu_b.id,
            "room_id": room.id,
            "prob_id": prob.id,
            "hw_id": hw.id,
            "sub_a_id": sub_a.id,
            "sub_b_id": sub_b.id,
        }


class TestProblemPurge:
    def test_problem_purge_removes_submissions_and_links(self, app):
        ids = _make_seeded_fixture(app)
        from app.extensions import db
        from app.models import Problem, Submission, homework_problems

        with app.app_context():
            prob = db.session.get(Problem, ids["prob_id"])
            assert Submission.query.filter_by(problem_id=prob.id).count() == 2
            db.session.execute(
                homework_problems.select().where(homework_problems.c.problem_id == prob.id)
            )
            prob.purge()
            db.session.commit()

            assert Submission.query.filter_by(problem_id=prob.id).count() == 0
            link_count = db.session.execute(
                homework_problems.delete().where(homework_problems.c.problem_id == prob.id)
            ).rowcount
            db.session.rollback()
            assert link_count == 0


class TestHomeworkPurge:
    def test_homework_purge_removes_submissions_and_links(self, app):
        ids = _make_seeded_fixture(app)
        from app.extensions import db
        from app.models import Homework, Submission, homework_problems

        with app.app_context():
            hw = db.session.get(Homework, ids["hw_id"])
            assert Submission.query.filter_by(homework_id=hw.id).count() == 1
            hw.purge()
            db.session.commit()

            assert Submission.query.filter_by(homework_id=hw.id).count() == 0
            rows = db.session.execute(
                homework_problems.select().where(homework_problems.c.homework_id == hw.id)
            ).all()
            assert len(rows) == 0


class TestClassroomPurge:
    def test_classroom_purge_cascades_homeworks(self, app):
        ids = _make_seeded_fixture(app)
        from app.extensions import db
        from app.models import Classroom, Homework, Submission, classroom_students

        with app.app_context():
            room = db.session.get(Classroom, ids["room_id"])
            assert Homework.query.filter_by(classroom_id=room.id).count() == 1
            assert Submission.query.filter_by(homework_id=ids["hw_id"]).count() == 1

            room.purge()
            db.session.commit()

            assert Submission.query.filter_by(homework_id=ids["hw_id"]).count() == 0
            assert Homework.query.filter_by(classroom_id=room.id).count() == 0
            rows = db.session.execute(
                classroom_students.select().where(classroom_students.c.classroom_id == room.id)
            ).all()
            assert len(rows) == 0


class TestUserPurge:
    def test_user_purge_teacher_removes_its_room(self, app):
        ids = _make_seeded_fixture(app)
        from app.extensions import db
        from app.models import Classroom, Submission, User

        with app.app_context():
            teacher = db.session.get(User, ids["teacher_id"])
            assert Classroom.query.filter_by(teacher_id=teacher.id).count() == 1
            assert Submission.query.count() == 2
            assert Submission.query.filter_by(homework_id=ids["hw_id"]).count() == 1

            teacher.purge()
            db.session.commit()

            assert Classroom.query.filter_by(teacher_id=teacher.id).count() == 0
            assert Submission.query.filter_by(homework_id=ids["hw_id"]).count() == 0
            assert Submission.query.count() == 1

    def test_user_purge_student_removes_its_submissions(self, app):
        ids = _make_seeded_fixture(app)
        from app.extensions import db
        from app.models import Submission, User, classroom_students

        with app.app_context():
            stu = db.session.get(User, ids["stu_a_id"])
            assert Submission.query.filter_by(user_id=stu.id).count() == 1

            stu.purge()
            db.session.commit()

            assert Submission.query.filter_by(user_id=stu.id).count() == 0
            rows = db.session.execute(
                classroom_students.select().where(classroom_students.c.student_id == stu.id)
            ).all()
            assert len(rows) == 0
