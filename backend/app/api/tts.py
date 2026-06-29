"""
TTS API endpoints.

Provides text-to-speech synthesis using SiliconFlow.
"""

import logging
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.tts_new.service import TTSService

logger = logging.getLogger(__name__)
router = APIRouter()


class TTSSynthesizeRequest(BaseModel):
    """Request model for TTS synthesis."""
    text: str = Field(..., description="Text to synthesize")
    voice: Optional[str] = Field(None, description="Voice ID (e.g., 'alex')")
    model: Optional[str] = Field(None, description="Model ID")
    speed: Optional[float] = Field(None, ge=0.25, le=4.0, description="Speech speed")
    gain: Optional[int] = Field(None, ge=-10, le=10, description="Volume gain dB")
    response_format: Optional[str] = Field(None, description="Output format (mp3/wav/opus)")
    sample_rate: Optional[int] = Field(None, description="Sample rate Hz")


class TTSVoiceResponse(BaseModel):
    """Response model for TTS voice."""
    id: str
    name: str


class TTSModelResponse(BaseModel):
    """Response model for TTS model."""
    id: str
    name: str


class TTSSynthesizeResponse(BaseModel):
    """Response model for TTS synthesis."""
    audio_path: str
    duration: float
    sample_rate: int
    format: str


@router.post("", response_model=TTSSynthesizeResponse)
async def synthesize_text(body: TTSSynthesizeRequest):
    """Synthesize text to audio.

    Converts text to speech using SiliconFlow TTS API.
    Returns audio file path with metadata.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if len(body.text) > 10000:
        raise HTTPException(
            status_code=400,
            detail="Text too long (max 10,000 characters)"
        )

    try:
        service = TTSService()

        # Create temp file for output
        temp_dir = tempfile.mkdtemp()
        output_filename = f"tts_output.{body.response_format or 'mp3'}"
        output_path = os.path.join(temp_dir, output_filename)

        result = await service.synthesize(
            text=body.text,
            output_path=output_path,
            voice=body.voice,
            model=body.model,
            speed=body.speed,
            gain=body.gain,
            response_format=body.response_format,
            sample_rate=body.sample_rate,
        )

        return TTSSynthesizeResponse(
            audio_path=result.audio_path,
            duration=result.duration,
            sample_rate=result.sample_rate,
            format=result.format,
        )

    except Exception as e:
        logger.error("TTS 语音合成失败: %s", e)
        raise HTTPException(status_code=500, detail="语音合成失败，请稍后重试")


@router.post("/stream")
async def synthesize_text_stream(body: TTSSynthesizeRequest):
    """Stream synthesized audio.

    Returns audio stream for real-time playback.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        service = TTSService()

        # Get format for content type
        response_format = body.response_format or "mp3"
        content_type_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "opus": "audio/opus",
            "pcm": "audio/pcm",
        }
        content_type = content_type_map.get(response_format, "audio/mpeg")

        async def audio_generator():
            async for chunk in service.synthesize_stream(
                text=body.text,
                voice=body.voice,
                model=body.model,
                speed=body.speed,
                gain=body.gain,
                response_format=response_format,
                sample_rate=body.sample_rate,
            ):
                yield chunk

        return StreamingResponse(
            audio_generator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename=tts_output.{response_format}"
            },
        )

    except Exception as e:
        logger.error("TTS 流式合成失败: %s", e)
        raise HTTPException(status_code=500, detail="语音流式合成失败，请稍后重试")


@router.get("/voices", response_model=list[TTSVoiceResponse])
async def list_voices():
    """List available TTS voices."""
    service = TTSService()
    voices = await service.get_available_voices()
    return [TTSVoiceResponse(**v) for v in voices]


@router.get("/models", response_model=list[TTSModelResponse])
async def list_models():
    """List available TTS models."""
    service = TTSService()
    models = await service.get_available_models()
    return [TTSModelResponse(**m) for m in models]
