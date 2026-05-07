<h1 align="center">CoView - Vision-Powered Desktop Assistant</h1>

<p align="center">
  <a href="README.zh-CN.md">中文文档</a>
</p>

<p align="center">
  <img src="image_capture_20260425_140311.png" alt="CoView desktop assistant preview" width="960">
</p>

<p align="center">
  <a href="https://github.com/mini-yifan/CoView"><img alt="Release" src="https://img.shields.io/badge/release-v2.0.0-0A84FF?style=for-the-badge"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-111827?style=for-the-badge">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-22C55E?style=for-the-badge"></a>
</p>

<p align="center">
  A personal AI assistant that watches your screen, understands your intent, and operates desktop apps through mouse, keyboard, voice, and background code-agent workflows.
</p>

---

## Why CoView

CoView is a local desktop automation agent built around a visual model control loop:

```text
Observe screen -> reason about the task -> execute one action -> observe again
```

Instead of only chatting, CoView can interact with the software you already use: browsers, editors, documents, websites, desktop apps, and coding workspaces. It supports a floating GUI, a terminal CLI, and a Python API, all routed through the same `ControlLoopRunner`.

## Highlights

- Visual desktop control with screenshot observation and multi-display support.
- Mouse and keyboard automation: click, drag, scroll, hotkeys, text input, page/document reading, and browser opening.
- Floating assistant UI with task input, stop control, runtime logs, settings, language switching, and companion suggestions.
- Voice interaction with ASR, TTS, local wake-word detection, and visual recording indicators.
- Background Code Agent jobs through providers such as Codex, Claude, Kimi, Qwen, and CodeBuddy.
- Cross-platform adapters for macOS and Windows.
- OpenAI-compatible model endpoint support through `base_url`, `api_key`, and `model_name`.
- Testable Python package with CLI and embeddable API.

## Status

CoView 2.0 is in beta. The architecture is already split into GUI, platform, voice, code-agent, model, and runner modules, but some areas are still moving quickly. Expect active iteration, especially around model adapters, UI polish, and packaged releases.

## Quick Start

Requirements:

- Python 3.10 or newer. Python 3.11/3.12 are recommended for the smoothest dependency resolution.
- macOS or Windows.
- A visual model endpoint compatible with the OpenAI-style API shape used by this project.

### 1. Clone the repository

| macOS / Linux | Windows PowerShell |
| --- | --- |
| `git clone https://github.com/mini-yifan/CoView.git` | `git clone https://github.com/mini-yifan/CoView.git` |
| `cd CoView` | `cd CoView` |

### 2. Create and activate a virtual environment

| macOS / Linux | Windows PowerShell |
| --- | --- |
| `python3 -m venv .venv` | `py -3 -m venv .venv` |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |

If PowerShell blocks activation, run this once in the same PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 3. Install CoView

| macOS | Windows |
| --- | --- |
| `python3 -m pip install -U pip` | `py -m pip install -U pip` |
| `python3 -m pip install -e ".[macos,voice,tts]"` | `py -m pip install -e ".[voice,tts]"` |

For development tools:

| macOS | Windows |
| --- | --- |
| `python3 -m pip install -e ".[macos,voice,tts,dev]"` | `py -m pip install -e ".[voice,tts,dev]"` |

### 4. Configure your model

CoView reads `config.json` from the repository root and merges it with defaults from `src/baodou_ai/core/config.py`.

Edit these fields first:

```json
{
  "api_config": {
    "api_key": "YOUR_API_KEY",
    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    "model_name": "doubao-seed-1-6-vision-250815"
  }
}
```

Notes:

- Do not commit real API keys to a public repository.
- Any OpenAI-compatible endpoint can be used if it supports the visual model behavior required by the agent.
- Voice features can use separate keys under `voice_interaction_config.asr_api_key` and `tts_config.api_key`.

### 5. Run the app

| Goal | macOS | Windows |
| --- | --- | --- |
| Start the floating GUI | `coview` | `coview` |
| Run one CLI task | `coview-cli "Open the browser and search today's weather"` | `coview-cli "Open Notepad and type Hello"` |
| Limit task steps | `coview-cli "Summarize the current page" --max-iterations 20` | `coview-cli "Open Calculator" --max-iterations 20` |
| Stop a CLI task | `Ctrl+C` | `Ctrl+C` |

## macOS vs Windows Differences

| Topic | macOS | Windows |
| --- | --- | --- |
| Python command | Usually `python3` | Usually `py` or `python` |
| Virtualenv activation | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Path style | `/Users/name/project` | `C:\Users\name\project` |
| Copy/paste hotkeys | `Command+C`, `Command+V` | `Ctrl+C`, `Ctrl+V` |
| App automation permission | Enable Accessibility, Screen Recording, and Microphone in System Settings | Run normally for standard apps; use an elevated terminal only when controlling elevated apps |
| Optional platform extra | `.[macos]` installs PyObjC support | No `macos` extra needed |
| GUI backend | PyQt5 + macOS platform adapter | PyQt5 + Windows platform adapter |

When writing tasks, natural language is usually better than naming platform-specific hotkeys. For example, say `copy the selected text` instead of `press Command+C`. If you do need to mention a shortcut, use the correct one for your system.

