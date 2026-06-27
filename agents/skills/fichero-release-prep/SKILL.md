---
description: Prepare a Fichero release — build, DMG, update release notes and site. Produces artifacts for Daniel to review before publishing.
name: fichero-release-prep
---

# /fichero-release-prep

Prepare everything for a release. Does NOT publish — produces artifacts for Daniel to review.

## Steps

### 1. Build the full release

Run the DMG build script (this builds backend + Xcode + styled DMG):
```bash
bash scripts/build-release-dmg.sh
```

If this fails on the backend, ensure `.briefcase-venv` exists and build manually:
```bash
cd fichero-api
.briefcase-venv/bin/briefcase create macOS --app fichero-backend 2>/dev/null || true
.briefcase-venv/bin/briefcase build macOS --app fichero-backend
# Sign with matching identity
SIGNING_ID=$(security find-identity -v -p codesigning | grep "Apple Development" | head -1 | awk -F'"' '{print $2}')
codesign --force --sign "$SIGNING_ID" --deep --timestamp build/fichero-backend/macos/app/FicheroBackend.app
cd ..
bash scripts/build-release-dmg.sh --skip-backend
```

### 2. Read the version

```bash
cat build/releases/release-manifest.txt
```

### 3. Update the site release notes

Edit `site/docs/index.md` — add a new entry under the "## Releases" / download section with what changed in this version. Read recent git log for context:
```bash
git log --oneline -20
```

### 4. Update the appcast

The `create-github-release.sh` script handles this during release. For now, note the version.

### 5. Test the DMG

Open the DMG and verify:
- App icon is correct (card-file cabinet)
- Applications symlink is present
- Launching from DMG shows the move-to-Applications prompt
- After moving, app launches and backend starts (health check on port 8765)

```bash
open build/releases/Fichero.dmg
```

### 6. Report for review

```
FICHERO RELEASE PREP — v[version] — [date]

Build:
  Backend:    [PASS/FAIL]
  Xcode:      [PASS/FAIL]
  Codesign:   [PASS/FAIL]
  DMG:        [PASS/FAIL] ([size])

Artifacts:
  DMG:        build/releases/Fichero.dmg
  Manifest:   build/releases/release-manifest.txt

Release notes updated: site/docs/index.md

Ready for: /fichero-release

Daniel — please review the DMG and release notes before proceeding.
```
