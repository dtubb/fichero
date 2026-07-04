# Hand-rolled URLSession Audit (#1666)

Audit of raw `URLSession`/`URLRequest` in `fichero/fichero/**` (the app, not the
`fichero-api-client` package — that is already clean and enforced by
`scripts/check_no_raw_urlsession.py` / #2393). Goal: display backend objects
through the generated OpenAPI client (`FicheroAPIClient`), reserving custom
transport for cases the generated client genuinely can't serve — and only behind
the one pinned/authed transport (`RemoteCertificatePinning.configuredSession()`
+ `addEngineAuth(libraryPath:)`).

## Headline finding

The **acute** risk this issue was filed for — hand-rolled calls to library-scoped
routes that omit `X-Fichero-Library-Path` (the annotations/notes silent-empty
bug class) — is **resolved** in the sites originally flagged:

- `WorkspaceItemPicker` now takes `DocumentServiceGenerated` (no raw URLSession).
- The entity/inspector fetches in `ArtifactServiceGenerated`
  (`listEntitiesForDocument`, `listInspectorEntitiesForDocument`) use the
  generated client and **throw** on non-`.ok` responses — no silent `[]`.

**Every** remaining raw site already uses the pinned session
(`RemoteCertificatePinning.configuredSession()`) and `addEngineAuth(...)` with
the library path where the route is library-scoped. So the residue is a
**maintainability / schema-drift** migration (hand-built request vs typed
generated operation), not an open security hole.

## Site inventory (real network calls; WebKit/comments excluded)

### KEEP — custom transport genuinely required

| File | n | Why legit |
|---|---|---|
| `Services/EmbeddedBackendService.swift` | 4 | Engine health poll + process lifecycle — localhost, app-wide, runs **before** the generated client/auth exists (readiness bootstrap). |
| `Services/WorkflowStreamService.swift` | 1 | SSE via `urlSession.bytes(for:)` — the generated client does not stream. Pinned session, class-retained (the #2605/#2608 delegate rule). |
| `Services/LibraryChangeStream.swift` | 1 | SSE (change stream). Same rationale. |
| `Services/ActivityStreamService.swift` | 1 | SSE (activity). Same rationale. |
| `App/AppState.swift` | 1 | `probeAuthenticatedRegistry` — auth/readiness probe returning only the HTTP status; app-wide, no library header by design. |
| `Models/DocumentStore+CRUD.swift` | 1 | Multipart `documents/import` upload — pinned + auth; multipart is awkward through the generated client. Revisit only if a generated multipart op lands. |
| WebKit: `DocumentKGWebPane`, `FicheroWebView` | — | `WKWebView` + SPKI pinning; not a URLSession data path. |

### MIGRATE — hand-rolled data ops with generated equivalents (sub-issues)

| File | n | Target |
|---|---|---|
| `Services/APIClient.swift` | 9 | The legacy hand-rolled JSON client. Umbrella: move callers (`apiClient.get/post`, e.g. `SourceOutlineView` → `document_outline`) onto the generated `FicheroClient`, then retire the raw request builders. Largest; stage by caller. |
| `Services/ImageEditingServiceGenerated.swift` | 5 | `/api/images/*` — route through the generated image operations. |
| `Services/ArtifactServiceGenerated.swift` | 2 | Remaining hand-built artifact/list `GET`s → generated `list_all_artifacts` etc. (the entity fetches are already migrated). |
| `Services/ActionInvokeService.swift` | 2 | `POST /api/actions/invoke` → generated action op (carries auth + library path + origin-window today). |
| `Services/WorkflowServiceGenerated.swift` | 1 | One residual raw request → generated workflow op. |

## Migration rules (for each sub-issue)

1. Use the generated `client.api.<operation>` and its typed response.
2. **Throw** on non-`.ok` (never decode a failure as `[]`/empty UI state —
   `prefer-raise-over-silent-fallback`).
3. Library-scoped routes carry the library path (generated `LibraryPathMiddleware`
   handles this centrally — that is the whole point of migrating).
4. Binary/byte endpoints that must stay custom go behind **one** audited storage
   wrapper (`StorageServiceGenerated`) that always sets the library path and
   never swallows status/decode failures.

## Enforcement (closed — #3031)

`scripts/check_no_raw_urlsession.py` scans only the client **package**.
`scripts/check_no_raw_urlsession_app.py` now covers the **app**
(`fichero/fichero/**`) as a ratchet: all 12 current raw-transport files are
grandfathered, so a NEW file with raw URLSession fails the gate. As the MIGRATE
sub-issues land, drop their entries from `GRANDFATHERED_FILES` (the check reports
stale entries). Auto-wired via the `scripts/check_*.py` gate convention; has a
`--self-test`.
