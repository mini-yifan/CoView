"""Code Agent provider 调度器。"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from baodou_ai.core.config import Config

from .adapters import (
    ClaudeCodeAdapter,
    CodeBuddyAdapter,
    CodexAdapter,
    KimiAdapter,
    QwenAdapter,
)
from .adapters.base import AdapterCallbacks, CodeAgentAdapter
from .models import BackgroundJobResult, CodeAgentRequest


class CodeAgentDispatcher:
    """根据配置选择并调用具体 provider adapter。"""

    def __init__(
        self,
        config: Optional[Config] = None,
        adapters: Optional[Dict[str, CodeAgentAdapter]] = None,
    ) -> None:
        self._config = config or Config()
        self._adapters: Dict[str, CodeAgentAdapter] = adapters or {
            "codex": CodexAdapter(),
            "claude": ClaudeCodeAdapter(),
            "kimi": KimiAdapter(),
            "qwen": QwenAdapter(),
            "codebuddy": CodeBuddyAdapter(),
        }

    def resolve_provider(self, provider: Optional[str] = None) -> str:
        configured = str(provider or self._config.code_agent_config.get("provider") or "codex").strip()
        if configured not in self._adapters:
            raise ValueError(f"不支持的 code agent provider: {configured}")
        return configured

    def run(
        self,
        request: CodeAgentRequest,
        on_log: Callable[[str], None],
        on_pid: Callable[[int], None],
        should_stop: Callable[[], bool],
    ) -> BackgroundJobResult:
        provider = self.resolve_provider(request.provider)
        adapter = self._adapters[provider]
        provider_config = self._get_provider_config(provider)
        callbacks = AdapterCallbacks(on_log=on_log, on_pid=on_pid)
        return adapter.run(
            request=request,
            callbacks=callbacks,
            should_stop=should_stop,
            provider_config=provider_config,
        )

    def _get_provider_config(self, provider: str) -> Dict[str, Any]:
        config = self._config.code_agent_config
        providers = config.get("providers", {})
        provider_config = providers.get(provider, {})
        if isinstance(provider_config, dict):
            return dict(provider_config)
        return {}
