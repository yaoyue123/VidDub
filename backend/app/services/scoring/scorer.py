"""VideoScorer — five-dimension content scoring for YouTube→China reposting.

Each video receives five 0-100 scores weighted into a single composite.
Weights are adjustable per user preference.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default weights (sum to 1.0)
DEFAULT_WEIGHTS = {
    "virality": 0.30,
    "translation": 0.25,
    "quality": 0.20,
    "market": 0.15,
    "cost": 0.10,
}

SCORER_VERSION = "1.0"

# Bilibili hot zone mapping: YouTube category → Bilibili compatibility (0-100)
BILIBILI_MARKET_FIT: dict[str, float] = {
    "science": 95.0,
    "education": 95.0,
    "tech": 90.0,
    "gaming": 85.0,
    "fitness": 90.0,
    "music": 80.0,
    "entertainment": 65.0,
    "comedy": 55.0,
    "news": 50.0,
    "lifestyle": 60.0,
    "other": 50.0,
}

# Duration sweet spot: 5–20 min (minutes)
DURATION_MIN_OPTIMAL = 5 * 60
DURATION_MAX_OPTIMAL = 20 * 60


def score_video(
    metrics: dict[str, Any],
    *,
    weights: Optional[dict[str, float]] = None,
    category: Optional[str] = None,
) -> dict[str, Any]:
    """Score a video across all five dimensions.

    Args:
        metrics: Raw video data (views, likes, duration, published_at, etc.).
        weights: Optional custom dimension weights.
        category: Pre-classified content category (if available).

    Returns:
        Dict with all five scores + composite + raw metrics.
    """
    w = weights or DEFAULT_WEIGHTS
    _validate_weights(w)

    virality = _score_virality(metrics)
    translation = _score_translation(metrics)
    quality = _score_quality(metrics)
    market = _score_market(metrics, category)
    cost = _score_cost(metrics)

    composite = (
        w["virality"] * virality
        + w["translation"] * translation
        + w["quality"] * quality
        + w["market"] * market
        + w["cost"] * cost
    )

    return {
        "virality_score": round(virality, 1),
        "translation_score": round(translation, 1),
        "quality_score": round(quality, 1),
        "market_score": round(market, 1),
        "cost_score": round(cost, 1),
        "composite_score": round(composite, 1),
        "weights_used": json.dumps(w),
        "raw_metrics": json.dumps(metrics, ensure_ascii=False),
        "category": category,
    }


def _validate_weights(weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Weights must sum to 1.0 (got {total:.3f})")


# ── Dimension 1: Virality (传播潜力, 0-100) ──

def _score_virality(metrics: dict[str, Any]) -> float:
    """Score based on view velocity, engagement, and recency.

    Components:
    - View velocity (40%): how fast views are accumulating
    - Engagement rate (30%): likes/comments per view
    - Recency boost (20%): penalty for older videos
    - Like/comment ratio (10%): quality signal
    """
    views = float(metrics.get("view_count") or 0)
    likes = float(metrics.get("like_count") or 0)
    comments = float(metrics.get("comment_count") or 0)
    published = metrics.get("published_at")

    if views <= 0:
        return 0.0

    # 1. View velocity (40 points)
    hours_since_pub = _hours_since(published) if published else 168  # default 1 week
    hours_since_pub = max(hours_since_pub, 1)  # avoid division by zero
    velocity = views / hours_since_pub

    # Score: 10K+ views/hour = 40pts, linear below
    velocity_score = min(40.0, (velocity / 10000) * 40.0)

    # 2. Engagement rate (30 points)
    engagement = (likes + comments * 2) / views  # comments weighted 2x
    engagement = min(engagement, 0.20)  # cap at 20%
    engagement_score = (engagement / 0.20) * 30.0

    # 3. Recency boost (20 points)
    if hours_since_pub <= 24:
        recency_score = 20.0
    elif hours_since_pub <= 72:
        recency_score = 15.0
    elif hours_since_pub <= 168:  # 1 week
        recency_score = 10.0
    elif hours_since_pub <= 720:  # 30 days
        recency_score = 5.0
    else:
        recency_score = 0.0

    # 4. Like ratio (10 points) — among engaged viewers, what % like it
    total_engagement = likes + comments
    if total_engagement > 0:
        like_ratio = likes / total_engagement
        like_score = min(10.0, like_ratio * 10.0)
    else:
        like_score = 5.0  # neutral when data missing

    return velocity_score + engagement_score + recency_score + like_score


# ── Dimension 2: Translation Suitability (翻译适配度, 0-100) ──

def _score_translation(metrics: dict[str, Any]) -> float:
    """Score how suitable this video is for Chinese translation + dubbing.

    Components:
    - Has captions (25 points): auto-captions 15, manual 25, none 0
    - Speaker count (25 points): 1 speaker=perfect, 2-3=ok, 4+=hard
    - Duration fit (25 points): very short/long harder to dub well
    - Language clarity (25 points): English=preferred, other=reduced
    """
    score = 0.0

    # 1. Captions availability (25 pts)
    captions = metrics.get("has_captions")
    if captions is True:
        score += 25.0
    elif captions == "auto":
        score += 15.0
    else:
        score += 5.0  # no captions → need Whisper anyway, but adds work

    # 2. Speaker count inverse (25 pts)
    speaker_count = int(metrics.get("speaker_count") or 1)
    if speaker_count <= 1:
        score += 25.0
    elif speaker_count <= 2:
        score += 18.0
    elif speaker_count <= 3:
        score += 10.0
    else:
        score += 3.0

    # 3. Duration suitability (25 pts)
    duration = float(metrics.get("duration_sec") or 0)
    if DURATION_MIN_OPTIMAL <= duration <= DURATION_MAX_OPTIMAL:
        score += 25.0
    elif duration < 60:  # < 1 min
        score += 5.0
    elif duration < DURATION_MIN_OPTIMAL:
        score += 18.0
    elif duration <= 3600:  # up to 1 hour
        score += 15.0
    else:
        score += 5.0

    # 4. Language clarity (25 pts) — English is easiest to translate well
    lang = (metrics.get("language") or "").lower()
    if lang == "en" or lang.startswith("en"):
        score += 25.0
    elif lang in ("ja", "ko"):  # Japanese/Korean also well-supported
        score += 15.0
    else:
        score += 8.0

    return score


# ── Dimension 3: Content Quality (内容质量, 0-100) ──

def _score_quality(metrics: dict[str, Any]) -> float:
    """Score content quality based on duration, authority, and presentation.

    Components:
    - Duration sweet spot (40 points): 5-20 min is optimal
    - View signal (30 points): higher views suggest quality content
    - Title quality (20 points): length, no clickbait patterns
    - Channel consistency (10 points): established channels preferred
    """
    score = 0.0

    # 1. Duration sweet spot (40 pts)
    duration = float(metrics.get("duration_sec") or 0)
    if DURATION_MIN_OPTIMAL <= duration <= DURATION_MAX_OPTIMAL:
        score += 40.0
    elif 60 <= duration < DURATION_MIN_OPTIMAL:
        # 1-5 min: good but short
        ratio = (duration - 60) / (DURATION_MIN_OPTIMAL - 60)
        score += 20.0 + 20.0 * ratio
    elif DURATION_MAX_OPTIMAL < duration <= 3600:
        # 20 min - 1 hour: declining quality for reposting
        ratio = 1.0 - (duration - DURATION_MAX_OPTIMAL) / (
            3600 - DURATION_MAX_OPTIMAL
        )
        score += 40.0 * max(ratio, 0.1)
    else:
        score += 5.0

    # 2. View signal (30 pts) — log scale for fairness
    views = float(metrics.get("view_count") or 0)
    if views >= 1_000_000:
        score += 30.0
    elif views >= 100_000:
        score += 24.0
    elif views >= 10_000:
        score += 16.0
    elif views >= 1_000:
        score += 8.0
    else:
        score += 2.0

    # 3. Title quality (20 pts)
    title = (metrics.get("title") or "").strip()
    title_len = len(title)
    if 20 <= title_len <= 100:
        score += 20.0
    elif 10 <= title_len <= 150:
        score += 12.0
    else:
        score += 5.0
    # Penalize obvious clickbait
    clickbait_markers = [
        "!!!", "??", "YOU WON'T BELIEVE", "SHOCKING", "GONE WRONG",
    ]
    title_upper = title.upper()
    for marker in clickbait_markers:
        if marker in title_upper:
            score -= 5.0
            break

    # 4. Channel authority (10 pts) — subscriber proxy
    subs = float(metrics.get("subscriber_count") or 0)
    if subs >= 1_000_000:
        score += 10.0
    elif subs >= 100_000:
        score += 7.0
    elif subs >= 10_000:
        score += 4.0
    else:
        score += 1.0

    return max(0.0, min(100.0, score))


# ── Dimension 4: Chinese Market Fit (中文市场潜力, 0-100) ──

def _score_market(
    metrics: dict[str, Any], category: Optional[str] = None,
) -> float:
    """Score how well this content fits Chinese platforms (Bilibili, Xigua).

    Uses a category-to-market-fit lookup table. Unknown categories get a
    neutral score.
    """
    cat = (category or metrics.get("category") or "").lower()
    base = BILIBILI_MARKET_FIT.get(cat, 50.0)

    # Bonus for China-related content
    title = (metrics.get("title") or "").lower()
    tags = " ".join(metrics.get("tags") or [])
    all_text = f"{title} {tags}".lower()
    china_markers = [
        "china", "chinese", "beijing", "shanghai", "mandarin",
        "中国", "中文", "华语",
    ]
    if any(m in all_text for m in china_markers):
        base = min(100.0, base + 15.0)

    # Penalize content likely to trigger Chinese content moderation
    risk_markers = ["political", "protest", "religion", "nsfw", "sensitive"]
    if any(m in all_text for m in risk_markers):
        base = max(5.0, base - 30.0)

    return max(0.0, min(100.0, base))


# ── Dimension 5: Production Cost (制作成本, 0-100, HIGHER = easier/cheaper) ──

def _score_cost(metrics: dict[str, Any]) -> float:
    """Score how easy/cheap this video is to process.

    HIGHER score = LOWER cost. Invert in composite if needed.

    Components:
    - Has captions (30 points): reduces Whisper dependency
    - Single speaker (25 points): no voice cloning needed
    - Visual content (25 points): less TTS work
    - Clean audio (20 points): less background separation work
    """
    score = 0.0

    # 1. Captions (30 pts)
    captions = metrics.get("has_captions")
    if captions is True:
        score += 30.0
    elif captions == "auto":
        score += 18.0
    else:
        score += 0.0

    # 2. Speaker count (25 pts)
    speaker_count = int(metrics.get("speaker_count") or 1)
    score += max(0.0, 25.0 - (speaker_count - 1) * 8.0)

    # 3. Visual content type (25 pts)
    visual_categories = {"fitness", "animation", "gaming", "music"}
    cat = (metrics.get("category") or "").lower()
    if cat in visual_categories:
        score += 25.0  # Minimal dubbing needed
    elif cat in ("education", "science", "tech"):
        score += 18.0  # Structured speech, easier to dub
    else:
        score += 10.0

    # 4. Clean audio guess (20 pts)
    # High production value channels tend to have cleaner audio
    subs = float(metrics.get("subscriber_count") or 0)
    if subs >= 500_000:
        score += 20.0
    elif subs >= 50_000:
        score += 12.0
    else:
        score += 5.0

    return max(0.0, min(100.0, score))


# ── Helpers ──

def _hours_since(published_at: Any) -> float:
    """Calculate hours since publication."""
    if isinstance(published_at, str):
        try:
            published_at = datetime.fromisoformat(
                published_at.replace("Z", "+00:00"),
            )
        except (ValueError, AttributeError):
            return 168.0  # default to 1 week

    if not isinstance(published_at, datetime):
        return 168.0

    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    delta = now - published_at
    return max(0.0, delta.total_seconds() / 3600.0)
