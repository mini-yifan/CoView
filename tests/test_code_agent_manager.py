import json
import io
import os
import threading
import time
from types import SimpleNamespace

import pytest

from baodou_ai.code_agent.adapters.codebuddy import CodeBuddyAdapter
from baodou_ai.code_agent.adapters import base as base_adapter
from baodou_ai.code_agent.adapters.codex import CodexAdapter
from baodou_ai.code_agent.adapters.claude_code import ClaudeCodeAdapter
from baodou_ai.code_agent.adapters.kimi import KimiAdapter
from baodou_ai.code_agent.adapters.qwen import QwenAdapter
from baodou_ai.code_agent.dispatcher import CodeAgentDispatcher
from baodou_ai.code_agent.manager import JobManager
from baodou_ai.code_agent.models import BackgroundJobResult, CodeAgentRequest
from baodou_ai.code_agent.reporter import CodeAgentReportGenerator
from baodou_ai.core.config import Config


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")


class SequencedDispatcher:
    def __init__(self, release_events):
        self._release_events = list(release_events)
        self.calls = []

    def resolve_provider(self, provider=None):
        return provider or "codex"

    def run(self, request, on_log, on_pid, should_stop):
        call_index = len(self.calls)
        self.calls.append(
            {
                "job_id": request.job_id,
                "title": request.title,
                "task": request.task,
                "workspace_path": request.workspace_path,
            }
        )
        release_event = self._release_events[call_index]
        on_pid(1000 + call_index)
        on_log(f"start {request.job_id}")
        on_log(f"task {request.task}")
        while not release_event.wait(0.02):
            if should_stop():
                return BackgroundJobResult(
                    ok=False,
                    summary="任务已取消",
                    provider=request.provider,
                    cancelled=True,
                )
        return BackgroundJobResult(
            ok=True,
            summary=f"{request.title} 已完成",
            provider=request.provider,
            final_output=f"done::{request.job_id}::{request.task}",
        )


class FakeReporter:
    def build_report(self, payload):
        title = str(payload.get("title") or "").strip()
        workspace = str(payload.get("workspace_path") or "").strip()
        return {
            "result_summary": f"{title} 的代码结果已生成",
            "spoken_report": f"后台代码任务“{title}”已执行成功。结果：{title} 的代码结果已生成。执行目录：{workspace}。",
        }


class FailingDispatcher:
    def resolve_provider(self, provider=None):
        return provider or "codex"

    def run(self, request, on_log, on_pid, should_stop):
        del should_stop
        on_pid(9001)
        on_log(f"start {request.job_id}")
        return BackgroundJobResult(
            ok=False,
            summary="任务失败",
            provider=request.provider,
            error="bad output",
            error_envelope={
                "source": "code_agent",
                "kind": "execution_failed",
                "user_message": "后台代码任务执行失败",
                "code": "CODE_AGENT_FAILED",
                "retryable": True,
            },
        )


def test_job_manager_rejects_new_job_when_concurrency_limit_is_reached(tmp_path):
    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", str(tmp_path))
    config.set("code_agent_config.max_concurrent_jobs", 1)

    release_first = threading.Event()
    dispatcher = SequencedDispatcher([release_first])
    manager = JobManager(
        config=config,
        dispatcher=dispatcher,
        reporter=FakeReporter(),
        session_root=tmp_path / "sessions",
    )

    first = manager.submit(task="first task", title="任务一")
    _wait_until(lambda: manager.list_jobs()[0]["status"] == "running")

    with pytest.raises(ValueError, match="当前后台代码任务已满"):
        manager.submit(task="second task", title="任务二")

    assert [job["job_id"] for job in manager.list_jobs()] == [first["job_id"]]
    assert manager.list_jobs()[0]["status"] == "running"

    release_first.set()
    _wait_until(lambda: manager.list_jobs()[0]["status"] == "completed")


