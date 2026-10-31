import random
import string
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from .. import db
from ..decorators import teacher_required
from ..models import (
    DIFFICULTIES,
    STATUS_LABELS,
    Classroom,
    ClassroomStudent,
    Homework,
    KnowledgePoint,
    Problem,
    Submission,
    TestCase,
    User,
    homework_problems,
)

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher", template_folder="../templates")


def _parse_dt(value):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _generate_join_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = db.session.scalar(select(Classroom).where(Classroom.join_code == code))
        if not exists:
            return code


def _sync_tags(problem, tag_ids, new_tag_text=""):
    tags = []
    for tid in tag_ids:
        kp = db.session.get(KnowledgePoint, int(tid))
        if kp:
            tags.append(kp)
    for raw in (new_tag_text or "").replace("，", ",").split(","):
        name = raw.strip()
        if not name:
            continue
        kp = db.session.scalar(select(KnowledgePoint).where(KnowledgePoint.name == name))
        if not kp:
            kp = KnowledgePoint(name=name)
            db.session.add(kp)
            db.session.flush()
        tags.append(kp)
    problem.tags = tags


def _sync_test_cases(problem, inputs, outputs, sample_flags):
    problem.test_cases.clear()
    db.session.flush()
    for i, out in enumerate(outputs):
        stdin_data = inputs[i] if i < len(inputs) else ""
        tc = TestCase(
            problem_id=problem.id,
            input_data=stdin_data,
            expected_output=out,
            is_sample=str(i) in sample_flags,
        )
        db.session.add(tc)


# ----------------------------- 题库管理 -----------------------------


@teacher_bp.route("/problems")
@login_required
@teacher_required
def problems():
    keyword = (request.args.get("q") or "").strip()
    difficulty = (request.args.get("difficulty") or "").strip()
    tag_id = request.args.get("tag", type=int)
    only_mine = request.args.get("mine") == "1"

    stmt = select(Problem)
    if keyword:
        stmt = stmt.where(Problem.title.like("%%%s%%" % keyword))
    if difficulty in DIFFICULTIES:
        stmt = stmt.where(Problem.difficulty == difficulty)
    if tag_id:
        stmt = stmt.where(Problem.tags.any(KnowledgePoint.id == tag_id))
    if only_mine:
        stmt = stmt.where(Problem.author_id == current_user.id)

    problems = db.session.scalars(
        stmt.order_by(Problem.id.desc()).options(
            selectinload(Problem.tags), selectinload(Problem.test_cases)
        )
    ).all()
    return render_template(
        "teacher/problems.html",
        problems=problems,
        tags=db.session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.name)).all(),
        difficulties=DIFFICULTIES,
        keyword=keyword,
        difficulty=difficulty,
        tag_id=tag_id,
        only_mine=only_mine,
    )


@teacher_bp.route("/problems/new", methods=["GET", "POST"])
@login_required
@teacher_required
def problem_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("题目标题不能为空。", "danger")
            return render_template("teacher/problem_form.html", problem=None, tags=_all_tags(), difficulties=DIFFICULTIES)

        problem = Problem(
            title=title,
            description=request.form.get("description") or "",
            difficulty=request.form.get("difficulty") or "easy",
            starter_code=request.form.get("starter_code") or "",
            reference_code=request.form.get("reference_code") or "",
            author_id=current_user.id,
        )
        db.session.add(problem)
        db.session.flush()
        _sync_tags(problem, request.form.getlist("tags"), request.form.get("new_tags", ""))
        _sync_test_cases(
            problem,
            request.form.getlist("tc_input"),
            request.form.getlist("tc_output"),
            set(request.form.getlist("tc_sample")),
        )
        db.session.commit()
        flash("题目已创建。", "success")
        return redirect(url_for("teacher.problem_edit", problem_id=problem.id))

    return render_template("teacher/problem_form.html", problem=None, tags=_all_tags(), difficulties=DIFFICULTIES)


@teacher_bp.route("/problems/<int:problem_id>/edit", methods=["GET", "POST"])
@login_required
@teacher_required
def problem_edit(problem_id):
    problem = db.session.get(Problem, problem_id) or abort(404)
    if request.method == "POST":
        problem.title = (request.form.get("title") or problem.title).strip()
        problem.description = request.form.get("description") or ""
        problem.difficulty = request.form.get("difficulty") or "easy"
        problem.starter_code = request.form.get("starter_code") or ""
        problem.reference_code = request.form.get("reference_code") or ""
        _sync_tags(problem, request.form.getlist("tags"), request.form.get("new_tags", ""))
        _sync_test_cases(
            problem,
            request.form.getlist("tc_input"),
            request.form.getlist("tc_output"),
            set(request.form.getlist("tc_sample")),
        )
        db.session.commit()
        flash("题目已保存。", "success")
        return redirect(url_for("teacher.problem_edit", problem_id=problem.id))

    return render_template("teacher/problem_form.html", problem=problem, tags=_all_tags(), difficulties=DIFFICULTIES)


