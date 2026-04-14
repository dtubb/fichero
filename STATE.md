# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed and clean. Swift client pipeline fully working.

**Status:** Backend cleanup complete (#460 closed). All new feature areas planned and tracked on GitHub. Milestone restructuring complete.

## In Progress

Nothing active.

## Test Health

**1785 passing, 0 failures, 21 skipped.** All pre-existing failures resolved.

## Milestone Map (post-restructure)

| Milestone | Issues | What |
|---|---|---|
| **0.0.1** | 6 open | Core Library — drag/drop + transcribe + window restore. Daniel's next test. |
| **0.0.2** | 0 open | Search + Semantic Foundation — branch done, ready to merge after 0.0.1 ships. |
| **0.0.3** | 6 open | Migration + Ops + re-enable layouts (#432, #433) |
| **0.0.4** | 6 open | Semantic UX + Trust Workflow (knowledge graph UI) |
| **0.0.5** | 26 open | Operations (async DNS fix, folder watchers, batch tools) |
| **0.0.6** | 9 open | Image Editing (crop, rotate, enhance, remove-bg, segment, lossless) |
| **0.0.7** | 7 open | Export System (JSON, Markdown, Word, Excel, HTML, Netlify) |
| **0.0.8** | 2 open | API Security + Auth (localhost + API key) |
| **0.0.9** | 5 open | Frontend Wiring v1 (feature gates, testing pipeline, search UI) |
| **0.1.0** | 16 open | Epistemic Platform Expansion |

## Parallel Release Workflow

When Daniel tests a release, Claude builds the next one on a separate worktree:
- Daniel testing: `0.0.1`
- Claude building next: `0.0.3` (after 0.0.2 merges)
- Trigger to merge forward: `/release <version>`

## Next Session — Start Here

1. **0.0.1 bugs** — fix #383, #384, #385, #386 (drag/drop, image import, window restore, transcribe). These are all SwiftUI issues.
2. **Frontend wiring plan** — read #479, create `docs/architecture/frontend/overview.md` and `FeatureFlags.swift`
3. **`/bug` skill** — already written in fichero-skills. Test it.
4. **Then: ship 0.0.1** — once bugs fixed, `/milestone-check` → Daniel human tests → `/release 0.0.1`
5. **Merge 0.0.2 → main** — immediately after 0.0.1 ships

---
*Last updated: 2026-04-14* — #460 closed, issues #461-480 filed, milestones restructured (0.0.6-0.0.9 created), /bug skill written
