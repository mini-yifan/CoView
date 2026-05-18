# 语音回声消除设计说明

本文说明同窗语音交互中的回声消除逻辑。目标读者是后续维护语音、ASR、TTS 和浮窗交互的开发者。

相关需求文档见：

- `docs/zh-CN/voice-echo-control-requirements.md`

## 问题背景

语音交互中，AI 会通过扬声器播报结果。扬声器声音可能被麦克风再次录入，导致系统把 AI 自己说过的话识别成用户命令。

典型误触发链路是：

```text
AI 播报 -> 扬声器外放 -> 麦克风录入 -> ASR 转写 -> 被当成用户指令
```

这类问题不能只靠降低音量解决。用户可能把扬声器开得很大，也可能使用外放设备。系统需要在音频层和文本层都做防护。

## 总体结构

当前实现采用跨平台方案，不接入 macOS 专有 VoiceProcessingIO。整体链路如下：

```text
TTS 播放音频
  -> 扬声器播放
  -> EchoCancellationBridge.add_rendered_audio()
     -> WebRTC AEC reverse stream
     -> 最近播放音频参考缓存

麦克风输入
  -> EchoCancellationBridge.process_capture()
     -> WebRTC AEC capture stream
  -> residual echo gate
  -> LocalVadSegmenter
  -> DashScope Qwen ASR
  -> VoiceInteractionController 文本回声过滤
  -> VoiceIntentClassifier 意图分类
```

核心思想是分层防护：

1. WebRTC AEC 尽量在音频层减掉 AI 自己的声音。
2. residual echo gate 在 VAD 前挡掉仍像播放参考的残留回声。
3. TTS 文本历史和播报后保护窗口挡掉迟到或截断的 ASR 回声。
4. 意图分类继续判断用户语音是暂停、新任务还是忽略。

## 关键模块

### TTS 播放与回声参考

实现位置：

- `src/baodou_ai/tts/cosyvoice.py`
- `src/baodou_ai/gui/floating/tts_controller.py`
- `src/baodou_ai/voice/echo_cancellation.py`

`CosyVoiceTTS._play_audio()` 每拿到一段 TTS 音频，会先调用：

```python
get_echo_cancellation_bridge().add_rendered_audio(data, _SAMPLE_RATE)
```

然后再写入扬声器：

```python
stream.write(data)
```

这里的“回声参考”不是保存完整音频文件，也不是等整段播完才处理。它是实时的：

```text
拿到一小段 TTS PCM
  -> 立刻作为 reference 送给 AEC
  -> 同时保存到最近播放参考缓存
  -> 再播放到扬声器
```

这样麦克风稍后收到类似声音时，系统可以判断这部分可能来自 AI 自己。

### WebRTC AEC

实现位置：

- `src/baodou_ai/voice/echo_cancellation.py`

`WebRtcEchoCanceller` 封装 `aec-audio-processing` 的 AudioProcessor。它维护两条流：

- reverse stream：AI 正在播放的音频
- capture stream：麦克风采集到的音频

TTS 音频进入：

```python
WebRtcEchoCanceller.add_rendered_audio()
```

麦克风音频进入：

```python
WebRtcEchoCanceller.process_capture()
```

AEC 会根据 reverse stream 尝试从 capture stream 中消除相似声音。

注意：

- AEC 不是百分百可靠。
- 扬声器过大、麦克风削波、房间反射、设备延迟不准都会降低效果。
- 因此后面仍然需要 residual echo gate 和文本层兜底。

### 最近播放音频参考缓存

实现位置：

- `EchoCancellationBridge._remember_rendered_audio()`
- `EchoCancellationBridge.looks_like_residual_echo()`

`EchoCancellationBridge` 除了把 TTS 音频送给 WebRTC AEC，还会保存最近约 2 秒的播放音频。

这个缓存用于 residual echo gate：

```text
AEC 后的麦克风 chunk
  -> 和最近播放参考做相关性比较
  -> 高相关时认为像 AI 残留回声
  -> 不送入 VAD/ASR
```

相关性判断大致过程：

1. 把 capture chunk 重采样到 reference 的采样率。
2. 转成 `int16 -> float32` 样本。
3. 对 capture 去均值并计算范数。
4. 在最近播放参考中滑动窗口。
5. 计算归一化相关系数。
6. 任一窗口相关性超过阈值，即认为是残留回声。

默认阈值：

```text
voice_interaction_config.residual_echo_correlation_threshold = 0.78
```

### Residual Echo Gate

实现位置：

- `QwenRealtimeAsrClient._should_drop_residual_echo()`
- `QwenRealtimeAsrClient._handle_chunk()`

麦克风 chunk 的处理顺序是：

```text
raw microphone chunk
  -> AEC process_capture()
  -> residual echo gate
  -> LocalVadSegmenter
  -> ASR
```

