"""初始化演示数据：知识点、示例账号、题库、班级与作业。

执行：python seed.py
"""
import json as _json
from datetime import datetime, timedelta

from app import create_app
from app.constants import QUESTION_TYPES, STAGES, SUBJECTS
from app.extensions import db
from app.models import (
    Classroom,
    ClassroomStudent,
    Homework,
    KnowledgePoint,
    Problem,
    TestCase,
    User,
)

KNOWLEDGE_POINTS = [
    {"name": "基础语法",        "subject": "信息技术", "grade": "小学高年级"},
    {"name": "输入输出",        "subject": "信息技术", "grade": "小学高年级"},
    {"name": "分支结构(if)",    "subject": "信息技术", "grade": "小学高年级"},
    {"name": "循环结构(for/while)", "subject": "信息技术", "grade": "小学高年级"},
    {"name": "字符串",          "subject": "信息技术", "grade": "小学高年级"},
    {"name": "列表",            "subject": "信息技术", "grade": "小学高年级"},
    {"name": "函数",            "subject": "信息技术", "grade": "小学高年级"},
    {"name": "数学运算",        "subject": "信息技术", "grade": "小学高年级"},
    {"name": "四则运算",        "subject": "数学",     "grade": "小学高年级"},
    {"name": "分数比较",        "subject": "数学",     "grade": "小学高年级"},
    {"name": "几何面积",        "subject": "数学",     "grade": "小学高年级"},
    {"name": "基本句型",        "subject": "英语",     "grade": "小学高年级"},
    {"name": "常用词汇",        "subject": "英语",     "grade": "小学高年级"},
    {"name": "语法规则",        "subject": "英语",     "grade": "小学高年级"},
]

CODE_DEFAULTS = {"type": "code", "subject": "信息技术", "stage": "小学"}

