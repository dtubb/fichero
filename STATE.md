# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — #666 fixes committed but NOT yet verified. Server must be restarted before testing.

**Goal:** Restart server → verify #666 (transcription runs end-to-end) → release pipeline.

## Open Issues (0.0.2 milestone)

| # | Title | Status |
|---|---|---|
| #666 | Transcription artifacts not saving | **Fix committed** — server not restarted, UNVERIFIED |
| #667 | Add Selection source node to workflow editor | Open — implementation pending |
| #668 | Workflow Input toggle UX confusion | Open |
| #669 | Right-click context menu: Run Workflow submenu | Open |
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool credentials |
| #660 | Dry-run: install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Can do now |
| #662 | Update tubb.ca/fichero with release notes + download | Can do now |
| #665 | Dev blog post: 3 years of AI-assisted coding | Content filing only |

## Moved to 0.0.3
- #619 / #605 — startup/backend perf (need on-device Instruments)
- #520 — Sparkle auto-update (needs Apple cert + feed URL)

## Next Session — Start Here

1. **FIRST**: Restart the server — `PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765`. The `sources.py` fix (`if raw_files:`) is committed but the running server still has old code.
2. **Verify #666**: Select a file in library → switch to Workflows → pick Transcribe → Run. Watch server logs — should see `[STEP] ✓ Completed: Files` then `Transcribe` node firing (not "No files to fan out"). Check Activity for real duration (>1s).
3. If verified: close #666, push, then move to release pipeline (#661/#662 site content first, then #658/#659 DMG).
4. **Spinner gap**: If #666 verified working, investigate why no spinner appears on files during processing — `updateProcessingStatus` path in `ContentView+Actions.swift` → `DocumentStore` → library row. May need a clean AI pass (prompt in last session).

---

*Last updated: 2026-04-22* — sources.py fix committed but server not restarted; all other session fixes pushed.
