"""Unified structured error envelope for runtime failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


SOURCE_CAPTURE = "capture"
SOURCE_PARSER = "parser"
SOURCE_TOOL = "tool"
SOURCE_CODE_AGENT = "code_agent"
SOURCE_VOICE = "voice"
SOURCE_TTS = "tts"
SOURCE_RUNTIME = "runtime"

KIND_EXECUTION_FAILED = "execution_failed"
KIND_VALIDATION_FAILED = "validation_failed"
KIND_DEPENDENCY_MISSING = "dependency_missing"
KIND_BACKEND_FALLBACK = "backend_fallback"
KIND_TIMEOUT = "timeout"
KIND_CANCELLED = "cancelled"
KIND_PROTOCOL_PARSE_FAILED = "protocol_parse_failed"

CODE_CAPTURE_FAILED = "CAPTURE_FAILED"
CODE_PARSER_FAILED = "PARSER_FAILED"
CODE_TOOL_EXEC_FAILED = "TOOL_EXEC_FAILED"
CODE_CODE_AGENT_FAILED = "CODE_AGENT_FAILED"
CODE_VOICE_INIT_FAILED = "VOICE_INIT_FAILED"
CODE_VOICE_RUNTIME_FAILED = "VOICE_RUNTIME_FAILED"
CODE_TTS_INIT_FAILED = "TTS_INIT_FAILED"
CODE_TTS_PLAYBACK_FAILED = "TTS_PLAYBACK_FAILED"
CODE_MODEL_API_KEY_MISSING = "MODEL_API_KEY_MISSING"


@dataclass(frozen=True)
class ErrorEnvelope:
    source: str
    kind: str
    user_message: str
    dev_detail: str = ""
    retryable: bool = False
    code: str = ""
    exception_type: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "user_message": self.user_message,
            "dev_detail": self.dev_detail,
            "retryable": bool(self.retryable),
            "code": self.code,
            "exception_type": self.exception_type,
            "extra": dict(self.extra),
        }

    def to_tool_result(
        self,
        summary_fallback: str,
        *,
        ok: bool = False,
        error: Optional[str] = None,
        **extra_fields: Any,
    ) -> Dict[str, Any]:
        result = {
            "ok": bool(ok),
            "summary": str(summary_fallback or self.user_message or "执行失败"),
            "error": str(error if error is not None else (self.user_message or self.dev_detail or "执行失败")),
            "error_envelope": self.to_dict(),
        }
        result.update(extra_fields)
        return result

    def to_runtime_log_payload(self) -> Dict[str, Any]:
        payload = {
            "source": self.source,
            "kind": self.kind,
            "code": self.code,
            "retryable": bool(self.retryable),
            "user_message": self.user_message,
            "dev_detail": self.dev_detail,
            "exception_type": self.exception_type,
        }
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload


def from_exception(
    exc: BaseException,
    *,
    source: str,
    kind: str,
    user_message: str,
    code: str = "",
    retryable: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        source=source,
        kind=kind,
        user_message=str(user_message or "执行失败"),
        dev_detail=str(exc),
        retryable=bool(retryable),
        code=str(code or ""),
        exception_type=exc.__class__.__name__,
        extra=dict(extra or {}),
    )


def from_message(
    *,
    source: str,
    kind: str,
    user_message: str,
    dev_detail: str = "",
    code: str = "",
    retryable: bool = False,
    exception_type: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        source=source,
        kind=kind,
        user_message=str(user_message or "执行失败"),
        dev_detail=str(dev_detail or ""),
        retryable=bool(retryable),
        code=str(code or ""),
        exception_type=str(exception_type or ""),
        extra=dict(extra or {}),
    )
