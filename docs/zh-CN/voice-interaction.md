# 语音交互

同窗的语音模式面向自然桌面协作：叫醒它、说出任务、执行时插话、打断当前操作或播报，并让它通过语音反馈结果。

## 主流程

1. 本地唤醒词监听 `你好小彤` 或 `hey Lucy`。
2. 命中唤醒词后，悬浮面板出现并显示语音状态。
3. 麦克风输入经过本地 VAD 和可选 WebRTC 回声消除。
4. `QwenRealtimeAsrClient` 把音频发送到 DashScope 实时 ASR，并接收转写文本。
5. 如果同窗空闲，合法转写会直接作为新的桌面任务。
6. 如果同窗正在执行或播报，`VoiceIntentClassifier` 会把转写分类为 `stop`、`new_task` 或 `ignore`。
7. 桌面 Agent 进入观察、推理、操作、反馈循环。
8. `CosyVoiceTTS` 播报进度和最终结果。

## 默认口令

| 目的 | 默认口令 |
| --- | --- |
| 唤醒词 | `你好小彤`、`hey Lucy` |
| 语音退出同窗 | `退出程序` |
| 英文退出同窗 | `exit program`、`quit app`，以及其他 `close/exit/quit program/app` 类指令 |
| 空闲时收起面板 | `退下吧` |

唤醒词可以在 `wake_word_config.phrases` 中修改。

## 运行模块

- `src/baodou_ai/voice/wake_word_engine.py`：唤醒词生命周期。
- `src/baodou_ai/voice/sherpa_keyword_spotter.py`：sherpa-onnx 关键词唤醒。
- `src/baodou_ai/voice/qwen_asr.py`：DashScope Qwen 实时 ASR、VAD 和音频边界。
- `src/baodou_ai/voice/echo_cancellation.py`：可选 WebRTC 回声消除桥接。
- `src/baodou_ai/voice/intent_classifier.py`：插话意图识别。
- `src/baodou_ai/gui/floating/voice_controller.py`：GUI 侧语音生命周期。
- `src/baodou_ai/gui/floating/tts_controller.py`：GUI 侧 TTS 状态。
- `src/baodou_ai/tts/cosyvoice.py`：语音播报。

## 回声消除

WebRTC 回声消除依赖 `aec-audio-processing`，当前项目 marker 只会在 Python 3.11+ 上安装它。如果该依赖不可用，同窗仍可进行语音输入，但 TTS 回声过滤效果会弱一些。

