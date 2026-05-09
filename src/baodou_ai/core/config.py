"""
配置管理模块

统一管理系统配置，包括API配置、AI配置、执行配置、截图配置和鼠标配置。
"""

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from baodou_ai.platform import get_platform_adapter

DEFAULT_CONFIG = {
    "api_config": {
        "api_key": "",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": "qwen3.6-35b-a3b",
        "tls_verify": True,
    },
    "ai_config": {
        "enable_thinking": False,
        "thinking_type": "disabled",
        "reasoning_effort": "minimal",
        "vl_high_resolution_images": False,
    },
    "memory_config": {"max_text_memory": 80, "max_image_memory": 3, "history_count": 5},
    "execution_config": {
        "max_visual_model_iterations": 80,
        "default_max_iterations": 80,
        "context_token_limit": 120000,
        "process_report_mode": "auto",
        "process_report_interval_steps": 3,
        "post_tool_capture_delay_ms": 250,
        "minimum_tool_interval_ms": 900,
        "held_modifier_auto_release_steps": 5,
        "held_modifier_auto_release_seconds": 10,
        "stalled_replan_threshold": 2,
        "stalled_difficult_threshold": 4,
        "action_signature_tolerance_px": 15,
        "settle_min_wait_ms": 250,
        "settle_probe_interval_ms": 100,
        "settle_required_stable_probes": 3,
        "settle_max_wait_ms": 4000,
        "settle_probe_width": 160,
        "settle_probe_height": 90,
        "settle_change_threshold": 0.01,
    },
    "screenshot_config": {
        "optimize_for_speed": True,
        "input_path": "imgs/screen.png",
        "save_debug_captures": False,
        "capture_backend": "auto",
        "capture_fallback_backend": "pyautogui",
    },
    "mouse_config": {"move_duration": 0.1, "min_move_duration": 0.35, "failsafe": False},
    "code_agent_config": {
        "enabled": True,
        "provider": "codex",
        "workspace_root": str(Path.home() / "Desktop"),
        "max_concurrent_jobs": 2,
        "default_timeout_seconds": 1800,
        "stream_logs_to_console": True,
        "providers": {
            "codex": {
                "command": "codex",
                "args": [
                    "exec",
                    "--json",
                    "--full-auto",
                    "--skip-git-repo-check",
                    "-m",
                    "{model}",
                    "-c",
                    'model_reasoning_effort="{reasoning_effort}"',
                    "{task}",
                ],
                "model": "",
                "reasoning_effort": "",
                "sandbox": "workspace-write",
            },
            "claude": {
                "command": "claude",
                "args": [
                    "-p",
                    "{task}",
                    "--output-format",
                    "json",
                    "--permission-mode",
                    "{permission_mode}",
                    "--model",
                    "{model}",
                ],
                "model": "",
                "permission_mode": "bypassPermissions",
            },
            "kimi": {
                "command": "kimi",
                "args": ["--quiet", "--work-dir", "{workspace_path}", "-p", "{task}"],
                "model": "",
                "auto_approve": True,
                "output_format": "text",
            },
            "qwen": {
                "command": "qwen",
                "args": ["-p", "{task}", "--output-format", "json", "--yolo"],
                "model": "",
                "auto_approve": True,
                "output_format": "json",
            },
            "codebuddy": {
                "command": "codebuddy",
                "args": ["-y", "-p", "{task}", "--output-format", "json"],
                "model": "",
                "auto_approve": True,
                "output_format": "json",
            },
        },
    },
    "tts_config": {
        "enabled": True,
        "api_key": "",
        "base_url": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        "model": "cosyvoice-v3-flash",
        "voice": "longanhuan",
        "speech_rate": 1.2,
        "volume": 50,
        "pitch_rate": 1.0,
    },
    "voice_interaction_config": {
        "enabled": True,
        "auto_start_when_pinned": True,
        "asr_provider": "qwen",
        "asr_api_key": "",
        "asr_url": "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        "asr_model": "qwen3-asr-flash-realtime",
        "asr_language": "zh",
        "sample_rate": 16000,
        "block_frames": 1600,
        "energy_threshold": 900.0,
        "adaptive_threshold_enabled": True,
        "adaptive_min_energy_threshold": 300.0,
        "adaptive_noise_multiplier": 1.8,
        "adaptive_noise_offset": 80.0,
        "adaptive_noise_alpha": 0.08,
        "vad_min_speech_ms": 200,
        "vad_end_silence_ms": 1200,
        "vad_pre_roll_ms": 500,
        "vad_max_utterance_ms": 20000,
        "echo_cancellation_enabled": True,
        "echo_cancellation_frame_ms": 10,
        "echo_cancellation_stream_delay_ms": 80,
        "echo_cancellation_ns": True,
        "echo_cancellation_agc": False,
        "asr_min_text_length": 1,
        "idle_submit_min_text_length": 3,
        "stop_spoken_text": "",
        "intent_model_name": "",
        "ignore_tts_echo": True,
        "idle_auto_unpin_seconds": 30,
        "show_voice_recording_indicator": True,
    },
    "wake_word_config": {
        "enabled": True,
        "provider": "sherpa_onnx",
        "phrases": [{"text": "你好小彤", "language": "zh"}, {"text": "hey Lucy", "language": "en"}],
        "threshold": 0.5,
        "cooldown_ms": 1500,
        "post_wake_timeout_seconds": 8,
        "show_indicator": True,
        "model_dir": "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20",
        "tokens_path": "",
        "encoder_path": "",
        "decoder_path": "",
        "joiner_path": "",
        "keywords_file": "",
        "keywords_text": "",
        "num_threads": 2,
    },
    "floating_ball_config": {
        "asset_path": "",
        "animation_always_play": False,
        "reset_animation_on_leave": True,
    },
    "companion_config": {
        "enabled": True,
        "disable_thinking": True,
        "suggestion_display_seconds": 30,
        "trigger_stable_delay_ms": 1200,
        "rapid_switch_window_seconds": 8,
        "rapid_switch_count_threshold": 4,
        "rapid_switch_cooldown_seconds": 20,
        "request_timeout_seconds": 20,
    },
    "companion_privacy_config": {
        "enabled": True,
        "enable_pre_capture_guard": True,
        "enable_post_capture_guard": True,
        "privacy_cooldown_seconds": 15,
        "app_blacklist_enabled": True,
        "title_keyword_guard_enabled": True,
        "url_guard_enabled": True,
        "password_focus_guard_enabled": True,
        "never_persist_review_screenshots": True,
    },
    "locale_config": {"locale": "zh_CN", "respond_language": ""},
}


