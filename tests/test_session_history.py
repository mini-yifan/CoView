import json

import pytest

from baodou_ai.ai.session_history import SessionHistory


def test_add_and_get_tasks(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    sh.add_task("打开浏览器", "completed", "成功打开", "", 3)
    tasks = sh.get_recent_tasks()
    assert len(tasks) == 1
    assert tasks[0]["instruction"] == "打开浏览器"
    assert tasks[0]["status"] == "completed"
    assert tasks[0]["report"] == "成功打开"
    assert tasks[0]["steps"] == 3


def test_max_five_tasks(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    for i in range(7):
        sh.add_task(f"任务{i}", "completed", f"结果{i}", "", i)
    tasks = sh.get_recent_tasks()
    assert len(tasks) == 5
    assert tasks[0]["instruction"] == "任务2"
    assert tasks[-1]["instruction"] == "任务6"


def test_build_interrupted_report():
    iterations = [
        {"tool_name": "click", "action": "点击搜索框"},
        {"tool_name": "type", "action": "输入文字"},
        {"tool_name": "scroll", "action": "向下滚动"},
    ]
    result = SessionHistory.build_interrupted_report("搜索内容", iterations)
    assert "was interrupted" in result
    assert "搜索内容" in result
    assert "3 steps" in result
    assert "click(点击搜索框)" in result
    assert "type(输入文字)" in result
    assert "scroll(向下滚动)" in result


def test_build_interrupted_report_empty():
    result = SessionHistory.build_interrupted_report("测试任务", [])
    assert "was interrupted" in result
    assert "0 steps" in result


def test_build_failed_report():
    iterations = [{"tool_name": "click", "action": "点击按钮"}]
    result = SessionHistory.build_failed_report("执行操作", iterations, "超时错误")
    assert "failed" in result
    assert "超时错误" in result
    assert "执行操作" in result


def test_build_context_prompt_completed(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    sh.add_task("打开浏览器", "completed", "成功打开", "", 3)
    prompt = sh.build_context_prompt()
    assert "打开浏览器" in prompt
    assert "Completed" in prompt
    assert "成功打开" in prompt
    assert "Agent memory" not in prompt


def test_build_context_prompt_uses_context_report_without_changing_display_report(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    sh.add_task(
        "后台代码任务：调研",
        "completed",
        "精简播报",
        "",
        0,
        context_report="精简播报\n\n最终结果：\n完整调研表格",
    )

    task = sh.get_recent_tasks()[0]
    assert task["report"] == "精简播报"

    prompt = sh.build_context_prompt()
    assert "精简播报" in prompt
    assert "完整调研表格" in prompt


def test_build_context_prompt_interrupted(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    sh.add_task("搜索内容", "interrupted", "被中断报告", "记住了一些内容", 5)
    prompt = sh.build_context_prompt()
    assert "搜索内容" in prompt
    assert "Interrupted" in prompt
    assert "Agent memory" in prompt
    assert "记住了一些内容" in prompt


def test_build_context_prompt_empty(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    prompt = sh.build_context_prompt()
    assert prompt == ""


def test_build_context_prompt_skips_entries_hidden_from_context(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    sh.add_task("后台代码任务：修复测试", "completed", "后台汇报", "", 0, include_in_context=False)
    sh.add_task("打开浏览器", "completed", "成功打开", "", 1)

    prompt = sh.build_context_prompt()

    assert "后台代码任务：修复测试" not in prompt
    assert "打开浏览器" in prompt


def test_clear(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    sh.add_task("任务A", "completed", "完成", "", 1)
    sh.clear()
    assert sh.get_recent_tasks() == []
    sh2 = SessionHistory(file_path=str(tmp_path / "test_history.json"))
    assert sh2.get_recent_tasks() == []


def test_corrupted_json(tmp_path):
    file_path = str(tmp_path / "test_history.json")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{invalid json content!!!")
    sh = SessionHistory(file_path=file_path)
    assert sh.get_recent_tasks() == []


def test_custom_max_tasks(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"), max_tasks=3)
    for i in range(5):
        sh.add_task(f"任务{i}", "completed", f"结果{i}", "", i)
    tasks = sh.get_recent_tasks()
    assert len(tasks) == 3
    assert tasks[0]["instruction"] == "任务2"


def test_set_max_tasks(tmp_path):
    sh = SessionHistory(file_path=str(tmp_path / "test_history.json"), max_tasks=5)
    for i in range(5):
        sh.add_task(f"任务{i}", "completed", f"结果{i}", "", i)
    sh.set_max_tasks(2)
    tasks = sh.get_recent_tasks()
    assert len(tasks) == 2
    assert tasks[0]["instruction"] == "任务3"
