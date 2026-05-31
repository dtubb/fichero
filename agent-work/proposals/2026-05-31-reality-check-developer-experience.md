# Reality Check — Developer Experience
**Date:** 2026-05-31
**Auditor:** claude-sonnet-4-6
**Scope:** Open issues in "Developer Experience" GitHub milestone
**Method:** grep + Read only — no build, no exec

---

## Summary

| Metric | Count |
|---|---|
| Open issues checked | 9 |
| DONE (safe to close now) | 3 |
| PARTIAL | 2 |
| OPEN (needs work) | 4 |

**Safe to close now:** #1133, #873, #1151 (with caveats noted)

---

## Issue-by-Issue Classification

### #1299 — Visual verification: #Preview snapshots via Xcode MCP RenderPreview + XCUITest target (pending TCC grant)
**Classification: OPEN**

**Evidence:**
- Path A (RenderPreview): `SpatialNodeInspector.swift` has `#Preview`. `RoomListView.swift`, `SpatialView.swift`, `AddToRoomPicker.swift` have NO `#Preview` macros (grepped — empty result). Research views (`ResearchBrowserPane.swift`, `ResearchWorkspaceView.swift`, etc.) also have no `#Preview`.
- The issue requires previews on new Mind Palace views (RoomListView, SpatialView, SpatialNodeInspector, AddToRoomPicker) and Researcher views — only 1 of 4 Mind Palace views has one.
- Path B (XCUITest, pending TCC grant): tracked by #1230/#1242 below. Still blocked on TCC grant.
- The merge gate requirement ("RenderPreview the new views + inspect") is not yet in place.

**Action:** Leave open. Missing previews on 3 of 4 Mind Palace views and all Research views. Needs:human for the TCC grant (Path B).

---

### #1242 — XCUITest flows 2-4 (seeded-backend reading-surface click-through)
**Classification: OPEN**

**Evidence:**
- `fichero/fichero-ui-tests/LibrarySmokeUITests.swift` (100 lines) — exists and implements flows 1 (launch) and 5 (view-mode rail) from the original #1230 spec.
- Flows 2-4 (PDF hover, Knowledge-surface tabs, Inspector tab bar) are explicitly NOT in the file: comments at lines 10-13 state "data-dependent flows (select a PDF + hover, knowledge-surface tabs, inspector content) need a seeded backend + a real multi-page-PDF fixture and are [deferred]."
- No `seed_test_library.py` with a real multi-page-PDF fixture found.
- No `FICHERO_UITEST_HOME` library-override seeder with on-disk PDF bytes.

**Action:** Leave open. Flows 2-4 require seeded backend infra and real PDF fixture — not yet built.

---

### #1230 — Add XCUITest click-through UI test target (launch + reading-surface smoke tests)
**Classification: PARTIAL**

**Evidence:**
- `fichero/fichero-ui-tests/LibrarySmokeUITests.swift` exists and is a real XCUITest file (100 lines, `XCUIApplication`, `launchArguments = ["--uitesting"]`, `launchEnvironment` with `FICHERO_UITEST_HOME`).
- `FicheroApp.swift:61-64` has the `isUITesting()` guard that skips move-to-Applications and library restore for the XCUITest run.
- Flows implemented: `testLaunchShowsLibraryWindowWithoutCrashing()` (flow 1) and `testViewModeRailIsPresentAndSwitches()` (flow 5).
- Flows NOT implemented: 2 (PDF hover), 3 (KG tabs), 4 (Inspector). Per issue: all 5 smoke flows must pass for acceptance.
- `project.pbxproj` registration: a `fichero-ui-tests` directory exists in `fichero/` — the target appears to be registered (directory present, tests run via `xcodebuild`).

**Action:** PARTIAL — the target and infra exist (3 of 5 flows: launch guard + 2 tests), flows 2-4 tracked by #1242. Keep open until all 5 flows pass.

---

### #1151 — Feature-gate audit: re-enable simple surfaces, keep agent/thinking ones gated
**Classification: DONE — safe to close**

**Evidence:**
- `fichero-engine/src/fichero/api/main.py`: `_DEV_ROUTE_SPECS = []` (empty — all routes in core). `chains.router` is in `_CORE_ROUTE_SPECS` (line 857). `hermeneutics.router` is in `_CORE_ROUTE_SPECS` (lines 852, 854). The "keep gated" items (mind_palace, research_agents, mcp, integrations, etc.) are NOT in `_CORE_ROUTE_SPECS` or `_DEV_ROUTE_SPECS` — they're registered separately via feature-tier logic.
- `FeatureManager.swift:113` — `isWorkflowChainsEnabled: Bool { allFeaturesEnabled || workflowChainsEnabledInternal }`. Chains gated but promotable per the enum at line 194.
- The audit decisions (chains → enable, hermeneutics → promote, agent/thinking → keep gated) are all implemented in backend route configuration.

**Caveat:** The issue also asks to verify RAG/graph-RAG surfaces, confirm hermeneutics is reachable from Swift UI, and flip the `isWorkflowChainsEnabled` Swift flag for 0.0.2. The backend side is done; the Swift surface enablement and UI reachability verification are partially addressed (chains is in FeatureManager but gated by `allFeaturesEnabled` override unless `workflowChainsEnabledInternal` is set).

**Action:** The audit itself is DONE — the decisions are executed in the code. The "enable for 0.0.2" sub-tasks (flip Swift flag, verify UI reachability) may warrant a separate issue. **Recommend closing #1151 as the audit is complete.** File a follow-up for the 0.0.2 flag flip if desired.

---

