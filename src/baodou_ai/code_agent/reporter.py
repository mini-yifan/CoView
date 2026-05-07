"""后台 Code Agent 完成汇报生成器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from baodou_ai.core.config import Config


class CodeAgentReportPayload(BaseModel):
    success: bool
    task_result_summary: str
    spoken_report: str


class CodeAgentReportGenerator:
    """使用与 baodou_ai 相同配置的模型生成后台任务汇报。"""

    _MAX_FINAL_OUTPUT_CHARS = 12000
    _MAX_LOG_LINES = 120
    _MAX_LOG_CHARS = 8000

    def __init__(self, config: Optional[Config] = None) -> None:
        self._config = config or Config()

    def build_report(self, payload: Dict[str, Any]) -> Dict[str, str]:
        fallback = self._build_fallback_report(payload)

        api_key = str(self._config.api_config.get("api_key", "") or "").strip()
        if not api_key:
            return fallback

        try:
            tls_verify = bool(self._config.api_config.get("tls_verify", True))
            client = OpenAI(
                api_key=api_key,
                base_url=self._config.api_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                http_client=httpx.Client(verify=tls_verify),
            )
        except Exception:
            return fallback

        try:
            completion = client.chat.completions.create(
                model=self._config.api_config.get("model_name", "qwen3.6-35b-a3b"),
                messages=self._build_messages(payload),
                extra_body=self._build_extra_body(),
            )
            content = completion.choices[0].message.content
            parsed = self._parse_payload(content)
            if parsed is None:
                return fallback
            return {
                "result_summary": parsed.task_result_summary.strip() or fallback["result_summary"],
                "spoken_report": parsed.spoken_report.strip() or fallback["spoken_report"],
            }
        except Exception:
            return fallback
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _build_messages(self, payload: Dict[str, Any]) -> List[Dict[str, str]]:
        respond_language = self._config.get_respond_language()
        title = str(payload.get("title") or "后台代码任务").strip()
        task = str(payload.get("task") or "").strip()
        status = str(payload.get("status") or "").strip()
        workspace_path = str(payload.get("workspace_path") or "").strip()
        summary = str(payload.get("summary") or "").strip()
        error = str(payload.get("error") or "").strip()
        final_output = self._clip_text(str(payload.get("final_output") or "").strip(), self._MAX_FINAL_OUTPUT_CHARS)
        logs = self._clip_text(
            "\n".join(str(line) for line in (payload.get("logs") or [])[-self._MAX_LOG_LINES:]),
            self._MAX_LOG_CHARS,
        )

        system_prompt = (
            "You summarize completed background code-agent tasks for the end user.\n"
            f"All output must be in {respond_language}.\n"
            "Return JSON only with keys: success, task_result_summary, spoken_report.\n"
            "Requirements:\n"
            "- spoken_report must include exactly these three ideas: whether the task succeeded, a brief result summary, and the workspace folder path.\n"
            "- Do not mention provider names, job ids, token usage, raw logs, JSON event names, or implementation internals.\n"
            "- Do not invent files or results that are not supported by the input.\n"
            "- task_result_summary should be one short sentence, preferably within 100 Chinese characters or equivalent.\n"
            "- spoken_report should be concise and natural for direct voice broadcast, preferably within 300 Chinese characters or equivalent.\n"
        )

        user_prompt = (
            "[Task Title]\n"
            f"{title}\n\n"
            "[Original Task]\n"
            f"{task or '(empty)'}\n\n"
            "[Execution Status]\n"
            f"{status}\n\n"
            "[Workspace Path]\n"
            f"{workspace_path or '(empty)'}\n\n"
            "[Adapter Summary]\n"
            f"{summary or '(empty)'}\n\n"
            "[Error]\n"
            f"{error or '(empty)'}\n\n"
            "[Final Output]\n"
            f"{final_output or '(empty)'}\n\n"
            "[Recent Logs]\n"
            f"{logs or '(empty)'}"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_extra_body(self) -> Dict[str, Any]:
        extra_body: Dict[str, Any] = {
            "thinking": {
                "type": self._config.ai_config.get("thinking_type", "disabled"),
            }
        }
        reasoning_effort = self._config.ai_config.get("reasoning_effort", "minimal")
        if reasoning_effort and self._is_volcengine_base_url():
            extra_body["reasoning_effort"] = reasoning_effort
        return extra_body

    def _is_volcengine_base_url(self) -> bool:
        base_url = (self._config.api_config.get("base_url", "") or "").strip().lower()
        return any(domain in base_url for domain in ("volces.com", "volcengine.com", "volcengineapi.com"))

    def _parse_payload(self, content: Any) -> Optional[CodeAgentReportPayload]:
        normalized = str(content or "").strip()
        if not normalized:
            return None

        candidates = [normalized]
        if normalized.startswith("```"):
            stripped = normalized.strip("`")
            if "\n" in stripped:
                candidates.append(stripped.split("\n", 1)[1].strip())

        for candidate in candidates:
            payload = self._try_parse_json(candidate)
            if payload is None:
                continue
            try:
                return CodeAgentReportPayload.model_validate(payload)
            except ValidationError:
                continue
        return None

    @staticmethod
    def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def _build_fallback_report(self, payload: Dict[str, Any]) -> Dict[str, str]:
        title = str(payload.get("title") or "后台代码任务").strip()
        workspace_path = str(payload.get("workspace_path") or "").strip()
        status = str(payload.get("status") or "").strip()
        result_summary = (
            str(payload.get("summary") or "").strip()
            or str(payload.get("error") or "").strip()
            or ("任务已完成" if status == "completed" else "任务执行失败")
        )
        workspace_clause = workspace_path or str(Path.home() / "Desktop")

        if status == "completed":
            spoken_report = (
                f"后台代码任务“{title}”已执行成功。结果：{result_summary}。执行目录：{workspace_clause}。"
            )
        else:
            spoken_report = (
                f"后台代码任务“{title}”执行失败。结果：{result_summary}。执行目录：{workspace_clause}。"
            )

        return {
            "result_summary": result_summary,
            "spoken_report": spoken_report,
        }

    @staticmethod
    def _clip_text(text: str, limit: int) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= limit:
            return normalized
        if limit <= 3:
            return normalized[:limit]
        return normalized[: limit - 3] + "..."
