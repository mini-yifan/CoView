"""Codex CLI adapter。"""

from __future__ import annotations

import json
from typing import Any, List

from .base import BaseCLIAdapter


class CodexAdapter(BaseCLIAdapter):
    provider_name = "codex"
    default_command = "codex"
    default_args = [
        "exec",
        "--json",
        "--full-auto",
        "--skip-git-repo-check",
        "-m",
        "{model}",
        "-c",
        'model_reasoning_effort="{reasoning_effort}"',
        "{task}",
    ]

    def _build_command(self, request, provider_config):
        command = super()._build_command(request, provider_config)
        reasoning_effort = str((provider_config or {}).get("reasoning_effort") or "").strip()
        if reasoning_effort:
            return command

        cleaned_command: List[str] = []
        skip_next = False
        for index, part in enumerate(command):
            if skip_next:
                skip_next = False
                continue
            if (
                index + 1 < len(command)
                and part == "-c"
                and command[index + 1].startswith("model_reasoning_effort=")
            ):
                skip_next = True
                continue
            cleaned_command.append(part)
        return cleaned_command

    def _extract_meaningful_output(self, text: str) -> str:
        final_message = self._extract_last_agent_message(text)
        if final_message:
            return final_message
        return super()._extract_meaningful_output(text)

    def _extract_last_agent_message(self, text: str) -> str:
        messages: List[str] = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = self._extract_agent_message_text(payload)
            if message:
                messages.append(message)
        return messages[-1] if messages else ""

    @staticmethod
    def _extract_agent_message_text(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        if payload.get("type") != "item.completed":
            return ""
        item = payload.get("item")
        if not isinstance(item, dict):
            return ""
        if item.get("type") != "agent_message":
            return ""
        return str(item.get("text") or "").strip()
