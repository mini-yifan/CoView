# 安装与配置

## 环境要求

- Python 3.10 或更新版本，推荐 Python 3.11/3.12。
- macOS 或 Windows。
- 一个兼容 OpenAI 风格接口的视觉模型服务。

## 安装

macOS / Linux:

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

开发依赖：

```bash
python3 -m pip install -e ".[macos,voice,tts,dev]"
```

Windows:

```powershell
py -m pip install -e ".[voice,tts,dev]"
```

## 模型配置

同窗默认读取仓库根目录的 `config.json`，并与 `src/baodou_ai/core/config.py` 中的默认配置合并。

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

不要把真实 API Key 提交到公开仓库。只要服务兼容 OpenAI 风格接口，并且模型具备本项目需要的视觉理解能力，就可以通过配置接入。

语音能力可以分别配置：

- `voice_interaction_config.asr_api_key`：实时语音识别。
- `tts_config.api_key`：语音播报。

## macOS 与 Windows 差异

| 主题 | macOS | Windows |
| --- | --- | --- |
| Python 命令 | 通常是 `python3` | 通常是 `py` 或 `python` |
| 虚拟环境激活 | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| 路径格式 | `/Users/name/project` | `C:\Users\name\project` |
| 复制粘贴快捷键 | `Command+C`、`Command+V` | `Ctrl+C`、`Ctrl+V` |
| 自动化权限 | 在系统设置中开启辅助功能、屏幕录制、麦克风权限 | 普通应用可直接运行；如需控制管理员窗口，再用管理员终端 |
| 平台依赖 | 推荐安装 `.[macos]`，包含 PyObjC 支持 | 不需要 `macos` extra |
| GUI 后端 | PyQt5 + macOS 平台适配 | PyQt5 + Windows 平台适配 |

写任务时，尽量用自然语言描述目标，而不是直接描述平台快捷键。例如说“复制选中的文本”，通常比说“按 Command+C”更稳。

## 默认交互快捷键

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

```bash
python3 scripts/download_wake_word_model.py
```

Windows:

```powershell
py scripts\download_wake_word_model.py
```

常用参数：

```bash
python3 scripts/download_wake_word_model.py --force
python3 scripts/download_wake_word_model.py --source github
python3 scripts/download_wake_word_model.py --url "https://your-cdn.example.com/model.tar.bz2"
```
