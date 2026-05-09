# Setup & Configuration

## Requirements

- Python 3.10 or newer. Python 3.11/3.12 are recommended.
- macOS or Windows.
- A visual model endpoint compatible with the OpenAI-style API shape used by this project.

## Install

```bash
git clone https://github.com/mini-yifan/CoView.git
cd CoView
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e ".[macos,voice,tts]"
```

Windows PowerShell:

```powershell
git clone https://github.com/mini-yifan/CoView.git
cd CoView
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -U pip
py -m pip install -e ".[voice,tts]"
```

For development:

```bash
python3 -m pip install -e ".[macos,voice,tts,dev]"
```

Windows:

```powershell
py -m pip install -e ".[voice,tts,dev]"
```

## Model Configuration

CoView reads `config.json` from the repository root and merges it with defaults from `src/baodou_ai/core/config.py`.

The first fields to configure are:

```json
{
  "api_config": {
    "api_key": "YOUR_API_KEY",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model_name": "qwen3.6-35b-a3b"
  }
}
```

Do not commit real API keys to a public repository. Any OpenAI-compatible endpoint can be used if it supports the visual model behavior required by the agent.

Voice features can use separate keys:

- `voice_interaction_config.asr_api_key` for realtime ASR.
- `tts_config.api_key` for speech output.

## Platform Differences

| Topic | macOS | Windows |
| --- | --- | --- |
| Python command | Usually `python3` | Usually `py` or `python` |
| Virtualenv activation | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Path style | `/Users/name/project` | `C:\Users\name\project` |
| Copy/paste hotkeys | `Command+C`, `Command+V` | `Ctrl+C`, `Ctrl+V` |
| App automation permission | Enable Accessibility, Screen Recording, and Microphone in System Settings | Run normally for standard apps; use an elevated terminal only when controlling elevated apps |
| Optional platform extra | `.[macos]` installs PyObjC support | No `macos` extra needed |
| GUI backend | PyQt5 + macOS platform adapter | PyQt5 + Windows platform adapter |

When writing tasks, use natural language when possible. For example, say `copy the selected text` instead of `press Command+C`.

## Default Interaction Shortcuts

| Action | macOS | Windows |
| --- | --- | --- |
| Show / focus CoView | `Command+Shift+Space` | `Ctrl+Alt+I` |
| Collapse the floating panel | `Command+Shift+Y` | `Ctrl+Alt+O` |
| Submit the typed task | `Enter` | `Enter` |
| Stop the current task | Stop button or show/focus shortcut while running | Stop button or show/focus shortcut while running |

## Wake-Word Model

Local wake-word detection expects this directory by default:

```text
models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20
```

Download it with:

```bash
python3 scripts/download_wake_word_model.py
```

Windows:

```powershell
py scripts\download_wake_word_model.py
```

Useful options:

```bash
python3 scripts/download_wake_word_model.py --force
python3 scripts/download_wake_word_model.py --source github
python3 scripts/download_wake_word_model.py --url "https://your-cdn.example.com/model.tar.bz2"
```
