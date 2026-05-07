"""
配置模块测试
"""

import json

import pytest
from baodou_ai.core.config import Config, DEFAULT_CONFIG


@pytest.fixture(autouse=True)
def reset_config_singleton():
    Config.reset_shared_instance()
    yield
    Config.reset_shared_instance()


class TestConfig:
    """配置类测试"""
    
    def test_default_config_exists(self):
        """测试默认配置存在"""
        assert "api_config" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["api_config"]["tls_verify"] is True
        assert "ai_config" in DEFAULT_CONFIG
        assert "execution_config" in DEFAULT_CONFIG
        assert "screenshot_config" in DEFAULT_CONFIG
        assert "mouse_config" in DEFAULT_CONFIG
        assert "settle_min_wait_ms" in DEFAULT_CONFIG["execution_config"]
        assert DEFAULT_CONFIG["execution_config"]["process_report_mode"] == "auto"
        assert DEFAULT_CONFIG["execution_config"]["process_report_interval_steps"] == 3
        assert DEFAULT_CONFIG["execution_config"]["post_tool_capture_delay_ms"] == 250
        assert DEFAULT_CONFIG["execution_config"]["minimum_tool_interval_ms"] == 900
        assert DEFAULT_CONFIG["execution_config"]["held_modifier_auto_release_steps"] == 5
        assert DEFAULT_CONFIG["execution_config"]["held_modifier_auto_release_seconds"] == 10
        assert "stalled_replan_threshold" in DEFAULT_CONFIG["execution_config"]
        assert "save_debug_captures" in DEFAULT_CONFIG["screenshot_config"]
        assert DEFAULT_CONFIG["screenshot_config"]["capture_backend"] == "auto"
        assert DEFAULT_CONFIG["screenshot_config"]["capture_fallback_backend"] == "pyautogui"
        assert DEFAULT_CONFIG["mouse_config"]["min_move_duration"] == 0.35
        assert DEFAULT_CONFIG["floating_ball_config"]["asset_path"] == ""
        assert DEFAULT_CONFIG["floating_ball_config"]["animation_always_play"] is False
        assert "wake_word_config" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["wake_word_config"]["enabled"] is True
        assert DEFAULT_CONFIG["wake_word_config"]["provider"] == "sherpa_onnx"
        assert DEFAULT_CONFIG["wake_word_config"]["phrases"] == [
            {"text": "你好彤彤", "language": "zh"},
            {"text": "hello Lulu", "language": "en"},
        ]
        assert DEFAULT_CONFIG["wake_word_config"]["threshold"] == 0.5
        assert DEFAULT_CONFIG["wake_word_config"]["cooldown_ms"] == 1500
        assert DEFAULT_CONFIG["wake_word_config"]["post_wake_timeout_seconds"] == 8
        assert DEFAULT_CONFIG["wake_word_config"]["show_indicator"] is True
        assert (
            DEFAULT_CONFIG["wake_word_config"]["model_dir"]
            == "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
        )
        assert "companion_privacy_config" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["companion_privacy_config"]["enabled"] is True
        assert DEFAULT_CONFIG["companion_privacy_config"]["privacy_cooldown_seconds"] == 15
        assert DEFAULT_CONFIG["companion_privacy_config"]["never_persist_review_screenshots"] is True
        assert DEFAULT_CONFIG["code_agent_config"]["provider"] == "codex"
        assert set(DEFAULT_CONFIG["code_agent_config"]["providers"]) == {
            "codex",
            "claude",
            "kimi",
            "qwen",
            "codebuddy",
        }
        assert DEFAULT_CONFIG["code_agent_config"]["providers"]["qwen"]["args"] == [
            "-p",
            "{task}",
            "--output-format",
            "json",
            "--yolo",
        ]
    
    def test_config_singleton(self):
        """测试配置单例模式"""
        config1 = Config()
        config2 = Config()
        assert config1 is config2
    
    def test_config_get_method(self):
        """测试配置获取方法"""
        config = Config()
        value = config.get("api_config.base_url", "default")
        assert isinstance(value, str)
    
    def test_config_set_method(self):
        """测试配置设置方法"""
        config = Config()
        config.set("test_key", "test_value")
        assert config.get("test_key") == "test_value"

    def test_create_isolated_returns_distinct_instances(self):
        shared = Config()
        isolated_one = Config.create_isolated()
        isolated_two = Config.create_isolated()

        assert shared is Config.get_instance()
        assert isolated_one is not shared
        assert isolated_two is not shared
        assert isolated_one is not isolated_two

    def test_reset_shared_instance_recreates_singleton(self):
        config_one = Config()

        Config.reset_shared_instance()

        config_two = Config()
        assert config_one is not config_two

    def test_reload_clears_stale_resolved_paths(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "screenshot_config": {
                        "input_path": "imgs/screen.png",
                    }
                }
            ),
            encoding="utf-8",
        )

        resolved_paths = iter([
            str(tmp_path / "first-screen.png"),
            str(tmp_path / "second-screen.png"),
        ])

        class FakePlatformAdapter:
            def get_resource_path(self, relative_path):
                if relative_path == "config.json":
                    return str(config_path)
                return next(resolved_paths)

        monkeypatch.setattr("baodou_ai.core.config.get_platform_adapter", lambda: FakePlatformAdapter())

        config = Config.create_isolated(str(config_path))
        assert config.get_resolved_path("input_path") == str(tmp_path / "first-screen.png")

        config.reload()

        assert config.get_resolved_path("input_path") == str(tmp_path / "second-screen.png")

    def test_legacy_config_merges_wake_word_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "api_config": {
                        "api_key": "demo-key",
                    }
                }
            ),
            encoding="utf-8",
        )

        config = Config.create_isolated(str(config_path))

        assert config.get("api_config.api_key") == "demo-key"
        assert config.wake_word_config["enabled"] is True
        assert config.get_wake_word_phrase("zh") == "你好彤彤"
        assert config.get_wake_word_phrase("en") == "hello Lulu"

    def test_invalid_wake_word_config_falls_back_to_defaults(self, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "wake_word_config": {
                        "enabled": False,
                        "provider": "",
                        "phrases": [
                            {"text": "", "language": "zh"},
                            {"language": "en"},
                            {"text": "ignored", "language": "jp"},
                        ],
                        "threshold": "oops",
                        "cooldown_ms": -1,
                        "post_wake_timeout_seconds": "bad",
                        "show_indicator": False,
                    }
                }
            ),
            encoding="utf-8",
        )

        config = Config.create_isolated(str(config_path))

        assert config.wake_word_config["enabled"] is False
        assert config.wake_word_config["provider"] == "sherpa_onnx"
        assert config.wake_word_config["phrases"] == [
            {"text": "你好彤彤", "language": "zh"},
            {"text": "hello Lulu", "language": "en"},
        ]
        assert config.wake_word_config["threshold"] == 0.5
        assert config.wake_word_config["cooldown_ms"] == 0
        assert config.wake_word_config["post_wake_timeout_seconds"] == 8
        assert config.wake_word_config["show_indicator"] is False
        assert (
            config.wake_word_config["model_dir"]
            == "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
        )

    def test_set_wake_word_phrase_updates_and_persists(self, tmp_path):
        config_path = tmp_path / "config.json"
        config = Config.create_isolated(str(config_path))

        config.set_wake_word_phrase("zh", "你好包豆")
        config.set_wake_word_phrase("en", "Hey Baodou")
        assert config.save() is True

        reloaded = Config.create_isolated(str(config_path))
        assert reloaded.get_wake_word_phrase("zh") == "你好包豆"
        assert reloaded.get_wake_word_phrase("en") == "Hey Baodou"

        reloaded.set_wake_word_phrase("zh", "")
        assert reloaded.get_wake_word_phrase("zh") == "你好彤彤"

    def test_resolve_resource_path_prefers_platform_lookup(self, monkeypatch, tmp_path):
        config_path = tmp_path / "config.json"
        config_path.write_text("{}", encoding="utf-8")
        resolved_dir = tmp_path / "models" / "wake"
        resolved_dir.mkdir(parents=True)

        class FakePlatformAdapter:
            def get_resource_path(self, relative_path):
                if relative_path == "config.json":
                    return str(config_path)
                if relative_path == "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20":
                    return str(resolved_dir)
                return None

        monkeypatch.setattr("baodou_ai.core.config.get_platform_adapter", lambda: FakePlatformAdapter())

        config = Config.create_isolated(str(config_path))
        assert (
            config.resolve_resource_path("models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20")
            == str(resolved_dir)
        )