Residual echo gate 只在以下条件都满足时启用：

- `residual_echo_gate_enabled` 为 true
- 最近有 TTS render reference 活跃
- VAD 当前还没有进入用户语音段
- AEC 后的 chunk 和最近播放参考高度相关

如果命中，就直接丢弃该 chunk：

```python
if self._should_drop_residual_echo(chunk):
    return
```

关键保护规则：

```python
if self._vad.in_speech:
    return False
```

也就是说，一旦已经确认用户语音段开始，后续 chunk 不再被 residual echo gate 丢弃。这样可以避免用户说话过程中，某些片段与 AI 播放内容相关而导致用户语音被截断。

### VAD

实现位置：

- `src/baodou_ai/voice/local_vad.py`
- `QwenRealtimeAsrClient._handle_chunk()`

VAD 使用的是本地能量型分段器 `LocalVadSegmenter`。它接收的是：

```text
AEC 后并经过 residual echo gate 的音频
```

不是原始麦克风音频。

这点很重要：

```text
原始麦克风音频：AI 外放声可能很大
AEC 后音频：AI 声音被削弱，更适合判断用户是否说话
```

VAD 负责形成完整语音段：

- `start`：检测到说话开始
- `chunk`：语音段中间音频
- `end`：检测到静音或达到最大时长

语音段结束后，ASR 才 commit：

```python
self._conversation.commit()
```

产品上，用户开始说话不会立即暂停 AI。系统会先收集候选语音段，等转写完成后再做意图判断。

## 文本层回声过滤

音频层无法保证完全消除回声，所以 ASR 文本还需要再过滤。

实现位置：

- `TTSController.recent_texts()`
- `TTSController.is_in_echo_guard()`
- `FloatingController.recent_tts_texts()`
- `FloatingController.is_in_tts_echo_guard()`
- `VoiceInteractionController._should_ignore_tts_echo()`

### TTS 文本历史

`TTSController` 会记录最近播报文本：

```text
(text, started_at, finished_at)
```

默认保留窗口：

```text
voice_interaction_config.tts_echo_history_seconds = 20
```

播报结束后，`current_text` 可以清空，但历史文本仍保留，用于判断迟到的 ASR 是否来自刚才的 AI 播报。

### 播报后保护窗口

播报结束后，ASR 可能稍晚才返回刚才的回声转写。为避免这类迟到文本被当成空闲新任务，系统保留一个保护窗口。

默认值：

```text
voice_interaction_config.tts_echo_guard_seconds = 2.5
```

保护窗口内，即使当前 TTS 已经结束，也不会把 transcript 直接走空闲提交：

```text
空闲 transcript -> submit_voice_task
```

而是进入忙碌/播报语境的意图分类：

```text
transcript -> stop / new_task / ignore
```

### 文本匹配规则

`VoiceInteractionController._should_ignore_tts_echo()` 使用当前 TTS 文本和最近 TTS 历史作为候选。

命中以下任一条件时，认为 transcript 是 AI 回声，应忽略：

- transcript 是播报文本子串
- 播报文本是 transcript 子串
- transcript 与播报文本相似度超过阈值
- transcript 与播报文本字符重合度超过阈值
- transcript 与播报文本分句片段高度相似

默认阈值：

```text
tts_echo_text_similarity_threshold = 0.72
tts_echo_fragment_similarity_threshold = 0.82
```

分句匹配用于处理这种情况：

```text
AI 播报：第一句说明。打开浏览器已经完成。最后一句。
ASR 返回：打开浏览器已经完成
```

虽然 ASR 只返回了播报的一小段，也应被识别为回声。

### 显式打断不被过滤

如果用户说的是明确打断词，不应因为它出现在 AI 播报文本里而被忽略。

例如 AI 播报：

```text
如果想停止可以说停下
```

用户说：

```text
停下
```

这时不能把“停下”当作回声过滤掉。因此 `_should_ignore_tts_echo()` 会先检查显式打断词：

- 停下
- 停止
- 暂停
- 别说
- 别执行
- 取消
- stop
- cancel
- pause

命中这些词时，直接允许进入意图分类。

## 状态和行为

### AI 执行任务但未播报

处理逻辑：

```text
用户说话 -> VAD/ASR -> 意图分类 -> stop/new_task/ignore
```

AI 不会因为用户开始说话而暂停任务。只有 transcript 完成并被分类为 `stop` 或 `new_task` 后，才改变任务状态。

### AI 正在播报

处理逻辑：

```text
麦克风输入
  -> AEC
  -> residual echo gate
  -> VAD/ASR
  -> 文本回声过滤
  -> 意图分类
```

只有 AI 自己的声音时：

```text
AEC / residual echo gate / 文本过滤
  -> ignore
```

用户插话时：

