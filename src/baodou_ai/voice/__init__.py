"""Voice interaction backends."""

from baodou_ai.voice.echo_cancellation import (
    EchoCancellationBridge,
    EchoCancellationConfig,
    WebRtcEchoCanceller,
    get_echo_cancellation_bridge,
)
from baodou_ai.voice.intent_classifier import VoiceIntentClassifier
from baodou_ai.voice.local_vad import LocalVadConfig, LocalVadEvent, LocalVadSegmenter
from baodou_ai.voice.qwen_asr import QwenRealtimeAsrClient, QwenRealtimeAsrSettings
from baodou_ai.voice.sherpa_keyword_spotter import (
    SherpaKeywordSpotter,
    SherpaKeywordSpotterSettings,
    WakeWordConfigurationError,
    WakeWordDependencyError,
    WakeWordHit,
    WakeWordPhrase,
)
from baodou_ai.voice.wake_word_engine import (
    WakeWordEngine,
    WakeWordEngineSettings,
    WakeWordEngineStatus,
)

__all__ = [
    "EchoCancellationBridge",
    "EchoCancellationConfig",
    "LocalVadConfig",
    "LocalVadEvent",
    "LocalVadSegmenter",
    "QwenRealtimeAsrClient",
    "QwenRealtimeAsrSettings",
    "SherpaKeywordSpotter",
    "SherpaKeywordSpotterSettings",
    "VoiceIntentClassifier",
    "WakeWordConfigurationError",
    "WakeWordDependencyError",
    "WakeWordEngine",
    "WakeWordEngineSettings",
    "WakeWordEngineStatus",
    "WakeWordHit",
    "WakeWordPhrase",
    "WebRtcEchoCanceller",
    "get_echo_cancellation_bridge",
]
