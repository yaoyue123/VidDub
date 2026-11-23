"""Auto-publish routing after compose."""
import pytest

from app.services.scheduler import TaskScheduler


@pytest.mark.asyncio
async def test_handle_publish_uses_configured_default_platform(monkeypatch):
    called = {}

    class FakeManager:
        async def auto_publish(self, video_id, platforms=None, **kwargs):
            called["video_id"] = video_id
            called["platforms"] = platforms
            return {}

    async def fake_configs():
        return {"default_upload_platform": "douyin"}

    monkeypatch.setattr(
        "app.services.scheduler._load_configs", fake_configs,
    )
    monkeypatch.setattr(
        "app.services.publish.manager.get_publish_manager", lambda: FakeManager(),
    )

    sched = TaskScheduler(download_dir=".", max_concurrent=1)
    await sched._handle_publish(42)

    assert called == {"video_id": 42, "platforms": ["douyin"]}


@pytest.mark.asyncio
async def test_handle_publish_falls_back_to_bilibili(monkeypatch):
    called = {}

    class FakeManager:
        async def auto_publish(self, video_id, platforms=None, **kwargs):
            called["platforms"] = platforms
            return {}

    async def fake_configs():
        return {}

    monkeypatch.setattr("app.services.scheduler._load_configs", fake_configs)
    monkeypatch.setattr(
        "app.services.publish.manager.get_publish_manager", lambda: FakeManager(),
    )

    sched = TaskScheduler(download_dir=".", max_concurrent=1)
    await sched._handle_publish(1)
    assert called["platforms"] == ["bilibili"]
