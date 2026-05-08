# CoView Architecture Flow

This flow is aligned with the current code structure. It is meant for README promotion, but the boxes map to real modules in `src/baodou_ai`.

## Runtime Flow

```mermaid
flowchart TD
    U["👤 User Intent<br/>Text input, voice transcript, CLI task, or Python API call"]

    subgraph Entry["Entry Layer"]
        GUI["🪟 GUI<br/>__main__.py → FloatingController → TaskSessionController"]
        CLI["⌨️ CLI<br/>cli.py"]
        API["🐍 Python API<br/>CoViewAI / execute_task"]
    end

    U --> GUI
    U --> CLI
    U --> API

    GUI --> RUNNER["🧠 ControlLoopRunner<br/>Unified desktop control loop"]
    CLI --> RUNNER
    API --> RUNNER

    subgraph Loop["One Observe → Think → Act Turn"]
        OBS["👀 ObservationService<br/>hide CoView windows, capture screenshots, collect frontmost app state"]
        SHOT["🖥️ ScreenshotCapture<br/>multi-display screenshots, frame hash, screen metadata"]
        PROMPT["🧩 AIClient + PromptBuilder<br/>system prompt, tool definitions, task memory, page/document context"]
        MODEL["☁️ OpenAI-compatible model<br/>default DashScope endpoint"]
        PARSE["📐 ResponseParser + agent.protocol<br/>normalize model JSON into one branch"]
        DECIDE{"Branch"}
        TOOL["🛠️ ToolExecutor<br/>dispatch tool branch to AutomationController.tool_*"]
        WAIT["⏳ page_loading<br/>wait, observe again, avoid blind clicking"]
        RESPOND["✅ respond<br/>return final answer/report"]
    end

    RUNNER --> OBS
    OBS --> SHOT
    SHOT --> PROMPT
    PROMPT --> MODEL
    MODEL --> PARSE
    PARSE --> DECIDE

    DECIDE -->|tool branch| TOOL
    DECIDE -->|page_loading| WAIT
    DECIDE -->|respond| RESPOND

    subgraph Tools["AutomationController Mixins"]
        DESKTOP["🖱️ Desktop tools<br/>click, drag, scroll, hotkey, input text, browser open"]
        PAGE["🌐 Page reader<br/>extract, search, chunk, next"]
        DOC["📄 Document reader<br/>Word, Excel, Preview, IDE/editor text extraction"]
        FILE["📁 File tools<br/>local file operations exposed to agent tools"]
        BG["🧑‍💻 Background tools<br/>code_agent / stop_code_agent"]
        RUNTIME["🧾 Runtime tools<br/>memory, feedback, artifacts"]
    end

    TOOL --> DESKTOP
    TOOL --> PAGE
    TOOL --> DOC
    TOOL --> FILE
    TOOL --> BG
    TOOL --> RUNTIME

    DESKTOP --> PLATFORM["🧩 PlatformAdapter<br/>macOS / Windows coordinates, DPI, hotkeys, transparency, mouse motion"]
    PAGE --> CTX["📚 ContextWindowManager<br/>page/document context for future turns"]
    DOC --> CTX
    RUNTIME --> MEM["🧠 TaskMemoryStore + RuntimeArtifactStore"]

    TOOL --> FEEDBACK["🔁 Tool feedback + metrics + stall policy<br/>visible change detection, replan, pacing, reports"]
    WAIT --> FEEDBACK
    FEEDBACK --> OBS
    RESPOND --> DONE["✨ Living Workspace<br/>CoView sees, acts, and collaborates with you"]
```

## Feature Side Flows

