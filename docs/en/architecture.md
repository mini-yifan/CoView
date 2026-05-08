# Architecture

CoView has three entry points, one shared execution kernel, and several capability layers around it.

## Repository Structure

```text
CoView/
├── src/baodou_ai/
│   ├── __main__.py              # Floating GUI entry
│   ├── api.py                   # Embeddable Python API
│   ├── cli.py                   # Terminal entry
│   ├── agent/                   # Tool schema, protocol, registry, executor
│   ├── ai/                      # Model client, prompts, parser, memory
│   ├── code_agent/              # Background coding job providers
│   ├── core/                    # Runner, screenshots, config, automation
│   ├── gui/                     # Floating ball, settings, logs, task UI
│   ├── platform/                # macOS and Windows adapters
│   ├── voice/                   # ASR, VAD, wake word, intent classification
│   └── tts/                     # Speech output
├── docs/
├── examples/
├── scripts/
├── tests/
├── config.json
├── pyproject.toml
└── README.md
```

## Entry Layer

- GUI: `src/baodou_ai/__main__.py` creates `QApplication`, loads `Config`, and starts `FloatingController`.
- CLI: `src/baodou_ai/cli.py` parses command-line arguments and calls `CoViewAI.execute()`.
- Python API: `src/baodou_ai/api.py` exposes `CoViewAI` and `execute_task`.

All three paths converge on `ControlLoopRunner`.

## Control Loop

Each turn performs:

1. Collect context.
2. Capture observation.
3. Build prompt with tool definitions and runtime state.
4. Call the model through `AIClient`.
5. Parse the response through `ResponseParser` and `agent.protocol`.
6. Execute one branch through `ToolExecutor`.
7. Collect feedback, update memory/artifacts, and continue or finish.

The main files are:

- `src/baodou_ai/core/runner.py`
- `src/baodou_ai/core/runner_turns.py`
- `src/baodou_ai/core/observation.py`
- `src/baodou_ai/core/screenshot.py`
- `src/baodou_ai/core/automation.py`

## Capability Layers

- `baodou_ai.agent`: protocol, tool registry, argument normalization, execution dispatch.
- `baodou_ai.ai`: OpenAI-compatible client, prompt loading, parsing, memory, and context.
- `baodou_ai.core`: runner, screenshots, automation, feedback, stall policy, task memory, runtime artifacts.
- `baodou_ai.gui`: floating UI, settings, logs, task session lifecycle, companion suggestions.
- `baodou_ai.platform`: macOS/Windows adapters for coordinates, DPI, hotkeys, transparency, and mouse behavior.
- `baodou_ai.voice`: ASR, VAD, wake word, echo cancellation, and voice intent classification.
- `baodou_ai.tts`: speech output.
- `baodou_ai.code_agent`: background coding job manager, provider adapters, reports, and session storage.

## Background Code Agent

The background Code Agent lets CoView run longer coding or automation tasks asynchronously. The main path is:

```text
Automation tool -> JobManager -> CodeAgentDispatcher -> provider adapter -> session store -> report generator
```

It supports providers such as Codex, Claude, Kimi, Qwen, and CodeBuddy.

