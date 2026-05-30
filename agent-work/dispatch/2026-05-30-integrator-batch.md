# Integrator dispatch — Phase 0 — 2026-05-30

**You are the integrator.** Worktree: `~/code/fichero-0.0.2`. Branch: `0.0.2`. You may edit code; verify each step with `mcp__xcode__BuildProject(windowtab1)`. Use jcodemunch-mcp for all code navigation ([[reference_jcodemunch_mcp_single_source]]).

Trunk is currently RED. Manager verified with `BuildProject` at 2026-05-30 09:11. Fix the 2 trunk errors **before** any merge, then attempt the Opus Mind-Palace merge.

## Step A — Fix trunk-red on 0.0.2 directly (no branch)

**Error A1** — `fichero/fichero/Views/Workflow/WorkflowEditor.swift:90`: "Switch must be exhaustive."
- Open the file via jcodemunch; identify the enum being switched and the missing case(s).
- Either add the missing case(s) explicitly (preferred — gives compile-time coverage for future additions) or add `default:` with a no-op + a `// TODO(#1240)` if the new case is genuinely out-of-scope.

**Error A2** — `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCardView.swift:8`: "Extra argument 'onNavigateToSource' in call" at `EntityDetailView+Claims.swift:100`.
- Root cause: `let onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)? = nil` — `let` with default value excludes the property from the synthesized memberwise initializer.
- **Fix:** change `let` → `var`. Keeps the default; restores the init param. (Don't drop the default — `SpeakerComparisonView.swift:77` calls `ClaimSummaryCard(claim:)` without it.)

**Gate:** `BuildProject(windowtab1)` → must be CLEAN. Commit both fixes in one commit: `fix: restore trunk build (WorkflowEditor exhaustive switch + ClaimSummaryCard let→var)`. Push to `0.0.2`.

## Step B — Merge Opus Mind-Palace Phase 3

Branch: `origin/opus-realitykit-design` (commits `6a39569a` design + `6f6fbdd5` impl). Work in a fresh **branch** off updated `0.0.2`, not directly on `0.0.2`, so you can iterate without polluting trunk:

```bash
git fetch origin opus-realitykit-design
git checkout -b integrate-opus-realitykit-design origin/0.0.2
git merge --no-ff --no-commit origin/opus-realitykit-design
```

**Expected conflicts in `fichero/fichero.xcodeproj/project.pbxproj`** (2 regions, both union-merge):
1. Models group (~line 1197): keep BOTH `KGFocusState.swift` (HEAD) and `MindPalaceTheme.swift` (opus).
2. Sources phase (~line 2212): keep BOTH `KGFocusState.swift in Sources` (HEAD) and `MindPalaceTheme.swift in Sources` + `MindPalaceLibraryProjector.swift in Sources` (opus).

`git add fichero/fichero.xcodeproj/project.pbxproj`. Don't commit yet.

`BuildProject(windowtab1)`. You will see ~8 errors. Fix them in this order:

**B1** — `KGTemporalSpatial.swift:110` and `KGTimelineView.swift:259`: "Switch must be exhaustive." From Opus's new `LinkType` cases. Add missing cases (preferred — they're a new enum with a bounded set, look at `MindPalaceLink` in opus's diff for the full list).

**B2** — `SpatialModels.swift:202`: "Main actor-isolated property 'globalLibrary'/'shared' cannot be referenced from a nonisolated context." Annotate the property declaration with `@MainActor` or the access with `MainActor.assumeIsolated { ... }`. Prefer `@MainActor` on the property — RealityKit scene-graph mutations are all main-thread per [[feedback_nsviewrepresentable_mainactor]].

**B3** — `SpatialScene3D.swift:404-410`: `LoadRequest<TextureResource>` returned where `TextureResource` expected; ":410 Expression is 'async' but is not marked with 'await'." Use the correct RealityKit async load pattern — `try await TextureResource(named:)` or `try await TextureResource.load(contentsOf:)`. See [[reference_realitykit_xplatform_primitives]].

**B4** — `DocumentKGSurface.swift:85`: "Invalid redeclaration of 'selectedEntityId'." This is the **same bug reviewer flagged** as MAJOR fix #3: `@State selectedEntityId` shadows the `let selectedEntityId` parameter at `:49`. Promote the state to `@SceneStorage("documentKGSurface.selectedEntityId")` and DELETE the dead `let` param at `:49` (and clean up any call sites that were passing it). **This satisfies reviewer fix #3 as a bonus.**

**Gate:** `BuildProject(windowtab1)` → CLEAN. Run `mcp__xcode__RunAllTests(windowtab1)` — known-red includes `test_same_person_in_two_docs_dedupes_to_one_entity` ([[project_known_red_dedup_test]]); everything else must pass.

## Step C — Merge to 0.0.2

```bash
git commit -m "merge: Opus Mind-Palace Phase 3 (#1297 follow-up) + cascading fixes"
# Then merge the integration branch into 0.0.2:
git checkout 0.0.2 && git pull && git merge --no-ff integrate-opus-realitykit-design
```

`BuildProject` again on `0.0.2` to confirm post-merge state.

Push `0.0.2`. Comment on **#1297** with the merge commit SHA + the 4 fixed errors. **Do NOT close #1297** until reviewer gates.

## Step D — Notify

Write `agent-work/dispatch/2026-05-30-integrator-DONE.md` with: merge SHA, list of fixes applied, BuildProject result, test result. Manager will pick up and route to reviewer.

## Hard rules

- Never `gh issue close` before grep-confirming the merge landed ([[feedback_lane_orchestration_lessons]] §4).
- Never run full `pytest fichero-engine/tests/unit/` on Daniel's machine ([[feedback_no_full_pytest_on_daniels_machine]]).
- Never edit backend `.py` while the engine is running ([[feedback_no_backend_edits_during_live_run]]). Check `lsof -i :8765` if unsure; pause if it's live.
- New `.swift` files MUST be registered via `ruby scripts/add-swift-file.rb <path>` ([[feedback_swift_file_sync]]). Opus added 3 new Swift files (`MindPalaceTheme.swift`, `MindPalaceLibraryProjector.swift`, `MindPalaceLinkTypeTests.swift`) — verify they're in `project.pbxproj` (they should be, from the union merge; if missing, register).
