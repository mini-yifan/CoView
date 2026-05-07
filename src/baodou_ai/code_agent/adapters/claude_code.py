"""Claude Code CLI adapter。"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseCLIAdapter


class ClaudeCodeAdapter(BaseCLIAdapter):
    provider_name = "claude"
    default_command = "claude"
    default_args = [
        "-p",
        "{task}",
        "--output-format",
        "json",
        "--permission-mode",
        "{permission_mode}",
        "--model",
        "{model}",
    ]

    def _extract_meaningful_output(self, text: str) -> str:
        final_result = self.extract_final_result(text)
        if final_result:
            return final_result
        return super()._extract_meaningful_output(text)

    @classmethod
    def extract_final_result(cls, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""

        parsed = cls._try_parse_json(normalized)
        if parsed is not None:
            extracted = cls._extract_json_result(parsed)
            if extracted:
                return extracted

        return ""

    @classmethod
    def _extract_json_result(cls, payload: Any) -> str:
        if isinstance(payload, list):
            for item in reversed(payload):
                extracted = cls._extract_json_result(item)
                if extracted:
                    return extracted
            return ""

        if not isinstance(payload, dict):
            return ""

        for key in ("result", "content", "message", "text", "output"):
            extracted = cls._extract_text(payload.get(key))
            if extracted:
                return extracted
        return ""

    @classmethod
    def _extract_text(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts = [cls._extract_text(item) for item in value]
            return "\n".join(part for part in parts if part).strip()
        if isinstance(value, dict):
            for key in ("text", "content", "message", "result", "output"):
                extracted = cls._extract_text(value.get(key))
                if extracted:
                    return extracted
        return ""

    @staticmethod
    def _try_parse_json(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
