"""Lightweight LLM classifier for voice barge-in intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from baodou_ai.core.config import Config


VALID_INTENTS = {"stop", "new_task", "ignore"}


@dataclass(frozen=True)
class VoiceIntentContext:
    transcript: str
    agent_status: str = ""
    current_task: str = ""
    tts_playing: bool = False
    tts_text: str = ""
    interaction_phase: str = ""


class VoiceIntentClassifier:
    """Classify a transcript into stop, new_task, or ignore without touching agent memory."""

    def __init__(self, config: Config, client_factory=None) -> None:
        self._config = config
        self._client_factory = client_factory

    def classify(self, context: VoiceIntentContext) -> str:
        transcript = str(context.transcript or "").strip()
        if not transcript:
            return "ignore"

        try:
            raw = self._request_model(context)
        except Exception as exc:
            print(f"[VOICE] 意图分类失败: {exc}")
            return "ignore"
        return self._parse_intent(raw)

    def _request_model(self, context: VoiceIntentContext) -> str:
        client = self._build_client()
        voice_config = self._config.voice_interaction_config
        model = str(voice_config.get("intent_model_name") or "").strip()
        if not model:
            model = str(self._config.api_config.get("model_name", "") or "").strip()

        completion = client.chat.completions.create(
            model=model,
            temperature=0,
            extra_body={
                "thinking": {
                    "type": "disabled",
                },
            },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify voice barge-in text for a desktop AI agent. "
                        "Return exactly one token from this set: stop, new_task, ignore. "
                        "Be conservative: when uncertain, choose ignore. "
                        "stop means the user only wants the current action or speech to stop, cancel, mute, or not continue, and does not give a replacement request. "
                        "new_task is strict: choose it only when the transcript contains a clear actionable command with an explicit task intent (verb + object/goal), such as opening an app, searching a topic, sending a message, or checking specific information. "
                        "Short, vague, emotional, social, or ambiguous utterances should be ignore, not new_task. "
                        "ignore includes unrelated speech, self-talk, background speech, filler words, acknowledgements, thanks, casual comments, and uncertain intent. "
                        "If interaction_phase is final_response_tts, the previous task has already finished and the system is only speaking the final response. "
                        "In that phase, classify as new_task only if a clear actionable request is present; otherwise use ignore. "
                        "Examples: "
                        "'stop' -> stop. "
                        "'cancel it' -> stop. "
                        "'thanks, enough' -> ignore. "
                        "'okay okay' -> ignore. "
                        "'stop and open the browser' -> new_task. "
                        "'do not read this, search the weather now' -> new_task. "
                        "Do not explain."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_user_prompt(context),
                },
            ],
        )
        return str(completion.choices[0].message.content or "")

    @staticmethod
    def _build_user_prompt(context: VoiceIntentContext) -> str:
        phase = str(context.interaction_phase or "").strip() or "unspecified"
        phase_note = (
            "The previous task has already finished and the system is only speaking the final response."
            if phase == "final_response_tts"
            else "The current task is still active or the phase is otherwise busy."
        )
        return (
            f"Transcript: {context.transcript}\n"
            f"Agent status: {context.agent_status}\n"
            f"Current task: {context.current_task}\n"
            f"TTS playing: {context.tts_playing}\n"
            f"TTS text: {context.tts_text}\n"
            f"Interaction phase: {phase}\n"
            f"Phase note: {phase_note}\n"
            "Intent:"
        )

    def _build_client(self):
        if self._client_factory is not None:
            return self._client_factory()

        api_config = self._config.api_config
        import httpx
        tls_verify = bool(api_config.get("tls_verify", True))

        return OpenAI(
            api_key=api_config.get("api_key", ""),
            base_url=api_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            http_client=httpx.Client(verify=tls_verify),
        )

    @staticmethod
    def _parse_intent(raw: Optional[str]) -> str:
        normalized = str(raw or "").strip().lower()
        if normalized in VALID_INTENTS:
            return normalized
        for token in VALID_INTENTS:
            if normalized.startswith(token):
                return token
        return "ignore"
