# social-auto-upload — Vendored Dependency

## Overview

[`social-auto-upload`](https://github.com/dreammis/social-auto-upload) is a Python library
that provides automated uploading to Chinese video platforms (Douyin, Kuaishou, Tencent Video,
Xiaohongshu, and Bilibili via the biliup Rust binary). It is the publishing backend for all
platforms in you2bili.

The library is currently **vendored** as a nested git repository inside the you2bili repository
at `social-auto-upload/`. It is not a git submodule — it has its own `.git` directory and
remote.

## How It Is Used

The vendored directory is injected into Python's `sys.path` at runtime by the publish modules
in `backend/app/services/publish/`:

```python
# backend/app/services/publish/sau_bilibili.py (and similar files)
_SAU_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "social-auto-upload")
)
if os.path.isdir(_SAU_DIR) and _SAU_DIR not in sys.path:
    sys.path.insert(0, _SAU_DIR)
```

## Local Development — Three Options

### Option A: Use the vendored copy (simplest)

The vendored copy at `social-auto-upload/` is ready to use. No setup is needed for local
development — the `sys.path` injection handles everything.

To update the vendored copy from upstream:

```bash
cd social-auto-upload
git pull origin main
```

### Option B: Git submodule

If you prefer a proper submodule relationship:

```bash
git submodule add https://github.com/dreammis/social-auto-upload.git social-auto-upload
git submodule update --init
```

Then remove the existing `.git` directory inside `social-auto-upload/`:

```bash
rm -rf social-auto-upload/.git
```

### Option C: pip install from upstream

```bash
pip install git+https://github.com/dreammis/social-auto-upload.git
```

If installed via pip, the `sys.path` injection becomes a no-op (the directory is already on
`sys.path` or the package is importable directly).

## Important Notes

### Configuration

`social-auto-upload` uses a `conf.py` file for platform cookies and credentials. The file at
`social-auto-upload/conf.py` contains sensitive cookies and **must never be committed to
version control**. The vendored repo's `.gitignore` already excludes `conf.py`.

To set up your own configuration:

```bash
cp social-auto-upload/conf.example.py social-auto-upload/conf.py
# Edit conf.py with your platform credentials
```

### Upstream Repository

- **URL:** https://github.com/dreammis/social-auto-upload
- **License:** MIT
- **Status:** Actively maintained

The you2bili vendored copy may lag behind upstream. When updating, check the changelog for
breaking changes to the publishing API.

### Duplicate Uploader: `xhs_uploader/` vs `xiaohongshu_uploader/`

The vendored `social-auto-upload/uploader/xhs_uploader/` directory is a partial duplicate
of `social-auto-upload/uploader/xiaohongshu_uploader/`. The `xhs_uploader/main.py` module
still provides `sign_local()` and `sign()` functions that are used internally by
`social-auto-upload/myUtils/auth.py` and `social-auto-upload/examples/upload_video_to_xhs.py`.

The `xhs_uploader/` directory cannot be deleted until those internal references are migrated
to use `xiaohongshu_uploader` instead. This is tracked as a future cleanup task.
