# Contributing to You2Bili

Thank you for considering contributing! This document outlines the development workflow, code style, and testing requirements.

---

## Development Environment Setup

### Prerequisites

- Python 3.10+ (3.11/3.12 recommended)
- Node.js 18+ (20 LTS recommended)
- ffmpeg (in PATH)
- Git

### One-Time Setup

```bash
# Clone the repository
git clone <your-fork-url> you2bili
cd you2bili

# Backend setup (venv + dependencies + Playwright Chromium)
cd backend
python -m venv venv

# Windows
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python -m playwright install chromium

# Linux/macOS
# venv/bin/pip install -r requirements.txt
# venv/bin/python -m playwright install chromium

# Copy environment config
cp .env.example .env
# Edit .env with your SILICONFLOW_API_KEY

# Frontend setup
cd ../frontend
npm install

# Database migration
cd ../backend
venv\Scripts\python -m alembic upgrade head
```

> **Note:** On Windows, the `setup.ps1` script automates all of the above. On Linux/macOS, `setup.sh` does the same.

---

## Code Style

### Python (Backend)

- **Formatter:** [Black](https://github.com/psf/black) (line length 100)
- **Linter:** [Ruff](https://docs.astral.sh/ruff/)
- **Import sorting:** `isort` (compatible with Black)
- **Type hints:** Required for all public functions and methods

```bash
# Format code
venv\Scripts\black backend/ --line-length 100
venv\Scripts\isort backend/ --profile black
```

### TypeScript / Vue (Frontend)

- **Formatter:** [Prettier](https://prettier.io/)
- **Linter:** [ESLint](https://eslint.org/) with TypeScript rules
- **Style:** Prefer Composition API with `<script setup lang="ts">`

```bash
# Lint and format
cd frontend
npx eslint src/ --fix
npx prettier --write src/
```

---

## Testing Requirements

All contributions must pass existing tests. New features should include tests.

### Backend Tests (pytest)

```bash
cd backend
venv\Scripts\python -m pytest tests/ -v
```

- Tests live in `backend/tests/` (unit/) and `backend/tests/integration/`
- Use `pytest-asyncio` for async tests
- Mock external services (SiliconFlow, YouTube, Playwright)
- No network-dependent tests should be required

### Frontend Build Verification

```bash
cd frontend
npm run build
```

The production build must succeed without errors.

### Pre-PR Checklist

- [ ] `pytest tests/ -x -q` passes with no regressions
- [ ] `npm run build` succeeds
- [ ] Black and Ruff pass on changed Python files
- [ ] ESLint and Prettier pass on changed frontend files
- [ ] Documentation updated if API or behavior changed

---

## Branching and PR Workflow

1. **Fork** the repository on GitHub
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
3. **Make changes** with atomic commits
4. **Run tests** (see above)
5. **Push** to your fork:
   ```bash
   git push origin feat/your-feature-name
   ```
6. **Open a Pull Request** against `main`

### PR Guidelines

- Title: concise summary of the change
- Description: what changed and why
- Reference related issues if applicable
- Keep PRs focused — one feature/fix per PR

---

## Documentation

- User-facing docs live in `docs/` (ARCHITECTURE.md, CONFIGURATION.md, TROUBLESHOOTING.md, etc.)
- Code-level docs use docstrings (Google-style for Python, JSDoc for TypeScript)
- The change log is at `CHANGELOG.md`

---

## Getting Help

- Open a GitHub Issue for bugs or feature requests
- Check `docs/TROUBLESHOOTING.md` for common issues
- Review `docs/ARCHITECTURE.md` for system design understanding
