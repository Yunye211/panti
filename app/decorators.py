from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user


def like(keyword):
    """构造安全的 SQL LIKE 表达式，转义用户输入中的 % 和 _ 通配符。"""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%%%s%%" % escaped, "\\"


def role_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                flash("当前账号无权限访问该页面。", "danger")
                return redirect(url_for("main.index"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


def student_required(func):
    return role_required("student")(func)


def teacher_required(func):
    # 管理员拥有教师端访问权，便于统一管理题库与班级
    return role_required("teacher", "admin")(func)


def admin_required(func):
    return role_required("admin")(func)


def ensure_owner(obj, attr="teacher_id"):
    """abort(403) if obj.attr != current_user.id。obj 为 None 时跳过。"""
    if obj is not None and getattr(obj, attr) != current_user.id:
        abort(403)
