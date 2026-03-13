# Workflow QA Validation Gates (0.0.1)

Purpose: define the workflow-specific release gate for issue `#250`.

## Gate A: Surface and Gating
- [ ] Workflow sidebar/menu surfaces appear only when workflow feature tier is enabled.
- [ ] Off-tier workflow execution surfaces remain hidden in release mode.
- [ ] Search/library workflows integration entry points do not expose unsupported controls.

## Gate B: Core Authoring Path
- [ ] Create a workflow from the workflow library.
- [ ] Rename and duplicate the workflow.
- [ ] Delete a workflow and verify it is removed after relaunch.
- [ ] Reorder workflows and confirm order persistence.

## Gate C: Execution Path
- [ ] Execute a workflow against at least 3 library documents.
- [ ] Output log updates during run (not only after completion).
- [ ] Run status transitions are visible and final state is correct.
- [ ] Failure path surfaces actionable error text for invalid node config.

## Gate D: Data Integrity
- [ ] Executions generate expected artifacts and attach them to source documents.
- [ ] Cancelling/deleting documents does not leave stale workflow run references.
- [ ] No orphan workflows remain after reset/delete operations.

## Gate E: API Contract
- [ ] OpenAPI contract contains expected workflow endpoints for current tier.
- [ ] Swift generated client compiles against current backend contract.
- [ ] Contract test suite passes for workflow endpoints.

## Required Evidence
- [ ] `swiftlint` output for workflow-touched files.
- [ ] `xcodebuild test` summary for workflow-related suites.
- [ ] `pytest` summary for backend workflow tests.
- [ ] One pass report from Daniel and one independent pass from Codex.
- [ ] Link all discovered failures to dedicated GitHub issues.

## Exit Criteria
Issue `#250` can be closed only when Gates A-E have explicit pass/fail entries and all failures are either fixed or tracked as accepted follow-up issues with milestone assignment.
