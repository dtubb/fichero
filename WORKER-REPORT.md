# Worker Report — Networking: OpenAPI-only (milestone #101)

Author: Claude (commits authored as Claude, co-authored Daniel Tubb). **Not pushed.**
Branch base: `c224697b` (origin/main). Date: 2026-06-28.

## Milestone state — important

`gh issue list --milestone 'Networking — OpenAPI-only (kill hand-rolled URLSession)' --state open`
returns **exactly one issue: EPIC #2410** "convert all hand-rolled URLSession services to the
generated OpenAPI client." There are **no separate child issues** to pick 3-5 from — the whole
milestone is that one EPIC, and the EPIC body is its own offender checklist.

The EPIC is **build-gated Swift frontend work** (rewriting request-building in Swift services to call
typed generated operations). A swiftlint-only worker cannot verify a networking conversion compiles
or round-trips, and a broken base client breaks the whole app. So I did the parts that are
**provably safe without an Xcode build** and produced an **accurate re-audit** (the EPIC's 2026-06-20
list is substantially stale) so the build-capable lane can finish efficiently.

## Done (committed, safe, gated)

**`refactor(net): drop dead OpenAPIURLSession import from converted services (#2410)`**
- `ActivityServiceGenerated.swift` and `ImportServiceGenerated.swift` are already fully converted —
  every call goes through `client.api.*`. Neither references any `OpenAPIURLSession` /
  `URLSessionTransport` symbol (the raw transport is built once inside `FicheroClient` in the
  api-client package), so `import OpenAPIURLSession` was dead. Removed from both.
- Gate: `swiftlint` clean on both files (pre-existing file/body-length warnings in
  ImportServiceGenerated untouched). Removing an unused import cannot change compilation; verified by
  grep that no transport symbol remains.

## Accurate re-audit of EPIC #2410 (replaces the stale 2026-06-20 list)

Counts are real request-building sites (`URLRequest(` / `session.data|bytes|download(for:)` /
`URLSession(`/`.shared`), excluding comments.

**Already converted — EPIC entries now stale (no URLSession/URLRequest at all):**
`AppState.swift`, `EngineConfig.swift`, `AppleScriptSupport.swift`, `StorageServiceGenerated.swift`
(only a doc comment), `ActionLibraryService.swift`, `ActionsService.swift`, `IntegrationsService.swift`,
`ModelComparisonService.swift`, `WorkflowExecutionService.swift`. The EPIC checklist should be ticked
for these.

**Real remaining offenders (need a build lane — typed-client conversion):**
| File | sites | Notes |
|------|-------|-------|
| `APIClient.swift` | 18 | The base hand-rolled client. The core of the EPIC; converting it is the big, app-critical change — must be done with an Xcode build. |
| `ArtifactServiceGenerated.swift` | 22 | Mostly **binary** artifact/image downloads. |
| `ImageEditingServiceGenerated.swift` | 10 | **Binary** image ops. |
| `ActionInvokeService.swift` | 4 | JSON actions — likely convertible once a typed op is confirmed. |
| `DocumentStore+CRUD.swift` | 2 | |
| `EmbeddedBackendService.swift` | 2 | Local backend lifecycle/health. |
| `APIClient+Types.swift`, `WorkflowServiceGenerated.swift`, `DocumentKGWebPane.swift`, `QuickLookComponents.swift`, `FicheroWebView.swift` | 1-2 each | Mixed; several are binary/WebKit. |

**SSE streaming — explicit Daniel-decision (EPIC says "decide"):**
`ActivityStreamService.swift`, `LibraryChangeStream.swift`, `WorkflowStreamService.swift` use
`URLSession.bytes(for:)` on the pinned session. Keep on the pinned transport vs OpenAPI streaming is
a design call — left untouched.

**The binary blocker (why many of the above are hand-rolled by necessity):**
swift-openapi can't model `image/png` etc. responses as bytes when the backend route mis-declares the
response media type. The diagram endpoints are the clearest case — and I found a **latent bug** worth a
ticket:

> `GET /api/workflow-execution/workflows/{id}/visualization.png`
> (`api/routes/workflow_execution/visualization.py:100`) is annotated `-> WorkflowVisualizationResponse`
> and just delegates to the JSON `…/visualization` endpoint — it returns **JSON (mermaid_code), not a
> PNG**. But `WorkflowServiceGenerated.fetchDiagramImage` does `PlatformImage(data: data)` on the
> response, which always fails → **workflow diagrams never render**. The real fix is a design decision
> (render mermaid client-side, or have the backend actually produce a PNG/SVG and declare
> `image/png`/`image/svg+xml` so OpenAPI models it as binary and the typed client can return bytes).
> Recommend filing this under #2410 / #1893.

## NOT done (and why)
- `APIClient.swift` base-client conversion and the other request-building services: build-gated; a
  swiftlint-only lane cannot verify them and a wrong typed-op call breaks the app. For the build lane.
- SSE services: Daniel-decision.
- The diagram/visualization binary fix: latent bug + design decision (client-side mermaid vs server
  image) — flagged above, not implemented.

## Gate results
- `swiftlint` clean on the two edited files (no new violations).
- No Python/docs changes this pass, so ruff/pytest/mkdocs not exercised.
- Did **not** run `xcodebuild` (house rule + Xcode lock); manager build-verifies Swift.
- Did **not** push.