@teacher_bp.route("/problems/<int:problem_id>/delete", methods=["POST"])
@login_required
@teacher_required
def problem_delete(problem_id):
    problem = db.session.get(Problem, problem_id) or abort(404)
    if problem.author_id != current_user.id:
        flash("只能删除自己创建的题目。", "danger")
        return redirect(url_for("teacher.problems"))
    Submission.query.filter_by(problem_id=problem.id).delete()
    db.session.execute(
        homework_problems.delete().where(homework_problems.c.problem_id == problem.id)
    )
    db.session.delete(problem)
    db.session.commit()
    flash("题目已删除。", "info")
    return redirect(url_for("teacher.problems"))


@teacher_bp.route("/problems/<int:problem_id>/preview")
@login_required
@teacher_required
def problem_preview(problem_id):
    problem = db.session.get(Problem, problem_id) or abort(404)
    return render_template(
        "problems/detail.html",
        problem=problem,
        samples=problem.test_cases,
        code=problem.reference_code or problem.starter_code or "",
        tab="preview",
    )


def _all_tags():
    return db.session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.name)).all()


# ----------------------------- 班级管理 -----------------------------


@teacher_bp.route("/classes", methods=["GET", "POST"])
@login_required
@teacher_required
def classes():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("班级名称不能为空。", "danger")
            return redirect(url_for("teacher.classes"))
        room = Classroom(name=name, join_code=_generate_join_code(), teacher_id=current_user.id)
        db.session.add(room)
        db.session.commit()
        flash("班级已创建，班级码：%s" % room.join_code, "success")
        return redirect(url_for("teacher.classes"))

    rooms = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == current_user.id).order_by(Classroom.created_at.desc())
    ).all()
    return render_template("teacher/classes.html", rooms=rooms)


@teacher_bp.route("/classes/<int:room_id>/delete", methods=["POST"])
@login_required
@teacher_required
def class_delete(room_id):
    room = db.session.get(Classroom, room_id) or abort(404)
    if room.teacher_id != current_user.id:
        abort(403)
    db.session.execute(
        ClassroomStudent.__table__.delete().where(ClassroomStudent.classroom_id == room.id)
    )
    for hw in list(room.homeworks):
        Submission.query.filter_by(homework_id=hw.id).delete()
        db.session.execute(
            homework_problems.delete().where(homework_problems.c.homework_id == hw.id)
        )
        db.session.delete(hw)
    db.session.delete(room)
    db.session.commit()
    flash("班级已删除。", "info")
    return redirect(url_for("teacher.classes"))


@teacher_bp.route("/classes/<int:room_id>/students/<int:student_id>/remove", methods=["POST"])
@login_required
@teacher_required
def class_remove_student(room_id, student_id):
    room = db.session.get(Classroom, room_id) or abort(404)
    if room.teacher_id != current_user.id:
        abort(403)
    student = db.session.get(User, student_id) or abort(404)
    if student in room.students:
        room.students.remove(student)
        db.session.execute(
            ClassroomStudent.__table__.delete().where(
                ClassroomStudent.classroom_id == room.id, ClassroomStudent.student_id == student.id
            )
        )
        db.session.commit()
        flash("已移除学生：%s" % student.name, "info")
    return redirect(url_for("teacher.class_detail", room_id=room.id))


@teacher_bp.route("/classes/<int:room_id>")
@login_required
@teacher_required
def class_detail(room_id):
    room = db.session.get(Classroom, room_id) or abort(404)
    if room.teacher_id != current_user.id:
        abort(403)
    stats = []
    for student in room.students:
        total = db.session.scalar(
            select(func.count(Submission.id)).where(Submission.user_id == student.id)
        ) or 0
        ac = db.session.scalar(
            select(func.count(Submission.id)).where(
                Submission.user_id == student.id, Submission.status == "AC"
            )
        ) or 0
        stats.append(
            {"student": student, "total": total, "accepted": ac, "rate": round(ac * 100 / total) if total else 0}
        )
    stats.sort(key=lambda x: -x["rate"])
    homeworks = db.session.scalars(
        select(Homework).where(Homework.classroom_id == room.id).order_by(Homework.created_at.desc())
    ).all()
    return render_template("teacher/class_detail.html", room=room, stats=stats, homeworks=homeworks, now=datetime.now())


