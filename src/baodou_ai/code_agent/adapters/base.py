"""Code Agent CLI adapter 基类。"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set

from baodou_ai.code_agent.models import BackgroundJobResult, CodeAgentRequest
from baodou_ai.core.error_envelope import (
    CODE_CODE_AGENT_FAILED,
    KIND_CANCELLED,
    KIND_EXECUTION_FAILED,
    KIND_TIMEOUT,
    KIND_VALIDATION_FAILED,
    SOURCE_CODE_AGENT,
    from_message,
)


@dataclass(frozen=True)
class AdapterCallbacks:
    on_log: Callable[[str], None]
    on_pid: Callable[[int], None]


class CodeAgentAdapter(Protocol):
    provider_name: str

    def run(
        self,
        request: CodeAgentRequest,
        callbacks: AdapterCallbacks,
        should_stop: Callable[[], bool],
        provider_config: Optional[Dict[str, Any]] = None,
    ) -> BackgroundJobResult:
        ...


class BaseCLIAdapter:
    """基于 CLI 进程的通用 adapter。"""

    provider_name = "cli"
    default_command = ""
    default_args: List[str] = []
    _placeholder_only_pattern = re.compile(r"^\{[a-zA-Z_][a-zA-Z0-9_]*\}$")
    extra_path_dirs = (
        "~/.local/bin",
        "~/bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
    )

    def run(
        self,
        request: CodeAgentRequest,
        callbacks: AdapterCallbacks,
        should_stop: Callable[[], bool],
        provider_config: Optional[Dict[str, Any]] = None,
    ) -> BackgroundJobResult:
        provider_config = dict(provider_config or {})
        command = self._build_command(request, provider_config)
        process_env = self._build_env(provider_config)
        executable = self._resolve_executable(command[0], env=process_env)
        if not executable:
            envelope = from_message(
                source=SOURCE_CODE_AGENT,
                kind=KIND_VALIDATION_FAILED,
                user_message=f"{self.provider_name} CLI 不可用",
                dev_detail=f"未找到命令: {command[0]}",
                code=CODE_CODE_AGENT_FAILED,
                retryable=False,
            )
            return BackgroundJobResult(
                ok=False,
                summary=f"{self.provider_name} CLI 不可用",
                provider=self.provider_name,
                error=f"未找到命令: {command[0]}",
                error_envelope=envelope.to_dict(),
            )
        command[0] = executable

        callbacks.on_log(
            f"启动 {self.provider_name} 命令: {' '.join(shlex.quote(part) for part in command)}"
        )

        process = subprocess.Popen(
            command,
            cwd=request.workspace_path or None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=(os.name == "posix"),
            env=process_env,
        )
        callbacks.on_pid(int(process.pid))

        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        reader_threads = [
            self._start_reader_thread(process.stdout, stdout_lines, callbacks.on_log, stream_name="stdout"),
            self._start_reader_thread(process.stderr, stderr_lines, callbacks.on_log, stream_name="stderr"),
        ]

        start_at = time.time()
        timed_out = False
        cancelled = False

        while True:
            if should_stop():
                cancelled = True
                self._terminate_process(process)
                break

            timeout_seconds = max(int(request.timeout_seconds or 0), 0)
            if timeout_seconds and (time.time() - start_at) >= timeout_seconds:
                timed_out = True
                self._terminate_process(process)
                break

            return_code = process.poll()
            if return_code is not None:
                break
            time.sleep(0.1)

        for thread in reader_threads:
            thread.join(timeout=1.0)

        stdout_text = "".join(stdout_lines).strip()
        stderr_text = "".join(stderr_lines).strip()
        return_code = process.poll()

        if cancelled:
            envelope = from_message(
                source=SOURCE_CODE_AGENT,
                kind=KIND_CANCELLED,
                user_message=f"{self.provider_name} 任务已取消",
                dev_detail="cancelled",
                code=CODE_CODE_AGENT_FAILED,
                retryable=True,
            )
            return BackgroundJobResult(
                ok=False,
                summary=f"{self.provider_name} 任务已取消",
                provider=self.provider_name,
                final_output=stdout_text,
                raw_output=stdout_text,
                error="cancelled",
                error_envelope=envelope.to_dict(),
                exit_code=return_code,
                cancelled=True,
            )

        if timed_out:
            envelope = from_message(
                source=SOURCE_CODE_AGENT,
                kind=KIND_TIMEOUT,
                user_message=f"{self.provider_name} 任务执行超时",
                dev_detail=stderr_text or "timeout",
                code=CODE_CODE_AGENT_FAILED,
                retryable=True,
            )
            return BackgroundJobResult(
                ok=False,
                summary=f"{self.provider_name} 任务执行超时",
                provider=self.provider_name,
                final_output=stdout_text,
                raw_output=stdout_text,
                error=stderr_text or "timeout",
                error_envelope=envelope.to_dict(),
                exit_code=return_code,
                metadata={"timed_out": True},
            )

        return self._build_result(
            request=request,
            return_code=return_code or 0,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            provider_config=provider_config,
        )

    def _build_command(self, request: CodeAgentRequest, provider_config: Dict[str, Any]) -> List[str]:
        command = str(provider_config.get("command") or self.default_command).strip()
        if not command:
            raise ValueError(f"{self.provider_name} 缺少 command 配置")

        args_template = provider_config.get("args")
        if isinstance(args_template, list) and args_template:
            return [command] + self._render_args(args_template, request=request, provider_config=provider_config)

        return [command] + self._render_args(self.default_args, request=request, provider_config=provider_config)

    def _render_args(
        self,
        values: List[str],
        *,
        request: CodeAgentRequest,
        provider_config: Dict[str, Any],
    ) -> List[str]:
        rendered_args: List[str] = []
        for value in values:
            template = str(value)
            rendered = self._render_arg(template, request=request, provider_config=provider_config).strip()
            if not rendered:
                if (
                    rendered_args
                    and self._is_placeholder_only(template)
                    and rendered_args[-1].startswith("-")
                ):
                    rendered_args.pop()
                continue
            rendered_args.append(rendered)
        return rendered_args

    def _render_arg(
        self,
        value: str,
        *,
        request: CodeAgentRequest,
        provider_config: Dict[str, Any],
    ) -> str:
        replacements = {
            "task": request.task,
            "title": request.title,
            "workspace_path": request.workspace_path,
            "timeout_seconds": str(request.timeout_seconds),
            "model": str(provider_config.get("model") or ""),
            "permission_mode": str(provider_config.get("permission_mode") or ""),
            "reasoning_effort": str(provider_config.get("reasoning_effort") or ""),
        }
        rendered = value
        for key, replacement in replacements.items():
            rendered = rendered.replace("{" + key + "}", replacement)
        return rendered

    @classmethod
    def _is_placeholder_only(cls, value: str) -> bool:
        return bool(cls._placeholder_only_pattern.fullmatch(str(value or "").strip()))

    @classmethod
    def _build_env(cls, provider_config: Dict[str, Any]) -> Dict[str, str]:
        env = dict(os.environ)
        env["PATH"] = cls._augment_path(str(env.get("PATH") or ""))

        raw_env = provider_config.get("env")
        if isinstance(raw_env, dict):
            for key, value in raw_env.items():
                key_text = str(key or "").strip()
                if not key_text:
                    continue
                env[key_text] = str(value)
            env["PATH"] = cls._augment_path(str(env.get("PATH") or ""))
        return env

    @classmethod
    def _augment_path(cls, path_value: str) -> str:
        parts = [part for part in str(path_value or "").split(os.pathsep) if part]
        seen = set(parts)
        for raw_dir in cls.extra_path_dirs:
            resolved = str(Path(raw_dir).expanduser())
            if resolved in seen or not Path(resolved).exists():
                continue
            parts.append(resolved)
            seen.add(resolved)
        return os.pathsep.join(parts)

    @classmethod
    def _resolve_executable(cls, command: str, env: Optional[Dict[str, str]] = None) -> Optional[str]:
        if os.path.sep in command:
            path = Path(command).expanduser()
            return str(path) if path.exists() else None
        return shutil.which(command, path=(env or {}).get("PATH")) or shutil.which(command)

    @classmethod
    def _command_exists(cls, command: str) -> bool:
        return cls._resolve_executable(command) is not None

    @staticmethod
    def _start_reader_thread(stream, sink: List[str], on_log: Callable[[str], None], stream_name: str) -> threading.Thread:
        def _reader() -> None:
            if stream is None:
                return
            try:
                for raw_line in iter(stream.readline, ""):
                    sink.append(raw_line)
                    stripped = raw_line.rstrip()
                    if stripped:
                        on_log(f"[{stream_name}] {stripped}")
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_reader, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _terminate_process(process: subprocess.Popen) -> None:
        try:
            if process.poll() is not None:
                return
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=1.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _build_result(
        self,
        *,
        request: CodeAgentRequest,
        return_code: int,
        stdout_text: str,
        stderr_text: str,
        provider_config: Optional[Dict[str, Any]] = None,
    ) -> BackgroundJobResult:
        provider_config = dict(provider_config or {})
        parsed_output = self._extract_meaningful_output(stdout_text)
        success_exit_codes = self._normalize_success_exit_codes(provider_config.get("success_exit_codes"))
        if return_code in success_exit_codes:
            summary = self._pick_summary(parsed_output)
            if not summary:
                title = str(request.title or "").strip()
                summary = f"{title} 已完成" if title else f"{self.provider_name} 任务执行完成"
            return BackgroundJobResult(
                ok=True,
                summary=summary,
                provider=request.provider,
                final_output=parsed_output or stdout_text,
                raw_output=stdout_text,
                exit_code=return_code,
            )

        error_text = self._pick_summary(stderr_text) or self._pick_summary(parsed_output or stdout_text) or "process failed"
        envelope = from_message(
            source=SOURCE_CODE_AGENT,
            kind=KIND_EXECUTION_FAILED,
            user_message=f"{self.provider_name} 任务执行失败",
            dev_detail=error_text,
            code=CODE_CODE_AGENT_FAILED,
            retryable=True,
            extra={"exit_code": return_code},
        )
        return BackgroundJobResult(
            ok=False,
            summary=f"{self.provider_name} 任务执行失败",
            provider=request.provider,
            final_output=parsed_output or stdout_text,
            raw_output=stdout_text,
            error=error_text,
            error_envelope=envelope.to_dict(),
            exit_code=return_code,
        )

    def _extract_meaningful_output(self, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""

        extracted_lines: List[str] = []
        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                extracted_lines.append(line)
                continue
            text_value = self._extract_text_from_json(payload)
            if text_value:
                extracted_lines.append(text_value)

        if extracted_lines:
            deduped: List[str] = []
            seen = set()
            for line in extracted_lines:
                if line in seen:
                    continue
                seen.add(line)
                deduped.append(line)
            return "\n".join(deduped)
        return normalized

    def _extract_text_from_json(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, list):
            parts = [self._extract_text_from_json(item) for item in payload]
            return "\n".join(part for part in parts if part)
        if not isinstance(payload, dict):
            return ""

        for key in (
            "summary",
            "result",
            "response",
            "text",
            "content",
            "message",
            "output",
            "final_output",
            "final_message",
        ):
            value = payload.get(key)
            extracted = self._extract_text_from_json(value)
            if extracted:
                return extracted

        if "delta" in payload:
            return self._extract_text_from_json(payload.get("delta"))
        if "assistant" in payload:
            return self._extract_text_from_json(payload.get("assistant"))
        if "final" in payload:
            return self._extract_text_from_json(payload.get("final"))
        return ""

    @staticmethod
    def _normalize_success_exit_codes(value: Any) -> Set[int]:
        if value is None:
            return {0}
        if isinstance(value, int):
            return {value}
        if not isinstance(value, list):
            return {0}

        parsed: Set[int] = set()
        for item in value:
            try:
                parsed.add(int(item))
            except (TypeError, ValueError):
                continue
        return parsed or {0}

    @staticmethod
    def _pick_summary(text: str, limit: int = 160) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not lines:
            return ""
        summary = lines[-1]
        if len(summary) <= limit:
            return summary
        return summary[: limit - 3] + "..."
