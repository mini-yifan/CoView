# Voice Interaction

CoView voice mode is designed for natural desktop collaboration: wake it, speak a task, interrupt while it is working, and let it respond through speech.

## Main Flow

1. Local wake-word detection listens for `你好彤彤` or `hello Lulu`.
2. The floating panel opens and shows the voice indicator.
3. Microphone input passes through local VAD and optional WebRTC echo cancellation.
4. `QwenRealtimeAsrClient` sends audio to DashScope realtime ASR and receives transcripts.
5. If CoView is idle, a valid transcript becomes a new desktop task.
6. If CoView is busy or speaking, `VoiceIntentClassifier` classifies the transcript as `stop`, `new_task`, or `ignore`.
7. The desktop agent observes, acts, and reports progress.
8. `CosyVoiceTTS` speaks progress and final results.

## Commands

| Purpose | Default commands |
| --- | --- |
| Wake word | `你好彤彤`, `hello Lulu` |
| Quit CoView by voice | `exit program`, `quit app`, or similar `close/exit/quit program/app` commands |
| Chinese quit command | `退出程序` |
| Dismiss while idle | Chinese: `退下吧`; English dismissal is represented as `dismiss` in the flow diagram |

Wake words can be changed under `wake_word_config.phrases`.

## Runtime Components

- `src/baodou_ai/voice/wake_word_engine.py`: wake-word lifecycle.
- `src/baodou_ai/voice/sherpa_keyword_spotter.py`: sherpa-onnx keyword spotting.
- `src/baodou_ai/voice/qwen_asr.py`: DashScope Qwen realtime ASR client, VAD, and audio boundaries.
- `src/baodou_ai/voice/echo_cancellation.py`: optional WebRTC acoustic echo cancellation bridge.
- `src/baodou_ai/voice/intent_classifier.py`: barge-in classification.
- `src/baodou_ai/gui/floating/voice_controller.py`: GUI-side voice interaction lifecycle.
- `src/baodou_ai/gui/floating/tts_controller.py`: GUI-side TTS state.
- `src/baodou_ai/tts/cosyvoice.py`: speech output.

## Echo Cancellation

WebRTC echo cancellation depends on `aec-audio-processing`, which is installed only on Python 3.11+ by the current project markers. If it is unavailable, CoView can still run voice input, but TTS echo filtering may be weaker.

