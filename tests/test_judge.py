# -*- coding: utf-8 -*-
"""判题核心逻辑：语法检查、AC/WA/RE/TLE、沙箱拦截（不依赖数据库）。"""
from types import SimpleNamespace

from app.judge import judge
from app.sandbox import run_code

CORRECT = "a, b = map(int, input().split())\nprint(a + b)"
CASES = [
    SimpleNamespace(input_data="1 2", expected_output="3"),
    SimpleNamespace(input_data="10 20", expected_output="30"),
]


def test_empty_code_ce():
    r = judge("", CASES)
    assert r["status"] == "CE"
    assert r["passed"] == 0


def test_syntax_error_ce():
    r = judge("def broken(:\n", CASES)
    assert r["status"] == "CE"
    assert "行" in r["message"]


def test_correct_code_ac():
    r = judge(CORRECT, CASES, time_limit=2)
    assert r["status"] == "AC"
    assert r["passed"] == 2
    assert r["total"] == 2


def test_wrong_answer_wa():
    r = judge("a, b = map(int, input().split())\nprint(a - b)", CASES, time_limit=2)
    assert r["status"] == "WA"
    assert r["passed"] == 0


def test_blank_lines_normalized():
    # 输出末尾多空行/行尾空格也应判对
    r = judge("a, b = map(int, input().split())\nprint(a + b)   \n\n", CASES, time_limit=2)
    assert r["status"] == "AC"


def test_blocked_import_re():
    r = judge("import socket\nprint('hi')", CASES, time_limit=2)
    assert r["status"] == "RE"
    assert "沙箱" in r["message"] or "禁止导入" in r["message"]


def test_blocked_subprocess_re():
    r = judge("import subprocess\nsubprocess.run(['ls'])", CASES, time_limit=2)
    assert r["status"] == "RE"


def test_infinite_loop_tle():
    r = judge("while True:\n    pass", CASES, time_limit=1)
    assert r["status"] == "TLE"


def test_run_code_stdin():
    r = run_code("print(input())", "hello", time_limit=2)
    assert r.status == "OK"
    assert r.stdout.strip() == "hello"


def test_run_code_capped_output():
    # 超大输出不应撑爆判题进程，应截断并正常返回
    r = run_code("while True:\n    print('x' * 1000)", time_limit=1)
    assert r.status == "TLE"
    assert r.stdout  # 有部分输出，且进程已被杀死
