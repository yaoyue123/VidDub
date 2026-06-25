"""Unit tests for Phase 15 rule engine."""
import json

import pytest

from app.services.scoring.condition_evaluator import (
    evaluate_conditions,
    validate_conditions,
    _evaluate_one,
    _apply_op,
)
from app.services.scoring.rule_engine import (
    validate_rule,
    RULE_TEMPLATES,
)


class TestConditionEvaluator:
    def test_eq(self):
        assert _apply_op(100, "eq", 100) is True
        assert _apply_op(100, "eq", 99) is False

    def test_neq(self):
        assert _apply_op(100, "neq", 99) is True
        assert _apply_op(100, "neq", 100) is False

    def test_gte_lte(self):
        assert _apply_op(100, "gte", 100) is True
        assert _apply_op(100, "gte", 99) is True
        assert _apply_op(100, "gte", 101) is False
        assert _apply_op(100, "lte", 100) is True
        assert _apply_op(100, "lte", 101) is True

    def test_gt_lt(self):
        assert _apply_op(100, "gt", 99) is True
        assert _apply_op(100, "gt", 100) is False
        assert _apply_op(100, "lt", 101) is True

    def test_in_not_in(self):
        assert _apply_op("tech", "in", ["tech", "education"]) is True
        assert _apply_op("news", "in", ["tech", "education"]) is False
        assert _apply_op("tech", "not_in", ["politics", "religion"]) is True
        assert _apply_op("politics", "not_in", ["politics"]) is False

    def test_between(self):
        assert _apply_op(500, "between", [100, 1000]) is True
        assert _apply_op(50, "between", [100, 1000]) is False
        assert _apply_op(2000, "between", [100, 1000]) is False

    def test_evaluate_single_condition(self):
        score = {"composite_score": 85.0, "category": "tech"}
        metrics = {"view_count": 500000, "duration_sec": 600}

        cond = {"field": "view_count", "op": "gte", "value": 100000}
        assert _evaluate_one(cond, score, metrics) is True

        cond = {"field": "view_count", "op": "lt", "value": 100000}
        assert _evaluate_one(cond, score, metrics) is False

    def test_evaluate_all_conditions_and(self):
        score = {"composite_score": 85.0, "category": "tech"}
        metrics = {"view_count": 500000, "duration_sec": 600}

        conditions = [
            {"field": "view_count", "op": "gte", "value": 100000},
            {"field": "category", "op": "in", "value": ["tech", "science"]},
        ]
        assert evaluate_conditions(conditions, score, metrics) is True

        conditions.append(
            {"field": "duration_sec", "op": "gt", "value": 1000},
        )
        assert evaluate_conditions(conditions, score, metrics) is False

    def test_empty_conditions(self):
        assert evaluate_conditions([], {}, {}) is True

    def test_category_condition(self):
        score = {"composite_score": 80, "category": "education"}
        metrics = {}
        cond = {"field": "category", "op": "in",
                "value": ["education", "science"]}
        assert _evaluate_one(cond, score, metrics) is True


class TestValidateConditions:
    def test_valid(self):
        conds = [{"field": "view_count", "op": "gte", "value": 10000}]
        ok, err = validate_conditions(conds)
        assert ok is True
        assert err == ""

    def test_invalid_field(self):
        conds = [{"field": "bogus_field", "op": "eq", "value": 1}]
        ok, err = validate_conditions(conds)
        assert ok is False
        assert "bogus_field" in err

    def test_invalid_op(self):
        conds = [{"field": "view_count", "op": "bogus", "value": 1}]
        ok, err = validate_conditions(conds)
        assert ok is False

    def test_missing_value(self):
        conds = [{"field": "view_count", "op": "gte"}]
        ok, err = validate_conditions(conds)
        assert ok is False
        assert "value" in err.lower()


class TestRuleTemplates:
    def test_five_templates(self):
        assert len(RULE_TEMPLATES) == 5

    def test_all_have_names(self):
        for tmpl in RULE_TEMPLATES:
            assert "name" in tmpl
            assert "weights" in tmpl

    def test_all_weights_sum_to_one(self):
        for tmpl in RULE_TEMPLATES:
            total = sum(tmpl["weights"].values())
            assert abs(total - 1.0) < 0.02, (
                f"{tmpl['name']} weights sum to {total}"
            )

    def test_all_have_valid_dimensions(self):
        valid = {"virality", "translation", "quality", "market", "cost"}
        for tmpl in RULE_TEMPLATES:
            for dim in tmpl["weights"]:
                assert dim in valid


class TestValidateRule:
    def test_valid_rule(self):
        conditions = [{"field": "view_count", "op": "gte", "value": 10000}]
        weights = {"virality": 0.3, "translation": 0.25, "quality": 0.2,
                    "market": 0.15, "cost": 0.1}
        ok, err = validate_rule(conditions, weights)
        assert ok is True

    def test_bad_weights(self):
        conditions = []
        weights = {"virality": 1.0, "translation": 0.5}
        ok, err = validate_rule(conditions, weights)
        assert ok is False
        assert "sum" in err.lower()

    def test_bad_conditions(self):
        conditions = [{"field": "bogus", "op": "eq", "value": 1}]
        weights = {"virality": 0.3, "translation": 0.25, "quality": 0.2,
                    "market": 0.15, "cost": 0.1}
        ok, err = validate_rule(conditions, weights)
        assert ok is False
