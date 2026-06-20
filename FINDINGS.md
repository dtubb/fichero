# Findings — openapi-activity worker lane

## What changed

- `fichero/fichero/Services/ActivityServiceGenerated.swift`
  - Import order fixed for swiftlint.
  - Conversion helpers (`convertToActivityItem`, `convertToActivityStats`, `convertToCheckpointHistory`, `convertToWorkflowRun`) moved from the `@MainActor` class body to a file-private extension to resolve the `type_body_length` warning and to make them testable.
  - `convertToCheckpointHistory` signature split to fix the `line_length` warning.
  - Conversion helpers changed from `private` to internal so `FicheroTests` can exercise them via `@testable import Fichero`.
  - No hand-rolled `URLSession`/`URLRequest` code remains; the service already calls the generated `FicheroAPIClient` operations (`getRecentActivitiesApiActivityRecentGet`, `listActivitiesApiActivityGet`, `getActivityStatsApiActivityStatsGet`, `getWorkflowActivityApiWorkflowWorkflowIdGet`, `getBatchActivityApiActivityBatchBatchIdGet`, `cleanupOldActivitiesApiActivityCleanupDelete`, `getThreadHistoryApiWorkflowExecutionThreadsThreadIdHistoryGet`, `getWorkflowRunApiWorkflowExecutionThreadsThreadIdRunGet`).

- `fichero/fichero-tests/ActivityServiceGeneratedTests.swift`
  - New test suite covering response mapping from generated OpenAPI schema types to app domain types:
    - `convertToActivityItem` preserves declared fields and coerces `metadata` values to strings.
    - `convertToActivityStats` unwraps typed `additionalProperties` maps for `activitiesByType` / `activitiesByLevel`.
    - `convertToCheckpointHistory` passes through the caller-supplied `threadId` and unwraps dynamic `stateValues` / `writes`.
    - `convertToWorkflowRun` unwraps `workflowSnapshot`, `nodeNameMap`, and `progressTimeline`.

## Operation used

The generated `FicheroAPIClient.Client` operations are used end-to-end. Auth, certificate pinning, and library-path injection stay in `FicheroClient` middleware, so the service does not hand-roll transport configuration.

## What needs a build

- Xcode build + `FicheroTests` run (manager/integrator lane) to confirm:
  - `ActivityServiceGenerated.swift` still compiles after the extension refactor.
  - The new `ActivityServiceGeneratedTests.swift` compiles and runs against the generated `Components.Schemas` types.
  - The Activity view populates correctly now that the generated client is in use (validates #2392 fix).

## Notes

- `fichero-tests` is a `fileSystemSynchronizedGroups` target, so the new test file is auto-registered; `scripts/add-swift-file.rb` was not needed for it.
- Did not run `xcodebuild` per lane instructions (manager owns the Xcode MCP build).
- Did not push.
