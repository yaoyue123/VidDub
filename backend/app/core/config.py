"""Unified application settings loaded from .env (single source of truth).

Only env-level configuration lives here:
- API credentials (keys, base URLs)
- Deployment-scoped defaults (whisper model, directories)
- App metadata

Model selection defaults (TTS models, STT models, translation models) live in
the DB Config table so they can be adjusted via the Settings UI at runtime.
Service code MUST read credentials from this module, NOT from os.getenv().
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    app_name: str = "viddub"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./data/viddub.db"

    # ── SiliconFlow credentials (loaded from .env) ──
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # ── Whisper local STT (deployment-scoped default; DB Config can override) ──
    whisper_model: str = "tiny"
    whisper_language: str = "en"

    # ── Storage ──
    # NOTE: This is ONLY a startup fallback for get_download_dir() in storage.py.
    # The runtime source of truth is the DB Config `download_dir` key, cached in
    # storage.py at startup and settable via the Settings UI. Do not read this
    # field directly in service code — always call get_download_dir().
    downloads_dir: str = "./downloads"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
