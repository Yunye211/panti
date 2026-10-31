"""管理员：管理学生与教师账号（列表、创建、编辑、启停、重置密码、删除）。"""
import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from .. import db
from ..decorators import admin_required
from ..models import (
    Classroom,
    ClassroomStudent,
    Homework,
    Problem,
    Submission,
    User,
    classroom_students,
    homework_problems,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates")

ROLES = (("student", "学生"), ("teacher", "教师"), ("admin", "管理员"))
DEFAULT_PASSWORD = "123456"


# ----------------------------- 仪表盘 -----------------------------


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    # 角色统计一次 group_by 取回，避免多次 count 查询
    role_counts = {
        row[0]: row[1]
        for row in db.session.execute(select(User.role, func.count(User.id)).group_by(User.role))
    }
    stats = {
        "student": role_counts.get("student", 0),
        "teacher": role_counts.get("teacher", 0),
        "admin": role_counts.get("admin", 0),
        "problems": db.session.scalar(select(func.count(Problem.id))) or 0,
        "classrooms": db.session.scalar(select(func.count(Classroom.id))) or 0,
        "homeworks": db.session.scalar(select(func.count(Homework.id))) or 0,
        "submissions": db.session.scalar(select(func.count(Submission.id))) or 0,
    }

    # 默认管理员密码仍在使用的安全提醒
    default_admin = db.session.scalar(select(User).where(User.username == "admin", User.role == "admin"))
    weak_password = bool(default_admin and default_admin.check_password("admin123"))

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        weak_password=weak_password,
        recent_users=db.session.scalars(
            select(User).order_by(User.created_at.desc()).limit(8)
        ).all(),
        recent_submissions=db.session.scalars(
            select(Submission).order_by(Submission.created_at.desc()).limit(8)
        ).all(),
    )


