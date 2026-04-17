# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed, clean (through `8d2ed415`).

**Active worktrees:**
- `~/code/fichero-0.0.2` — bug fixes, Daniel testing
- `~/code/fichero-0.0.3` — Wire: Search v1 (Claude loop, branch `0.0.3`)

**Status:** Process-hardening session, no code changes. Peekaboo MCP now wired for visual verification; `AGENTS.md` strengthened with three-leg Swift check, test-as-you-go rule (#5), agent-team delegation. Bug filed: #589 (kreuzberg cache cwd pollution) with .gitignore band-aid applied. 0.0.2 feature/bug backlog unchanged: #556, #571 awaiting verify; #588 PDFView pinch; #520 Sparkle; #589 new.

## In Progress

Nothing actively coding. Same verification loop as end of prior session — Daniel's retest of `413b6614` (PDF↔grid sync, folder drop, settings grouped).

## Test Health

**Swift Testing suite:** 25+ passing (SidebarItemBuilder, DocumentNavigation, PDFThumbnailRendering, DragDropModel). No regressions introduced this session.

**Python backend tests:** 190+ passing, 13 pre-existing infra failures (missing `endpoints.json`/`export_api_schemas.py` — separate from 0.0.2 work).

## Next Session — Start Here

1. **Read the new `AGENTS.md` — test-as-you-go is now hard rule #5.** Every SwiftUI fix/feature must land with unit tests in the same commit. Also skim the "Agent Team" section for delegation patterns (Plan → critic → test-runner → peekaboo → code-reviewer).
2. **#588 PDF pinch-zoom** — likely next actionable. Audit: grep `.gesture`/`.simultaneousGesture`/`MagnificationGesture` in ancestors of `PDFPageView`; test trackpad pinch. Add `.highPriorityGesture(MagnificationGesture())` proxy to PDFKit's zoom if blocked. **Write the XCTest regression test in the same commit.**
3. **#589 kreuzberg cache location** — proper fix (backend): pass explicit `cache_dir` into kreuzberg config in `fichero-api/src/fichero/loaders/{pdf_loader.py:156, document_loader.py:128}`. Follow `db_embeddings.py:94` / `local_models.py:257` pattern using `MODELS_BASE / "kreuzberg"`. `.gitignore` band-aid already shipped.
4. **#556, #571 verification** — still awaiting Daniel's retest (settings `.formStyle(.grouped)` + sidebar drop highlight).
5. **#520 Sparkle** — last 0.0.2 task. SDK wire-up, appcast signing, update-check UI.

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-17 (session 2)* — Process hardening: peekaboo MCP online, AGENTS.md strengthened (three-leg Swift check, test-as-you-go rule #5, agent-team delegation, cross-link to agents/AGENTS.md). #589 filed for kreuzberg cwd pollution; band-aid gitignored. Awaiting Daniel's verification pass on 0.0.2.