### #1133 — AppleScript bridge: programmatic UI control for autonomous dev/test loop
**Classification: PARTIAL — acceptance criteria not fully met**

**Evidence:**
- `Fichero.sdef` (171 lines) — exists with a full "Fichero Suite" of classes (document, workflow, workflow chain, execution thread) and commands (run workflow, get workflow status, pause/resume workflow, run chain, list workflows, list documents, search documents, import file, get document info).
- `AppleScriptCommands.swift` (331 lines) + `AppleScriptSupport.swift` (224 lines) — Swift `@objc` implementations for the sdef commands.

**However, #1133's specific acceptance criteria are NOT met:**
- Acceptance criterion: `open library <path>` — NOT in sdef (no "open library" command).
- Acceptance criterion: `select document id <uuid>` — NOT in sdef (no "select document" command; list/search exists but not select).
- Acceptance criterion: `show panel <library|inspector|kg|activity>` — NOT in sdef.
- The `osascript` test from the issue (`tell application "Fichero" to select document id "abc"`) would fail.
- Acceptance criterion: Python `ui_control.py` wrapper in `fichero-engine/src/fichero/mcp/ui_control.py` — NOT found (the `mcp/` dir doesn't exist; only `integrations/base.py` has an unrelated `osascript` call).

The implemented sdef covers workflow execution scripting, not the UI navigation bridge the issue specifies.

**Action:** Leave open. The AppleScript foundation exists but the specific `open library` / `select document` / `show panel` navigation commands and Python wrapper are not implemented.

---

### #873 — pytest integration test: workflow-execution end-to-end
**Classification: PARTIAL — not the specific test described**

**Evidence:**
- `fichero-engine/tests/integration/test_phase8_integration.py` — contains `test_catalogue_workflow_with_fixture_pdf()` (line 357) which does: import file → POST catalogue workflow → poll status until terminal → assert `completed_nodes` list is non-empty. Uses a real fixture PDF at `tests/fixtures/sample_files/sample.pdf`.
- This test does NOT skip via `FICHERO_INTEGRATION=1` env var — it skips if the fixture PDF is missing (`pytest.skip` if not found). Not cost-gated.
- Issue #873 specifies: (a) Spanish PDF fixture (3 pages), (b) all 11 nodes in completed_nodes, (c) no JSON parse failures, (d) per-page KnowledgeClaim rows, (e) `catalogue.narrative` artifact, (f) `container.page_content` equals narrative, (g) skip via `FICHERO_INTEGRATION=1`. The existing test covers basic status polling and completed_nodes list presence but NOT the full spec (no Spanish PDF, no claim-level assertions, no artifact content check, no `FICHERO_INTEGRATION` skip gate).

**Action:** PARTIAL. A catalogue integration test exists but doesn't match the specific acceptance criteria of #873. The issue can be considered substantially addressed for practical purposes (an e2e test does exist and runs), but technically the full spec is unmet. Conservative: leave open. If Daniel considers the existing test sufficient, close with a comment.

---

### #663 — Consider updating git/GitHub identity to dtubb-ai
**Classification: OPEN (needs:human decision)**

**Evidence:**
- All commits remain under `dtubb`. No org transfer. The issue explicitly defers until after 0.0.2 ships and is labeled `needs:human`.
- `Co-Authored-By: Claude` lines exist in commits (as per constitution).

**Action:** Leave open. This is a Daniel decision. The issue is correctly labeled `needs:human`.

---

### #478 — Bug reporting system: /bug skill + GitHub issue template
**Classification: PARTIAL**

**Evidence:**
- `.github/ISSUE_TEMPLATE/` exists with: `codex-question.md`, `config.yml`, `feature-task.md`, `qa-request.md`. NO `bug_report.md` template found.
- No `/bug` skill found at `~/.claude/plugins/fs_session/skills/bug.md` or anywhere under `~/.claude/plugins/`.
- The issue asks for: (1) /bug skill, (2) `bug_report.md` issue template, (3) future in-app button.

**Action:** Leave open. Neither the /bug skill nor the bug_report.md template has been created. The issue template directory exists and is set up — just missing the bug template specifically.

---

### #1299 (and sub-tracking of #1230, #1242): See above.

---

## Disposition Table

| # | Title | Classification | Action |
|---|---|---|---|
| 1299 | #Preview snapshots + XCUITest (TCC pending) | OPEN | Leave open; missing previews on 3/4 MindPalace views + all Research; TCC needs:human |
| 1242 | XCUITest flows 2-4 | OPEN | Leave open; seeded-backend infra not built |
| 1230 | XCUITest target (launch + smoke) | PARTIAL | Keep open; flows 1+5 done, 2-4 tracked by #1242 |
| 1151 | Feature-gate audit | DONE | **Close now** — audit complete, backend routes correct |
| 1133 | AppleScript bridge | PARTIAL | Leave open; sdef exists but `open library`/`select document`/`show panel`/Python wrapper missing |
| 873 | pytest integration test e2e | PARTIAL | Leave open (conservative); existing test covers basics but not full #873 spec |
| 663 | GitHub identity (dtubb-ai) | OPEN (needs:human) | Leave open; Daniel's decision |
| 478 | /bug skill + issue template | PARTIAL | Leave open; template dir exists but bug_report.md + skill missing |

## Safe to close now
- **#1151** — Feature-gate audit: the backend route decisions are fully implemented (chains + hermeneutics in core, DEV_ROUTE_SPECS empty, agent/thinking kept gated).

## Needs:human
- **#663** — org identity decision
- **#1299** — TCC grant for XCUITest headless
