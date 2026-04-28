# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — HEAD `9cbc5193`. Massive 0.0.2 polish day shipped 7 commits: folder inspector, thumbnail aspect, Catalogue (composable) reducer, page artifact scope fix, workflow template dedupe + folder grouping, sidebar drag investigation. Bug count: 0 net (4 fixed, several 0.0.3 deferred items filed cleanly).

**Goal:** ship 0.0.2 — release pipeline is now the only remaining work. All Daniel-blocked or content tasks.

## Open Issues (0.0.2 milestone)

### Real remaining 0.0.2 work — all release-pipeline / content
| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |
| #665 | Dev blog post — 3 years AI coding | Content writing |

### Filed but should be moved to 0.0.3 or deferred
| # | Title | Notes |
|---|---|---|
| #713 | Sidebar drag icon/name asymmetry — NSOutlineView wrapper | 0.0.3 — deferred, SwiftUI gap |
| #714 | Workflow Templates Install Defaults undercount alert | Likely fixed by #722 dedupe |
| #715 | Inspector RTF editor: ⌥←/⌥→ shortcuts don't work | 0.0.3 — likely AttributedTextEditor keyDown swallow |
| #716 | Paleography Transcribe (SILReST 6-step chain) | 0.0.3 — multi-day prompt engineering, manuals need repo move |
| #717 | Grid icon click highlight | Likely fixed by #712 browserSelection clear; verify |
| #719 | Eager-prefetch thumbnails per-folder | 0.0.3 — TaskGroup + LRU cache work |
| #711 | Sidebar drag unification | Closed by `4ee5e608` (whitespace path); icon/name path → #713 |
| #598 / #702 | Sidebar drop routing / drop-target type matrix | Subsumed by #711 / #713 |
| #603 / #694–705 | Various V1 inspector / sidebar bugs | Most are completed in code per task list — need GitHub close |

### 0.0.3 milestone — already filed
| # | Title |
|---|---|
| #712 | Folder inspector + hide preview pane (SHIPPED on 0.0.2 this session) |
| #713 | Sidebar drag NSOutlineView wrapper |
| #720 | Catalogue (composable) reducer (SHIPPED) |

## Blocked
- #658–#660 release pipeline blocked on Daniel creating the `fichero-releases` repo + getting Apple notarytool credentials.

## Next Session — Start Here

1. **Close GitHub issues already done in code.** Many issues (#603, #694, #695, #696, #697, #698, #699, #700, #701, #703, #704, #705, #696, #720, #721, #722) are completed in commits but still open on GitHub. Close them with a comment linking to the commit. About 15 minutes of cleanup.
2. **Move deferred-but-shippable issues to 0.0.3** explicitly: #713, #715, #716, #717, #719. Update STATE.md after.
3. **If nothing else broken in user testing** → start the release pipeline: ask Daniel to create `dtubb/fichero-releases` repo, then begin #659 (codesign + notarytool). Read `docs/architecture/release-process.md` first.
4. **Architecture docs to read for orientation**: `docs/architecture/swiftui/inspector_redesign.md`, `docs/architecture/swiftui/api_client.md`, `docs/architecture/api/development_standards.md`, `docs/architecture/release-process.md`.
5. **Diagnostic log markers still in the code** (`🎯` on `.dropDestination`, `🔵` on `.onMove`, `📥` on `.onDrop`) — leave them in for #713 work, they don't fire in normal use.

## Key constraints carried forward (still hot)

- `inspectorDocument` precedence: grid match (only if child of current sidebar folder) → viewMode.library doc → detailDocument. **Don't reorder** — the precedence matters for the folder inspector to show on sidebar clicks (#712).
- Inspector V2 strict per-document scope: every `getArtifacts` call must pass `includeDescendants: false` (#721). The legacy aggregation default is V1-only and should never be used in new V2 code paths.
- SwiftUI `Text` registers `NSDraggingSource` at AppKit level — `.allowsHitTesting(false)` directly on `Text` is the only suppression; `.textSelection(.disabled)` is not enough (#711 / #713 history).
- Workflow templates ship in `fichero-api/src/fichero/resources/default_workflows/*.json` with `folder_path` for menu grouping. Backend is canonical; Swift `WorkflowStore.defaultWorkflowTemplates` is empty (#722).
- `reinstall-defaults` endpoint with `force=True` deletes is_template=True rows and re-inserts. Reinstalling the app's defaults pulls in updated JSON.

---

*Last updated: 2026-04-28* — session-end after the 7-commit 0.0.2 polish day.
