"""
Seed default (UI-adjustable) configuration values into the database on first startup.

BOUNDARY (v5.0 Phase 3):
- Settings (.env) = env-level config (API keys, base URLs, deployment defaults like whisper model)
- DB Config (this table) = UI-adjustable runtime parameters (model selection, TTS voices, pipeline params)

IMPORTANT: API credentials (keys, base URLs) live in Settings/.env — NOT here.
This table is ONLY for runtime parameters users adjust via the Settings UI.
"""

import logging
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import Config

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    # ── Download ──
    "download_dir": {
        "value": "./downloads",
        "description": "视频下载目录",
    },
    "max_resolution": {
        "value": "1080",
        "description": "最大下载分辨率 (720/1080/2160)",
    },
    "max_concurrent_downloads": {
        "value": "3",
        "description": "最大并发下载数",
    },
    "max_results_per_search": {
        "value": "20",
        "description": "每次搜索最大返回数",
    },
    "yt_dlp_cookies": {
        "value": "",
        "description": "yt-dlp Cookie 文件路径 (可选)",
    },
    # ── Target language ──
    "target_language": {
        "value": "zh",
        "description": "翻译目标语言代码",
    },
    # ── STT backend ──
    "transcription_backend": {
        "value": "whisper",
        "description": "语音转写后端 (whisper/siliconflow)",
    },
    "transcription_model": {
        "value": "FunAudioLLM/SenseVoiceSmall",
        "description": "硅基流动转写模型",
    },
    # ── Translation ──
    "translation_backend": {
        "value": "siliconflow",
        "description": "翻译后端 (siliconflow/google)",
    },
    "translation_model": {
        "value": "deepseek-ai/DeepSeek-V4-Flash",
        "description": "翻译模型名",
    },
    "translation_context_window": {
        "value": "2",
        "description": "翻译滑窗上下文段数",
    },
    # ── TTS ──
    "tts_backend": {
        "value": "siliconflow",
        "description": "语音合成后端 (siliconflow/edge-tts)",
    },
    "tts_model": {
        "value": "FunAudioLLM/CosyVoice2-0.5B",
        "description": "语音合成模型",
    },
    "tts_voice": {
        "value": "FunAudioLLM/CosyVoice2-0.5B:alex",
        "description": "默认音色",
    },
    "tts_voice_simple": {
        "value": "anna",
        "description": "TTS 默认音色（自动拼 model:voice 前缀）",
    },
    "tts_speed": {
        "value": "1.0",
        "description": "语速 (0.25-4.0)",
    },
    "tts_gain": {
        "value": "0",
        "description": "音量增益 dB (-10 to 10)",
    },
    "tts_format": {
        "value": "mp3",
        "description": "输出格式 (mp3/wav/opus/pcm)",
    },
    "tts_sample_rate": {
        "value": "32000",
        "description": "采样率 Hz",
    },
    # ── Voice cloning ──
    "voice_clone_enabled": {
        "value": "false",
        "description": "开启音色克隆：自动从原视频提取说话人音色进行 TTS 克隆",
    },
    "extract_voice_sample_during_transcribe": {
        "value": "false",
        "description": "转写阶段提前提取音色样本（无需等待合成阶段）",
    },
    # ── Dubbing pipeline ──
    "atempo_min": {
        "value": "0.7",
        "description": "atempo 调速下限（<则 pad 静音）",
    },
    "atempo_max": {
        "value": "1.5",
        "description": "atempo 调速上限（>则 trim 截断）",
    },
    # ── Upload / Platform ──
    "default_upload_platform": {
        "value": "bilibili",
        "description": "默认上传平台 (bilibili/douyin等)",
    },
    "upload_default_tags": {
        "value": "技术,YouTube,搬运",
        "description": "默认上传标签 (逗号分隔)",
    },
    "upload_default_tid": {
        "value": "122",
        "description": "Bilibili 默认分区 ID (122=野生技术协会)",
    },
    # ── Publish ──
    "auto_publish_enabled": {
        "value": "true",
        "description": "配音完成后是否自动发布到平台 (true/false)",
    },
    "bilibili_default_category": {
        "value": "122",
        "description": "哔哩哔哩默认分区 tid (122=野生技术协会)",
    },
    "publish_default_tags": {
        "value": "搬运,英语学习,翻译",
        "description": "发布默认标签 (逗号分隔，最多 10 个)",
    },
    "publish_retry_max": {
        "value": "3",
        "description": "发布失败最大重试次数",
    },
    "publish_upload_timeout_sec": {
        "value": "600",
        "description": "视频上传 + 处理最长等待秒数 (默认 10 分钟)",
    },
    # ── AI Title ──
    "title_generator_enabled": {
        "value": "true",
        "description": "AI 标题/标签自动生成开关 (true/false)",
    },
    "title_generator_candidate_count": {
        "value": "5",
        "description": "AI 候选标题数量 (默认 5)",
    },
    "title_generator_tag_count": {
        "value": "8",
        "description": "AI 候选标签数量 (默认 8)",
    },
    # ── Subtitle ──
    "subtitle_enabled": {
        "value": "true",
        "description": "合成视频时是否烧录中文字幕（true/false）",
    },
    "subtitle_font_size": {
        "value": "20",
        "description": "字幕字体大小 (12-48)",
    },
    "subtitle_position": {
        "value": "bottom",
        "description": "字幕位置 (bottom/top)",
    },
    # ── Channel Scanner ──
    "scan_max_concurrent": {
        "value": "3",
        "description": "频道扫描最大并发数",
    },
    "scan_default_interval_hours": {
        "value": "6",
        "description": "频道默认扫描间隔小时数 (1/3/6/12/24)",
    },
}


async def seed_default_config(db: AsyncSession) -> None:
    """Insert default config values if they don't exist."""
    result = await db.execute(select(func.count(Config.id)))
    count = result.scalar() or 0
    if count > 0:
        logger.debug("Config already seeded (%d entries), skipping", count)
        return

    for key, cfg in DEFAULT_CONFIGS.items():
        db.add(Config(
            key=key,
            value=cfg["value"],
            description=cfg["description"],
        ))

    await db.flush()
    logger.info("Seeded %d default config entries", len(DEFAULT_CONFIGS))