def test_job_manager_failed_report_contains_error_envelope(tmp_path):
    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", str(tmp_path))
    manager = JobManager(
        config=config,
        dispatcher=FailingDispatcher(),
        reporter=FakeReporter(),
        session_root=tmp_path / "sessions",
    )

    job = manager.submit(task="fail task", title="失败任务")
    _wait_until(lambda: manager.get_job(job["job_id"])["status"] == "failed")

    reports = manager.collect_pending_reports()
    assert reports
    assert reports[0]["status"] == "failed"
    assert reports[0]["error"] == "bad output"
    assert reports[0]["error_envelope"]["source"] == "code_agent"


def test_job_manager_defaults_workspace_root_to_desktop(tmp_path, monkeypatch):
    desktop_dir = tmp_path / "Desktop"
    desktop_dir.mkdir()

    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", "")
    dispatcher = SequencedDispatcher([threading.Event()])
    manager = JobManager(
        config=config,
        dispatcher=dispatcher,
        reporter=FakeReporter(),
        session_root=tmp_path / "sessions",
    )

    monkeypatch.setattr("baodou_ai.code_agent.manager.Path.home", lambda: tmp_path)

    job = manager.submit(task="desktop task", title="桌面任务")

    assert job["workspace_path"] == str(desktop_dir.resolve())
    manager.cancel(job["job_id"])
    _wait_until(lambda: manager.list_jobs()[0]["status"] == "cancelled")


def test_job_manager_reuses_job_id_for_completed_followup_and_persists_session_files(tmp_path):
    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", str(tmp_path))
    release_first = threading.Event()
    release_second = threading.Event()
    dispatcher = SequencedDispatcher([release_first, release_second])
    session_root = tmp_path / "sessions"
    manager = JobManager(
        config=config,
        dispatcher=dispatcher,
        reporter=FakeReporter(),
        session_root=session_root,
    )

    first = manager.submit(task="build app", title="构建应用", goal="生成基础版本")
    release_first.set()
    _wait_until(
        lambda: (
            manager.get_job(first["job_id"])["status"] == "completed"
            and manager.get_job(first["job_id"])["result_summary"] == "构建应用 的代码结果已生成"
        )
    )

    completed = manager.get_job(first["job_id"], include_logs=True)
    assert completed["run_id"] == f"{first['job_id']}-run-0001"
    assert completed["goal"] == "生成基础版本"
    assert completed["result_summary"] == "构建应用 的代码结果已生成"

    session_dir = session_root / first["job_id"]
    session_payload = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    card_payload = json.loads((session_dir / "card.json").read_text(encoding="utf-8"))
    run_payload = json.loads((session_dir / "runs" / f"{first['job_id']}-run-0001.json").read_text(encoding="utf-8"))
    run_log = (session_dir / "runs" / f"{first['job_id']}-run-0001.log").read_text(encoding="utf-8")

    assert session_payload["job_id"] == first["job_id"]
    assert session_payload["status"] == "completed"
    assert card_payload["job_id"] == first["job_id"]
    assert card_payload["status"] == "completed"
    assert run_payload["run_id"] == f"{first['job_id']}-run-0001"
    assert "start" in run_log

    followup = manager.submit(
        job_id=first["job_id"],
        task="polish app styles",
        title="优化应用",
        goal="在之前产物基础上继续优化样式",
    )
    _wait_until(lambda: manager.get_job(first["job_id"])["status"] == "running")

    assert followup["job_id"] == first["job_id"]
    running = manager.get_job(first["job_id"])
    assert running["run_id"] == f"{first['job_id']}-run-0002"
    assert running["goal"] == "在之前产物基础上继续优化样式"
    assert running["task"] == "polish app styles"
    assert running["instruction_history"] == ["build app", "polish app styles"]
    assert dispatcher.calls[1]["task"] == "polish app styles"

    release_second.set()
    _wait_until(
        lambda: (
            manager.get_job(first["job_id"])["status"] == "completed"
            and manager.get_job(first["job_id"])["result_summary"] == "优化应用 的代码结果已生成"
        )
    )

    reports = manager.collect_pending_reports()
    assert reports == [{
        "job_id": first["job_id"],
        "title": "优化应用",
        "provider": "codex",
        "status": "completed",
        "summary": "优化应用 已完成",
        "workspace_path": str(tmp_path.resolve()),
        "result_summary": "优化应用 的代码结果已生成",
        "spoken_report": f"后台代码任务“优化应用”已执行成功。结果：优化应用 的代码结果已生成。执行目录：{str(tmp_path.resolve())}。",
        "final_output": f"done::{first['job_id']}::polish app styles",
        "error": None,
        "created_at": reports[0]["created_at"],
    }]


