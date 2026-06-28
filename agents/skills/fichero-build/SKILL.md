---
description: Build Fichero — Briefcase backend + Xcode app. Use for debug or release builds during development.
name: fichero-build
---

# /fichero-build

> **⚠️ STALE — verify before use.** The steps below predate the `fichero-api` → `fichero-engine`
> rename and the consolidated release tooling. The canonical build/release path is now
> `scripts/release-all.sh` + `fichero-engine/scripts/build_backend_bundle.sh`, documented in
> `docs/release/release-lane.md`. Treat the commands here as historical until reconciled
> (tracked in `PLAN-GOVERNANCE.md` §5).

Build Fichero with the embedded Python backend. Defaults to debug; pass `release` for a release build.

## Arguments

- No argument or `debug` → Debug build
- `release` → Release build

## Steps

### 1. Build the Python backend with Briefcase

```bash
cd fichero-api
.briefcase-venv/bin/briefcase create macOS --app fichero-backend 2>/dev/null || true
.briefcase-venv/bin/briefcase build macOS --app fichero-backend
```

If `.briefcase-venv` doesn't exist, tell the user to create it:
```bash
python3.13 -m venv fichero-api/.briefcase-venv
fichero-api/.briefcase-venv/bin/pip install briefcase
```

### 2. Sign the backend

The backend must be signed with the same identity as the parent app:
```bash
SIGNING_ID=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')
codesign --force --sign "$SIGNING_ID" --deep --timestamp fichero-api/build/fichero-backend/macos/app/FicheroBackend.app
```

### 3. Run the build script

For debug:
```bash
bash scripts/build-debug.sh --skip-backend
```

For release:
```bash
bash scripts/build-release.sh --skip-backend
```

(Backend is already built in step 1, so `--skip-backend` skips the Briefcase step in the script.)

### 4. Report

```
FICHERO BUILD — [Debug/Release] — [date]

Backend:  [PASS / FAIL]
Xcode:    [PASS / FAIL]
Codesign: [PASS / FAIL]

App: [path to .app]
```
