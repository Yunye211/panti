import hmac
import os
import secrets

from flask import Flask, abort, jsonify, request, session
from markupsafe import Markup

from .extensions import db, login_manager
from .models import User

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

CSRF_EXEMPT_ENDPOINTS = set()


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "python-online-judge-secret"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL")
        or "sqlite:///" + os.path.join(INSTANCE_DIR, "judge.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JUDGE_TIME_LIMIT=int(os.environ.get("JUDGE_TIME_LIMIT", "2")),
        JUDGE_TOTAL_TIME=int(os.environ.get("JUDGE_TOTAL_TIME", "15")),
        JUDGE_MEMORY_MB=int(os.environ.get("JUDGE_MEMORY_MB", "256")),
        MAX_CODE_LENGTH=int(os.environ.get("MAX_CODE_LENGTH", "20000")),
        TEACHER_INVITE_CODE=os.environ.get("TEACHER_INVITE_CODE", "teacher2024"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if config:
        app.config.update(config)

    os.makedirs(INSTANCE_DIR, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请先登录后再访问该页面。"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ------------------------- CSRF 防护 -------------------------

    def _csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_hex(24)
            session["csrf_token"] = token
        return token

    @app.context_processor
    def _inject_csrf():
        def csrf_field():
            return Markup(
                '<input type="hidden" name="csrf_token" value="%s">' % _csrf_token()
            )

        return {"csrf_token": _csrf_token, "csrf_field": csrf_field}

    @app.before_request
    def _csrf_protect():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        if request.endpoint in CSRF_EXEMPT_ENDPOINTS:
            return None
        expected = session.get("csrf_token")
        supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
            if request.path.startswith("/api/"):
                return jsonify({"error": "CSRF 校验失败，请刷新页面后重试。"}), 400
            abort(400, description="表单已过期或来源不可信（CSRF 校验失败），请刷新页面后重试。")

    @app.errorhandler(400)
    def _bad_request(err):
        if request.path.startswith("/api/"):
            return jsonify({"error": getattr(err, "description", "请求有误")}), 400
        return (
            "<h3>400 - 请求有误</h3><p>%s</p><p><a href='/'>返回首页</a></p>"
            % getattr(err, "description", "请求有误"),
            400,
        )

    from .views.api import api_bp
    from .views.auth import auth_bp
    from .views.homework import homework_bp
    from .views.main import main_bp
    from .views.problems import problems_bp
    from .views.teacher import teacher_bp

    for bp in (auth_bp, main_bp, problems_bp, homework_bp, teacher_bp, api_bp):
        app.register_blueprint(bp)

    with app.app_context():
        db.create_all()

    return app
