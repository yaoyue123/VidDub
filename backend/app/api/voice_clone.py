"""
Voice Clone API endpoints.

Provides voice cloning operations using SiliconFlow.
"""

import os
import shutil
import tempfile
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from app.services.voice_cloner.service import VoiceClonerService

router = APIRouter()


class VoiceCloneResponse(BaseModel):
    """Response model for voice cloning."""
    uri: str
    name: str


class VoiceListResponse(BaseModel):
    """Response model for voice listing."""
    voices: list[VoiceCloneResponse]


@router.post("", response_model=VoiceCloneResponse)
async def clone_voice(
    file: UploadFile = File(...),
    custom_name: str = Form(..., description="Custom name for the voice"),
    text: str = Form(..., description="Corresponding text content"),
):
    """Clone a voice from an audio file.

    Uploads an audio file to SiliconFlow to create a voice clone
    for use with TTS.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    # Validate file type
    allowed_extensions = {".mp3", ".wav", ".opus", ".pcm", ".m4a", ".flac"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {allowed_extensions}"
        )

    if not custom_name.strip():
        raise HTTPException(status_code=400, detail="Custom name cannot be empty")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Save uploaded file temporarily
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Clone voice
        service = VoiceClonerService()
        result = await service.clone_voice(
            audio_path=temp_path,
            custom_name=custom_name,
            text=text,
        )

        return VoiceCloneResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.get("", response_model=VoiceListResponse)
async def list_voices():
    """List available voice clones."""
    service = VoiceClonerService()
    voices = await service.list_voices()
    return VoiceListResponse(
        voices=[VoiceCloneResponse(**v) for v in voices]
    )


@router.get("/{name}", response_model=VoiceCloneResponse)
async def get_voice(name: str):
    """Get a voice clone by name."""
    service = VoiceClonerService()
    voice = await service.get_voice(name)

    if not voice:
        raise HTTPException(status_code=404, detail=f"Voice '{name}' not found")

    return VoiceCloneResponse(**voice)


@router.delete("/{name}")
async def delete_voice(name: str):
    """Delete a voice clone."""
    service = VoiceClonerService()
    deleted = await service.delete_voice(name)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Voice '{name}' not found")

    return {"message": f"Voice '{name}' deleted"}
