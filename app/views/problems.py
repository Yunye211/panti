import random
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, select

from .. import db
from ..decorators import student_required
from ..models import DIFFICULTIES, KnowledgePoint, Problem, Submission, User

problems_bp = Blueprint("problems", __name__, url_prefix="/problems", template_folder="../templates")

PRACTICE_SESSION_KEY = "practice_queue"
PRACTICE_META_KEY = "practice_meta"


@problems_bp.route("/")
@login_required
def index():
    keyword = (request.args.get("q") or "").strip()
    tag_id = request.args.get("tag", type=int)
    difficulty = (request.args.get("difficulty") or "").strip()
    page = request.args.get("page", type=int, default=1)

    stmt = select(Problem)
    if keyword:
        like = "%%%s%%" % keyword
        stmt = stmt.where(Problem.title.like(like))
    if difficulty in DIFFICULTIES:
        stmt = stmt.where(Problem.difficulty == difficulty)
    if tag_id:
        stmt = stmt.where(Problem.tags.any(KnowledgePoint.id == tag_id))

    pagination = db.paginate(stmt.order_by(Problem.id.asc()), page=page, per_page=12, error_out=False)

    # 学生每题的通过状态
    solved_ids = set()
    if current_user.is_student:
        rows = db.session.execute(
            select(Submission.problem_id).where(
                Submission.user_id == current_user.id, Submission.status == "AC"
            ).distinct()
        ).all()
        solved_ids = {r[0] for r in rows}

    return render_template(
        "problems/list.html",
        pagination=pagination,
        problems=pagination.items,
        tags=db.session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.name)).all(),
        difficulties=DIFFICULTIES,
        keyword=keyword,
        tag_id=tag_id,
        difficulty=difficulty,
        solved_ids=solved_ids,
    )


@problems_bp.route("/<int:problem_id>")
@login_required
def detail(problem_id):
    problem = db.session.get(Problem, problem_id) or abort(404)
    samples = [tc for tc in problem.test_cases if tc.is_sample]
    last = db.session.scalar(
        select(Submission).where(
            Submission.user_id == current_user.id, Submission.problem_id == problem_id
        ).order_by(Submission.created_at.desc()).limit(1)
    )
    code = (last.code if last else None) or problem.starter_code or ""
    return render_template(
        "problems/detail.html",
        problem=problem,
        samples=samples,
        code=code,
        tab="free",
    )


# ----------------------------- 专项练习 -----------------------------


@problems_bp.route("/practice/setup", methods=["GET", "POST"])
@login_required
@student_required
def practice_setup():
    tags = db.session.scalars(select(KnowledgePoint).order_by(KnowledgePoint.name)).all()
    if request.method == "POST":
        tag_ids = [int(x) for x in request.form.getlist("tags") if x.isdigit()]
        difficulty = (request.form.get("difficulty") or "").strip()
        count = request.form.get("count", type=int, default=5)
        count = max(1, min(count, 20))

        stmt = select(Problem)
        if tag_ids:
            stmt = stmt.where(Problem.tags.any(KnowledgePoint.id.in_(tag_ids)))
        if difficulty in DIFFICULTIES:
            stmt = stmt.where(Problem.difficulty == difficulty)

        candidates = db.session.scalars(stmt).all()
        if not candidates:
            flash("没有符合条件的题目，请放宽筛选条件。", "warning")
            return redirect(url_for("problems.practice_setup"))

        random.shuffle(candidates)
        chosen = candidates[:count]
        session[PRACTICE_SESSION_KEY] = [p.id for p in chosen]
        session[PRACTICE_META_KEY] = {
            "difficulty": difficulty,
            "tags": tag_ids,
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        return redirect(url_for("problems.practice_run", index=1))

    return render_template("problems/practice_setup.html", tags=tags, difficulties=DIFFICULTIES)


@problems_bp.route("/practice/<int:index>")
@login_required
@student_required
def practice_run(index):
    queue = session.get(PRACTICE_SESSION_KEY) or []
    if not queue:
        flash("请先选择练习条件。", "info")
        return redirect(url_for("problems.practice_setup"))
    if index < 1 or index > len(queue):
        return redirect(url_for("problems.practice_run", index=1))

    problem = db.session.get(Problem, queue[index - 1]) or abort(404)
    samples = [tc for tc in problem.test_cases if tc.is_sample]
    last = db.session.scalar(
        select(Submission).where(
            Submission.user_id == current_user.id,
            Submission.problem_id == problem.id,
            Submission.source == "practice",
        ).order_by(Submission.created_at.desc()).limit(1)
    )
    code = (last.code if last else None) or problem.starter_code or ""

    return render_template(
        "problems/practice_run.html",
        problem=problem,
        samples=samples,
        code=code,
        index=index,
        total=len(queue),
        queue=queue,
        meta=session.get(PRACTICE_META_KEY, {}),
    )


# ----------------------------- 提交记录 -----------------------------


@problems_bp.route("/submissions/")
@login_required
def submissions():
    status = (request.args.get("status") or "").strip()
    source = (request.args.get("source") or "").strip()
    page = request.args.get("page", type=int, default=1)

    stmt = select(Submission).where(Submission.user_id == current_user.id)
    if status:
        stmt = stmt.where(Submission.status == status)
    if source:
        stmt = stmt.where(Submission.source == source)
    pagination = db.paginate(stmt.order_by(Submission.created_at.desc()), page=page, per_page=15, error_out=False)

    total = db.session.scalar(select(func.count(Submission.id)).where(Submission.user_id == current_user.id)) or 0
    ac = db.session.scalar(
        select(func.count(Submission.id)).where(
            Submission.user_id == current_user.id, Submission.status == "AC"
        )
    ) or 0

    return render_template(
        "problems/submissions.html",
        pagination=pagination,
        submissions=pagination.items,
        status=status,
        source=source,
        total=total,
        accepted=ac,
    )


@problems_bp.route("/submissions/<int:submission_id>")
@login_required
def submission_detail(submission_id):
    sub = db.session.get(Submission, submission_id) or abort(404)
    if sub.user_id == current_user.id:
        return render_template("problems/submission_detail.html", sub=sub)
    # 教师只能查看自己班级学生的提交，避免跨班越权查看源代码
    if current_user.is_teacher and _teacher_can_view(current_user, sub):
        return render_template("problems/submission_detail.html", sub=sub)
    abort(403)


def _teacher_can_view(teacher, submission):
    from ..models import Classroom

    student = db.session.get(User, submission.user_id)
    if not student or not student.is_student:
        return False
    rooms = db.session.scalars(
        select(Classroom).where(Classroom.teacher_id == teacher.id)
    ).all()
    room_ids = {room.id for room in rooms}
    return any(room.id in room_ids for room in student.joined_classrooms)
