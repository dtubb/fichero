# Release Notes

*Full commit-level history, day by day, lives in [`CHANGELOG.md`](CHANGELOG.md).*

## 2026.07.18

### Improved

**Faster, more reliable local startup.** Fichero now owns the embedded engine at
the app level instead of tying it to a window. Heavy AI, workflow, image, and
network imports are deferred until they are needed; TLS preparation, token
reads, and package creation no longer block the first frame; and a proven local
readiness result is reused without leaking across a host switch.

**Safer imports and library lifecycle.** Path-based imports are confined to
approved roots, Move and Link modes reach the engine intact, route-based ingest
now emits audit and change events, and completed ingest tasks are bounded. When
a library closes in the app it also closes in the engine.

**More dependable workflows, exports, and knowledge data.** Every bundled
workflow preset now passes the execution validator, including the paleography
ensemble workflow. Parent-document exports include page-child transcription,
repeated knowledge claims are stored once with a mention count, and incomplete
task results fail instead of being reported as successful.

### Fixed

- Embedded-engine shutdown now drains live-update streams instead of force
  killing the process after a timeout.
- A broken iPhone or iPad pairing can return to the QR setup screen, and a
  single transient connection blip no longer immediately opens the outage pane.
- Paired remote devices can again load their permitted libraries and live
  update streams.
- Spawned engines no longer inherit environment flags that can disable
  authentication, while app-wide authorization-library requests no longer
  carry an unrelated library header.
- Cancelled thumbnail requests are no longer logged as image failures.

### Under The Hood

The dormant Swift test target was restored and expanded, and the frontend
source tree was reorganized by app surface without changing behavior. The
release gate now covers the real macOS test plan and the current per-platform
Xcode schemes.

## 2026.07.17.2

### Improved

**Faster engine launch.** The engine now defers optional workflow, MCP, and
provider imports until they are needed, reducing the work required before the
local API becomes available.

## 2026.07.17

### Improved

**Faster embedded-engine startup.** The bundled engine ships with precompiled
Python bytecode, waits until it is ready before restoring saved libraries, and
binds before optional heavyweight work. It no longer opens every known library
or warms embeddings during local startup.

**Faster library UI.** This build removes an artifact/entity N+1 fetch, avoids
unnecessary sidebar rebuilds, moves full-image decoding off the main thread,
and improves library filtering, reader, and knowledge-graph work.

**Paleography workflows.** New zoom/image-preparation tools, ensemble
transcription, and deterministic consistency checks are available in the
workflow library.

### Fixed

- Fixed local and embedded engines incorrectly showing a sign-in wall. A
  loopback engine now treats its host as the owner and keeps library-scope
  failures scoped to that library instead of calling them authentication
  failures.
- Fixed healthy launches briefly rendering as `Backend Not Connected` and
  removed a launch-blocking move-to-Applications modal.
- Fixed sandboxed builds opening a library added after engine launch, and
  hardened App Store helper signing and embedded-engine packaging.
- Fixed workflow selection so one click opens the selected workflow in the
  node editor.

## 2026.07.13.4-beta

Inspector and startup hardening after the first notarized beta.

### Improved

**Document Inspector.** Artifact, entity, claim, citation, annotation, note, and
knowledge-graph inspector paths are more consistent. Inspector selections now
preserve focus across tab routing, entity merges, and refreshes. Artifact clicks
route into inspector detail, entity names route into library search, and the
knowledge-graph browser warns when a cap truncates results.

**Mac shell polish.** Toolbar IDs, mini-toolbar chrome, split focus, sidebar PDF
drop targeting, empty activity windows, and live-update pause behavior were
tightened for the internal Mac test build.

**Connection and launch recovery.** Startup errors are classified more clearly,
library live-update streams wait until the backend is ready, and sandbox token
sync handles the UUID container path used by signed/sandboxed app launches.

### Fixed

- Fixed several inspector regressions around artifact selection, entity merge
  refresh, lower-detail layout, outline disclosure, and source routing.
- Fixed catalogue/page-level workflow output refresh so inspector content tracks
  page-scoped workflow results.
- Fixed local pairing QR PIN lookup and kept the shared engine bound to
  loopback unless sharing is intentionally enabled.
- Repaired Swift build and guardrail drift after the inspector and feature-tier
  batches.

## 2026.07.10-beta

The first notarized build, auto-updating via Sparkle.

### New

**Local models, managed for you.** Fichero can now download, store, and run
local models itself — a supervised MLX sidecar with its own isolated runtime,
gated on hardware that can actually run it. No terminal, no separate server.
Apple Intelligence and Apple Vision remain fully on-device options.

**Knowledge Graph, grown up.** Claims and entities now carry attribution —
speaker, quotation kind, language, audience, genre, and the source of the
confidence score. Claims link to other claims. Everything scopes to a page, a
document, or a folder, and keeps the passage it came from. Entities
de-duplicate; conflicting types get flagged rather than silently merged.

**Document Inspector V2.** Tabbed Info / Metadata / Content / Artifacts /
Knowledge Graph, alongside a multi-pane reading layout with a PDF page view and
per-page artifacts. Content is editable in place.

**Canvas and Space.** Library contents arrange on a 2D canvas or in a 3D space,
with layouts that persist per library.

**Translation.** Translate a document into a language you choose. The
translation is stored as its own artifact, embedded so it turns up in search,
and listed by language in the reader alongside the source. The immersive reader
gains a Source / Diplomatic selector, and every machine-made representation
carries its provenance and an **AI unreviewed** badge until a person says
otherwise.

