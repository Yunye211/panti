from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db

# ----------------------------- 关联表 -----------------------------

problem_tags = db.Table(
    "problem_tags",
    db.Column("problem_id", db.Integer, db.ForeignKey("problems.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("knowledge_points.id"), primary_key=True),
)

classroom_students = db.Table(
    "classroom_students",
    db.Column("classroom_id", db.Integer, db.ForeignKey("classrooms.id"), primary_key=True),
    db.Column("student_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)

homework_problems = db.Table(
    "homework_problems",
    db.Column("homework_id", db.Integer, db.ForeignKey("homeworks.id"), primary_key=True),
    db.Column("problem_id", db.Integer, db.ForeignKey("problems.id"), primary_key=True),
)


DIFFICULTIES = {"easy": "简单", "medium": "中等", "hard": "困难"}
STATUS_LABELS = {
    "AC": "通过",
    "WA": "答案错误",
    "RE": "运行时错误",
    "CE": "语法错误",
    "TLE": "运行超时",
}


# ----------------------------- 模型 -----------------------------


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(64), nullable=False, default="")
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="student")  # student / teacher / admin
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    joined_classrooms = db.relationship(
        "Classroom", secondary=classroom_students, back_populates="students"
    )

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_teacher(self):
        return self.role == "teacher"

    @property
    def is_student(self):
        return self.role == "student"

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def role_label(self):
        return {"student": "学生", "teacher": "教师", "admin": "管理员"}.get(self.role, self.role)

    @property
    def name(self):
        return self.display_name or self.username


class KnowledgePoint(db.Model):
    __tablename__ = "knowledge_points"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255), default="")


class Problem(db.Model):
    __tablename__ = "problems"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    difficulty = db.Column(db.String(16), nullable=False, default="easy")
    starter_code = db.Column(db.Text, default="")
    reference_code = db.Column(db.Text, default="")
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    tags = db.relationship("KnowledgePoint", secondary=problem_tags, backref="problems")
    test_cases = db.relationship(
        "TestCase", back_populates="problem", cascade="all, delete-orphan", order_by="TestCase.id"
    )

    @property
    def difficulty_label(self):
        return DIFFICULTIES.get(self.difficulty, self.difficulty)

    @property
    def tag_names(self):
        return [t.name for t in self.tags]


class TestCase(db.Model):
    __tablename__ = "test_cases"

    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False)
    input_data = db.Column(db.Text, default="")
    expected_output = db.Column(db.Text, default="")
    is_sample = db.Column(db.Boolean, default=True)
    score = db.Column(db.Integer, default=10)

    problem = db.relationship("Problem", back_populates="test_cases")


class Classroom(db.Model):
    __tablename__ = "classrooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    join_code = db.Column(db.String(20), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    students = db.relationship(
        "User", secondary=classroom_students, back_populates="joined_classrooms"
    )


class ClassroomStudent(db.Model):
    """学生加入班级的记录（方便扩展）"""
    __tablename__ = "classroom_student_records"

    id = db.Column(db.Integer, primary_key=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.now)


class Homework(db.Model):
    __tablename__ = "homeworks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    due_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    classroom = db.relationship("Classroom", backref="homeworks")
    problems = db.relationship("Problem", secondary=homework_problems, backref="homeworks")

    def is_closed(self):
        return datetime.now() > self.due_at


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    problem_id = db.Column(db.Integer, db.ForeignKey("problems.id"), nullable=False)
    homework_id = db.Column(db.Integer, db.ForeignKey("homeworks.id"))
    code = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(8), nullable=False, default="WA")
    passed_count = db.Column(db.Integer, default=0)
    total_count = db.Column(db.Integer, default=0)
    message = db.Column(db.Text, default="")
    max_time_ms = db.Column(db.Integer, default=0)
    source = db.Column(db.String(16), default="practice")  # practice / free / homework
    is_late = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    author = db.relationship("User", backref="submissions")
    problem = db.relationship("Problem", backref="submissions")
    homework = db.relationship("Homework", backref="submissions")

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def score(self):
        """百分制得分"""
        if not self.total_count:
            return 0
        return round(self.passed_count * 100 / self.total_count)
