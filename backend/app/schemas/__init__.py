from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Video ──

class VideoResponse(BaseModel):
    id: int
    youtube_url: str
    youtube_id: str
    title: str
    channel: str
    duration: Optional[int] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    status: str = "pending"
    filepath: Optional[str] = None
    dubbed_filepath: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VideoListResponse(BaseModel):
    total: int
    items: list[VideoResponse]


class VideoStatusUpdate(BaseModel):
    status: str


# ── Task ──

class TaskResponse(BaseModel):
    id: int
    video_id: int
    type: str
    status: str = "pending"
    progress: float = 0.0
    message: Optional[str] = None
    error_msg: Optional[str] = None
    # v3.2: 从关联 Video 表填充的显示字段
    video_title: Optional[str] = None
    video_thumbnail_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]


# ── Config ──

class ConfigResponse(BaseModel):
    id: int
    key: str
    value: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}


class ConfigUpdateItem(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    configs: list[ConfigUpdateItem]


# ── Stats ──

class StatsResponse(BaseModel):
    total_videos: int = 0
    status_counts: dict[str, int] = {}
    total_tasks: int = 0


# ── Transcription ──

class TranscriptionSegmentResponse(BaseModel):
    id: int
    start: float
    end: float
    text: str


class TranscriptionResponse(BaseModel):
    text: str
    language: Optional[str] = None
    segments: list[TranscriptionSegmentResponse] = []


