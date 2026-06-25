"""JSON condition parser + evaluator for the content rule engine.

Supported operators: eq, neq, gt, gte, lt, lte, in, not_in, between
Supported fields: view_count, like_count, duration_sec, published_days_ago,
  category, composite_score, virality_score, translation_score,
  quality_score, market_score, cost_score, has_captions, language,
  subscriber_count
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def evaluate_conditions(
    conditions: list[dict[str, Any]],
    score: dict[str, Any],
    metrics: dict[str, Any],
) -> bool:
    """Evaluate a list of conditions against a video's score+metrics.

    All conditions must pass (AND logic). Returns True if all pass.

    Args:
        conditions: List of condition dicts with field/op/value.
        score: Dict with virality_score, composite_score, etc.
        metrics: Dict with view_count, duration_sec, category, etc.

    Returns:
        True if all conditions pass.
    """
    if not conditions:
        return True

    for cond in conditions:
        if not _evaluate_one(cond, score, metrics):
            return False
    return True


def _evaluate_one(
    cond: dict[str, Any],
    score: dict[str, Any],
    metrics: dict[str, Any],
) -> bool:
    """Evaluate a single condition."""
    field = cond.get("field", "")
    op = cond.get("op", "eq")
    value = cond.get("value")

    # Resolve field value from score or metrics
    actual = _resolve_field(field, score, metrics)
    if actual is None:
        return False

    return _apply_op(actual, op, value)


def _resolve_field(
    field: str,
    score: dict[str, Any],
    metrics: dict[str, Any],
) -> Any:
    """Resolve a field name to its actual value."""
    # Score fields
    score_fields = {
        "composite_score", "virality_score", "translation_score",
        "quality_score", "market_score", "cost_score",
    }
    if field in score_fields:
        return score.get(field)

    # Metrics fields (direct mapping)
    if field in ("view_count", "like_count", "comment_count",
                  "duration_sec", "subscriber_count"):
        return float(metrics.get(field) or 0)

    if field == "category":
        return (score.get("category") or metrics.get("category") or "").lower()

    if field == "language":
        return (metrics.get("language") or "en").lower()

    if field == "has_captions":
        captions = metrics.get("has_captions")
        return captions is True or captions == "auto" or captions == "manual"

    if field == "published_days_ago":
        published = metrics.get("published_at")
        if not published:
            return None
        try:
            if isinstance(published, str):
                published = datetime.fromisoformat(
                    published.replace("Z", "+00:00"),
                )
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - published
            return delta.total_seconds() / 86400.0
        except (ValueError, AttributeError):
            return None

    logger.debug("Unknown condition field: %s", field)
    return None


def _apply_op(actual: Any, op: str, expected: Any) -> bool:
    """Apply a comparison operator."""
    try:
        if op == "eq":
            return actual == expected
        elif op == "neq":
            return actual != expected
        elif op == "gt":
            return float(actual) > float(expected)
        elif op == "gte":
            return float(actual) >= float(expected)
        elif op == "lt":
            return float(actual) < float(expected)
        elif op == "lte":
            return float(actual) <= float(expected)
        elif op == "in":
            if not isinstance(expected, list):
                return False
            return str(actual).lower() in [str(v).lower() for v in expected]
        elif op == "not_in":
            if not isinstance(expected, list):
                return True
            return str(actual).lower() not in [str(v).lower() for v in expected]
        elif op == "between":
            if not isinstance(expected, list) or len(expected) != 2:
                return False
            low, high = float(expected[0]), float(expected[1])
            return low <= float(actual) <= high
        else:
            logger.debug("Unknown operator: %s", op)
            return False
    except (TypeError, ValueError) as e:
        logger.debug("Condition evaluation failed: %s", e)
        return False


def validate_conditions(conditions: list[dict[str, Any]]) -> tuple[bool, str]:
    """Validate condition syntax. Returns (is_valid, error_message)."""
    valid_fields = {
        "view_count", "like_count", "duration_sec", "published_days_ago",
        "category", "composite_score", "virality_score", "translation_score",
        "quality_score", "market_score", "cost_score",
        "has_captions", "language", "subscriber_count",
    }
    valid_ops = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "between"}

    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            return False, f"Condition {i}: must be a dict"
        field = cond.get("field", "")
        op = cond.get("op", "")
        if field not in valid_fields:
            return False, f"Condition {i}: unknown field '{field}'"
        if op not in valid_ops:
            return False, f"Condition {i}: unknown op '{op}'"
        if "value" not in cond:
            return False, f"Condition {i}: missing 'value'"

    return True, ""