```text
用户声音保留
  -> ASR
  -> stop/new_task/ignore
```

### 用户先说话，AI 后播报

产品要求是 AI 不等待。

处理逻辑：

```text
用户开始说话
AI 继续执行或播报
TTS 音频实时进入回声参考
麦克风音频继续 AEC/VAD/ASR
用户说完后再做意图分类
```

这样无关自言自语不会拖慢执行，有效指令会在完整转写后生效。

### AI 刚播完

处理逻辑：

```text
TTS 结束
进入 tts_echo_guard_seconds 保护窗口
迟到 transcript 不直接提交新任务
先做文本回声过滤
再做意图分类
```

这样可以避免 AI 最后一句话的尾音变成新任务。

## 配置项

新增配置均位于 `voice_interaction_config`。

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `tts_echo_guard_seconds` | `2.5` | TTS 结束后的文本保护窗口 |
| `tts_echo_history_seconds` | `20` | 最近 TTS 文本保留时长 |
| `tts_echo_text_similarity_threshold` | `0.72` | transcript 与整段 TTS 文本的相似度阈值 |
| `tts_echo_fragment_similarity_threshold` | `0.82` | transcript 与 TTS 分句片段的相似度阈值 |
| `residual_echo_gate_enabled` | `true` | 是否启用 AEC 后、VAD 前的残留回声门控 |
| `residual_echo_correlation_threshold` | `0.78` | 音频相关性超过该值时判定为残留回声 |
| `residual_echo_reference_hangover_ms` | `300` | TTS reference 最后活跃后继续认为 render active 的时间 |

已有相关配置：

| 配置项 | 默认值 | 作用 |
| --- | --- | --- |
| `echo_cancellation_enabled` | `true` | 是否启用 WebRTC AEC |
| `echo_cancellation_frame_ms` | `10` | AEC 帧长 |
| `echo_cancellation_stream_delay_ms` | `80` | 估计的播放到采集延迟 |
| `echo_cancellation_ns` | `true` | 是否启用降噪 |
| `echo_cancellation_agc` | `false` | 是否启用 AGC |
| `ignore_tts_echo` | `true` | 是否启用文本层 TTS 回声过滤 |

## 失败和降级

### AEC 不可用

如果 `aec-audio-processing` 不可用，`EchoCancellationBridge.available` 为 false，系统会退回原始麦克风输入。

即使 AEC 不可用，以下保护仍然有效：

- TTS 文本历史
- 播报后保护窗口
- 文本相似度回声过滤
- 意图分类保守判断

### residual echo gate 不命中

如果音频相关性不足，chunk 会继续进入 VAD。这不是错误，因为可能是用户真实说话。

后续仍有：

- VAD 分段
- ASR
- 文本回声过滤
- 意图分类

### 显式打断误判风险

显式打断词会绕过文本回声过滤。这样做是为了保证用户可以打断 AI。

代价是：如果 AI 播报中恰好只说了“停下”这类词，且音频层没有挡住，可能进入意图分类。后续意图分类仍会结合上下文判断，不会直接执行。

## 维护建议

调试回声问题时，优先按这个顺序看：

1. TTS 播放音频是否调用了 `add_rendered_audio()`。
2. `EchoCancellationBridge.available` 是否为 true。
3. `residual_echo_gate_enabled` 是否为 true。
4. ASR transcript 是否与最近 TTS 文本相似。
5. TTS 是否刚结束，是否处于 `tts_echo_guard_seconds` 窗口内。
6. 用户说话是否已经进入 VAD speech 段。

调整参数时建议：

- 误过滤用户语音：降低 residual gate 强度，或提高 `residual_echo_correlation_threshold`。
- AI 回声仍进入 ASR：降低 `residual_echo_correlation_threshold`，或增加 `tts_echo_guard_seconds`。
- AI 播报尾音变成新任务：检查 `tts_echo_guard_seconds` 和 `tts_echo_history_seconds`。
- 播报内容片段未被过滤：降低 `tts_echo_fragment_similarity_threshold`。

不要只依赖单层保护。大音量扬声器回灌是物理声学问题，AEC、残留门控、文本历史和意图分类需要一起工作。

## 测试覆盖

主要测试在：

- `tests/test_voice_interaction.py`
- `tests/test_config.py`

覆盖场景包括：

- AEC reverse/capture stream 连接正确。
- residual echo gate 能挡掉高相关播放参考。
- 用户语音段开始后 residual echo gate 不再丢弃 chunk。
- TTS 播报文本结束后仍保留最近历史。
- 当前 TTS 文本和历史片段能过滤 ASR 回声。
- 显式打断词不会被文本回声过滤拦截。
- 播报后保护窗口内 transcript 不直接提交为空闲新任务。

建议修改语音链路后至少运行：

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_voice_interaction.py tests/test_config.py
```
