# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — #666 root cause found and fixed. Need Daniel to verify on-device. Release pipeline next.

**Goal:** Daniel verifies #666 fix (select docs in library → switch to workflow → run → artifacts save). Then: build + notarize 0.0.2 DMG → site → merge to main → start 0.0.3.

## Open Issues (0.0.2 milestone)

| # | Title | Status |
|---|---|---|
| #666 | Transcription artifacts not saving | **Fix committed** — needs Daniel on-device verify |
| #667 | Add Selection source node to workflow editor | Open — implementation pending |
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool credentials |
| #660 | Dry-run: install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Can do now (page content ready in site/) |
| #662 | Update tubb.ca/fichero with release notes + download | Can do now (draft in site/src/apps/fichero/index.md) |
| #665 | Dev blog post: 3 years of AI-assisted coding | Content filing only — write when ready |

## Moved to 0.0.3
- #619 / #605 — startup/backend perf (need on-device Instruments)
- #520 — Sparkle auto-update (needs Apple cert + feed URL)

## Next Session — Start Here

1. **Verify #666**: Ask Daniel to select a PDF in the library → switch to Workflows → open a transcription workflow → hit Run. Check Activity for progress and curl `/api/artifacts/document/<id>` to confirm artifacts saved.
2. If #666 verified: close the issue, then move to release pipeline (#661/#662 site content → #658/#659 DMG).
3. **#667 (Selection node)**: Implement new `selection` source tool in `sources.py` that reads `selected_doc_ids` from state — errors fast if empty. Register it, add to workflow node registry.
4. **3 commits unpushed** on `0.0.2` branch — push before anything else.

---

*Last updated: 2026-04-22* — #666 fixes committed (unit tests + editor selection + browserSelection wiring). Release pipeline blocked on Daniel testing.
