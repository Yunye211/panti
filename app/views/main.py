from datetime import datetime

from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import func, select

from ..models import Classroom, ClassroomStudent, Homework, KnowledgePoint, Problem, Submission, db

main_bp = Blueprint("main", __name__, template_folder="../templates")


@main_bp.route("/")
@login_required
def index():
    if current_user.is_teacher:
        return _teacher_home()
    return _student_home()


def _student_home():
    total = db.session.scalar(
        select(func.count(Submission.id)).where(Submission.user_id == current_user.id)
    ) or 0
    accepted = db.session.scalar(
        select(func.count(Submission.id)).where(
            Submission.user_id == current_user.id, Submission.status == "AC"
        )
    ) or 0
    solved_problems = db.session.scalar(
        select(func.count(func.distinct(Submission.problem_id))).where(
            Submission.user_id == current_user.id, Submission.status == "AC"
        )
    ) or 0
    problem_count = db.session.scalar(select(func.count(Problem.id))) or 0

    recent = db.session.scalars(
        select(Submission).where(Submission.user_id == current_user.id)
        .order_by(Submission.created_at.desc()).limit(8)
    ).all()

    homeworks = []
    for room in current_user.joined_classrooms:
        for hw in db.session.scalars(
            select(Homework).where(Homework.classroom_id == room.id)
            .order_by(Homework.due_at.desc())
        ).all():
            homeworks.append((room, hw))
    homeworks.sort(key=lambda item: item[1].due_at, reverse=True)

    return render_template(
        "student_home.html",
        total=total,
        accepted=accepted,
        solved_problems=solved_problems,
        problem_count=problem_count,
        recent=recent,
        homeworks=homeworks[:6],
        now=datetime.now(),
        knowledge_points=db.session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.name)).all(),
    )


def _teacher_home():
    my_problems = db.session.scalar(
        select(func.count(Problem.id)).where(Problem.author_id == current_user.id)
    ) or 0
    classes = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == current_user.id).order_by(Classroom.created_at.desc())
    ).all()
    room_ids = [c.id for c in classes]
    student_total = 0
    for room in classes:
        student_total += len(room.students)

    homeworks = []
    if room_ids:
        homeworks = db.session.scalars(
            select(Homework).where(Homework.classroom_id.in_(room_ids))
            .order_by(Homework.created_at.desc())
        ).all()

    recent = []
    if room_ids:
        recent = db.session.scalars(
            select(Submission).where(Submission.homework_id.in_(
                select(Homework.id).where(Homework.classroom_id.in_(room_ids))
            )).order_by(Submission.created_at.desc()).limit(10)
        ).all()

    return render_template(
        "teacher_home.html",
        my_problems=my_problems,
        classes=classes,
        student_total=student_total,
        homeworks=homeworks[:6],
        homework_total=len(homeworks),
        recent=recent,
        now=datetime.now(),
    )


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    from flask import flash, redirect, request, url_for

    if request.method == "POST":
        current_user.display_name = (request.form.get("display_name") or "").strip() or current_user.username
        new_pwd = request.form.get("password") or ""
        if new_pwd:
            if len(new_pwd) < 6:
                flash("密码长度至少 6 位。", "danger")
                return redirect(url_for("main.profile"))
            current_user.set_password(new_pwd)
        db.session.commit()
        flash("资料已更新。", "success")
        return redirect(url_for("main.profile"))
    return render_template("profile.html")


@main_bp.route("/classes/join", methods=["POST"])
@login_required
def join_class():
    from flask import flash, redirect, request, url_for

    if not current_user.is_student:
        flash("只有学生可以加入班级。", "danger")
        return redirect(url_for("main.index"))
    code = (request.form.get("join_code") or "").strip()
    room = db.session.scalar(select(Classroom).where(Classroom.join_code == code))
    if not room:
        flash("班级码不存在，请向教师确认。", "danger")
    elif room in current_user.joined_classrooms:
        flash("你已在该班级中。", "info")
    else:
        current_user.joined_classrooms.append(room)
        db.session.add(ClassroomStudent(classroom_id=room.id, student_id=current_user.id))
        db.session.commit()
        flash("已加入班级：%s" % room.name, "success")
    return redirect(request.referrer or url_for("main.index"))
