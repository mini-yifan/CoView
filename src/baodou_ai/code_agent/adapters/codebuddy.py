"""CodeBuddy CLI adapter."""

from __future__ import annotations

import json
from typing import Any, List

from .base import BaseCLIAdapter


class CodeBuddyAdapter(BaseCLIAdapter):
    provider_name = "codebuddy"
    default_command = "codebuddy"
    default_args = [
        "-y",
        "-p",
        "{task}",
        "--output-format",
        "json",
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
            extracted = cls._extract_result_payload(parsed)
            if extracted:
                return extracted

        jsonl_items = cls._parse_json_lines(normalized)
        if jsonl_items:
            return cls._extract_result_payload(jsonl_items)

        return ""

    @classmethod
    def _extract_result_payload(cls, payload: Any) -> str:
        if isinstance(payload, list):
            for item in reversed(payload):
                extracted = cls._extract_result_payload(item)
                if extracted:
                    return extracted
            return ""

        if not isinstance(payload, dict):
            return ""

        if str(payload.get("type") or "").strip().lower() == "result":
            return cls._extract_text(payload.get("result"))

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

    @staticmethod
    def _parse_json_lines(text: str) -> List[Any]:
        items: List[Any] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items
