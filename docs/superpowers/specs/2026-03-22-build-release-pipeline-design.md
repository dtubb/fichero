# Fichero Build & Release Pipeline — Design Spec

**Date:** 2026-03-22
**Status:** Approved

## Problem

Fichero has a dual-codebase architecture (SwiftUI frontend + Python FastAPI backend) but no unified build, release, or distribution pipeline. The existing scripts in `fichero-engine/scripts/` handle individual steps (Briefcase bundling, backend copy) but nothing orchestrates the full flow from source to notarized DMG to GitHub release.

## Decision

Keep the existing Briefcase approach for bundling the Python backend into `FicheroBackend.app`. Build a set of shell scripts in `fichero/scripts/` that orchestrate the full pipeline, modeled on the proven patterns from `fichero_toolbox/scripts/`.

## Architecture

```
scripts/build-debug.sh          Dev build (Briefcase + Xcode Debug)
scripts/build-release.sh        Release build (Briefcase + Xcode Release + codesign)
scripts/build-release-dmg.sh    DMG packaging
scripts/notarize.sh             Apple notarization + stapling
scripts/build-and-validate.sh   Full pipeline: lint → test → build → DMG → notarize
scripts/start-backend.sh        Dev-mode hot-reload wrapper
scripts/create-github-release.sh  GH release + DMG upload + appcast update
scripts/deploy-site.sh          Sync site to tubb.ca and push
scripts/release.sh              Orchestrator: validate → release → deploy
```

## Build Flow

```
                    ┌──────────────────────┐
                    │  fichero-engine/        │
                    │  (Python backend)    │
                    └──────┬───────────────┘
                           │ briefcase package
                           ▼
                    ┌──────────────────────┐
                    │  FicheroBackend.app  │
                    │  (standalone .app)   │
                    └──────┬───────────────┘
                           │ copy to Resources/
                           ▼
                    ┌──────────────────────┐
                    │  fichero/    │
                    │  (SwiftUI frontend)  │
                    └──────┬───────────────┘
                           │ xcodebuild
                           ▼
                    ┌──────────────────────┐
                    │  Fichero.app         │
                    │  (with embedded      │
                    │   FicheroBackend)    │
                    └──────┬───────────────┘
                           │ codesign + DMG + notarize
                           ▼
                    ┌──────────────────────┐
                    │  Fichero.dmg         │
                    │  (notarized)         │
                    └──────────────────────┘
```

## Site

Eleventy static site in `fichero/site/`, same stack as fichero_toolbox:
- `site/src/index.md` — hero, description, download, release notes
- `site/src/faq.md` — FAQ
- `site/src/_layouts/base.njk` — shared layout
- `site/src/css/style.css` — Libre Baskerville academic style

Deploys to `tubb.ca/apps/fichero/` via `scripts/deploy-site.sh`.

## GitHub Releases

`create-github-release.sh` reads version from built app, creates a GH release via `gh release create`, uploads the notarized DMG, and updates `appcast.xml`.

## One-Time Setup Required

1. **Developer ID Application certificate** — Apple Developer portal
2. **Notarytool credentials** — `xcrun notarytool store-credentials "notarytool"`
3. **Sparkle EdDSA key pair** — `generate_keys`, store private key securely

## Conventions

- All scripts use `set -euo pipefail`
- All scripts resolve `ROOT_DIR` from their own location
- Build artifacts go in `build/` (gitignored)
- Release artifacts go in `build/releases/`
- Scripts print step numbers: `[N/M] description`
- Validation scripts print pass/fail summary
