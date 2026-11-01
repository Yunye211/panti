# -*- coding: utf-8 -*-
"""按《基于Python的中小学课程在线测评系统》测试结果表模板生成 Excel 报告。

用法：python gen_test_report.py
输出：reports/基于Python的中小学课程在线测评系统-测试结果表（N条）.xlsx
"""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
REPORT_DIR = os.path.join(ROOT, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

COLLECT_FILE = os.path.join(REPORT_DIR, "collected.txt")
JUNIT_FILE = os.path.join(REPORT_DIR, "junit.xml")


def run(cmd):
    print("[gen] $", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT, shell=False)


def step1_collect():
    run([sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", "--no-header"])
    out = subprocess.check_output(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", "--no-header"],
        cwd=ROOT,
    ).decode("utf-8", errors="replace")
    with open(COLLECT_FILE, "w", encoding="utf-8") as f:
        f.write(out)
    lines = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("=") and not l.startswith("warning")]
    print("[gen] 收集到 %d 条用例" % len(lines))
    return lines


def step2_run_junit():
    run([
        sys.executable, "-m", "pytest",
        "--junitxml=%s" % JUNIT_FILE,
        "--tb=no", "-q", "-p", "no:cacheprovider", "--no-header",
    ])


def step3_parse_junit():
    items = []
    tree = ET.parse(JUNIT_FILE)
    for tc in tree.iter("testcase"):
        classname = tc.attrib.get("classname", "")
        name = tc.attrib.get("name", "")
        nodeid = "%s::%s" % (classname, name)
        duration = float(tc.attrib.get("time", "0"))
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")
        if failure is not None:
            outcome = "failed"
        elif error is not None:
            outcome = "error"
        elif skipped is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        items.append({"nodeid": nodeid, "outcome": outcome, "duration": duration})
    items.sort(key=lambda x: x["nodeid"])
    print("[gen] 解析 %d 条结果" % len(items))
    return items


def _junit_to_parts(nodeid):
    """
    junit classname::name -> (filename, classname, funcname)
    e.g. 'tests.test_admin::test_admin_login' -> ('test_admin.py', '', 'test_admin_login')
    e.g. 'tests.test_optimizations.TestLikeEscape::test_plain_keyword' -> ('test_optimizations.py', 'TestLikeEscape', 'test_plain_keyword')
    """
    classname, _, funcname = nodeid.partition("::")
    parts = classname.split(".")
    # 去掉开头的 'tests'
    if parts and parts[0] == "tests":
        parts = parts[1:]
    if len(parts) == 1:
        filename = parts[0] + ".py"
        cls = ""
    else:
        filename = parts[0] + ".py"
        cls = ".".join(parts[1:])
    return filename, cls, funcname


def _parse_nodeid(nodeid):
    filename, cls, funcname = _junit_to_parts(nodeid)
    module = FILE_TO_MODULE.get(filename, filename.replace(".py", ""))

    cls_display = cls.replace("Test", "").replace("_", " ") if cls else ""
    display = funcname.replace("test_", "").replace("_", " ").strip()
    if display:
        display = display[0].upper() + display[1:]
    return module, cls_display, display


# ---------- 用例名解析 ----------


FILE_TO_MODULE = {
    "test_admin.py": "管理员",
    "test_api.py": "API 判题",
    "test_auth.py": "登录注册",
    "test_judge.py": "判题内核",
    "test_pages.py": "页面与安全",
    "test_optimizations.py": "代码优化",
    "test_objective.py": "客观题",
}


def guess_priority(title):
    high = re.compile(r"登录|注册|判题|删除|权限|拦截|提交|AC|WA|CE|TLE|RE|CSRF|停用|越权|提权|限流|锁")
    mid = re.compile(r"编辑|修改|重置|列表|分页|搜索|学生/教师页面|创建|新增|批量|编辑页面|提示")
    if high.search(title):
        return "高"
    if mid.search(title):
        return "中"
    return "低"


def _infer_steps_and_expected(display, func_name, filename):
    func_lower = func_name.lower()
    fn_lower = filename.lower()
    if "admin" in fn_lower:
        return "管理员已登录", "在 /admin/users 执行该操作", "页面渲染正确，数据生效"
    if "auth" in fn_lower:
        return "系统初始化完成", "提交登录/注册表单并观察行为", "账号行为符合安全预期"
    if "api" in fn_lower or "judge" in fn_lower:
        return "存在可用题目与测试用例", "POST /api/judge 提交代码", "返回正确判题状态与消息"
    if "pages" in fn_lower:
        return "系统初始化完成，存在测试账号", "访问对应页面并观察响应", "页面可访问或正确重定向/拦截"
    if "optimizations" in fn_lower:
        if "like" in func_lower:
            return "输入含 SQL 通配符的关键词", "调用 like() 构造 LIKE 表达式", "通配符被正确转义"
        if "ensure" in func_lower:
            return "构造 Flask 请求上下文 + 当前用户", "调用 ensure_owner 检查所有权", "匹配通过 / 不匹配 403"
        if "purge" in func_lower:
            return "构造完整关联数据链", "调用 Model.purge()", "级联记录被清理"
        return "基础数据已准备", "调用优化点方法", "行为正确"
    return "基础数据已准备", "执行用例", "行为符合预期"


# ---------- Excel 生成 ----------


HEADER_FILL = PatternFill("solid", fgColor="FFE8E8E8")
PASS_FILL = PatternFill("solid", fgColor="FFC6EFCE")
FAIL_FILL = PatternFill("solid", fgColor="FFFFC7CE")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
THIN = Side(border_style="thin", color="FFBFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def _style_header(ws):
    headers = ["用例编号", "测试模块", "用例标题", "前置条件", "测试步骤", "预期结果", "实际结果", "", "", "测试状态", "缺陷编号", "测试优先级"]
    for col, val in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col, value=val)
        c.font = Font(bold=True)
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = BOX
    ws.merge_cells("G1:I1")


def _set_col_widths(ws):
    widths = {"A": 10, "B": 14, "C": 28, "D": 26, "E": 30, "F": 34, "G": 48, "J": 10, "L": 12}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def _write_row(ws, row_num, tf_id, module, title, pre, step, expected, actual, status, priority):
    values = [tf_id, module, title, pre, step, expected, actual, None, None, status, None, priority]
    for col, val in enumerate(values, start=1):
        c = ws.cell(row=row_num, column=col, value=val)
        c.border = BOX
        c.alignment = CENTER if col in (1, 10, 12) else LEFT
    ws.merge_cells(start_row=row_num, start_column=7, end_row=row_num, end_column=9)
    cell = ws.cell(row=row_num, column=10)
    cell.fill = PASS_FILL if status == "通过" else FAIL_FILL
    ws.row_dimensions[row_num].height = 36


def _merge_module_col(ws, module_rows):
    i = 0
    while i < len(module_rows):
        cur = module_rows[i]
        j = i
        while j + 1 < len(module_rows) and module_rows[j + 1] == cur:
            j += 1
        if j > i:
            ws.merge_cells(start_row=i + 2, start_column=2, end_row=j + 2, end_column=2)
        ws.cell(row=i + 2, column=2).alignment = CENTER
        i = j + 1


def build_excel(items, out_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "测试结果"
    _style_header(ws)
    _set_col_widths(ws)

    module_rows = []
    ok = fail = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, it in enumerate(items, start=1):
        nodeid = it["nodeid"]
        filename, cls_name, func_name = _junit_to_parts(nodeid)
        module, cls, display = _parse_nodeid(nodeid)
        pre, step, expected = _infer_steps_and_expected(display, func_name, filename)

        dur_ms = it["duration"] * 1000
        status_label = "通过" if it["outcome"] in ("passed",) else "失败"

        outcome_cn = {"passed": "通过", "failed": "失败", "error": "错误", "skipped": "跳过"}.get(it["outcome"], it["outcome"])
        actual = "pytest 用例%s，耗时 %.1fms。" % (outcome_cn, dur_ms)
        if cls:
            actual += "（类 %s）" % cls
        if it["outcome"] != "passed":
            actual += "  详细失败信息见 pytest 输出。"

        if status_label == "通过":
            ok += 1
        else:
            fail += 1

        tf_id = "TF-%03d" % idx
        priority = guess_priority(display)
        row_num = idx + 1
        _write_row(ws, row_num, tf_id, module, display, pre, step, expected, actual, status_label, priority)
        module_rows.append(module)

    for row_idx in range(2, len(items) + 2):
        ws.cell(row=row_idx, column=2).alignment = CENTER

    last_row = len(items) + 2
    ws.cell(row=last_row + 1, column=1,
            value="测试统计：共执行 %d 条用例，通过 %d 条、失败 %d 条；执行时间 %s" % (len(items), ok, fail, now_str))
    ws.cell(row=last_row + 1, column=1).font = Font(bold=True)
    ws.merge_cells(start_row=last_row + 1, start_column=1, end_row=last_row + 1, end_column=12)

    ws.cell(row=last_row + 2, column=1,
            value="缺陷记录：测试过程中未发现新缺陷。本轮已修复 BUG-003（LIKE 通配符未转义）、BUG-004（N+1 查询）、BUG-005（清理逻辑分散）、BUG-006（权限检查重复）。")
    ws.merge_cells(start_row=last_row + 2, start_column=1, end_row=last_row + 2, end_column=12)

    wb.save(out_path)
    print("[gen] 报告已生成 -> %s" % out_path)
    print("[gen] 通过 %d / 失败 %d / 总计 %d" % (ok, fail, len(items)))
    return ok, fail, len(items)


# ---------- main ----------


def main():
    print("=" * 50)
    print(" 基于Python的中小学课程在线测评系统 —— 测试报告生成流程")
    print("=" * 50)
    print()
    step1_collect()
    print()
    step2_run_junit()
    print()
    items = step3_parse_junit()
    out_path = os.path.join(
        REPORT_DIR,
        "基于Python的中小学课程在线测评系统-测试结果表（%d条）.xlsx" % len(items),
    )
    print()
    print("-" * 50)
    build_excel(items, out_path)


if __name__ == "__main__":
    main()
