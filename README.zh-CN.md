<h1 align="center">同窗 2.0 - 桌面 AI 伙伴</h1>

<p align="center">
  <a href="README.md">English README</a>
</p>

<p align="center">
  <img src="image_capture_20260425_140311.png" alt="同窗桌面助手预览图" width="960">
</p>

<p align="center">
  <a href="https://github.com/mini-yifan/CoView"><img alt="Release" src="https://img.shields.io/badge/release-v2.0.0-0A84FF?style=for-the-badge"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-111827?style=for-the-badge">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-22C55E?style=for-the-badge"></a>
</p>

<p align="center">
  一个会看见、会行动、会与你协作的桌面 AI 伙伴，让电脑成为有生命感的工作空间。
</p>

---

## 为什么是同窗

同窗想做的是一件很直接的事：让电脑不再只是等待指令的工具。它应该能看见你正在看的内容，理解你想完成的任务，并和你一起在真实软件里推进工作。

同窗的核心是一个运行在本地的视觉控制循环：

```text
观察屏幕 -> 理解任务 -> 执行一步操作 -> 再次观察
```

所以它不是只能聊天的助手，而是能真正操作你正在使用的软件：浏览器、编辑器、文档、网页、桌面应用和代码工作区都可以成为它的协作现场。目标是让桌面从被动工具变成一个能回应、能行动、能陪你完成工作流的空间。

## 核心能力

| 能力                   | 同窗可以做什么                                                                         |
| ---------------------- | -------------------------------------------------------------------------------------- |
| 👀 看见桌面            | 基于截图观察和视觉推理，支持截图后端回退。                                             |
| 🖥️ 多屏幕操作        | 能理解并操作多个显示器上的窗口和内容，不局限于单一屏幕。                               |
| 🖱️ 操作电脑          | 点击、拖拽、滚动、快捷键、输入文本、读取页面/文档、打开浏览器。                        |
| 🤝 与人协作            | 通过悬浮助手提供任务输入、停止控制、运行日志、设置窗口和伴随推荐。                     |
| 🎙️ 听见并回应        | 支持 ASR 识别、TTS 播报、本地唤醒词和录音状态提示。                                    |
| 🌐 中英文支持          | 提供中英文界面文案与使用流程，适配中文和英文用户。                                     |
| 🧑‍💻 后台 Code Agent | 在后台运行代码与自动化任务，支持 Codex、Claude、Kimi、Qwen、CodeBuddy 等 provider。    |
| 🧩 跨平台              | 适配 macOS 和 Windows。                                                                |
| 🔌 模型灵活            | 支持 OpenAI-compatible 模型接口，通过 `base_url`、`api_key`、`model_name` 配置。 |
| 🛠️ 易于集成          | 可作为 Python 包嵌入，也可以直接通过 CLI 或 GUI 使用。                                 |

## 当前状态

同窗 2.0 仍处于 beta 阶段。核心架构已经拆分为 GUI、平台适配、语音、Code Agent、模型调用与 runner 模块，但模型适配、界面体验和打包发布仍在快速迭代中。

## 快速开始

环境要求：

- Python 3.10 或更新版本。为了依赖解析更顺滑，推荐使用 Python 3.11/3.12。
- macOS 或 Windows。
- 一个兼容 OpenAI 风格接口的视觉模型服务。

### 1. 克隆仓库

| macOS / Linux                                          | Windows PowerShell                                     |
| ------------------------------------------------------ | ------------------------------------------------------ |
| `git clone https://github.com/mini-yifan/CoView.git` | `git clone https://github.com/mini-yifan/CoView.git` |
| `cd CoView`                                          | `cd CoView`                                          |

### 2. 创建并激活虚拟环境

| macOS / Linux                 | Windows PowerShell             |
| ----------------------------- | ------------------------------ |
| `python3 -m venv .venv`     | `py -3 -m venv .venv`        |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |

如果 PowerShell 阻止激活虚拟环境，可以在当前 PowerShell 窗口执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 3. 安装项目

| macOS                                              | Windows                                 |
| -------------------------------------------------- | --------------------------------------- |
| `python3 -m pip install -U pip`                  | `py -m pip install -U pip`            |
| `python3 -m pip install -e ".[macos,voice,tts]"` | `py -m pip install -e ".[voice,tts]"` |

如果你要参与开发，安装开发依赖：

| macOS                                                  | Windows                                     |
| ------------------------------------------------------ | ------------------------------------------- |
| `python3 -m pip install -e ".[macos,voice,tts,dev]"` | `py -m pip install -e ".[voice,tts,dev]"` |

### 4. 配置模型

同窗默认读取仓库根目录的 `config.json`，并与 `src/baodou_ai/core/config.py` 里的默认配置合并。

最先需要配置的是：

