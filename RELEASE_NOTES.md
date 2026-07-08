# Fichero — Release Notes

What changed in each release you can actually download, newest first — Apple
"what's new" style, grouped **New / Improved / Security / Fixed**.

Releases are dated (CalVer) from 2026.07.08 onward. The one earlier public
build predates that scheme and keeps its original number, `0.0.1`. A release
entry is written when a build is signed and notarized — nothing appears here
that was never distributed. For the commit-level history of every working day,
see [`CHANGELOG.md`](CHANGELOG.md).

---

## 2026.07.08-beta

The first notarized, auto-updating build. It carries everything since the
April alpha: a matured knowledge graph, a redesigned reader and inspector, a
typed `fichero` command line, on-device local models, user accounts and
sharing, and a static-site export path.

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

---

## 0.0.1 — Alpha (2026-04-29)

### Added — Knowledge Graph layer

- Catalogue workflows now write structured `KnowledgeEntity` +
  `KnowledgeClaim` rows into a queryable layer alongside the
  human-readable markdown artifacts. Six entity types ship: **people,
  places, organizations, events, dates, keywords**.
- Each claim carries page-level provenance — `source_page_label` ("Page N")
  and `source_excerpt` (the literal passage). Substrate ready for
  cross-document views ("show me every page that mentions María Angel")
  in upcoming releases.
- New **Knowledge Graph section** in the Document Inspector — typed views
  per EntityType. Click an entity name to copy it to the clipboard for
  cross-document search.

### Added — Catalogue workflow variants

- **Catalogue (Apple Intelligence)** — runs the full catalogue pipeline
  entirely on-device using Apple Foundation Models (macOS 26+ Apple
  Silicon with Apple Intelligence enabled). Zero cloud calls.
- **Catalogue (composable)** — fans extraction across six per-section
  extractors so users can swap or customize one without touching others.
- **Per-page entity extraction** — multi-page docs split on the page
  boundary, run an LLM call per page in parallel, and each extracted
  entity carries its source page label.

### Added — Transcribe variants

- **Transcribe (Apple Vision)** — on-device OCR via macOS Vision
  framework. Renamed from the original `Transcribe`.
- **Transcribe (cloud)** — uses the user's chosen vision LLM (GPT-4o,
  Claude Sonnet, Qwen-VL, etc.). Better than Apple Vision for handwriting
  and historical scripts.

### Added — Document inspector redesign

- Tinderbox-style inspector with one panel per artifact: each panel is
  independently editable, has its own delete and save indicator, and
  shows the provider and model that produced it.
- Equal-divide panel heights — one panel fills the pane, two split in
  half, three thirds, and so on. Falls back to scrolling when too many
  to fit.
- AppKit ruler and format strip (Styles, alignment, spacing, lists)
  above each editable artifact panel.
- View → Show / Hide Ruler (⌃⌘R) to toggle the ruler and format strip
  globally.
- View → Find in Artifact (⌘F) for inline find within the focused panel.
- Per-page PDF artifact storage — each page gets its own artifact row,
  not just the parent PDF.

### Added — Workflow Library polish

- Default workflows ship with `folder_path` for menu grouping. The
  Library list now shows `Transcribe` and `Catalogue` as collapsible
  folder sections instead of a flat list.
- Canvas node icons read from the backend tool registry — no more
  generic gear icons on extractor / aggregator nodes.
- Run Workflow context menu on any document selection groups workflows
  by folder.

### Added — Activity / Inspector / Sidebar

- Cache-hit indicator on the Activity progress view so users can see
  when a workflow is reusing a prior result.
- Folder inspector: click a folder in the sidebar to see its contents,
  metadata, and workflow artifacts in the right-hand panel.

### Security