```mermaid
flowchart TD
    subgraph Voice["🎙️ Voice Interaction"]
        WAKE["WakeWordEngine<br/>local sherpa-onnx wake words: 你好小彤 / hey Lucy"]
        ASR["QwenRealtimeAsrClient<br/>DashScope realtime ASR"]
        INTENT["VoiceIntentClassifier<br/>stop / new_task / ignore / voice exit"]
        TTS["CosyVoiceTTS<br/>spoken reports and acknowledgements"]
    end

    subgraph Floating["🪟 Floating Companion UI"]
        BALL["FloatingController<br/>floating ball, global shortcuts, pin/collapse"]
        PANEL["PanelWindow<br/>task input, stop button, runtime status"]
        SESSION["TaskSessionController<br/>AIWorker lifecycle, stop handling, history"]
        LOGS["RuntimeLogBuffer + LogWindow<br/>live execution logs"]
    end

    subgraph Companion["💡 Companion Suggestions"]
        FRONT["FrontmostAppTracker<br/>foreground app/window sampling"]
        PRIVACY["CompanionPrivacyGuard<br/>pre/post capture privacy checks"]
        RECOMMENDER["CaptureRecommendWorker + CompanionRecommender<br/>suggestions from current screen context"]
        SUGGESTION["SuggestionWindow<br/>quick action chips near the floating companion"]
    end

    subgraph CodeAgent["🧑‍💻 Background Code Agent"]
        JOBS["JobManager<br/>submit/list/cancel/dismiss jobs"]
        DISPATCH["CodeAgentDispatcher<br/>provider selection"]
        PROVIDERS["Adapters<br/>Codex, Claude, Kimi, Qwen, CodeBuddy"]
        REPORTER["CodeAgentReportGenerator<br/>result summary and spoken report"]
        STORE["JobStore + session files<br/>status, logs, artifacts"]
    end

    WAKE --> BALL
    BALL --> ASR
    ASR --> INTENT
    INTENT -->|new task| SESSION
    INTENT -->|stop / exit| PANEL
    SESSION --> TTS
    SESSION --> LOGS

    FRONT --> PRIVACY
    PRIVACY --> RECOMMENDER
    RECOMMENDER --> SUGGESTION
    SUGGESTION --> PANEL

    SESSION --> JOBS
    JOBS --> DISPATCH
    DISPATCH --> PROVIDERS
    PROVIDERS --> STORE
    STORE --> REPORTER
    REPORTER --> PANEL
```

## 中文版

```mermaid
flowchart TD
    U["👤 用户意图<br/>文字输入、语音转写、CLI 任务或 Python API 调用"]

    subgraph Entry["入口层"]
        GUI["🪟 GUI<br/>__main__.py → FloatingController → TaskSessionController"]
        CLI["⌨️ CLI<br/>cli.py"]
        API["🐍 Python API<br/>CoViewAI / execute_task"]
    end

    U --> GUI
    U --> CLI
    U --> API

    GUI --> RUNNER["🧠 ControlLoopRunner<br/>统一桌面控制循环"]
    CLI --> RUNNER
    API --> RUNNER

    subgraph Loop["单轮观察 → 思考 → 行动"]
        OBS["👀 ObservationService<br/>隐藏自身窗口、截图、收集前台应用状态"]
        SHOT["🖥️ ScreenshotCapture<br/>多屏幕截图、帧哈希、屏幕元数据"]
        PROMPT["🧩 AIClient + PromptBuilder<br/>系统提示词、工具定义、任务记忆、网页/文档上下文"]
        MODEL["☁️ OpenAI-compatible 模型<br/>默认阿里云 DashScope 兼容接口"]
        PARSE["📐 ResponseParser + agent.protocol<br/>把模型 JSON 归一化为一个分支"]
        DECIDE{"分支类型"}
        TOOL["🛠️ ToolExecutor<br/>将工具分支分发到 AutomationController.tool_*"]
        WAIT["⏳ page_loading<br/>等待页面变化，再重新观察"]
        RESPOND["✅ respond<br/>返回最终结果或报告"]
    end

    RUNNER --> OBS
    OBS --> SHOT
    SHOT --> PROMPT
    PROMPT --> MODEL
    MODEL --> PARSE
    PARSE --> DECIDE

    DECIDE -->|工具分支| TOOL
    DECIDE -->|页面加载| WAIT
    DECIDE -->|最终回复| RESPOND

    subgraph Tools["AutomationController 工具能力"]
        DESKTOP["🖱️ 桌面工具<br/>点击、拖拽、滚动、快捷键、输入文本、打开浏览器"]
        PAGE["🌐 网页读取<br/>提取、搜索、分块、继续读取"]
        DOC["📄 文档读取<br/>Word、Excel、Preview、IDE/编辑器文本提取"]
        FILE["📁 文件工具<br/>暴露给 Agent 的本地文件能力"]
        BG["🧑‍💻 后台工具<br/>code_agent / stop_code_agent"]
        RUNTIME["🧾 运行时工具<br/>记忆、反馈、产物"]
    end

    TOOL --> DESKTOP
    TOOL --> PAGE
    TOOL --> DOC
    TOOL --> FILE
    TOOL --> BG
    TOOL --> RUNTIME

    DESKTOP --> PLATFORM["🧩 PlatformAdapter<br/>macOS / Windows 坐标、DPI、热键、透明穿透、鼠标运动"]
    PAGE --> CTX["📚 ContextWindowManager<br/>把网页/文档上下文带入后续轮次"]
    DOC --> CTX
    RUNTIME --> MEM["🧠 TaskMemoryStore + RuntimeArtifactStore"]

    TOOL --> FEEDBACK["🔁 工具反馈 + 指标 + 停滞策略<br/>可见变化检测、重规划、节奏控制、过程报告"]
    WAIT --> FEEDBACK
    FEEDBACK --> OBS
    RESPOND --> DONE["✨ 有生命感的工作空间<br/>同窗会看见、会行动、会与你协作"]
```
