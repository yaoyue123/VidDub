"""SiliconFlow API namespace (P4-10).

统一封装 SiliconFlow 云端 API：
- client: HTTP + tenacity 重试
- translate: Qwen2.5-7B-Instruct 中英翻译（滑窗上下文）
- tts: CosyVoice2-0.5B 语音合成

注意：STT 改用本地 Whisper（见 ADDENDUM D-17），不在此命名空间。
"""

from app.services.siliconflow.client import (
    get_api_key,
    get_async_client,
    sf_post,
    sf_post_bytes,
)
from app.services.siliconflow.translate import translate_segments, translate_text

__all__ = [
    "get_api_key",
    "get_async_client",
    "sf_post",
    "sf_post_bytes",
    "translate_segments",
    "translate_text",
]