PROBLEMS = [
    {
        "title": "A + B 问题",
        "difficulty": "easy",
        "tags": ["输入输出", "基础语法"],
        "description": "输入两个整数 a 和 b（以空格分隔），输出它们的和。\n\n输入示例：3 5\n输出示例：8",
        "starter": "a, b = map(int, input().split())\nprint(a + b)",
        "reference": "a, b = map(int, input().split())\nprint(a + b)",
        "cases": [("3 5", "8"), ("10 20", "30"), ("-1 1", "0")],
        **CODE_DEFAULTS,
    },
    {
        "title": "判断奇偶数",
        "difficulty": "easy",
        "tags": ["分支结构(if)", "基础语法"],
        "description": "输入一个整数 n，若为偶数输出\"偶数\"，否则输出\"奇数\"。",
        "starter": "n = int(input())\n# 在这里补充你的代码\n",
        "reference": "n = int(input())\nprint('偶数' if n % 2 == 0 else '奇数')",
        "cases": [("4", "偶数"), ("7", "奇数"), ("0", "偶数")],
        **CODE_DEFAULTS,
    },
    {
        "title": "三个数的最大值",
        "difficulty": "easy",
        "tags": ["分支结构(if)", "数学运算"],
        "description": "输入三个整数（空格分隔），输出其中的最大值。\n\n输入示例：1 5 3\n输出示例：5",
        "starter": "a, b, c = map(int, input().split())\n# 不能使用 max()，请用 if 完成\n",
        "reference": "a, b, c = map(int, input().split())\nm = a\nif b > m:\n    m = b\nif c > m:\n    m = c\nprint(m)",
        "cases": [("1 5 3", "5"), ("-2 -5 -1", "-1"), ("7 7 7", "7")],
        **CODE_DEFAULTS,
    },
    {
        "title": "成绩等级转换",
        "difficulty": "easy",
        "tags": ["分支结构(if)"],
        "description": "输入一个整数成绩 score（0~100）：\n90 分及以上输出\"优秀\"；\n80~89 输出\"良好\"；\n60~79 输出\"及格\"；\n60 分以下输出\"不及格\"。",
        "starter": "score = int(input())\n# 在这里补充你的代码\n",
        "reference": "score = int(input())\nif score >= 90:\n    print('优秀')\nelif score >= 80:\n    print('良好')\nelif score >= 60:\n    print('及格')\nelse:\n    print('不及格')",
        "cases": [("95", "优秀"), ("85", "良好"), ("70", "及格"), ("45", "不及格")],
        **CODE_DEFAULTS,
    },
    {
        "title": "1 到 n 的累加和",
        "difficulty": "easy",
        "tags": ["循环结构(for/while)", "数学运算"],
        "description": "输入正整数 n，输出 1 + 2 + ... + n 的结果。\n\n输入示例：10\n输出示例：55",
        "starter": "n = int(input())\n# 使用 for 或 while 循环完成\n",
        "reference": "n = int(input())\ntotal = 0\nfor i in range(1, n + 1):\n    total += i\nprint(total)",
        "cases": [("10", "55"), ("100", "5050"), ("1", "1")],
        **CODE_DEFAULTS,
    },
    {
        "title": "输出 1~n 之间的偶数",
        "difficulty": "easy",
        "tags": ["循环结构(for/while)"],
        "description": "输入正整数 n，按从小到大的顺序输出 1~n（含）之间所有的偶数，用空格分隔。\n\n输入示例：10\n输出示例：2 4 6 8 10",
        "starter": "n = int(input())\n# 在这里补充你的代码\n",
        "reference": "n = int(input())\nres = [str(i) for i in range(1, n + 1) if i % 2 == 0]\nprint(' '.join(res))",
        "cases": [("10", "2 4 6 8 10"), ("5", "2 4"), ("2", "2")],
        **CODE_DEFAULTS,
    },
    {
        "title": "斐波那契数列第 n 项",
        "difficulty": "medium",
        "tags": ["循环结构(for/while)", "数学运算"],
        "description": "斐波那契数列定义为 F(1)=1，F(2)=1，F(n)=F(n-1)+F(n-2)。\n输入正整数 n，输出 F(n)。\n\n输入示例：6\n输出示例：8",
        "starter": "n = int(input())\n# 在这里补充你的代码\n",
        "reference": "n = int(input())\na = b = 1\nfor _ in range(3, n + 1):\n    a, b = b, a + b\nprint(b if n > 2 else 1)",
        "cases": [("1", "1"), ("2", "1"), ("6", "8"), ("10", "55")],
        **CODE_DEFAULTS,
    },
    {
        "title": "字符串反转",
        "difficulty": "easy",
        "tags": ["字符串"],
        "description": "输入一个字符串（不含空格），将其反转后输出。\n\n输入示例：hello\n输出示例：olleh",
        "starter": "s = input().strip()\n# 在这里补充你的代码\n",
        "reference": "s = input().strip()\nprint(s[::-1])",
        "cases": [("hello", "olleh"), ("Python", "nohtyP"), ("12345", "54321")],
        **CODE_DEFAULTS,
    },
    {
        "title": "素数判断",
        "difficulty": "medium",
        "tags": ["循环结构(for/while)", "数学运算"],
        "description": "输入一个正整数 n，若为素数输出\"是素数\"，否则输出\"不是素数\"。\n注意：1 不是素数。",
        "starter": "n = int(input())\n# 在这里补充你的代码\n",
        "reference": "n = int(input())\nif n < 2:\n    print('不是素数')\nelse:\n    for i in range(2, int(n ** 0.5) + 1):\n        if n % i == 0:\n            print('不是素数')\n            break\n    else:\n        print('是素数')",
        "cases": [("7", "是素数"), ("2", "是素数"), ("1", "不是素数"), ("9", "不是素数")],
        **CODE_DEFAULTS,
    },
    {
        "title": "阶乘计算",
        "difficulty": "medium",
        "tags": ["函数", "循环结构(for/while)"],
        "description": "输入非负整数 n，输出 n! 的值（0! = 1）。\n请使用函数完成。\n\n输入示例：5\n输出示例：120",
        "starter": "def factorial(n):\n    # 在这里补充你的代码\n    pass\n\n\nn = int(input())\nprint(factorial(n))",
        "reference": "def factorial(n):\n    result = 1\n    for i in range(2, n + 1):\n        result *= i\n    return result\n\n\nn = int(input())\nprint(factorial(n))",
        "cases": [("5", "120"), ("0", "1"), ("7", "5040")],
        **CODE_DEFAULTS,
    },
    {
        "title": "列表去重并排序",
        "difficulty": "medium",
        "tags": ["列表", "基础语法"],
        "description": "输入一行整数（空格分隔），去除重复元素后按升序输出，用空格分隔。\n\n输入示例：3 1 2 3 2\n输出示例：1 2 3",
        "starter": "nums = list(map(int, input().split()))\n# 在这里补充你的代码\n",
        "reference": "nums = list(map(int, input().split()))\nuniq = sorted(set(nums))\nprint(' '.join(map(str, uniq)))",
        "cases": [("3 1 2 3 2", "1 2 3"), ("5 5 5", "5"), ("-1 3 -1 0", "-1 0 3")],
        **CODE_DEFAULTS,
    },
    {
        "title": "统计字符出现次数",
        "difficulty": "medium",
        "tags": ["字符串", "循环结构(for/while)"],
        "description": "输入两行：第一行为一个字符串 s，第二行为一个字符 ch。\n输出 ch 在 s 中出现的次数。\n\n输入示例：\nhello\nl\n输出示例：2",
        "starter": "s = input()\nch = input().strip()\n# 在这里补充你的代码\n",
        "reference": "s = input()\nch = input().strip()\ncount = 0\nfor c in s:\n    if c == ch:\n        count += 1\nprint(count)",
        "cases": [("hello\nl", "2"), ("banana\na", "3"), ("abc\na", "1")],
        **CODE_DEFAULTS,
    },
    {
        "title": "水仙花数判断",
        "difficulty": "medium",
        "tags": ["循环结构(for/while)", "数学运算"],
        "description": "输入一个三位正整数 n，若它等于各位数字立方之和（水仙花数）则输出\"是\"，否则输出\"否\"。\n\n输入示例：153\n输出示例：是（1³+5³+3³=153）",
        "starter": "n = int(input())\n# 在这里补充你的代码\n",
        "reference": "n = int(input())\nnums = list(map(int, str(n)))\ntotal = sum(x ** 3 for x in nums)\nprint('是' if total == n else '否')",
        "cases": [("153", "是"), ("370", "是"), ("123", "否"), ("947", "否")],
        **CODE_DEFAULTS,
    },
    {
        "title": "冒泡排序",
        "difficulty": "hard",
        "tags": ["列表", "循环结构(for/while)", "基础语法"],
        "description": "输入一行整数（空格分隔），使用冒泡排序将其升序排列后输出，用空格分隔。\n（不要直接使用 sorted()，请用冒泡排序算法实现）\n\n输入示例：5 3 1 4\n输出示例：1 3 4 5",
        "starter": "nums = list(map(int, input().split()))\n# 使用冒泡排序完成\n",
        "reference": "nums = list(map(int, input().split()))\nfor i in range(len(nums) - 1):\n    for j in range(len(nums) - 1 - i):\n        if nums[j] > nums[j + 1]:\n            nums[j], nums[j + 1] = nums[j + 1], nums[j]\nprint(' '.join(map(str, nums)))",
        "cases": [("5 3 1 4", "1 3 4 5"), ("2 1", "1 2"), ("9 8 7 6 5", "5 6 7 8 9")],
        **CODE_DEFAULTS,
    },
    {
        "title": "Python 中 list 和 tuple 的主要区别是什么？",
        "difficulty": "easy",
        "tags": ["基础语法", "列表"],
        "description": "下列关于 Python 中 list（列表）和 tuple（元组）的描述，正确的是哪一项？",
        "type": "choice",
        "subject": "信息技术",
        "stage": "小学",
        "options": ["list 是可变的，tuple 是不可变的", "list 是不可变的，tuple 是可变的", "两者完全相同，只是名字不同", "list 只能存数字，tuple 只能存字符串"],
        "standard_answer": _json.dumps({"multi": False, "correct": ["A"]}, ensure_ascii=False),
    },
    {
        "title": "判断：Python 中 for 循环只能遍历列表，不能遍历字符串。",
        "difficulty": "easy",
        "tags": ["循环结构(for/while)"],
        "description": "Python 中 for 循环只能遍历列表，不能遍历字符串。",
        "type": "judge",
        "subject": "信息技术",
        "stage": "小学",
        "standard_answer": _json.dumps({"multi": False, "correct": ["F"]}, ensure_ascii=False),
    },
    {
        "title": "圆的周长公式填空",
        "difficulty": "easy",
        "tags": ["数学运算"],
        "description": "请填写圆的周长公式（用 r 表示半径）：\n\nC = ____ × r",
        "type": "fill",
        "subject": "数学",
        "stage": "小学",
        "standard_answer": _json.dumps([["2 * pi", "2*pi", "2π", "2 * π"]], ensure_ascii=False),
    },
    {
        "title": "语文古诗填空",
        "difficulty": "easy",
        "tags": ["语文"],
        "description": "请补全李白《静夜思》中的诗句：\n\n床前明月光，____。\n举头望明月，____。",
        "type": "fill",
        "subject": "语文",
        "stage": "小学",
        "standard_answer": _json.dumps([["疑是地上霜"], ["低头思故乡"]], ensure_ascii=False),
    },
    {
        "title": "数学：25 × 4 + 60 ÷ 3 = ?",
        "difficulty": "easy",
        "tags": ["四则运算", "数学运算"],
        "description": "计算：25 × 4 + 60 ÷ 3 = ?",
        "type": "choice",
        "subject": "数学",
        "stage": "小学",
        "options": ["120", "100", "140", "110"],
        "standard_answer": _json.dumps({"multi": False, "correct": ["A"]}, ensure_ascii=False),
    },
    {
        "title": "数学：以下哪个分数最大？",
        "difficulty": "easy",
        "tags": ["分数比较"],
        "description": "下列四个分数中，最大的是哪一个？",
        "type": "choice",
        "subject": "数学",
        "stage": "小学",
        "options": ["3/4", "2/3", "1/2", "5/8"],
        "standard_answer": _json.dumps({"multi": False, "correct": ["A"]}, ensure_ascii=False),
    },
    {
        "title": "数学：正方形面积为 64，边长是？",
        "difficulty": "easy",
        "tags": ["几何面积"],
        "description": "一个正方形的面积是 64 平方厘米，它的边长是多少厘米？",
        "type": "choice",
        "subject": "数学",
        "stage": "小学",
        "options": ["6 厘米", "7 厘米", "8 厘米", "9 厘米"],
        "standard_answer": _json.dumps({"multi": False, "correct": ["C"]}, ensure_ascii=False),
    },
    {
        "title": "英语判断：'I am a student.' 是正确的陈述句。",
        "difficulty": "easy",
        "tags": ["基本句型", "常用词汇"],
        "description": "判断：'I am a student.' 是一个语法正确的陈述句。",
        "type": "judge",
        "subject": "英语",
        "stage": "小学",
        "standard_answer": _json.dumps({"multi": False, "correct": ["T"]}, ensure_ascii=False),
    },
    {
        "title": "英语判断：英语单词 'apple' 的复数形式是 'apples'。",
        "difficulty": "easy",
        "tags": ["语法规则", "常用词汇"],
        "description": "判断：英语单词 'apple' 的复数形式是 'apples'。",
        "type": "judge",
        "subject": "英语",
        "stage": "小学",
        "standard_answer": _json.dumps({"multi": False, "correct": ["T"]}, ensure_ascii=False),
    },
]


