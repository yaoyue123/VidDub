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


# ── Rules ──

class RuleResponse(BaseModel):
    id: Optional[int] = None
    name: str
    enabled: bool = True
    is_template: bool = False
    weights: dict[str, float] = {}
    conditions: list[dict] = []
    whitelist_channels: list[str] = []
    blacklist_keywords: list[str] = []
    blacklist_channels: list[str] = []
    max_results: int = 20
    auto_create_dub: bool = False
    sort_order: int = 100
    last_evaluated_at: Optional[str] = None


class RuleListResponse(BaseModel):
    items: list[RuleResponse]
    total: int


class RuleEvaluateResponse(BaseModel):
    rule_id: int
    rule_name: str
    total_scored: int
    total_matched: int
    matches: list


# ── Analytics ──

class PerformanceLogResponse(BaseModel):
    id: Optional[int] = None
    video_id: int
    platform: str
    predicted_score: Optional[float] = None
    actual_score: Optional[float] = None
    score_accuracy: Optional[float] = None
    platform_views: Optional[int] = None
    platform_likes: Optional[int] = None
    logged_at: Optional[str] = None


class PerformanceDetailResponse(BaseModel):
    video_id: int
    logs: list[PerformanceLogResponse]


class TopPerformerResponse(BaseModel):
    items: list


class PerformanceReportResponse(BaseModel):
    period: str
    summary: dict
    top_performers: list[dict]
    accuracy_interpretation: str