def test_job_manager_restarts_running_job_with_same_job_id(tmp_path):
    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", str(tmp_path))
    release_first = threading.Event()
    release_second = threading.Event()
    dispatcher = SequencedDispatcher([release_first, release_second])
    manager = JobManager(
        config=config,
        dispatcher=dispatcher,
        reporter=FakeReporter(),
        session_root=tmp_path / "sessions",
    )

    first = manager.submit(task="initial task", title="任务一", goal="初始目标")
    _wait_until(lambda: manager.get_job(first["job_id"])["status"] == "running")

    followup = manager.submit(
        job_id=first["job_id"],
        task="updated task",
        title="任务一优化版",
        goal="更新后的目标",
    )
    _wait_until(lambda: len(dispatcher.calls) == 2)

    assert followup["job_id"] == first["job_id"]
    snapshot = manager.get_job(first["job_id"], include_logs=True)
    assert snapshot["status"] == "running"
    assert snapshot["run_id"] == f"{first['job_id']}-run-0002"
    assert snapshot["title"] == "任务一优化版"
    assert snapshot["goal"] == "更新后的目标"
    assert snapshot["task"] == "updated task"
    assert snapshot["instruction_history"] == ["initial task", "updated task"]
    assert [call["task"] for call in dispatcher.calls] == ["initial task", "updated task"]

    release_second.set()
    _wait_until(lambda: manager.get_job(first["job_id"])["status"] == "completed")


def test_job_manager_limits_memory_window_and_rejects_evicted_job_followup(tmp_path):
    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", str(tmp_path))
    config.set("code_agent_config.max_concurrent_jobs", 2)
    release_events = [threading.Event() for _ in range(4)]
    dispatcher = SequencedDispatcher(release_events)
    manager = JobManager(
        config=config,
        dispatcher=dispatcher,
        reporter=FakeReporter(),
        session_root=tmp_path / "sessions",
    )

    jobs = []
    for index, event in enumerate(release_events, start=1):
        job = manager.submit(task=f"task-{index}", title=f"任务{index}")
        jobs.append(job)
        event.set()
        _wait_until(lambda job_id=job["job_id"]: manager.get_job(job_id)["status"] == "completed")

    memory_jobs = manager.get_memory_jobs()
    assert len(memory_jobs) == 3
    assert [item["job_id"] for item in memory_jobs] == [jobs[3]["job_id"], jobs[2]["job_id"], jobs[1]["job_id"]]

    with pytest.raises(ValueError, match="已不在当前记忆窗口中"):
        manager.submit(job_id=jobs[0]["job_id"], task="continue task-1", title="继续任务1")


def test_job_manager_builds_memory_prompt_and_pending_reports_with_new_fields(tmp_path):
    config = Config.create_isolated()
    config.set("code_agent_config.workspace_root", str(tmp_path))
    release_event = threading.Event()
    dispatcher = SequencedDispatcher([release_event])
    manager = JobManager(
        config=config,
        dispatcher=dispatcher,
        reporter=FakeReporter(),
        session_root=tmp_path / "sessions",
    )

    job = manager.submit(task="build app", title="构建应用", goal="生成基础版本")
    running_prompt = manager.build_running_jobs_prompt()
    assert "job_id=" in running_prompt
    assert f"job_id={job['job_id']}" in running_prompt
    assert "goal=生成基础版本" in running_prompt
    assert "rewrite a complete fresh task yourself" in running_prompt

    release_event.set()
    _wait_until(lambda: manager.get_job(job["job_id"])["status"] == "completed")

    updated_prompt = manager.build_running_jobs_prompt()
    assert "result_summary=构建应用 的代码结果已生成" in updated_prompt

    pending_prompt = manager.build_pending_reports_prompt()
    assert job["job_id"] in pending_prompt
    assert "status=completed" in pending_prompt
    assert "后台代码任务“构建应用”已执行成功" in pending_prompt
    assert "Final output:" in pending_prompt
    assert f"done::{job['job_id']}::build app" in pending_prompt


