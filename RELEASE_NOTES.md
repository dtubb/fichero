# Release Notes

*Full commit-level history, day by day, lives in [`CHANGELOG.md`](CHANGELOG.md).*

## 2026.08.01

### Dev build

The overnight build: 122 commits on top of the morning's 2026.07.29
release — the workflow-trust overhaul, the iPhone launch fix, and a
night-long bug sweep. Internal TestFlight + DMG dev prerelease from
green `integration` (1,990 XCTests + 1,927 Swift Testing + 8,500+
Python tests, 0 failures).

### Workflows you can trust

**Every run tells you what it did.** Artifacts now record which run and
step produced them; the artifact browser groups results by run in
pipeline order with "Produced by → View Run" navigation; and a new
Trace tab on every run shows the executed graph — each node colored by
what happened, with the provider and model actually used, timings, and
per-step outputs one click away.

**Results land where you're looking.** Transcriptions appear in the
content pane the moment a workflow writes them — no reselecting, from
any window, even runs launched from the CLI.

**Honest lifecycle.** Cancel stops multi-file steps within one file;
paused runs can be resumed, cancelled, or deleted; failed runs release
their documents instead of spinning forever; Cancelled shows as
Cancelled; and Pause/Resume/Stop buttons visibly do what they say.

**A node editor that explains itself.** Ports and connection types are
finally visible with distinct parallel edges, fan-out badges reflect
real behavior, execution order is numbered on the canvas, a Tidy
command lays the graph out, drops land under the cursor, and the
palette only offers tools that actually run. Zoom nodes show a live
tile-grid preview.

**Works out of the box.** A fresh install with no API keys runs every
default workflow on-device; a workflow that needs a missing key says so
before running, naming the provider. Default presets cleaned up
(internal components hidden from Run menus, explicit routing, real
source nodes).

### Fixed

