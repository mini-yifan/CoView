"""Lightweight recommender for companion suggestions (no tool calls, no memory)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from openai import OpenAI

from baodou_ai.core.config import Config


class CompanionRecommender:
    """Calls the vision model to produce exactly two short actionable suggestions."""

    def __init__(self, config: Optional[Config] = None):
        self._config = config or Config()
        self._client: Optional[OpenAI] = None
        self._client_signature: Optional[tuple[str, str, bool, float]] = None

    def _get_client(self) -> Optional[OpenAI]:
        api_config = self._config.api_config
        api_key = str(api_config.get("api_key") or "").strip()
        base_url = str(api_config.get("base_url") or "").strip()
        if not api_key or not base_url:
            return None

        tls_verify = bool(api_config.get("tls_verify", True))
        timeout_seconds = max(
            5.0,
            float((getattr(self._config, "companion_config", {}) or {}).get("request_timeout_seconds", 20) or 20),
        )
        signature = (api_key, base_url, tls_verify, timeout_seconds)
        if self._client is not None and self._client_signature == signature:
            return self._client

        self.close()
        import httpx

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(
                verify=tls_verify,
                timeout=httpx.Timeout(timeout_seconds),
            ),
        )
        self._client_signature = signature
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self._client_signature = None

    def _is_volcengine_like_base_url(self) -> bool:
        base_url = str(self._config.api_config.get("base_url", "") or "").strip().lower()
        if not base_url:
            return False
        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        hostname = (parsed.hostname or "").lower()
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in ("volces.com", "volcengine.com", "volcengineapi.com")
        )

    def _build_extra_body(self) -> Dict[str, Any]:
        """
        为伴随 AI 构造额外参数。

        当 companion_config.disable_thinking=true 时，显式下发 thinking=disabled，
        以严格停用深度思考，而不是仅仅“未配置思考参数”。
        """
        companion_config = getattr(self._config, "companion_config", {}) or {}
        disable_thinking = bool(companion_config.get("disable_thinking", True))
        if disable_thinking:
            extra_body: Dict[str, Any] = {"thinking": {"type": "disabled"}}
            # 对火山兼容接口，显式给最弱推理强度，避免沿用其他默认值。
            if self._is_volcengine_like_base_url():
                extra_body["reasoning_effort"] = "minimal"
            return extra_body
        return {}

    def get_recommendations(self, image_data_url: str, context_text: str = "") -> List[str]:
        client = self._get_client()
        if client is None:
            return []

        model = str(self._config.api_config.get("model_name", "") or "").strip()
        if not model:
            return []

        system_prompt = (
            "You are a companion suggestion generator for a desktop AI agent.\n"
            "Your job is not to operate the computer and not to explain. "
            "Your only job is to look at the user's current frontmost window and produce exactly TWO short, high-value task suggestions that the main agent can likely carry out after the user clicks one.\n"
            "\n"
            "## What the main agent is good at\n"
            "- navigate apps, webpages, and local folders\n"
            "- click, type, scroll, use hotkeys, and complete moderate multi-step GUI workflows\n"
            "- read the main content of the current browser page\n"
            "- read the main content of the current document or editor in many common apps\n"
            "- search, organize, rename, move, create, and delete files when file-manager context is available\n"
            "- delegate artifact-producing work to a background code agent, such as drafting documents, reports, spreadsheets, code, scripts, or other reusable deliverables\n"
            "\n"
            "## What kinds of suggestions to prefer\n"
            "- save multiple manual steps\n"
            "- are clearly useful in the current screen context\n"
            "- can be clicked and directly used as a task for the main agent\n"
            "- are specific enough to act on, but still short and natural\n"
            "- fit one of these patterns when relevant: summarize, extract key information, compare, organize, find or locate something, draft a reply, identify an issue, continue with a practical next step, or create or revise a reusable deliverable through a background agent\n"
            "\n"
            "## What kinds of suggestions to avoid\n"
            "- trivial one-click actions the user can do faster themselves\n"
            "- vague, generic, or chatty suggestions\n"
            "- tasks that depend on heavy human judgment with no clear actionable outcome\n"
            "- suggestions that sound like internal tool instructions\n"
            "- exposing tool names, parameter ideas, or implementation details\n"
            "- mainly suggesting closing, minimizing, or hiding windows\n"
            "- unrealistic assumptions beyond the visible context\n"
            "\n"
            "## Style rules\n"
            "- Output JSON only.\n"
            '- Schema: {"recommendations": ["...", "..."]}\n'
            "- Always output exactly two recommendations.\n"
            "- Each recommendation must be a short task command (<= 16 Chinese chars if Chinese, <= 10 words if English).\n"
            "- Make them feel natural and clickable.\n"
            "- Do NOT include explanations, numbering, markdown, or extra keys.\n"
            "\n"
            "## Decision rule\n"
            '- Think: "What are the two most useful things the main agent could plausibly help with here?"\n'
            '- Do not think: "What tools exist?" or "What is theoretically possible?"\n'
            "- Prefer practical, high-yield, handoff-ready tasks.\n"
        )
        user_text = (context_text or "").strip() or "Generate two recommendations."
        extra_body = self._build_extra_body()

        try:
            request_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    },
                ],
                "temperature": 0.4,
            }
            if extra_body:
                request_kwargs["extra_body"] = extra_body
            resp = client.chat.completions.create(**request_kwargs)
            content = ""
            try:
                content = str(resp.choices[0].message.content or "").strip()
            except Exception:
                content = ""
            return self._parse_recommendations(content)
        except Exception:
            return []
        finally:
            # Avoid leaking connections across many small calls.
            self.close()

    @staticmethod
    def _parse_recommendations(raw: str) -> List[str]:
        text = str(raw or "").strip()
        if not text:
            return []

        # Fast path: JSON object.
        try:
            data = json.loads(text)
            recs = data.get("recommendations") if isinstance(data, dict) else None
            if isinstance(recs, list):
                cleaned = [str(x or "").strip() for x in recs if str(x or "").strip()]
                return cleaned[:2] if len(cleaned) >= 2 else []
        except Exception:
            pass

        # Fallback: attempt to extract a JSON object substring.
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            try:
                data = json.loads(text[start : end + 1])
                recs = data.get("recommendations") if isinstance(data, dict) else None
                if isinstance(recs, list):
                    cleaned = [str(x or "").strip() for x in recs if str(x or "").strip()]
                    return cleaned[:2] if len(cleaned) >= 2 else []
            except Exception:
                pass

        # Last resort: split lines and take first two non-empty lines.
        lines = [ln.strip(" \t-•0123456789.，、") for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]
        return lines[:2] if len(lines) >= 2 else []
