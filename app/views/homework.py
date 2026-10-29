from datetime import datetime

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required
from sqlalchemy import select

from .. import db
from ..decorators import student_required
from ..models import Homework, Problem, Submission

homework_bp = Blueprint("homework", __name__, url_prefix="/homeworks", template_folder="../templates")


def _best_status_map(user_id, homework_id):
    """返回 {problem_id: Submission}，取该题在本次作业中最好的一次提交。"""
    subs = db.session.scalars(
        select(Submission).where(
            Submission.user_id == user_id, Submission.homework_id == homework_id
        ).order_by(Submission.created_at.desc())
    ).all()
    best = {}
    for s in subs:
        cur = best.get(s.problem_id)
        if cur is None or (s.status == "AC" and cur.status != "AC") or (
            s.status == cur.status and s.score > cur.score
        ):
            best[s.problem_id] = s
    return best


@homework_bp.route("/")
@login_required
@student_required
def index():
    items = []
    for room in current_user.joined_classrooms:
        homeworks = db.session.scalars(
            select(Homework).where(Homework.classroom_id == room.id).order_by(Homework.due_at.desc())
        ).all()
        for hw in homeworks:
            best = _best_status_map(current_user.id, hw.id)
            done = sum(1 for s in best.values() if s.status == "AC")
            items.append(
                {
                    "homework": hw,
                    "classroom": room,
                    "done": done,
                    "total": len(hw.problems),
                    "closed": hw.is_closed(),
                }
            )
    items.sort(key=lambda x: x["homework"].due_at, reverse=True)
    return render_template("homework/list.html", items=items, now=datetime.now())


@homework_bp.route("/<int:homework_id>")
@login_required
@student_required
def detail(homework_id):
    hw = db.session.get(Homework, homework_id) or abort(404)
    if hw.classroom not in current_user.joined_classrooms:
        abort(403)
    best = _best_status_map(current_user.id, hw.id)
    rows = []
    for problem in hw.problems:
        sub = best.get(problem.id)
        rows.append(
            {
                "problem": problem,
                "status": sub.status if sub else "未提交",
                "status_label": sub.status_label if sub else "未提交",
                "score": sub.score if sub else 0,
                "last_at": sub.created_at if sub else None,
            }
        )
    done = sum(1 for r in rows if r["status"] == "AC")
    return render_template(
        "homework/detail.html",
        homework=hw,
        rows=rows,
        done=done,
        total=len(rows),
        now=datetime.now(),
    )


@homework_bp.route("/<int:homework_id>/problems/<int:problem_id>")
@login_required
@student_required
def solve(homework_id, problem_id):
    hw = db.session.get(Homework, homework_id) or abort(404)
    if hw.classroom not in current_user.joined_classrooms:
        abort(403)
    problem = db.session.get(Problem, problem_id) or abort(404)
    if problem not in hw.problems:
        abort(404)
    samples = [tc for tc in problem.test_cases if tc.is_sample]
    last = db.session.scalar(
        select(Submission).where(
            Submission.user_id == current_user.id,
            Submission.homework_id == homework_id,
            Submission.problem_id == problem_id,
        ).order_by(Submission.created_at.desc()).limit(1)
    )
    code = (last.code if last else None) or problem.starter_code or ""
    history = db.session.scalars(
        select(Submission).where(
            Submission.user_id == current_user.id,
            Submission.homework_id == homework_id,
            Submission.problem_id == problem_id,
        ).order_by(Submission.created_at.desc()).limit(5)
    ).all()
    return render_template(
        "problems/detail.html",
        problem=problem,
        samples=samples,
        code=code,
        homework=hw,
        history=history,
        tab="homework",
        now=datetime.now(),
    )
