(AI generated. Not reviewed.)

# Capture Sessions And Resumable Upload Contract

Issue: `#2352`

Status: contract slice only. This document does **not** introduce new backend routes or OpenAPI changes.

## Purpose

Define the product contract for:

1. mobile/offline capture sessions,
2. resumable upload behavior,
3. idempotent retry semantics,
4. provenance/citation linkage expectations, and
5. security boundaries.

This slice is intentionally scoped so the app and engine can converge on names,
state transitions, and acceptance criteria **before** any new API endpoints are
added.

## Current Architecture Constraint

Today Fichero already has:

- one-shot file ingest through `POST /api/documents/import` and `/api/ingest/*`,
- document-level `provenance_chain`,
- per-image `image_provenance`,
- workflow provenance in `workflow_runs`,
- remote-host auth/token routing for signed-app remote clients.

Today Fichero does **not** have:

- a persisted backend-side upload-session resource,
- chunked/resumable upload routes,
- server-side capture-session lifecycle endpoints.

Because those route changes would require OpenAPI and backend work, this issue
defines the contract first and leaves wire-level API introduction to a follow-up
implementation issue.

## Terms

### Capture Session

A client-owned record for one logical capture/import attempt from a mobile or
camera-adjacent surface.

It groups:

- the locally captured asset(s),
- upload/retry state,
- idempotency keys,
- provenance fields known at capture time, and
- the eventual imported `document_id` once ingest succeeds.

### Upload Attempt

One network attempt to send bytes for a capture session to the configured
backend host.

### Session Identity

A stable client-generated identifier that survives app relaunch, offline queue
storage, and retry.

Recommended format:

- `capture_session_id`: UUID/ULID generated on the client at capture creation.
- `asset_id`: stable per-file identifier within the session.
- `idempotency_key`: deterministic string derived from `(capture_session_id, asset_id, logical_operation)`.

## Contract Boundary

### In Scope For This Contract

- client-side capture session state machine,
- local queue persistence requirements,
- retry and idempotency semantics,
- required provenance fields,
- required document linkage after successful ingest,
- security expectations for queued bytes and remote uploads.

### Explicitly Out Of Scope For This Slice

- new backend chunk/session routes,
- OpenAPI changes,
- SPKI/HTTPS transport hardening beyond existing policy,
- watched-folder engine implementation details,
- citation extraction algorithm changes.

## Canonical Client Model

The app should treat capture/import as a durable local record with these fields:

```text
CaptureSession
  id: String                      // capture_session_id
  created_at: Date
  updated_at: Date
  source_kind: enum              // mobile_photo, mobile_scan, watched_folder, dslr_import
  origin_device_id: String       // app-generated local device id or paired device id
  target_host: URL               // exact configured backend root; never implicit localhost
  target_library_id: String?     // optional until known
  parent_document_id: String?    // folder/collection destination if chosen
  state: enum
  assets: [CaptureAsset]
  imported_document_ids: [String]
  last_error: String?
  retry_count: Int
  idempotency_scope: String      // stable namespace for retries
  provenance_seed: CaptureProvenanceSeed
```

```text
CaptureAsset
  id: String
  local_file_url: URL
  byte_size: Int64
  mime_type: String
  sha256: String?                // computed client-side when practical
  upload_state: enum             // pending, uploading, uploaded, failed
  uploaded_bytes: Int64          // must survive relaunch for future resumable routes
  remote_receipt_id: String?     // reserved for future server-side session/chunk ack
```

```text
CaptureProvenanceSeed
  capture_started_at: Date
  capture_completed_at: Date?
  captured_by_device_name: String?
  captured_by_device_model: String?
  capture_app_surface: String    // e.g. ios_camera, ipad_library, watched_folder
  source_path_hint: String?      // watched folder / card import path, if relevant
  image_provenance: map
  provenance_chain_append: [map]
```

## State Machine

`CaptureSession.state` should follow this contract:

- `draft`: session created, no final asset committed yet.
- `queued_offline`: asset captured and persisted locally, backend not reachable or upload deferred.
- `uploading`: app is actively sending bytes to the configured host.
- `awaiting_confirmation`: bytes finished sending, waiting for imported document confirmation.
- `imported`: backend accepted ingest and returned stable `document_id` values.
- `failed_retryable`: last attempt failed but session remains eligible for retry.
- `failed_terminal`: local asset missing/corrupt, auth revoked, or contract-invalid target host.
- `cancelled`: user explicitly discarded the queued capture.

Rules:

- The app must never discard bytes just because the backend is unreachable.
- A retryable failure must preserve `capture_session_id`, `asset_id`, and idempotency keys.
- `imported` is terminal and must record the imported document ids.
- `target_host` is immutable once upload begins; changing hosts requires a new session.

## Existing-Route Compatibility Contract

Until dedicated upload-session routes exist, mobile capture should map onto the
existing single-request import path like this:

1. capture session is stored locally first,
2. when the target backend is reachable, the app performs one-shot upload/import,
3. on success, the app stores returned `document_id`,
4. client appends provenance metadata through already-supported document metadata
   surfaces or follow-up document update flows once available.