def test_collect_workspace_artifacts_excludes_only_runtime_owned_memory_and_context_debug(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    runtime_context_dir = workspace / "imgs" / "context_debug"
    runtime_context_dir.mkdir(parents=True)
    other_context_dir = workspace / "demo_project" / "context_debug"
    other_context_dir.mkdir(parents=True)
    other_memory_dir = workspace / "demo_project"
    other_memory_dir.mkdir(parents=True, exist_ok=True)

    runtime_memory = workspace / "memory.txt"
    runtime_memory.write_text("runtime memory", encoding="utf-8")
    runtime_debug = runtime_context_dir / "round_001.json"
    runtime_debug.write_text("{}", encoding="utf-8")

    kept_index = workspace / "index.html"
    kept_index.write_text("<html></html>", encoding="utf-8")
    kept_other_memory = other_memory_dir / "memory.txt"
    kept_other_memory.write_text("project memory", encoding="utf-8")
    kept_other_context = other_context_dir / "log.json"
    kept_other_context.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "baodou_ai.code_agent.manager.resolve_memory_file",
        lambda: runtime_memory.resolve(),
    )
    monkeypatch.setattr(
        "baodou_ai.code_agent.manager.resolve_context_debug_dir",
        lambda: runtime_context_dir.resolve(),
    )

    artifacts = JobManager._collect_workspace_artifacts(str(workspace), limit=10)

    assert "memory.txt" not in artifacts
    assert "imgs/context_debug/round_001.json" not in artifacts
    assert "index.html" in artifacts
    assert "demo_project/memory.txt" in artifacts
    assert "demo_project/context_debug/log.json" in artifacts


def test_codex_adapter_extracts_final_agent_message_from_json_stream():
    adapter = CodexAdapter()
    raw_output = "\n".join([
        '{"type":"thread.started","thread_id":"t1"}',
        '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"过程提示"}}',
        '{"type":"item.completed","item":{"id":"item_1","type":"mcp_tool_call","result":{"content":[{"type":"text","text":"tool output"}]}}}',
        '{"type":"item.completed","item":{"id":"item_2","type":"agent_message","text":"**最终报告**\\n| 项目 | 结论 |\\n|---|---|\\n| claw-code | Rust CLI agent |"}}',
        '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":20}}',
    ])
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="codex",
        title="调研",
        task="research",
        workspace_path="/tmp",
        timeout_seconds=120,
    )

    result = adapter._build_result(
        request=request,
        return_code=0,
        stdout_text=raw_output,
        stderr_text="",
    )

    assert result.ok is True
    assert result.final_output == "**最终报告**\n| 项目 | 结论 |\n|---|---|\n| claw-code | Rust CLI agent |"
    assert result.raw_output == raw_output
    assert "turn.completed" not in result.final_output


def test_codex_adapter_default_command_uses_gpt54_high():
    adapter = CodexAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="codex",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp",
        timeout_seconds=120,
    )
    provider_config = {
        "model": "gpt-5.4",
        "reasoning_effort": "high",
    }

    command = adapter._build_command(request, provider_config)

    assert command == [
        "codex",
        "exec",
        "--json",
        "--full-auto",
        "--skip-git-repo-check",
        "-m",
        "gpt-5.4",
        "-c",
        'model_reasoning_effort="high"',
        "Fix the bug",
    ]


def test_codex_adapter_omits_model_flag_when_model_is_empty():
    adapter = CodexAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="codex",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp",
        timeout_seconds=120,
    )
    provider_config = {
        "model": "",
        "reasoning_effort": "high",
    }

    command = adapter._build_command(request, provider_config)

    assert command == [
        "codex",
        "exec",
        "--json",
        "--full-auto",
        "--skip-git-repo-check",
        "-c",
        'model_reasoning_effort="high"',
        "Fix the bug",
    ]


