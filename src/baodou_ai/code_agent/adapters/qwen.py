"""Qwen Code CLI adapter."""

from __future__ import annotations

from .base import BaseCLIAdapter


class QwenAdapter(BaseCLIAdapter):
    provider_name = "qwen"
    default_command = "qwen"
    default_args = [
        "-p",
        "{task}",
        "--output-format",
        "json",
        "--yolo",
    ]
