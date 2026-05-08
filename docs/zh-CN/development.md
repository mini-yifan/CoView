# 开发指南

## 阅读顺序

快速建立全貌：

1. `README.md`
2. `docs/zh-CN/README.md`
3. `src/baodou_ai/__main__.py`
4. `src/baodou_ai/api.py`
5. `src/baodou_ai/core/runner.py`
6. `src/baodou_ai/gui/floating/controller.py`

理解主执行链：

1. `src/baodou_ai/core/runner.py`
2. `src/baodou_ai/core/runner_turns.py`
3. `src/baodou_ai/ai/client.py`
4. `src/baodou_ai/ai/parser.py`
5. `src/baodou_ai/agent/tool_registry.py`
6. `src/baodou_ai/agent/tool_executor.py`
7. `src/baodou_ai/core/automation.py`

## 测试命令

| macOS / Linux | Windows |
| --- | --- |
| `python3 -m pytest tests/` | `py -m pytest tests/` |
| `python3 -m pytest tests/test_runner.py -q` | `py -m pytest tests/test_runner.py -q` |
| `python3 scripts/run_gui_acceptance.py` | `py scripts\run_gui_acceptance.py` |

## 格式化与检查

| macOS / Linux | Windows |
| --- | --- |
| `black src/baodou_ai tests` | `black src\baodou_ai tests` |
| `flake8 src/baodou_ai tests` | `flake8 src\baodou_ai tests` |
| `mypy src/baodou_ai` | `mypy src\baodou_ai` |

## 扩展点

- 新增或调整桌面工具：`src/baodou_ai/core/automation_tools/` 和 `src/baodou_ai/agent/tool_registry.py`。
- 调整 prompt：`src/baodou_ai/ai/prompts/` 和 `src/baodou_ai/ai/client.py`。
- 改进模型解析：`src/baodou_ai/ai/parser.py` 和 `src/baodou_ai/agent/protocol.py`。
- 增加平台行为：`src/baodou_ai/platform/`。
- 改进 GUI 任务生命周期：`src/baodou_ai/gui/floating/task_session_controller.py`。
- 扩展后台任务：`src/baodou_ai/code_agent/`。
- 改进语音行为：`src/baodou_ai/voice/` 和 `src/baodou_ai/tts/`。

