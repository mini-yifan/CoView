import cv2
import numpy as np

from baodou_ai.core.config import Config
from baodou_ai.core.runner import ControlLoopRunner
from baodou_ai.core.screenshot import ScreenCaptureBundle


def make_bundle(index: int = 0, value: int = 0) -> ScreenCaptureBundle:
    image = np.full((8, 8, 3), value, dtype=np.uint8)
    success, buffer = cv2.imencode(".png", image)
    assert success
    png_bytes = buffer.tobytes()
    return ScreenCaptureBundle(
        index=index,
        x=0,
        y=0,
        width=1920,
        height=1080,
        logical_width=1920,
        logical_height=1080,
        is_primary=True,
        png_bytes=png_bytes,
        data_url="data:image/png;base64,test",
        frame_hash=f"frame-{index}-{value}",
        path=None,
    )


class FakeScreenshot:
    def __init__(self, bundle_groups):
        self.bundle_groups = list(bundle_groups)
        self.index = 0

    def capture_all_screens_bundle(self):
        current_index = min(self.index, len(self.bundle_groups) - 1)
        self.index += 1
        return True, self.bundle_groups[current_index]

    @staticmethod
    def calculate_image_difference(previous_gray, current_gray):
        diff = np.abs(previous_gray.astype(np.float32) - current_gray.astype(np.float32))
        return float(diff.mean() / 255.0)


class FakeAIClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def clear_memory(self):
        return None

    def get_next_action_from_capture(self, captures, user_content, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0), {
            "encode_ms": 1.0,
            "request_prepare_ms": 1.0,
            "model_latency_ms": 1.0,
        }


class FakeAutomation:
    def __init__(self):
        self.executed = []
        self.stopped = []
        self._last_settle_result = None

    def set_window_callbacks(self, hide_callback, show_callback):
        return None

    def auto_release_stale_modifier_keys(self, current_step, max_steps, max_seconds):
        return None

    def get_held_modifier_keys(self):
        return []

    def get_frontmost_app_info(self):
        return {}

    def release_all_held_modifier_keys(self):
        return []

    def get_last_settle_result(self):
        return self._last_settle_result

    def tool_code_agent(
        self,
        task,
        title=None,
        goal=None,
        job_id=None,
        workspace_path=None,
        timeout_seconds=None,
        screen_info=None,
        should_stop=None,
    ):
        self.executed.append({
            "task": task,
            "title": title,
            "goal": goal,
            "job_id": job_id,
            "workspace_path": workspace_path,
            "timeout_seconds": timeout_seconds,
        })
        return {
            "ok": True,
            "summary": "后台代码任务已启动（code-job-0001）",
            "error": None,
            "launch_report": "我已经在后台启动代码任务，你可以继续使用电脑。我完成后会向你汇报结果。",
            "job_id": "code-job-0001",
            "job_status": "running",
            "provider": "codex",
        }

    def tool_stop_code_agent(
        self,
        job_id,
        screen_info=None,
        should_stop=None,
    ):
        self.stopped.append({
            "job_id": job_id,
        })
        return {
            "ok": True,
            "summary": "后台代码任务已停止（code-job-0001）",
            "error": None,
            "stop_report": "后台代码任务“计算器页面”已停止。",
            "job_id": job_id,
            "job_status": "cancelled",
            "provider": "codex",
        }


def test_runner_returns_immediately_after_code_agent_launch(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    config = Config.create_isolated()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._tool_executor._automation = runner._automation
    runner._ai_client = FakeAIClient([{
        "thinking": "这是一个较长的代码任务，应当放到后台执行。",
        "report": "我先把代码任务放到后台。",
        "code_agent": {
            "task": "Fix failing tests in the current repo",
            "workspace_path": str(workspace),
        },
    }])

    result = runner.run("task", max_iterations=3)

    assert result == "我已经在后台启动代码任务，你可以继续使用电脑。我完成后会向你汇报结果。"
    assert runner._automation.executed == [{
        "task": "Fix failing tests in the current repo",
        "title": None,
        "goal": None,
        "job_id": None,
        "workspace_path": str(workspace),
        "timeout_seconds": None,
    }]
    assert len(runner._ai_client.calls) == 1


def test_runner_treats_stop_code_agent_as_regular_tool():
    config = Config.create_isolated()
    runner = ControlLoopRunner(config)
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._tool_executor._automation = runner._automation
    runner._ai_client = FakeAIClient([
        {
            "thinking": "用户要求停止后台代码任务。",
            "report": "我先停止这个后台代码任务。",
            "stop_code_agent": {
                "job_id": "code-job-0001",
            },
        },
        {
            "thinking": "后台代码任务已经停止，现在向用户汇报。",
            "respond": {
                "outcome": "completed",
                "report": "之前的后台代码任务已经停止。",
            },
        },
    ])

    result = runner.run("task", max_iterations=4)

    assert result == "之前的后台代码任务已经停止。"
    assert runner._automation.stopped == [{
        "job_id": "code-job-0001",
    }]
    assert len(runner._ai_client.calls) == 2


def test_runner_injects_background_job_prompts_into_model_context():
    class FakeJobManager:
        def build_running_jobs_prompt(self):
            return "running prompt"

        def build_pending_reports_prompt(self):
            return "pending prompt"

    config = Config.create_isolated()
    runner = ControlLoopRunner(config, job_manager=FakeJobManager())
    runner._clear_memory_files = lambda: None
    runner._read_memory_content = lambda: ""
    runner._screenshot = FakeScreenshot([[make_bundle()]])
    runner._automation = FakeAutomation()
    runner._tool_executor._automation = runner._automation
    runner._ai_client = FakeAIClient([{
        "thinking": "当前可以直接汇报。",
        "respond": {
            "outcome": "completed",
            "report": "任务完成",
        },
    }])

    result = runner.run("task", max_iterations=1)

    assert result == "任务完成"
    assert runner._ai_client.calls[0]["background_jobs_prompt"] == "running prompt"
    assert runner._ai_client.calls[0]["pending_reports_prompt"] == "pending prompt"
