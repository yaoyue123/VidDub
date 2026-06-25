"""Rule engine — evaluate ContentRules against video scores."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.core.database import async_session_factory
from app.models.content_rule import ContentRule
from app.models.video_score import VideoScore
from app.services.scoring.condition_evaluator import (
    evaluate_conditions,
    validate_conditions,
)
from app.services.scoring.scorer import score_video

logger = logging.getLogger(__name__)

# Template rule definitions
RULE_TEMPLATES = [
    {
        "name": "爆款优先",
        "weights": {"virality": 0.40, "translation": 0.20, "quality": 0.20,
                     "market": 0.10, "cost": 0.10},
        "conditions": [
            {"field": "view_count", "op": "gte", "value": 500000},
            {"field": "published_days_ago", "op": "lte", "value": 7},
        ],
        "max_results": 20,
        "description": "追求流量最大化：只看播放量>50万、7天内发布的热门视频",
    },
    {
        "name": "教育精品",
        "weights": {"virality": 0.15, "translation": 0.35, "quality": 0.25,
                     "market": 0.15, "cost": 0.10},
        "conditions": [
            {"field": "category", "op": "in", "value": ["education", "science"]},
            {"field": "duration_sec", "op": "between", "value": [300, 1500]},
        ],
        "max_results": 15,
        "description": "垂直深耕教育类：专注5-25分钟的教育/科普视频",
    },
    {
        "name": "科技快报",
        "weights": {"virality": 0.30, "translation": 0.25, "quality": 0.15,
                     "market": 0.20, "cost": 0.10},
        "conditions": [
            {"field": "category", "op": "in", "value": ["tech"]},
            {"field": "published_days_ago", "op": "lte", "value": 3},
            {"field": "duration_sec", "op": "lte", "value": 900},
        ],
        "max_results": 10,
        "description": "时效优先：3天内发布的科技类短视频",
    },
    {
        "name": "低风险搬运",
        "weights": {"virality": 0.20, "translation": 0.30, "quality": 0.20,
                     "market": 0.20, "cost": 0.10},
        "conditions": [
            {"field": "view_count", "op": "gte", "value": 10000},
            {"field": "language", "op": "eq", "value": "en"},
        ],
        "blacklist_keywords": ["political", "protest", "religion", "nsfw"],
        "max_results": 20,
        "description": "避免风险：排除政治/宗教敏感内容，只要英文视频",
    },
    {
        "name": "测试水温",
        "weights": {"virality": 0.20, "translation": 0.20, "quality": 0.20,
                     "market": 0.20, "cost": 0.20},
        "conditions": [
            {"field": "composite_score", "op": "gte", "value": 70},
        ],
        "max_results": 10,
        "description": "求稳：只看综合评分>70、制作成本低的高质量视频",
    },
]


async def evaluate_rule(
    rule: ContentRule,
    video_scores: list[VideoScore],
) -> list[dict[str, Any]]:
    """Evaluate a rule against a list of scored videos.

    Returns filtered + re-scored results, sorted by composite desc.
    """
    weights = json.loads(rule.weights)
    conditions = json.loads(rule.conditions) if rule.conditions else []
    whitelist = json.loads(rule.whitelist_channels or "[]")
    blacklist_kw = json.loads(rule.blacklist_keywords or "[]")
    blacklist_ch = json.loads(rule.blacklist_channels or "[]")

    results = []
    for vs in video_scores:
        # Apply whitelist
        if whitelist and vs.channel_id not in whitelist:
            continue

        # Apply blacklist (channels)
        if blacklist_ch and vs.channel_id in blacklist_ch:
            continue

        # Apply blacklist (keywords in title)
        if blacklist_kw:
            title_lower = vs.title.lower()
            if any(kw.lower() in title_lower for kw in blacklist_kw):
                continue

        # Parse metrics and score
        raw_metrics = json.loads(vs.raw_metrics) if vs.raw_metrics else {}

        # Apply conditions
        score_dict = {
            "virality_score": vs.virality_score,
            "translation_score": vs.translation_score,
            "quality_score": vs.quality_score,
            "market_score": vs.market_score,
            "cost_score": vs.cost_score,
            "composite_score": vs.composite_score,
            "category": vs.category,
        }

        if not evaluate_conditions(conditions, score_dict, raw_metrics):
            continue

        # Re-score with rule weights
        rescored = score_video(raw_metrics, weights=weights,
                               category=vs.category)
        results.append({
            "youtube_id": vs.youtube_id,
            "title": vs.title,
            "channel_name": vs.channel_name,
            "thumbnail_url": vs.thumbnail_url,
            "composite_score": rescored["composite_score"],
            "virality_score": rescored["virality_score"],
            "translation_score": rescored["translation_score"],
            "quality_score": rescored["quality_score"],
            "market_score": rescored["market_score"],
            "cost_score": rescored["cost_score"],
            "category": vs.category,
            "view_count": raw_metrics.get("view_count", 0),
            "duration_sec": raw_metrics.get("duration_sec", 0),
        })

    # Sort by composite desc, limit
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results[:rule.max_results]


async def test_rule(
    rule: ContentRule,
    sample_size: int = 50,
) -> dict[str, Any]:
    """Test a rule against recent video scores to preview results.

    Returns counts and sample matches for UI preview.
    """
    async with async_session_factory() as session:
        scores = (
            await session.execute(
                select(VideoScore)
                .order_by(VideoScore.scored_at.desc())
                .limit(sample_size),
            )
        ).scalars().all()

    matches = await evaluate_rule(rule, list(scores))

    return {
        "total_tested": len(scores),
        "total_matched": len(matches),
        "match_rate": round(len(matches) / max(len(scores), 1) * 100, 1),
        "matches": matches[:10],  # Preview first 10
    }


async def seed_rule_templates() -> None:
    """Seed template rules if they don't exist."""
    async with async_session_factory() as session:
        existing = (
            await session.execute(
                select(ContentRule).where(ContentRule.is_template == True),
            )
        ).scalars().all()

        if existing:
            logger.debug("%d template rules already exist", len(existing))
            return

        for i, tmpl in enumerate(RULE_TEMPLATES):
            rule = ContentRule(
                name=tmpl["name"],
                is_template=True,
                enabled=True,
                weights=json.dumps(tmpl["weights"], ensure_ascii=False),
                conditions=json.dumps(tmpl.get("conditions", []),
                                     ensure_ascii=False),
                blacklist_keywords=json.dumps(
                    tmpl.get("blacklist_keywords", []), ensure_ascii=False,
                ) if tmpl.get("blacklist_keywords") else None,
                max_results=tmpl.get("max_results", 20),
                sort_order=i,
            )
            session.add(rule)

        await session.commit()
        logger.info("Seeded %d rule templates", len(RULE_TEMPLATES))


def validate_rule(conditions: list[dict], weights: dict) -> tuple[bool, str]:
    """Validate rule syntax. Returns (is_valid, error_message)."""
    # Validate conditions
    ok, err = validate_conditions(conditions)
    if not ok:
        return False, err

    # Validate weights
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        return False, f"Weights must sum to 1.0 (got {total:.3f})"

    valid_dims = {"virality", "translation", "quality", "market", "cost"}
    for dim in weights:
        if dim not in valid_dims:
            return False, f"Unknown weight dimension: {dim}"

    return True, ""
