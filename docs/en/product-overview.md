# Product Overview

CoView is a desktop AI companion that sees, acts, and collaborates, turning your computer into a living workspace.

It is not only a chat interface. CoView runs a local visual control loop:

```text
Observe screen -> reason about the task -> execute one action -> observe again
```

That loop lets CoView work across browsers, editors, documents, desktop apps, websites, and coding workspaces through real mouse, keyboard, voice, and background code-agent workflows.

## Core Capabilities

| Capability | Details |
| --- | --- |
| See | Captures screenshots, understands visible UI, and supports screenshot backend fallback. |
| Multi-Screen Control | Understands screen metadata and can operate across multiple displays. |
| Act | Clicks, drags, scrolls, uses hotkeys, inputs text, opens browsers, and reads pages or documents. |
| Collaborate | Provides a floating assistant UI with task input, stop control, live logs, settings, and companion suggestions. |
| Listen & Respond | Supports realtime ASR, TTS, local wake-word detection, VAD, echo cancellation, and recording indicators. |
| Chinese & English | Includes bilingual UI copy and documentation paths. |
| Background Code Agent | Runs coding and automation jobs in the background through providers such as Codex, Claude, Kimi, Qwen, and CodeBuddy. |
| Cross Platform | Provides macOS and Windows adapters. |
| Model Flexible | Uses OpenAI-compatible endpoints through `base_url`, `api_key`, and `model_name`. |
| Developer Ready | Ships as a Python package with GUI, CLI, Python API, tests, and examples. |

## Product Status

CoView 2.0 is in beta. The architecture is already split into GUI, platform, voice, code-agent, model, and runner modules. Model adapters, UI polish, packaged releases, and cross-platform acceptance are still moving quickly.

