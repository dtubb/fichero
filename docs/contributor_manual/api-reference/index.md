---
hide:
  - toc
---

(AI generated. Not reviewed.)

# API Reference

!!! warning "Work in progress, unstable"
    The Fichero API is still in progress. Endpoints and response shapes will
    change before 1.0, and this is not yet a stable contract. Do not build
    against it expecting backward compatibility.

The Fichero engine is a FastAPI application that exposes an OpenAPI 3 schema.
The interactive reference below is rendered from the committed schema
(`openapi.json`, copied from `fichero-server/tests/contracts/openapi.json`).

That committed schema is the real backend surface used to generate the Swift
client and document the engine routes. In the current contract it includes route
families for documents, search, workflows, workflow execution, annotations,
providers, knowledge-graph endpoints, canvas endpoints (the former
mind-palace routes, renamed to `/api/canvas`), and more.

## Connected clients

`GET /api/clients`

- Purpose: which surfaces are currently talking to this engine — the app,
  the `fichero` CLI, an MCP client — each with its transport (`uds`, `tcp`),
  request count, and first/last seen times. Sharing settings renders this so
  a user can see that the command-line tool and MCP server really are
  connected, rather than inferring it from a successful command.
- Presence, not authorization: entries come from the `X-Fichero-Client`
  header recorded during auth enforcement, so an unnamed caller is attributed
  by transport rather than rejected.

## Signing in by a client's key (#2403)

`POST /api/auth/challenge` and `POST /api/auth/sign-in` sign a registered client (a paired device or the app) in
with its own key instead of a password.

- `POST /api/auth/challenge` `{client_id}` answers a single-use `nonce`, `expires_in` (60 seconds), `expires_at` and
  this engine's `engine_id`. At most 5 challenges are outstanding per client; an older one is dropped. An unknown and a
  revoked client get the same 401, so client ids cannot be probed.
- `POST /api/auth/sign-in` `{client_id, nonce, signature}`: the signature is ECDSA P-256 / SHA-256 over
  `fichero-sign-in-v1`, the engine id, the client id, the nonce and its expiry, NUL-separated, so a signature made for
  another engine, client or expiry never verifies. The nonce is spent whether or not the signature is good. A good
  one answers `session_token`, the `user` and the `client`; anything else is 401 "sign-in refused", and more than 10
  failed sign-ins a minute for one client is 429 with `Retry-After: 60`.

## W3C annotation export

`GET /api/documents/{doc_id}/annotations.jsonld`

- Purpose: export a document's annotations as a W3C Web Annotation
  `AnnotationPage`, including the JSON-LD context and annotation targets.
- Path param: `doc_id` (required string), the source document id.
- Response: `200` with the JSON-LD AnnotationPage object; missing documents
  return `404`.

## Document outline view (Mandate 1, 2026-08-24)

`GET /api/documents/{doc_id}/view`

- Purpose: one answer for "where am I, what's in here, what does it have" —
  ancestors root-first, the anchor document, level-aware children, and an
  attachment summary (renditions, artifacts, annotation/entity counts). The
  ONE outline endpoint every tree consumer (sidebar, grid, breadcrumbs,
  entry ladder, dataset router) migrates onto, replacing five client-side
  tree builders that each cached and disagreed.
