# View QA Matrix

Purpose: provide a single checklist for Daniel's manual QA runs and Codex follow-up triage.

For release-gate execution on milestone `0.0.1`, use [0.0.1-manual-qa-checklist.md](./0.0.1-manual-qa-checklist.md).
Workflow release gate details are tracked in [workflow-qa-validation-gates.md](./workflow-qa-validation-gates.md).
Capture and intake smoke coverage lives in [CAPTURE_SMOKE_MATRIX.md](./CAPTURE_SMOKE_MATRIX.md).

## Reporting Format
- Prefix every result with `[DANIEL]` or `[CODEX]` in issue comments.
- For each failed step include:
  - view/screen
  - exact action
  - expected result
  - actual result
  - whether backend route(s) were involved

## Library View (issue #114)
1. Open library root, switch list/grid modes, and select documents.
2. Verify inspector updates as selection changes.
3. Run search/filter and clear state.
4. Import file/folder and confirm progress/errors are shown.

Backend observables:
- `/api/documents/*`
- `/api/search*`
- `/api/ingest/*`

## Workflow Editor (issue #115)
1. Create workflow, add/remove nodes, connect edges.
2. Edit node configuration in popover and save.
3. Execute workflow and observe live status.
4. Duplicate/rename/export/import workflow.
5. Display modes:
   - With `workflow_editor_advanced_views` OFF: only Icon + List are available.
   - With `workflow_editor_advanced_views` ON: Table mode appears in addition to Icon + List.

Backend observables:
- `/api/workflows/*`
- `/api/workflow-execution/*`
- `/api/chains/*` (if chaining UI used)

## Sidebar Surfaces (issue #116)
1. Switch modes via clicks and keyboard shortcuts.
2. Create/rename/delete sidebar items where supported.
3. Validate context menus and drag/drop behavior.
4. Confirm mode state persists when navigating.
5. Batches visibility gate:
   - With `batches` feature flag OFF: no "Batches" navigation row appears.
   - With `batches` feature flag ON: "Batches" row appears independently of Workflows/Activity.

Backend observables:
- `/api/documents/*`
- `/api/workflows/*`
- `/api/providers/*`
- `/api/activity/*`

## Backend API Audit (issue #117)
Automated baseline already passing for focused suites (129 tests).
Manual QA should flag only UI-observed API behavior mismatches that escaped unit coverage.

## Completion Criteria
- #114, #115, #116 each include at least one full pass report from Daniel.
- Any failures are split into separate actionable issues and linked back.
- #117 closed after backend-impacting failures are triaged or fixed.
