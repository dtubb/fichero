# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed `52af797b` (37 commits ahead since 2026-05-01).
Catalogue pipeline now per-page end-to-end (Phase E multi-output + Phase
C/D cleanup tools); inspector V2 has the Finder Get Info shape Daniel
asked for; Debug iteration loop down to ~5s thanks to Embed-skip on
Debug. Apple Intelligence runs locally via on-device Foundation Models.

**Goal:** Daniel runs the new Catalogue pipeline on a real folder and
confirms per-file artifacts land + KG inspector reads well, then we
move to release packaging (#658–#660).

## Open Issues (0.0.2 milestone)

**Release pipeline (Daniel-blocked):**
| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |

**Engineering — open or deferred:**
| # | Title | Status |
|---|---|---|
| #178/#803 | Phase C: page_cleanup tool | ✅ Shipped 2026-05-04 |
| #179/#804 | Phase D: folder_cleanup tool | ✅ Shipped 2026-05-04 |
| #180/#805 | Phase E: multi-output catalogue | ✅ Shipped 2026-05-04 |
| #806 | Duplicate Apple Intelligence in model picker | ✅ Closed (dedup at startup) |
| #807 | Phantom SourceKit "Self has no member" errors | ✅ Closed (3 real lint fixes) |
| #720 | Catalogue (composable) doesn't emit combined artifact | Resolved by Phase E (multi-output) |
| #721 | Inspector shows parent's container artifacts on child page | Inspector V2 ships per-doc strict scope |
| #702 | Drag-drop folder onto PDF row | Validation matrix, not started |
| #598 | Sidebar drop routes to selected row, not cursor target | Pending |

## In Progress

- Inspector V2 Phase 2 (#156): RTF-editable panels ✓, delete ✓, AI
  display attributes (deferred), per-type artifact payloads (deferred).

## Blocked

Nothing right now. Daniel needs to test the new pipeline end to end on
a real folder before the release packaging path opens up.

## Overnight Work (2026-05-06 → morning)

**Master plan:** #872. Tonight's execution sequence covers the LLM-stack
overhaul rolled up under Themes #868 (Provider abstraction), #869
(Contract robustness), #870 (Apple path consolidation), #871 (Test +
observability).

**Live bug fix shipped tonight:** `d04dae26` — #868 routes Apple
Intelligence's `unsupportedLanguageOrLocale` to the $large fallback
the same way guardrail refusals already are. New typed exception
hierarchy: `AppleUnavailableError` base + `GuardrailViolationError`
and `UnsupportedLocaleError` subclasses. fm-bridge stderr mapping
updated. Live symptom on the 68-page 'Legal Case' (Spanish):
extract_all hard-failing every chunk → no claims → empty catalogue
narrative. Restart the backend to pick this up.

**Decisions logged (Daniel approved):**
- Theme C: stay on fm-bridge as canonical Apple integration.
- Theme A: do the LLMProvider Protocol refactor — long-hall worth it.

## Next Session — Start Here

1. **Restart the backend** on the new commit so the unsupported_language
   fix is live. Re-run Catalogue (Mixed) on Legal Case. Expect: extract_all
   calls Apple → unsupported_language → silently routes to $large →
   Spanish entities extracted; catalogue.narrative populates;
   container.page_content shows narrative in inspector RTF panel.
2. **Test the new Catalogue pipeline** on Test 2 / 1931 Antonio
   Asprilla folder via Apple Intelligence. Verify per-file `_clean`
   artifacts land on each file doc (not just folder). Use the
   Knowledge Graph tab on a single file to check.
2. **If per-file works**: move on to release pipeline #658–#660 (DMG
   build / notarize / dry-run install).
3. **If per-file doesn't land**: check engine.log for
   `page_cleanup(<key>): wrote <key>_clean on N/M descendant docs` —
   N>0 means it's working. If N=0, the records flow lost doc_ids
   again; verify catalogue.json has both `transcribe.texts → aggregate.text`
   AND `files-source.documents → aggregate.documents` (force-reseed
   defaults via Settings if not).
4. Iterate on the inspector via plain Xcode: `BuildProject` (~1.5s) +
   `open .../Fichero.app` (~5s end-to-end). Don't try SwiftUI
   previews of the Inspector — they hit the 30s app-launch timeout
   and the SPM workaround isn't worth the duplication cost.
5. New bugs Daniel files via `/bug` go to milestone 0.0.2.

## Architecture Reminders

- **Engine**: external (`./fichero-engine/scripts/start_backend.sh` or
  briefcase dev) — Debug Embed phase no longer copies the briefcase
  bundle; the Swift app probes `:8765` for 5s and uses whatever's there.
- **Auth**: token at `~/Library/Application Support/Fichero/.api-key`,
  written by `initialize_token()` on every engine start regardless of
  launch path.
- **Test 2 folder**: `7dbba674ae204be9b08dc8df5a00f6fa` (Asprilla,
  15 files); Catalogue workflow id changes per reseed — query
  `/api/workflows/` to find current.