# ----------------------------- 用户管理 -----------------------------


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    role = (request.args.get("role") or "").strip()
    keyword = (request.args.get("q") or "").strip()
    page = request.args.get("page", type=int, default=1)

    stmt = select(User)
    if role in dict(ROLES):
        stmt = stmt.where(User.role == role)
    if keyword:
        like = "%%%s%%" % keyword
        stmt = stmt.where(User.username.like(like) | User.display_name.like(like))

    pagination = db.paginate(
        stmt.order_by(User.role, User.id.desc()), page=page, per_page=20, error_out=False
    )
    items = pagination.items

    # 提交数一次性聚合，避免列表里逐行查询（N+1）
    counts = {}
    ids = [u.id for u in items]
    if ids:
        counts = {
            row[0]: row[1]
            for row in db.session.execute(
                select(Submission.user_id, func.count(Submission.id))
                .where(Submission.user_id.in_(ids))
                .group_by(Submission.user_id)
            )
        }

    return render_template(
        "admin/users.html",
        pagination=pagination,
        users=items,
        counts=counts,
        role=role,
        keyword=keyword,
        roles=ROLES,
    )


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def user_new():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        role = request.form.get("role") or "student"
        password = request.form.get("password") or DEFAULT_PASSWORD
        display_name = (request.form.get("display_name") or "").strip() or username

        if not _valid_username(username):
            flash("用户名需为 3~32 位字母、数字、下划线、点或短横线。", "danger")
            return render_template("admin/user_form.html", user=None, roles=ROLES, form=request.form)
        if role not in dict(ROLES):
            role = "student"
        if len(password) < 6:
            flash("密码长度至少 6 位。", "danger")
            return render_template("admin/user_form.html", user=None, roles=ROLES, form=request.form)
        if db.session.scalar(select(User).where(User.username == username)):
            flash("该用户名已被注册。", "danger")
            return render_template("admin/user_form.html", user=None, roles=ROLES, form=request.form)

        user = User(username=username, display_name=display_name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("账号 %s 创建成功。" % username, "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", user=None, roles=ROLES, form={})


@admin_bp.route("/users/<int:user_id>")
@login_required
@admin_required
def user_detail(user_id):
    user = db.session.get(User, user_id) or abort(404)
    total = db.session.scalar(select(func.count(Submission.id)).where(Submission.user_id == user.id)) or 0
    accepted = db.session.scalar(
        select(func.count(Submission.id)).where(Submission.user_id == user.id, Submission.status == "AC")
    ) or 0
    submissions = db.session.scalars(
        select(Submission).where(Submission.user_id == user.id).order_by(Submission.created_at.desc()).limit(10)
    ).all()
    taught_rooms = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == user.id).order_by(Classroom.name)
    ).all()
    return render_template(
        "admin/user_detail.html",
        user=user,
        total=total,
        accepted=accepted,
        rate=round(accepted * 100 / total) if total else 0,
        submissions=submissions,
        joined_classrooms=user.joined_classrooms,
        taught_rooms=taught_rooms,
        created_problems=db.session.scalar(select(func.count(Problem.id)).where(Problem.author_id == user.id)) or 0,
    )


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def user_edit(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        role = request.form.get("role") or user.role

        if not _valid_username(username):
            flash("用户名需为 3~32 位字母、数字、下划线、点或短横线。", "danger")
            return render_template("admin/user_form.html", user=user, roles=ROLES, form=request.form)
        if role not in dict(ROLES):
            role = user.role
        duplicate = db.session.scalar(select(User).where(User.username == username, User.id != user.id))
        if duplicate:
            flash("该用户名已被占用。", "danger")
            return render_template("admin/user_form.html", user=user, roles=ROLES, form=request.form)

        # 不允许把最后一个管理员降级，避免系统失去管理员
        if user.role == "admin" and role != "admin":
            admin_count = db.session.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0
            if admin_count <= 1:
                flash("系统至少需要保留一个管理员。", "danger")
                return redirect(url_for("admin.user_edit", user_id=user.id))

        user.username = username
        user.display_name = (request.form.get("display_name") or "").strip() or username
        user.role = role
        new_password = request.form.get("password") or ""
        if new_password:
            if len(new_password) < 6:
                flash("密码长度至少 6 位。", "danger")
                return render_template("admin/user_form.html", user=user, roles=ROLES, form=request.form)
            user.set_password(new_password)
        db.session.commit()
        flash("账号信息已保存。", "success")
        return redirect(url_for("admin.user_detail", user_id=user.id))

    return render_template("admin/user_form.html", user=user, roles=ROLES, form={})


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def user_reset_password(user_id):
    user = db.session.get(User, user_id) or abort(404)
    user.set_password(DEFAULT_PASSWORD)
    db.session.commit()
    flash("已将 %s 的密码重置为 %s。" % (user.username, DEFAULT_PASSWORD), "info")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin_bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def user_toggle_active(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("不能停用当前登录的管理员账号。", "danger")
        return redirect(url_for("admin.user_detail", user_id=user.id))
    if user.role == "admin":
        admin_count = db.session.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0
        if user.is_active and admin_count <= 1:
            flash("系统至少需要保留一个管理员。", "danger")
            return redirect(url_for("admin.user_detail", user_id=user.id))
    user.is_active = not user.is_active
    db.session.commit()
    flash("账号已%s。" % ("启用" if user.is_active else "停用"), "info")
    return redirect(url_for("admin.user_detail", user_id=user.id))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def user_delete(user_id):
    user = db.session.get(User, user_id) or abort(404)
    if user.id == current_user.id:
        flash("不能删除当前登录的管理员账号。", "danger")
        return redirect(url_for("admin.users"))
    if user.role == "admin":
        admin_count = db.session.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0
        if admin_count <= 1:
            flash("系统至少需要保留一个管理员。", "danger")
            return redirect(url_for("admin.users"))

    _purge_user(user)
    db.session.delete(user)
    db.session.commit()
    flash("账号 %s 已删除。" % user.username, "info")
    return redirect(url_for("admin.users"))


# ----------------------------- 辅助 -----------------------------


def _valid_username(name):
    return bool(re.match(r"^[A-Za-z0-9_.-]{3,32}$", name or ""))


def _purge_user(user):
    """删除用户前清理其关联数据，避免出现孤儿记录。"""
    Submission.query.filter_by(user_id=user.id).delete()

    # 退出所有班级
    db.session.execute(
        classroom_students.delete().where(classroom_students.c.student_id == user.id)
    )
    db.session.execute(
        ClassroomStudent.__table__.delete().where(ClassroomStudent.student_id == user.id)
    )

    # 教师：连带删除其班级、作业与作业提交
    rooms = db.session.scalars(select(Classroom).where(Classroom.teacher_id == user.id)).all()
    for room in rooms:
        for hw in list(room.homeworks):
            Submission.query.filter_by(homework_id=hw.id).delete()
            db.session.execute(
                homework_problems.delete().where(homework_problems.c.homework_id == hw.id)
            )
            db.session.delete(hw)
        db.session.execute(
            ClassroomStudent.__table__.delete().where(ClassroomStudent.classroom_id == room.id)
        )
        db.session.execute(
            classroom_students.delete().where(classroom_students.c.classroom_id == room.id)
        )
        db.session.delete(room)

    db.session.flush()


@admin_bp.app_context_processor
def _inject_now():
    return {"now": datetime.now()}