**Bibliography.** A reference panel that extracts citations from a document,
resolves their metadata from a DOI or ISBN, lets you edit it in a native form,
imports references in bulk, and exports BibTeX. Deletes are undoable.

**Search.** Results show the matched excerpt in context, not just a filename.
Typos are tolerated, and exact matches rank above semantic neighbours.

**Users and sharing.** Fichero now has real user accounts. Libraries can be
shared, access granted and revoked per folder, and every mutation is recorded
with the account that made it. Off by default — a single-user library behaves
exactly as before.

**Device pairing.** Pair your own Macs and iPads over the local network with a
QR code and per-device tokens.

**Static export.** Export a library as a browsable, offline-searchable static
site with per-entity knowledge pages.

**`fichero` command line.** A typed command surface mirroring the engine's HTTP
API — engine lifecycle, library management, import, and a persisted registry of
known libraries.

**Primary Language setting**, and NFC path normalization so accented filenames
round-trip correctly between Finder, the database, and disk.

### Improved

**Chat** has a cleaner header, conversation-scoped attachments, and a compact
layout for iPhone and iPad.

**Cancellation.** Workflows can be cancelled mid-run, and workflow execution
moved off the main event loop — a slow node no longer freezes the engine.

**Multilingual catalogue reliability.** When Apple Intelligence refuses a
locale or trips a safety filter, the run falls back to your configured cloud
model instead of returning an empty catalogue.

**Undo** reaches the surfaces that promised it: documents, images, knowledge
graph and artifacts, claim links, annotations, classifications, snapshots,
bookmarks. Every audited action is recorded centrally, so ⌘Z works across the
app rather than in a handful of places — and when an undo fails it says so
instead of quietly doing nothing.

**Reading layouts.** Multi-page PDFs can be read one page at a time or several
up, with a layout picker in the reader.

**Knowledge graph housekeeping.** A possible-duplicates surface merges entities
in one click, with a picker for which record survives. Repeated claims from
different sources fold into a single canonical row.

**Errors say what happened.** Service, research, and per-library history
failures now surface the real message instead of a generic Cocoa error, and the
engine re-probes with backoff to recover a healthy connection rather than
failing the launch outright.

### Security

**Per-launch API token.** The engine binds loopback-only (`127.0.0.1`) and
requires a startup-generated bearer token
(`~/Library/Application Support/Fichero/.api-key`, mode `0600`). Fichero is not
reachable from the internet or your local network; the token closes the
remaining gap of other apps running as you on the same Mac.

**Audited writes.** Every backend mutation routes through one audited action
layer that records what changed and which account changed it.

**Path confinement.** A lexical `..` traversal in the library path allowlist is
closed, and the QuickLook preview sanitizes a server-supplied filename before
using it as a path. Annotation geometry and colour are validated on the way in.

**Fail loud, not quiet.** Export provenance gaps, importer degradation, and
startup misconfiguration now surface as errors instead of silently substituting
a default. A workflow fan-out that fails completely reports the failure rather
than returning an empty result, and values the pipeline cannot interpret are
routed to human review instead of guessed at.

### Fixed

- **Launch crash.** Opening a library window could crash the app: SwiftUI was
  registering the search field twice, once globally and again in individual
  mode views. Per-view search now defers to the single toolbar search, and the
  first-run provider sheet waits until the toolbar has laid itself out.
- **The app could not open its own library.** A sandboxed build was denied
  access to its container path, and a stale API token produced an
  authorization failure on a freshly started engine.
- **Activity progress and log** stream correctly. The workflow event stream was
  a single-consumer queue that starved a second subscriber, leaving 0% progress
  and an empty log; it is now a fan-out broadcaster with a replay buffer.
- **Chat** no longer blocks while the model is thinking, and it remembers the
  conversation — earlier turns are included in the prompt, and context survives
  a retry.
- **Knowledge Graph and the document reader** render again over the pinned
  engine connection.
- **Per-page transcription** applies across every Transcribe and Catalogue
  preset.
- **Shell**: iPhone inspector opens full-height; the macOS sidebar selection
  updates the view; the iOS reader hides desktop zoom on compact widths.
- Backend 500s on list endpoints, knowledge-graph cascade deletes, LanceDB
  fork-safety, a DuckDB upsert crash, re-OCR of already-digital PDFs, keyword
  over-extraction, and an assortment of inspector, thumbnail, and activity bugs.

### Under the hood

- Every list endpoint speaks one OpenAPI envelope contract, guarded by a
  permanent endpoint-walker test.
- The Swift app talks to the engine through generated, typed operations rather
  than hand-written requests.
- `scripts/verify_all.sh` (SwiftLint + Xcode test suite + backend contract
  tests) is the single answer to "is it green", wired to ⌘U, and renders its
  failures to an HTML dashboard.
- In Debug the engine runs externally; a Release build embeds and launches it,
  signed with hardened-runtime entitlements.
- A launch-crash smoke test boots the built `.app` and asserts it survives.
- Graph retrieval no longer scans the whole table; citation and reference
  filters run in the database.

### Known issues

- The live-updates event stream (`/api/changes/stream`) fails TLS on a
  self-signed `.local` certificate.
- IIIF endpoints are staged behind `FICHERO_FEATURE_TIER=dev` and are off in a
  release build.