def test_codex_adapter_omits_reasoning_flag_when_reasoning_effort_is_empty():
    adapter = CodexAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="codex",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp",
        timeout_seconds=120,
    )
    provider_config = {
        "model": "gpt-5.4",
        "reasoning_effort": "",
    }

    command = adapter._build_command(request, provider_config)

    assert command == [
        "codex",
        "exec",
        "--json",
        "--full-auto",
        "--skip-git-repo-check",
        "-m",
        "gpt-5.4",
        "Fix the bug",
    ]


def test_dispatcher_registers_supported_cli_agent_providers():
    dispatcher = CodeAgentDispatcher(Config.create_isolated())

    for provider in ("codex", "claude", "kimi", "qwen", "codebuddy"):
        assert dispatcher.resolve_provider(provider) == provider


def test_claude_adapter_default_command_uses_json_permission_and_model():
    adapter = ClaudeCodeAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="claude",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp/project",
        timeout_seconds=120,
    )
    provider_config = {
        "model": "sonnet",
        "permission_mode": "bypassPermissions",
    }

    command = adapter._build_command(request, provider_config)

    assert command == [
        "claude",
        "-p",
        "Fix the bug",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
        "--model",
        "sonnet",
    ]


def test_claude_adapter_omits_model_flag_when_model_is_empty():
    adapter = ClaudeCodeAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="claude",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp/project",
        timeout_seconds=120,
    )
    provider_config = {
        "model": "",
        "permission_mode": "bypassPermissions",
    }

    command = adapter._build_command(request, provider_config)

    assert command == [
        "claude",
        "-p",
        "Fix the bug",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]


def test_new_cli_agent_adapters_build_default_commands():
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="kimi",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp/project",
        timeout_seconds=120,
    )

    assert KimiAdapter()._build_command(request, {}) == [
        "kimi",
        "--quiet",
        "--work-dir",
        "/tmp/project",
        "-p",
        "Fix the bug",
    ]
    assert QwenAdapter()._build_command(request, {}) == [
        "qwen",
        "-p",
        "Fix the bug",
        "--output-format",
        "json",
        "--yolo",
    ]
    assert CodeBuddyAdapter()._build_command(request, {}) == [
        "codebuddy",
        "-y",
        "-p",
        "Fix the bug",
        "--output-format",
        "json",
    ]


def test_cli_adapter_resolves_commands_from_common_user_bin_dirs(tmp_path, monkeypatch):
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    executable = bin_dir / "kimi"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/bin"]))

    env = KimiAdapter._build_env({})

    assert str(bin_dir) in env["PATH"].split(os.pathsep)
    assert KimiAdapter._resolve_executable("kimi", env=env) == str(executable)


def test_cli_adapter_hides_windows_subprocess_window(monkeypatch):
    adapter = KimiAdapter()
    popen_calls = []

    class FakeStartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    class FakeProcess:
        pid = 1234

        def __init__(self):
            self.stdout = io.StringIO('{"response":"done"}\n')
            self.stderr = io.StringIO("")

        def poll(self):
            return 0

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(base_adapter.os, "name", "nt")
    monkeypatch.setattr(base_adapter.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(base_adapter.subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr(base_adapter.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(base_adapter.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(KimiAdapter, "_build_env", classmethod(lambda cls, provider_config: {}))
    monkeypatch.setattr(
        KimiAdapter,
        "_resolve_executable",
        classmethod(lambda cls, command, env=None: "kimi.exe"),
    )
    monkeypatch.setattr(base_adapter.subprocess, "Popen", fake_popen)

    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="kimi",
        title="fix",
        task="Fix the bug",
        workspace_path="",
        timeout_seconds=120,
    )

    result = adapter.run(
        request,
        callbacks=SimpleNamespace(on_log=lambda message: None, on_pid=lambda pid: None),
        should_stop=lambda: False,
        provider_config={},
    )

    assert result.ok is True
    assert popen_calls[0][1]["creationflags"] == 0x08000000
    assert popen_calls[0][1]["startupinfo"].dwFlags & 1
    assert popen_calls[0][1]["startupinfo"].wShowWindow == 0


def test_cli_adapter_does_not_add_hidden_subprocess_kwargs_on_non_windows(monkeypatch):
    monkeypatch.setattr(base_adapter.os, "name", "posix")

    assert KimiAdapter._hidden_subprocess_kwargs() == {}


def test_claude_adapter_extracts_result_from_json_output():
    adapter = ClaudeCodeAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="claude",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp/project",
        timeout_seconds=120,
    )

    result = adapter._build_result(
        request=request,
        return_code=0,
        stdout_text=json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "result": "Claude 最终结果\n- 修改完成",
                "session_id": "abc",
                "usage": {"input_tokens": 10},
            },
            ensure_ascii=False,
        ),
        stderr_text="",
    )

    assert result.ok is True
    assert result.final_output == "Claude 最终结果\n- 修改完成"
    assert "usage" not in result.final_output


