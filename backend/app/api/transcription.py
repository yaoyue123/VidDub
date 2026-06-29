"""
Transcription API endpoints.

Provides speech-to-text transcription using SiliconFlow or Whisper.
"""

import logging
import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from app.schemas import TranscriptionResponse
from app.services.transcriber.service import TranscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    """Transcribe an audio file to text.

    Accepts audio files (WAV, MP3, etc.) and returns transcribed text.
    Uses SiliconFlow API or local Whisper based on configuration.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Validate file type
    allowed_extensions = {".wav", ".mp3", ".opus", ".pcm", ".m4a", ".flac"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {allowed_extensions}"
        )

    # Save uploaded file temporarily
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Transcribe
        service = TranscriptionService()
        result = await service.transcribe(
            audio_path=temp_path,
            language=language,
        )

        return TranscriptionResponse(
            text=result.text,
            language=result.language,
            segments=[
                {
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                }
                for seg in result.segments
            ],
        )

    except Exception as e:
        logger.error("语音转文字失败: %s", e)
        raise HTTPException(status_code=500, detail="语音转文字失败，请稍后重试")

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.get("/providers")
async def list_providers():
    """List available transcription providers."""
    return {
        "providers": ["whisper", "siliconflow"],
        "default": "whisper",
    }
