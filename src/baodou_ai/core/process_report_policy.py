from typing import Any, Dict, List, Tuple

from baodou_ai.core.stall_policy import StallPolicy


class ProcessReportPolicy:
    """process_report_mode 的提示构造与触发策略。"""

    def __init__(
        self,
        config: Any,
        stall_policy: StallPolicy,
        report_request_prompt: str,
        auto_skip_report_prompt: str,
        off_skip_report_prompt: str,
        loop_report_request_prompt: str,
    ) -> None:
        self._config = config
        self._stall_policy = stall_policy
        self._report_request_prompt = report_request_prompt
        self._auto_skip_report_prompt = auto_skip_report_prompt
        self._off_skip_report_prompt = off_skip_report_prompt
        self._loop_report_request_prompt = loop_report_request_prompt

    def normalize_report_mode(self) -> str:
        mode = str(self._config.execution_config.get("process_report_mode", "auto") or "auto").strip().lower()
        if mode not in {"auto", "every_step", "off"}:
            return "auto"
        return mode

    def get_report_interval_steps(self) -> int:
        try:
            interval = int(self._config.execution_config.get("process_report_interval_steps", 3))
        except (TypeError, ValueError):
            interval = 3
        return max(interval, 1)

    def build_process_report_request(
        self,
        report_mode: str,
        step_index: int,
        last_process_report_step: int,
        pending_required_report: bool,
        current_screen_hash: str,
        recent_effective_history: List[Dict[str, Any]],
    ) -> Tuple[str, bool, str, bool]:
        loop_report_requested = self._stall_policy.is_loop_report_required(
            current_screen_hash=current_screen_hash,
            recent_effective_history=recent_effective_history,
        )
        if loop_report_requested:
            return self._loop_report_request_prompt, True, "loop", True

        if report_mode == "every_step":
            return self._report_request_prompt, True, "mode", False

        if report_mode == "auto":
            if pending_required_report or step_index == 0:
                return self._report_request_prompt, True, "mode", False
            if (step_index - last_process_report_step) >= self.get_report_interval_steps():
                return self._report_request_prompt, True, "mode", False
            return self._auto_skip_report_prompt, False, "mode", False

        if report_mode == "off":
            return self._off_skip_report_prompt, False, "off", False

        return "", False, "", False