This means:

- true byte-range resumption is **not** yet guaranteed server-side,
- but local queue durability and idempotent logical retry **are** required now,
- and the client model must already track `uploaded_bytes` / `remote_receipt_id`
  so the future chunked protocol can slot in without changing local persistence.

## Retry And Idempotency Contract

### Required Behavior

- Retrying the same queued session must not silently create duplicate logical captures.
- Reopening the app must not mint a new session id for the same queued asset.
- Switching from offline to online must resume the queued session, not create a fresh one.

### Current Implementation Constraint

Because the backend does not yet expose a dedicated idempotent upload-session
resource, the contract for this phase is:

- idempotency is guaranteed **client-side first**,
- the client must suppress duplicate re-submission of the same completed session,
- the client must persist a success receipt `(capture_session_id -> document_id[])`,
- if a retry happens after ambiguous failure, the client must record that ambiguity
  and surface it for reconciliation rather than deleting the local session.

### Required Future Backend Hook

The eventual resumable-upload API must accept a stable idempotency key tied to
`capture_session_id` so the engine can answer:

- “already imported” with the original `document_id`, or
- “continue upload from offset N”, or
- “no server session exists; restart from zero”.

That future API is intentionally not specified as a route in this slice.

## Provenance Contract

Every successful capture/import path must preserve enough information to explain:

- how the digital artifact entered Fichero,
- on which device/surface it was captured,
- when the capture happened,
- whether it arrived via mobile capture, photo-library selection, watched folder, or DSLR import,
- and which workflow(s) later processed it.

### Required Mapping

At minimum, the eventual imported document should be able to express:

- `image_provenance.capture_date`
- `image_provenance.equipment`
- `image_provenance.photographer` when known
- `image_provenance.condition_notes` when capture constraints are known
- one `provenance_chain` append step indicating ingest path, e.g.:
  - `captured on iPhone`
  - `queued offline on iPad`
  - `imported from watched folder`
  - `copied from DSLR card`

### Provenance Rule

Capture provenance must describe the digital-surrogate event, not overwrite the
document’s broader historical provenance.

## Citation Linkage Contract

Shell/Capture/import itself does not create citations, but it must not block or sever
later citation extraction.

Acceptance rule:

- a document imported from a capture session must remain eligible for the normal
  citation extraction workflows,
- any citations later extracted from that document must still resolve back to the
  imported `document_id`,
- no capture-session retry or dedupe behavior may replace the document identity
  in a way that strands citations/provenance on an orphan row.

## Security Contract

### Host Selection

- queued sessions must target the explicit configured backend host,
- no remote capture/upload flow may silently substitute localhost/bootstrap,
- changing from one remote host to another requires a new session or explicit
  operator migration flow.

### Auth

- uploads must use the host-scoped auth/token path for the session’s `target_host`,
- pairing/bootstrap tokens must not leak across hosts,
- unauthenticated pairing remains separate from authenticated upload/import.

### Local Storage

- queued bytes are app-private local state,
- session metadata must not require `~/.api-key` or other development-only file assumptions,
- production remote-client behavior must remain compatible with signed-app
  host-scoped token storage.

### Replay / Duplicate Safety

- retried sessions must reuse the same logical identity,
- clients must not generate a fresh session merely because the app relaunched,
- ambiguous failures must be visible for reconciliation, not hidden behind silent duplicate upload.

## Acceptance Criteria

### Offline Queue

- a captured photo can be stored locally while the backend is unreachable,
- the session survives app relaunch,
- the queued session retains its target host and provenance seed,
- no bytes are dropped merely because the app launched without a backend.

### Retry

- when the backend becomes reachable, the same session retries instead of creating a new one,
- retryable failures remain actionable after relaunch,
- successful retry transitions the session to `imported` and records returned `document_id`s.

### Idempotency

- one logical capture session maps to at most one imported logical result from the client’s perspective,
- post-success retries are suppressed client-side,
- ambiguous failures are surfaced as ambiguous, not silently duplicated.

### Provenance / Citation Linkage

- imported documents can carry capture-path provenance in `image_provenance` and/or `provenance_chain`,
- later workflow runs append `workflow_runs` without overwriting capture provenance,
- citation extraction remains attached to the stable imported document identity.

### Security

- queued uploads use the configured host only,
- no localhost fallback occurs in remote-client mode,
- auth tokens remain host-scoped,
- local queued session metadata does not depend on development-only bootstrap token files.

## Follow-Up Implementation Split

### Phase 1: Client-Local Contract Adoption

- add Swift-side persisted `CaptureSession` / `CaptureAsset` models,
- route current mobile capture/import surfaces through the local queue,
- map successful queue flushes onto existing one-shot import routes,
- write focused tests for session persistence, retry, and host immutability.

### Phase 2: Backend Upload Session Resource

Required before true resumable byte-range upload is claimed:

- persisted backend upload-session model,
- idempotency-key lookup,
- offset/chunk acknowledgement contract,
- completion/finalize step that returns stable `document_id`s,
- OpenAPI + client regeneration.

That phase requires backend API work and is intentionally deferred from this issue slice.
