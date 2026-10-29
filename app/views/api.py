from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from .. import db
from ..judge import judge
from ..models import Homework, Problem, Submission
from ..sandbox import run_code

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/judge", methods=["POST"])
@login_required
def api_judge():
    data = request.get_json(silent=True) or {}
    code = data.get("code") or ""
    try:
        problem_id = int(data.get("problem_id"))
    except (TypeError, ValueError):
        problem_id = None

    problem = db.session.get(Problem, problem_id) if problem_id else None
    if not problem:
        return jsonify({"error": "题目不存在。"}), 404

    max_len = int(current_app.config.get("MAX_CODE_LENGTH", 20000))
    if len(code) > max_len:
        return jsonify({"error": "代码过长（上限 %d 字符）。" % max_len}), 400

    homework = None
    if data.get("homework_id"):
        homework = db.session.get(Homework, int(data["homework_id"]))
        if homework and current_user.is_student and homework.classroom not in current_user.joined_classrooms:
            return jsonify({"error": "无权提交该作业。"}), 403

    # 超时与内存一律取服务端配置，不接受客户端参数，防止恶意放大资源占用
    result = judge(
        code,
        problem.test_cases,
        time_limit=int(current_app.config.get("JUDGE_TIME_LIMIT", 2)),
        total_limit=int(current_app.config.get("JUDGE_TOTAL_TIME", 15)),
        memory_mb=int(current_app.config.get("JUDGE_MEMORY_MB", 256)),
    )

    save = data.get("save", True)
    if save and current_user.is_student:
        is_late = bool(homework and datetime.now() > homework.due_at)
        submission = Submission(
            user_id=current_user.id,
            problem_id=problem.id,
            homework_id=homework.id if homework else None,
            code=code,
            status=result["status"],
            passed_count=result["passed"],
            total_count=result["total"],
            message=(result["message"] or "")[:2000],
            max_time_ms=result["max_time_ms"],
            source=(data.get("source") or ("homework" if homework else "free")),
            is_late=is_late,
        )
        db.session.add(submission)
        db.session.commit()
        result["submission_id"] = submission.id
        result["is_late"] = is_late

    result.pop("status_label", None)
    return jsonify(result)


@api_bp.route("/run", methods=["POST"])
@login_required
def api_run():
    """自定义输入运行（不判题、不记录）。"""
    data = request.get_json(silent=True) or {}
    code = data.get("code") or ""
    stdin_data = data.get("stdin") or ""
    max_len = int(current_app.config.get("MAX_CODE_LENGTH", 20000))
    if len(code) > max_len:
        return jsonify({"error": "代码过长。"}), 400
    if len(stdin_data) > 20000:
        return jsonify({"error": "输入内容过长。"}), 400
    result = run_code(
        code,
        stdin_data,
        time_limit=int(current_app.config.get("JUDGE_TIME_LIMIT", 2)) + 1,
        memory_mb=int(current_app.config.get("JUDGE_MEMORY_MB", 256)),
    )
    return jsonify(
        {
            "status": result.status,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:4000],
            "time_ms": result.time_ms,
        }
    )