```json
{
  "api_config": {
    "api_key": "YOUR_API_KEY",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model_name": "qwen3.6-35b-a3b"
  }
}
```

注意：

- 不要把真实 API Key 提交到公开仓库。
- 只要服务兼容 OpenAI 风格接口，并且模型具备本项目需要的视觉理解能力，就可以通过配置接入。
- 语音识别和语音播报可以分别配置 `voice_interaction_config.asr_api_key` 和 `tts_config.api_key`。

### 5. 启动

| 目标              | macOS                                             | Windows                                         |
| ----------------- | ------------------------------------------------- | ----------------------------------------------- |
| 启动悬浮 GUI      | `coview`                                        | `coview`                                      |
| 执行一个 CLI 任务 | `coview-cli "打开浏览器并搜索上海天气"`         | `coview-cli "打开记事本并输入 Hello"`         |
| 限制最大执行步数  | `coview-cli "总结当前页面" --max-iterations 20` | `coview-cli "打开计算器" --max-iterations 20` |
| 停止 CLI 任务     | `Ctrl+C`                                        | `Ctrl+C`                                      |

## macOS 与 Windows 命令差异

| 主题           | macOS                                          | Windows                                                |
| -------------- | ---------------------------------------------- | ------------------------------------------------------ |
| Python 命令    | 通常是 `python3`                             | 通常是 `py` 或 `python`                            |
| 虚拟环境激活   | `source .venv/bin/activate`                  | `.venv\Scripts\Activate.ps1`                         |
| 路径格式       | `/Users/name/project`                        | `C:\Users\name\project`                              |
| 复制粘贴快捷键 | `Command+C`、`Command+V`                   | `Ctrl+C`、`Ctrl+V`                                 |
| 自动化权限     | 在系统设置中开启辅助功能、屏幕录制、麦克风权限 | 普通应用可直接运行；如需控制管理员窗口，再用管理员终端 |
| 平台依赖       | 推荐安装 `.[macos]`，包含 PyObjC 支持        | 不需要 `macos` extra                                 |
| GUI 后端       | PyQt5 + macOS 平台适配                         | PyQt5 + Windows 平台适配                               |

写任务时，尽量用自然语言描述目标，而不是直接描述平台快捷键。例如说“复制选中的文本”，通常比说“按 Command+C”更稳。如果必须写快捷键，请使用当前系统对应的按键。

## 60 秒上手交互

1. macOS 运行 `coview`，Windows 运行 `coview`。
2. 打开悬浮助手的设置窗口，填入模型 API Key、Base URL 和模型名称。
3. 点击悬浮输入框，输入任务，按 Enter 执行。
4. 助手会持续汇报执行过程：观察屏幕、选择操作、执行一步、再次观察，直到任务完成。
5. 如果任务偏离目标、范围过大或操作了错误窗口，点击停止按钮。

适合第一次尝试的任务：

```text
打开浏览器并搜索上海天气。
总结当前浏览器标签页中的文章。
打开计算器并计算 128 * 46。
读取当前可见文档，并列出待办事项。
创建一个后台 Code Agent 任务，分析这个仓库的测试结构。
```

语音交互：

- 在设置中开启语音输入。
- 配置 `voice_interaction_config.asr_api_key` 用于语音识别。
- 配置 `tts_config.api_key` 用于语音播报。
- 如果需要免手动唤醒，下载本地唤醒词模型。
- 默认唤醒词是 `你好彤彤` 和 `hello Lulu`，可以在 `wake_word_config.phrases` 中修改。
- 说 `退出程序` 可以通过语音退出同窗；英文支持 `exit program`、`quit app` 等 `close/exit/quit program/app` 类指令。
- 空闲时说 `退下吧` 可以收起悬浮面板，但不会退出程序。
- WebRTC 回声消除依赖 `aec-audio-processing`，当前项目 marker 只会在 Python 3.11+ 上安装它。

默认交互快捷键：

| 操作 | macOS | Windows |
| --- | --- | --- |
| 呼出 / 聚焦同窗 | `Command+Shift+Space` | `Ctrl+Alt+Space` |
| 收起悬浮面板 | `Command+Shift+Y` | `Ctrl+Alt+Enter` |
| 提交输入框任务 | `Enter` | `Enter` |
| 停止当前任务 | 停止按钮，或运行中按呼出快捷键 | 停止按钮，或运行中按呼出快捷键 |

## 本地唤醒词模型

本地语音唤醒默认读取以下目录：

```text
models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20
```

下载命令：

| macOS                                           | Windows                                    |
| ----------------------------------------------- | ------------------------------------------ |
| `python3 scripts/download_wake_word_model.py` | `py scripts\download_wake_word_model.py` |

常用参数：

