(AI generated. Not reviewed.)

> **ARCHIVED 2026-06-27** — historical point-in-time audit. All tracked issues
> (#1412–#1417, #1710) are now CLOSED and the recommendations here are fully done.
> Kept for provenance only; do not treat its code line-refs as current.

# API Consistency Audit

Date: 2026-06-07
Branch: `chore/api-architecture-pass2`
Scope: generated-client supersession check for #1412-#1417, remaining Swift raw transport/model drift, backend `response_model` gaps, blocking-route candidates, and endpoint coverage status for #1443.

## Supersession Verdict: #1412-#1417

| Issue | Verdict | Evidence |
| --- | --- | --- |
| #1412 generate `Endpoints.swift` | Superseded | The canonical endpoint surface is now the generated Swift package plus `FicheroClient`, not a hand-maintained path enum. See [fichero/fichero-api-client/Sources/FicheroAPIClient/FicheroClient.swift](fichero/fichero-api-client/Sources/FicheroAPIClient/FicheroClient.swift:22) and the schema sync pipeline in `fichero-engine/scripts/sync_openapi_schema.sh`. |
| #1413 shared `EngineRequest` helper | Superseded in intent | `FicheroClient` already centralizes transport and middleware, and `LibraryPathMiddleware` is the shared request-layer fix for header correctness. See [FicheroClient.swift](fichero/fichero-api-client/Sources/FicheroAPIClient/FicheroClient.swift:45) and [LibraryPathMiddleware.swift](fichero/fichero-api-client/Sources/FicheroAPIClient/LibraryPathMiddleware.swift:5). Building a second hand-rolled request abstraction would duplicate the generated stack. |
| #1414 | Superseded by generated-client migration work | Actions transport is already de-duplicated onto one generated-client path. See [fichero/fichero/Services/ActionsService.swift](fichero/fichero/Services/ActionsService.swift:5) and commits `22a0af6e` / `e192e28e` (#1711). |
| #1415 | Superseded by generated-client migration work | Workflow execution already routes through `FicheroClient`. See [fichero/fichero/Services/WorkflowExecutionService.swift](fichero/fichero/Services/WorkflowExecutionService.swift:8) and commits `562d1b22` / `6956d5e5` (#1712). |
| #1416 | Superseded by generated-client migration work | Integrations already route through `FicheroClient`. See [fichero/fichero/Services/IntegrationsService.swift](fichero/fichero/Services/IntegrationsService.swift:6) and commit `69f931af` (#1713). |
| #1417 | Largely superseded; only residual sweep remains | Model comparison moved first (`c76176ef`, #1666), then the tier-2 stragglers moved (`9d883ca8`, #1714). Pass 2 moved `ResearchService` onto `FicheroClient`; remaining raw transport is now concentrated in `ArtifactServiceGenerated`, `ImageEditingServiceGenerated`, and a few justified SSE/binary call sites. |

### #1710 status

#1710 is **not** superseded. Phase 1 already landed: the generated client has a real `LibraryPathMiddleware` and `FicheroClient` wires it in centrally. The remaining #1710 Phase 2 work is the mechanical removal of now-redundant per-call-site `xFicheroLibraryPath` arguments.

## Remaining Swift Raw Transport

### Still hand-rolled and should be treated as migration backlog

- [fichero/fichero/Services/ArtifactServiceGenerated.swift](fichero/fichero/Services/ArtifactServiceGenerated.swift:116)
  Large residual raw transport surface. Notable direct sites: all-artifacts list, citation usages, library entity-type registry, classification list reads, and hermeneutics interpretation/framework reads and writes.
- [fichero/fichero/Services/ImageEditingServiceGenerated.swift](fichero/fichero/Services/ImageEditingServiceGenerated.swift:103)
  Entire `/api/images` router is still raw `URLSession`; comments explicitly say it was kept raw for path visibility to the wiring checker.
- [fichero/fichero/Models/DocumentStore+CRUD.swift](fichero/fichero/Models/DocumentStore+CRUD.swift:212)
  Multipart `/api/documents/import` upload is still hand-built.
- [fichero/fichero/Views/MindPalace/SpatialScene3D.swift](fichero/fichero/Views/MindPalace/SpatialScene3D.swift:463)
  View-level direct request, not routed through a generated service wrapper.

### Raw transport that appears intentional / legitimate

- [fichero/fichero/Services/WorkflowStreamService.swift](fichero/fichero/Services/WorkflowStreamService.swift:142)
  SSE stream subscription; generated client cannot consume `text/event-stream`.
- [fichero/fichero/Services/BatchServiceGenerated.swift](fichero/fichero/Services/BatchServiceGenerated.swift:128)
  SSE kickoff path; same limitation.
- [fichero/fichero/Services/StorageServiceGenerated.swift](fichero/fichero/Services/StorageServiceGenerated.swift:14)
  Binary/image fetches.
- [fichero/fichero/App/AppState.swift](fichero/fichero/App/AppState.swift:80)
  App-lifecycle `/api/health` probe and settings bootstrap.
- [fichero/fichero/Services/EmbeddedBackendService.swift](fichero/fichero/Services/EmbeddedBackendService.swift:277)
  Embedded backend lifecycle checks.
- [fichero/fichero/App/WelcomeView+OnboardingWizardActions.swift](fichero/fichero/App/WelcomeView+OnboardingWizardActions.swift:49)
  External provider probes, not Fichero backend transport.

## Hand-Rolled Swift Models Still Duplicating Backend Shapes

- [fichero/fichero/Models/ResearchModels.swift](fichero/fichero/Models/ResearchModels.swift:45)
  Research project/plan/task/note/source/checklist types are still frontend-owned duplicates even though transport now runs through the generated client.
- [fichero/fichero/Models/SpatialModels.swift](fichero/fichero/Models/SpatialModels.swift:98)
  Mind Palace room/node/connection/stack/viewport types remain hand-rolled even though the backend exposes typed responses.
- [fichero/fichero/Models/Document.swift](fichero/fichero/Models/Document.swift:334)
  Manual response envelopes like `DocumentListResponse`, `SearchResponse`, and `StatsResponse` still exist beside generated schemas.
- [fichero/fichero/Services/AnnotationService.swift](fichero/fichero/Services/AnnotationService.swift:56)
  `DocumentAnnotation` is still a manual duplicate.

## Backend Routes Missing Explicit `response_model`

`fichero-engine/tests/contracts/endpoints.json` currently records 42 OpenAPI operations with `response_model = null`.

### Legitimate null-model cases

- Binary / HTML / streaming responses: IIIF image routes, storage binary routes, view HTML routes, workflow/batch SSE routes.
- `204` / no-body delete routes where the endpoint truly returns no payload.

### Actionable route families still worth converting

- `/api/annotations/{annotation_id}` and `/api/annotations/{annotation_id}/crop`
- `/api/artifacts/{artifact_id}`
- `/api/batches/{batch_id}/execute`, `/resume`, `/retry`
- `/api/claims/{claim_id}` and `/api/entities/{entity_id}`
- `/api/documents/{doc_id}` and `/api/documents/{doc_id}/notes`
- `/api/storage/stats`

## Blocking / Event-Loop Risk Candidates

These are candidates, not fully-audited fixes:

- `fichero-engine/src/fichero/api/routes/image_editing.py`
  PIL image transforms, segmentation, and preview generation are synchronous and potentially expensive.
- `fichero-engine/src/fichero/api/routes/local_models.py`
  Model management is filesystem/network heavy; download initiation is backgrounded, but list/delete paths are still sync functions.
- `fichero-engine/src/fichero/api/routes/documents.py`
  Import and PDF backfill routes are the main I/O-heavy document paths.
- `fichero-engine/src/fichero/api/routes/workflow_execution/core.py`
  The route comments already reference event-loop starvation concerns around workflow execution.

## Endpoint Coverage Snapshot (#1443)

- OpenAPI surface after regen: 587 endpoints across 55 resources.
- CLI intentional no-coverage allowlist: 4 endpoints only.
  `/api/activity/stream`, `/api/storage/debug/{doc_id}`, `/api/tasks/tasks/health`, `/api/workflow-execution/stream/{thread_id}`.
- SwiftUI allowlist backlog: 246 endpoints in `fichero-engine/tests/contracts/ui_wiring_allowlist_swiftui.json`.

### Main SwiftUI no-consumer clusters still on the backlog

- Actions secondary endpoints (`builtin`, `categories`, `popular`, `recent`, `search`, `export`, `use`)
- Batch management
- Chains
- Integrations long tail
- Library entity-type registry
- MCP / migrations / schedules / tasks / triggers
- Large parts of mind-palace CRUD
- Provider/registry management
- Workflow-execution admin/cache/visualization endpoints

### Coverage notes

- The CLI surface is close to complete; its remaining omissions are intentional.
- The SwiftUI backlog is still large enough that #1443 should remain open after this pass.
- A few allowlist entries are likely stale because the app now calls those paths indirectly or through new wrappers. Re-running `scripts/check_ui_wiring.py` after each migration batch should be part of the cleanup.

## Safe Batch Landed In This Pass

- Migrated `SearchServiceGenerated.keywordCloud()` off a hand-written `URLSession` request and onto the generated OpenAPI client.
- Moved the action and local-model response envelopes into `fichero.models`, added explicit `response_model=` coverage to those legacy routes, and added an OpenAPI regression test for them.
- Added shared explicit response models for `/api/health`, `/api/stats`, `/api/search/stats`, `/api/workflows/reinstall-defaults`, and the remaining provider detail/probe routes; regenerated `openapi.json` and the Swift client schema.
- Migrated `ResearchService` off legacy `APIClient` transport onto generated `FicheroClient` operations while preserving the existing research UI-facing model layer.

## Remaining Recommended Work

- Close #1412 and #1413 as superseded.
- Close or re-scope #1414-#1417 around the **actual** remaining transport debt (`ArtifactServiceGenerated`, `ImageEditingServiceGenerated`, multipart upload helpers), rather than the old Endpoints/EngineRequest plan.
- Keep #1710 open for Phase 2 header-arg cleanup.
- Keep #1443 open. The CLI side is almost done; SwiftUI endpoint coverage is not.
