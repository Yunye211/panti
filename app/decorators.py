from functools import wraps

from flask import abort, flash, redirect, url_for
from flask_login import current_user


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
