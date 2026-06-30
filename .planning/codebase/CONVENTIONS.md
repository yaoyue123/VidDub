# Coding Conventions

**Generated:** 2026-06-30
**Focus:** quality

## Python Conventions

### Formatting
- **Formatter**: Black with line length 100 (`--line-length 100`)
- **Import sorting**: isort with `--profile black`
- **Linter**: Ruff (all default rules)

### Type Annotations
- Required for all public function signatures
- Use `| None` instead of `Optional[]` (Python 3.10+ style)
- Use `Self` return type for class methods returning `self`
- Avoid `Any` — suppress only when interfacing with untyped libraries

### Imports
- **Absolute imports preferred**: `from app.api.videos import router` not `from .videos import router`
- Standard lib → third-party → local (separated by blank line)

### Error Handling
- Catch specific exceptions, never bare `except:`
- No empty `except: pass` blocks
- Use `raise` without argument to re-raise
- Custom exceptions in `models/enums.py` or inline where used

### Async Patterns
- `async def` for all I/O-bound functions
- `asyncio.Semaphore` for concurrency limits
- `tenacity` for retry with exponential backoff on API calls
- `AsyncSession` from SQLAlchemy for all database operations

## TypeScript / Vue Conventions

### Component Style
- Composition API with `<script setup lang="ts">` exclusively
- No Options API components
- Component file names: PascalCase (e.g., `VideoCard.vue`)

### TypeScript
- Strict mode enabled in `tsconfig.json`
- **No `as any`** — type errors must be fixed, never suppressed
- **No `@ts-ignore` or `@ts-expect-error`**
- Interfaces over type aliases for object shapes

### State Management
- Pinia stores with Composition API syntax (`defineStore`)
- Store files: camelCase + "Store" suffix (e.g., `taskStore.ts`)

### HTTP
- Single axios instance in `api/index.ts`
- All endpoints defined as methods on the client object
- Response type: `{ data: T }` for success, `{ detail: string }` for error

## Database Conventions

- All models inherit from `DeclarativeBase` in `models/base.py`
- Table names: snake_case, auto-generated from class name
- Migration files: descriptive names (e.g., `85e4114b41ec_init.py`)
- Run `alembic revision --autogenerate` after model changes

## Git Conventions

- **Commit messages**: Chinese, brief description of change
- **No Co-Authored-By trailers**: All commits treated as single-author
- **Branch naming**: `feat/xxx` or `fix/xxx`
- **Base branch**: `master` (not `main`)
- **No force push** to shared branches

## API Conventions

- RESTful paths: `/api/{resource}`
- Response envelope: `{"data": ...}` for success, `{"detail": "..."}` for errors
- HTTP methods: GET (read), POST (create), PUT (update), DELETE (remove)
- Pagination: `?offset=0&limit=20` query params where applicable

## File Organization

- One class per file (exception: small related models in enums.py)
- Service files named after responsibility (e.g., `whisper_service.py` not `stt.py`)
- Test files mirror source structure under `tests/`
- No `__init__.py` in test directories
