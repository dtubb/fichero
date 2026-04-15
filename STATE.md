# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean. Backend work complete.

**Status:** Session complete. 40 milestones, release gate issues filed, testing process documented, `/bug` skill live, bug priority rule wired into autonomous sessions.

## In Progress

Nothing active. Waiting on Daniel to test 0.0.1.

## Test Health

**1785 passing, 0 failures, 21 skipped.**

## Release Map

| Milestone | Theme | Issues |
|---|---|---|
| **0.0.1** | Core Library — ship next | 6 |
| **0.0.2** | Backend merge (no UI) | 0 |
| **0.0.3** | Wire: Search v1 | 8 |
| **0.0.4** | Wire: Search v2 (Filters + Layouts) | 4 |
| **0.0.5** | Wire: Search v3 (Semantic Map) | 3 |
| **0.0.6** | Wire: Providers + API Keys | 8 |
| **0.0.7** | Wire: Local Models | 1 |
| **0.0.8** | Wire: Chat v1 | 4 |
| **0.0.9** | Wire: Chat v2 (Model Comparison) | 2 |
| **0.1.0** | Wire: Workflow Basics | 5 |
| **0.1.1** | Wire: Workflow Editor | 4 |
| **0.1.2** | Wire: Workflow Tools | 3 |
| **0.1.3** | Wire: Workflow Chains (LangGraph) | 1 |
| **0.1.4** | Wire: Batch Processing | 6 |
| **0.1.5** | Wire: Activity Monitor | 2 |
| **0.1.6** | Wire: Automation (Triggers + Schedules) | 2 |
| **0.2.0** | Wire: KG Entities | 1 |
| **0.2.1** | Wire: KG Claims List | 1 |
| **0.2.2** | Wire: KG Claim Inspector | 2 |
| **0.2.3** | Wire: Ontology Browser | 1 |
| **0.2.4** | Wire: Epistemology Graph | 2 |
| **0.2.5** | Wire: KG Predictions | 1 |
| **0.2.6** | Wire: Hermeneutics | 3 |
| **0.3.0** | Wire: Image Editing v1 (Crop + Rotate) | 7 |
| **0.3.1** | Wire: Image Editing v2 (Enhance + Remove BG) | 3 |
| **0.3.2** | Wire: Image Segmentation | 2 |
| **0.4.0** | Wire: Export Basics (JSON + Markdown) | 4 |
| **0.4.1** | Wire: Export Documents (Word + PDF) | 2 |
| **0.4.2** | Wire: Export Spreadsheets (Excel) | 2 |
| **0.4.3** | Wire: Export Web + Netlify | 3 |
| **0.5.0** | Wire: MCP Servers | 2 |
| **0.5.1** | Wire: API Security + Auth | 3 |
| **0.6.0** | Wire: Spatial Knowledge Layer | 9 |
| **0.6.1** | Wire: Spatial Library | 1 |
| **0.7.0** | Wire: Agents | 1 |
| **0.7.1** | Wire: Research Agents | 1 |
| **0.7.2** | Wire: Integrations | 2 |
| **0.8.0** | Backend Ops + Migrations | 4 |
| **0.8.1** | Backend Operations | 4 |
| **0.9.0** | Epistemic Platform Expansion | 8 |

## Testing Process

See `docs/architecture/release-process.md` — every milestone follows the same pipeline:
1. Backend tests + lint
2. Enable feature flag + Xcode build + SwiftLint
3. Claude: MCP API tests + Peekaboo visual screenshots
4. Daniel: human test checklist (in release gate issue)
5. Bug loop via `/bug` skill
6. `/release` to ship

## Next Session — Start Here

1. **Fix 0.0.1 bugs autonomously** — #383, #384, #385, #386 (drag/drop, image import, window restore, transcribe) + #516 (FileType enum). Run `/session-start-auto` overnight.
2. **Daniel: test 0.0.1** → `/release 0.0.1`
3. **Merge 0.0.2 → main** — immediately after 0.0.1 ships
4. **Begin 0.0.3** — Wire: Search v1 (11 open issues: list/table views, artifacts column, import progress)

## Parallel Workflow

Daniel tests N → Claude builds N+1 in a separate worktree.
Gate: Claude never merges without Daniel's `/release N`.

---
*Last updated: 2026-04-14* — 40 milestones, release gate issues filed (#481-515), release-process.md written