def get_or_create_kp(name, subject="信息技术", grade=""):
    kp = KnowledgePoint.query.filter_by(name=name).first()
    if not kp:
        kp = KnowledgePoint(name=name, subject=subject, grade=grade)
        db.session.add(kp)
        db.session.flush()
    else:
        if kp.subject != subject:
            kp.subject = subject
        if kp.grade != grade and grade:
            kp.grade = grade
    return kp


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        for kp_def in KNOWLEDGE_POINTS:
            get_or_create_kp(kp_def["name"], kp_def.get("subject", "信息技术"), kp_def.get("grade", ""))

        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", display_name="系统管理员", role="admin")
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.flush()

        teacher = User.query.filter_by(username="teacher").first()
        if not teacher:
            teacher = User(username="teacher", display_name="王老师", role="teacher")
            teacher.set_password("123456")
            db.session.add(teacher)
            db.session.flush()

        students = []
        for username, name in (("student", "李小明"), ("student2", "张小红")):
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, display_name=name, role="student")
                user.set_password("123456")
                db.session.add(user)
                db.session.flush()
            students.append(user)

        created = 0
        updated = 0
        for item in PROBLEMS:
            problem = Problem.query.filter_by(title=item["title"]).first()
            if problem:
                patched = False
                expected_type = item.get("type", "code")
                expected_subject = item.get("subject", "信息技术")
                expected_stage = item.get("stage", "小学")
                if problem.type != expected_type:
                    problem.type = expected_type
                    patched = True
                if problem.subject != expected_subject:
                    problem.subject = expected_subject
                    patched = True
                if problem.stage != expected_stage:
                    problem.stage = expected_stage
                    patched = True
                if patched:
                    updated += 1
                continue

            problem = Problem(
                title=item["title"],
                description=item["description"],
                difficulty=item["difficulty"],
                type=item.get("type", "code"),
                subject=item.get("subject", "信息技术"),
                stage=item.get("stage", "小学"),
                starter_code=item.get("starter"),
                reference_code=item.get("reference"),
                options=_json.dumps(item["options"], ensure_ascii=False) if item.get("options") else None,
                standard_answer=item.get("standard_answer"),
                author_id=teacher.id,
            )
            problem.tags = [get_or_create_kp(t, subject=item.get("subject", "信息技术")) for t in item["tags"]]
            for idx, (stdin_data, expected) in enumerate(item.get("cases", [])):
                problem.test_cases.append(
                    TestCase(
                        input_data=stdin_data,
                        expected_output=expected,
                        is_sample=(idx == 0),
                        score=10,
                    )
                )
            db.session.add(problem)
            created += 1
        db.session.flush()

        room = Classroom.query.filter_by(join_code="CLASS1").first()
        if not room:
            room = Classroom(name="六年级1班", join_code="CLASS1", teacher_id=teacher.id)
            db.session.add(room)
            db.session.flush()
        elif room.name != "六年级1班":
            room.name = "六年级1班"
        for s in students:
            if s not in room.students:
                room.students.append(s)
                db.session.add(ClassroomStudent(classroom_id=room.id, student_id=s.id))

        if not Homework.query.filter_by(title="第1次作业：分支与循环").first():
            titles = ["判断奇偶数", "成绩等级转换", "1 到 n 的累加和", "斐波那契数列第 n 项", "素数判断"]
            hw = Homework(
                title="第1次作业：分支与循环",
                description="完成下列 5 道题目，重点练习 if 分支与 for/while 循环。",
                classroom_id=room.id,
                teacher_id=teacher.id,
                due_at=datetime.now() + timedelta(days=7),
            )
            db.session.add(hw)
            db.session.flush()
            for t in titles:
                p = Problem.query.filter_by(title=t).first()
                if p:
                    hw.problems.append(p)

        db.session.commit()
        print(f"初始化完成：新增题目 {created} 道，补齐旧题目 {updated} 道")
        print("管理员账号：admin / admin123")
        print("教师账号：teacher / 123456")
        print("学生账号：student / 123456、student2 / 123456")
        print("班级码：CLASS1")


if __name__ == "__main__":
    main()
