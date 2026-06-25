"""Config API: list, update, and test SiliconFlow connectivity.

Phase 5 新增：
- PUT /api/config/{key}       — 按 key 单独更新（per D5-05）
- POST /api/config/test-siliconflow — 测试 SiliconFlow API Key 连通性 (per D5-04)
"""
import logging
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.config import Config
from app.schemas import ConfigResponse, ConfigUpdateRequest

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──

class ConfigSingleUpdateRequest(BaseModel):
    """单 key 配置更新 (D5-05)."""
    value: str


class ConfigTestResponse(BaseModel):
    """SiliconFlow 连通性测试结果."""
    ok: bool
    latency_ms: int
    error: Optional[str] = None


# ── Endpoints ──

@router.get("", response_model=list[ConfigResponse])
async def list_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Config))
    configs = result.scalars().all()
    return list(configs)


@router.put("", response_model=list[ConfigResponse])
async def update_configs(body: ConfigUpdateRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Config))
    existing_configs = {c.key: c for c in result.scalars().all()}

    for item in body.configs:
        if item.key in existing_configs:
            config = existing_configs[item.key]
            config.value = item.value
            if item.description is not None:
                config.description = item.description
        else:
            config = Config(key=item.key, value=item.value, description=item.description)
            db.add(config)

    await db.flush()

    final_result = await db.execute(select(Config))
    return list(final_result.scalars().all())


@router.put("/{key}", response_model=ConfigResponse)
async def update_single_config(
    key: str,
    body: ConfigSingleUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """按 key 单独更新一个配置项 (D5-05).

    不存在则创建。
    """
    result = await db.execute(select(Config).where(Config.key == key))
    config = result.scalar_one_or_none()
    if config:
        config.value = body.value
    else:
        config = Config(key=key, value=body.value, description=None)
        db.add(config)
    await db.flush()
    await db.refresh(config)
    return config


@router.post("/test-siliconflow", response_model=ConfigTestResponse)
async def test_siliconflow(
    db: AsyncSession = Depends(get_db),
):
    """测试 SiliconFlow API Key 连通性 (D5-04).

    用一次最小的 chat completions 请求验证 Key 是否有效，并测量延迟。
    不会保存任何数据，仅做连通性测试。
    """
    from app.core.config import settings

    api_key = settings.siliconflow_api_key.strip()

    if not api_key:
        return ConfigTestResponse(
            ok=False, latency_ms=0,
            error="未配置 SiliconFlow API Key。请在「设置 → SiliconFlow」中填写，"
                  "或在 backend/.env 中设置 SILICONFLOW_API_KEY。",
        )

    base_url = settings.siliconflow_base_url
    url = f"{base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": "deepseek-ai/DeepSeek-V4-Flash",
        "messages": [
            {"role": "user", "content": "ping"},
        ],
        "max_tokens": 4,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        return ConfigTestResponse(ok=False, latency_ms=0, error="请求超时（15s）")
    except httpx.HTTPError as e:
        return ConfigTestResponse(ok=False, latency_ms=0, error=f"网络错误: {e}")
    latency_ms = int((time.perf_counter() - start) * 1000)

    if resp.status_code == 200:
        return ConfigTestResponse(ok=True, latency_ms=latency_ms)
    if resp.status_code == 401:
        return ConfigTestResponse(
            ok=False, latency_ms=latency_ms,
            error="API Key 无效或已过期 (401)",
        )
    if resp.status_code == 429:
        return ConfigTestResponse(
            ok=False, latency_ms=latency_ms,
            error="已达调用频控 (429)，但 Key 有效",
        )
    body_tail = (resp.text or "")[:200]
    return ConfigTestResponse(
        ok=False, latency_ms=latency_ms,
        error=f"HTTP {resp.status_code}: {body_tail}",
    )