# ----------------------------- 作业管理 -----------------------------


@teacher_bp.route("/homeworks", methods=["GET", "POST"])
@login_required
@teacher_required
def homeworks():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        room = db.session.get(Classroom, request.form.get("classroom_id", type=int))
        due_at = _parse_dt(request.form.get("due_at"))
        if not title or not room or not due_at:
            flash("请填写完整的作业信息（标题、班级、截止时间）。", "danger")
            return redirect(url_for("teacher.homeworks"))
        problem_ids = [int(x) for x in request.form.getlist("problems")]
        if not problem_ids:
            flash("请至少选择一道题目。", "danger")
            return redirect(url_for("teacher.homeworks"))

        hw = Homework(
            title=title,
            description=request.form.get("description") or "",
            classroom_id=room.id,
            teacher_id=current_user.id,
            due_at=due_at,
        )
        db.session.add(hw)
        db.session.flush()
        for pid in problem_ids:
            problem = db.session.get(Problem, pid)
            if problem:
                hw.problems.append(problem)
        db.session.commit()
        flash("作业已发布。", "success")
        return redirect(url_for("teacher.homework_detail", homework_id=hw.id))

    rooms = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == current_user.id).order_by(Classroom.name)
    ).all()
    room_ids = [r.id for r in rooms]
    items = []
    if room_ids:
        hws = db.session.scalars(
            select(Homework).where(Homework.classroom_id.in_(room_ids)).order_by(Homework.created_at.desc())
            .options(
                selectinload(Homework.classroom).selectinload(Classroom.students),
                selectinload(Homework.problems),
            )
        ).all()
        for hw in hws:
            submitted = db.session.scalar(
                select(func.count(func.distinct(Submission.user_id))).where(Submission.homework_id == hw.id)
            ) or 0
            items.append({"homework": hw, "submitted": submitted, "members": len(hw.classroom.students)})
    return render_template(
        "teacher/homeworks.html",
        items=items,
        rooms=rooms,
        problems=db.session.scalars(
            select(Problem).order_by(Problem.id.desc()).options(selectinload(Problem.tags))
        ).all(),
        now=datetime.now(),
    )


@teacher_bp.route("/homeworks/<int:homework_id>")
@login_required
@teacher_required
def homework_detail(homework_id):
    hw = db.session.get(Homework, homework_id) or abort(404)
    if hw.teacher_id != current_user.id:
        abort(403)

    subs = db.session.scalars(
        select(Submission).where(Submission.homework_id == hw.id).order_by(Submission.created_at.desc())
    ).all()

    best = {}
    for s in subs:
        key = (s.user_id, s.problem_id)
        cur = best.get(key)
        if cur is None or (s.status == "AC" and cur.status != "AC") or (
            s.status == cur.status and s.score > cur.score
        ):
            best[key] = s

    rows = []
    for student in hw.classroom.students:
        cells = []
        done = 0
        for problem in hw.problems:
            sub = best.get((student.id, problem.id))
            if sub and sub.status == "AC":
                done += 1
            cells.append({"problem": problem, "submission": sub})
        total = len(hw.problems)
        rows.append(
            {
                "student": student,
                "cells": cells,
                "done": done,
                "total": total,
                "rate": round(done * 100 / total) if total else 0,
                "last": max(
                    [c["submission"].created_at for c in cells if c["submission"]], default=None
                ),
            }
        )
    rows.sort(key=lambda r: (-r["rate"], r["student"].username))

    problem_stats = []
    for problem in hw.problems:
        ac_count = sum(1 for r in rows for c in r["cells"] if c["problem"].id == problem.id and c["submission"] and c["submission"].status == "AC")
        total_students = len(hw.classroom.students)
        problem_stats.append(
            {
                "problem": problem,
                "ac_count": ac_count,
                "total": total_students,
                "rate": round(ac_count * 100 / total_students) if total_students else 0,
            }
        )

    status_counter = {}
    for s in subs:
        status_counter[s.status] = status_counter.get(s.status, 0) + 1

    knowledge_stats = _knowledge_stats(subs)

    return render_template(
        "teacher/homework_detail.html",
        homework=hw,
        rows=rows,
        problems=hw.problems,
        problem_stats=problem_stats,
        submissions=subs[:50],
        status_counter=status_counter,
        status_labels=STATUS_LABELS,
        knowledge_stats=knowledge_stats,
        now=datetime.now(),
    )


