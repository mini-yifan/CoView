# CoView Voice Interaction Flow

This is a README-ready promotional flow for CoView's voice interaction. It keeps the diagram simple while reflecting the real runtime path: local wake word, realtime ASR, intent handling, desktop action, and spoken feedback.

```mermaid
flowchart TD
    A["🎙️ Wake<br/>你好小彤 / hey Lucy"] --> B["🪟 CoView Opens<br/>floating panel + voice indicator"]
    B --> C["👂 Listen<br/>microphone + VAD + echo cancellation"]
    C --> D["✍️ Understand Speech<br/>Qwen realtime ASR transcript"]
    D --> E{"🧭 What did you mean?"}

    E -->|idle request| F["🚀 Start Task<br/>send voice command to desktop agent"]
    E -->|while busy| G["⚡ Barge In<br/>stop / new task / ignore"]
    E -->|priority command| H["🛑 Voice Control<br/>close program / dismiss"]

    F --> I["👀 Observe & Act<br/>screens, apps, clicks, typing, reading"]
    G -->|new task| I
    G -->|stop| J["⏹️ Stop Current Work<br/>cancel action or speech"]
    G -->|ignore| K["🎧 Keep Listening<br/>filter noise, echo, and background speech"]

    I --> L["🗣️ Speak Back<br/>TTS reports result and progress"]
    J --> K
    H --> K
    L --> K
    K --> C

    L --> M["✨ Natural Collaboration<br/>talk, interrupt, continue, and work together"]
```

## 中文版

这版更适合直接放进中文 README，用来宣传同窗的语音交互机制：先用本地唤醒词叫醒，再通过实时语音识别理解任务，随后进入桌面智能体的观察和操作循环，最后用语音播报结果；执行中还能随时插话、停止或切换任务。

```mermaid
flowchart TD
    A["🎙️ 唤醒<br/>你好小彤 / hey Lucy"] --> B["🪟 同窗出现<br/>悬浮面板 + 语音状态提示"]
    B --> C["👂 聆听<br/>麦克风 + VAD + 回声消除"]
    C --> D["✍️ 语音转文字<br/>Qwen 实时 ASR 转写"]
    D --> E{"🧭 理解意图"}

    E -->|空闲任务| F["🚀 开始执行<br/>把语音指令交给桌面 Agent"]
    E -->|执行中插话| G["⚡ 插话判断<br/>停止 / 新任务 / 忽略"]
    E -->|高优先级口令| H["🛑 语音控制<br/>退出程序 / 退下吧"]

    F --> I["👀 观察并操作<br/>看屏幕、控应用、点按、输入、读取"]
    G -->|新任务| I
    G -->|停止| J["⏹️ 停止当前工作<br/>取消操作或打断播报"]
    G -->|忽略| K["🎧 继续聆听<br/>过滤噪声、回声和背景语音"]

    I --> L["🗣️ 语音回应<br/>播报进度和最终结果"]
    J --> K
    H --> K
    L --> K
    K --> C

    L --> M["✨ 自然协作<br/>可以说话、打断、继续，让电脑更像伙伴"]
```

## README Copy

CoView's voice mode is designed for natural desktop collaboration. You can wake it with `你好小彤` or `hey Lucy`, speak a task, interrupt while it is working, stop speech or actions, and let it respond through TTS after the desktop agent finishes each step.