**iPhone launches again.** The iOS TestFlight build crashed instantly at
launch: the shell's fully composed view type overflowed the iPhone's 1MB
main-thread stack during type-metadata instantiation (macOS's 8MB stack
absorbed the identical code). Bounded type-erasures at the compact layout's
chokepoints fix it (#4331).

**Edits can no longer vanish.** A rejected page-content save silently marked
the buffer clean, so the next refresh replaced your edit with stale content.
Saves are now transactional: a failure keeps the buffer dirty, shows an
inline error, and retries — and write conflicts with a running workflow
resolve with retries server-side instead of surfacing as an unexplained
error (#4285, #4286).

**Table sorting can't crash.** Sorting by Name crashed the app when the
persisted sort field had no matching table column; sort state now only emits
column-backed descriptors (#4282).

**Sidebar behaves.** Chevron prefetch restored (#4294), selection survives
tree rebuilds (#4297), drop-hover highlights only the target row instead of
washing the whole subtree (#4229), folders dropped at the library root import
at the root instead of vanishing into Inbox (#4274), and per-row progress
spinners reflect actual running work regardless of selection (#4295).

**Workflows tell the truth.** Single-page runs no longer widen to the whole
PDF (#4298); runs where every file failed record as failed with the real
error instead of a green checkmark (#4283); newly added AI providers appear
in the Run Workflow menu immediately, from any window or device (#4276); and
a connection error in the status island clears itself once the server is
reachable again (#4296).

### New

**iPhone essentials.** Tapping a document on iPhone opens the reader again
(#2666), first-run setup skips the Mac-only steps (#2807), and list rows get
native swipe-to-delete (#2501).

**Recognized-text boxes.** Every OCR/transcription pass now stores the text's
bounding geometry, and the reader gains a Text Boxes overlay showing exactly
where each recognized line sits on the page (#4309).

**Convert to Markdown, HTML, and SVG.** New AI conversion workflows render a
page into portable formats, viewable in place — flip a page between its image
and its generated rendition in the reader (#4329).

**Chat with your library.** The research chat now answers through audited,
read-only library tools with each tool call visible and attributed, and
creating a chat works without an AI provider configured (#2067, #4308).
## 2026.07.29

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration` — the
first release gated end-to-end by the new serialized test harness (full unit,
engine, transport-matrix, and UI-session legs all green).

**Fixed**
- Sidebar rows no longer jump after the list loads; root ordering is stable.
- Sidebar clicks are faster: the selection path uses an O(1) index instead of
  re-walking the whole tree, prefetch batches its cache writes, and disclosure
  toggles no longer trigger needless preference writes.
- Folder selection and drops show a loading/importing state immediately
  instead of a dead interval or a false "No Documents".
- Import status can no longer stick at "5/5" after an import finishes.
- Thumbnails: intermittent 500s fixed (alias sync is idempotent and atomic);
  imported images now get thumbnails via a background derivative stage instead
  of staying "Pending"; HEIC photos are supported.
- Legacy .doc files that failed with "Malformed MiniFAT" now extract via a
  fallback reader.
- iCloud placeholder files are refused loudly at import instead of importing
  as empty records.
- Ingest and serving path rules are unified — anything importable is servable.
- Canvas (2D/3D) view modes share the library selection with the list views.
- Engine startup prints a transport diagnostic naming exactly what bound
  where and what a client must set (ends the socket-path guessing game).

**App icon**
- New Icon Composer app icon.

## 2026.07.26

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration`.

### New

**Instant launch.** The window mounts real content on the first frame:
saved libraries materialize before the scene graph builds, and nothing
waits for the engine health probe anymore — data streams in as the
engine connects (#4036). Warm first frame dropped from ~1.9s to ~1.4s,
and it shows your library shell instead of a spinner.

**Xcode-style status island.** Engine state, background activity, and
errors now live in one center toolbar island beside the title — a
message area ("Starting engine…", import progress, running workflows,
errors in red) flanked by the engine button (connection details +
Retry) and the activity button (task list). The full-window
"Connecting to backend…" takeover and the login-wall flash at launch
are gone; a broken connection is visible chrome, never a blocked app.

**Finder-grade sidebar.** The full drag grammar landed: insertion-line
drops, Option-drag copies (through the audited `document.duplicate`
deep-copy action), Finder-style aliases (badge, target resolution,
Make Alias), Duplicate parity for workflows, saved searches, and
conversations, multi-item drop feedback, count-aware Delete, and
right-arrow handing keyboard focus from a leaf row to the content
pane. Every library gets its own header row, and the pinned bottom
navigation rows are retired. Document-scoped chat is back on Mac as a
context-menu command on the document ("Add to Chat").

### Fixed

- **100% CPU at idle** — a per-frame UserDefaults write spun the
  AttributeGraph; the app idles at 0% again.
- **Default Workflows tree** — presets seed into the global library
  only, subfolder ids route correctly (no embedded slashes), legacy
  preset folders that lingered at the sidebar's top level re-home
  under the locked "Default Workflows" container on next open, the
  container's read-only lock is enforced on document actions, and
  re-seeding no longer resurrects soft-deleted workflow mirrors.
- **One path, not four** — the location breadcrumb renders only in the
  toolbar; the duplicate in-window path bars are gone and the bottom
  status bar is Finder-style (what's selected, not where it is).
- **Cycle-creating document moves are rejected** by the engine.
- Restored-selection reconcile + launch invalidation storm fixed.

### Under The Hood

The macOS verify leg is genuinely green: a MainActor-isolation crash
that killed the test host mid-run, three stale contracts hidden from
failure greps, and a sub-millisecond Date flake are fixed. New engine
tests cover the Default Workflows tree heal.

## 2026.07.24

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration` after
fast-forwarding it into `main` via the new `scripts/merge-integration-to-main.sh`
pre-step. Not promoted to production.

> **Note:** the `v2026.07.23` tag was cut from `main@d141bc139` (the
> 2026.07.22-beta code) before the `integration` lane was merged, so its build
> did **not** contain the workflow sidebar nodes or the chat-tools agent loop.
> `2026.07.24` is the first release that actually ships that work.

### New

**Workflow nodes in the library sidebar.** Workflows now render as real nodes
under their folders in the library sidebar tree (#4 / #2081) — previously only
the folders showed.

**Read-only chat-tools agent loop.** A read-only agentic chat loop
(`chat_tools.py`) is wired into `/api/chat` behind the `FICHERO_CHAT_TOOLS`
flag (#3 / #1847 / #1848). The model acts as a user issuing audited MCP tools.

### Under The Hood

**Release infra.** `scripts/release-all.sh` now takes `--dev` / `--tier
<release|beta|alpha|dev>` to bake the full dev feature surface (Dev Embedded
mac config + dev `FICHERO_FEATURE_TIER` on iOS), not just stripped release
features. `scripts/merge-integration-to-main.sh` fast-forwards `integration`
into `main` and pushes as the pre-step before a release — so releases no longer
ship without the lane's work.

## 2026.07.23

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `integration`. Not
promoted to production.

### Under The Hood

**Connection hygiene complete.** Every app↔engine call now routes through the
centralized `FicheroClient` transport (UDS / HTTPS-when-sharing / in-memory) —
no remaining hand-rolled `URLSession` bypasses. `EntityService` (the inspector's
"0 entities" bug), `ImageEditingService` preview, the knowledge-graph web pane,
and the workflow diagram were all migrated. The KG web pane works over UDS via a
`WKURLSchemeHandler` bridge (no new network listener), and the workflow diagram
now renders live mermaid (`mermaid.js` in a `WKWebView`) instead of a broken
JSON-as-image.

**Legible failures.** A typed `ConnectionError` classifies transport failures by
`{transport, operation, cause}` so an error names itself instead of a bare
`NSURLErrorDomain -1004`. A wrapped-cancellation fix (`Error.isCancellationError`
across ~60 sites) stops superseded inspector/store loads from mislogging as
failures.

**Fixes.** Sidebar folder-node click (workflow/search/chat folders showed
nothing) now navigates correctly.

**Engine cleanup + speed.** The 61 flat re-export shims left by the package reorg
were removed and 487 callers repointed to the restructured paths; `cryptography`
was deferred off the startup import graph (−50 modules). ModelComparison moved to
an `@Observable` store (#1863). Full engine suite green (7955 passed / 0 failed).

## 2026.07.21-beta

### Dev build

Internal TestFlight + DMG dev prerelease cut from green `main` for Daniel's
testing. Not promoted to production.

### Under The Hood

**Engine hygiene reorg landed on `main`.** The engine's top-level packages were
reorganized into `mcp/`, `security/`, `llm/`, `db/`, `models/`, and `kg/` using
identity-preserving `sys.modules` shims, so every existing import keeps
resolving. Full engine suite green (8048 passed / 0 failed). Route count held at
360 and guardrail allowlists were repointed to the new package paths.

**Transport architecture done.** A pluggable `ClientTransport` seam routes the
app↔engine connection by platform: Unix domain sockets for local Mac, HTTPS
for iOS / remote / sharing / Debug, and in-memory for the Mac Dev/DMG path.
Loopback + UDS/in-memory connections are owner-scoped with no login wall;
`AuthTokenMiddleware` recognizes `http+unix` for bootstrap tokens.

**Crash self-heal.** The embedded engine auto-restarts on an unexpected crash
with a crash-loop guard (max 5 restarts / 60 s, then `.failed`) instead of
needing a manual Retry.

**Test reliability.** Auth middleware now attaches at conftest load, before any
module can start the shared app, fixing the "Cannot add middleware" cascade in
verify-all. `library_discovery.py` (dead home-crawl) was removed; the
recents-registry is the list source.

## 2026.07.20-beta

### New

**Workflow nodes in the sidebar.** Saved workflows now appear in the library
tree. Built-in presets are grouped under a locked **Default Workflows**
hierarchy; duplicate a default to create an editable library copy.

### Improved

**Settings navigation.** The Settings detail pane now has System
Settings-style back and forward controls plus a clearer section header.

### Testing Build

This prerelease uses Fichero's development feature tier, exposing every
implemented app surface and workflow tool for testing.

### Under The Hood

Large SwiftUI files across the app shell, library, sidebar, previews,
Inspector, services, and platform bridges were split into focused extensions
without changing behavior. Source-contract tests were updated to follow the
new file boundaries.

## 2026.07.19.2

### Improved

**RealityKit canvas rendering.** The 2D Canvas and 3D Space views now use the
RealityKit renderers by default. The previous renderers remain available as a
revert path while the new interaction and visual behavior is validated.

**Clearer Settings.** Settings now uses a System Settings-style sidebar with
clearer section names, colored icons, and pairing controls grouped under
Sharing.

### Fixed

- Release builds now reconstruct the embedded Briefcase engine from current
  source every time instead of reusing a potentially stale staged bundle.
- The app, embedded engine bundle, and installed Python package now carry the
  same release version.
- Newest-first activity ordering now handles ISO 8601 timestamps both with and
  without fractional seconds.
- Switching libraries now preserves the app's configured secure network
  session, and Boolean activity metadata displays as `true`/`false` instead of
  `1`/`0`.
- Invalid action payloads now fail safely instead of crashing the app. Legacy
  decomposed library paths normalize correctly, and whitespace-only searches
  remain a local no-op instead of reaching the engine.

### Under The Hood

The Inspector, embedded-engine lifecycle service, chat views, and entity
service were split into smaller concern-focused files without changing their
behavior. The release gate also resolves the shared project Python correctly
when run from a git worktree.

## 2026.07.19

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
