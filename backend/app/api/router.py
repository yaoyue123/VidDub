from fastapi import APIRouter

from app.api.videos import router as videos_router
from app.api.tasks import router as tasks_router
from app.api.config import router as config_router
from app.api.stats import router as stats_router
from app.api.discovery import router as discovery_router
from app.api.subtitles import router as subtitles_router
from app.api.transcription import router as transcription_router
from app.api.tts import router as tts_router
from app.api.voice_clone import router as voice_clone_router
from app.api.dub import router as dub_router
from app.api.platform import router as platform_router
from app.api.publish import router as publish_router
from app.api.title import router as title_router
from app.api.channels import router as channels_router
from app.api.export import router as export_router
api_router = APIRouter()
api_router.include_router(videos_router, prefix="/api/videos", tags=["videos"])
api_router.include_router(tasks_router, prefix="/api/tasks", tags=["tasks"])
api_router.include_router(config_router, prefix="/api/config", tags=["config"])
api_router.include_router(stats_router, prefix="/api/stats", tags=["stats"])
api_router.include_router(discovery_router, prefix="/api/discovery", tags=["discovery"])
api_router.include_router(subtitles_router, prefix="/api/subtitles", tags=["subtitles"])
api_router.include_router(transcription_router, prefix="/api/transcription", tags=["transcription"])
api_router.include_router(tts_router, prefix="/api/tts", tags=["tts"])
api_router.include_router(voice_clone_router, prefix="/api/voice-clone", tags=["voice-clone"])
api_router.include_router(dub_router, prefix="/api/dub", tags=["dub"])
api_router.include_router(platform_router, prefix="/api/platform", tags=["platform"])
api_router.include_router(publish_router, prefix="/api/publish", tags=["publish"])
api_router.include_router(title_router, prefix="/api/title", tags=["title"])
api_router.include_router(channels_router, prefix="/api/channels", tags=["channels"])
api_router.include_router(export_router, prefix="/api/export", tags=["export"])