@teacher_bp.route("/homeworks/<int:homework_id>/delete", methods=["POST"])
@login_required
@teacher_required
def homework_delete(homework_id):
    hw = db.session.get(Homework, homework_id) or abort(404)
    if hw.teacher_id != current_user.id:
        abort(403)
    Submission.query.filter_by(homework_id=hw.id).delete()
    db.session.execute(
        homework_problems.delete().where(homework_problems.c.homework_id == hw.id)
    )
    db.session.delete(hw)
    db.session.commit()
    flash("作业已删除。", "info")
    return redirect(url_for("teacher.homeworks"))


# ----------------------------- 学情统计 -----------------------------


def _knowledge_stats(submissions):
    """按知识点统计正确率。"""
    data = {}
    for s in submissions:
        for tag in s.problem.tags:
            item = data.setdefault(tag.name, {"total": 0, "accepted": 0})
            item["total"] += 1
            if s.status == "AC":
                item["accepted"] += 1
    result = [
        {
            "name": name,
            "total": v["total"],
            "accepted": v["accepted"],
            "rate": round(v["accepted"] * 100 / v["total"]) if v["total"] else 0,
        }
        for name, v in data.items()
    ]
    result.sort(key=lambda x: (x["rate"], -x["total"]))
    return result


@teacher_bp.route("/stats")
@login_required
@teacher_required
def stats():
    rooms = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == current_user.id).order_by(Classroom.name)
    ).all()
    room_id = request.args.get("room", type=int)
    room = db.session.get(Classroom, room_id) if room_id else (rooms[0] if rooms else None)
    if room and room.teacher_id != current_user.id:
        abort(403)

    subs = []
    if room:
        hw_ids = [h.id for h in room.homeworks]
        if hw_ids:
            subs = db.session.scalars(
                select(Submission).where(Submission.homework_id.in_(hw_ids))
            ).all()

    student_stats = []
    if room:
        for student in room.students:
            mine = [s for s in subs if s.user_id == student.id]
            ac = sum(1 for s in mine if s.status == "AC")
            solved = len({s.problem_id for s in mine if s.status == "AC"})
            student_stats.append(
                {
                    "student": student,
                    "total": len(mine),
                    "accepted": ac,
                    "solved": solved,
                    "rate": round(ac * 100 / len(mine)) if mine else 0,
                }
            )
        student_stats.sort(key=lambda x: (-x["rate"], -x["total"]))

    return render_template(
        "teacher/stats.html",
        rooms=rooms,
        room=room,
        knowledge_stats=_knowledge_stats(subs),
        student_stats=student_stats,
        total_submissions=len(subs),
    )


@teacher_bp.route("/submissions")
@login_required
@teacher_required
def submissions():
    room_id = request.args.get("room", type=int)
    student_id = request.args.get("student", type=int)
    status = (request.args.get("status") or "").strip()
    page = request.args.get("page", type=int, default=1)

    rooms = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == current_user.id).order_by(Classroom.name)
    ).all()
    room_ids = [r.id for r in rooms] or [0]
    hw_ids = db.session.scalars(
        select(Homework.id).where(Homework.classroom_id.in_(room_ids))
    ).all()

    stmt = select(Submission)
    if room_id:
        ids = db.session.scalars(
            select(Homework.id).where(Homework.classroom_id == room_id)
        ).all()
        stmt = stmt.where(Submission.homework_id.in_(ids or [0]))
    else:
        stmt = stmt.where(Submission.homework_id.in_(hw_ids or [0]))
    if student_id:
        stmt = stmt.where(Submission.user_id == student_id)
    if status:
        stmt = stmt.where(Submission.status == status)

    pagination = db.paginate(stmt.order_by(Submission.created_at.desc()), page=page, per_page=20, error_out=False)
    students = []
    seen = set()
    for r in rooms:
        for s in r.students:
            if s.id not in seen:
                seen.add(s.id)
                students.append(s)

    return render_template(
        "teacher/submissions.html",
        pagination=pagination,
        submissions=pagination.items,
        rooms=rooms,
        students=students,
        room_id=room_id,
        student_id=student_id,
        status=status,
        status_labels=STATUS_LABELS,
    )
