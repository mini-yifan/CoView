# 架构说明

同窗有三个入口、一个统一执行内核，以及围绕它展开的多个能力层。

## 仓库结构

```text
CoView/
├── src/baodou_ai/
│   ├── __main__.py              # 悬浮 GUI 入口
│   ├── api.py                   # 可嵌入 Python API
│   ├── cli.py                   # 命令行入口
│   ├── agent/                   # 工具 schema、协议、注册表、执行器
│   ├── ai/                      # 模型 client、prompt、解析、记忆
│   ├── code_agent/              # 后台代码任务 provider
│   ├── core/                    # runner、截图、配置、自动化
│   ├── gui/                     # 悬浮球、设置、日志、任务界面
│   ├── platform/                # macOS / Windows 适配
│   ├── voice/                   # ASR、VAD、唤醒词、意图识别
│   └── tts/                     # 语音播报
├── docs/
├── examples/
├── scripts/
├── tests/
├── config.json
├── pyproject.toml
└── README.md
```

## 入口层

- GUI：`src/baodou_ai/__main__.py` 创建 `QApplication`、加载 `Config`，并启动 `FloatingController`。
- CLI：`src/baodou_ai/cli.py` 解析命令行参数，然后调用 `CoViewAI.execute()`。
- Python API：`src/baodou_ai/api.py` 暴露 `CoViewAI` 和 `execute_task`。

三个入口最终都会收敛到 `ControlLoopRunner`。

## 控制循环

每一轮执行大致包括：

1. 收集上下文。
2. 获取观察结果。
3. 拼装包含工具定义和运行状态的 prompt。
4. 通过 `AIClient` 调用模型。
5. 通过 `ResponseParser` 和 `agent.protocol` 解析响应。
6. 通过 `ToolExecutor` 执行一个主分支。
7. 收集反馈、更新记忆和产物，继续或结束。

核心文件：

- `src/baodou_ai/core/runner.py`
- `src/baodou_ai/core/runner_turns.py`
- `src/baodou_ai/core/observation.py`
- `src/baodou_ai/core/screenshot.py`
- `src/baodou_ai/core/automation.py`

## 能力层

- `baodou_ai.agent`：协议、工具注册、参数归一化、执行分发。
- `baodou_ai.ai`：OpenAI-compatible client、prompt 加载、解析、记忆和上下文。
- `baodou_ai.core`：runner、截图、自动化、反馈、停滞策略、任务记忆、运行产物。
- `baodou_ai.gui`：悬浮 UI、设置、日志、任务生命周期、伴随推荐。
- `baodou_ai.platform`：macOS/Windows 坐标、DPI、热键、透明穿透和鼠标行为。
- `baodou_ai.voice`：ASR、VAD、唤醒词、回声消除和语音意图识别。
- `baodou_ai.tts`：语音播报。
- `baodou_ai.code_agent`：后台代码任务管理、provider adapter、报告和会话存储。

## 后台 Code Agent

后台 Code Agent 用于异步运行更长的代码或自动化任务。主要路径是：

```text
Automation tool -> JobManager -> CodeAgentDispatcher -> provider adapter -> session store -> report generator
```

当前支持 Codex、Claude、Kimi、Qwen、CodeBuddy 等 provider。

