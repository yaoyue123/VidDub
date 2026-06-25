"""Phase 15: Content rule API endpoints."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update as sql_update

from app.core.database import get_db, async_session_factory
from app.models.content_rule import ContentRule

logger = logging.getLogger(__name__)
router = APIRouter()


class RuleCreate(BaseModel):
    name: str
    weights: dict[str, float]
    conditions: list[dict] = []
    whitelist_channels: Optional[list[str]] = None
    blacklist_keywords: Optional[list[str]] = None
    blacklist_channels: Optional[list[str]] = None
    max_results: int = 20
    auto_create_dub: bool = False


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    weights: Optional[dict[str, float]] = None
    conditions: Optional[list[dict]] = None
    whitelist_channels: Optional[list[str]] = None
    blacklist_keywords: Optional[list[str]] = None
    blacklist_channels: Optional[list[str]] = None
    max_results: Optional[int] = None
    auto_create_dub: Optional[bool] = None


@router.get("")
async def list_rules(db=Depends(get_db)):
    """List all rules (templates + custom), ordered by sort_order."""
    result = await db.execute(
        select(ContentRule).order_by(ContentRule.sort_order.asc()),
    )
    rules = result.scalars().all()
    return {"items": [_rule_to_dict(r) for r in rules], "total": len(rules)}


@router.post("")
async def create_rule(body: RuleCreate, db=Depends(get_db)):
    """Create a custom rule."""
    from app.services.scoring.rule_engine import validate_rule
    ok, err = validate_rule(body.conditions, body.weights)
    if not ok:
        raise HTTPException(status_code=400, detail=err)

    rule = ContentRule(
        name=body.name,
        is_template=False,
        enabled=True,
        weights=json.dumps(body.weights, ensure_ascii=False),
        conditions=json.dumps(body.conditions, ensure_ascii=False),
        whitelist_channels=json.dumps(
            body.whitelist_channels, ensure_ascii=False,
        ) if body.whitelist_channels else None,
        blacklist_keywords=json.dumps(
            body.blacklist_keywords, ensure_ascii=False,
        ) if body.blacklist_keywords else None,
        blacklist_channels=json.dumps(
            body.blacklist_channels, ensure_ascii=False,
        ) if body.blacklist_channels else None,
        max_results=body.max_results,
        auto_create_dub=body.auto_create_dub,
        sort_order=100,  # Custom rules after templates
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.put("/{rule_id}")
async def update_rule(rule_id: int, body: RuleUpdate, db=Depends(get_db)):
    """Update a rule."""
    rule = await db.get(ContentRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if body.name is not None:
        rule.name = body.name
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.weights is not None:
        from app.services.scoring.rule_engine import validate_rule
        ok, err = validate_rule(
            json.loads(rule.conditions) if rule.conditions else [],
            body.weights,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=err)
        rule.weights = json.dumps(body.weights, ensure_ascii=False)
    if body.conditions is not None:
        rule.conditions = json.dumps(body.conditions, ensure_ascii=False)
    if body.whitelist_channels is not None:
        rule.whitelist_channels = json.dumps(
            body.whitelist_channels, ensure_ascii=False,
        )
    if body.blacklist_keywords is not None:
        rule.blacklist_keywords = json.dumps(
            body.blacklist_keywords, ensure_ascii=False,
        )
    if body.blacklist_channels is not None:
        rule.blacklist_channels = json.dumps(
            body.blacklist_channels, ensure_ascii=False,
        )
    if body.max_results is not None:
        rule.max_results = body.max_results
    if body.auto_create_dub is not None:
        rule.auto_create_dub = body.auto_create_dub

    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db=Depends(get_db)):
    """Delete a rule (templates cannot be deleted)."""
    rule = await db.get(ContentRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.is_template:
        raise HTTPException(status_code=400, detail="Cannot delete template rules")
    await db.delete(rule)
    await db.commit()
    return {"ok": True}


@router.post("/{rule_id}/evaluate")
async def evaluate_rule_endpoint(
    rule_id: int,
    limit: int = Query(default=100, le=500),
    db=Depends(get_db),
):
    """Evaluate a rule against all scored videos, return matches."""
    rule = await db.get(ContentRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    from app.models.video_score import VideoScore
    from app.services.scoring.rule_engine import evaluate_rule as eval_rule

    scores = (
        await db.execute(
            select(VideoScore)
            .order_by(VideoScore.composite_score.desc())
            .limit(limit),
        )
    ).scalars().all()

    matches = await eval_rule(rule, list(scores))

    assert rule.id is not None
    await db.execute(
        sql_update(ContentRule)
        .where(ContentRule.id == rule_id)
        .values(last_evaluated_at=datetime.now(timezone.utc)),
    )
    await db.commit()

    return {
        "rule_id": rule_id,
        "rule_name": rule.name,
        "total_scored": len(scores),
        "total_matched": len(matches),
        "matches": matches,
    }


@router.post("/{rule_id}/test")
async def test_rule_endpoint(
    rule_id: int,
    db=Depends(get_db),
):
    """Test a rule against 50 recent videos, showing preview results."""
    rule = await db.get(ContentRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    from app.services.scoring.rule_engine import test_rule
    return await test_rule(rule, sample_size=50)


@router.post("/{rule_id}/duplicate")
async def duplicate_rule(rule_id: int, db=Depends(get_db)):
    """Duplicate a rule as a starting point for customization."""
    rule = await db.get(ContentRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    new_rule = ContentRule(
        name=f"{rule.name} (副本)",
        is_template=False,
        enabled=True,
        weights=rule.weights,
        conditions=rule.conditions,
        whitelist_channels=rule.whitelist_channels,
        blacklist_keywords=rule.blacklist_keywords,
        blacklist_channels=rule.blacklist_channels,
        max_results=rule.max_results,
        auto_create_dub=rule.auto_create_dub,
        sort_order=200,
    )
    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)
    return _rule_to_dict(new_rule)


def _rule_to_dict(rule: ContentRule) -> dict:
    """Convert ContentRule to API response dict."""
    return {
        "id": rule.id,
        "name": rule.name,
        "enabled": rule.enabled,
        "is_template": rule.is_template,
        "weights": json.loads(rule.weights),
        "conditions": json.loads(rule.conditions) if rule.conditions else [],
        "whitelist_channels": json.loads(
            rule.whitelist_channels,
        ) if rule.whitelist_channels else [],
        "blacklist_keywords": json.loads(
            rule.blacklist_keywords,
        ) if rule.blacklist_keywords else [],
        "blacklist_channels": json.loads(
            rule.blacklist_channels,
        ) if rule.blacklist_channels else [],
        "max_results": rule.max_results,
        "auto_create_dub": rule.auto_create_dub,
        "sort_order": rule.sort_order,
        "last_evaluated_at": (
            rule.last_evaluated_at.isoformat()
            if rule.last_evaluated_at else None
        ),
    }
