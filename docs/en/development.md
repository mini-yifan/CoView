# Development

## Reading Order

For a quick orientation:

1. `README.md`
2. `docs/en/README.md`
3. `src/baodou_ai/__main__.py`
4. `src/baodou_ai/api.py`
5. `src/baodou_ai/core/runner.py`
6. `src/baodou_ai/gui/floating/controller.py`

For the main runtime:

1. `src/baodou_ai/core/runner.py`
2. `src/baodou_ai/core/runner_turns.py`
3. `src/baodou_ai/ai/client.py`
4. `src/baodou_ai/ai/parser.py`
5. `src/baodou_ai/agent/tool_registry.py`
6. `src/baodou_ai/agent/tool_executor.py`
7. `src/baodou_ai/core/automation.py`

## Test Commands

| macOS / Linux | Windows |
| --- | --- |
| `python3 -m pytest tests/` | `py -m pytest tests/` |
| `python3 -m pytest tests/test_runner.py -q` | `py -m pytest tests/test_runner.py -q` |
| `python3 scripts/run_gui_acceptance.py` | `py scripts\run_gui_acceptance.py` |

## Formatting and Checks

| macOS / Linux | Windows |
| --- | --- |
| `black src/baodou_ai tests` | `black src\baodou_ai tests` |
| `flake8 src/baodou_ai tests` | `flake8 src\baodou_ai tests` |
| `mypy src/baodou_ai` | `mypy src\baodou_ai` |

## Extension Points

- Add or adjust desktop tools in `src/baodou_ai/core/automation_tools/` and register schemas in `src/baodou_ai/agent/tool_registry.py`.
- Adjust prompt behavior in `src/baodou_ai/ai/prompts/` and `src/baodou_ai/ai/client.py`.
- Improve model parsing in `src/baodou_ai/ai/parser.py` and `src/baodou_ai/agent/protocol.py`.
- Add platform behavior in `src/baodou_ai/platform/`.
- Improve GUI task lifecycle in `src/baodou_ai/gui/floating/task_session_controller.py`.
- Extend background jobs in `src/baodou_ai/code_agent/`.
- Improve voice behavior in `src/baodou_ai/voice/` and `src/baodou_ai/tts/`.