class Config:
    """统一配置管理类"""

    _instance: Optional["Config"] = None

    def __new__(
        cls,
        config_path: Optional[str] = None,
        *,
        _shared: bool = True,
    ) -> "Config":
        if _shared:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
                cls._instance._is_shared_instance = True
            return cls._instance

        instance = super().__new__(cls)
        instance._initialized = False
        instance._is_shared_instance = False
        return instance

    def __init__(self, config_path: Optional[str] = None, *, _shared: bool = True):
        if self._initialized:
            return

        self._initialized = True
        self._config: Dict[str, Any] = {}
        self._resolved_paths: Dict[str, str] = {}
        self._platform_adapter = get_platform_adapter()
        self._config_path = Path(config_path) if config_path else self._get_default_config_path()

        self.load()

    def _get_default_config_path(self) -> Path:
        """获取默认配置文件路径"""
        if self._is_packaged_app_bundle():
            if sys.platform == "win32":
                appdata = os.environ.get("APPDATA", "")
                base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
                return base_dir / "CoView" / "config.json"
            return Path.home() / "Library" / "Application Support" / "CoView" / "config.json"

        config_path = self._platform_adapter.get_resource_path("config.json")
        if config_path and Path(config_path).exists():
            return Path(config_path)

        return Path("config.json")

    def _is_packaged_app_bundle(self) -> bool:
        is_app_bundle = getattr(self._platform_adapter, "is_app_bundle", None)
        if not callable(is_app_bundle):
            return False
        try:
            return bool(is_app_bundle())
        except Exception:
            return False

    def _merge_with_defaults(self, config_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """将外部配置与默认配置递归合并，补齐新增配置项。"""
        if not isinstance(config_data, dict):
            return copy.deepcopy(DEFAULT_CONFIG)

        def deep_merge(defaults: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
            merged = copy.deepcopy(defaults)
            for key, value in overrides.items():
                if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key] = deep_merge(merged[key], value)
                else:
                    merged[key] = value
            return merged

        merged = deep_merge(DEFAULT_CONFIG, config_data)
        merged["wake_word_config"] = self._normalize_wake_word_config(
            merged.get("wake_word_config")
        )
        return merged

    def _normalize_wake_word_config(self, config_data: Any) -> Dict[str, Any]:
        """规范化本地语音唤醒配置，并在非法输入时回退默认值。"""
        defaults = copy.deepcopy(DEFAULT_CONFIG["wake_word_config"])
        if not isinstance(config_data, dict):
            return defaults

        normalized = copy.deepcopy(defaults)

        if "enabled" in config_data:
            normalized["enabled"] = bool(config_data["enabled"])

        provider = self._coerce_non_empty_str(
            config_data.get("provider"),
            defaults["provider"],
        )
        if provider:
            normalized["provider"] = provider

        phrases = self._normalize_wake_word_phrases(config_data.get("phrases"))
        normalized["phrases"] = phrases

        normalized["threshold"] = self._coerce_float(
            config_data.get("threshold"),
            defaults["threshold"],
            minimum=0.0,
            maximum=1.0,
        )
        normalized["cooldown_ms"] = self._coerce_int(
            config_data.get("cooldown_ms"),
            defaults["cooldown_ms"],
            minimum=0,
        )
        normalized["post_wake_timeout_seconds"] = self._coerce_int(
            config_data.get("post_wake_timeout_seconds"),
            defaults["post_wake_timeout_seconds"],
            minimum=0,
        )
        normalized["model_dir"] = self._coerce_non_empty_str(
            config_data.get("model_dir"),
            defaults["model_dir"],
        )
        normalized["tokens_path"] = self._coerce_non_empty_str(
            config_data.get("tokens_path"),
            defaults["tokens_path"],
        )
        normalized["encoder_path"] = self._coerce_non_empty_str(
            config_data.get("encoder_path"),
            defaults["encoder_path"],
        )
        normalized["decoder_path"] = self._coerce_non_empty_str(
            config_data.get("decoder_path"),
            defaults["decoder_path"],
        )
        normalized["joiner_path"] = self._coerce_non_empty_str(
            config_data.get("joiner_path"),
            defaults["joiner_path"],
        )
        normalized["keywords_file"] = self._coerce_non_empty_str(
            config_data.get("keywords_file"),
            defaults["keywords_file"],
        )
        normalized["keywords_text"] = self._coerce_non_empty_str(
            config_data.get("keywords_text"),
            defaults["keywords_text"],
        )
        normalized["num_threads"] = self._coerce_int(
            config_data.get("num_threads"),
            defaults["num_threads"],
            minimum=1,
        )

        if "show_indicator" in config_data:
            normalized["show_indicator"] = bool(config_data["show_indicator"])

        return normalized

    def _normalize_wake_word_phrases(self, phrases: Any) -> List[Dict[str, str]]:
        """确保始终保留一条中文和一条英文唤醒词。"""
        default_map = self._default_wake_word_phrase_map()
        phrase_map = dict(default_map)

        if isinstance(phrases, list):
            for phrase in phrases:
                if not isinstance(phrase, dict):
                    continue
                language = str(phrase.get("language", "") or "").strip().lower()
                text = str(phrase.get("text", "") or "").strip()
                if language in phrase_map and text:
                    phrase_map[language] = text

        return [
            {"text": phrase_map["zh"], "language": "zh"},
            {"text": phrase_map["en"], "language": "en"},
        ]

    def _default_wake_word_phrase_map(self) -> Dict[str, str]:
        defaults = DEFAULT_CONFIG["wake_word_config"]["phrases"]
        return {str(item["language"]): str(item["text"]) for item in defaults}

    def _coerce_int(
        self,
        value: Any,
        default: int,
        *,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> int:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            coerced = int(default)

        if minimum is not None:
            coerced = max(minimum, coerced)
        if maximum is not None:
            coerced = min(maximum, coerced)
        return coerced

    def _coerce_float(
        self,
        value: Any,
        default: float,
        *,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        try:
            coerced = float(value)
        except (TypeError, ValueError):
            coerced = float(default)

        if minimum is not None:
            coerced = max(minimum, coerced)
        if maximum is not None:
            coerced = min(maximum, coerced)
        return coerced

    @staticmethod
    def _coerce_non_empty_str(value: Any, default: str = "") -> str:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
        return str(default or "").strip()

    def load(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if self._config_path and self._config_path.exists():
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = self._merge_with_defaults(json.load(f))
            else:
                self._config = copy.deepcopy(DEFAULT_CONFIG)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            self._config = copy.deepcopy(DEFAULT_CONFIG)

        self._resolved_paths.clear()
        self._apply_platform_paths()
        return self._config

    def _apply_platform_paths(self) -> None:
        """应用平台特定路径"""
        screenshot_config = self._config.get("screenshot_config", {})
        if "input_path" in screenshot_config:
            path = screenshot_config["input_path"]
            if not os.path.isabs(path):
                resolved = self._platform_adapter.get_resource_path(path)
                if resolved:
                    self._resolved_paths["input_path"] = resolved

        if "output_path" in screenshot_config:
            path = screenshot_config["output_path"]
            if not os.path.isabs(path):
                resolved = self._platform_adapter.get_resource_path(path)
                if resolved:
                    self._resolved_paths["output_path"] = resolved

        if "previous_image_path" in screenshot_config:
            path = screenshot_config["previous_image_path"]
            if not os.path.isabs(path):
                resolved = self._platform_adapter.get_resource_path(path)
                if resolved:
                    self._resolved_paths["previous_image_path"] = resolved

    def get_resolved_path(self, key: str) -> Optional[str]:
        """获取解析后的绝对路径"""
        if key in self._resolved_paths:
            return self._resolved_paths[key]

        screenshot_config = self._config.get("screenshot_config", {})
        return screenshot_config.get(key)

    def resolve_resource_path(self, path: Optional[str]) -> str:
        """将相对资源路径解析为绝对路径。"""
        normalized = str(path or "").strip()
        if not normalized:
            return ""

        candidate = Path(normalized)
        if candidate.is_absolute():
            return str(candidate)

        resolved = self._platform_adapter.get_resource_path(normalized)
        if resolved:
            return str(Path(resolved))

        config_dir = self._config_path.parent if self._config_path else Path(".")
        return str((config_dir / normalized).resolve())

    def save(self) -> bool:
        """保存配置到文件"""
        try:
            config_dir = self._config_path.parent if self._config_path else Path(".")
            config_dir.mkdir(parents=True, exist_ok=True)

            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    @property
    def api_config(self) -> Dict[str, Any]:
        """获取API配置"""
        return self._config.get("api_config", DEFAULT_CONFIG["api_config"])

    @property
    def ai_config(self) -> Dict[str, Any]:
        """获取AI配置"""
        return self._config.get("ai_config", DEFAULT_CONFIG["ai_config"])

    @property
    def execution_config(self) -> Dict[str, Any]:
        """获取执行配置"""
        return self._config.get("execution_config", DEFAULT_CONFIG["execution_config"])

    @property
    def memory_config(self) -> Dict[str, Any]:
        """获取记忆配置"""
        return self._config.get("memory_config", DEFAULT_CONFIG["memory_config"])

    @property
    def screenshot_config(self) -> Dict[str, Any]:
        """获取截图配置"""
        return self._config.get("screenshot_config", DEFAULT_CONFIG["screenshot_config"])

    @property
    def mouse_config(self) -> Dict[str, Any]:
        """获取鼠标配置"""
        return self._config.get("mouse_config", DEFAULT_CONFIG["mouse_config"])

    @property
    def code_agent_config(self) -> Dict[str, Any]:
        """获取后台 Code Agent 配置"""
        return self._config.get("code_agent_config", DEFAULT_CONFIG["code_agent_config"])

    @property
    def tts_config(self) -> Dict[str, Any]:
        """获取TTS语音播报配置"""
        return self._config.get("tts_config", DEFAULT_CONFIG["tts_config"])

    @property
    def voice_interaction_config(self) -> Dict[str, Any]:
        """获取语音交互配置"""
        return self._config.get(
            "voice_interaction_config", DEFAULT_CONFIG["voice_interaction_config"]
        )

    @property
    def wake_word_config(self) -> Dict[str, Any]:
        """获取本地语音唤醒配置"""
        return self._config.get("wake_word_config", DEFAULT_CONFIG["wake_word_config"])

    def get_wake_word_phrase(self, language: str) -> str:
        """按语言获取当前唤醒词，不存在时回退默认值。"""
        normalized_language = str(language or "").strip().lower()
        phrase_map = self._default_wake_word_phrase_map()
        for phrase in self.wake_word_config.get("phrases", []):
            if not isinstance(phrase, dict):
                continue
            phrase_language = str(phrase.get("language", "") or "").strip().lower()
            if phrase_language == normalized_language:
                text = str(phrase.get("text", "") or "").strip()
                if text:
                    return text
        return phrase_map.get(normalized_language, "")

    def set_wake_word_phrase(self, language: str, text: str) -> None:
        """更新指定语言的唤醒词，并保持配置结构合法。"""
        normalized_language = str(language or "").strip().lower()
        if normalized_language not in {"zh", "en"}:
            return

        phrase_map = {
            "zh": self.get_wake_word_phrase("zh"),
            "en": self.get_wake_word_phrase("en"),
        }
        normalized_text = str(text or "").strip()
        if normalized_text:
            phrase_map[normalized_language] = normalized_text
        else:
            phrase_map[normalized_language] = self._default_wake_word_phrase_map()[
                normalized_language
            ]

        self.set(
            "wake_word_config.phrases",
            [
                {"text": phrase_map["zh"], "language": "zh"},
                {"text": phrase_map["en"], "language": "en"},
            ],
        )

    @property
    def floating_ball_config(self) -> Dict[str, Any]:
        """获取悬浮球外观配置"""
        return self._config.get("floating_ball_config", DEFAULT_CONFIG["floating_ball_config"])

    @property
    def companion_config(self) -> Dict[str, Any]:
        """获取伴随推荐配置"""
        return self._config.get("companion_config", DEFAULT_CONFIG["companion_config"])

    @property
    def companion_privacy_config(self) -> Dict[str, Any]:
        """获取伴随推荐隐私保护配置"""
        return self._config.get(
            "companion_privacy_config",
            DEFAULT_CONFIG["companion_privacy_config"],
        )

    @property
    def locale_config(self) -> Dict[str, Any]:
        """获取语言区域配置"""
        return self._config.get("locale_config", DEFAULT_CONFIG["locale_config"])

    def get_respond_language(self) -> str:
        """根据 locale 配置推断模型输出语言"""
        explicit = str(self.locale_config.get("respond_language", "") or "").strip()
        if explicit:
            return explicit
        locale = str(self.locale_config.get("locale", "zh_CN") or "zh_CN").strip()
        lang_map = {
            "zh_CN": "Chinese (Simplified)",
            "zh_TW": "Chinese (Traditional)",
            "en_US": "English",
            "ja_JP": "Japanese",
            "ko_KR": "Korean",
        }
        return lang_map.get(locale, "English")

    def get_model_api_key_missing_message(self, respond_language_override: str = "") -> str:
        """返回与当前响应语言一致的主模型 API Key 缺失提示。"""
        override = str(respond_language_override or "").strip()
        language = override or self.get_respond_language()
        if override:
            use_english = "english" in language.lower()
        else:
            use_english = (
                "english" in language.lower()
                or str(self.locale_config.get("locale", "")).strip() == "en_US"
            )
        if use_english:
            return "Model API key is not configured. Please enter an API key in Settings first."
        return "模型 API Key 未配置，请先在设置中填写接口密钥。"

    @property
    def api_key(self) -> str:
        """获取API密钥"""
        return self.api_config.get("api_key", "")

    @api_key.setter
    def api_key(self, value: str) -> None:
        """设置API密钥"""
        self.set("api_config.api_key", value)
        self.save()

    def reload(self) -> None:
        """重新加载配置"""
        self.load()

    @classmethod
    def create_isolated(cls, config_path: Optional[str] = None) -> "Config":
        """创建独立配置实例，不复用共享单例。"""
        return cls(config_path=config_path, _shared=False)

    @classmethod
    def reset_shared_instance(cls) -> None:
        """重置共享配置单例。"""
        cls._instance = None

    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> "Config":
        """获取配置单例"""
        return cls(config_path)