- Query params: `level` (`stored` default — the sidebar's structural tier;
  `content` looks through containers, the grid's tier), `children` and
  `attachments` (booleans; a cheap caller skips halves).
- Response: `200` `DocumentViewResponse`; unknown ids return a declared
  `404`.

## Renditions (bbox program, 2026-08-20)

`GET /api/documents/{document_id}/renditions`

- Purpose: list a document's renditions — the same page in different pixel
  frames (archival original, enhanced, background-removed). The engine
  returns them in canonical order (primary first, then role preference), so
  every client agrees what "next" means. Missing documents return a declared
  `404`.

`GET /api/documents/{document_id}/renditions/{rendition_id}/content`

- Purpose: the bytes of one named rendition, for the preview's up/down
  rendition flip. Unknown document or rendition id returns a declared `404`.
  Not yet called from Swift — tracked in the ui-wiring baseline until the
  flip control is wired.

## Prototype attributes and the dataset query (datasets Stages 1–2)

`GET /api/documents/{doc_id}/effective-attributes`

- Purpose: a node's structured data, resolved — attribute declarations from
  its prototype chain (typed, with renderer roles) plus effective values
  (chain defaults overlaid with the node's own `attributes`). Unresolvable
  prototypes return `422`, never partial data.

`POST /api/documents/{doc_id}/proposed-kind/accept` and `POST /api/documents/{doc_id}/proposed-kind/reject`

- Purpose: answer the kind a run proposed for a node (#5600, ruled 2026-10-08:
  a run proposes, a person decides). `GET /api/documents/{doc_id}` shows the
  pending proposal at `metadata.proposed_attributes.prototype` with its
  evidence (run, artifact, model, what it said). Accept assigns the prototype
  through `document.assign_prototype`, with the run as source and the person as
  `accepted_by`; reject (`document.reject_proposed_kind`) keeps the proposal
  marked rejected, so the same kind is not proposed again. Both are audited, and
  undo puts the proposal back as waiting. Answer:
  `{document_id, prototype_key, state, audit_id}`.

`GET /api/classifications/resolved/{key}`

- Purpose: one prototype's chain-merged declarations and defaults — the
  editor's inheritance preview. Unknown key or cycle returns `422`.

`POST /api/documents/dataset/query`

- Purpose: the one renderer query over a folder's attribute-bearing rows —
  server-side sort (typed, nulls last), typed filters, paging, date binning
  (year/month/day, for timeline and calendar), and facet counts, all via
  DuckDB `json_extract` per the Stage 2 measurement. The response carries
  each involved prototype's chain-merged defaults so clients overlay a page
  cheaply; a prototype that no longer resolves reports its error string
  under `_unresolved`.

## Transfer between projects (#5657)

`POST /api/documents/transfer`

- Purpose: copy a selection (each item with its live subtree) from another open
  project into this one — the library header names the TARGET, the body names the
  `source` package, `items`, `target_parent_id` (absent: the target's Sources
  folder), `mode` and `dry_run`. Runs the audited action `document.transfer` in the
  target (undo: `document.untransfer`, which sends the copies to the target's Trash
  and withdraws the merges it proposed).
- `dry_run: true` writes nothing in either project and returns the plan.
- Answer (`TransferResult`): counts by kind (planned, and written after the
  read-back), files and bytes copied, linked originals (the reference travels, not
  the file), vocabulary matched by key or made, entity matches proposed as
  `EntityMatchCandidate` (method `transfer`, never merged by the transfer), every
  edge cut and why, items left behind, the new top-level ids (`copies`) and the
  `audit` row to undo (`POST /api/actions/audit/{audit}/undo`).
- `mode: move` copies and checks first, then sends the source's items to the
  source's Trash through `document.delete` with `moved_to` (the Trash lists them
  "moved to <project>") in one audited source action, `document.transfer_out`, which
  also cuts what cannot follow (canvas places and links, workspace slots, aliases,
  synced-folder ties) and lists each in `cuts`. If that step fails twice the copy is
  taken back (500, in words). Undo works from the target's `document.transfer` row
  or the source's `document.transfer_out` row; both projects must be open.
- Refused in words, changing nothing: source not open (409), same project (400),
  unknown item (404), trashed item or alias ("Aliases stay within a project.",
  409), locked node (403), target not a folder (400), an item a pending move
  holds ("These items are already being moved to <project>.", 409). A failure while
  writing rolls the target back (500, the reason in words); the record
  (`TransferRecord`, one per project) keeps the journal, and a move a crash left
  half-way finishes when both projects are open.
- Spec: `docs/contributor_manual/specs/source/moving-between-projects.md`.

## Copy between machines (#5657)

Between machines a transfer is always a copy. The sending engine pushes; the far engine lands.

`GET /api/machines` · `POST /api/machines/pair` · `DELETE /api/machines/{machine_id}` (forget a machine: removes this Mac's saved token, owner only)

- The other Fichero engines this one is paired with, and pairing with one: `address`
  (its tailnet name, `name.tailnet.ts.net`) and the `code` its Fichero shows. This
  engine becomes a paired device there; the token is kept in the Keychain, never
  returned.

`POST /api/documents/transfer/to-machine`

- On the SENDING engine (the library header names the source project): `items`,
  `machine`, `target_project` (its package path there), `target_parent_id`,
  `pages_may_leave` (required yes), `resume` (a stopped copy's id: only what had not
  arrived is sent). Audited as `document.transfer_to_machine`. Answer: the far side's
  `TransferResult`, with `machine`, `objects_sent` and `linked_elsewhere`. 502 when the
  send stops: what arrived is kept there, nothing landed.

`POST /api/documents/transfer/incoming` ·
`PUT /api/documents/transfer/incoming/{transfer_id}/objects/{sha256}` ·
`POST /api/documents/transfer/incoming/{transfer_id}/land` ·
`DELETE /api/documents/transfer/incoming/{transfer_id}`

- On the RECEIVING engine (the library header names the target project; the device
  token names the person): open a copy (its `SyncManifest`; refused when the
  contract sha256 differs) and learn which objects are missing; take one object
  (octet-stream, re-hashed on arrival; 422 when damaged); land it all or nothing as
  the audited action `document.transfer_in` (undo: `document.untransfer`); or abandon
  it, removing what arrived.

## Pages in iCloud (#5669)

`GET /api/documents/in-icloud` · `POST /api/documents/copy-into-project`

- The project's pages (or one folder's, `folder_id`) whose linked originals are in iCloud and not on this
  Mac: how many, their size, a sentence, whether this disk has room, and the offer to copy them into the
  project (`document.copy_into_project` and its params). Null when none. The Start plan (`in_icloud`) and a
  finished import's status (`in_icloud`) carry the same answer; Start is refused only when the disk cannot
  hold them.
- The copy (audited, undoable): each original brought down (bounded), copied by the import's Copy path, the
  page then pointing at its own copy (`metadata.copied_from` keeps where it was). Undo points the pages back
  at their originals and removes the copies it made.

## Locate Originals (#5672)

`GET /api/documents/missing-originals` · `POST /api/documents/relink-originals/plan` ·
`POST /api/documents/relink-originals`

- Linked pages whose originals are not where the project says, said once with the folders they were in
  (null when none).
- With the folder the originals are in now (`new_root`, optionally one `folder_id`): the plan matches each
  missing original by its path below the old root (the longest tail), ties broken by size and checksum, never
  by name alone; lists the ones not found and the ambiguous ones; and names the folders whose root moves with
  them. The action (`document.relink_originals`, audited, undoable) repoints the matched pages and folders and
  their recorded source paths. Server paths: owner only, inside an allowed location.

## Making a cluster's key (#5238)

`POST /api/hpc/clusters/{cluster_id}/key/make` · `GET /api/hpc/clusters/{cluster_id}/key/public`

- The engine makes the cluster's Ed25519 pair with the system `ssh-keygen`; the private half stays in the engine's
  folder (mode 0600) and is never returned. `make` answers `{cluster_id, public_key}`, to add to the person's own
  cluster account (CCDB on the Alliance); 409 if a key is already made (it would orphan the one already added).
  `public` shows the same public half again (404 before one is made). Owner only. `DELETE .../key` removes both halves.

## Remote runs in Activity (#5740)

`POST /api/reading-at-scale/jobs/{job_id}/catch-up`

- Look at the far side now, after the Mac slept: a live run skips its next wait once; a run the scheduler dropped
  (paused or failed with shards still out) is queued again and carries on from its recorded shards. Answers
  `{job_id, state}`; 404 for an unknown run; 409 for a run that has ended (completed, cancelled, or failed with no shard still out): a finished run is never resent. `parent_job_id` on a start must be an existing run or step job (422 otherwise). `GET /api/reading-at-scale/jobs/{job_id}` now also answers the
  run's `target`, `far_state`, `shards_done`/`shards_total`, `pages_landed`, each shard, `estimate` and `actual`; a
  run in `GET /api/activity/jobs` carries a `remote` summary and its `parent_id` (the step that sent it).

## Set Up, one page per stage (#5668)

`GET /api/recipes/stages`

- The eleven stages of Set Up in order (section 7c of `source/models-chains-and-projects.md`): each with its
  title, sentence and example, the registry jobs it carries, whether this project's recipe has it on, its own
  questions (each a `job_answers` key, with options, its default and this project's answer), the stages it
  needs and why in words, and whether it can be tried on the sample pages (by the bake-off, or by its
  workflow). Without an open project every stage is off and every answer its default.
- `money_and_place` (#5769): the project's Hugging Face cap (`hf_spend_cap_usd`), whether working copies may
  stay on a cluster as it stands (`copies_may_stay_on_cluster`) and whether that still follows pages-may-leave
  because the person has not answered it (`copies_follow_pages_may_leave`), and the clusters set up here
  (`clusters`, by name; the copies question applies only where there is one; empty for a caller who is not
  the owner, as every `/api/hpc` route is owner-only, and so is the Start plan's cluster offer). This month's spend against the cap
  is on the Start plan (`hf_spend`).

`GET /api/recipes/hands` · `GET`/`PUT /api/recipes/samples` · `POST`/`GET /api/recipes/stages/{stage}/try`

- Which hand: the curated hands for a script, those of the period's centuries, each with its Hugging Face tags
  (they join the reader search); the answers keep `period` and `hands` (typed hands kept as typed).
- The sample pages: the person's choice, else 3 to 5 proposed across the material, each with why.
- Try a stage on them: Read and Find Lines start the bake-off on the samples; any other stage runs its own
  steps on a copy of the samples (a `try-a-stage` job), its result kept beside the setup, never the
  project's work; a stage using the cloud is refused (402) with its cost until `cost_ok`.

## Fold endpoints documented here

The node-model fold shipped backend storage changes this session, but the API
surface is still route-based. The paths below are the committed public
contract in `fichero-server/tests/contracts/openapi.json`.

### `/api/bookmarks`

`POST /api/bookmarks`

- Purpose: create a bookmark node that points at another document.
- Request body: `BookmarkCreate`
  - `target_id` (required string): the target document id.
  - `parent_id` (optional string or null): parent bookmark container.
  - `name` (optional string or null): override display name for the alias node.
- Response: `201` with a `Document` object.
  - The route code creates the bookmark through alias machinery and then sets
    `prototype_key="bookmark"`, so the returned document is the alias-backed
    bookmark node rather than the resolved target.

`GET /api/bookmarks`

- Purpose: list bookmark nodes.
- Query params:
  - `parent_id` (optional string): filter by parent bookmark container.
- Response: `200` with `DocumentListResponse`.
  - `items`: array of `Document` rows.
  - `count`: total rows returned.

### `/api/bookmarks/{bookmark_id}/resolve`

`GET /api/bookmarks/{bookmark_id}/resolve`

- Purpose: resolve a bookmark node to its current target document.
- Path params:
  - `bookmark_id` (required string): bookmark document id.
- Response: `200` with a `Document` object for the live target.
- Failure behavior from the route code: a dangling or missing bookmark target is
  returned as `404`, not a partial alias object.

### `/api/search/saved`

These saved-search endpoints still expose `SavedSearch*` request and response
models even though saved searches are folded into node-backed storage in the
backend.

`GET /api/search/saved`

- Purpose: list all saved searches.
- Response: `200` with `SavedSearchListResponse`.
  - `items`: array of `SavedSearchResponse`.
  - `count`: total rows returned.

`POST /api/search/saved`

- Purpose: save a search for later.
- Request body: `SavedSearchCreate`
  - `query` (required string).
  - `is_smart_search` (optional boolean, default `true`).
  - `filters` (optional object or null).
  - `search_type` (optional string, default `"hybrid"`).
  - `sort_by` (optional string, default `"relevance"`).
  - `sort_direction` (optional string, default `"desc"`).
  - `folder_path` (optional string, default `"/"`).
  - `sort_order` (optional integer, default `0`).
- Response: `200` with `SavedSearchResponse`.
  - Fields include `id`, `query`, `is_smart_search`, `filters`,
    `search_type`, `sort_by`, `sort_direction`, `folder_path`, `sort_order`,
    and `created_at`.

### `/api/search/saved/{search_id}`

`PUT /api/search/saved/{search_id}`

- Purpose: update a saved search.
- Path params:
  - `search_id` (required string).
- Request body: `SavedSearchUpdate`.
  - Partial update fields are `query`, `is_smart_search`, `filters`,
    `search_type`, `sort_by`, `sort_direction`, and `folder_path`.
- Response: `200` with `SavedSearchResponse`.

`DELETE /api/search/saved/{search_id}`

- Purpose: delete a saved search.
- Path params:
  - `search_id` (required string).
- Response: `200` with the route's `DeletedResponse` object.

### `/api/search/saved/{search_id}/duplicate`

`POST /api/search/saved/{search_id}/duplicate`

- Purpose: duplicate a saved search under a new id.
- Path params:
  - `search_id` (required string).
- Response: `200` with `SavedSearchResponse`.

### `/api/search/saved/reorder`

`POST /api/search/saved/reorder`

- Purpose: reorder saved searches within a folder.
- Query params:
  - `folder_path` (optional string, default `"/"`).
- Request body: JSON array of saved-search ids in the desired order.
- Response: `200` with the route's reorder response object.

## Recently added engine endpoints

These routes are in the committed OpenAPI contract. They are documented here
until their corresponding Swift service wrappers land; the engine CLI already
exposes them.

### Device enrollment

`POST /api/pair/enroll`

- Purpose: exchange an owner's synced enrollment secret for a new, distinct
  per-device token.
- Request body: `EnrollmentRequest` with the required `enrollment_secret`.
- Response: `200` with `PairResponse`. The enrollment secret is not itself a
  device credential, so the returned token remains independently revocable.

### First launch: the owner

`POST /api/auth/first-run`

- Purpose: make the library's owner and register their public key, once
  (`multiuser.first-launch-creates-owner-and-key`, #2403). Local only: it works over the engine's Unix socket and
  never over TCP.
- Request: header `X-Fichero-Launch-Secret` (the per-launch secret the app handed the engine; the old bearer token is
  refused) and a body with `display_name`, `public_key_pem` (a P-256 public key) and `client` (`name`, `host`).
- Response: `200` with the owner `user` and the registered `client`; the app then signs in by challenge. `401` for a
  missing or wrong secret, `403` over TCP, `409` once an owner exists, `422` for a key that is not P-256.

`POST /api/auth/migrate-owner`

- Purpose: give an existing owner row its first key, once (`multiuser.migrate-owner`, #2403). Same guards as
  first-run; the body is `public_key_pem` and `client` (no `display_name`: the owner row has its name). The key goes
  to the owner row only.
- Response: `200` with the owner `user` and the registered `client`. `401` for a missing or wrong launch secret, `403`
  over TCP, `404` when no owner exists (use first-run), `409` when the owner already has a key, `422` for a non-P-256 key.

`POST /api/auth/invites/redeem`

- Purpose: accept an invite with a password, or with the person's own key (`multiuser.invite-registers-public-key`,
  #2403). Body: `invite_token`, then `new_password` OR `public_key_pem` (P-256) with `client` (`kind` app/device,
  `name`, `host`). A key redemption gives the person an unusable password: they sign in by challenge.
- Response: `200` with `session_token`, `user` and `client` (null for a password redemption). `422` when neither
  a password nor a key is sent, for a non-P-256 key, or for a key without a client; the invite stays unused.

### Sign in by key

`POST /api/auth/challenge`

- Purpose: start a passwordless sign-in for a registered client (`multiuser.sign-in-by-challenge`, #2403).
- Request: `client_id`.
- Response: `200` with `nonce`, `expires_in`, `expires_at` and `engine_id`. The nonce is single use and lives 60 s;
  at most 5 stay outstanding per client. `401` ("sign-in refused") for an unknown or revoked client, with the same
  body for both. Open: no session needed.

`POST /api/auth/sign-in`

- Purpose: finish the sign-in with the client's signature.
- Request: `client_id`, `nonce`, and `signature`: base64 DER ECDSA-P256-SHA256 over
  `"fichero-sign-in-v1" 0x00 engine_id 0x00 client_id 0x00 nonce 0x00 expires_at`. The engine rebuilds the message
  from its own `engine_id`, so a signature made for another engine is refused.
- Response: `200` with `session_token`, `user` and `client`. `401` ("sign-in refused") for any failure; `429` after
  10 failures a minute for a live client. Open: no session needed.

### Local CLI and MCP clients

All under `/api/auth/local-clients`. Off until the owner turns a switch on (`multiuser.first-connection-asks-the-person`,
#2403). Engine side only: the transport that stamps the socket's verified peer onto each request comes with the app.

`GET /api/auth/local-clients/switches` and `PUT /api/auth/local-clients/switches`

- Purpose: read or set *Allow local MCP clients* and *Allow the fichero CLI* (`{mcp, cli}`, both default off). The
  signed-in owner only; the bootstrap token is refused.

`POST /api/auth/local-clients/request`

- Purpose: a local program asks to be allowed (`{kind: cli|mcp, name, host}`). Unix socket only (`403` over TCP), a
  verified peer of the same macOS user (`403` otherwise), and the kind's switch on (`403` "not allowed on this Mac").
- Response: `200` with the request, including what the engine verified about the program (`peer.pid`, `peer.exe`,
  `peer.signer`) and `state` `pending`. Requests expire after five minutes; at most 20 are pending (`429`).

`GET /api/auth/local-clients/requests`

- Purpose: the pending and decided requests, for the app's approval sheet. Signed-in owner only.

`POST /api/auth/local-clients/requests/{request_id}/decision`

- Purpose: Allow or Deny (`{allow}`). Signed-in owner only; audited. `404` unless pending.

`POST /api/auth/local-clients/register`

- Purpose: the allowed program registers its OWN public key (`{request_id, public_key_pem}`, P-256), once. Unix socket only, from
  the same program (pid and path) that asked. `409` while pending, `403` when denied or the switch went off, `404`
  for another program or a used request.
- Response: `200` with the new client; it then signs in by challenge. The client acts for the owner who allowed it.

### Sharing state

`GET /api/pair/tailnet`

- Purpose: this Mac's `.ts.net` address when Tailscale is running, for the share
  sheet to offer instead of a typed address (#5318). Owner only.
- Response: `200` with `tailnet_url` (null when Tailscale is missing or stopped).

`GET /api/pair/sharing`

- Purpose: read Sharing state (#5751). Owner only.
- Response: `200` with `multiuser_enabled`, `tailnet_url`, `tailnet_serve_command`
  (the one command to paste when the app cannot make the tailnet forward, #5317)
  and `paired_device_count`.

`PUT /api/pair/multiuser`

- Purpose: set the persisted Multi-user switch (#5751). Owner only.
- Request body: `{"enabled": bool}`. Response: `200` with the sharing state, or
  `409` when `FICHERO_MULTIUSER` in the environment decides it.

### Cluster connection (ACENet)

`POST /api/hpc/clusters/{cluster_id}/check`

- Purpose: the live check on the login node: hostname, storage, Apptainer,
  GPUs and fair share (`compute.connect.check-really-checks`).
- Response: `200` with `HpcCheckResponse`.

`PUT /api/hpc/clusters/{cluster_id}/key` and
`DELETE /api/hpc/clusters/{cluster_id}/key`

- Purpose: the app pushes the cluster's private key into the engine's own
  folder, or removes it; the key is never read back.
- Request body (PUT): `HpcKeyPush`.
- Response: `200` with `HpcKeyState`.

`POST /api/hpc/clusters/{cluster_id}/sign-in`

- Purpose: open the one connection to the cluster; ssh's prompts come out of
  `GET /api/hpc/prompts` for the app to answer.
- Response: `200` with `HpcKeyState`.

`GET /api/hpc/prompts` and `POST /api/hpc/prompts/{prompt_id}`

- Purpose: what a cluster login is waiting on (a second factor, a
  passphrase), and the person's answer to one. Owner only.
- Request body (POST): `HpcPromptAnswer`.
- Response: `200` with `HpcPromptList`.

### Agent workspace membership

`PATCH /api/chat/workspaces/{workspace_id}/members`

- Purpose: add or remove curated source, entity, claim, or note references on
  an explicit saved agent workspace.
- Path param: `workspace_id` (required string).
- Request body: `AgentWorkspaceMembershipPatch`, with `add` items and/or
  `remove_ids`.
- Response: `200` with the updated `AgentWorkspace`; mutations are audited and
  undoable through the workspace action layer.

### Content representations and revisions

`GET /api/content-representations/document/{document_id}` lists a document's
typed `ContentRepresentation` records. `document_id` is required; response is
`200` with an array of representations.

`GET /api/content-representations/{representation_id}/revisions` lists the
immutable `ContentRepresentationRevision` history for one representation.
Returns `200` with an array or `404` when the representation does not exist.

`POST /api/content-representations/{representation_id}/revisions` records a
reviewer revision without changing the source representation. The body is
`RepresentationRevisionParams` (`content` required, `decision` optional); the
response is `200` with the new `ContentRepresentationRevision`.

### PyKEEN prediction review lifecycle

`POST /api/kg/pykeen/reviews` persists a `KnowledgePredictionReview` for a
user-confirmed review workflow; response `200` returns that review.

`GET /api/kg/pykeen/reviews` lists review records as `PykeenListResponse`.
Optional query `state` filters by the typed `PredictionReviewState`.

`PATCH /api/kg/pykeen/reviews/{review_id}` records an accept/reject/review
decision. The body is `PredictionReviewDecision` (`state` required, `note` and
`resulting_claim_id` optional); returns the updated review or `404`.

### Entity biography export

`GET /api/entities/{entity_id}/export` downloads one entity's existing
structured biography as an attachment. `entity_id` is required. The optional
`format` query parameter accepts `markdown` (default), `text`, or `json`; the
response is the corresponding attachment with a filesystem-safe filename.
Unknown entity ids return `404`.

### Record-bundle exports

`POST /api/export/jsonl` writes a JSON Lines record bundle for an optional
`target_id`, or for the whole library when it is omitted, to the requested
`output_path`. `POST /api/export/parquet` writes the same target's typed
Parquet bundle, or the whole library when `target_id` is omitted, to its
requested `output_path`. Both routes return a conflict rather than replacing
an existing destination unless the request sets `overwrite` (default `false`),
and return `404` when a supplied target does not exist. Their requested destinations are engine-local filesystem paths, so
these are CLI/backend-only surfaces: no SwiftUI save/export workflow may call
them.

### Live library handles

`GET /api/registry/open`

- Purpose: report the backend's currently open library connections, distinct
  from persisted `GET /api/registry` known-library rows.
- Response: `200` `OpenLibraryHandlesResponse`, whose items expose `id`,
  `path`, and `is_open` from a lock-safe manager snapshot.

`POST /api/registry/release`

- Purpose: release a project (#5563). The engine closes its database connection
  for the project and stops the background work it runs for it: its job threads
  (derivatives, embeddings and other page jobs) finish the page in hand and wait,
  and its background conversion stops at a page boundary. The project STAYS in
  the registry, so the app's sidebar keeps it; any later request naming it opens
  it again and its waiting jobs carry on. `DELETE /api/registry/{path}` (CLI
  `library close`) is the one that unregisters.
- Request: JSON `ReleaseLibraryParams` with `path`, the `.fichero` package.
- Response: `200` `ReleaseLibraryResponse`: `status` (`released`, or `not_open`
  when the engine held no connection: nothing is opened to release it),
  `path`, `registered`, `jobs_stopped`, `jobs_waiting`, `conversion_stopped`.
- Refusals: `409` while a workflow run or batch is waiting or running in the
  project (named in `detail`), and for the engine's global library. A release
  never starts a conversion or a snapshot (#5562).
- Audited as the `library.release` action. CLI: `fichero registry
  release-library --path …`; MCP: `fichero_library_release`.

`GET /api/registry/resolve?name=…`

- Purpose: find a known project by its name as the sidebar shows it (#5567),
  so a client opens a project by the name a person sees rather than its
  `.fichero` path. A registered path matches first; then the shown name (the
  registered `name`, else the package name without `.fichero`), ignoring case.
- Response: `200` `KnownLibrary` (its `path` is what the library header takes).
- Refusals: `404` naming the known projects; `409` when two projects share the
  name, naming their paths.
- A read of the global registry. CLI: `--library <name>` and `library open
  <name>` resolve through it; MCP: `fichero_use_library("<name>")`, and the
  generated `fichero_library_resolve_known`.

### A folder's canvas as a picture

`GET /api/canvas/folders/{folder_id}/canvas-picture?max_size=1600`

- Purpose: let an agent LOOK at a folder's 2D board while it organises a
  project (#5568): lay out, look, adjust, without screen control.
- Response: `200` `image/png`, drawn from the saved layout
  (`GET …/canvas-layout`) and the stored thumbnails. Each card sits at its
  saved centre (`w`/`h` if saved, else 120 x 150), shows its cached thumbnail
  (a grey card when none is made yet; nothing is generated), and is labelled
  with its name and the first 8 characters of its id. A group is outlined in
  blue with its member count and shows its first member; canvas items (notes,
  text) are yellow boxes with their text; links are lines. Children of the
  folder with no saved position are drawn in a "not placed" strip below, in
  folder order (at most 400 drawn, the rest counted).
- `max_size` (256 to 4096, default 1600) bounds the longest side; out of range
  is `422`.
- A read under the library's read access; nothing is changed. MCP: the
  generated `fichero_canvas_get_folder_picture` returns MCP image content (every
  GET answering `image/*` does, #5568); CLI: `fichero canvas
  get-folder-picture`.

### Reversible image regions and batches

All routes below preserve the source document. Crop and split create derived
children; uncrop, unsplit, and batch undo remove those derived children.

`POST /api/images/{document_id}/crop` accepts `CropOperationRequest` (`left`,
`top`, `width`, `height`, optional `page`/`auto_orient`) and returns
`ImageCropResponse` for one derived child. `POST /api/images/{document_id}/uncrop`
accepts no body and returns the reversible crop response.

`POST /api/images/{document_id}/split` accepts `ImageSplitRequest` with region
`bboxes` and returns `ImageSplitResponse`; `POST /api/images/{document_id}/unsplit`
accepts no body and returns `ImageUnsplitResponse` after removing those children.

`POST /api/images/crops/batch` applies one `ImageBatchCropRequest` region to
its required `document_ids`, returning `ImageBatchCropResponse` with children.

`POST /api/images/batch-apply` applies one crop or split spec to all images in
a required folder (`BatchImageApplyRequest`) and returns `BatchResponse` with
per-item state. `POST /api/images/batch-apply/{batch_id}/undo` reverses its
completed derived children and returns `BatchImageUndoResponse`; unknown or
non-image batch ids return `404`.

!!! note
    This is a static render of the committed contract schema. For live,
    interactive docs against a running engine, start it locally with
    `bash fichero-server/scripts/start_fichero_server.sh` and open
    `https://127.0.0.1:8765/docs` (Swagger UI) or `/redoc`.

### Kept exports, bake-offs, ground truth, reading pages again (2026-10-06)

- `GET /api/export/kept` — the project's kept exports and what each wrote.
- `POST /api/export/kept` — keep an export in a folder, written again as the work changes. One-way: Fichero writes the folder and never reads it back; each write overwrites only the files this export wrote and deletes nothing. Writing is background work.
- `DELETE /api/export/kept/{export_id}` — stop keeping an export; the files it wrote stay.
- `POST /api/export/kept/{export_id}/write` — write a kept export now, as one background job shown in Activity.
- `GET /api/recipes/project/bakeoffs/{bakeoff_id}` — a bake-off's pages, its job's state and its ranked table; scores are read from each model's card.
- `POST /api/recipes/project/bakeoffs/{bakeoff_id}/use` — make a scored candidate the reading step's reader for the project or one folder (audited, undoable).
- `PUT /api/segments/passes/{pass_id}/ground-truth` — mark a pass as ground truth, or unmark it (#5513).
- `POST /api/workflow-execution/threads/{thread_id}/read-again` — one new run of the same workflow and model over the pages a run did not do: the pages that failed, or after an interruption the pages not done (#5555).
- `GET /api/activity/jobs/{job_id}/log` — the log of one Activity row and the rows under it, newest last: a run's activity events, a step's node events, and each job's own lines (started, failed and why, waiting and for what); nothing from another row (#5561).

### The Trash and taking steps back (2026-10-10)

`docs/contributor_manual/specs/safety/trash.md` (#2077, #5243) and `safety/undo.md` (#5242, #5658).

- `GET /api/documents/trash` — the Trash of the project the request names (one per project). Each thing deleted once, newest first: `item_count` (what inside went with it), `deleted_at`, `deleted_by`, where it was (`from_folder_id`, `from_folder_path`, `from_folder_state`: `top`, `live`, `in-trash`, `gone`, and `from_where` in words), and why (`reason`: `deleted` or `moved`; for a move `moved_to_project`, `moved_on`, `transfer_id`; `why` in words, "Moved to Istmina on 10 Oct 2026"). `total` counts every item the caller may see.
- A move between projects writes the reason by soft-deleting its source through `document.delete` with `moved_to: {project, transfer_id}`.
- `POST /api/documents/{doc_id}/restore` — Put Back: the item and what was deleted with it return to its old folder, or to the project's Sources folder when that folder is in the Trash or gone. Answers `folder_id`, `folder_name`, `into_sources`, `folder_in_trash_id` (offer to put the folder back too) and `message` ("Put back in Sources: its folder is in the Trash."). Recorded and undoable.
- `GET /api/documents/trash/empty` — what Empty Trash would remove (`items`, `documents`, `statements`), the moves it would make permanent (`moved`, one line per target project) and the question to ask. Changes nothing.
- `POST /api/documents/trash/empty` — Empty Trash: one recorded step (`document.empty_trash`), a snapshot first (503 and nothing removed when the snapshot cannot be made). Cannot be undone.
- While a page is in the Trash, statements resting only on trashed pages, and entities with no live source that no person verified, are left out of `GET /api/claims`, `GET /api/entities`, the graph's neighbourhood and `GET /api/kg/search`. Put Back brings them back; Empty Trash removes them.
- `POST /api/actions/audit/{audit_id}/undo` — take back one step (a set of one). Refusals are declared: 404 and 409 with `{detail, reason, audit_id}`, `detail` a sentence and `reason` one of `changed` (a later step still in effect touched the same things; the step stays), `already-undone`, `gone`, `not-undoable`.
- `POST /api/actions/audit/undo` — take back a set of steps (`{audit_ids}`), newest first, in one transaction, all or none; a refusal names the step that refused. The answer's `audit_ids` are the new rows: taking those back as a set is the redo.
- `GET /api/actions/registry/{name}` — one registered action whole, with its parameter schema (an agent's lean answer for one action, beside the list); 404 for a name the registry does not have.

## Sandbox (Mac App Store)

### `POST /api/sandbox/security-scoped-access`

Grants the **running engine process** access to a security-scoped library folder.

Under the Mac App Store's App Sandbox, a child process inherits only the parent's
**static** entitlements. The user's folder grant (from `NSOpenPanel`) is a **dynamic**
Powerbox extension, and dynamic rights are **not inherited** — so the sandboxed engine
cannot open the user's library on its own. The app therefore hands the engine an
app-scoped **security-scoped bookmark**, which this endpoint resolves on the live engine
process and calls `startAccessingSecurityScopedResource()` against.

Returns whether the grant was already held (so the bookmark was not resolved twice).

**On failure it returns 400 and the engine refuses the library** — a malformed bookmark,
or a refusal from `startAccessingSecurityScopedResource()`, means the engine genuinely
cannot read that library, and the app must say so rather than open it and fail later.

See `agent-work/superpowers/specs/2026-07-13-mac-app-store-sandbox-research.md` (#3747).

<redoc spec-url="openapi.json" hide-download-button></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>

### Artifact span → page region

`GET /api/artifacts/{artifact_id}/region` resolves a line or character span of
a transcription artifact to its normalized page region — the single addressing
scheme (#4418) behind sentence-level highlight provenance. Optional query
parameters `char_start`/`char_end` (offsets into the artifact's content) or
`line` (zero-based) choose the span. The response is `ArtifactRegionResponse`:
a `geometry_status` (so "this engine cannot point at the page" is
distinguishable from "this page is blank"), an optional `geometry_reason`, and
the resolved `region` when geometry exists. Unknown artifact ids return `404`.

### Artifact region curation

`PUT /api/artifacts/{artifact_id}/regions` curates an artifact's
`ocr_geometry.boxes`. The body is `ArtifactRegionsEditRequest` with an `op`:
`move` (one index plus a normalized `bbox`), `delete` (one or more indices),
`add` (a `bbox`, optional `text`/`level` — bootstraps an empty user geometry
when the artifact has none yet, which is the rubber-band draw on a bare page),
or `combine` (two or more indices replaced by their union box, texts joined in
reading order). Every edit runs as one audited, undoable action with a full
before-snapshot, and appends a `curation_log` entry inside the geometry so the
history travels with the artifact. The response is `ArtifactResponse` with
geometry included, so the caller re-renders its overlay from the reply rather
than re-fetching.

### Segments (source model)

`GET /api/segments/document/{doc_id}` returns a source page's segments —
region, line and word boxes — resolved from whichever of its artifacts carry
`ocr_geometry` (the old blob) AND from real `Segment`/`SegmentPass` rows
where they exist (slice 3): the caller cannot tell which store a segment
came from. Reading a page's segments this way writes nothing: calling it
twice creates no row. The response is `SegmentListResponse` (`document_id`,
`passes`, `segments`); a document with neither yet returns an empty list,
not an error, and an unknown `doc_id` returns `404`. Optional query
parameters `artifact_id` (restrict to one artifact's boxes, or one real
pass's source artifact), `pass_id` (restrict to one pass — a `legacy:` one
or a real pass id), `kind` (restrict to one segment kind — region, line,
word), and `area` (a rectangle, `x,y,w,h` in image fractions — every real
segment whose box intersects it) narrow the result.

A segment read from today's blob is **provisional**:
`legacy:<artifact_id>:<box_index>` and its pass `legacy:<artifact_id>`, both
marked `provisional: true`. A provisional id is refused on write — the
regions-edit route (`PUT /api/artifacts/{artifact_id}/regions` above) and
every segment-write route below return `422` if handed one.

Each segment's `anchor` is a `SourceAnchor` (rect always; a polygon only when
the source box's metadata carries one — a Kraken line's polygon and baseline
are normalized from pixels to the anchor's fractional top-left convention).
Raw pixel values, and why a box's geometry could not be held, ride in the
segment's own `metadata` (`raw_polygon_px`, `raw_baseline_px`,
`raw_pixel_frame`, `geometry_problem`) — never on the anchor, which slices 3
and 6 store.

`POST /api/segments/passes` creates a `SegmentPass` (body:
`SegmentPassCreateParams` — `document_id`, `name`, optional `run_id` and
`source_artifact_id`), one typed audited action
(`segment.pass_create`/`.pass_delete`/`.pass_restore`). `DELETE
/api/segments/passes/{pass_id}` soft-deletes it (the row is never removed;
its segments stop appearing in the seam).

`POST /api/segments` creates one `Segment` in an existing pass (body:
`SegmentCreateParams` — `document_id`, `pass_id`, `kind`, `anchor`, optional
`baseline`, `parent_segment_id`, `kind_raw`); `POST /api/segments/bulk`
creates several in one `save_many` transaction (`SegmentCreateManyParams`).
Both refuse (`409`) a `pass_id` from another document or a
`parent_segment_id` in another pass/document, and (`422`) a client-supplied
`id`, `bbox_*`, `tile`, `version` or `provenance_kind` — the params models
declare none of them, so `extra="forbid"` rejects the request outright; the
four box columns are always engine-derived from `anchor`. Update and delete
of a segment as a user-facing feature, with version compare-and-set, arrive
in a later slice.

**Matches, forwarding notes, a citable reference (slice 4).** An id never
moves: "this new segment is that old one" is a `SegmentMatch` record, and a
merge/split/delete leaves an append-only `SegmentForwarding` note so an old
id can always be followed (`resolve_segment`, used by the citable reference
below).

`POST /api/segments/matches` proposes a match (body: `from_segment_id`,
`to_segment_id`, optional `certainty`, `note`), one typed audited action
(`segment.match_propose`/`.match_withdraw`). `POST
/api/segments/matches/{match_id}/accept` and `POST
/api/segments/matches/{match_id}/reject` change its state; only a person
may accept — a machine caller gets `422` (`MatchNeedsAPerson`).

`POST /api/segments/merge` absorbs two or more segments (one pass) into
`keep_id` (body: `segment_ids`, `keep_id`); the absorbed rows are
soft-deleted and each gets a `merged` forwarding note. Merging into a
segment that already forwards to the one being absorbed is refused (`409`,
`SegmentForwardingWouldLoop`) — this is what stops a merge cycle. `POST
/api/segments/split` splits one segment into two or more `parts` (each an
`anchor` and optional `baseline`); the original id stays on the first
part, and a `split` forwarding note names every resulting id.

`POST /api/segments/carry` copies readings/annotations/claim-evidence
across an **accepted** match (body: `match_id`, `kinds` — any of
`reading`, `annotation`, `claim_evidence`); the original is never moved.
A `reading` is carried only across a **one-to-one** match (accepted
matches only) — a many-to-many match carries no reading and reports why in
`not_carried`. Its inverse, `segment.uncarry`, removes exactly the copies.

`GET /api/segments/{segment_id}/reference` returns a citable string,
`fichero:segment/<library_uuid>/<document_id>/<segment_id>`, worked out on
request (never stored). It resolves through the EXISTING `POST
/api/locations/resolve` — never a second resolver — which gains an
optional `segmentId` (a bare id or the citable string form, checked against
the current library and refused with `422` if it names another one): the
route follows any forwarding first (`resolve_segment`), so a merged, split
or deleted id still resolves to where its content lives today. The
response's `liveSegmentIds` names EVERY live part (a split line has two —
this never quietly picks one), `resolvedSegmentId` names the primary
(the part that kept the requested id, else the first part listed when the
split was made), `segmentForwarding` is the trail followed, and
`segmentDeleted` says whether nothing is live any more. A `documentId` sent
alongside a `segmentId` that disagrees with what it resolves to is refused
(`422`) rather than the segment's silently winning.

**Versions, and refusing a stale edit (slice 5).** Every segment carries a
`version`, and every writing action names the version it read
(`expected_version`); if the segment has changed since, the write is
refused with `409` — never silently merged, never silently overwritten.
Editing while out of reach of the engine (a device offline) is **not
supported** in this work: a queue of stale edits made while disconnected is
refused one by one, same as any other stale edit, with no reconciliation.

`PUT /api/segments/{segment_id}` changes one segment's `anchor`,
`baseline`, `kind`, `kind_raw`, `parent_segment_id` and/or `is_furniture`
(body: `SegmentUpdateParams` — `segment_id` matching the path, plus
`expected_version`; `document_id`/`pass_id` are not accepted — a segment
never moves pass or document, that is a merge). A stale `expected_version`
is refused (`409`, body: `{message, segment_id, expected_version,
current_version, changed}` — `changed` names exactly the fields that moved
since); an update to a deleted (or merged-away) segment is refused
(`409`).

`POST /api/segments/delete` soft-deletes one or more segments in the same
pass and document (body: `segment_ids`, `expected_versions` — one per id
— optional `reason`), writing a `SegmentVersion` snapshot and a `deleted`
forwarding note for each. This REPLACES slice 3's internal stand-in: it is
now a real, undoable action with a real inverse. `POST
/api/segments/undelete` brings them back (body: `segment_ids`), clearing
`deleted_at` and writing a `restored` forwarding note.

`POST /api/segments/{segment_id}/restore-version` writes the segment back
to one of its own recorded versions (body: `version`, `expected_version`),
as a NEW version — history only grows, nothing is overwritten in place.
Restoring a version number that was never recorded for this segment (a
version that belongs to a different segment, or simply does not exist) is
a `404`.

`GET /api/segments/{segment_id}/versions` lists one segment's own history
(`SegmentVersion` rows, oldest first) without touching any other segment's
rows. `GET /api/segments/{segment_id}` returns the live row, resolving
through the same forwarding walk as the citable reference when the id has
been merged, split or deleted, and saying so
(`resolved_from_forwarding`, `trail`).

Access follows the same rule as every other library-scoped route today (a
valid token bound to the library, write-checked per target id; no
finer-grained per-document read check yet — see #4917 for the known gap in
that check for artifact-scoped reads).

### Workflow folder presentation

`GET /api/workflows/folders` returns the presentation metadata for workflow
folders — `path`, `display_name`, `sort_order`, and `icon` per folder, plus a
`count`. The order is the order work actually happens (prepare, find regions,
read, clean, translate, extract, catalogue), which is data rather than a rule,
so the capability bar draws its verbs from this list instead of a literal in
Swift. A folder absent from the list is not hidden: the client sorts it after
the known route with a fallback glyph, so a user's own folder appears the
moment they make one.

### Chain step execution

`POST /api/chains/{chain_id}/execute-steps` runs a chain's steps as real,
sequential workflow runs — the workflow bar's staged chain. The body is
`ExecuteChainStepsRequest` (`inputs`: the frozen run inputs shared by every
step; each step merges its own `static_inputs` on top). The response is `202`
with `ChainStepsAcceptedResponse`: an `execution_id` and, per step, a
pre-assigned `thread_id` and `stream_url`, so a client can attach to a step's
SSE stream before that step starts. Poll
`GET /api/chains/executions/{execution_id}` for per-step statuses. Unknown
chain ids return `404`; a chain with no steps returns `400`.

### Workflow runs

`GET /api/workflow-execution/runs` lists workflow runs from the **runs table** — the same
record the toolbar popover reads, and deliberately NOT the event log that `GET /api/activity`
reads. Those two disagreed, and this is the store that settles it: a run with no `activities`
rows at all still appears here, because a run that produced no events is still a run that
happened. Optional `status` repeats to filter (`?status=failed`), with `limit` (1–500, default
50) and `offset`. Paging, sorting and filtering are pushed to SQL, so the cost of listing does
not grow with how many runs the library holds.

`POST /api/workflow-execution/runs/delete` deletes runs in bulk, and "Clear Failed" is the
same audited action with a status filter rather than a second path — one audited action, two
ways of asking. **Checkpoints are left alone**: a deleted run hides the run without destroying
what it produced, and a thread's checkpoint goes separately via
`DELETE /api/workflow-execution/threads/{thread_id}`. That separation is the point, so
clearing a list of failures cannot quietly discard work.

### Background jobs and the global pause

`GET /api/activity/jobs` lists what is working in the background: the derivative queue, running
or failed workflow runs, and the rows of the project's `jobs` table (the one job model,
`specs/ui/activity-and-automatic-work.md`): `running`, `waiting` (one row per kind when more
than one waits, with the count in `total`), `paused` and recent `failed` jobs, each with its
`reason` in words ("Paused by you", "Waiting for Kraken (another page is using it)").
`paused` says whether *Pause Background Work* is on.

`PUT /api/activity/jobs/paused` with `{"paused": true}` or `false` turns it on or off for the
whole Mac, through the audited, undoable action `background.pause`. The switch is an app
setting, so it holds across relaunch. While it is on, the scheduler starts nothing; a job already
running finishes.

`PUT /api/activity/jobs/mode` with `{"mode": "automatic" | "started" | "paused"}` is the Start / Stop
control (#5621, `activity.mode.start-stop`), through the audited, undoable action `background.mode`:
`started` lets waiting work go ahead although the person is at the Mac or it is on battery (memory and
heat still hold it, and heavy work still runs one job at a time while memory is busy) until set back to
`automatic`; `paused` is *Pause Background Work*. `GET /api/activity/jobs` reports `mode`. The import's
row (`derivatives`) and a kind's counted rows (`waiting:<kind>`, `paused:<kind>`) take the one-job
routes below too, applied to every job they stand for that has not started, and
`GET /api/activity/jobs/derivatives` reads the import as a tree of its stages (#5623).

One job: `PUT /api/activity/jobs/{job_id}/paused` with `{"paused": true}` holds a waiting job
(it stays paused across relaunch) and `false` resumes it, through the undoable action
`job.pause`; `POST /api/activity/jobs/{job_id}/cancel` stops it through `job.cancel`. Both answer
`{"id", "state"}` with the job's state after the request: a job already running finishes the item
it is on and answers `running`; a training Job is cancelled on Hugging Face. A page a workflow
run is waiting for is paused with its run (`409`); an unknown id is `404`. MCP: `fichero_jobs`,
`fichero_pause_background_work`, `fichero_job_pause`, `fichero_job_cancel`.

`POST /api/activity/jobs/clear-failed` is the Activity window's Clear Failed (`job.clear_failed`, audited): failed jobs are hidden from the list (kept in the table, with `cleared_at`), alongside the failed workflow runs the window deletes; it answers how many it cleared. Retrying a cleared job lists it again (#5634).

`POST /api/activity/jobs/{job_id}/retry` runs a failed or stopped job again through `job.retry`
(#5356): it goes back to waiting with its attempts cleared and carries on from its own checkpoint;
any other state is answered unchanged. A page a workflow run handed in, a training on Hugging Face,
or work already waiting again is refused (`409`, with the reason).

`GET /api/documents/run-history?ids=<id>&ids=<id>` says what has been run on each document (#5434):
its job rows (pictures, embeddings, names, line finding, page reads) and the workflow runs recorded
on it, newest first, with the model and provider as recorded, the outcome, an absolute UTC time and a
cost that is null unless priced. One call serves a table's visible rows; an unknown id is left out
and a document the caller may not read is withheld and counted.

A workflow run is a job too (#5353): its row's id is the run's thread id, each step is a child
(`<run>:<step>`), and each page a step hands to a lane is a grandchild, named by its model (a cloud
model's page on the network lane, capped per Mac; a local model's on the local-model lane).
`GET /api/activity/jobs/{job_id}` returns a job and everything under it, each with `done` and
`total` pages rolled up; pages in `/api/activity/jobs` carry their step as `parent_id`. Pause and
Stop on a run's row (`PUT .../paused`, `POST .../cancel`) reach the run's own Pause and Stop: its
pages still waiting for a lane are withdrawn ("Paused with its run", "Stopped by you"). A paused
run is resumed with `POST /api/workflow-execution/threads/{thread_id}/resume`.

A recipe run (`run-a-recipe`, #5576) is a job whose children are its stages' own jobs. Its node in
`GET /api/activity/jobs/{job_id}` also carries `stages`: every card of the run in order, those not
started and those not run included, each a workflow stage with its run's `account` (pages done,
failed and left, the time left, what its pages wait for), and its `reason` says what the run waits
for while it waits or runs. Once it has ended, the node carries `summary`, the same answer as
`GET /api/recipes/project/runs/{job_id}/summary` (#5577).

### Training a reader (Hugging Face Jobs)

`POST /api/training/kraken` queues a `train-a-model` job (#5398, `specs/compute/jobs-and-fine-tuning.md`):
the pages under `scope_ids` whose lines the `teacher` model read are written as PAGE XML beside their
photographs (the `held_out_ids` pages stay home as the test), sent to a private bucket of the
person's Hugging Face account, and Fichero's trainer fine-tunes the `base` Kraken reader there on the
chosen `flavor` with an explicit `timeout`. The answer carries the job id and the hardware's
`price_per_hour_usd`. It is refused, with nothing queued, without `pages_may_leave: true` (403),
without a Hugging Face token in Settings (412), or with a base reader that is not installed (422).
Through the audited, non-undoable action `training.start`. `target` names where it trains: `huggingface-jobs`
(the default), or a cluster set up here by its id, where the set goes to the run's folder, one GPU job runs the
same trainer in the server image, `flavor` does not apply and `price_per_hour_usd` is null; a cluster with no
key in the app is refused by name (422, #5238). The run's folder leaves the cluster when the reader is home
unless the project said working copies may stay (#5769).

`POST /api/training/vision-lora` is the same job on the vision-model card (`compute.tune.lora`): the
same training set cut into line pictures with the line reader's own instruction and the teacher's
answers, a LoRA on the bf16 `base_repo` (`Qwen/Qwen3-VL-8B-Instruct` by default; any image-text-to-text
model, its licence recorded) on the cheapest listed GPU that fits unless a `flavor` is named, and,
back on this Mac, the merged model converted to 4-bit MLX on the local ML lane and landed as
`fichero-trained/<name>`: one card, two builds (MLX here; the merged Hugging Face weights and adapter
in the job's bucket for Linux GPUs; `keep_merged_here` keeps a copy on this Mac too). The same refusals. Through `training.start_vision_lora`.
`arm` (#4642) chooses what the student learns to write: `answer` (the transcription), `why` (a
palaeographer's reasons, then the transcription), `thinking` (its thinking, then the transcription) or
`review` (a review of a draft reading). The answer is always the checked text; the reasons come from the
episode ledger (`training.reasons`) and are kept only where the palaeographer's own reading is within
`max_trace_cer` of the checked one; the A/B arms train on the lines every reasoning arm covers unless
`all_lines`. The set's arm counts and drops are on the job.

`GET /api/training/jobs/{job_id}` follows it: `state`, the `reason` in words, its `phase` and
`history`, the Job's `far_id` on Hugging Face, the training set's counts (including how many lines a
model read and a person checked), the Job's `last_lines` when it ends, and, once landed, the
`reader_id` (`kraken-trained-…`) or `model_id` (`fichero-trained/…`) to read with. The job also appears in `GET /api/activity/jobs`.

Every training set leaves out flagged lines (#5446, `compute.tune.set-excludes-flagged-lines`): a line
whose reading is empty or the word `null`, and a line whose newest check verdict (`check.verdict`, a
person's or a checker model's) rejects it. The set's manifest and the job's `training_set` count them
(`lines_left_out`, `left_out` by flag, `left_out_lines` with each line's segment), say how many lines
carry a verdict and whether the check had run (`check_ran`), and name the flags checked
(`flags_checked`). `GET /api/training/set?teacher=…&scope_ids=…[&held_out_ids=…]` counts the same set
without writing or sending anything (one code path with the job's), so an operator sees what a run would
train on before starting it. The reading check's own flags (a reading closer to a neighbour's line, one
below the set score) are not built yet.

`POST /api/training/reasons` queues a `gather-reasons` job (#4642): a palaeographer (a reasoning vision
model, `provider` and `model`) is asked about every line of the `checked` pass in scope, held-out pages
left out: the letterforms, abbreviations and uncertain readings behind each reading, then the
transcription. `prompt_file` is the recipe's own prompt. Each call is one episode in the ledger, which
the vision card's `why` and `thinking` arms read (its `review` arm reads a check run of the readings,
below). Through `training.gather_reasons`; 422 with no scope. `GET /api/training/reasons/{job_id}` gives its counts (lines, with reasons, with thinking,
unanswered, pages missing and why); `POST /api/training/reasons/{job_id}/cancel` stops it
(`training.cancel_reasons`): no further lines are asked about, and what was gathered stays.

`POST /api/training/reasons-ab` queues a `reasons-ab` job (#4642, `distill.reasoning.ab-decides`): each
of the `contenders` (`label`, `provider`, `model`, `arm`, `role`: student, teacher or baseline) reads the
held-out checked lines (`held_out_ids`, required) as it was trained, and a reasoning student also with
its reasoning off; one CER and WER each, seconds a line, and for a `why` student how many of its errors
fall on lines it called uncertain. A reasoning student is adopted only if it beats the answer-only
student by more than `noise_band` (the request's, else the project's noise band, 0.005 until measured, #5692); the result is written on every Fichero-trained contender's
card either way. Through `training.measure_reasons_ab`; `GET /api/training/reasons-ab/{job_id}` gives the
scores and verdicts.

`POST /api/training/jobs/{job_id}/cancel` stops it (`training.cancel`): a job not started ends at
once; a running one is cancelled on Hugging Face at its next look and ends `cancelled`.

`GET /api/training/models` lists the models Fichero trained or fine-tuned on this engine, newest first,
as the training node shows them (#5439, `source.model.node-in-sidebar`), each read from its card: `kind`
(`kraken-reader` or `vision-lora`), `base`, `teacher`, `training_set` counts, `job_id`, `trained_at`,
`trained_where`, the newest held-out `scores` (CER per normalisation policy; null before any
evaluation), `size_bytes`, `runs_on` (each build and whether it is here), `licence` (the base's; null
for a Kraken reader, whose card names none) and `may_publish` (true only when the card says
`not_for_release: false`). A downloaded or imported model is not listed. `GET /api/training/model?model=…`
gives one model's Inspector facts: the same, plus its whole `card` and every evaluation
(`evaluation_history`); 404 for a model Fichero did not train. Each also says where it `lives` (#5539):
`project` (inside this project's package, `models/`), `global` (the engine's store) or `both`.

`POST /api/training/models/make-global` with `{"model": …}` (a `kraken-trained-<job>` or
`fichero-trained/<name>` id) copies a model trained in this project, card and weights, from the
project's `models/` folder into the engine's global store, so every project can use it (#5539,
`compute.model.make-global`). The project keeps its copy; the card goes unchanged, `not_for_release`
included. One audited action (`training.make_model_global`); returns `model_id`, `global_path` and
`may_publish`. 404 when the project holds no such model; 409 when the global store already has one by
that id (never overwritten). MCP: `fichero_training_make_trained_model_global`.

### Evaluation (#5441)

`POST /api/evaluation/runs` queues one `evaluate-models` job on the local model lane
(`distill.eval.job`): each of the `candidates` (`model`, `reader`: kraken or vision, `provider`: only
`omlx`, this Mac, for a vision model) and, unless `add_out_of_the_box` is false, the registry's
out-of-the-box readers of the same kind on this Mac read the lines of the `checked` pass (its model id
or name; none: the newest pass a person made on each page) on the held-out pages, and are scored with the one CER under every normalisation policy. The
pages are `held_out_ids`, each of which must be held out of every trained candidate, or with none named,
the pages every trained candidate's card holds out. Refused (422) in words before anything is queued:
a trained model whose card holds no held-out page, a named page a trained candidate may have trained
on, no page with a checked reading, a model not on this Mac, a remote provider. Through
`evaluation.run` (not undoable: a score is a result). `GET /api/evaluation/runs/{job_id}` gives the plan
(candidates, pages, pages missing and why, readers not on this Mac) and the result (per model and per
page, the CER under each policy, who checked each page, the best, and `adoption`: whether the best trained
Kraken reader became the project's read-a-line reader, only past the project's noise band, and why). Each model's scores are appended to
its card; `GET /api/evaluation/scores?model=&reader=` reads them back. Activity's stop ends it before
its next page, with nothing written on the cards.

### Reading at scale (Hugging Face Jobs)

`POST /api/reading-at-scale` queues a `read-at-scale` job (#5398 slice 2,
`specs/compute/jobs-and-fine-tuning.md`): the pages under `scope_ids` (images here, or IIIF canvases
imported by reference, fetched where the job runs at `longest` pixels) are packed with the `reader`
(`kraken` or `vlm`, named by `card`) and Fichero's runner, sent once to a private bucket of the
person's Hugging Face account, and read in shards of `shard_size`, at most `max_in_flight` at once,
each on `flavor` with an explicit `timeout`. As each shard finishes, its PAGE files land as new passes
through `format.import` (a IIIF page's lines on its canvas); a page whose result already landed is not
landed again. One row in `GET /api/activity/jobs`, on the remote lane. Refused, with nothing queued,
without `pages_may_leave: true` (403), without a Hugging Face token (412), or with a reader that cannot
run off this Mac (422). Through the audited, non-undoable action `reading.start_at_scale`.

`GET /api/reading-at-scale/jobs/{job_id}` follows it: `state`, the `reason` in words, the shard
`counts` (pending, submitted, landed, failed), each failed shard's reason and last lines, the
`package` (sources, shards, pages skipped and why) and the `landing` counts. For a run on Hugging Face,
`hf_spend` is this month's Hugging Face spend against the project's cap, as on the Start plan (each shard sent
is a Job); null for a run on a cluster (#5769).

`POST /api/reading-at-scale/jobs/{job_id}/resend-failed` sends the failed shards again, and only those
(`reading.resend_failed`; 409 while the run is still going). `POST /api/reading-at-scale/jobs/{job_id}/cancel`
stops it (`reading.cancel_at_scale`): its running shards are cancelled on Hugging Face.

### Training a layout model on this Mac

`POST /api/training/regions/here` fine-tunes a YOLO layout model on the regions a person drew or corrected
(`train-regions-on-this-mac`, the audited action `training.start_regions_here`, `training/yolo_local.py`):
the regions are exported as a YOLO set, trained on the GPU in the engine's process with the same gentle
checks as Kraken here, and the model lands in the project's Models with its card (`model.pt` and
`fichero-card.json`, scored as region overlap mAP50 on the held-out pages). `GET /api/training/jobs/{job_id}`
follows it.

### Training a reader on this Mac

`POST /api/training/kraken/here` queues the same Kraken card on this Mac (`train-on-this-mac`, the
audited action `training.start_here`): the same training set and `ketos train` settings, nothing
sent and nothing paid. It runs on the local-model lane inside the engine (a child process of the
sandboxed engine cannot start), on the CPU (Kraken's CTC loss has no Apple GPU kernel), at utility
priority with bounded threads. It holds while the Mac is in use, hot or on battery; lets memory go
and goes back to waiting when memory is tight, background work is paused or a person waits for
other work; and resumes from its last finished epoch (`ketos train --resume`, checked on Kraken
7.1.1). Body: the Kraken card's fields without the Hugging Face ones, plus `epochs` (none: stop
when it stops improving) and `batch_size`. `GET /api/training/jobs/{job_id}` follows it, with
`measured` (peak resident memory, what training added, device, threads, epochs, seconds), and
`POST /api/training/jobs/{job_id}/cancel` stops it at its next step. MCP: `fichero_train_kraken_here`.

### Synced folders

`POST /api/sync-folders` with `{"path", "formats"}` ties the project to a folder on the engine's
disk (a full path there; the app never assumes it can see it) and writes the project's PAGE, ALTO
and/or TEI into it through the exporter, then keeps them current (#4952, `specs/source/synced-folder.md`).
The layout is Fichero's: one subfolder per format, one file per source named
`<title>--<lasting id><extension>`, its loss report beside it as `<file>.loss.json`; each file
names its source (`fichero-source`), pass, reading order and reading kind in the format's own
identifier place. Writing is background work (kind `write-to-folder`); a change to a page rewrites
its files after a short quiet period; every file is written to a temporary file and renamed into
place; a file Fichero did not write, or one changed since it wrote it, is never overwritten.
`GET /api/sync-folders` gives each folder's place, formats, last write, files waiting, and the
files written, in the way, changed outside and deleted outside (found again when the library opens).
`DELETE /api/sync-folders/{folder_id}` unties it and leaves its files.
`GET /api/sync-folders/{folder_id}/intake` says whether intake is on and what it would bring in now
(files changed outside, by format); `PUT` with `{"on": true}` switches it on (an adopted folder has
it on from the start). With intake on, a file Fichero wrote or adopted that is changed in the folder
comes in as a new pass made by "edited outside Fichero", which never becomes the working pass by
itself; one whose page changed in Fichero too is listed under `conflicts` with both kept, and is no
longer written. A folder imported with `mode: index` is adopted: kept in its own layout and written
back in place. With intake on, the folder is watched while the engine runs: a file of Fichero's
renamed or moved is matched by the lasting id it carries; new images, with any layout file beside
them, come in through the same import a drop of files takes (listed under `taken_in`); any other
file is listed under `not_read_back`. The preview counts new images under `images`. A file that is
already a document's own file (live or in the trash) never comes in again, so a restart takes in
nothing the project holds; a new file lands in the project folder of the folder it was put in (#5495).

`GET /api/sync-folders/duplicates` is the dry run of the duplicate repair (#5495): each file of a
synced folder held by more than one live document (`path`), the document kept (`keep`: the first
made, in its folder) and those that would go (`remove`), each with `id`, `name`, `parent_id`,
`created_at` and `passes`; nothing changes. `POST /api/sync-folders/duplicates/remove` with
`{"document_ids": [...]}` runs the audited, undoable `sync.remove_duplicates`: each named document,
which must be one the dry run lists under `remove`, goes to the trash with anything under it, and
`removed` lists them. A kept document, or one no longer a duplicate, is refused (409) in words and
nothing is removed. Undoing the audit row restores them.

A folder is kept as `index` (the default: files stay where they are) or `keep-arranged` (#5480,
`specs/source/models-chains-and-projects.md` section 7b): `POST /api/sync-folders` takes `mode`,
`GET` shows it. `GET /api/sync-folders/{folder_id}/arrangement` is the dry run: each file that
would move (`document_id`, `from_path`, `to_path`, inside the folder) and `refused`, the reason in
words when it would not be arranged; nothing moves. `PUT /api/sync-folders/{folder_id}/mode` with
`{"mode": "keep-arranged"}` is the yes: refused (422) in words for a folder Fichero cannot write to,
or that no project folder came from (import it with Index first). Kept arranged, the folder follows
the project's own folders: a document moved or renamed, or a folder renamed, in the project queues
an `arrange-folder` job, which runs the audited `sync.arrange` action listing every move; files
move only inside the folder, never over another (a clash takes `name 2.jpg`), and none is deleted.
Undoing that audit row (`POST /api/actions/audit/{id}/undo`) puts every file back. A file moved by
hand inside the folder stays where it was put: its document's record, project folder and name
follow it (`sync.follow`), marked `placed_by_hand`.

### Checking a layer's proposals

`specs/source/checking.md` (`source.check.*`, #5404). `POST /api/check/runs` queues a `check` job: the
checker (`provider`, `model`) is shown each proposal of `layer` in `scope_ids`, one a call:
`readings` (the palaeographer reviewer: each line's picture and its counting reading of `kind`; the
lines of the page's newest pass, or of `pass_model`'s), `claims` (each statement's text, subject,
relation, object and the passage it came from) or `entities` (each entity's name, type, other names
and the passages that mention it). `prompt_file` is the recipe's prompt for the card. Each answer
(confirm, correct or reject, with reasons) is a verdict through `check.verdict`, recorded at the trust
level `model`; each call is an episode in the ledger, named on its verdict. A corrected reading is
first written as a new reading of the line naming the one checked (`representation.create`, a
machine's reading); a statement's or entity's correction is held on the verdict for a person to take.
A model never curates a statement or verifies an entity: its *reject* moves an `unreviewed` statement to
`shortlisted`, and nothing further. Through `check.run`. `GET /api/check/runs/{job_id}` gives the counts
(confirm, correct, reject, unanswered) in words; `POST /api/check/runs/{job_id}/cancel` stops it before
its next proposal (`check.cancel`).

`POST /api/check/verdicts` records your own verdict (`layer`, `target_id`, `verdict`, `reasons`,
`correction`) through `check.verdict`, at `person`; the trust level and the checker are the server's
(422 if sent). It moves no curation state: a statement's curation is its own action.
`POST /api/mcp/tools/check/verdicts` is the same for an agent, recorded at `model`.
`GET /api/check/verdicts` lists verdicts by `target_id`, `run_id` or `layer`.
The static site (`POST /api/export/eleventy-site`, and a recipe's `publish` step) shows each check where one
has run (`source.check.on-the-site`): under each statement on its page and in the claim index, and on each
entity's page: the verdict, by whom (a person, or a model), why, and a correction's offered values.

### Finding the documents in a box

`specs/source/finding-documents.md` (`finddocs.*`, #5550). `POST /api/find-documents/runs` (`scope_ids`:
folders, or a selection of pages, each found within its folder; optional `accept_above`) queues one
`find-documents-in-a-folder` job through `finddocs.run`: each folder's loose pages (photographs, or the pages
cut from them) in the folder's order are paired into leaves (a near-blank page after a written one is its
verso; a page whose text nearly repeats one just before is a second shot), and a document boundary is
proposed at each join whose evidence says so: opening cues at the head of the page (a court caption, a
heading such as VISTOS or Demanda, a place-and-date line, a salutation), closing cues at the foot of the page
before ("Cópiese, notifíquese", "(fdo)", "Atentamente"), folio numbers restarting or running on, and a
sentence running over the break. The cues are one table (`finddocs/cues.py`; Spanish and English rows).
Each document has its kind (a prototype name), its date, its parties and a confidence; documents sharing
two parties are proposed as a group, in date order. The proposal is stored as a `grouping` artifact on the
folder; nothing in the source changes. `GET /api/find-documents/runs/{job_id}` gives the run's state, words
and `proposal_ids`; `GET /api/find-documents/proposals` (`folder_id`) and
`GET /api/find-documents/proposals/{proposal_id}` read them (`documents`, `groups`, `findings`: blank
versos, blank pages, duplicate shots, pages with no reading; `joins`: every join's probability and signals).

`POST /api/find-documents/proposals/{proposal_id}/accept` (`document_indexes`, or `min_confidence`, or
neither for all; `arrange`, `groups`) is one audited action, `finddocs.accept`: each document of two or more
pages becomes a group node of its pages (the Group command's code), a one-page document stays its page; its
prototype is assigned, made first when the project has none of that name; a proposed group whose documents
are all accepted becomes a group of them; the folder's canvas is laid out in their order. The response's
`audit_id` undoes all of it at once (`POST /api/actions/audit/{audit_id}/undo`, through
`finddocs.unaccept`). `POST /api/find-documents/proposals/{proposal_id}/reject` (`document_indexes`) marks
documents rejected (`finddocs.reject`), kept for the project's own model to learn from. A recipe's
`find-documents-in-a-folder` step runs the same job, with the step's `accept_above` (default 0.95).

Before accepting, a person adjusts a proposal (`finddocs.adjust`), changing the stored proposal only:
`POST /api/find-documents/proposals/{proposal_id}/split` (`document_index`, `page_id`: the page that starts
the second document), `POST /api/find-documents/proposals/{proposal_id}/join` (`document_index`: joined to the
next) and `POST /api/find-documents/proposals/{proposal_id}/move-page` (`document_index`, `to`: `previous`
moves its first page to the document before, `next` its last page to the document after). Each renumbers the
documents, marks the touched ones set by the person (`adjusted_by`, confidence 1.0) and appends labelled
examples to the proposal's `examples` (`left_page_id`, `right_page_id`, `boundary`, `decided_by`, `at`, the
run's `run_probability` and `run_reasons` for that join). Each answers the proposal, the new examples and an
`audit_id` whose undo (`finddocs.unadjust`) restores the proposal exactly. An index or page out of range is
422; a superseded proposal, a document already accepted or rejected, or pages grouped since is 409.

A folder's proposal is scored against a person's breakdown (`finddocs.scored`): the documents a person accepted
or adjusted. `POST /api/find-documents/score` (`folder_id`, optional `proposal_id`: left out, the folder's newest
current proposal) runs `finddocs.score` (audited, not undoable: a measurement) and keeps the score as a
`finddocs_score` artifact on the folder: `documents`, the judged `joins`, `boundaries_proposed`,
`boundaries_actual`, `precision`, `recall`, `exact_documents`, `kinds_confirmed`, `kinds_right`,
`kind_accuracy`, and `levels` (for 0.5 to 0.99: the judged joins the run was at least that sure of and how many
the person agreed with). It answers the score, its `audit_id`, the folder's stored scores and the suggestion
below. A folder with no proposal, or none of whose documents a person set, is 422; an unknown folder or
proposal is 404. `GET /api/find-documents/score` (`folder_id`) lists stored scores newest first, with `levels`
pooled over every folder's newest score and `suggested_accept_above`: the lowest level at least 99% agreed over
at least `min_joins` (50) joins, null until then. The suggestion never turns the auto-accept on.

### Workflow run comparison

`GET /api/workflow-execution/comparisons` diffs what two runs produced from
the same input. Required query parameters `left` and `right` are the two
thread ids. Artifacts pair on (document, artifact type); the
`RunComparisonResponse` reports line-level differences for transcriptions and,
for extraction runs, which entities or claims each side found that the other
missed.

### Workflow run episodes

`GET /api/workflow-execution/threads/{thread_id}/episodes` returns the
episode-ledger records recorded under one run — per-node model-call
provenance: each record carries the node, the full exchange (prompt, raw
output, thinking), model identity and use case, the subject
(document/page/file), and timing. Optional `limit` (default 500). The
response is `{thread_id, count, episodes}` with records in ledger order.
This is the per-node inspection surface and the resolver behind episode
citation keys; corrections and invalidations referencing the run's
episodes appear by id.

### Interpretation search leg

`POST /api/search` accepts `"interpretations"` in `include` (opt-in, like
`"artifacts"`). A matching interpretation — its text, key insights, or
predicate — folds its SOURCE document into `results` with
`metadata.matched_via = "interpretation"`, the interpretation text as the
preview, and `interpretation_id`/`framework_id` in metadata so the client
can open the interpretive context alongside the document.

### Training export

`POST /api/export/training` writes chat-format training samples from the
episode ledger to a `.jsonl` destination. One sample per recorded model
call: system+user messages from the recorded exchange; the assistant turn
is the human correction when one exists (`gold: true`, with the model's
original output in `rejected` for DPO pairing), otherwise the model
output. Optional `use_case` filters to one workflow step's calls;
`gold_only` keeps only corrected pairs. Engine-local destination path — a
CLI/backend surface like the record-bundle exports, with the same
conflict rule (`409` unless `overwrite`).

## The source model

These are the routes of the source model — the layer that holds what is on a
page (segments, their shapes, their readings), the facts that describe it
(language, script, direction), the orders a scholar reads it in, the links
between its parts, and the interchange formats it reads and writes. Every write
below goes through the one audited action layer, so each answer carries an
`audit_id` and each change has an inverse.

### Comparing two readings of a page

`POST /api/documents/{document_id}/readings/compare`: how far one reading of this page is from
another, scored by Fichero's CER definition under each normalisation policy asked for (#5389). Refuses
(`422`) rather than return a number it cannot stand behind.

`GET /api/documents/{page_id}/disagreement`: where this page's readers disagree, line by line and word by
word (#5665). Each line's readings are brought to the line as written; the medoid reading is the reference,
each other reading is aligned to it, and each word scores the share of readers that gave exactly it:
agreement, never accuracy. With fewer than two readings, 200 with `lines` empty and `page_agreement` null; an
unknown page is 404. Read-only.

### A segment's readings

`GET /api/segments/{segment_id}/readings`

- One line can have several readings — a recogniser's, a scholar's correction, a
  normalisation, a translation — and exactly one of each kind COUNTS. The answer
  lists them and names the counting one per kind, so a caller never has to
  decide which is authoritative.
- Optional `kind` narrows to one kind. A provisional segment id is accepted,
  because asking what a line says has to work before anybody has edited the
  page.
- Refuses with `404` when there is no such segment. A **provisional** id is
  accepted here on purpose, unlike on the write routes: a reader asking what a
  line says must work before anybody has edited the page.

`POST /api/segments/{segment_id}/readings/choice`

- Records which reading counts. **Only a person may**: a machine choosing which
  of its own outputs is the true one is exactly the judgement this layer exists
  to keep human, so a run's context is refused with `403`.
- Also `422` for a reading kind this library does not have, and for a reading
  whose anchor does not match the segment it is being chosen for: choosing a
  reading of somewhere else is a mistake worth a sentence rather than a silent
  write.

`POST /api/segments/{segment_id}/correct`

- Corrects a line: `{"text": "..."}`, with `kind` (default `transcription`) and
  `expected_counting_id` optional. The engine fills in the document, the reading
  corrected (the one counting now, or the file text a provisional reading still
  lives in) and the compare-and-set, and writes one `representation.create`, so
  the correction is audited and undone as every correction is (#5499).
- `409` (nothing written) when another reading counts than `expected_counting_id`,
  naming it and its text; `404` for no such segment; `422` for a provisional id
  or empty text. Returns the new reading.

### A page's derived text

`GET /api/segments/document/{document_id}/text`

- The page's text is WORKED OUT, never stored: it is the working pass's
  segments, each contributing its counting reading. The answer carries `spans`
  pointing back at the segment and representation each stretch came from —
  text with no way back to the reading it came from is a wall of words.
- `pass_id` reads a named pass instead of the working one, and the answer always
  says which pass it used and why (`pass_basis`).
- `order` follows a named reading order; omitting it means box order, which the
  answer reports honestly as `order: null` rather than claiming a name.
- Furniture — running heads, folio numbers, catchwords — is left out unless
  `include_furniture` is set, because a page number in the middle of a sentence
  is worse than a missing one.
- `omitted` names every segment the order names that the text does not contain,
  each with a reason: `deleted`, `furniture`, `other_pass` (with the pass that
  holds it) or `unknown`. A cross-pass continuation and a deleted line must not
  look the same, because a silently shortened transcription looks like a correct
  one.
- Refuses with `404` for no such pass or an `order` id that names nothing, `409`
  for an order that was withdrawn, and `422` when the named order is an order of
  a **different pass** from the one being read — the sentence names both passes
  and says which `pass_id` to ask for, because a text assembled from one pass's
  readings in another pass's order is a sentence nobody wrote.

### A segment's picture

`GET /api/segments/{segment_id}/picture`

- PNG bytes of the segment's own area, cut to its shape: cropped to its box plus
  `margin`, masked outside its polygon with `mask`, levelled along its baseline
  with `straighten`, and bounded by `size` (the default is bounded, not
  unlimited).
- Bytes rather than a storage reference, because the storage routes address a
  document and not one of its derived crops — and a local path would break the
  rule that the engine may be remote.
- It refuses rather than answering when the segment was measured against a
  different image from the one on the document: a picture of the wrong place is
  worse than an error.
- That refusal is a `422` whose sentence names the image it was measured on and
  the one that is there now. The same `422` covers every other reason a picture
  cannot be made honestly.

### Source settings: language, script and direction

`GET /api/source-settings/resolve`

- The three facts and the text encoding for ONE selection (`segment_id`, or
  `document_id` for the page), each with the rung that answered it: the segment,
  the document, the project, or a default. A fact that does not say where it came
  from cannot be argued with.
- For one selection and not a list, deliberately: resolving every segment of a
  page here would be one cascade walk per row.
- Refuses with `404` when the node it is asked about does not exist.

`PUT /api/source-settings`

- States a fact, or stops stating it — an empty value clears rather than writing
  a blank, so "nobody has said" and "somebody said nothing" stay different.
- A level it does not own is refused by name. Segment-level facts belong to
  `segment.update`, which owns a segment's own fields; this route owns the
  project and the document.
- Every refusal is a `422` that names what was wrong: a level this route does not
  own, a level that is not a level, a project fact outside the known keys, a
  script code that is not ISO 15924, a direction outside the known set, a node
  reference with no target, or an empty value sent to the setter instead of the
  clearer.

### Reading orders

`POST /api/reading-orders`

- Creates a named order over a pass. A page holds several: the order as written,
  a commentary order, an imposed order, and a **flow**, which is the one kind
  whose entries may name segments of another pass because text continues onto
  the next folio.
- `seed_from_pass` fills the new order from the pass's own box order, which is
  what makes an as-written order agree with what a recogniser produced.
- Refuses with `409` when a segment is already in the order, or when a segment
  belongs to a different pass and the order is not a flow — that distinction is
  the flow's whole point — and `422` when an order's positions have run out of
  room and need renumbering first, which is a request to renumber rather than a
  failure.

`GET /api/reading-orders/document/{document_id}`

- A source's orders, the as-written one first. `include_deleted` shows withdrawn
  ones, since an order is soft-deleted and restorable like everything else here.
- The entry and neighbour reads refuse with `404` for no such order and `409` for
  a deleted one, rather than answering emptily: an order that was withdrawn and
  an order with nothing in it are different facts.

`GET /api/reading-orders/{order_id}/entries`

- ONE LEVEL of one order — the top level, or the children of `parent_entry_id`.
  Orders nest (regions in order, lines in order within each), and returning a
  whole tree would make a bounded read depend on how deeply somebody nested
  their reading.

`GET /api/reading-orders/{order_id}/neighbours`

- What reads before and after one segment **in this order**. Always of a named
  order: there is no "next segment" call without one, because a page holds
  several orders and answering from a default would be the engine picking a
  scholarly reading without saying so.
- Two bounded lookups, not a walk of the order.
- `422` when no order is named, because there is no default order to fall back
  to.

### Typed links

`GET /api/links/types`

- This library's link vocabulary: each type's key, its label, its inverse label,
  and whether it is built in. Aliases are reported alongside, so a client that
  knows a display name can find the one key it maps to.

`GET /api/links/of/{end_id}`

- Every link touching one thing, **from either side**. "What relates to this
  line" is one question a reader asks, not two, so it is one call and two
  indexed reads. `include_deleted` shows withdrawn links.

`POST /api/links`

- Relates two ends by a typed link, with an optional `certainty` and `note`. An
  unknown link type is refused by name rather than being created on the fly: a
  vocabulary that grows by typo is not a vocabulary.
- Both refusals are `422`: an unknown link type (the sentence names the
  vocabulary), and a link missing one of its two ends. A display alias is
  resolved to its one key first, so `references` and `cites` are the same link
  rather than two.

### Interchange formats

`GET /api/formats`

- Which interchange formats this build reads and writes, with each one's
  extensions and whether it is schema-validated. A client asks rather than
  hard-coding a list that will be wrong the next release.

`POST /api/documents/{doc_id}/import`

- A PAGE XML, ALTO, hOCR, TEI or YOLO file becomes a **new pass** on the
  document. `format` forces a format instead of recognising one from the bytes;
  `name` says what to call the pass.
- An import does NOT become the working pass. Somebody else's file arriving is
  not a decision about which reading of the page is authoritative.
- Content the model has no field for is kept and labelled, so exporting back to
  that format writes it out again rather than quietly dropping it.
- The refusals are the point and carry a sentence the app is expected to show:
  `409` when this exact file is already a pass (the sentence names which),
  `422` when nothing recognises the file or its shapes lie outside the page it
  declares (the sentence names the formats this build reads, or the segments that
  disagree), `404` for no such document or an unreadable upload.

`GET /api/documents/{doc_id}/export/{format_name}`

- Writes one page out as PAGE XML, ALTO or TEI, returning the file as text with
  the filename to save it under, plus a **loss report**: what the format cannot
  carry, named rather than dropped silently.
- `pass_id` picks the pass (the working pass by default), `order_id` the reading
  order (as written by default), `reading_kind` which kind of reading to write.
- An export that does not validate against its schema is a reported failure and
  **no file**, because a file that exists and does not validate is one somebody
  sends to a colleague.
- Refuses with `404` for a format nothing here knows, for a document with no pass
  to export, and for an order that names nothing; `409` for a format this build
  reads but cannot write; `500` for an export that failed validation, which is
  our bug and not the caller's.
- The loss report is not a warning to be skipped. A format that cannot carry fine
  geometry, or direction, or a rival reading says so by name, and the round trip
  subtracts exactly what the report names.

## Page-model and paleography routes (2026-09)

Each line is drawn from the route's own summary in `openapi.json`.

**Campaigns**, the order in which a source's work was laid down:

- `GET /api/campaigns/document/{document_id}`: a source's campaigns, first laid down first.
- `GET /api/campaigns/reading/{representation_id}`: the campaigns of one reading.
- `GET /api/campaigns/segment/{segment_id}`: the campaign one segment belongs to.

**Conversion** of older results to the page model when a library opens:

- `GET /api/conversion/status`: what the conversion has done, is doing, and has left.
- `POST /api/conversion/{run_id}/seen`: a person has seen this run's report.

**Import**, pairing images with their layout files:

- `POST /api/documents/import-batch`: files dropped together (multipart), paired exactly as when their folder is dropped.
- `POST /api/ingest/files`: several files ingested as one set; a layout file that pairs with an image in the set becomes a pass on that image.

**Editorial, statements and matches:**

- `GET /api/editorial/segment/{segment_id}`: a segment's live editorial facts, and its counting reading.
- `GET /api/segments/{segment_id}/statements`: what is said about a segment. Each statement with its span on the line's reading (`char_start`, `char_end`); each mention with its span on the line, its span of the page text (`source_char_start`, `source_char_end`, which name it to correct it) and `corrected_by_person`.
- `POST /api/entities/{entity_id}/mentions/repoint`: the name at a mark is someone else; the mention at `document_id` + `char_start`..`char_end` of the page text moves to `to_entity_id` (`mention.repoint`, audited, undoable; #5602). The entity it left refuses that span, so a later extraction run does not put it back.
- `POST /api/entities/{entity_id}/mentions/respan`: the mention's words are wrong; it becomes `new_char_start`..`new_char_end` of the page text, on its line when the page is tied (`mention.respan`, audited, undoable). `422` for a span that is not words of the page text. Both answer with where the mention now sits and the `audit_id` to undo it.
- `GET /api/segments/document/{doc_id}/matches`: the matches recorded on one page, for review.
- `GET /api/segments/passes/{pass_id}/original`: the file an imported pass was read from, byte for byte.

**Places and georeferencing:**

- `GET /api/entities/{entity_id}/place`: a place as of a date, never the nearest geometry.
- `GET /api/entities/{entity_id}/linked-places`: a place as Linked Places Format.
- `GET /api/links/naming`: every segment that names a place `same_as` a URI.
- `GET /api/georeference/documents/{doc_id}/geojson`: an image's segments placed in the world, as GeoJSON.
- `GET /api/georeference/passes/{pass_id}/transform`: a pass's transform, with residuals.
- `PUT /api/georeference/passes/{pass_id}/transformation`: choose the transformation type; returns 422 with the number of GCPs needed when a pass has too few.
- `GET /api/georeference/segments/{segment_id}/world-shape`: one segment's shape in the world.

**Hands, meaning who wrote what:**

- `GET|POST /api/hands`: list the project's hands, or create one.
- `POST /api/hands/{hand_id}/withdraw`: withdraw a hand.
- `POST /api/hands/attributions`: attribute a segment to a hand.
- `POST /api/hands/attributions/{attribution_id}/withdraw`: withdraw an attribution.
- `GET /api/hands/segment/{segment_id}`: every live judgement of a segment's hand, rivals side by side.
- `GET /api/hands/{hand_id}/attributions`: everything in one hand that the caller may read.

**Letterforms and signs:**

- `GET /api/letterforms`: every live mark of a character, allograph or hand; at least one of the three must be named.
- `GET /api/letterforms/allographs`, `GET /api/letterforms/features`: the allographs, and the features in use.
- `GET /api/letterforms/segment/{segment_id}`: the letterform description of one segment.
- `GET|POST /api/signs`: list signs, or declare one.
- `GET /api/signs/{sign_id}/instances`: a sign's instances.
- `POST /api/signs/{sign_id}/withdraw`: withdraw a sign.

**Reading orders:**

- `GET /api/reading-orders/flows/onto/{document_id}`: the flows this page's segments could join, nearest earlier page first.
- `POST /api/reading-orders/{order_id}/place`: the single reorder call made by the Reader, the Inspector and the Segments pane. It is audited and undoable.

**Rights:**

- `POST /api/rights`: set rights on a target.
- `GET /api/rights/effective`: what applies to a target; every record above it, combined tighten-only.
- `POST /api/rights/{record_id}/withdraw`: withdraw a rights record.

**Fonts:**

- `GET /api/fonts`: the bundled fallback fonts, in fallback order.
- `GET /api/fonts/{name}`: one bundled font file, or its licence.

## Recipes and project setup

Spec: `docs/contributor_manual/specs/source/models-chains-and-projects.md` (`source.recipe.*`,
`source.onboard.*`, `source.project.*`).

- `GET /api/recipes/jobs`: every job a recipe can name, with what it takes and gives, its plain description and the `topic` that explains it.
- `GET /api/topics`, `GET /api/topics/{topic_id}`: each topic setup teaches and each recipe job, explained once (#5471): `kind` (`job` or `topic`), `title`, `short` (one sentence), `long` (a paragraph after it), `example` and `manual`. `404` for an unknown id. The text lives only in `fichero-server/src/fichero_server/recipes/seed/topics.yaml`; a job's name and description are read from it.
- `GET /api/recipes/purposes`: the purposes setup offers, in order, and whether each runs by itself.
- `POST /api/recipes/assemble`: the recipe the rules give for setup's answers, each choice with its reasons and each gap named; a whole recipe (`fichero_recipe`, `version`, `suits`) that passes the check. `left_off` lists the steps left off by default with why and their cost; Correct's carries `offered` when a cloud corrector's provider has a key set here (its `card`, `runs_on`, `pages`, `cost_usd`), offered at Ready, never turned on by itself (#5677). The Normalise step (`translate-transliterate-normalise`) carries `run_titles`, its runs by title in the order Start makes them: one for each reading level asked ("As written", "Abbreviations expanded", "Normalised spelling", "Modernised") and one for a translation ("Translation into English"); null on every other step (#5795). Writes nothing.
- `POST /api/recipes/check`: every reason a recipe cannot run as it stands, step by step.
- `GET /api/recipes/candidates?scripts=&languages=&material=&job=&online=`: every reader candidate for these scripts and languages (#5519), each a card saying where it came from (`source`: `shipped`, `installed`, `kraken-repository`, `hugging-face`), why it is offered (`offered_because`), what it states (scripts, languages, licence, size, published CER) and what the rules make of it (`rule_rank` in the fixed order, or `refused` with the rules' reason), and `measured` ("unmeasured on your pages until a bake-off measures it" until one does). Installed: every complete MLX vision model in the model store no shipped card pins, its card made from its own config and README (a model Fichero trained included). Kraken's repository: htrmopo's listing of Zenodo's `ocr_models` community (the call `kraken list` makes), Kraken recognition models only, newest version of each, kept in the model store's `discovery/` folder and fetched again at most daily; a record's published CER is ranked on only when it names the project's languages. Hugging Face: image-to-text and image-text-to-text models by task and language tag, MLX builds only (or a safetensors model's MLX conversion, found by its `base_model:` tag), never GGUF; listed with `in_recipe_rules: false` because Fichero cannot download a Hub model outside its catalogue yet. The network is reached only with `online=true` and never when the engine works offline (`FICHERO_LOCAL_ONLY` / `local_only_ai`); `sources` says what each source did (`read`, `searched`, `cached`, `not-searched`, `offline`, `failed`). `POST /api/recipes/assemble` and the bake-off choose from the shipped, installed and cached repository cards (never the network); an assembled step's `card.source` names where its card came from. `422` for an unknown script, language, material or job.
- `GET /api/recipes/htr-united?languages=&scripts=` (#5571): HTR-United's ground-truth datasets kept for these languages (required; codes or names) and scripts, most lines first, never the network (the search job keeps the catalogue). `fetched_at` is when it was kept (null: never searched). Each of `datasets` has `title`, `url`, `languages`, `scripts`, `handwriting`, `format`, `licence {name, url}`, `lines`, `pages`, and what it may be used as: `as` (`test-set`, `training`; empty until a licence outside the open ones is accepted), `accept` (the words to accept first, null when open) and `importable` (PAGE or ALTO). `422` for an unknown script or language.
- `GET|PUT /api/recipes/project`: the open project's saved setup answers and recipe (files in the project's `recipe/` folder). Saving is audited and undoable, and is not Start.
- `GET /api/recipes/project/start`: what Start would run — `runs`, in order, each a card: a shipped workflow (the steps it carries out, with the step's model as its override), a check run (`check`, its layer and checker) the project's synced folder (`export`, its folder and formats) or the project as a static site (`publish`, the folder its `where` names); `skipped`, each step Start cannot run with why (no model, a condition Start cannot honour yet, a cloud step in a project that keeps its pages here, a job no card runs yet); the steps only offered later (training); `refusals`, which stop Start (no recipe, a recipe that fails the check, nothing left to run, a model neither on this Mac nor downloading); `waiting`, the steps that wait for a model already downloading, in words, which do not stop Start (each such `downloads` entry has `downloading`, its `job_id` and its `progress`; the run's steps on it wait for it to land, #5660); the page count and the cost estimate — and the first yes once given. Each run carries `done`, `of` and a `note`: "already done on N of M pages" for splitting, finding lines and reading (a page already split, already with lines, or already read by the step's own model), or that the card cannot tell and runs on every page. `train_offers` lists, per trainable step, its ways and each way's `targets` (`place` this-mac, huggingface-jobs or cluster; `starts` and `params`; `held`, why a Hugging Face place stays an offer under a $0 spend cap, setup's `answers.hf_spend_cap_usd`; and for a cluster set up here, `first_run`, the attended first run's steps, with `starts` null), with the project's training `setting` (#5769) and its `noise_band` (`value`, `measured`, `basis`: the CER spread over 3 held-out splits an evaluation measured, else the ruled 0.5 CER points, #5692). `hf_spend` is this month's Hugging Face spend against that cap (`cap_usd`, `spent_at_most_usd`: each Job sent this month at its hardware's price an hour times its time limit, `jobs`, `unpriced`: Jobs with no listed price, never counted as $0, `month`, `sentence`; #5769).
- `POST /api/recipes/project/start`: the first yes. Records when Start was pressed and on which recipe version (`recipe/started.yaml`), audited and undoable, and runs the recipe over the project's material as one `run-a-recipe` job (#5390): the cards in order, each its own job beneath it (a workflow run, a check run, the synced folder's writes), a card starting only when the one before has finished, one that fails stopping those after it. `started.job_id` names the run. A step runs only on the pages that do not yet have its output, unless its id is in the optional body's `redo` (`{"redo": ["read"]}`). The cards include `Split Pages` (a photograph of an open notebook cut at its gutter; the steps after it read the cut pages) and, for a reading step pinned to a cloud or MLX model, `Read Lines (Kraken lines, vision model)`. `422` while the plan has refusals. After Start, on a purpose that runs by itself, each import runs the recipe over the pages it brought; on a "tools" purpose, nothing runs at import.
- `POST /api/recipes/project/start/use-instead`: use an installed model instead of downloading the one the plan waits for (#5583, `source.onboard.auto.installed-model-first`). Body `{model, card}`: `model` as the plan's `downloads` entry names it, `card` one of that entry's `instead` (each with its name and, when not open, its `licence`, which the press accepts). Kept as a project-scope override, as a bake-off's Use This is, so proposing the recipe again keeps it. `422` for a choice the plan does not offer.
- `POST /api/recipes/project/steps/use-candidate`: use any candidate `GET /api/recipes/candidates` lists as a step's reader (#5612, `source.find.app-card-actions`). Body `{step, card}`. Kept as a project-scope override by the path use-instead takes, through `project.save_setup` (audited, undoable); a model still to download is then a download the Start plan offers. Each candidate also carries `download` (`model.download` with its runtime and id, or null), `installed` and `runs_where` (`this_mac`, `own_machine`, `provider`). `422` for a card not found here, a step the recipe lacks, or a card that does not do the step's job.
- `GET /api/recipes/candidates` (#5660 items 3, 8): the online search also asks Hugging Face by name for HTR words (`htr`, `manuscript`, `trocr`, …) and the project's languages, so TrOCR fine-tunes and VLMs trained on manuscripts are found; one this build cannot run is listed with `availability: not_here` and `refused` in words, never chosen by the rules. Each candidate says where it stands (`availability`: `ships`, `installed`, `download`, `elsewhere`, `not_here`; `availability_words`, e.g. "Download (16 MB)"); a Kraken reader's weights are a `model.download` with runtime `kraken` until on this Mac. Each source's `detail` is one short sentence ("Searching Hugging Face…", "3 found on Zenodo"). `step=<id>` marks the open project's step's reader `chosen` and lists it first; a chosen reader holds when the recipe is proposed again, even for answers the finder would not list it for.
- `POST /api/recipes/project/layers`: add a layer (`{"layers": ["entities"]}`) or a language (`{"languages": ["la"]}`) to the project later (#5470, `source.onboard.add-layer`), audited (`project.add_layer`) and undoable. The layer joins the answers (`answers.layers`) and its steps join the recipe beside the ones it has (a model the person chose stays); a language proposes the recipe again from the answers. The layer's steps are proposed for the material already in the project (`recipe/proposed.yaml`): the Start plan returned carries `proposed` (the layers and each step with its topic's title and explanation) and, once the project has started, its runs and estimate are those steps alone. Nothing runs until `POST /api/recipes/project/start`, which runs them over all the material and clears the proposal. `{"remove": true}` takes a layer out and withdraws its proposed steps. `422` for a project not set up, an unknown layer (it names the ones it can add), or one it already has. `POST /api/recipes/assemble` takes the same `layers`.
- `POST /api/recipes/project/bakeoffs`: the bake-off for the reading step (#4951, slice 1: readers only). The evaluation job (`evaluation.run`, audited) run on the corrected sample pages (`page_ids`; none: every page with a pass a person made, whose lines are the right readings): the top three `read-a-line` readers by rule rank for the project's script and default material, plus Tesseract for print or typescript when its card has the project's language (never for handwriting), each read on the same pages and scored by the one CER. A candidate that cannot be scored here (not on this Mac, its runtime not in this build, a remote model) is in the table with why; a cloud one only where the project allows the cloud, priced for the whole volume first. `422` in words, with nothing run, below 100 corrected lines on two pages (saying how many more), for a project not set up, or when no candidate can be scored. The comparison is kept in `recipe/bakeoffs/<id>.yaml`. `GET /api/recipes/project/bakeoffs` lists them, newest first; `GET /api/recipes/project/bakeoffs/{id}` gives the pages, the job's state and the table (`rows`: CER under each policy and per page, local or remote, pages an hour measured in the run, whole-volume cost, carbon, trainability), ranked by the fixed order, its scores read from each model's card so the table outlives the job row. `POST /api/recipes/project/bakeoffs/{id}/use` (`{"card": ..., "scope": "project"|"folder", "folder_id": ...}`) is Use This: an override on the recipe (`overrides`) for that scope and, for the project, the step's model too, through `project.save_setup` (audited, undoable). **#5660 item 7:** beside the rules' top three, one of each kind of reader takes part (`role: contender`): Kraken, Apple Vision (read on this Mac, its recognised text the reading), an MLX vision model, and a cloud reader (scored only when the project lets pages leave, else priced and said; with no provider set up, "not available yet: add Claude (Anthropic) in Settings › AI"). Each row carries `wer` beside its CER. With `{"step": "find-lines"}` the line finders are compared instead (a `compare-line-finders` job): Kraken's segmenter and Apple Vision's text lines, each row with `lines_found` of `lines_checked` and `extra_lines`; the YOLO layout model is listed as finding regions, not lines; Use This takes Kraken's line finder only, the one the line step runs.
- `GET /api/recipes/project/automatic`: what runs by itself in this project (#5362), `on_add` (on the pages an import brings) and `on_correction` (on a page whose text a person corrects). Each entry names the job kind (`job`, as Activity's rows name it), its `name`, whether it `runs`, `why` in words (the setting that decides it), and the recipe `steps` it carries out. Pictures and search always run on an import; the NLP draft and the re-read of names follow the Ingestion setting; the recipe's own steps follow its first yes, a purpose that runs by itself, What runs by itself and the Start plan, and a step that will not run is listed with `job` null and the plan's why. Read from the same gates the import and the correction use; reads only.
- `GET /api/recipes/project/runs`: the project's recipe runs, newest first. `GET /api/recipes/project/runs/{job_id}`: one run: its state and reason in words, the pages it ran over (`documents`; none: all the project's material), each card's state (`waiting`, `running`, `done`, `failed`, `not run`) with its own job (`child_id`), its `job`, why, and, for a workflow stage that has started, its run's `account` (#5555, #5576); `waiting_for` (another recipe run, or what the running stage's pages wait for) and the running stage's `estimate_seconds_left`; and the skipped steps with why and their `fix` (`choose-model`, `allow-cloud`, or null). An import after Start whose recipe cannot run is a run too, `failed`, `started_by: "import"`, its `refusals` and `reason` saying why and what fixes it, and its pages not read (#5575). `GET /api/recipes/project/runs/{job_id}/summary`: what the run made over the pages it ran on (#5577): `pages`, `pages_read` (pages with a reading), `names` by kind and `dates` (the document knowledge graph's grouping), `statements`, `documents_proposed` (null until Find the Documents runs as a stage), each workflow stage's failed pages with its offer and `thread_id` for `POST /api/workflow-execution/threads/{thread_id}/read-again`, the skipped steps with their fixes, and the stages that did not run; `finished` false while it runs. `404` for no such run. The Start plan's `skipped` carry the same `fix`, and its `downloads` each name the model, its size and the download (`POST /api/local-models/download/{runtime}/{model}`).
- `GET /api/recipes/languages?q=`: search ISO 639-3 joined with Glottolog 5.3 (languages ISO lacks, and dialects) by name, tag or glottocode; each answer keeps its BCP 47 `code` and its `glottocode` apart, a dialect carrying its language's tag.
- `GET /api/iiif/iiif/lines/{document_id}`: a page's working-pass lines as a W3C AnnotationPage on its IIIF canvas, each the counting reading's text, language and maker, at line granularity, in canvas pixels.
- `POST /api/iiif/import`: start a job in Activity that imports a IIIF manifest or collection (an https URL; Presentation 2 or 3) into a folder bound to it, each canvas a page by reference; a source already bound imports into its folder, adding only new canvases. Returns the job id.
- `POST /api/iiif/folders/{folder_id}/refresh`: start the same job for a folder bound to a IIIF source; 404 when the folder has no source.
- `GET /api/recipes/derived?scripts=&period=`: what setup works out instead of asking, each fact with where it came from: per script its direction, whether it may be vertical and its bundled font, chosen from the script and the period (the saved period when none is given, and a font the project chose); this Mac's chip and memory; providers with a key (names only); places work can run.
- `PUT /api/recipes/font`: the transcription font the project chose for a script (`{script, font}`), saved in the project setup through the audited `project.save_setup` action; a font that does not cover the script is refused.
- `GET /api/recipes/routes?teacher=&local_reader=&pages=&sample_pages=`: what can be done with this many pages: the cloud, this-Mac and distil routes, each cost and time marked `measured`, `estimate` or `unknown`.
- `GET /api/recipes/scripts?q=`: search ISO 15924 scripts by name or code (the Unicode Consortium's table, shipped with the engine).
- `GET /api/settings/compute`: how hard local model work may push this Mac (`priority`: `balanced`, the default, keeps the Mac usable; `fast` drops the throttle; `background` yields to everything) and on which processor (`device`: `auto`, `cpu`, `gpu`), plus `effective`, what applies now (`FICHERO_COMPUTE_PRIORITY` / `FICHERO_COMPUTE_DEVICE` override the saved choice for a test run).
- `PUT /api/settings/compute`: save those preferences (owner only); Kraken reads them on its next page.
- A Kraken reader rides the run-level override: `provider_override: "kraken"` with `model_override` a catalogue id (`kraken-catmus-medieval`) or a `.mlmodel` path sets the reader of every node that reads lines with Kraken; a workflow with no such node refuses it (`400`).
