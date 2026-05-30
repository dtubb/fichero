# Manager Resume Brief — 2026-05-30

**Trunk:** `0.0.2` @ `09cb3d37` (pushed). Engine + app launch flag `FICHERO_FEATURE_TIER=dev` is committed in the Xcode Run scheme.

**Lane status at handoff:**
- `f_opus` — **STILL RUNNING.** Do not interrupt; it's working steadily on Mind Palace / cross-platform code.
- `f_integrator`, `f_reviewer`, `f_planner`, `f_bugtriage`, `f_sonnet`, `f_haiku`, `f_codex53`, `f_gpt`, `f_gpt_mini` — all session-ended.
- Three unmerged f_gpt batch-6 branches sit local: `gpt-activity-window` `94a0a96e` (#1264), `gpt-bibtex-metadata` `51099f97` (#1101, OpenAPI change), `gpt-inspector-style` `54cb64cf` (#1241).

**All four DONE proposals live in `agent-work/proposals/`:**
- `2026-05-29-swiftui-endpoint-coverage.md` (f_integrator)
- `2026-05-30-issue-triage.md` (f_bugtriage)
- `2026-05-30-post-collapse-review.md` (f_reviewer)
- `2026-05-30-mindpalace-phased-plan.md` (f_planner)

---

## What needs doing — synthesized from the four lane outputs

### Phase 0 — TRUNK IS RED. Fix this BEFORE anything else.

Verified by `mcp__xcode__BuildProject` on 2026-05-30:

**Trunk-only errors (must fix on `0.0.2` directly):**
1. `fichero/fichero/Views/Workflow/WorkflowEditor.swift:90` — "Switch must be exhaustive."
2. `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift:8` — `let onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)? = nil` excludes the property from the synthesized memberwise initializer. Callers like `EntityDetailView+Claims.swift:100` pass it explicitly → "Extra argument 'onNavigateToSource' in call." **Fix:** change `let` → `var` (keeps the default; restores the init parameter). Also audit `SpeakerComparisonView.swift:77` which currently calls `ClaimSummaryCard(claim:)` without `onNavigateToSource` — if you keep the `var` fix, that call site is fine.

**Then attempt the Opus Mind-Palace merge** (`origin/opus-realitykit-design`, 2 commits ahead of `0.0.2`: `6a39569a` design, `6f6fbdd5` impl). When I attempted the merge in this session, the pbxproj had 2 union-mergeable conflict regions in `project.pbxproj` (Models group + Sources phase) — both resolved by keeping BOTH sides (KGFocusState + MindPalaceTheme + MindPalaceLibraryProjector entries). After that, the build surfaces 8 errors that need fixing before commit:
- `KGTemporalSpatial.swift:110` and `KGTimelineView.swift:259` — "Switch must be exhaustive." Likely from Opus's new `LinkType` enum cases. Add the missing cases or a `default:`.
- `SpatialModels.swift:202` — "Main actor-isolated property 'globalLibrary'/'shared' cannot be referenced from a nonisolated context." Annotate the property or its access site with `@MainActor`.
- `SpatialScene3D.swift:404-410` — `LoadRequest<TextureResource>` is being assigned where `TextureResource` is expected. Use `try await TextureResource(loadRequest:)` / `await load()` pattern; also `:410` flagged "Expression is 'async' but is not marked with 'await'."
- `DocumentKGSurface.swift:85` — "Invalid redeclaration of 'selectedEntityId'." This is the reviewer's flagged shadow-of-param bug (`fichero/fichero/Views/Library/DocumentKGSurface.swift:55-56` and `:49`). Promote it to `@SceneStorage` and delete the dead `let` param at `:49`. **Bonus: this also satisfies Reviewer fix #3.**

Dispatch sequence: **integrator** fixes Phase 0 trunk-red (errors 1+2) directly on `0.0.2`. Then **integrator** does the Opus merge with the union pbxproj resolution + the 8-error fix-up; recommend doing this in a fresh worktree branch off `0.0.2`, gate with `mcp__xcode__BuildProject`, then merge to `0.0.2`. **reviewer** verifies. Until Phase 0 is green, Phases 1+ are blocked.

### Phase 1 — GitHub hygiene (manager only, no code; can run while Opus continues)

From `2026-05-30-issue-triage.md`. Apply these via `gh` CLI:

**1a. Add 3 custom fields to Project #5 "fichero"** (single-select):
- **Epic**: KG Single-Path, Mind Palace, MCP, Exporter, Importers, Translation, NER, Hermeneutics, Researcher, Onboarding, Settings, Infrastructure, Backlog
- **Status**: Backlog, Ready, In-Progress, Review, Done
- **Priority**: P0-Critical, P1-High, P2-Medium, P3-Low

**1b. Close as duplicates** (with cross-reference comment):
- #1327 → #1338 (simplified MCP subsumed by full-featured)
- #475 → #1334 (static site exporter)
- #423 → #375 (Interpretations workspace)
- #1303 (oMLX env constraint, not a code bug — see [[project_known_red_dedup_test]] sibling reasoning)
- #1326 → #1318 (CLI parity, already closed)

**1c. Verify+close** #1217 (folder timestamp refresh) — fix landed in `73856f0d` but issue still open.

**1d. Bulk-label as `roadmap`/`parking-lot`** and hide from default board view:
- Release-gate stubs: #488–#515, #511, #512, #505–#508
- Future roadmap: #740, #657, #1092–#1095, #1158–#1161, #374, #375, #378–#380, #461

**1e. Retire feature-based milestones with 0 closed issues** (close with no-further-work note; items migrate to Epic field):
- KG Entities (#31), KG Claims List (#32), KG Claim Inspector (#33), Epistemology Graph (#35), KG Predictions, Chat v1, Chat v2, Local Models, Workflow Basics/Editor/Tools/Chains, Activity Monitor, Automation, Batch Processing, Ontology Browser, Search v2, Search v3, Providers + API Keys, Spatial Knowledge Layer (#12), Hermeneutics (#37), Export: JSON + Markdown (#14)

**1f. Keep** the active version milestones: `0.0.2 - Backend Merge + Bug Fixes`, `0.0.3 - KG Navigation + Polish`, `0.0.3 - Post-LLM-stack`, `0.0.4 - Local RAG`.

**1g. Bulk-set Epic field** per the mapping table in §7 of the triage doc.

### Phase 2 — Code work (dispatch in parallel; opus stays on Mind Palace P1)

**Lane A: integrate the three unmerged f_gpt batch-6 branches into 0.0.2.** OpenAPI regen + Swift BuildProject required after `gpt-bibtex-metadata` (#1101). Order: activity-window → inspector-style → bibtex-metadata (do bibtex last so OpenAPI churn lands last).

**Lane B (Codex/sonnet — pick by tier): Reviewer's 5 fixes** from `2026-05-30-post-collapse-review.md`, in priority order:
1. Route `KGMapView.swift:221` + `KGTimelineView.swift:279` (also `EntityDigestView.swift` and `DocumentInspectorInfoTab.swift:173`) through `entityService.documentKnowledgeGraph(...)` — the canonical endpoint. **MAJOR.**
2. Share one descendant-walk helper between `folders.py:_folder_descendant_documents` and `claims.py:_descendant_doc_ids`. **MAJOR.**
3. Promote `DocumentKGSurface.swift:55–56` `@State` → `@SceneStorage`/shared state; delete the shadowed `selectedEntityId` param at `:49`. **MAJOR.**
4. Add unit tests for `KGFocusState`'s drive-direction guards (`focusEntity`/`focusClaim`/`clear` idempotency, no-oscillation). Cheap, highest-value test hole.
5. `#if os(macOS)` color shim for `SpatialScene3D.swift:47/88/318/329` and `RoomListView.swift:60` — needed for iOS/visionOS compile (Mind Palace P3/P4 prep).

**Lane C: f_opus (already running)** — Mind Palace P1, 5 child tickets from `2026-05-30-mindpalace-phased-plan.md`:
1. Backend `GET /api/mind_palace/library_snapshot` (docs+entities → nodes; claims → edges; `include_children` flag).
2. Wire snapshot into `MindPalaceService` / `MindPalaceState` so the whole corpus loads (not a room).
3. Cross-platform color helper (overlaps with Reviewer fix #5 — coordinate so only one lane edits these files).
4. LinkType edge labels (via `slug_verb`) + `HoverEffectComponent` highlight.
5. Incremental scene diffing in `update:` (replace make-only build) for corpus scale.

**Lane D (low-priority, queue for later): Integrator's 5 wrapper gaps** from `2026-05-29-swiftui-endpoint-coverage.md`:
1. `/api/schedules/*` and `/api/triggers/*` — automation Swift wrappers.
2. `/api/chains/*` — `ChainService` wrapper (chains UI exists already).
3. `/api/export/*` — Swift wrapper before exposing export menu items (also unblocks Exporter Epic).
4. `/api/annotations/*` — wrapper before annotation editing/crop/promote-to-claim UI.
5. `/api/local-models/*` — Local Model manager wrapper (Settings).

### Phase 3 — Release-gate cluster (after Phase 2)

From triage doc §3:
- **#1216** Large folder ingest data missing after relaunch — **data-loss bug, P0**.
- **#1224 + #1225** Activity Viewer (user-facing names + step completion) — both same surface; one PR.
- **#1220** Workflow nodes/inspector miswired/feature-gated — blocks basic workflow UX.
- **#1215** Toolbar + View menu pane controls unreliable.
- **#1151** Feature-gate audit (re-enable simple surfaces) before tier promotion.
- **#659** Build/sign/notarize 0.0.2 DMG.
- **#660** Dry-run release on Daniel's machine.

---

## Coordination notes

- **Hot file in this session:** `SpatialScene3D.swift` (cross-platform color fix overlaps between Reviewer's fix #5 and Opus's P1 child #3). Assign to ONE lane only.
- **OpenAPI lanes serialise:** never run two OpenAPI-changing lanes in parallel. Order: `gpt-bibtex-metadata` (#1101) → snapshot endpoint (Opus P1 child #1) → chains/export/annotations wrappers.
- **Gates per merge:** ruff + targeted pytest (NEVER full suite, see [[feedback_no_full_pytest_on_daniels_machine]]) + `mcp__xcode__BuildProject` + `sync_openapi_schema.sh` if backend changed.
- **Verify-then-close:** `git log origin/main..HEAD | grep "(#N)"` before any `gh issue close`. See [[feedback_lane_orchestration_lessons]] §4.
- **Engine flag:** Daniel's app launches with `FICHERO_FEATURE_TIER=dev`; engine must be launched with the same env var or Mind-Palace/Research/MCP endpoints 404.

---

## Suggested manager startup prompt

Paste this after `/session-start-manager`:

> Read `agent-work/handoff/2026-05-30-manager-resume.md` and proceed:
> 1. Start Phase 1 (GitHub hygiene) right away — pure `gh` CLI, runs in background. Do NOT touch code.
> 2. While Phase 1 runs, dispatch Phase 2 Lane A (merge three unmerged f_gpt batch-6 branches) to f_codex53 or f_gpt, and Phase 2 Lane B (reviewer's 5 fixes) to f_sonnet.
> 3. Leave f_opus alone — it's mid-flight on Mind Palace P1.
> 4. Tick every 15 min; merge as lanes go idle.
> 5. After Phase 2 is integrated, plan Phase 3 (release-gate cluster). Surface any blocker to Daniel before starting Phase 3.

---

*Generated by manager pre-session-end; sources: the four DONE proposals + STATE.md + MEMORY lessons.*
