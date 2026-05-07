"""Kimi Code CLI adapter."""

from __future__ import annotations

from .base import BaseCLIAdapter


class KimiAdapter(BaseCLIAdapter):
    provider_name = "kimi"
    default_command = "kimi"
    default_args = [
        "--quiet",
        "--work-dir",
        "{workspace_path}",
        "-p",
        "{task}",
    ]
