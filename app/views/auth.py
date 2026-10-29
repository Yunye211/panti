import hmac
import re
import time

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from .. import db
from ..models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth", template_folder="../templates")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

# 简单的登录失败限流（单进程内存计数；多进程部署请改用 Redis）
_LOGIN_FAILS = {}
MAX_FAILS = 5
LOCK_SECONDS = 60


def _fail_key(username):
    return "%s|%s" % ((username or "").lower(), request.remote_addr or "-")


def _locked(key):
    info = _LOGIN_FAILS.get(key)
    if not info:
        return False
    if time.time() < info["until"]:
        return True
    _LOGIN_FAILS.pop(key, None)
    return False


def _register_fail(key):
    info = _LOGIN_FAILS.get(key)
    now = time.time()
    if not info or now >= info["until"]:
        info = {"count": 0, "until": now + LOCK_SECONDS}
        _LOGIN_FAILS[key] = info
    info["count"] += 1
    if info["count"] >= MAX_FAILS:
        info["until"] = now + LOCK_SECONDS
    for k in [k for k, v in _LOGIN_FAILS.items() if v["until"] < now - 600]:
        _LOGIN_FAILS.pop(k, None)


def _clear_fail(key):
    _LOGIN_FAILS.pop(key, None)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        display_name = (request.form.get("display_name") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        role = request.form.get("role") or "student"
        invite = (request.form.get("invite_code") or "").strip()

        if role not in ("student", "teacher"):
            role = "student"
        if role == "teacher" and not hmac.compare_digest(invite, current_app.config.get("TEACHER_INVITE_CODE", "")):
            flash("教师注册码不正确。", "danger")
            return render_template("auth/register.html", form=request.form)
        if not USERNAME_RE.match(username):
            flash("用户名需为 3~32 位字母、数字、下划线、点或短横线。", "danger")
            return render_template("auth/register.html", form=request.form)
        if len(password) < 6:
            flash("密码长度至少 6 位。", "danger")
            return render_template("auth/register.html", form=request.form)
        if password != confirm:
            flash("两次输入的密码不一致。", "danger")
            return render_template("auth/register.html", form=request.form)
        if db.session.scalar(select(User).where(User.username == username)):
            flash("该用户名已被注册。", "danger")
            return render_template("auth/register.html", form=request.form)

        user = User(username=username, display_name=display_name or username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("注册成功，请登录。", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form={})


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key = _fail_key(username)

        if _locked(key):
            flash("登录失败次数过多，请 1 分钟后再试。", "danger")
            return render_template("auth/login.html")

        user = db.session.scalar(select(User).where(User.username == username))
        if user and user.check_password(password):
            _clear_fail(key)
            login_user(user)
            flash("欢迎回来，%s！" % user.name, "success")
            next_url = request.args.get("next")
            # 只允许站内跳转，避免开放重定向
            if next_url and (not next_url.startswith("/") or next_url.startswith("//")):
                next_url = None
            return redirect(next_url or url_for("main.index"))

        _register_fail(key)
        flash("用户名或密码错误。", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录。", "info")
    return redirect(url_for("auth.login"))

