# Testing

**Generated:** 2026-06-30
**Focus:** quality

## Test Framework

| Tool | Version | Purpose |
|------|---------|---------|
| pytest | 8.0+ | Test runner |
| pytest-asyncio | 0.23+ | Async test support |
| pytest-mock | 3.12+ | Mocking support |
| unittest.mock | stdlib | Additional mocking |

## Test Layout

Tests are in `backend/tests/`:

```
backend/tests/
├── __init__.py
├── conftest.py             # Shared fixtures
├── test_api.py             # API endpoint integration tests
├── test_douyin_publish.py  # Douyin publishing tests
├── test_integration.py     # Integration smoke tests
├── test_transcription.py   # STT service tests
├── test_tts.py             # TTS service tests
├── test_voice_cloner.py    # Voice cloning tests
├── unit/                   # Unit tests
│   ├── __init__.py
│   ├── test_alignment.py
│   ├── test_ffmpeg_cmd.py
│   ├── test_paths.py
│   ├── test_sf_client.py
│   ├── test_sf_transcriber.py
│   ├── test_sf_translator.py
│   └── test_sau_bilibili_publisher.py
├── integration/            # Integration tests
│   ├── __init__.py
│   ├── test_e2e_dub.py
│   ├── test_migration.py
│   └── test_phase10_e2e.py
└── fixtures/               # Test data
    ├── sample_en.mp3
    ├── sample_en.wav
    ├── silent.wav
    └── stt_smoke_result.json
```

## Configuration

`backend/pytest.ini`:
```
[pytest]
testpaths = tests
asyncio_mode = auto
python_files = test_*.py
markers =
    integration: marks tests as integration tests (deselect with '-m "not integration"')
    e2e: end-to-end tests (slow, external dependencies)
    slow: marks tests as slow
```

## Running Tests

```bash
# All tests
venv\Scripts\python -m pytest tests/ -v

# Unit tests only
venv\Scripts\python -m pytest tests/unit/ -v

# Integration tests
venv\Scripts\python -m pytest tests/integration/ -v

# Fast fail (stop on first error)
venv\Scripts\python -m pytest tests/ -x -q

# Run with specific marker
venv\Scripts\python -m pytest tests/ -v -m "not integration"
```

## Testing Patterns

### Async Tests
All async tests use `pytest-asyncio` with `asyncio_mode = auto`:
```python
async def test_something():
    result = await my_async_function()
    assert result == expected
```

### Mocking External Services
External API calls (SiliconFlow, YouTube) are mocked:
```python
async def test_translate(mocker):
    mock_client = mocker.AsyncMock()
    mock_client.chat.return_value = {"choices": [{"message": {"content": "..."}}]}
    # Inject mock into service
```

### Conftest Fixtures
`conftest.py` provides shared fixtures:
- `db_session` — In-memory SQLite async session
- `sample_video` — Video model fixture
- `sample_task` — Task model fixture
- `client` — FastAPI TestClient

### Test Characteristics
- Unit tests: Mock all external services, test business logic in isolation
- Integration tests: Test real database + some real service calls
- E2E tests: Marked `@pytest.mark.e2e`, not run by default
- No network-dependent tests required (all external calls mocked in unit tests)

## Coverage

There is no formal coverage requirement configured. No `--cov` flag or `.coveragerc` file found. Tests focus on:
- Core service logic (SiliconFlow client, translation, TTS)
- API endpoint handlers
- Pipeline orchestration (scheduler handlers)
- Platform login + publish flows
