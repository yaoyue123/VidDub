# Phase 15: 自定义规则引擎

**Goal:** 用户自定义筛选规则——可视化条件组合、权重调整、白名单/黑名单、预设模板。让每个人都有自己的搬运策略。

**Dependencies:** Phase 13 (scoring), Phase 14 (discovery)

**Estimated effort:** 5-7 hrs

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Rule Engine                         │
│                                                     │
│  ContentRule (DB)                                   │
│  ┌──────────────────────────────────────────────┐   │
│  │ name, enabled, conditions[], weights{}        │   │
│  │ whitelist[], blacklist[], auto_dub: bool      │   │
│  └──────────────────────────────────────────────┘   │
│           │                                         │
│           ▼                                         │
│  ┌──────────────────────────────────────────────┐   │
│  │         RuleEvaluator                        │   │
│  │                                              │   │
│  │  evaluate(rule, videos[]) → filtered[]       │   │
│  │  1. Score each video (with rule weights)     │   │
│  │  2. Apply conditions (AND/OR logic)          │   │
│  │  3. Apply whitelist/blacklist                │   │
│  │  4. Sort by composite → return top N         │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  RuleTemplates (static)                             │
│  ┌──────────────────────────────────────────────┐   │
│  │ 爆款优先 / 教育精品 / 科技快报 /              │   │
│  │ 低风险搬运 / 测试水温                         │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Data Model

### New table: `content_rules`

```python
class ContentRule(Base, TimestampMixin):
    __tablename__ = "content_rules"

    id: int (PK)
    name: str                    # User-friendly name
    enabled: bool (default True)
    is_template: bool (default False)

    # Scoring weights (JSON)
    # {"virality": 0.30, "translation": 0.25, "quality": 0.20, "market": 0.15, "cost": 0.10}
    weights: str (JSON)

    # Filter conditions (JSON array)
    # [{"field": "view_count", "op": "gte", "value": 50000},
    #  {"field": "category", "op": "in", "value": ["tech", "education"]},
    #  {"field": "published_days_ago", "op": "lte", "value": 7}]
    conditions: str (JSON)

    # Lists
    whitelist_channels: str (JSON, nullable)   # ["UC...", "@channel"]
    blacklist_keywords: str (JSON, nullable)   # ["politics", "religion"]
    blacklist_channels: str (JSON, nullable)

    # Output
    max_results: int (default 20)
    auto_create_dub: bool (default False)  # Auto-create dub task when rule matches

    # Metadata
    sort_order: int (default 0)  # Display order in UI
    last_evaluated_at: datetime (nullable)
```

## Supported Condition Schema

```json
{
  "field": "view_count | like_count | duration_sec | published_days_ago |
            category | composite_score | virality_score | translation_score |
            quality_score | market_score | cost_score |
            has_captions | language | subscriber_count",
  "op": "eq | neq | gt | gte | lt | lte | in | not_in | between",
  "value": "<number> | <string> | [<values>] | [<min>, <max>]"
}
```

## Task Breakdown

### T1: `ContentRule` model
- File: `backend/app/models/content_rule.py`
- Register in `__init__.py`
- Include 5 template rules as seed data (`config_seeder.py`)
- **Acceptance:** Table created with 5 template rows

### T2: `RuleEngine` service
- File: `backend/app/services/scoring/rule_engine.py`
- `evaluate_rule(rule, video_scores[]) → scored_results[]`
  - Apply custom weights to rescore
  - Apply each condition (AND logic within conditions)
  - Apply whitelist/blacklist
  - Sort by composite_score desc
  - Return top `max_results`
- `validate_rule(rule) → (bool, str)` — validate condition syntax
- `test_rule(rule, sample_size=50) → preview_results[]` — test against recent videos
- **Acceptance:** Rule evaluation produces correct filtered output

### T3: Condition parser + evaluator
- File: `backend/app/services/scoring/condition_evaluator.py`
- Parse JSON conditions into callable predicates
- Support all operators (eq, neq, gt, gte, lt, lte, in, not_in, between)
- Type coercion: "50000" → int when field is view_count
- **Acceptance:** All operators work correctly with test data

### T4: Rule API endpoints
- File: `backend/app/api/rules.py`
- `GET /api/rules` — list all rules (templates + custom)
- `POST /api/rules` — create custom rule
- `PUT /api/rules/{id}` — update rule
- `DELETE /api/rules/{id}` — delete rule
- `POST /api/rules/{id}/evaluate` — run rule against discovery results, return matches
- `POST /api/rules/{id}/test` — test rule against 50 recent videos, show what would match
- `POST /api/rules/{id}/duplicate` — duplicate a rule as starting point
- **Acceptance:** Full CRUD + evaluate + test endpoints

### T5: Rule templates seeder
- File: `backend/app/services/config_seeder.py` (extend)
- 5 templates as `ContentRule(is_template=True)`:
  1. "爆款优先" — views > 500K, published < 7d, all categories, virality weight 40%
  2. "教育精品" — category=education, duration 5-25min, engagement > 5%
  3. "科技快报" — category=tech, duration < 15min, published < 3d
  4. "低风险搬运" — exclude politics/religion, views > 10K, language=en
  5. "测试水温" — composite > 70, cost > 8
- **Acceptance:** 5 templates appear on `GET /api/rules`

### T6: Frontend — Rule editor in Settings
- File: `frontend/src/views/SettingsView.vue` (modify — add "选题规则" section)
- Or: New `frontend/src/components/RuleEditor.vue`
- UI features:
  - List saved rules with enable/disable toggle
  - Edit rule: name + weight sliders (5 dimensions) + condition builder (add/remove conditions with field/op/value selects) + whitelist/blacklist textareas
  - "Test rule" button → show preview of what would match
  - "Apply rule" → set as active for discovery
  - Template selector: pick from 5 presets
- Reuse existing Settings field patterns (select/number/input)
- **Acceptance:** User can create, edit, test, and apply rules from Settings

### T7: Unit tests
- File: `backend/tests/unit/test_rule_engine.py`
- Test condition evaluation for each operator
- Test rule evaluation with mock scores
- Test whitelist/blacklist filtering
- Test weight override
- **Acceptance:** ≥ 15 tests pass

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/content_rule.py` | Create | ContentRule model |
| `backend/app/services/scoring/rule_engine.py` | Create | Rule evaluator + test engine |
| `backend/app/services/scoring/condition_evaluator.py` | Create | JSON condition parser |
| `backend/app/api/rules.py` | Create | Rule CRUD + evaluate + test |
| `backend/app/services/config_seeder.py` | Modify | Add rule templates |
| `backend/app/api/router.py` | Modify | Register rules router |
| `frontend/src/components/RuleEditor.vue` | Create | Visual rule builder UI |
| `frontend/src/views/SettingsView.vue` | Modify | Add rule editor section |
| `backend/tests/unit/test_rule_engine.py` | Create | Unit tests |

## Verification

1. **Rule creation:** `POST /api/rules` with conditions → rule created and validated
2. **Evaluation:** `POST /api/rules/1/evaluate` → returns scored + filtered videos
3. **Template seed:** After server start, `GET /api/rules` returns 5 templates
4. **Weight override:** Rule with virality_weight=0.5 produces different ranking than default
5. **Blacklist:** Video with keyword "politics" excluded when rule has blacklist
6. **Rule editor UI:** User can create/edit/delete rules, adjust weights, and test rules from Settings
