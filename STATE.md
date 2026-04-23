# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — Catalogue workflow landed end-to-end, content-editor reliability fixes shipped.

**Goal:** Ship 0.0.2 with Transcribe + Catalogue + reliability fixes. Search backport decision pending (see Next Session).

## What Landed This Session

### Content editor reliability (#671, #672 research)
- RTF color/font persistence: normalizer no longer blanks user formatting on load (5991a5d6).
- Draft preservation: onDisappear no longer cancels pending saves; saveContent uses refreshLocalContent (not updateLocal) so a content save never removes the doc from the grid (9bec7d8f).
- #672 filed but not yet fixed: workflows silently overwrite user-edited page_content.

### Context-menu Run Workflow submenu (#669)
- Inline workflow submenu in library grid + sidebar context menus.
- Folders expand to files in files_tool so Run-on-Folder actually works.

### Catalogue workflow — #676 and children

| Issue | Status |
|---|---|
| #677 Un-hide catalogue tools | Done (22532176) |
| #678 Catalogue tool rewrite (9-section output) | Done (00d4dfbc, 93077035, 8aa6e16f) |
| #679 skip_if_artifact_exists | Done (93077035, 54c9f683) |
| #681 Default workflow seeding | Done (e1682a4a) |
| #682 Inspector per-section rendering | Done (8563af60) |
| #680 Aggregate node (first-class) | Deferred to 0.0.3 |
| #683 Visual fan-out / aggregate markers | Deferred to 0.0.3 |
| #684 Chained per-file steps | Deferred to 0.0.3 |

**What works now**: Right-click a folder → Run Workflow → Catalogue. Transcribes every file (skip-if-done), runs one LLM call with aggregated text, produces nine-section structured output, saves as individual per-section artifacts (people, dates, rivers, events, mines, properties, keywords, summary, legal_references) on the container folder. Also writes the combined markdown to the folder's page_content so the Content tab shows the full entry.

**Inspector UX**: each catalogue artifact type renders as its own structured preview (tables, not JSON).

### Tests
- Backend: **1857 passing** (141 existing workflow + 36 new catalogue/seeding/skip-if-done + the rest of the suite).
- Swift: 2 new test files for CatalogueArtifactPreviews + FeatureManager tool allowlist.

## Blockers / Open

| # | Title | Status |
|---|---|---|
| #672 | Workflows overwrite user-edited page_content | **Closed** (de67f81e) — user edits flagged via metadata timestamp; workflows respect. |
| #670 | files_tool resolves page → parent PDF silently | 0.0.3 (broad fix) |
| #673 | fileCompletedCount storm on inspector refresh | 0.0.3 polish |
| #674 | documentSignature hashes full content per diff | 0.0.3 polish |
| #675 | convertToSendable lossy for Date/URL metadata | 0.0.3 polish |
| #680, #683, #684 | First-class Aggregate node + visual markers + chained per-file steps | 0.0.3 — the Catalogue preset uses implicit aggregate so it works today without these |

## Next Session — Start Here

1. **Daniel decision: search backport vs defer.**
   The 0.0.3 worktree (`~/code/fichero-0.0.3`) has 3762 insertions / 12846 deletions vs 0.0.2 — massive refactors beyond search (Sidebar modes split, etc.). Safer paths:
   - (A) Lock down 0.0.2, ship with Transcribe + Catalogue + reliability, move to 0.0.3 worktree to finish search.
   - (B) Cherry-pick only search-tagged commits from 0.0.3 into 0.0.2 (risky — dependencies on the Sidebar refactor).
   My recommendation is (A). Awaiting your call before moving.

2. **Xcode build + smoke-test the Catalogue workflow**. Right-click a folder → Run Catalogue. Confirm:
   - Existing transcriptions are reused (skip-if-done).
   - Nine-section markdown appears in the folder's Content tab.
   - Per-section artifacts render in the Artifacts tab with clean tables.
   - Editing a document's text after transcription survives a re-run of Catalogue.

3. **Release prep** (#661, #662, #658, #659) once smoke-test passes and search decision is made.

---

*Last updated: 2026-04-22 (autonomous session)* — catalogue landed; ship-readiness pending #672 + search decision.