## First Interaction in 60 Seconds

1. Start the GUI with `coview` on macOS or `coview` on Windows.
2. Open the floating assistant settings and enter your model API key, base URL, and model name.
3. Click the floating assistant input, type a task, and press Enter.
4. Watch the assistant report what it is doing. It will observe the screen, choose one action, execute it, then continue until the task is done.
5. Use the stop button if the task is wrong, too broad, or interacting with the wrong window.

Good first tasks:

```text
Open the browser and search for the weather in Shanghai.
Summarize the article in the current browser tab.
Open Calculator and compute 128 * 46.
Read the visible document and list the action items.
Create a background code-agent task to inspect this repository's test structure.
```

Voice workflow:

- Enable voice input in Settings.
- Configure `voice_interaction_config.asr_api_key` for ASR and `tts_config.api_key` for speech output.
- Download the local wake-word model if you want hands-free wakeup.
- Default wake words are configured under `wake_word_config.phrases`.
- WebRTC echo cancellation depends on `aec-audio-processing`, which is only installed on Python 3.11+ by the current project markers.

## Wake-Word Model

Local wake-word detection expects this model directory by default:

```text
models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20
```

Download it with:

| macOS | Windows |
| --- | --- |
| `python3 scripts/download_wake_word_model.py` | `py scripts\download_wake_word_model.py` |

Useful options:

```bash
python3 scripts/download_wake_word_model.py --force
python3 scripts/download_wake_word_model.py --source github
python3 scripts/download_wake_word_model.py --url "https://your-cdn.example.com/model.tar.bz2"
```

Windows equivalents:

```powershell
py scripts\download_wake_word_model.py --force
py scripts\download_wake_word_model.py --source github
py scripts\download_wake_word_model.py --url "https://your-cdn.example.com/model.tar.bz2"
```

## CLI Usage

```bash
coview-cli "Open the browser and search CoView" --api-key YOUR_API_KEY
coview-cli "Close the active window" --max-iterations 10
coview-cli "Read the current page and summarize it" --base-url https://api.example.com
```

Windows:

```powershell
coview-cli "Open Notepad and type Hello" --api-key YOUR_API_KEY
coview-cli "Close the active window" --max-iterations 10
coview-cli "Read the current page and summarize it" --base-url https://api.example.com
```

## Python API

```python
from baodou_ai import CoViewAI

ai = CoViewAI(
    api_key="YOUR_API_KEY",
    base_url="https://ark.cn-beijing.volces.com/api/v3",
    model_name="doubao-seed-1-6-vision-250815",
)

result = ai.execute(
    "Open the browser, search for today's AI news, and summarize the top results.",
    max_iterations=30,
)

print(result)
```

With progress callbacks:

```python
from baodou_ai import CoViewAI

ai = CoViewAI(api_key="YOUR_API_KEY")

def on_iteration(index, info):
    print(f"[step {index + 1}] {info.get('thinking', '')}")

result = ai.execute(
    "Open Calculator and compute 128 * 46.",
    on_iteration=on_iteration,
)
```

## Project Structure

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
├── docs/                        # Architecture and integration notes
├── examples/                    # API examples
├── scripts/                     # Helper and acceptance scripts
├── tests/                       # Automated tests
├── config.json                  # Local runtime config
├── pyproject.toml
└── README.md
```

## Development

Run tests:

| macOS | Windows |
| --- | --- |
| `python3 -m pytest tests/` | `py -m pytest tests/` |
| `python3 -m pytest tests/test_runner.py -q` | `py -m pytest tests/test_runner.py -q` |
| `python3 scripts/run_gui_acceptance.py` | `py scripts\run_gui_acceptance.py` |

Format and check:

| macOS | Windows |
| --- | --- |
| `black src/baodou_ai tests` | `black src\baodou_ai tests` |
| `flake8 src/baodou_ai tests` | `flake8 src\baodou_ai tests` |
| `mypy src/baodou_ai` | `mypy src\baodou_ai` |

## Agent Protocol

The model response uses one primary branch per turn:

- A tool branch such as `click`, `input_text`, `hotkey`, `open_in_browser`, or `read_current_document`.
- Or `page_loading`.
- Or `respond`.

Optional fields such as `report` and `remember` can be attached. The runner validates the branch, executes exactly one main action, captures the next observation, and continues.

Example:

```json
{
  "thinking": "The search field is visible, so I can enter the query directly.",
  "report": "I am searching from the browser input field.",
  "input_text": {
    "screen_index": 0,
    "position": [520, 150],
    "text": "weather in Shanghai",
    "replace": true,
    "submit": true
  }
}
```

## Safety Notes

CoView controls real desktop input. Start with low-risk tasks, keep sensitive apps closed during testing, and watch the first few runs. On macOS, grant only the permissions you understand. On Windows, avoid running the assistant as administrator unless you specifically need to control administrator-level windows.

## Contributing

Contributions are welcome. Good first areas:

- Windows and macOS regression testing.
- Model adapter improvements.
- Safer task interruption and recovery.
- More examples and bilingual documentation.
- Packaging, signing, and release automation.

Please keep changes focused, add tests for behavior changes, and avoid committing private keys or local runtime files.

## License

CoView is released under the [MIT License](LICENSE).