```bash
python3 scripts/download_wake_word_model.py --force
python3 scripts/download_wake_word_model.py --source github
python3 scripts/download_wake_word_model.py --url "https://your-cdn.example.com/model.tar.bz2"
```

Windows 对应写法：

```powershell
py scripts\download_wake_word_model.py --force
py scripts\download_wake_word_model.py --source github
py scripts\download_wake_word_model.py --url "https://your-cdn.example.com/model.tar.bz2"
```

## CLI 用法

macOS / Linux:

```bash
coview-cli "打开浏览器并搜索同窗" --api-key YOUR_API_KEY
coview-cli "关闭当前窗口" --max-iterations 10
coview-cli "读取当前页面并总结" --base-url https://api.example.com
```

Windows:

```powershell
coview-cli "打开记事本并输入 Hello" --api-key YOUR_API_KEY
coview-cli "关闭当前窗口" --max-iterations 10
coview-cli "读取当前页面并总结" --base-url https://api.example.com
```

## Python API

```python
from baodou_ai import CoViewAI

ai = CoViewAI(
    api_key="YOUR_API_KEY",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name="qwen3.6-35b-a3b",
)

result = ai.execute(
    "打开浏览器，搜索今天的 AI 新闻，并总结排名靠前的结果。",
    max_iterations=30,
)

print(result)
```

带进度回调：

```python
from baodou_ai import CoViewAI

ai = CoViewAI(api_key="YOUR_API_KEY")

def on_iteration(index, info):
    print(f"[第 {index + 1} 步] {info.get('thinking', '')}")

result = ai.execute(
    "打开计算器并计算 128 * 46。",
    on_iteration=on_iteration,
)
```

## 项目结构

```text
CoView/
├── src/baodou_ai/
│   ├── __main__.py              # 悬浮 GUI 入口
│   ├── api.py                   # 可嵌入的 Python API
│   ├── cli.py                   # 命令行入口
│   ├── agent/                   # 工具 schema、协议、注册表、执行器
│   ├── ai/                      # 模型 client、prompt、解析、记忆
│   ├── code_agent/              # 后台代码任务 provider
│   ├── core/                    # runner、截图、配置、自动化
│   ├── gui/                     # 悬浮球、设置、日志、任务界面
│   ├── platform/                # macOS / Windows 平台适配
│   ├── voice/                   # ASR、VAD、唤醒词、意图识别
│   └── tts/                     # 语音播报
├── docs/                        # 架构与集成文档
├── examples/                    # API 示例
├── scripts/                     # 辅助脚本与验收脚本
├── tests/                       # 自动化测试
├── config.json                  # 本地运行配置
├── pyproject.toml
└── README.md
```

## 开发命令

测试：

| macOS                                         | Windows                                  |
| --------------------------------------------- | ---------------------------------------- |
| `python3 -m pytest tests/`                  | `py -m pytest tests/`                  |
| `python3 -m pytest tests/test_runner.py -q` | `py -m pytest tests/test_runner.py -q` |
| `python3 scripts/run_gui_acceptance.py`     | `py scripts\run_gui_acceptance.py`     |

格式化与检查：

| macOS                          | Windows                        |
| ------------------------------ | ------------------------------ |
| `black src/baodou_ai tests`  | `black src\baodou_ai tests`  |
| `flake8 src/baodou_ai tests` | `flake8 src\baodou_ai tests` |
| `mypy src/baodou_ai`         | `mypy src\baodou_ai`         |

## Agent 协议

模型每一轮只允许一个主分支：

- 工具分支，例如 `click`、`input_text`、`hotkey`、`open_in_browser`、`read_current_document`。
- 或 `page_loading`。
- 或 `respond`。

可以附加 `report`、`remember` 等字段。Runner 会校验分支、执行一个主操作、截取下一帧观察，然后继续循环。

示例：

```json
{
  "thinking": "搜索框可见，可以直接输入查询内容。",
  "report": "我正在浏览器输入框里搜索。",
  "input_text": {
    "screen_index": 0,
    "position": [520, 150],
    "text": "上海天气",
    "replace": true,
    "submit": true
  }
}
```

## 安全提示

同窗会真实控制桌面输入。刚开始请从低风险任务试起，测试时尽量关闭敏感应用，并观察前几次执行。macOS 上只授予你理解的系统权限。Windows 上除非确实需要控制管理员权限窗口，否则不要用管理员身份运行助手。

## 参与贡献

欢迎参与开源建设。适合优先贡献的方向：

- Windows / macOS 回归测试。
- 模型适配与解析稳定性。
- 更安全的任务中断与恢复。
- 更多示例与双语文档。
- 打包、签名、发布自动化。

请尽量保持改动聚焦；行为变化请补充测试；不要提交私钥、API Key 或本地运行产物。

## License

同窗基于 [MIT License](LICENSE) 开源。
