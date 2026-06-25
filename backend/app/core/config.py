"""Unified application settings loaded from .env (single source of truth).

All API credentials and model defaults live here. DB Config table is ONLY for
UI-adjustable runtime parameters (download_dir, max_concurrent, etc.).
Service code MUST read credentials from this module, NOT from os.getenv() or DB Config.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "you2bili"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./data/you2bili.db"

    # ── SiliconFlow credentials (loaded from .env) ──
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # ── SiliconFlow model defaults ──
    siliconflow_tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    siliconflow_stt_model: str = "FunAudioLLM/SenseVoiceSmall"
    siliconflow_translate_model: str = "deepseek-ai/DeepSeek-V4-Flash"

    # ── Whisper local STT ──
    whisper_model: str = "tiny"
    whisper_language: str = "en"

    # ── Storage ──
    downloads_dir: str = "./downloads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