- **Engine API now requires a per-launch shared-secret token** (#742).
  The embedded engine binds to `127.0.0.1` (not exposed to any network)
  and additionally requires `Authorization: Bearer <token>` on every
  request. The token is generated fresh at engine startup, written to
  `~/Library/Application Support/Fichero/.api-key` with mode `0600`, and
  read by Fichero.app. Other apps running as the same user can no
  longer hit the API at `127.0.0.1:8765` without first reading the
  permission-restricted token file.
- Fichero is **not reachable from the internet or the local network** —
  loopback-only binding means external packets to `127.0.0.1` are
  dropped at the kernel before they reach the engine, with or without
  the token. The token closes the remaining gap of co-resident apps on
  the same Mac.
- Planned: migration to a Unix domain socket for tighter
  filesystem-permission-based isolation. Real macOS App Sandbox + XPC
  is on the longer-term roadmap.

### Changed

- **Generic catalogue extractors by default.** Archive-specific extractors
  (rivers, mines, properties, legal_references) are no longer in the
  default workflow but remain registered as draggable tools.
- **Catalogue cloud workflows** use `vision_mode: "llm"` by default so
  transcription uses the user's configured cloud vision provider. Use
  the standalone "Transcribe (Apple Vision)" workflow for on-device OCR.
- **Catalogue reducer** reads existing claims when they're present
  (composable workflow) instead of running a duplicate full-extraction
  LLM pass. Saves N-1 LLM calls per run.
- **Settings → Defaults model picker** shows only models you've
  configured for that provider under Settings → Models. Empty pickers
  mean "go add some" rather than "pick anything LiteLLM knows about."

### Fixed

- Workflow Library list endpoint returned empty after Reset Defaults
  because the default `folder_path="/"` filter excluded folder-grouped
  templates. Now optional; omit to return all.
- Default workflow templates duplicating on every install (backend
  dedupe in the seed routine).
- Inspector strict per-document scope — every `getArtifacts` call
  passes `includeDescendants: false` so child page artifacts no longer
  appear on parent documents.
- Folder inspector populates when nothing is selected.
- Sidebar drag for files and folders dropped from Finder routes
  correctly; first-click and activity run display fixed.
- Document inspector showing stale transcription after workflow
  completion.
- Catalogue artifacts not appearing after a workflow run.
- Bold and other rich-text formatting being silently dropped when
  saving an artifact edit.
- Deleted artifacts re-appearing after navigating away and back.
- Duplicate provider entries (e.g. "My OpenAI") accumulating across
  launches.
- Transcribe spinner getting stuck after all files completed.
- Activity run titles showing file paths and opaque IDs instead of
  readable workflow names.
- Grid view falling back to placeholder icons instead of thumbnails.
- LINK / COPY / MOVE ingest-mode badges not appearing on document rows.
- PDF preview zoom toolbar (zoom in/out, fit to window, 100%) and
  horizontal trackpad swipe page navigation.

### Removed

- Legacy single-text inspector — the per-artifact panel layout is the
  only inspector.

### Architecture (for the curious)

- **Backend KG layer connected.** `KnowledgeEntity`, `KnowledgeClaim`,
  `EntityMergeAudit` Pydantic models + `/api/entities` + `/api/claims`
  + `/api/graph_*` routes were already shipped in earlier work but
  unpopulated. Catalogue extractors now feed them via new
  `_entity_writer` helpers (`upsert_entity`, `save_claim`).
- **Apple Intelligence bridge** — `fichero-api/bin/fm-bridge/main.swift`
  is a 90-line Swift CLI wrapping `FoundationModels.LanguageModelSession`.
  Python `chat()` subprocesses it when `provider == "apple"`. Build with
  `fichero-api/bin/fm-bridge/build.sh`. The Foundation Models public
  API is Swift-native (not @objc-exposed), so pyobjc loads the classes
  but can't call their methods directly — subprocess pattern bridges
  the gap.

### Tests

- 49 new tests covering KG round-trip, extractor → KG integration, edge
  cases, API-level integration via FastAPI TestClient, per-page
  provenance, catalogue-consumes-claims, and default-workflow locks.
  297 workflow tests pass; 1993 backend tests pass.

### What's in this release (foundation features)

The Knowledge Graph layer + Apple Intelligence Catalogue are new in
0.0.1. The features below are also in this first public release:

- **Document library** with folder organization and file import. LINK
  mode (security-scoped bookmarks; zero disk usage) or COPY mode (APFS
  instant-cloning).
- **AI workflow engine** with visual node editor. LangGraph-backed
  execution with streaming progress. 30+ tools registered:
  transcription, entity extraction, summarization, classification,
  document conversion, custom LLM prompts, logic / control flow.
- **Multiple LLM providers** via LiteLLM routing. Local: Ollama,
  LM Studio, Apple Vision OCR, Apple Foundation Models (Apple
  Intelligence). Cloud: OpenAI, Anthropic, Google, Mistral, Cohere,
  Groq, Together, DeepSeek, OpenRouter, DashScope, xAI, Perplexity,
  Azure, Bedrock, HuggingFace, and more.
- **37+ supported file types** — PDFs, Word, RTF, plain text, images
  (JPEG/PNG/HEIC/RAW), audio (MP3/WAV/M4A), video, archives, code
  files, and more.
- **Embedded Python backend** (Fichero Engine,
  `com.fichero.fichero.engine`). Auto-launches when the app opens; no
  separate server to install or maintain.
- **Multi-window, multi-library** — open multiple libraries in
  separate windows.
- **Sparkle auto-update** wired (signed EdDSA appcast feed; first
  end-to-end update test happens against the next release).

### Not yet in this release (feature-gated or work-in-progress)

These are visible in the codebase but not user-facing in 0.0.1.
Will land in upcoming Alpha builds:

- **Semantic search** — vector embeddings exist (BAAI/bge-m3 via
  fastembed) but search UI / retrieval flow not yet wired end-to-end.
- **Chat** — feature-flagged off.
- **Agents** — feature-flagged off.
- **Automation** (triggers, schedules, folder watchers) — UI scaffolded,
  backend not wired.
- **Workflow Chains** (multi-workflow orchestration) — feature-flagged
  off.
- **MCP integrations** — feature-flagged off.

---

*This is the first public release. Earlier internal builds were never
distributed.*

---

*Full commit-level history, day by day, lives in [`CHANGELOG.md`](CHANGELOG.md).*
