# social-auto-upload — Vendored Dependency

## Overview

[`social-auto-upload`](https://github.com/dreammis/social-auto-upload) is a Python library
that provides automated uploading to Chinese video platforms (Douyin, Kuaishou, Tencent Video,
Xiaohongshu, and Bilibili via the biliup Rust binary). It is the publishing backend for all
platforms in viddub.

The library is a **git submodule** at `social-auto-upload/`, pinned to a known-good
upstream commit. It is tracked as a gitlink (mode `160000`) and configured by
`.gitmodules`.

After a fresh clone, initialize it once:

```bash
git submodule update --init --recursive
```

`start.bat` / `start.sh` also run this automatically when the directory is empty.
The backend creates `social-auto-upload/conf.py` from `conf.example.py` on first
publish, so no manual copy is required.

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

### Option A: Initialize the submodule (recommended)

```bash
git submodule update --init --recursive
```

That is all that is needed: the backend injects the directory into `sys.path`,
creates `conf.py` on first use, and stores platform cookies under
`social-auto-upload/cookies/`.

To update the pinned copy from upstream:

```bash
cd social-auto-upload
git pull origin main
```

### Option B: pip install from upstream

```bash
pip install git+https://github.com/dreammis/social-auto-upload.git
```

If installed via pip, the `sys.path` injection becomes a no-op (the directory is already on
`sys.path` or the package is importable directly).

## Important Notes

### Configuration

`social-auto-upload` uses a `conf.py` file for platform settings. The backend creates it
automatically from `conf.example.py` on first publish; the file is gitignored because it may
gain sensitive cookies when using SAU's own login flows.

To customise it:

```bash
cp social-auto-upload/conf.example.py social-auto-upload/conf.py
# Edit conf.py with your platform credentials
```

### Upstream Repository

- **URL:** https://github.com/dreammis/social-auto-upload
- **License:** MIT
- **Status:** Actively maintained

The viddub vendored copy may lag behind upstream. When updating, check the changelog for
breaking changes to the publishing API.

### Duplicate Uploader: `xhs_uploader/` vs `xiaohongshu_uploader/`

The vendored `social-auto-upload/uploader/xhs_uploader/` directory is a partial duplicate
of `social-auto-upload/uploader/xiaohongshu_uploader/`. The `xhs_uploader/main.py` module
still provides `sign_local()` and `sign()` functions that are used internally by
`social-auto-upload/myUtils/auth.py` and `social-auto-upload/examples/upload_video_to_xhs.py`.

The `xhs_uploader/` directory cannot be deleted until those internal references are migrated
to use `xiaohongshu_uploader` instead. This is tracked as a future cleanup task.