def test_base_cli_adapter_extracts_response_key_from_json_output():
    adapter = QwenAdapter()
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="qwen",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp/project",
        timeout_seconds=120,
    )

    result = adapter._build_result(
        request=request,
        return_code=0,
        stdout_text='{"response":"修改已完成"}',
        stderr_text="",
    )

    assert result.ok is True
    assert result.final_output == "修改已完成"
    assert result.summary == "修改已完成"


def test_codebuddy_adapter_extracts_result_event_from_json_array():
    adapter = CodeBuddyAdapter()
    raw_output = json.dumps(
        [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "system prompt and user task"}],
            },
            {
                "type": "reasoning",
                "content": "分析过程不应该展示在最终结果里",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "中间回复"}],
            },
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "最终可读结果\n- 文件已生成\n- 测试已通过",
            },
        ],
        ensure_ascii=False,
        indent=2,
    )
    request = CodeAgentRequest(
        job_id="code-job-0001",
        provider="codebuddy",
        title="修复问题",
        task="Fix the bug",
        workspace_path="/tmp/project",
        timeout_seconds=120,
    )

    result = adapter._build_result(
        request=request,
        return_code=0,
        stdout_text=raw_output,
        stderr_text="",
    )

    assert result.ok is True
    assert result.final_output == "最终可读结果\n- 文件已生成\n- 测试已通过"
    assert "system prompt" not in result.final_output
    assert "分析过程" not in result.final_output


def test_reporter_prompt_requires_concise_spoken_report():
    reporter = CodeAgentReportGenerator(Config.create_isolated())

    messages = reporter._build_messages(
        {
            "title": "调研任务",
            "task": "整理结果",
            "status": "completed",
            "workspace_path": "/tmp/workspace",
            "summary": "已完成",
            "final_output": "最终结果",
            "logs": [],
        }
    )

    system_prompt = messages[0]["content"]
    assert "within 100 Chinese characters" in system_prompt
    assert "within 300 Chinese characters" in system_prompt


def test_fallback_report_preserves_content_without_hard_clipping():
    reporter = CodeAgentReportGenerator(Config.create_isolated())
    long_summary = "结果" * 300

    report = reporter._build_fallback_report(
        {
            "title": "长结果任务",
            "status": "completed",
            "workspace_path": "/tmp/workspace",
            "summary": long_summary,
        }
    )

    assert report["result_summary"] == long_summary
    assert long_summary in report["spoken_report"]
    assert "..." not in report["spoken_report"]


def test_reporter_build_report_respects_tls_verify(monkeypatch, tmp_path):
    config = Config.create_isolated(str(tmp_path / "config.json"))
    config.set("api_config.api_key", "test-key")
    config.set("api_config.base_url", "https://example.test/v1")
    config.set("api_config.tls_verify", False)
    reporter = CodeAgentReportGenerator(config)
    captured = {}

    class FakeHttpxClient:
        def __init__(self, *, verify):
            captured["verify"] = verify

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, http_client):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            captured["http_client"] = http_client
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
                )
            )

        def close(self):
            return None

    monkeypatch.setattr("baodou_ai.code_agent.reporter.httpx.Client", FakeHttpxClient)
    monkeypatch.setattr("baodou_ai.code_agent.reporter.OpenAI", FakeOpenAI)

    reporter.build_report({"status": "completed", "summary": "ok"})

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["verify"] is False
