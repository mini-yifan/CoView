import pytest

from baodou_ai.agent.protocol import normalize_agent_response
from baodou_ai.agent.tool_registry import get_tool_definition, get_tool_json_schema, normalize_tool_args
from baodou_ai.core.automation import (
    AutomationController,
    DOCUMENT_EXTRACT_DIR,
    MEMORY_FILE,
)


def test_normalize_code_agent_tool_args_accepts_workspace_timeout_goal_and_job_id(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()

    normalized = normalize_tool_args(
        "code_agent",
        {
            "task": "Fix failing tests",
            "title": "修复测试",
            "goal": "修复当前项目中的失败测试",
            "job_id": "code-job-0001",
            "workspace_path": str(workspace),
            "timeout_seconds": "600",
        },
    )

    assert normalized == {
        "task": "Fix failing tests",
        "title": "修复测试",
        "goal": "修复当前项目中的失败测试",
        "job_id": "code-job-0001",
        "workspace_path": str(workspace.resolve()),
        "timeout_seconds": 600,
    }


def test_normalize_agent_response_accepts_code_agent_branch(tmp_path):
    workspace = tmp_path / "project"
    workspace.mkdir()

    response = normalize_agent_response({
        "thinking": "这是一个耗时的代码任务，应该切到后台执行。",
        "code_agent": {
            "task": "Review the current repository and summarize risks",
            "workspace_path": str(workspace),
        },
    })

    assert response == {
        "thinking": "这是一个耗时的代码任务，应该切到后台执行。",
        "code_agent": {
            "task": "Review the current repository and summarize risks",
            "workspace_path": str(workspace.resolve()),
        },
    }


def test_normalize_stop_code_agent_tool_args_accepts_job_id():
    normalized = normalize_tool_args(
        "stop_code_agent",
        {
            "job_id": "code-job-0001",
        },
    )

    assert normalized == {
        "job_id": "code-job-0001",
    }


def test_normalize_agent_response_accepts_stop_code_agent_branch():
    response = normalize_agent_response({
        "thinking": "用户要求停止后台代码任务。",
        "stop_code_agent": {
            "job_id": "code-job-0001",
        },
    })

    assert response == {
        "thinking": "用户要求停止后台代码任务。",
        "stop_code_agent": {
            "job_id": "code-job-0001",
        },
    }


def test_normalize_code_agent_tool_args_rejects_missing_task():
    with pytest.raises(ValueError, match="task 不能为空"):
        normalize_tool_args("code_agent", {"workspace_path": "/tmp"})

    with pytest.raises(ValueError, match="job_id 不能为空"):
        normalize_tool_args("stop_code_agent", {})


def test_normalize_code_agent_tool_args_rejects_empty_goal_or_job_id():
    with pytest.raises(ValueError, match="goal 不能为空"):
        normalize_tool_args("code_agent", {"task": "x", "goal": "   "})

    with pytest.raises(ValueError, match="job_id 不能为空"):
        normalize_tool_args("code_agent", {"task": "x", "job_id": "   "})


def test_code_agent_tool_definition_requires_model_to_rewrite_full_followup_task():
    definition = get_tool_definition("code_agent")

    assert "Use code_agent when the task is to produce, modify, organize, analyze, or save a reusable deliverable" in definition.description
    assert "spreadsheets, CSV" in definition.description
    assert "Do NOT use code_agent for foreground website/app tasks" in definition.description
    assert "checking several accounts' follower counts" in definition.description
    assert "open_in_browser" in definition.description
    assert "read_current_page" in definition.description
    assert "open-ended or multi-step research" not in definition.description
    assert "you MUST rewrite a COMPLETE fresh" in definition.description
    assert "Preserve the user's explicit scope" in definition.description
    assert "Do NOT infer or add requirements" in definition.description
    assert "do not add unstated features" in definition.args_prompt
    assert "does NOT merge tasks" in definition.description

    stop_definition = get_tool_definition("stop_code_agent")
    assert "Stop a currently running background code-agent task" in stop_definition.description


def test_manage_files_tool_definition_mentions_batch_limits():
    definition = get_tool_definition("manage_files")

    assert "at most 20 items in one call" in definition.description
    assert "at most 20 items in one call" in definition.args_prompt


def test_pydantic_tool_args_keep_legacy_dict_outputs_and_ignore_extra_fields():
    assert normalize_tool_args(
        "click",
        {
            "screen_index": "2",
            "position": ["100", 200],
            "unused": "ignored",
        },
    ) == {
        "screen_index": 2,
        "position": [100.0, 200.0],
    }

    assert normalize_tool_args(
        "input_text",
        {
            "screen_index": "0",
            "position": [10, 20],
            "text": "hello",
            "replace": "true",
            "submit": "false",
            "unused": "ignored",
        },
    ) == {
        "text": "hello",
        "replace": True,
        "submit": False,
        "screen_index": 0,
        "position": [10.0, 20.0],
    }


def test_pydantic_tool_args_reject_key_boundary_cases():
    with pytest.raises(ValueError, match="必须且只能提供 url 或 query"):
        normalize_tool_args("open_in_browser", {"url": "https://example.com", "query": "example"})

    with pytest.raises(ValueError, match="必须同时提供 screen_index 和 position"):
        normalize_tool_args("input_text", {"text": "hello", "screen_index": 0})

    with pytest.raises(ValueError, match="mode=chunk\\) 必须提供 chunk_index"):
        normalize_tool_args("read_current_page", {"mode": "chunk"})

    with pytest.raises(ValueError, match="单次最多创建 20 个条目"):
        normalize_tool_args(
            "manage_files",
            {
                "mode": "create",
                "items": [{"name": f"file-{idx}.txt"} for idx in range(21)],
            },
        )

    with pytest.raises(ValueError, match="duration_seconds 必须在 1-10 秒之间"):
        normalize_tool_args("long_press", {"screen_index": 0, "position": [500, 500], "duration_seconds": 11})


def test_open_in_browser_accepts_empty_args_to_launch_browser():
    assert normalize_tool_args("open_in_browser", {}) == {}


def test_long_press_tool_args_default_and_custom_duration():
    assert normalize_tool_args("long_press", {"screen_index": 0, "position": [500, 500]}) == {
        "screen_index": 0,
        "position": [500.0, 500.0],
        "duration_seconds": 3.0,
    }

    assert normalize_tool_args(
        "long_press",
        {"screen_index": "1", "position": [250, 750], "duration_seconds": "2.5"},
    ) == {
        "screen_index": 1,
        "position": [250.0, 750.0],
        "duration_seconds": 2.5,
    }


def test_pydantic_schema_is_available_without_changing_prompt_contract():
    schema = get_tool_json_schema("input_text")

    assert schema["title"] == "InputTextArgs"
    assert "properties" in schema


def test_long_press_json_schema_exposes_duration_seconds():
    schema = get_tool_json_schema("long_press")

    assert schema["title"] == "LongPressArgs"
    assert "duration_seconds" in schema["properties"]


def test_automation_public_import_compatibility_exports_remain_available():
    assert AutomationController is not None
    assert isinstance(DOCUMENT_EXTRACT_DIR, str)
    assert isinstance(MEMORY_FILE, str)
