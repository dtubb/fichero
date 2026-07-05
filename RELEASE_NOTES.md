# Fichero — Release Notes

Newest first. Apple "what's new" style — grouped **New / Improved / Security / Fixed**.

## Highlights

**New — Knowledge Graph layer.** Catalogue workflows write queryable entity rows (people, places, organizations, events, dates, keywords) alongside the readable markdown — each with page-level provenance.

**New — Catalogue & Transcribe presets.** *Catalogue* (one cloud pass), *Catalogue (composable)* (six swappable per-section extractors), *Catalogue (Apple Intelligence)* (fully on-device, no cloud), plus *Transcribe (Apple Vision)* and cloud *Transcribe* for handwriting.

**New — Per-page extraction.** Multi-page documents extract page-by-page; every entity carries its source page — groundwork for cross-document views.

**Improved — Workflow Library.** Folder grouping, generic extractors by default (archive-specific ones stay as draggable tools), real SF Symbol node icons.

**Improved — Settings.** Model picker reads configured providers; folder inspector on empty selection; orientation-aware grid thumbnails.

**Security — Per-launch API token.** The engine binds loopback-only (`127.0.0.1`) and requires a startup-generated bearer token (`~/Library/Application Support/Fichero/.api-key`, `0600`), closing same-Mac API access. Unix-socket isolation planned next.

**Fixed.** Empty Workflow Library after Reset Defaults; template duplication on install; composable-catalogue duplicate extraction pass; assorted inspector/sidebar bugs.

---

## Curated changelog

Hand-written release entries, newest first, folded in from the former
`CHANGELOG.md`. The dated changelog below is generated from git history by
`scripts/release-notes-gen.sh`; add curated highlights here, not in the
generated section.

### 0.0.2 — Alpha (unreleased)

Stability + reliability release: backend hardening, the knowledge-graph layer,
a typed CLI surface, and the redesigned document inspector. Packaging
(notarization, signing) is the only remaining gate.

#### Fixed

- **Activity live progress + log** now stream — the workflow SSE was a
  single-consumer queue that starved a second subscriber (0% progress, empty
  log); replaced with a fan-out broadcaster + replay buffer, and `totalFiles`
  is seeded from file events.
- **Knowledge Graph + document reader** render again over the pinned-HTTPS
  engine (the WKWebView now honours the same cert pin as the URLSession stack).
- **Per-page transcription** applies across every Transcribe/Catalogue preset.
- **Shell**: iPhone inspector opens full-height; macOS sidebar selection updates
  the view; iOS reader hides desktop zoom on compact; sidebar/library
  mini-toolbars use Liquid Glass.
- *(known issue, in progress)* `/api/changes/stream` live-updates SSE fails TLS
  on the self-signed/`.local` cert — its pinned-session trust path regressed.

#### Added

- **Knowledge Graph maturity** — claim/entity attribution (speaker, quotation
  kind, language, audience, genre, confidence source), canonical verbs,
  claim↔claim links, and at-page / at-doc / at-folder scoping with context.
  Entity de-duplication, type-conflict detection, source-text grounding for events.
- **Document Inspector V2** — tabbed Info / Metadata / Content (editable) /
  Artifacts / Knowledge Graph, plus a multi-pane reading layout with a PDF page
  view and per-page artifacts.
- **`fichero` CLI** — typed command surface mirroring the engine's HTTP API,
  with engine lifecycle (`status`/`start`/`stop`/`restart`), library management,
  and a persisted known-library registry.
- **Workflow cancellation** endpoint + CLI; workflow execution moved off the
  main event loop so a blocking node no longer freezes the backend.
- **Multilingual catalogue reliability** — Apple Intelligence locale/safety
  refusals fall back to the configured cloud model instead of an empty
  catalogue; reasoning-enabled narrative synthesis; tunable per-section claim
  caps. (Detail in `docs/release-notes-0.0.2.md`.)
- **Engine auth** — shared-secret token between the engine and the Swift app.

#### Changed

- **Unified verification gate** — `scripts/verify_all.sh` (SwiftLint + Xcode test
  suite + `CrossLanguageGateTests` → `scripts/verify_python.sh`) is the single
  source of truth for "is it green", wired to ⌘U.
- All list endpoints unified on the OpenAPI envelope contract, guarded by a
  permanent endpoint-walker contract test.

#### Fixed

- Backend 500s (bare-list-under-envelope responses), KG claim cascade-delete,
  LanceDB fork-safety, DuckDB upsert crash, transcribe re-OCR of digital PDFs,
  keyword over-extraction, and assorted SwiftUI inspector / thumbnail / activity bugs.

---

### 2026.04.29 — Alpha

#### Added — Knowledge Graph layer

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

#### Added — Catalogue workflow variants

- **Catalogue (Apple Intelligence)** — runs the full catalogue pipeline
  entirely on-device using Apple Foundation Models (macOS 26+ Apple
  Silicon with Apple Intelligence enabled). Zero cloud calls.
- **Catalogue (composable)** — fans extraction across six per-section
  extractors so users can swap or customize one without touching others.
- **Per-page entity extraction** — multi-page docs split on the page
  boundary, run an LLM call per page in parallel, and each extracted
  entity carries its source page label.

#### Added — Transcribe variants

- **Transcribe (Apple Vision)** — on-device OCR via macOS Vision
  framework. Renamed from the original `Transcribe`.
- **Transcribe (cloud)** — uses the user's chosen vision LLM (GPT-4o,
  Claude Sonnet, Qwen-VL, etc.). Better than Apple Vision for handwriting
  and historical scripts.

#### Added — Document inspector redesign

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

#### Added — Workflow Library polish

- Default workflows ship with `folder_path` for menu grouping. The
  Library list now shows `Transcribe` and `Catalogue` as collapsible
  folder sections instead of a flat list.
- Canvas node icons read from the backend tool registry — no more
  generic gear icons on extractor / aggregator nodes.
- Run Workflow context menu on any document selection groups workflows
  by folder.

#### Added — Activity / Inspector / Sidebar

- Cache-hit indicator on the Activity progress view so users can see
  when a workflow is reusing a prior result.
- Folder inspector: click a folder in the sidebar to see its contents,
  metadata, and workflow artifacts in the right-hand panel.

#### Security

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
- Planned for 0.0.3: migration to a Unix domain socket for tighter
  filesystem-permission-based isolation. Real macOS App Sandbox + XPC
  is on the longer-term roadmap.

#### Changed

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

#### Fixed

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

#### Removed

- Legacy single-text inspector — the per-artifact panel layout is the
  only inspector.

#### Architecture (for the curious)

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

#### Tests

- 49 new tests covering KG round-trip, extractor → KG integration, edge
  cases, API-level integration via FastAPI TestClient, per-page
  provenance, catalogue-consumes-claims, and default-workflow locks.
  297 workflow tests pass; 1993 backend tests pass.

#### What's in this release (foundation features)

The Knowledge Graph layer + Apple Intelligence Catalogue are new in
2026.04.29. The features below are also in this first public release:

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

#### Not yet in this release (feature-gated or work-in-progress)

These are visible in the codebase but not user-facing in 2026.04.29.
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

## Dated changelog

Generated from git history (non-merge commits, conventional-commit subjects), newest first, grouped by type within each day. Covers the SwiftUI/Python era from the 2025-12-05 pivot forward (#2572).

### 2026-07-05

**Features**

- feat(swiftui): bottom-anchor the remaining Preview mini-toolbars ([#3060](https://github.com/dtubb/fichero/issues/3060))

**Tests**

- test: green the safe verify-failure batch by fixing explicit embedding autoschedule assertions and reclassifying dead-files / stale-baseline guardrails as current reality or real remaining debt ([#2962](https://github.com/dtubb/fichero/issues/2962), [#2955](https://github.com/dtubb/fichero/issues/2955), [#2956](https://github.com/dtubb/fichero/issues/2956), [#2957](https://github.com/dtubb/fichero/issues/2957), [#2958](https://github.com/dtubb/fichero/issues/2958), [#2960](https://github.com/dtubb/fichero/issues/2960), [#2963](https://github.com/dtubb/fichero/issues/2963))

**Docs**

- docs: add subtree `AGENTS.md` files for `fichero/` and `fichero-engine/`, then audit and tighten `fichero-engine/scripts/README.md` against the current supported script set ([#2554](https://github.com/dtubb/fichero/issues/2554), [#2552](https://github.com/dtubb/fichero/issues/2552))

### 2026-07-04

**Features**

- feat(local-models): ship the managed local-inference stack — supervised MLX sidecar, isolated runtime provisioning, model download/store management, fm-bridge packaging, hardware gating, and iOS subprocess-provider gating ([#3114](https://github.com/dtubb/fichero/issues/3114), [#3115](https://github.com/dtubb/fichero/issues/3115), [#3116](https://github.com/dtubb/fichero/issues/3116), [#3117](https://github.com/dtubb/fichero/issues/3117), [#3118](https://github.com/dtubb/fichero/issues/3118), [#3119](https://github.com/dtubb/fichero/issues/3119), [#3122](https://github.com/dtubb/fichero/issues/3122))
- feat(canvas/space): land the renderer-agnostic CanvasScene contract, new 2D/3D renderer work, per-library canvas stores, real canvas-layout persistence, and the `/api/canvas/*` rename away from Mind Palace ([#3078](https://github.com/dtubb/fichero/issues/3078), [#3079](https://github.com/dtubb/fichero/issues/3079), [#3080](https://github.com/dtubb/fichero/issues/3080), [#3081](https://github.com/dtubb/fichero/issues/3081), [#3082](https://github.com/dtubb/fichero/issues/3082), [#3083](https://github.com/dtubb/fichero/issues/3083), [#3084](https://github.com/dtubb/fichero/issues/3084), [#3086](https://github.com/dtubb/fichero/issues/3086), [#3088](https://github.com/dtubb/fichero/issues/3088), [#3090](https://github.com/dtubb/fichero/issues/3090), [#3103](https://github.com/dtubb/fichero/issues/3103), [#3104](https://github.com/dtubb/fichero/issues/3104))
- feat(unicode): ship NFC path normalization, collision detection/prompting, snapshot file coverage, and the synthetic-data mojibake merge engine plus sidecar union/hardening work ([#3071](https://github.com/dtubb/fichero/issues/3071), [#3072](https://github.com/dtubb/fichero/issues/3072), [#3073](https://github.com/dtubb/fichero/issues/3073), [#3074](https://github.com/dtubb/fichero/issues/3074), [#3075](https://github.com/dtubb/fichero/issues/3075), [#3076](https://github.com/dtubb/fichero/issues/3076))
- feat(pairing/export/search): add device-token renewal and pairing payload v2, static export E1-E3 (shared record stream, Eleventy knowledge pages, offline search), matched-excerpt search previews, geo/export wiring, and the Primary Language setting ([#3095](https://github.com/dtubb/fichero/issues/3095), [#3097](https://github.com/dtubb/fichero/issues/3097), [#3124](https://github.com/dtubb/fichero/issues/3124), [#3125](https://github.com/dtubb/fichero/issues/3125), [#3126](https://github.com/dtubb/fichero/issues/3126), [#1781](https://github.com/dtubb/fichero/issues/1781), [#3055](https://github.com/dtubb/fichero/issues/3055), [#1808](https://github.com/dtubb/fichero/issues/1808))

**Fixes**

- fix(action-layer): route a broad backend write surface through audited registry actions and add undo where promised — documents, images, KG/artifacts, claim-links, annotations, classifications, folder-canvas, hermeneutics, research, snapshots, authz role changes, library links, bookmarks, and image straighten ([#3003](https://github.com/dtubb/fichero/issues/3003), [#3004](https://github.com/dtubb/fichero/issues/3004), [#3005](https://github.com/dtubb/fichero/issues/3005), [#3006](https://github.com/dtubb/fichero/issues/3006), [#3007](https://github.com/dtubb/fichero/issues/3007), [#3020](https://github.com/dtubb/fichero/issues/3020), [#3021](https://github.com/dtubb/fichero/issues/3021), [#3022](https://github.com/dtubb/fichero/issues/3022), [#3023](https://github.com/dtubb/fichero/issues/3023), [#3024](https://github.com/dtubb/fichero/issues/3024), [#3025](https://github.com/dtubb/fichero/issues/3025), [#2982](https://github.com/dtubb/fichero/issues/2982), [#2984](https://github.com/dtubb/fichero/issues/2984), [#2985](https://github.com/dtubb/fichero/issues/2985), [#2986](https://github.com/dtubb/fichero/issues/2986))
- fix(frontend transport): retire more raw `APIClient` usage by migrating document, action, image-edit, MCP, automation, and chain flows onto typed generated operations, while tightening the OpenAPI types those migrations needed ([#3028](https://github.com/dtubb/fichero/issues/3028), [#3029](https://github.com/dtubb/fichero/issues/3029), [#3030](https://github.com/dtubb/fichero/issues/3030), [#3131](https://github.com/dtubb/fichero/issues/3131), [#3136](https://github.com/dtubb/fichero/issues/3136))
- fix(hardening): fail loud on export provenance/cost gaps, importer degradation paths, startup defaults, Bonjour trust hints, ingest tri-state handling, and the closed-handle DuckDB bookmark path ([#3127](https://github.com/dtubb/fichero/issues/3127), [#3128](https://github.com/dtubb/fichero/issues/3128), [#3132](https://github.com/dtubb/fichero/issues/3132), [#3133](https://github.com/dtubb/fichero/issues/3133), [#3134](https://github.com/dtubb/fichero/issues/3134), [#3135](https://github.com/dtubb/fichero/issues/3135), [#3099](https://github.com/dtubb/fichero/issues/3099), [#3110](https://github.com/dtubb/fichero/issues/3110), [#2876](https://github.com/dtubb/fichero/issues/2876), [#3068](https://github.com/dtubb/fichero/issues/3068))

**Tests**

- test: add adversarial and edge hardening around pairing, unicode merges, snapshots, canvas layout persistence, local-model startup, export regressions, search previews, bookmark DB lifecycle, and typed response schemas ([#3100](https://github.com/dtubb/fichero/issues/3100), [#3071](https://github.com/dtubb/fichero/issues/3071), [#3072](https://github.com/dtubb/fichero/issues/3072), [#3073](https://github.com/dtubb/fichero/issues/3073), [#3074](https://github.com/dtubb/fichero/issues/3074), [#3078](https://github.com/dtubb/fichero/issues/3078), [#2180](https://github.com/dtubb/fichero/issues/2180), [#1781](https://github.com/dtubb/fichero/issues/1781), [#3068](https://github.com/dtubb/fichero/issues/3068))

### 2026-07-03

**Features**

- feat(devex/cli): expand the typed CLI around per-user auth sessions, canonical resource nouns, generated `--field` flags, and importer-over-HTTP routing for many import surfaces ([#2889](https://github.com/dtubb/fichero/issues/2889), [#2890](https://github.com/dtubb/fichero/issues/2890), [#2891](https://github.com/dtubb/fichero/issues/2891), [#2916](https://github.com/dtubb/fichero/issues/2916), [#2917](https://github.com/dtubb/fichero/issues/2917), [#2918](https://github.com/dtubb/fichero/issues/2918), [#2919](https://github.com/dtubb/fichero/issues/2919), [#2920](https://github.com/dtubb/fichero/issues/2920), [#2921](https://github.com/dtubb/fichero/issues/2921), [#2922](https://github.com/dtubb/fichero/issues/2922), [#2923](https://github.com/dtubb/fichero/issues/2923), [#2924](https://github.com/dtubb/fichero/issues/2924), [#2925](https://github.com/dtubb/fichero/issues/2925), [#2926](https://github.com/dtubb/fichero/issues/2926), [#2927](https://github.com/dtubb/fichero/issues/2927), [#2893](https://github.com/dtubb/fichero/issues/2893))
- feat(multiuser/connection): land per-library backend hosts, authenticated readiness/no-adoption launch flow, sharing + ACL grant/revoke, and the first multi-user login gate slices ([#2862](https://github.com/dtubb/fichero/issues/2862), [#2863](https://github.com/dtubb/fichero/issues/2863), [#2864](https://github.com/dtubb/fichero/issues/2864), [#2866](https://github.com/dtubb/fichero/issues/2866), [#2867](https://github.com/dtubb/fichero/issues/2867), [#2869](https://github.com/dtubb/fichero/issues/2869), [#2021](https://github.com/dtubb/fichero/issues/2021), [#2022](https://github.com/dtubb/fichero/issues/2022))
- feat(shell/chat): ship the compact-shell and chat cleanup batch — adaptive layout policy, compact entity browser, attach-sheet and move-to-folder cleanup, Xcode-style chat header, and conversation-scope attach flows ([#1926](https://github.com/dtubb/fichero/issues/1926), [#2551](https://github.com/dtubb/fichero/issues/2551), [#3008](https://github.com/dtubb/fichero/issues/3008), [#3009](https://github.com/dtubb/fichero/issues/3009), [#3010](https://github.com/dtubb/fichero/issues/3010), [#3011](https://github.com/dtubb/fichero/issues/3011), [#3014](https://github.com/dtubb/fichero/issues/3014), [#3015](https://github.com/dtubb/fichero/issues/3015), [#3016](https://github.com/dtubb/fichero/issues/3016), [#3017](https://github.com/dtubb/fichero/issues/3017), [#3019](https://github.com/dtubb/fichero/issues/3019), [#2449](https://github.com/dtubb/fichero/issues/2449), [#3056](https://github.com/dtubb/fichero/issues/3056), [#3057](https://github.com/dtubb/fichero/issues/3057), [#3058](https://github.com/dtubb/fichero/issues/3058), [#3059](https://github.com/dtubb/fichero/issues/3059), [#3061](https://github.com/dtubb/fichero/issues/3061))

**Fixes**

- fix(cli/contracts): close the generated ingest payload and migration-status regressions, add generated GET smoke coverage, and drain the first API-surface CLI contract suite batch across KG, docs, orchestration, providers, search, and library-admin surfaces ([#3047](https://github.com/dtubb/fichero/issues/3047), [#3048](https://github.com/dtubb/fichero/issues/3048), [#2988](https://github.com/dtubb/fichero/issues/2988), [#2989](https://github.com/dtubb/fichero/issues/2989), [#2990](https://github.com/dtubb/fichero/issues/2990), [#2991](https://github.com/dtubb/fichero/issues/2991), [#2992](https://github.com/dtubb/fichero/issues/2992), [#2993](https://github.com/dtubb/fichero/issues/2993), [#2994](https://github.com/dtubb/fichero/issues/2994), [#2996](https://github.com/dtubb/fichero/issues/2996), [#2997](https://github.com/dtubb/fichero/issues/2997), [#2998](https://github.com/dtubb/fichero/issues/2998), [#2999](https://github.com/dtubb/fichero/issues/2999), [#3000](https://github.com/dtubb/fichero/issues/3000), [#3001](https://github.com/dtubb/fichero/issues/3001))
- fix(tooling/docs): make milestone picking follow due-order within a tier, recover the ROADMAP/security spine, add the `notify_manager` helper, and ground another round of architecture/contributor docs in the current code ([#2913](https://github.com/dtubb/fichero/issues/2913), [#1797](https://github.com/dtubb/fichero/issues/1797))

### 2026-07-02

**Fixes**

- fix(action-layer): route document mutations through the audited registry while preserving change-stream behavior ([#2789](https://github.com/dtubb/fichero/issues/2789))

**Tests**

- test: add centralized LLM error-path coverage and F5 room-convergence edge coverage ([#1825](https://github.com/dtubb/fichero/issues/1825), [#2787](https://github.com/dtubb/fichero/issues/2787))

**Docs**

- docs: add the iOS/iPad interaction-model reference for the shipped compact/scene behavior ([#2810](https://github.com/dtubb/fichero/issues/2810))

### 2026-06-28

**Features**

- feat(node-model): ship a large node-model fold tranche — saved searches, research workspaces/plans/tasks/steps, bookmark nodes, room-node bridges, notes/milestones, entities-in-folders, chat-scope node references, and workspace folder prototypes ([#2591](https://github.com/dtubb/fichero/issues/2591))
- feat(reader/library): add text, image, and PDF region annotations, immersive full-screen reading, bookmark surface wiring, and inspector ownership/entity-default cleanup ([#2458](https://github.com/dtubb/fichero/issues/2458), [#2520](https://github.com/dtubb/fichero/issues/2520), [#2755](https://github.com/dtubb/fichero/issues/2755), [#2696](https://github.com/dtubb/fichero/issues/2696), [#2697](https://github.com/dtubb/fichero/issues/2697))
- feat(workflows): centralize workflow LLM routing through the shared chat/structured-output path ([#1825](https://github.com/dtubb/fichero/issues/1825))

**Fixes**

- fix(action-layer): audit folded node-model creates so audit rows and change-stream updates stay paired on the folded write paths ([#2789](https://github.com/dtubb/fichero/issues/2789))
- fix(chat/ui): switch sidebar chat bubbles to native markdown rendering and drop the custom icon/table/map transcript modes in favor of the shipped bubble UI ([#2639](https://github.com/dtubb/fichero/issues/2639), [#1891](https://github.com/dtubb/fichero/issues/1891))
- fix(inspector): close the trailing-edit autosave data-loss race with a coalescing save runner ([#2536](https://github.com/dtubb/fichero/issues/2536))

**Docs**

- docs: ground contributor docs, user-guide claims, release/QA docs, API reference coverage, node-model status pages, and the mutation-invariants guidance against the current code ([#108](https://github.com/dtubb/fichero/issues/108), [#2591](https://github.com/dtubb/fichero/issues/2591), [#2690](https://github.com/dtubb/fichero/issues/2690), [#2691](https://github.com/dtubb/fichero/issues/2691), [#1848](https://github.com/dtubb/fichero/issues/1848), [#1863](https://github.com/dtubb/fichero/issues/1863))

**Tests**

- test: broaden the node-model and audit contract net with fold-route coverage, bookmark integration coverage, prototype/room regressions, API-doc drift checks, and mutation-invariant locks ([#108](https://github.com/dtubb/fichero/issues/108), [#2787](https://github.com/dtubb/fichero/issues/2787))

### 2026-06-27

**Features**

- feat(shell): toolbar view-mode menu, popover detail binding, iOS DocumentStore env
- feat(swiftui): bounded three-pane split (#2481)
- feat(reader): collapse toolbar clusters with remembered state (#2467)

**Fixes**

- fix(release): ReaderToolbar splitAxisActions + explicit inits + release runbook
- fix(build): resolve compile errors from the mac-inspector merge
- fix(swiftui): multi-select delete list browsers (#2519)
- fix(reader): sync library selection focus (#2522)
- fix(ios): back compact reader navigationDestination with @State so the iPhone push fires (#2666)
- fix(inspector): slide list detail in from the right (#2455)
- fix(inspector): distinguish child-derived KG rows (#2521)
- fix(inspector): remove redundant artifacts tab (#2468)
- fix(inspector): keep library clicks in place (#2661)
- fix(ios): re-gate .spatial display mode to stop iPad launch stack overflow (#2665)

**Refactors**

- refactor(views): merge Spatial(2D) into Canvas — two view modes, one node store (#2667)

**Docs**

- docs(state): manager session-end 2026-06-27 — shell batch + Canvas/Space shipped, release lane owned, build-gate lesson
- docs(state): session-end 2026-06-27 — shell batch shipped, release lane handoff, build-gate lesson

**Build**

- build(release): build/notarize/distribute scripts (release lane)
- build(xcode): release versioning, scheme, engine imageset

**Chore**

- chore(engine): KG routes, engine entrypoint, NER, deps + tests (lane WIP)
- chore(views): remove dead LibraryMapComponents after Canvas/Spatial merge (#2667)

### 2026-06-26

**Features**

- feat: organize same-document clusters into subfolders via action registry (#2284)
- feat: add Describe (visual) workflow preset wiring the describe tool per-page (#2283)
- feat: same-document clustering tool + preset (first slice, folder-organize deferred) (#2284)
- feat: extract + persist per-page Gemini bounding boxes for HTR (#2530)
- feat: add detachable document detail popover (#2002)
- feat: make security/multi-user backend visible in Settings (#2082)
- feat(llm): add ordered multi-tier fallback chain (#1827)
- feat(llm): add Apple LangChain chat wrapper (#1826)
- feat: Per-library sharing + role assignment UI (#2086)
- feat(node-model): position as document attributes, retire canvas_items (#2589)
- feat(node-model): add general library links endpoint (#2636)
- feat(settings): Multi-user toggle (#2084) fix returns
- feat(workspace): add workspace management surface (#2619)

**Fixes**

- fix(scripts): spawn-worker.sh worktree path under fichero-worktrees/, not bare sibling
- fix: percent-encode X-Fichero-Library-Path so non-ASCII library paths round-trip (#2646)
- fix: update _propagate_to_page_children mock assertion for #2530 page_geometries kwarg
- fix: workflow P2 hardening bundle — EdgeDef validator + save-None + registry cap (#2534)
- fix: cap workflow State outputs growth for 100k-scale (#2541)
- fix: honor single-user bypass in app-wide config gate (#2644)
- fix: decouple openapi export from the running engine's app.duckdb lock (#2643)
- fix: honor single-user bypass in assert_can_read/assert_can_write (#2642)
- fix: return mermaid text instead of Pyppeteer PNG for workflow visualization (#2525)
- fix(kg): keep cloud extraction quality aligned across providers (#1807)
- fix(kg): merge near-duplicate entities at upsert (#1804)
- fix(tests): authorize canvas action fixtures (#2641)

**Docs**

- docs: drop last stale 0.0.2 working-branch ref in .claude/CLAUDE.md
- docs: sweep 0.0.2 working-branch refs to main after PR #2652 merge
- docs: stage node-model subsystem fold for #2591 (#2591)

**Tests**

- test: attach auth bearer token in _client() so library route tests pass in isolation (#2647)
- test: restore single-user env for action tests + fix default-on authz siblings (#2642 sweep)
- test: regression test for openapi export app.duckdb decoupling (#2645)
- test(contracts): quarantine backend-only endpoints (#2638)

**Build**

- build: drop unused bundled deps (#2584)

### 2026-06-25

**Features**

- feat(image editing): restore straighten tool (#2587)
- feat: add adaptive apple shell host #2328
- feat: expose workflow run graph and artifacts (#2628)

**Fixes**

- fix: hydrate persisted workflow run timeline (#2635)
- fix: batch3 Swift build — ActivityMonitor switch + openWindow access
- fix: push compact inspector navigation #2616
- fix: keep changes stream alive under TLS (#2621)
- fix: sidebar selectedItemId computed setter must be nonmutating (#2548)
- fix: collapse split panes on narrow shells (#2372)
- fix: condense reader split controls on narrow widths (#2387)
- fix: expose shared view commands on iPad (#2390)
- fix: unblock 0.0.2 Swift build (missing import, if-let shadow, os-log interpolation)
- fix: tighten compact shell defaults (#2329 #2331 #2332)
- fix: key workflow page progress by document identity (#2634)
- fix: drive activity refresh from stream (#2633)
- fix: route workflow stop through cancel endpoint (#2631)
- fix: bootstrap loopback TLS pins in release builds
- fix: expose built-in workflow palette tools
- fix: share pinned engine stream requests
- fix: handle non-dict workflow node outputs
- fix: preserve selected PDF page workflow semantics
- fix: preserve workflow routing and chain selection context
- fix: recover debug loopback TLS pins (#2621)
- fix: refresh release validation paths (#2402)
- fix(workflow): #2613 empty-query reference search skips gracefully; #2612 402/quota errors surface in Activity payload

**Refactors**

- refactor: consolidate knowledge package shims (#2596)
- refactor: move workflow runner into execution (#2594)

**Docs**

- docs: remove personal Sparkle key location (#2553)
- docs: add repo hygiene guidance (#2553 #2554 #2556 #2559)
- docs(state): checkpoint manager takeover after Claude handoff

**Tests**

- test: pin knowledge package import shims (#2596)
- test: satisfy authz chokepoint in changes-stream endpoint tests
- test: fix touched swiftlint failures (#2634)
- test: clean diff-owned swiftlint warnings (#2634)
- test: stub KG finalize vector path in no-token matrix (#2627)
- test: extend no-token workflow matrix (#2627)
- test: add no-token workflow matrix (#2627)
- test: add no-token workflow execution paths (#2627)
- test: guard SSE stream paths against OpenAPI drift
- test: restore FicheroTests Swift 6 compile gate (#2623)
- test: reduce Swift test target compile failures (#2623)
- test: update runner source guard for execution move (#2594)

**Chore**

- chore: sync generated OpenAPI surface

### 2026-06-24

**Fixes**

- fix(library_links): gate read endpoints on library-path header (#2590)
- fix(#2605): pin LibraryChangeStream SSE session\n\nStore the URLSession as a class-level property built via\nRemoteCertificatePinning.configuredSession() so the SPKI-pin\nchallenge delegate is retained and invoked for the\nURLSession.bytes SSE path. Per-call local sessions work for\nsession.data(for:) but not for the streaming task, which fell\nback to default trust (-9807) on the pinned loopback HTTPS cert.
- fix(transport): host Mac app always connects to own engine via 127.0.0.1:8765 (#2604)
- fix: match WKNavigationDelegate/URLSessionDelegate challenge signatures so pinned TLS handlers are invoked (#2601)
- fix(transport): restore persisted Share URL and bind all interfaces in shared mode (#2603)
- fix(transport): default engine bind to loopback and atomically refresh SPKI pins (#2603)

**Docs**

- docs(agent-workflow): export manager-with-workers skills as contributor docs (#2599)
- docs(state): overnight codex loop — #2589/2590/2591/2595/2597 landed; #2593/2594/2596/104 held for Daniel

### 2026-06-23

**Features**

- feat(#2589): add position_x/y/z to Document model, routes, and tests
- feat(shell): compact library tap pushes reader, Overcast-style (#2551)

**Fixes**

- fix(#2597): changes-stream TLS — DynamicPinnedSessionDelegate validates SPKI pin for URLSession (codex/kimi)
- fix(release-notes): drop pre-pivot November; pivot=Dec 5 2025; harder Mac 'What's New' voice (#2572)
- fix(release-notes-gen): non-reasoning model default + strip ANSI/control chars (#2572)
- fix(#2538): route KG/reader WKWebView through the pinned HTTPS transport

**Refactors**

- refactor(#2578): rename MindPalace* types → Spatial*, delete dead MindPalaceRoom (#104)

**Docs**

- docs(session-end): changelog this session's fixes; STATE next-session = gate changes-stream fix then codex node-model lanes
- docs(#2588): endpoints-vs-UX node-model consolidation audit
- docs: November release notes (generated, #2572)
- docs: shorten release-notes Highlights + undate (April-era content); fix gen trim
- docs: RELEASE_NOTES.md — current release entry + by-day history scaffold
- docs(design): iOS/iPad engine embedding + multi-library feasibility & architecture
- docs(#104): staged SwiftUI app reorg plan — canonical FE vocabulary, MindPalace→Spatial
- docs(#2566): staged engine package + api/routes reorg plan
- docs: refresh top-level, app, and engine READMEs (#2556)
- docs(#2563): explore fichero-web — browser front-end feasibility
- docs: fix stale api-client README — https+pinned client, correct sync path

**Build**

- build: ollama-driven RELEASE_NOTES by-day generator (#2572)
- build: add fichero-engine/LICENSE so Briefcase embed config resolves (#2580)

**Chore**

- chore: declutter repo root — refile agent scratch into agent-work/, untrack session sentinel
- chore: de-personalize for release — remove archival corpus, de-hardcode paths, swap email

### 2026-06-22

**Features**

- feat(#2532,#2541): enable graph-level parallel fan-out on the live run path
- feat(#2546): Activity = live workflow monitor as a poppable hierarchical table (B2)
- feat(#2546): shared live WorkflowExecutionStore feeds the Activity monitor
- feat(workflows): untested trust flag on tools + presets (display-only)

**Fixes**

- fix(#2546): Live Log tab read the empty observer, never the store
- fix(#2549): hide zoom/fit reader controls on compact width
- fix(#2546): fan-out workflow SSE events so live Activity gets them
- fix(#2546): live Overall Progress bar stayed 0% — seed totalFiles from file events
- fix(shell): full-height iPhone inspector sheet + reconcile restored sidebar selection (#2547 #2548)
- fix(#2544): cap eager folder/collection source load to bound RAM
- fix(#2543): per-provider circuit breaker + backoff for vision rate-limits
- fix(#2537): type the Workflow nodes/edges persistence boundary
- fix(#2523): wire per-page documents into every transcription preset
- fix(#2540): offload save_artifact's sync DB+embed work off the event loop
- fix(#1943/#2538): converge Activity SSE stream onto the shared FicheroClient transport
- fix(#2523): HTR two-pass saves per-page, not the parent PDF
- fix(#2513): validate save_artifact document= pass-through up front (no silent swallow)

**Performance**

- perf(#2542): bounded LanceDB compaction + batched DuckDB/embedding writes
- perf(#2539): process vision/transcribe files bounded-concurrently
- perf(M1/#2545): cache resolved API keys + invalidate on keychain write
- perf(#2532): trim full outputs blob from parallel fan-out Send payloads

**Refactors**

- refactor(#2533): collapse per-family save_artifact wrappers onto one shared helper
- refactor(#2514): remove redundant DBWriter — single lock already serializes writes

**Docs**

- docs(state): all 4 shell P0/P1/P2 done; EPIC #2551 remainder needs Daniel
- docs(state): overnight loop active — 100k chain on, Activity stream fixed, shell UX in progress
- docs(#2538): dev engine must serve HTTPS — replace bare-HTTP uvicorn command
- docs(session): 2026-06-22 handoff — #2513/#2514/#2523 shipped, workflow review + EPIC, stale-worktree lesson

**Tests**

- test(#2532): #1665 stays dead on the REAL Catalogue preset topology
- test(#2532): checkpointer-backed regression for parallel run path

**Style**

- style(#2550): glass mini-toolbars — sidebar mode bar + library bars

### 2026-06-21

**Features**

- feat(#2508): Phase 3a — locked Database.execute helpers for direct-SQL stores
- feat(reader): collapse overflow tools into a trailing '…' menu when narrow (#2488)
- feat(reader): unify image + PDF reader toolbars into one bottom ReaderToolbar (#2423 #2421)
- feat(ios): add mini-toolbar overlay to iOS image viewer (#2471)
- feat(library): replace page/artifact count rows with individual navigable rows (#2405)
- feat(inspector): add status badge + sort + stable ID to WorkflowProvenancePanel (#2434)
- feat(inspector): show relative timestamp per artifact in list (#2429)
- feat(inspector): unify on SwiftUI AttributedString TextEditor, delete AppKit editor (#2453)
- feat(image): preload ±3 folder neighbors + bounded display cache (#2469)

**Fixes**

- fix(#2430): per-page PDF granularity — split-fail-loud + whole-doc guard
- fix(#2518): surface change-stream connect failures (no silent retry)
- fix(#2518): canonicalize change-hub library_path key on both seams
- fix(#2518): emit change events at workflow completion + KG finalize
- fix(#2508): Phase 3b — seal direct-SQL stores onto the locked seam
- fix(#2508): Phase 2 — collapse to one DuckDB connection + lock per package
- fix(workflows): no silent fallback in artifact cache lookup + save (#2510 #2511)
- fix(workflows): finalize #2430 — fail loud on genuine doc miss, no orphan save
- fix(workflows): forward document= through vision save_artifact wrapper (#2430)
- fix(workflows): pass page-child document through state to eliminate db.get re-fetch (#2430)
- fix(workflows): thread-local DB in task workers + no silent re-embed (#2509 #2512)
- fix(vision,rtf): per-page doc-id fallback never fires on parent; drop bare-hex (#2430 #2505)
- fix(inspector): preserve bold/formatting when saving rich-text editor (#2494 #2416)
- fix(workflows): prevent save_artifact file_path fallback from rerouting page-child artifacts to parent PDF (#2430)
- fix(reader): build errors — iOS ZoomableImagePreview signature + bounded toolbar bodies (#2421 #2423 #2488)
- fix(chat): route model construction through llm.get_langchain_model (#2490)
- fix(loader): decode RTF \'XX hex escapes before stripping control chars (#2486)
- fix(ios): import FicheroAPIClient in ImageViewerComponents so the iOS #Preview resolves FicheroClient
- fix(inspector): add htmlForWebView codec helper; never raw RTF to DOM (#2454)
- fix(workflows): route non-parallel edges to _process node for parallel targets (#2483)
- fix(sidebar): PDF is a leaf — stop yielding page children in tree (#2404)
- fix(image-editor): invalidate display cache after edit so viewer shows edited image (#2459)
- fix(sidebar): populate sidebar on iPhone launch independent of column visibility (#2472)
- fix(sidebar): apply 52/44 touch tier + Liquid Glass to sidebar bottom bar (#2475)
- fix(workflow): increase node/edge spacing in canvas and preset graphs (#2437)
- fix(workflow): route run output to Activity, remove editor bottom panel (#2439)
- fix(model): make Document @unchecked Sendable — unblocks store-owned page-content save across actors (#2453/#2466)
- fix(workflow): silent save (remove 'Saved' flash #2438) + larger node help text #2445
- fix(entities): filter/guard garbage entity names like '12:10' (#2482)
- fix(reading): pin keeps page, focus ring fades fast, image full-res zoom (#2428 #2424 #2427)

**Refactors**

- refactor(#2518): centralize completion emit + carry KG ids
- refactor(toolbar): route view/mode/reader-tab switching to main toolbar + View menu (#2431 #2432 #2436)

**Docs**

- docs(state): #2518 + #2430 shipped overnight; backend-hardening-finish (#2513/#2514) running
- docs(state): overnight 2026-06-22 — #2508 shipped; #2513/#2514 + #2518 emit-gap lanes running; #2430 transcribe-per-page queued
- docs(state): branch-cruft triage — safe-prune set (closed-issue throwaway) vs review set (real divergence); deleted confirmed tmp-1318
- docs(state): deleted superseded worktree-agent branch (confirmed merged via 22 #2376 commits); noted broader branch cruft
- docs(state): backend health check — HEAD healthy (1218 fails are environmental); filed #2483 (real broken default workflow)
- docs(state): ios-reader-polish diff summary + integrate-vs-drop recommendation for Daniel
- docs(state): triage round — #2474 is a real sibling (libraryBottomActionBar), not a #2475 dup; scoped + deferred
- docs(state): maintenance — #2461 swiftlint scoping posted; flag 2 stale local branches for Daniel's review
- docs(state): ~24 closed — borderline-design trio done (#2405/#2404/#2471); remaining is held/device/perimeter
- docs(state): ~21 issues closed — clean queue drained; categorized remaining open for Daniel's direction
- docs(state): overnight wrap — ~18 issues closed (incl #2453 keystone); morning handoff + held items for Daniel
- docs(state): overnight progress — ~15 issues closed incl #2453 editor unification; held design-coupled toolbar cluster for Daniel

**Tests**

- test(#2518): guardrail + behavioral tests for terminal-node emits
- test(#2508): add cross-thread read-after-write + no-deadlock stress tests
- test(#2508): Phase 4 — permanent single-connection guardrail
- test(#2508): Phase 0 — single-connection write-model proof harness
- test: adversarial per-page artifact placement tests (#2430)

### 2026-06-20

**Features**

- feat: integrate Activity live-refresh (#2448) + window-title breadcrumb (#2425)
- feat(toolbars): persisted show/hide toggle for reader mini-toolbars (#2460)
- feat(toolbars): Tahoe Liquid Glass for mini-toolbars + workflows button (#2041 #2415)
- feat(views): folder image prev/next navigation (#2420)
- feat(pairing): iOS onOpenURL — tap fichero://pair link to connect (#2399)
- feat(pairing): Mac host UI — ShareLink + security note + host field (#2399)
- feat(capture): add Capture menu to connected-library toolbar (#2401)
- feat(net): convert AppleScriptSupport.swift to generated OpenAPI client (#2414)
- feat(net): convert AppState.swift to generated OpenAPI client (#2414)
- feat(net): convert EngineConfig.swift to generated OpenAPI client (#2414)
- feat(net): convert APIClient.swift to generated OpenAPI client (#2414)
- feat(net): convert ActivityServiceGenerated.swift to generated OpenAPI client (#2413 #2392)
- feat(net): convert StorageServiceGenerated.swift to generated OpenAPI client (#2411)
- feat(net): convert ImportServiceGenerated to generated OpenAPI client (#2412 #2406)
- feat(ios): launch compact shell on the sidebar/library list (#2329 #2334)
- feat(ios): root the collapsed shell on the reader column (#2329 #2334)
- feat(ios): switch between known libraries from the registry (#2394)
- feat(shell): platform-aware mini-toolbar sizing + larger iOS/tvOS touch targets (#2098 #883)
- feat(settings): wire Users tab to real API via UsersStore (#2083)
- feat(settings): add Engine and Share settings surfaces (#2371 #2379)
- feat(pairing-ui): add QR-first device entry screen (#2370)
- feat(settings): add per-user capture settings (#2380)
- feat(settings): add Users account and access surface (#2083)

**Fixes**

- fix(embeddings): log legacy-vector-table warning once per process (#2480)
- fix(inspector): page-editor reliability — self-echo filter, flush-on-nav, width clamp (#2476 #2477 #2478 #2479)
- fix(search): surface page-level doc IDs for PDF hits, enrich with parent metadata (#2452)
- fix(chat): send nil conversationId on first message so backend auto-creates it (#2451)
- fix(spatial): loosen Spatial2DCanvas members to internal for cross-file extensions
- fix(scripts): force UTF-8 in add/remove-swift-file.rb to avoid US-ASCII pbxproj read error
- fix(api): normalize doc: prefix in /outline and /inspector, unify soft-delete handling (#2462)
- fix(ios): @discardableResult on resumePendingUploads — covers both call sites (#2401)
- fix(ios): discard unused result of resumePendingUploads (#2401 follow-up)
- fix(ios): prefer saved/paired remote host first, skip localhost probe (#2465)
- fix(inspector): store-owned page-content save survives view cancellation (#2466)
- fix(shell): MiniToolbar split + ContentView type-check budget + visionOS subtitle compat
- fix(workflow): offload draw_mermaid_png to threadpool — fixes 500 on diagram render (#2473)
- fix(ios): iOS picker shows all known libraries, surfaces fetch errors (#2457)
- fix(inspector): collapse duplicate references tab onto citations (#2456)
- fix(search): declare pylance dependency for LanceDB full-text search
- fix(pairing): @MainActor on defaultDeviceName() (#2399)
- fix(ios): pinch-to-zoom on image/PDF canvas and WebKit (#2417)
- fix(capture): MobileCaptureBackendUploadClient targets active library id (#2401)
- fix(shell): mark pane-width constants nonisolated for WidescreenPanePlan
- fix(net): drop nonexistent .unprocessableContent cases in PairingService (#2414)
- fix(ios): remove macOS-only drawsBackground KVC that crashes iPad WKWebView
- fix(glass): keep .glassEffect() bar, revert split buttons to plain+accent
- fix(transcription): per-page fan-out must not call _propagate_to_page_children (#2303 #2395 #2396)
- fix(toolbar): scale mini-toolbar split glyphs with Dynamic Type, larger on touch (#883)
- fix(settings): clear stale sharing setup warning (#2371)
- fix(pairing): keep stale mobile hosts on connect screen (#2376)
- fix(pairing): use advertised host library path (#2376)
- fix(security): require pinned HTTPS for local engine (#2376 #2370)
- fix(ios): use engine icon on QR pairing entry (#2370 #2376)
- fix(settings): compile capture picker lists (#2380)
- fix(ios): compile capture button modifiers (#2370)
- fix(pairing): make device names and lint gate platform-safe (#2370 #2351)
- fix(pairing-ui): align mobile entry and settings defaults (#2370 #2371 #2380)
- fix(pairing-ui): correct visionOS fallback copy in QRCodeScannerSheet (#2370)
- fix(share): auto-detect .local hostname so QR appears on toggle (#2371 #2379)
- fix(pairing-ui): address manager review blockers for device entry (#2370)
- fix: clean up pairing guardrails (#2378)

**Refactors**

- refactor(spatial): split SpatialView into Gestures + Items + NodeThumbnail files
- refactor(spatial): split Spatial2DCanvas body into extensions for SwiftLint
- refactor(settings): replace ponytail comment with production note (#2380)

**Docs**

- docs(state): overnight autonomous run plan + priority bands + editor-unify decision
- docs(state): integration cycle done + 3 workers running (connection/shell)
- docs(design): refine mockups per review
- docs(design): interactive per-device shell mockups (#2030 #2328)
- docs(state): overnight autonomous operating model + priority order + worker policy
- docs(state): kimi worker output summary + final wrap-up (manager stop)
- docs(state): session-end hand-off — kimi workers continue, Daniel integrates later
- docs(state): demo path shipped (iOS libs+nav, per-page, glass bar); reader-polish lane up; Tailscale TLS flagged for Daniel
- docs(state): iOS demo shell landed+built+pushed; per-page restarted + glass lane up
- docs(ios): FINDINGS for the multiple-libraries + compact-nav lane
- docs(state): manager handoff — recovered Codex session, worktrees 23→1, 0.0.2 synced
- docs: add settings and device UX wireframes

**Tests**

- test(views): unit tests for image folder nav (#2420)
- test(pairing): URL-object round-trip + rejection tests for invite links (#2399)
- test(capture): unit tests for active-library wiring in upload client (#2401)

**Build**

- build: raise Mac deployment target to macOS 26 (min-26 all platforms, Liquid Glass)

**Style**

- style(glass): adopt .glassEffect() + GlassEffectContainer on MiniToolbar + PaneFilterBar (#2041)

**Chore**

- chore: drop stray worker FINDINGS.md pulled in by cherry-pick
- chore: add tvOS destination support (#2370)
- chore: replace ponytail comment prefix with plain comment in ShareSettingsView (#2371 #2379)

### 2026-06-19

**Features**

- feat: add secure same-network remote access path (#2377)
- feat: add mobile capture queue slice (#2353)
- feat: add touch chat scope actions (#2342)

**Fixes**

- fix(shell): collapse narrow widescreen panes (#2372)
- fix(pairing-ui): make Mac host QR pairing direct (#2371)
- fix(test-plan): keep Mac tests off iOS destinations (#2374)
- fix(pairing-ui): simplify connect screen (#2370)
- fix(shell): gate repeated visionOS subtitles (#2369)
- fix: gate visionOS mobile capture camera path (#2353)
- fix(shell): gate visionOS inspector APIs (#2369)
- fix: gate iOS QR scanner for visionOS (#2370)
- fix(shell): include visionOS in webview wrapper (#2369)
- fix(shell): gate inspector width on visionOS (#2369)
- fix: use color accent style in iOS connect hero (#2370)
- fix: gate remote pin preload to mac host settings (#2351)
- fix(shell): expose measured width to actions (#2369)
- fix(shell): relax narrow inspector band (#2369)
- fix(shell): measure narrow width before clamp (#2369)
- fix(shell): collapse panes when narrow (#2369)
- fix: tighten health auth/header exclusions (#2351)
- fix: block remote kg web auth and normalize host pins (#2351)
- fix: scope remote trust material by host (#2351)
- fix: pin remote API transport to pairing SPKI (#2351)
- fix: tighten iOS QR connect flow (#2370)
- fix: simplify iOS connect screen (#2370)
- fix: include mobile capture files in app target (#2353)
- fix: isolate mobile capture tests on main actor (#2353)
- fix: make mobile capture uploader main-actor safe (#2353)
- fix: isolate mobile capture upload on main actor (#2353)
- fix: preserve interrupted capture retry state (#2353)
- fix: avoid duplicate capture retries (#2353)
- fix: add capture privacy strings (#2353)
- fix: add connected mobile capture entry and queue recovery (#2353)
- fix: use mac-safe toolbar placements (#2369)
- fix: improve camera folder intake provenance (#2354)
- fix: guard capture smoke matrix existence (#2355)
- fix: complete retry readiness for configured backends (#2326)
- fix: expose compact sidebar size class (#2342)
- fix: add compact sidebar chat and move actions (#2342)
- fix: use static compact flow helper in navigation (#2334)
- fix: wrap compact research workspace branches (#2334)
- fix: adapt inner mode sidebars on compact (#2334)
- fix: use configured remote backend on Mac startup (#2326)
- fix: close sidebar drag handler guard path (#2344)
- fix: make sidebar drag moves transactional (#2344)
- fix: gate compact navigation flow on non-macOS (#2332)
- fix: collapse widescreen reading flow on compact (#2332)
- fix: adapt inspector presentation across Apple platforms (#2331)
- fix: tighten unauthenticated path matching (#2161)
- fix: clean up failed sidebar drop temp files (#2343)
- fix: trust native split compact defaults (#2329)
- fix: split detail toolbar for type-checker (#2329)
- fix: keep compact split visibility runtime-only (#2329)
- fix: keep compact split state runtime-only (#2329)
- fix: use native compact collapse for split view (#2329)
- fix: remove duplicate test group (#2346)
- fix: remove manual test project entries (#2346)
- fix: classify mixed sidebar drop providers deterministically (#2346)
- fix: resolve Sparkle test repo root robustly (#2319)
- fix: lock Sparkle linkage to macOS (#2319)
- fix: keep SplittablePane off compact layouts (#2333)
- fix: keep transcribe artifacts on page children (#2303)
- fix: gate model comparison sidebar row on chat flag (#2341)
- fix: keep compact image preview on native path (#2334)
- fix: batch touch chat scope updates (#2342)
- fix: separate Mac shell minimums from compact layout (#2330)
- fix: lock Mac pairing settings surface (#2327)
- fix: compile compact split persistence
- fix: normalize compact split visibility restore (#2334)
- fix: adapt iPad shell and image preview (#2334)
- fix: reject loopback remote access hosts (#2351)
- fix: serialize launch backend resync
- fix: resync launch backend state and routing assertions
- fix: unify chat doc scope routing and drops (#2336 #2337 #2338 #2340 #2345)
- fix: start dev backend without reload by default

**Refactors**

- refactor: remove stale sidebar chat surface (#2339)

**Docs**

- docs(pairing-ux): add Claude UX review for QR capture flow (#2376)
- docs(pairing-ux): seed QR and capture onboarding contract (#2376)
- docs: triage visionOS RealityWidgets watchdog (#2375)
- docs: define capture session upload contract (#2352)
- docs: add capture smoke matrix (#2355)

**Tests**

- test: align retry readiness source assertion (#2326)
- test: split sidebar drag drop tests for lint (#2346)
- test: extract adaptive shell policy coverage (#2330)
- test: cover adaptive shell defaults and preview (#2335)

**Chore**

- chore: clean shell lint after iPad integration

### 2026-06-18

**Features**

- feat: share library workspace across Apple platforms
- feat(ios): gate Mac-only SwiftUI APIs and add cross-platform colour shims (#2098)
- feat(ios): replace HSplitView/VSplitView with Platform shims (#2098)

**Fixes**

- fix: rebind app services after engine host changes (#2349)
- fix: fail closed on malformed engine host (#2349)
- fix: remove localhost KG fetch from document view (#2349)
- fix: align pairing backend with advertised URL (#2347)
- fix: rebind Swift clients to configured engine host (#2349)
- fix: restore integrations service configured client initializer
- fix: use platform quaternary label on mac
- fix: gate PDF loupe overlay by platform (#2098)
- fix: unblock iOS simulator build (#2098)
- fix(ios): BackendConnectionView uses Image(platformImage:) (#2098)

**Refactors**

- refactor(ios): gate ScrollWheelZoom Mac-only (#2098)
- refactor(ios): gate QuickLookPreviewViews Mac-only (#2098)
- refactor(ios): gate AppleScriptSupport Mac-only (#2098)
- refactor(ios): gate ImageViewerComponents Mac-only (#2098)
- refactor(ios): gate ClaimSummaryCardView Mac-only (#2098)
- refactor(ios): gate AppleScriptCommands Mac-only (#2098)
- refactor(ios): gate QuickLookComponents Mac-only (#2098)
- refactor(ios): gate panels/alerts Mac-only, bucket C group 2 (#2098)
- refactor(ios): gate SparkleUpdater behind #if os(macOS) (#2319 #2098)
- refactor(ios): gate app-shell Mac-only code behind #if os(macOS), group 1 (#2098)

**Docs**

- docs(session-end): iOS gate pause + MCP-build handover (2026-06-18)
- docs: update STATE.md — #2311 already merged, iOS gate still pending (#2098)
- docs: add codex-in-Xcode prompt for #2309 toolbar cleanup
- docs: update STATE.md morning handoff for iOS shell drive (#2098)

**Tests**

- test(remote): add pairing verification gates (#2350)
- test: cover bootstrap token session contamination (#2348)

**Build**

- build(ios): register FicheroApp_iOS.swift in Xcode target + add SwiftUI iOS entry (#2098)
- build(ios): restrict Sparkle framework link to macOS (#2319)
- build(ios): add iPhone/iPad destinations to Fichero target, iOS 26 min deployment (#2099)

**Chore**

- chore: checkpoint remote pairing and iOS bringup work
- chore: track Xcode shared workspace settings

### 2026-06-17

**Features**

- feat(panes): independent 2×2 widths, view switcher in reading pane, fix close priority
- feat(panes): pin to far right, X close, WebKit zoom, constraint-loop fix (#2316 #2317)
- feat(workflows): export_documents tool + Export-to-Desktop preset (MD/DOCX/XLSX) (#2315)
- feat(toolbar): breadcrumb title, left-aligned nav buttons, Space ⌘5, Canvas ⌘4 (#2309)
- feat(toolbar): persist per-mode sidebar widths; widen max to 600 (#2309)
- feat(toolbar): add principal centred context label, Xcode-style (#2309)
- feat(toolbar): move list/chat to sidebar toolbar, remove Plus (#2309)
- feat(toolbar): list navigator button + single sidebar hide (#2309)
- feat(library): bottom action bar on selection (#2313)
- feat: remove sidebar toolbar title; add −/export/workflow to bottom bar (#2309)
- feat: chat column drops back button; per-mode column width (#2309)
- feat: list|chat navigator selector + Mail-style sidebar toggle (#2309)
- feat(view-menu): group Spatial/3D view modes with Icons/List/Table (#2308)
- feat(chat): Xcode-style sidebar⟷chat swap in the left column (#2034)

**Fixes**

- fix(panes): Preview rename, conditionalSearchable split-crash guard, inspector widths (#2309)
- fix(panes): X close collapses split, falls back to hiding pane
- fix(ui): replace verbose empty states with consistent 'No selection' (#2309)
- fix(toolbar): centre title across full window, not just content section (#2309)
- fix(toolbar): left-align navigator buttons; label Back/Forward/Navigator/RA (#2309)
- fix(toolbar): add names to Navigator, Research Assistant, Inspector items (#2309)
- fix(toolbar): hide list/chat navigator when sidebar is collapsed (#2309)
- fix(inspector): text editor respects available height in content tab (#2309)
- fix(library): move entity filter from toolbar to bottom action bar (#2309)
- fix(toolbar): instant sidebar toggle, consistent chat button style (#2309)
- fix(layout): include inspector width in window minimum to prevent sidebar overlay (#2309)
- fix(toolbar): restore system sidebar toggle, opacity-only chat icon (#2309)
- fix(toolbar): consolidate sidebar controls onto sidebar column toolbar (#2309)
- fix(toolbar): list/chat left-aligned in sidebar, accent-color active state (#2309)
- fix(toolbar): list/chat to sidebar-left, drop .principal, fix Library hidden (#2309)
- fix(toolbar): remove workflow button, move inspector to content section (#2309)
- fix(toolbar): title to content section, list/chat to sidebar right (#2309)
- fix(library): view mode follows user choice, no spatial default (#2311)
- fix(spatial): persist 2D/3D node positions on blur; load saved 3D layout instead of resetting to circle (#2312)
- fix: sidebar dividers non-interactive — .allowsHitTesting(false) + .selectionDisabled() (#2310)

**Performance**

- perf(workflows): debounce changeToken-driven loadWorkflows reload (#2307)
- perf(files): drop AnyView erasure from recursive folderSection for structural diffing (#2307)
- perf(library): minimize idle work in processing poll timer (#2307)

**Refactors**

- refactor(ios): codemod shimmable AppKit types→Platform* + canImport guards, bucket A/B (#2101)

**Docs**

- docs(ios): per-file AppKit audit for iPhone/iPad/Mac shared codebase (#2101)
- docs(state): session-end — #2313 shipped, worktrees cleaned, HEAD b18b26ab
- docs(state): session-end — Mac shell chrome+perf+spatial; ollama/codex-only worker policy (gpt-5.x ladder)

**Style**

- style(toolbar): grey bubble active state, bubbles.and.sparkles chat icon (#2309)

**Chore**

- chore(guardrails): allowlist FileMenuCommands.swift AppKit import (NSSavePanel/NSAlert) (#2101)

### 2026-06-16

**Features**

- feat(export): File ▸ Export ▸ BibTeX (.bib) surfaces existing endpoint (#2088)
- feat(inspector): document notes live in the inspector (Notes tab); retire the standalone notes browser sheet (#1500)
- feat(library): preview layout — side / bottom / hidden, switched from the View menu (#2032/§6d)
- feat(library): Xcode-style bottom filter bar on the library list (#2032/frame)
- feat(shell): document representations → View-menu "Add View" items, retire floating content icon bar (#2032/§G)
- feat(shell): Mail-style zoned toolbar — actions grouped, presentation→View menu (#2032)
- feat(library): expandable outline table + GET /documents/{id}/rollup (#2258)
- feat(shell): native .inspector() column replaces window-level inspector HStack — toolbar no longer overruns inspector (#1199, #2033)
- feat(inspector): platform-adaptive presenter (.docked/.floating/.sheet) + stacked panes (#2254)
- feat(shell): chat surface above the sidebar (chat / results / agent modes) (#2274)
- feat(shell): Duplicate Window clones library+selection+lens via WindowSeed (#2262)
- feat(panes): splittable library + image + WebKit (h/v) extending #1932 (#2276)
- feat(shell): persist window/tab state (library+selection+lens) across relaunch (#2273)
- feat(library): native alternating row stripes (#2259)
- feat(sidebar): expandable folder→doc→page hierarchy drives shared inspector (#2260)
- feat(mac-shell): backups UI — list/create/restore snapshots in Settings (#2087)
- feat(apple): expose Document/Entity/Claim as AppEntity + EntityQuery (#1837)
- feat(mac-shell): global audit/history viewer + undo (#2085)
- feat(spatial): grid-arrange button for 3D scene by page order (#1726)
- feat(spatial): native resize grab-handle for 2D canvas items (#1748)
- feat(spatial): render image/PDF node thumbnails in 2D canvas (#1744)
- feat(mac-shell): surface storage stats in Backend settings (#1442)
- feat: render heterogeneous CanvasItem kinds in 3D RealityKit scene (#2294)
- feat: 2D heterogeneous CanvasItem rendering + @Observable CanvasItemStore (#2294)

**Fixes**

- fix(library): restore 2D-spatial + 3D-RealityKit entry via the View menu (rail-removal regression)
- fix(inspector): Info tab renders full document metadata, not just the header (#2107)
- fix(shell): Research mode keeps the persistent sidebar (no longer hides it)
- fix(shell): kill idle-CPU loop — drop toolbar Delete's @FocusedValue read in ContentView (#2032)
- fix(shell): drop macOS-26-only ToolbarSpacer — zone via placements (deployment target is macOS 15) (#2032)
- fix(shell): content min no longer collapses sidebar + search renders content-side not over inspector (frame ① bug-fixes)
- fix(library): type tableColumnCustomization for LibraryOutlineNode rows (#2258)
- fix(shell): split LibraryWindow body into bounded sub-expressions to satisfy the Swift type-checker (#2262)
- fix(shell): library renders beside sidebar not below (#2263)
- fix(#1748): flatten double-optional in persistedItemSize (type-check choke)
- fix(#1442): reach storageService via libraryManager, not a crashing @EnvironmentObject
- fix(#2294): import FicheroAPIClient in SpatialScene3D + remove orphan split file
- fix(#2294): merge Spatial2DCanvasItems back into SpatialView (cross-file private symbols unresolvable)

**Performance**

- perf(activity): hoist node-state sort out of streaming view bodies (#2307)
- perf(library): memoize filteredDocuments/Entities + thumbnail prefetch key (#2307)
- perf(inspector,ontology): memoize entity grouping + ontology filters (#2307)
- perf(window): wrap LibraryWindow action focused values in Equatable FocusedLibraryAction (UI churn)
- perf(library): make librarySelectAll/Delete/SortField focused values Equatable (UI churn)
- perf(shell): make documentRepresentation focused value Equatable to stop per-frame republish churn (#2032)
- perf(spatial): viewport culling + resolution-by-zoom LOD for 2D canvas (#2298)

**Refactors**

- refactor(mac-shell): consolidate onboarding onto FirstRunWindow, remove old wizard (#1947)

**Style**

- style(library): remove redundant view-mode icon rail from the content toolbar (modes live in View menu) (#2032)
- style(inspector): inspector facet tabs as a clean Xcode-style segmented control (#1228)

### 2026-06-15

**Features**

- feat: CanvasItem model + CRUD + canvas.item.* actions for standalone canvas placeables (#2294)
- feat: smooth 3D camera navigation + stable grid (#2296)
- feat: 2D canvas pan/zoom/marquee via native SwiftUI gestures (#2295)
- feat: canvas arrange strategies (grid/row/column/circle/stack) → persisted transforms (#2297)
- feat: persist 3D RealityKit canvas positions via shared observable store (#2293)
- feat: persist 2D canvas item positions across view switches (#2293)
- feat: @Observable CanvasLayoutStore — load/save folder layout via OpenAPI client (#2293)
- feat: persist canvas layout — folder-scoped load/save endpoints (#2293)
- feat: persist canvas layout — folder-scoped CanvasLayout model (#2293)
- feat(#2098): gate NSWorkspace Reveal-in-Finder; migrate open(url) to @Environment(\.openURL)
- feat(#2098): gate EmbeddedBackendService engine-spawn behind #if os(macOS)
- feat: cross-platform Platform abstraction layer — Image/Font/Color/View/Pasteboard/FilePicker shims (#2097)
- feat: programmatic guardrails — no-hand-rolled-URLs, AppKit-import allowlist, model-download-folder, OpenAPI-shadow-types (#2271)
- feat: harden release pipeline scripts with --dry-run mode + self-test (#1358)
- feat: guardrail for Python comment hygiene (#1915)
- feat(#1918): strategic prefetch — prewarm populates _EMBEDDER_CACHE + per-library cache warm
- feat: guardrail for toolbar tooltip coverage (#1953)
- feat(#2246): batch result cache for sequential LLM nodes (extract_all, catalogue, cleanup)

**Fixes**

- fix(#2293): wrap canvas-layout GET in {items,count} envelope + ponytail save shrink
- fix: drop dead mind-palace-browser selection branch (referenced removed .mindPalace) (#1455)
- fix(guardrail): update AppKit KNOWN_VIOLATIONS for #2098 cross-platform shims (#2098 #2289)
- fix(tests): bridge XCTest sandbox token-path mismatch for engine auth (#2288)
- fix(tests): fix Swift 6 actor-isolation error in EntityStoreTests (#2288)
- fix(tests): fix test rot in PDFHandlingTests against current APIs (#2288)
- fix(tests): fix test rot against updated EditorView routes and EntityCurationState (#2288)
- fix(tests): fix test rot against updated generated types (#2288)
- fix: unblock Swift test target compilation (#2288)
- fix: invalid widescreen content-pane frame width (#2006)
- fix(#2235): strip enum objects from workflow state via model_dump(mode='json')
- fix: repoint retired multipass test to subworkflow parent (#2251)
- fix: mark all stale 'running' threads failed on startup regardless of age (#2223)
- fix: surface needs_human_selection in route_map instead of silent branch-0 fallback (#2238)
- fix: propagate real page_content to page children; skip blank OCR (#2214)
- fix: propagate page_content to blank page children in _propagate_to_page_children (#2214)
- fix: classify_script surfaces "mixed" for multi-type batches (#2237)
- fix(tests): reconcile #2213 test assertions to cast(null as string) dialect
- fix: resolve .fichero bundle dir to duckdb file in compare-workflow (#2211)
- fix: migrate legacy LanceDB schema on stamped writes (#2213)
- fix: treat empty/None vision response as error in compare_vision (#2212)

**Performance**

- perf: cache PDF document open across page renders (#2247)

**Refactors**

- refactor: drop redundant create round-trip + update double-read in canvas.item actions (#2294)
- refactor(#2297): ponytail shrink arrange (circle comprehension, params subclass, hoist set) + allowlist arrange endpoint
- refactor: shrink Spatial2DCanvas.persistLayout unmoved-node loop (#2293)
- refactor: drop unused loadedFolderId + per-call library header from CanvasLayoutStore (#2293)
- refactor: delete orphaned MindPalace views/state after mode retirement (#1455 #1569)
- refactor: retire .mindPalace sidebar mode, fold 3D/2D into Library view-mode switcher (#1455 #1569)
- refactor: drop unused platform shims — YAGNI / ponytail (#2097)
- refactor: migrate NSImage → PlatformImage shim (chunk 5) (#2098)
- refactor: migrate Color(nsColor:) → Color(platformColor:) shim (chunk 4) (#2098)
- refactor: migrate NSPasteboard → PlatformPasteboard shim (chunk 3) (#2098)

**Docs**

- docs(state): UI reform handoff — Phase 1 entry point, manager+worker policy, Swift gating, target
- docs: reform brief — principle 9 (SwiftUI shows, logic is backend; thin client)
- docs: reform plan §8 — RESOLVED design decisions (Daniel 2026-06-15)
- docs: reform plan — agentic chat as first-class control surface (MCP + App Intents + in-app), via action registry #1848
- docs: reform plan capture round 2 — selection/DnD, multi-window restore, chat-above-sidebar + agents, splittable panes, observability incl backend activity, a11y/AppleScript/localization gates, Tahoe/Golden Gate target
- docs: reform plan — providers/models in Settings + shared-models-folder guardrail
- docs: reform master plan — add programmatic-guardrail suite + folder-as-room/aliases/stripes/export-preview
- docs: UI reform master plan — shell/spatial/toolbar/inspector/annotation/representations/cross-platform (2026-06-15)
- docs(state): morning handoff — 36 shipped, 3 hardening milestones DONE
- docs(state): #1973 held for Daniel (2 blind Swift builds failed); W&C tail dispatched
- docs(state): 29 shipped, AI Infra done; #1973 Swift build-failed, held
- docs(state): 25 shipped; #2214/#2213 bounced; gate caught 4 red batches kept green

**Tests**

- test: adversarial CanvasItem CRUD + action tests (#2294)
- test: adversarial coverage for canvas arrange — geometry, empty, unknown strategy, idempotency, action audit (#2297)
- test: folder-scoped canvas layout round-trip, defaults, idempotency (#2293)
- test: drop stale Mind Palace sidebar source-assertions (retired in PR1) (#1455)
- test: drop isMindPalaceEnabled assertion (flag removed in PR1) (#1455)
- test: path-keyed EntityStore mock — kill FIFO-queue flakiness (#2289)
- test: serialize FicheroTests target — globally-registered URLProtocol mocks bled across parallel suites (flaky EntityStore/Annotation/Note/KG) (#2289)
- test: update stale Swift test assertions after store-pattern migration (#2289)
- test: batch A stale-assertion fixes (#2289)
- test(#1815): seeded perf benchmarks for document list + claims list + cache key throughput

**Chore**

- chore: regen OpenAPI for canvas-items + baseline guardrail allowlists (#2294)
- chore: regen openapi + seed coverage baselines for canvas arrange/layout endpoints (#2297)
- chore: regenerate OpenAPI surface — storage/regenerate-missing endpoint
- chore: standardize transcription preset vision_mode/language/descriptions (#2252)
- chore: rationalize transcribe presets, retire 2 duplicates (#2251)

### 2026-06-14

**Features**

- feat: add canonical-renderer guardrail script for #1935
- feat: normalize OCR geometry providers (#2206)
- feat: preserve apple vision OCR geometry (#1644)
- feat: add model recommendation API (#2204)
- feat: add model language fit contracts (#1820)
- feat: add dynamic model profiles (#2058)
- feat(net): add optional bonjour discovery advertiser (#2158)
- feat(local-ai): expose local inference control API (#1814)
- feat(embeddings): add explicit space migration (#2203)
- feat(embeddings): support bge-m3 opt-in (#2117)
- feat(workflows): add spanish script v2 preset (#2202)
- feat(workflows): add typed sub-workflow contracts (#2201)

**Fixes**

- fix: inject WorkflowExecutionObserver into all secondary scene roots (#1587)
- fix: route whole-PDF multi-page texts to page children, not parent artifact (#2249)
- fix: index alignment + abs paths + per-page fan-out in collection/folder tools (#2239 #2240 #2242)
- fix: full-table column scan in drift guard — 32-row cap → all rows (#2232)
- fix: guard image_uri before retry block on blank page (cloud provider) (#2241)
- fix(tests): patch _compute_timeout + AsyncMock for async offload (#2224 #2228 #2231 #2234)
- fix: explicit remote embeddings gated only by local-only mode, not fallback flag (#2234)
- fix: batch embed_entities/embed_claims to bound peak RAM usage (#2233)
- fix: offload synchronous ONNX embedding to thread in async route handlers (#2231)
- fix: vision() wall-clock timeout backstop + usage telemetry (#2228)
- fix: content-addressed result cache for vision/LLM calls (#2224)
- fix: detect empty transcription output and report it (#2244, #2245)
- fix: migrate legacy LanceDB schema to stamp embedding_model_id on append (#2225)
- fix: vision provider fallback excludes Apple — Catalogue/Transcribe fail with only Apple Intelligence (#2243)
- fix: Auto-Detect transcribe bypasses per-page fan-out, missing documents input (#2236)
- fix: harden AI backend — quota classification, E5 roles, embed error handling, bg task tracking (#2226 #2227 #2229 #2230)
- fix: scanned PDF pages skip LLM vision due to text-layer shortcut in llm mode (#2222)
- fix: bound vision fan-out concurrency via semaphore (#2221)
- fix: use write-authorized db for regenerate-missing; update no-files test assertions
- fix: warm companion thumbnail/display on first access + batch regeneration endpoint (#2216 #2217 #2218)
- fix: gracefully handle empty file list from stale selected_doc_ids (#2220)
- fix: complete parent file doc after per-page fan-out transcription (#2219)
- fix: anchor SVO claims to canvas date via claim_recorded_at (#1657)
- fix: LLM vision processes all PDF pages, not just page 0 (#2215)
- fix: compare vision from library documents
- fix: parse current roadmap in choose-next (#2210)
- fix: hide library path from OpenAPI operations (#1715)
- fix: load derived coverage for uncommon languages (#1820)
- fix(settings): expose safe embedding model choices (#1819)
- fix(settings): harden ai defaults updates (#1809)
- fix(remote): make library paths host-configurable (#2121)
- fix(snapshots): keep route database open during snapshot (#2123)
- fix(infra): harden change stream snapshots (#2123)
- fix(documents): offload async write handlers (#2164)
- fix(storage): offload preview generation (#2164)
- fix(documents): offload upload import ingest (#2164)
- fix(search): offload content retriever (#2164)
- fix(security): require explicit ack for non-loopback bind (#2122)
- fix(workflows): keep preflight scoped to policy checks

**Docs**

- docs(state): 24 issues shipped; per-page holds across all source paths; Observable started
- docs(state): 18 issues shipped; AI Backend Hardening done bar deps
- docs(state): 15 issues shipped; AI Backend Hardening nearly drained
- docs(state): overnight progress — 10 issues shipped, held-broken + deps notes
- docs: document CLI test harness pattern (#1411)
- docs: decide image editing backend strategy (#2061)
- docs: design Pi agent harness (#2071)
- docs(remote): document tailscale private transport (#2026)
- docs(ai): define apple vs ai skills (#2059)

**Tests**

- test: index alignment, abs paths, and fan-out for collection/folder tools (#2239 #2240 #2242)
- test: _propagate_to_page_children works for single-page PDFs (#2249)
- test: regression guard one-vision-call-per-page + per-page-child attribution (#2250)
- test: guard e5 embedding role prefixes (#1795)
- test: cover page offset input resolver (#1981)
- test: cover retrieval payload defaults (#1986)
- test: cover integration registry initialization (#1983)
- test(workflows): isolate extract-all change-event coverage (#2012)
- test(guardrails): finish path-injectable script coverage (#2007)
- test(documents): guard write-route event-loop starvation (#2164)
- test(storage): cover upload cap streaming (#2186)
- test(perf): guard backend hot paths (#2169)
- test(workflows): preserve alias resolver stubs

**Chore**

- chore(deps): update backend Python deps to latest compatible (#2248)
- chore(session-end): final handover — Opus reviews complete, milestones populated
- chore(session-end): overnight handoff + per-page transcribe mandate (#2222)
- chore: run contract guardrails in repo validation (#2207)
- chore: track project context
- chore(session-end): write completion sentinel
- chore(session-end): backend handoff
- chore: guard non-route observable saves (#2001)
- chore(state): record apple vision geometry
- chore(state): record pydantic guardrail
- chore: guard pydantic persistence writes (#2205)
- chore(state): record image editing strategy
- chore(state): record model recommendation API
- chore: baseline model recommendation undo coverage (#2204)
- chore(state): record model recommendation worker
- chore(state): record language fit endpoint
- chore: baseline language fit endpoint wiring (#1820)
- chore(state): record language-fit worker
- chore(state): record Pi agent harness design
- chore(state): record model profiles
- chore(state): record extract-all flake fix
- chore(state): record guardrail test coverage
- chore(state): record OpenAPI typed-field guardrail
- chore(guardrails): catch OpenAPI typed-field misuse
- chore(state): record embedding options
- chore(state): record bonjour discovery
- chore(state): record settings defaults hardening
- chore(state): record tailscale transport docs
- chore(state): record remote path hardening
- chore(state): record change stream hardening
- chore(state): record async offload completion
- chore(state): record upload streaming test
- chore(state): record storage offload
- chore(state): record upload offload
- chore(state): record search offload
- chore(state): record perf guard work
- chore(state): record bind host policy
- chore(state): close ai infrastructure epic
- chore(state): record local inference api
- chore(state): record embedding migration
- chore(state): record apple ai skills design
- chore(state): record bge-m3 opt-in
- chore(state): record spanish script v2
- chore(state): record sub-workflow contracts
- chore(state): record vision alias preflight

### 2026-06-13

**Features**

- feat(workflows): add vision-tier alias preflight (#2200)
- feat(ai): add local MLX service manager contracts (#2199)
- feat(workflows): add Spanish Script multi-pass transcription preset (#938)
- feat(embeddings): pin model+pooling, stamp model-id on vectors + mismatch guard; gate cloud embedding default (#2194 #2193)
- feat(llm): add batched chat and vision calls via abatch (#2057)
- feat(llm): symmetric paid-fallback consent gate + local-only perimeter — no silent cloud leak (#2191 #2192)
- feat(model-comparison): CLI verbs + compare-workflow-across-models (#2195)

**Fixes**

- fix(workflows): make paleography reference search optional (#2190)
- fix(embeddings): register pinned fastembed source correctly (#2194)
- fix(transcribe): presets honor configured vision provider instead of pinning gpt-4o-mini (#2189)
- fix(model-comparison): await async vision() in compare-vision (#2056)
- fix(workflows): transcribe artifact save resolves doc by relative path when file_path is absolute (#2188)

**Performance**

- perf(llm): cache get_langchain_model + bounded in-flight concurrency (#2055 #2062)

**Docs**

- docs(workflows): plan multi-pass workflow engine primitives (#2198)
- docs(ai): plan local MLX on-device agent architecture (#2066)
- docs(ai-infra): architecture + efficiency/batching + AI-test plan (#2056)
- docs(state): #2157 built but HELD — auth-contract conflict with #2177 needs Daniel's call
- docs(state): #2188+#2187 done, ICANH judged (#2189/#2190), #2157 in flight, #2158 deferred
- docs(state): ICANH transcription unblocked (#2188 shipped); Apple-vs-cloud findings + #2189/#2190 gaps

**Tests**

- test(ai): cover remaining model-access edge cases (#2197)
- test(guardrails): catch raw AI model metadata dicts (#2196)
- test(integration): repair stale integration tests + skip-guard real-dep cases (#2187)
- test: adversarial coverage for workflow builder + llm core
- test: adversarial coverage for KG modules (_common, kg routes, graph_rag)
- test: adversarial coverage for db layer + search/documents routes
- test: adversarial coverage for KG extraction core (extract_all + entity_writer)
- test: adversarial coverage for authz/accounts/audit-chain/pairing security surface
- test(guardrails): allowlist 2 helper-delegating security-guardrail meta-tests in vacuous detector (#2153)

**Style**

- style(tests): drop extraneous f-prefix in test_workflow_integration (F541) — #2187 sweep
- style(tests): drop extraneous f-prefixes in test_api_contracts (F541) — #2187 sweep

**Chore**

- chore(state): record workflow engine design
- chore(state): record local MLX service manager
- chore(state): record MLX on-device agent design
- chore(state): record Spanish Script multi-pass preset
- chore(state): record paleography reference-search fix
- chore(state): record AI backend test sweep shipped
- chore(state): record embeddings pin shipped
- chore(state): record #2057 shipped
- chore(state): record #2055/#2062 shipped and #2057 dispatched
- chore(state): tick 1 shipped #2195/#2189/#2191/#2192; tick 2 embeddings+efficiency in flight (#2056)
- chore(state): autonomous backend direction — AI-infra/security/efficiency/comparison, Mac deferred (#2056)
- chore(session-end): refine work order — Spanish-script (not paleography) + HTR models, add Lane 4 Mac App Shell + resume prompt
- chore(session-end): autonomous work order — ICANH bake-off + AI-Infra review + backend cleanup
- chore(state): overnight handoff — 15 issues + 5 test batches shipped, Security milestone done, #2186/#2187/#2157-8 follow-ups

### 2026-06-12

**Features**

- feat(ai): agent working-memory layer — source-anchored, actor-attributed, user-visible notes (#2152)
- feat(ai): central AI-integrity system-prompt framework — facts-not-interpretation, no-pretend-human (#2151)
- feat(auth): per-device tokens + pairing, bootstrap secret loopback-only, HMAC server-proof (#2155 #2156 #2159)

**Fixes**

- fix(security): cap upload size (413) + confine/validate parquet path+columns (#2146)
- fix(security): session sliding-expiry option + stop echoing api_key prefixes (#2129)
- fix(security): login rate-limit + lockout against brute-force (#2145)
- fix(perf): batch reindex_all embedding forward passes (#2168)
- fix(perf): batch search PDF-page projection lookups — kill N+1 (#2167)
- fix(perf): batch list_documents children — kill N+1 (#2166)
- fix(perf): parallelize Stage-2 claim extraction under existing semaphore (#2165)
- fix(workflows): serialize DuckDB connection access in checkpointer — concurrency corruption (#2184)
- fix(app_db): CHECKPOINT after devices migration — prevent poisoned-WAL crash loop
- fix(workflows): resolve library-relative paths to absolute in all source tools (#2183)
- fix(app_db): migrate existing devices table to add expires_at (regression from #2173)
- fix(auth): throttle last_seen writes + device token expiry (#2172 #2173)
- fix(authz): read routes use read authorizer (viewers can read) + document pairing single-process invariant (#2171 #2174)
- fix(security): escape AppleScript interpolation in integrations + lazy dummy password hash (#2170 #2175)
- fix(security): confine all path resolution to library root — arbitrary file read closed (#2139 #2150)

**Tests**

- test(security): consolidated programmatic security-invariant guardrail (#2153)
- test(security): drop order-flaky upload-streaming unit test (event-loop pollution); route-level 413 test covers the cap (#2146, follow-up #2186)
- test(security): make upload-cap streaming test order-independent (explicit max_bytes) (#2146)
- test(authz): key write-authz allowlist by file:handler:method, not line number (#2185)
- test(guardrails): baseline agent-memory mutating routes in undo coverage (UI deferred) (#2152)
- test(guardrails): baseline agent-memory endpoints as cli-only (SwiftUI deferred) (#2152)
- test(authz): update write-authz allowlist line for enhanced_search after search.py perf edit (#2167)
- test(security): adversarial path/xml/pairing/auth-fork/ACL coverage (#2176 #2177)

**Chore**

- chore(openapi): regen schema for agent_memory endpoints (#2152)
- chore(openapi): regen schema for device expires_at on GET /api/pair/devices (#2173)
- chore(state): all CRITICALs closed (26 shipped); conn-auth lane live; phase order set

### 2026-06-11

**Features**

- feat(embeddings): e5-large default (correctly prefixed) + per-model formatting + passage/chunk-level embedding (#2095 #2115)
- feat(sse): bounded subscriber queues + thread-safe emit + event-id replay (#2045)
- feat(ingest): extract PDF named page_label onto page Documents (#2080)
- feat(authz): refuse library access without an authorized session — kill ambient authority, behind FICHERO_MULTIUSER (#2025)
- feat(engine): configurable FICHERO_BIND_HOST (default loopback, refuse 0.0.0.0) (#2048 backend)
- feat(authz): per-library/folder ACL enforced at registry.invoke + read choke-point, behind FICHERO_MULTIUSER (#2024)
- feat(trash): backend soft-delete + restore + purge data layer (#2075)
- feat(audit): tamper-evident hash-chained ActionAudit + verify routine (#2043)
- feat(backups): scheduled periodic snapshots + configurable offsite destination (#2046)
- feat(auth): derive ActionContext.actor from authenticated session — attribution (#2023)
- feat(auth): user accounts + sessions backend behind FICHERO_MULTIUSER flag (#2022)
- feat(auth): password-hash + session-token core for user accounts (#2022)
- feat(ui): annotations + notes as List + detachable detail (Track B, #2010, #2011)
- feat(intents): expose curated audited actions as App Intents / Shortcuts (#2017, #1848)
- feat(ui): route claim/document/annotation/note mutation buttons through /api/actions/invoke (#1848)
- feat(ui): ⌘Z undoes the last audited action via /api/actions/audit/{id}/undo (#2015)
- feat(ui): route entity-merge through /api/actions/invoke (audited action, #1848 exhibit A)
- feat(actions): define 5 missing actions — annotation dup/merge/relink, search reindex, workflow run (#2018)
- feat(actions): chat tools generated from the action registry (#2016/#1847)
- feat(actions): generalized registry-driven undo + audit-log endpoint (#2015)
- feat(actions): action-library mutations as audited actions (#2014)
- feat(actions): annotation mutations as audited actions (#2014)
- feat(actions): import mutations as audited actions (#2014)
- feat(actions): note mutations as audited actions (#2014)

**Fixes**

- fix(workflows): scheduler/file_watcher await, batch Path, executor retry, create_task refs, UTC datetimes, entity dedup claims, bounded caches, swallow/name-collision (#2130 #2147 #2131 #2132 #2133 #2134 #2135 #2136 #2137)
- fix(security): HMAC-key the audit chain + external head/count anchor — truncation + forgery now detectable (#2127)
- fix(infra): write-conflict retry + single-process lock error + serialize LanceDB writes (#2118 #2119 #2120)
- fix(security): harden workflow eval, SSRF, deserialization, XML, CLI and MCP launch paths (#2138 #2140 #2143 #2144 #2141 #2142 #2148 #2149)
- fix(security): write-gate mutating routes + gate ungated library/config routes + generic ACL targets (#2124 #2125 #2126 #2128)
- fix(audit): route chain_seq writes through typed db.save, not raw SQL (#1876 guardrail)
- fix(audit): order chain by monotonic chain_seq — no false-tamper on same-microsecond rows (#2076)
- fix(pdf): PDF page thumbnails (docType==page, fileType=nil) always show the page image, never extracted text (#2052 completion)
- fix(pdf): label page thumbnails by page number (prefer page_label) (#2053 frontend)
- fix(pdf): page thumbnail always renders page image via storage endpoint, never extracted text (#2052)
- fix(engine): PID/owner-scoped orphan-kill — never SIGTERM a shared/remote engine (#2079)
- fix(swiftui): unwrap optional claim.sourceDocumentId at 5 sites — restore app build (openapi #2019)
- fix(menu): File ▸ New creates a new .fichero library via save panel + opens window (#2042)
- fix(settings): app no longer crashes opening the Settings window (#2051)
- fix(models): cache whisper (+pykeen) process-global like embeddings/spaCy (#2050)
- fix(embeddings): load embedding model once per process, not per Database/thread
- fix(engine): pin to single uvicorn process — clamp --workers to 1 (#2044)
- fix(actions): chat-tool description uses model's own __doc__ not inherited BaseModel docstring (#2016)

**Performance**

- perf(llm): reuse pooled API LLM clients per identity; characterize fm-bridge (#2055)

**Docs**

- docs: mark WRITE/synthesis layer as planned (not built) — ground docs in code (#2108)
- docs: human-readable end-user + developer documentation (draft for review)
- docs(session): handoff — design session + infra completion (16 shipped); 2 embedding/audit lanes live; READ→THINK→WRITE spine
- docs(spine): three-layer product model READ→THINK→WRITE + synthesis layer (EPIC #2108)
- docs(roadmap): refined order from 2026-06-11 PM design session — node model #2081 foundation + new reading/bibliography/language/model issues
- docs(mac): holistic UI-shape design proposal for EPIC #2030 (DRAFT for review)
- docs(state): #2053 shipped (13 total); #2080 page_label-extract backend lane live
- docs(state): #2052 shipped (12 total); #2053 page-labels lane live; #2080 filed
- docs(state): #2079 shipped (11 total); #2052 PDF-thumbnail lane live
- docs(state): #2042 shipped + app build restored; #2079 lane live
- docs(state): Phase 1 COMPLETE (9 shipped, auth chain done); pivot to Phase 2 Mac (#2030)
- docs(state): 7 shipped incl #2024 ACL; #2025 + #2048 lanes live
- docs(state): 5 shipped (#2055/#2023/#2046/#2043/#2075); #2024 ACL + #2078 guardrails lanes live
- docs(state): Phase 1 — #2055/#2023/#2046 shipped; #2043+#2075 lanes live
- docs(state): #2055 shipped; #2023 keystone in gate
- docs(state): manager coordination — 2-lane Phase-1 dispatch + verify-gate (no-GUI)
- docs(roadmap): reconcile — 4-phase order is the single sequence; gates cross-cutting; old tiers mapped in
- docs(session): handoff — infra march + 4-phase roadmap planned; continue Phase 1 (#2023 next)
- docs(roadmap): 4-phase work order (infra → mac → workflow/AI-inference → agent) + privacy guarantee + new EPICs (#2021/#2030/#2056/#2067)
- docs(session): handoff — #1848 frontend remainder + Track B Phase 2 (#2010/#2011/#2017) done; openapi staleness + new backlog noted
- docs(morning-test): add #1848 frontend buttons + #2017 App Intents click-tests
- docs(session): handoff — #1848 backend+exhibit-A+⌘Z done; frontend remainder (buttons/#2017/#2010/#2011) queued
- docs(session): #2014 DONE — 109 audited actions/14 domains; #2015/#2016/#2018 downstream in flight

**Chore**

- chore(state): overnight — security/infra wave complete (16 shipped); audit-hmac #2127 landed
- chore(state): overnight — security fix wave (12 issues) landed @ 5b533bcd
- chore(state): infra lanes integrated + review complete — foundation done, hardening backlog filed (#2118-2129)
- chore(openapi): regen — Last-Event-ID header from SSE replay (#2045)
- chore(guardrails): reconcile completeness-matrix baselines to green — backend-first endpoints + prune stale (#2078)

### 2026-06-10

**Features**

- feat(actions): saved-search mutations as audited actions (#2014)
- feat(actions): batch mutations as audited actions (#2014)
- feat(actions): provider mutations as audited actions (#2014)
- feat(actions): conversation mutations as audited actions (#2014)
- feat(actions): document mutations as audited actions (#2014)
- feat(actions): workflow mutations as audited actions (#2014)
- feat(actions): image-editing mutations as audited actions (#2014)
- feat(actions): classification/ontology mutations as audited actions (#2014)
- feat(actions): bibliography/source/reference mutations as audited actions (#2014)
- feat(actions): manual claims (KnowledgeClaim.source_document_id optional, #2019) + duplicate-paths allowlist create_claim→create_claim_impl (#2014 claim sweep)
- feat(actions): claim-domain mutations as audited actions (#2014)
- feat(actions): action registry + audit + invoke chokepoint, entity.merge pilot (#2013)
- feat(observable): InterpretationStore on substrate + reactive Interpretations panel (#2009)
- feat(observable): hermeneutics routes emit interpretation.* change events + close emit-coverage blind spot (#2008)
- feat(ui): citations + references as List + detachable detail (reuses #2003 pattern) #2004 #2005
- feat(ui): artifacts as List + detachable detail window (replaces stacked text boxes) #2003
- feat(observable): ArtifactStore/CitationStore/ReferenceStore on substrate + live-refresh existing views (#1997 #1998 #1999)
- feat(observable): emit document/artifact/citation/reference change events (routes + extraction) #1996 #1997 #1998 #1999
- feat(observable): generic ObservableDomainStore substrate + DocumentStore as first consumer (#1995 #1996)
- feat(observable): emit entity/claim change events per document during extraction #1994
- feat(observable): emit workflow + note-link change events (final store-backed coverage)
- feat(observable): emit document/entity/claim change events on remaining mutations
- feat(dx): test-assertion guard + coverage-gap backlog scanner + pipeline docs
- feat(observable): emit annotation/note change events #1974
- feat(dx): emit_change coverage guardrail #1976
- feat(observable): emit action/research change events #1975

**Fixes**

- fix(test): ontology interpretation-update test uses a canonicalizable predicate (reveals)
- fix(test): claim-action tests provide required source_document_id (manual-claim model constraint)
- fix(test): patch emit_change at source module so the registry's lazy import is spied (#2013)
- fix(actions): lazy emit_change import in registry — break module-load cycle so any import order works (#2013)
- fix(actions): import action/ActionContext/ChangeSpec from submodule not package — avoid partial-init cycle (#2013)
- fix(dx): emit-coverage scanner recognizes substrate changeDomain shape — restores 6 migrated domains the #1995 migration silently dropped (75→87 routes)
- fix(test): guardrail-script tests — repo-root path (parents[4]), sys.modules registration for @dataclass, skip 6 path-injection-dependent cases (#2007)
- fix(test): assert workflow emit types by membership not fixed order (document.updated/artifact.created now also fire)
- fix(observable): emit_change accepts artifact/citation/reference ids (kwarg regression) + update 2 extraction tests for document.updated emit
- fix(test): _make_document arity in artifact/citation emit tests + openapi regen for new route headers
- fix(swiftui): pass xFicheroLibraryPath in createNode — workflow route now requires it (obs-wf regression)
- fix(swiftui): change-stream debounce 150→300ms — coalesce extraction emit bursts (#1994)
- fix(dx): scanner parses issue URL for number + guards edit; ratchet drained modules
- fix(swiftui): change-stream apply() must be O(1) non-blocking — kill click beachball #1973
- fix(dx): coverage-gap scanner — milestone-by-title, body cap, seeded #82 baseline
- fix(dx): scan_test_coverage_gaps excludes generated code + groups by top-level package

**Refactors**

- refactor(observable): migrate 8 stores onto ObservableDomainStore substrate — de-dup change-stream boilerplate (#1995)

**Docs**

- docs: morning-test checklist for the overnight autonomous run
- docs(session): #2013 action-layer keystone landed; #2014 domain sweep next
- docs(architecture): action layer — rewrite all 28 hand-rolled ops onto typed+audited actions, test-first (Daniel approved #1848)
- docs(architecture): action layer plan for EPIC #1848 (registry + audit + undo + chat/intents)
- docs(session): #2000 done (hermeneutics observable + guardrail regression fixed); #2012 flake filed; #1848 next plan-first
- docs(session): Track B Phase 1 complete — artifacts+citations+references on list+detachable-detail (#2003/#2004/#2005)
- docs(session): #2003 artifacts UI + SSE endpoint tests landed; #2004/#2005 cite/ref in flight
- docs(session): observable infra fully done (8 stores migrated); Track B UI (#2003) started
- docs(session): Track A Phase 1 complete — observable substrate + stores + extraction emits
- docs(site): add About Fichero narrative (docs/about.md) + site refinements (catalogues, LiteLLM/LangGraph)
- docs(session): observables COMPLETE (routes + extraction emit) + RAM-rule skill fix
- docs(session): observables routes closed (0 gaps) + completeness audit → #1994 extractor-emit gap
- docs(session): handoff — beachball fix + observables done + test-writer wave 1
- docs(session): handoff — observable backend emit coverage + test-infrastructure

**Tests**

- test(dx): quarantine flaky test_extract_all_mock_emits_workflow_change_events as xfail(strict=False) so it can't fail the gate (#2012)
- test(observable): cover the SSE /api/changes/stream endpoint (open frame, delivery, scoping, unsubscribe-on-disconnect)
- test(dx): cover the test-infra guardrail scripts (check_test_assertions / scan_test_coverage_gaps / check_emit_change_coverage)
- test: cover kg/loaders/bibliography untested symbols (#1984 #1985 #1980)

**Style**

- style(dx): drop extraneous f-prefixes in create-issues.py (ruff F541)

**Chore**

- chore(dx): close emit-change coverage — 0 gaps; mark 2 compute-only POSTs permanently exempt
- chore(openapi): regenerate schemas after observable emit wiring
- chore(session-end): handoff after observable and dx overnight

### 2026-06-09

**Features**

- feat: add gardener helper for #1919
- feat(dx): add OpenAPI client parity guardrail (#1921)
- feat(dx): add choose-next selector skill (#1924)
- feat(verify): observer-pattern audit guardrail — flag legacy @EnvironmentObject/@StateObject/direct-endpoint views (#1851)
- feat(verify): action-surface completeness matrix — action×{menu,context,toolbar,keyboard} (#1925)
- feat(verify): 3 completeness-matrix guardrails — endpoint×{store,cli}, undo, CRUD (#1925)
- feat(mac): replace emoji with SF Symbols / strip from logs (#1913)
- feat(guardrails): Xcode-registration check — every .swift is in project.pbxproj (#1941)
- feat(mac): native List for 8 hand-rolled row collections (#1912)
- feat(library): DB + embedding snapshot & rollback (#1934)
- feat(guardrails): folder-org, dead-files, sidebar-items, service-consistency checks (#1940 #1943 #1944 #1945 #1946)
- feat(verify): ruff in fast tier + check_unmerged_work.py manager check (#1938 #1942)
- feat(stores): ActionStore + ResearchStore + SearchStore; finish view→store migration (#1903 #1904 #1905)
- feat(verify): tier split (fast/standard/full) + auto-file-with-dedup reporter (#1910 #1919)
- feat(guardrails): endpoint-usage matrix + version-date check (#1920 #1923)
- feat(stores): NoteStore + AnnotationStore; migrate notes/annotation views off in-view services (#1882 #1883 #1889)
- feat(guardrails): native-controls, no-emoji/SF-Symbols, comment-hygiene, feature-flag checks (#1912 #1913 #1916 #1922)
- feat(kg): add ClaimStore + retire NotificationCenter claim/entity bus (#1862)

**Fixes**

- fix(swiftui): propagate workflow execution observer into presented views #1967
- fix(kg): granular in-place entity updates — no wholesale list re-render on edit (#1961)
- fix(transcription): preserve uncertainty/diacritics/illegible markers across prompts + quality gate (#289 #1386 #1387 #1388 #1398)
- fix(documents): tolerate doc: prefix + skip unresolvable children to stop 404 thrashing (#1957)
- fix: OSLog message can't be concatenated with + (line-wrap broke it) (#1915)
- fix(stores): SearchStore import FicheroAPIClient + searchStore internal for +Helpers extension (#1903)
- fix(verify): roll up auto-file reporter to one issue per guardrail — no spam, stable dedup (#1919)
- fix(kg): make mutationError internal so the +Details extension (separate file) can set it (#1862)
- fix(ui): remote-safe Reveal in Finder + clean onboarding swiftlint (#1861 #1881 #1866)
- fix(kg): dedup near-duplicate claims via normalized SVO key (#1805)
- fix(dev): scope uvicorn --reload to engine src + wire guardrails into verify_all
- fix(swiftui): wire List(selection:) into ChainListContent (#1895)

**Performance**

- perf(library): versioned thumbnail cache + perf_span instrumentation (#1917 #1958)

**Refactors**

- refactor(observable): DocumentStore ObservableObject→@Observable + @Environment migration (16 consumers) (#1851)
- refactor(kg): Source Annotations → native List with per-document sections (#1960)
- refactor(observable): WorkflowStore ObservableObject→@Observable + change-stream + migrate 2 views (#1911)
- refactor(guardrails): key KNOWN_VIOLATIONS on content-signature, not file:line (#1948)
- refactor(services): route artifact-list + batch-execute through the generated client (#1943)
- refactor(swiftui): convert view-local ObservableObject state holders to @Observable macro (#1884 #1886 #1887 #1901 #1858)
- refactor(db): route raw db.conn through typed db.py methods (#1909)

**Docs**

- docs(session-end): worktree-safety rule (rule 11) + evening cleanup/incident handoff
- docs(state): landed action-matrix/transcription/source-annotations; entities-rerender root cause + no-rerender rule; observer sweep worklist
- docs(state): landed #1911/#1925; pruned 50 stale orphan branches; transcription-fidelity re-apply in flight
- docs(state): integrated #1948/#1957/#1917/#1958; record file-set partition rule
- docs(history): 2026-06-09 session summary
- docs: VERIFY.md — authoritative checklist of what verify checks + gaps (#1938-1942)

**Tests**

- test(guardrail): re-baseline comment-hygiene line after line-wrap shift (#1916 #1948)
- test(guardrail): baseline POST /api/artifacts/ as cli-only after #1943 refactor
- test(guardrail): re-baseline native-controls KNOWN_VIOLATIONS after ResearchTasksPane line shift (#1912)
- test(verify): wire native-controls/emoji/comment/feature-flag guardrails into fast tier (#1912 #1913 #1916 #1922)

**Chore**

- chore(session-end): handoff for incoming codex manager — observable/infra grind + runtime-bug triage (#1960-#1971)
- chore(state): reset handoff — codex-only, 3 lanes to integrate, tmux+send-keys pattern
- chore(session-end): night checkpoint + handoff — data-layer keystone landed, codex #1909 in flight

### 2026-06-08

**Features**

- feat(guardrails): add view→store bypass checker (#1876)
- feat(kg): observable EntityStore + per-library change-stream consumer (#1885 #1863)
- feat(api): emit change-stream events on claim + document mutations (#1863)
- feat(api): add per-library change-stream shell + SSE endpoint (#1863)
- feat(kg): modernize EntityDetailView, in-place entity rename, KG-claim List interactions (#1864 #1865)
- feat(inspector): native List + two-step attributes across document inspector tabs (#1838 #1839 #1853)
- feat(webkit): plot document places on the map
- feat(webkit): render document events on the timeline
- feat(library): entity icon view (#1773)
- feat(workflow): discrete KG-Persist step 5 + full-pipeline chaining (#1757)
- feat(library): entities as a first-class collection in list view
- feat(workflow): discrete Merge/Dedup step 4 (#1757)
- feat(kg): claim merge/unmerge UI in inspector (#1689)
- feat(kg): claim merge + unmerge endpoints (#1689)
- feat(workflow): discrete Extract-SVO step 3 (#1757)
- feat(workflow): discrete Extract-Entities step 2 (#1757)
- feat(workflow): discrete Import→Artifacts step 1 (#1757)
- feat(curation): Prune-trivial button in claim inspector (#1763)
- feat(curation): prune-trivial claim detector + endpoint (#1763)
- feat(notes): page+folder add/delete UI for notes & annotations (#1759)
- feat(notes): page+folder add/delete parity for notes & annotations — backend (#1759)
- feat(search): scope selector in search UI (#1766)

**Fixes**

- fix(workflows): prune legacy catalogue presets
- fix(swiftui): native List/Grid for workflow, comparison & agent control surfaces (#1894 #1900 #1896)
- fix(swiftui): native List + ContentUnavailableView for Mac-assed panes (#1897 #1878 #1898 #1890)
- fix(kg): gate embedding auto-merge behind lexical agreement (#1907)
- fix(kg): accent-fold entity dedup so near-duplicates collapse (#1811)
- fix(inspector): single-click selects, double-click opens; fix 2 review HIGHs (#1838 #1839)
- fix(kg): exclude tombstoned entities from alias-map too (fix-then-sweep #1849)
- fix(kg): hide merged-away entities from entity list so merge actually shows (#1849)
- fix(kg): make multi-provider KG extraction populate fields on OpenRouter + Apple (#1802)
- fix(kg): make structured extraction work across providers (#1803)
- fix(kg): folder-scope extraction skips a single failed page instead of aborting the whole run (#1799)
- fix(kg): unambiguous compactMap in entity mention lineLabel
- fix(demo): inspector tab order (Content/Annotations/Notes/KG/Outline/Entities/Artifacts/Info) + hide Mind Palace & Batches from sidebar
- fix(library): drop optional chaining on non-optional windowState.libraryId (entity-as-library)
- fix(kg): unambiguous compactMap in claim merge displayName (#1689)
- fix(notes): repair #1759 UI merge — container-decode list path, scope addNote caller, revert hand-edited pbxproj
- fix(annotations): skip document-less annotations after #1759 made documentId optional
- fix(curation): declare kgFocusState env, unwrap claim.id, kill false-success no-op message (#1763)

**Performance**

- perf(entities): push doc-scoped list_entities filters to SQL (#1815)

**Refactors**

- refactor(views): drop iOS swipe actions + finish raw-URLSession removal (#1885 #1893 #1902)
- refactor(views): finish URLSession/host removal — OSLog in DocumentPickerSheet, drop dead error enum (#1880 #1879)

**Docs**

- docs: add developer manual pages (#1797)
- docs: add user manual pages (#1796)
- docs(swiftui): design the observable data layer + backend change-stream (#1851 #1863)
- docs(swiftui): Mac control choice (List vs Table), no swipe, edit-via-navigation not modal
- docs(swiftui): whole-app Mac-assed/2026 audit + existing-views Observable in scope
- docs(swiftui): Observation-first + Golden-Gate-only modern conventions for agents
- docs: 2026 Apple-stack foundation — Golden Gate-only target, Sept 1 release (#1838)
- docs: switch to dated-release / milestone-at-a-time model; capture action-layer direction (#1848)
- docs: ratify Mac-assed AppKit-fidelity direction + sequence new arcs (#1838 #1844)
- docs(session): morning handoff — loop paused (Daniel awake), 20 merged overnight, ready-next list
- docs(session): tick — #1757 CLOSED (5-step pipeline complete) + entity-as-library list MVP; icon-view + extensibility-guarantee lanes running
- docs(session): overnight tick — #1757 step4 + #1689 UI merged (#1689 closed); step5+chaining and entity-library-view lanes running
- docs(session): overnight tick — #1689 backend + #1757 step3 merged; claim-merge-UI + step4 lanes running
- docs(session): overnight tick — #1757 step2 merged + wiring-test fixed; claimmerge(restarted) + step3 lanes running
- docs(session): overnight tick — #1757 step1 + #1763 prune-button merged (#1763 closed); step2 + claim-merge-backend lanes dispatched
- docs(session): overnight tick — #1763 prune-trivial backend + #1759 notes/annotations UI merged; prune-button + import-step lanes dispatched
- docs(session): overnight tick — #1759 backend + #1766 UI merged; notes-UI + prune-trivial lanes dispatched
- docs(session): overnight tick — #1766 backend + #1763 claim-curation merged; scope-UI + notes-audit lanes dispatched

**Tests**

- test(guardrail): exclude generated/ dirs from db-access scan (#1876)
- test: guard raw DuckDB/SQL access to the persistence layer (#1876)
- test(perf): add gate-safe entity-list perf harness + baseline (#1815)
- test(contracts): enforce additive/no-migration extensibility guarantee (#1652)
- test(contracts): allowlist 5 streaming/upload endpoints in swiftui wiring coverage

**Chore**

- chore(state): night checkpoint — data-layer keystone landed (~14 batches)
- chore(state): night progress checkpoint — 5 batches landed, 2 workers running
- chore(session-end): checkpoint state — multi-provider extraction merged, roadmap #1774-1834 filed

### 2026-06-07

**Features**

- feat(search): claims:/entities: scopes + include array (#1766)
- feat(curation): claim bulk-curation parity in inspector (#1763)
- feat(curation): entity Merge action in bulk-curation UI (#1751)
- feat(search): embed entities + claims into canonical LanceDB tables, fix semantic search (#1767)
- feat(curation): entity bulk-curation MVP — multi-select Approve/Reject/Suppress + scope choice (#1751)
- feat(curation): exclude-from-processing toggle + KGCurationService (generated client) (#1752)
- feat(curation): enforce entity-resolution + claim-suppression rules at the write gate (#1761 #1763)
- feat(ui): search results in list view with clickable excerpts + entity lozenges in list/column (#1769 #1770 #1771)
- feat: add persistent curation rule models (#1761)
- feat: add kg curation rule routes (#1761)
- feat(library): add .workspace + .spatial view-mode stubs, flag-gated (#1740 Phase 1)
- feat(menu): File menu Open Recent + Close Database (#1720)

**Fixes**

- fix(curation): wire Merge to entityService + unwrap optional corroborationCount (#1751)
- fix(library): auto-seed Inbox on library registration (#1592)
- fix(curation): resolve build errors in entity bulk-curation MVP (#1751)
- fix(curation): resolve build errors in exclude-toggle wiring (#1752)
- fix(curation): case-insensitive entity-rule matching + redirect-cycle suppresses (#1772)
- fix(extract): robust output-language detect + pinnable primary-language override (#1764)
- fix(import): persist SVO claims inline + register import_receipt artifact (#1662, #1756)
- fix: audit search stack and unhide legacy entity vectors (#1758)
- fix(api): add typed response models for audit batch
- fix(swiftui): keywordCloud generated-init arg order (apiarch gate fix)
- fix(api): add explicit response models for legacy routes
- fix(sidebar): add Mind Palace mode icon (#1728)
- fix(storage): store image paths relative to library root (#1663, #1664)
- fix(inspector): show page-scoped entities in the Entities panel (#1653)
- fix(window): drop a .fichero library opens/focuses a window, not replace (#1721)
- fix(api): correct generated schema name + metadata helper collision + Identifiable (#1702)
- fix(library): auto-seed an Inbox on create + open (#1727)
- fix(window): pane-aware min width (#1735)
- fix(library): allow single-column min width (#1734)
- fix(library): mini-toolbar overflow menu (#1733)
- fix(toolbar): consistent toggle styling (#1732)

**Refactors**

- refactor(swift): migrate research service to generated client
- refactor(swiftui): use generated keyword cloud client
- refactor(api): NoteItem uses generated schema (#1702)
- refactor(api): ActionItem uses generated schema (#1702)
- refactor(api): ActivityItem uses generated schema (#1702)
- refactor(api): model comparison uses generated schemas (#1702)

**Docs**

- docs(session): overnight tick — #1592 + #1751 merged, search-scope + claim-curation lanes dispatched
- docs(session): overnight tick — #1767 merged, inbox + entity-merge lanes dispatched
- docs(session): apiarch2 gated; Marshall one-folder results + #1662/#1756 port plan
- docs(session): #1750 review APPROVE + cache-flush follow-up filed
- docs(session): new direction — #1756-1759, Marshall one-folder, #1750 review running
- docs(session): gate results + pbxproj lesson + Marshall #1662 finding
- docs(api): add consistency audit report
- docs(session): big-picture architecture priority; 3 lanes (no-local/apiarch/marshall); milestone-first-review
- docs(session): morning plan — 11 new issues, build waves, model locked; Wave 1 (#1750) running
- docs(session): tick 12 — idle pacing-down, no safe stale-close
- docs(session): tick 11 — #1740 Phase 1 stubs shipped (20 closed tonight); pacing down
- docs(session): tick 10 — #1728 + #1611 closed (20 tonight); #1740 Phase 1 stubs lane running
- docs(session): tick 9 — relative paths + inspector entities shipped (18 closed); #1728 lane running
- docs(session): tick 8 — #1721 shipped (15 closed); #1653 + #1663 lanes running
- docs(session): tick 7 — #1720 File menu shipped (14 closed); #1721 drag-open lane running
- docs(session): tick 6 — #1702 shipped (13 closed); #1720 File menu lane running
- docs(session): tick 5 — #1727 Inbox + #1725 resolved (12 closed); #1702 lane running; worktree housekeeping
- docs(session): tick 4 — responsive cluster shipped (10 closed); #1727 + #1725 lanes running

**Build**

- build: unregister deleted LocalImageThumbnailView from pbxproj (#1750 gate fix)

### 2026-06-06

**Features**

- feat(api): add LibraryPathMiddleware to generated client (#1710 phase 1)
- feat(ui): Open / Open in New Tab / Open in New Window context menus + Cmd-click (#1685)
- feat(workflows): add staged catalogue artifact preset

**Fixes**

- fix(window): open-in-new-tab opens a tab not a window (#1736)
- fix(mindpalace): persist node position on drag (#1730)
- fix(sidebar): clear stuck grey row highlight (#1737)
- fix(library): render PDFs via shared storage path (#1707, #1731)
- fix(storage): serve PDF page images via storage (#1707 #1731)
- fix(swiftui): restore access level + @ViewBuilder on split files (#1703)
- fix(toolbar): clarify library browser toggle (#1724)
- fix(sidebar): surface hidden sidebar destinations (#1723)
- fix(swiftui): guard try! crash sites + surface silent import/fetch errors (#1718)
- fix(swiftui): inject library path into Note/Annotation services — kill init-race (#1716)
- fix(swiftui): /api/actions ops require the library header — pass it (#1711)
- fix(swiftui): pause/cancel workflow ops are app-wide — drop library header (#1712)
- fix(swiftui): pass library path to compare-node (it's library-scoped) (#1666)
- fix(ui): make Model Comparison UI reachable (#1475)
- fix(ui): show all items — remove 30/50 display caps (#1687)
- fix(swiftui): route batches/model-comparison/local-models through generated client (#1701)
- fix(layout): keep reading pane toggles stable
- fix(library): keep storage images and canvas panes stable
- fix(layout): route image pages away from pdf canvas
- fix(layout): keep canvas on selected preview document
- fix(inspector): show imported entities before claims
- fix(library): select pages into the image canvas
- fix(swiftui): use generated client for document entities
- fix(import): report manifest artifact counts
- fix(library): keep reading panes stable when library hidden
- fix(library): reveal storage image canvas after layout

**Refactors**

- refactor(swiftui): split DocumentInspectorInfoTab into focused files (#1703)
- refactor(swiftui): split WelcomeView + SidebarItemRow into focused files (#1703)
- refactor(swiftui): split SidebarView+ViewComponents into focused files (#1703)
- refactor(swiftui): split DocumentInspectorArtifactsTab into focused files (#1703)
- refactor(swiftui): split DocumentInspector into focused files (#1703)
- refactor(swiftui): split OntologyBrowser into focused files (#1703)
- refactor(swiftui): extract shared EntityRowView, de-dup entity renderers (#1690)
- refactor(swiftui): centralize engine base URL + remove force-unwrapped URLs (#1717)
- refactor(swiftui): migrate Tier-2 REST stragglers to generated client (#1714)
- refactor(swiftui): de-dup + migrate Actions services to generated client (#1711)
- refactor(swiftui): migrate + consolidate IntegrationsService to generated client (#1713)
- refactor(swiftui): migrate WorkflowExecutionService to generated client (#1712)
- refactor(swiftui): migrate ModelComparisonService to generated client (#1666)
- refactor(swiftui): extract shared FicheroWebView, de-dup WKWebView wrappers (#1699)

**Docs**

- docs(session): tick 3 — #1736/#1730 shipped; responsive cluster running; Views reorg deferred (needs move helper)
- docs(session): overnight tick 2 — PDF render + grey-row shipped; #1736/#1730 lanes running
- docs(session): overnight tick 1 — backend PDF + InfoTab split shipped; 2 lanes running
- docs(session): overnight cleanup plan — 2 lanes launched, #1740 parked
- docs(session): manager tick — sidebar split shipped, UX worker dispatched (#1703/#1723/#1724)
- docs(session): compact handoff + RealityKit feature filed
- docs(session): 3 big-file splits shipped; codex53 = worker engine
- docs(session): audit-hunt batches shipped; #1704 reorg plan posted
- docs(session): lint gate closed (#1719); swiftlint now pre-commit
- docs(session): #1716+#1717 batched-shipped; next disjoint batches queued
- docs(session): Swift URLSession sweep complete; next phase = audit hunt
- docs(session): #1711 done; #1715 root-cause backend fix filed
- docs(session): #1710 phase 1 done (middleware skip-list fixed)
- docs(session): after migrations, return to audit findings + hunt more consistency bugs
- docs(session): #1712 done; elevate #1710 LibraryPathMiddleware as next
- docs(session): checkpoint — #1666 audit + migration backlog (#1710-1714)
- docs(session): checkpoint — #1685/#1475 shipped, branch backlog cleared
- docs(session): checkpoint manager consistency sweep + IIIF integration
- docs(session): record Marshall SwiftUI handoff
- docs(architecture): fix stale paths + standardize knowledge-object terminology (#1705)

**Style**

- style(swiftui): swiftlint cleanup — session-introduced + mechanical violations (#1719)

**Chore**

- chore(xcode): normalize project.pbxproj (Xcode reserialization, build-verified)
- chore: commit page-content CLI option + pbxproj registrations (build-verified)

### 2026-06-05

**Features**

- feat(workflows): add reviewable catalogue stage presets

**Fixes**

- fix(storage): resolve copied files relative to library
- fix(ontology): load entity notes from current library
- fix(library): render image-backed pages via storage
- fix(library): route imported image thumbnails through storage
- fix(library): prefetch thumbnails for imported pages
- fix(workflows): report persisted run status
- fix(iiif-import): persist transcript artifacts
- fix(workflows): match exit completion by event label
- fix(workflows): fail when exit nodes do not complete
- fix(workflows): remove dead citation dependency from Catalogue (#1665)
- fix(workflows): dedupe graph scheduling edges (#1665)
- fix(workflows): disable live Send fanout until checkpoint-safe (#1665)
- fix(library): close stale DB handles before recreate (#1668)
- fix(swiftui): use generated workspace picker API (#1666)
- fix(swiftui): route imported pages through storage display

**Tests**

- test(workflows): cover imported page catalogue outputs

**Chore**

- chore(session): record Marshall workflow handoff

### 2026-06-04

**Features**

- feat: add IIIF annotation importer (#1646)

**Fixes**

- fix(import): materialize artifacts for manifest pages
- fix(library): make known-library registry global + add Close Library (#1661)
- fix(inspector): surface source-doc-scoped entities without claims (#1653/#1655)
- fix(iiif-import): real entities from SpecificResource.source + dc:type (#1646)
- fix(iiif-import): one collection folder + map supplementing transcript to page_content (#1646)

**Docs**

- docs(architecture): portable LangGraph workflows + IIIF/W3C/RDF interchange format (#1649)

**Chore**

- chore(session-end): checkpoint state — import architecture (IIIF/W3C/RDF) + corpus pipeline

### 2026-06-03

**Features**

- feat(manifest-import): navigable group folders, local-cached previews, link/copy/move ingest (#1639)
- feat(manifest-import): add --copy-images option to canonical importer (#1637)
- feat(cli): add general import-manifest command
- feat: visible Workspaces section + New Workspace affordance (#1617)

**Fixes**

- fix: guard reading-surface WKWebView against non-finite frame (#1641) (#1642)
- fix(extract_all): inject schema into Apple Stage-1 prompt so NER entities are extracted (#1633) (#1638)
- fix: make Apple _EntitiesOnly grammar permissive again (revert #1272 over-constraint); detect empty via soft-fail (#1633)
- fix: label the search-result relevance badge instead of a bare '%' (#1476)
- fix: shrink Library list-row thumbnail so the title gets more width (#1459)
- fix: make Add Research Project reachable + load existing projects (#1614)
- fix: restore Library table/column mode for folders + rename list/table → List/Column (#1613)
- fix(library): remove RealityKit/3D tab from the document/WebKit pane (#1616)
- fix: drop corrupting knowledgeclaims ART indexes (#1611, follow-up to #1596)

**Docs**

- docs: add scripts/launch-release.sh + bash-launch debugging note (#760)
- docs: broaden SwiftUI→backend logic audit to whole app (#1072)

### 2026-06-02

**Features**

- feat: bound the thumbnail prefetch cache with FIFO eviction (#719)
- feat: add entity sidebar entry point (#1486)
- feat(workspace): node-class chip + curated-items section in inspector (#1570 Phase 1 D/E)
- feat(workspace): node_class service + wire models (#1570 Phase 1 A/B/C)
- feat: built-in mock provider for zero-cost catalogue debug runs (#1566)
- feat: node-class dimension + workspace-item node_class (#1570 Phase 1 backend)
- feat(view-menu): add pane-visibility items mirroring toolbar toggles (#1215)

**Fixes**

- fix: wire knowledge graph endpoints (#1422)
- fix: wire hermeneutics endpoints (#1423)
- fix: wire claims entities endpoints (#1424)
- fix: wire annotation artifact endpoints (#1425)
- fix: highlight claim source text pane (#1464)
- fix(mind-palace): bound RealityKit scene to prevent GPU watchdog crash (#1400)
- fix: scope KG graph to active page (#1568)
- fix: refresh page content after a workflow completes (#1445)
- fix: wire research-project endpoints into ResearchTasksPane (#1431)
- fix: open source annotations from claim cards (#1564)
- fix: reveal SVO source claims inline (#1565)
- fix: keep KG node selection in map (#1563)
- fix: allow Fichero and CloudStorage library roots (#1594)
- fix: guard DuckDB entity upserts against ART index crash (#1593)
- fix: allow iCloud-synced Documents/Desktop in library-path allowlist (#1585)
- fix: compare view preserves image aspect ratio, not square (#1558)
- fix: align edit button with other image-toolbar icons (#1556)
- fix: image-editor mini-toolbar height matches sibling toolbars (#1555)
- fix: normalize doc: prefix in /children lookup (#1345)
- fix: don't label on-device Apple Intelligence as PAID in cost note (#1560)
- fix: catalogue stamps claims+entities with per-child doc id, parent compiles union (#1562 write-path)
- fix: entities endpoint honors per-page source_document_ids (#1562 read-side)
- fix(ingest): make folder ingest thread-safe — stop the shared-DuckDB race dropping files (#1554)
- fix(crash): inject WorkflowExecutionObserver into detached inspector host (#1561)
- fix(kg): scope entities to their source page/doc, not just the parent (#1562)
- fix(api): order document list/children endpoints by sort_order (#572)
- fix(api): /children accepts doc:-prefixed document ids (#1345)
- fix(canvas): make magnifier control-bar text legible over bright content (#1530)

**Refactors**

- refactor(inspector): remove dead V1 artifacts-tab code, keep live shared types (#1507)

**Docs**

- docs: update architecture for real-data library discipline
- docs(thinking-layer): universal node-class north star + Workspace/ResearchProject as tree nodes by class (#1570)
- docs(thinking-layer): record Daniel's 5 decisions + node-class/prototype direction (#1488 #1570)

**Tests**

- test: cover Activity-run sidebar value mappers (#583)

**Style**

- style(inspector): silence empty_count false-positive on numeric badge count (#1509 follow-up)

**Chore**

- chore: record worker session end
- chore(state): PM manager-loop checkpoint — #1566 merged, #1581/#1583 open for visual verify
- chore(session-end): 2026-06-02 — design lock-in + #1562/#1561 foundation; STATE/MEMORY/HISTORY

### 2026-06-01

**Features**

- feat(notes): standalone NotesBrowserView (#1500)
- feat(kg): entity-bio notes in entity inspector (#1501)
- feat(library): Add-to-Workspace picker (#1494)
- feat: SourceOutlineView — document drill-down inspector tab (#1492)
- feat: surface the Research workspace at first run (#1499)
- feat: claim provenance + click-to-expand source passage inline (#1467)
- feat: entity names in the KG digest are clickable lozenges (#1466)
- feat: retarget the Document Inspector to a clicked entity (#1484)
- feat: move Sort + Filter into the Library mode rail (#1477)
- feat: stable layout by default; selection-driven changes are opt-in (#1452)
- feat: per-window show/hide for the document canvas and reading pane (#1448)
- feat: add Edit-mode toggle on the image canvas (#1453)
- feat(reading-surface): decouple active-document from page-focus scope (#1463)
- feat(a11y): accessibility labels + identifiers on sidebar mode bar and rename field (#584)
- feat(toolbar): view display mode picker in toolbar, sync with View menu (#1215)
- feat(toolbar): mode icon + title in toolbar center, toolbarIcon computed prop (#323)
- feat(image-editor): add fuzzy-clean toolbar button + accessibility labels on pickers (#1371)
- feat(kg-viz): hop depth control + degree-scaled node sizes in force graph (#902)
- feat(image-editor): complete step editors (remove_bg, fuzzy_clean, segment) + interpretation inline edit (#1420)
- feat(import): add Chota+Pacific maps corpus importer (#1232)
- feat(kg): hermeneutics create-interpretation form in inspector panel
- feat(image-editor): crop aspect-ratio presets + A/B wipe compare refinement (#1420/#1395)
- feat(providers): promote OCR/HTR model defaults (#1145)
- feat(import): add GHC catalogued materials importer (#1233)
- feat(import): add Archivo Judicial de Medellin catalogue importer (#1234)
- feat(citations): detect numbered footnote citation lines in extraction workflow (#1100)
- feat(bibliography): add folder sidecar matching + record attach endpoint (#1101)
- feat(import): add source-archive importers for Newton + Istmina corpora (#1236 #1238)
- feat(kg): hermeneutics interpretations panel in KG inspector tab
- feat(image-editor): rotate angle slider in edit chain step editor (#1420)
- feat(inspector): bibliography panel — copy-BibTeX buttons + inline BibTeX view (#1100)
- feat(inspector): document prototype/class picker in Info tab (#1377)
- feat(mcp): add mind-palace notes tools + typed full-surface returns (#1301)
- feat(inspector): wire curation history, bibliography, and workflow provenance panels (#1434)
- feat(mcp): expose workflow pause/resume controls in full surface (#1223)
- feat(import): add Box link-reference importer CLI path (#1329)
- feat(import): add Dropbox link-reference importer path (#1330)
- feat(mcp): add claim mutation tools to full MCP surface (#1269)
- feat(import): add Sergio corpus + spreadsheet importer path (#1235)
- feat(mcp): complete full MCP tool surface with vision hook paths (#1338)
- feat(inspector/workflow): LazyVStack in KG entity rows + user-defined extraction targets (#994, #1372)
- feat(mcp): add simplified external-agent MCP surface (#1327)
- feat(workflows): add DeepL translation preset wiring test (#1332)
- feat(documents): add PDF page-range navigation endpoints (#1378)
- feat(#1355): Notes tab in Document Inspector — add/edit/delete notes via notes.py backend

**Fixes**

- fix(tests): repair FicheroTests target compile on merged main
- fix(library): decode image thumbnails off the main thread (#1509)
- fix: move PDF page nav from window toolbar to document toolbar (#1531)
- fix: restyle canvas edit-mode toggle to match toolbar items (#1528)
- fix(image-editor): show busy overlay in all compare modes (#1532)
- fix(image-editor): relabel image 'Fuzzy Clean' as 'Despeckle' (#1534)
- fix(image-edit): honour EXIF orientation in preview render (#1529)
- fix(image-editor): correct Before/After sides in wipe compare (#1538)
- fix(image-editor): coalesce original↔edited toggle to latest intent (#1508)
- fix(image-edit): split alpha before despeckle/autocontrast — preserve transparency, green tests (#1534 follow-up)
- fix(image-edit): fuzzy-clean no longer 500s on RGBA (Remove-Background output) (#1534)
- fix(library): widen content-list min width 240→300 so Sort/Filter rail doesn't clip (#1477)
- fix(storage): one canonical data dir — app + engine both use Application Support/Fichero/
- fix(embeddings): default to fastembed-supported model; pre-warm guard (#1524)
- fix: KG Map + Timeline stop dropping in-scope claims (#1470, #1471)
- fix: restore Knowledge Graph + Research entries in the View menu (#1485)
- fix: Dates facet respects the KG filter + Hide all (#1468)
- fix: make the document KG graph fill the pane + drop the useless legend (#1465)
- fix: polish the per-window pane toggles (#1516)
- fix: inspector toggle works when the sidebar is collapsed (#1513)
- fix: route image-edit toolbars through the shared height constant (#1449, #1460)
- fix: use a clean user-facing name for the knowledge pane (#1450)
- fix: de-duplicate the view-mode picker — one home per context (#1446)
- fix: floor the PDF canvas pane width so its toolbar can't crop (#1454)
- fix(research): make URL safety DNS checks non-blocking async (#461)
- fix: pin Workflows/Batches/Activity once at sidebar bottom (#1456)
- fix: per-window inspector toggle (#1451) + PDF page in window title (#1482)
- fix(kg): persist timeline/map-ready date+place claim fields (#1470 #1471)
- fix(clean_text): deterministic OCR garbage cleanup path (#1462)
- fix(search-explain): use real doc fields and include source attribution (#424)
- fix(library): icon size, image thumbnails, filter visibility, WebKit selection color (#1459, #1458, #1473, #1481)
- fix(search): project pdf file hits to page-scoped results with anchors (#1478)
- fix(runtime): defer @Published mutations in selectRoom + toggleEdited (#1444)
- fix(tooltips): add missing .help() on artifacts-browser refresh/copy and filter clear buttons (#1371)
- fix(migrations): report rolled_back status when run fully reversed
- fix(runtime): map camelCase node provider/model aliases
- fix(image-viewer): expand loupe and magnifier panel size range (#355)
- fix(storage): ignore invalid metadata path types in resolve_source
- fix(runtime): support camelCase edge aliases in workflow normalization
- fix(storage): expanduser for source path resolution
- fix(kg_writer): skip writes with empty target_doc_id
- fix(kg): dedupe duplicate citation hits per page/reference (#924)
- fix(kg): skip empty-svo claims in triangulation support counts
- fix(gate): detect generated-client operation usage in wiring check (#1418)
- fix(kg-surface): load document entities for Timeline and Map tabs (#1434)
- fix(#625): JSON/text files now show content preview thumbnail in grid and list view

**Performance**

- perf(icons): eager thumbnail prefetch when folder contents load (#719)

**Docs**

- docs: add UI map cheat-sheet + thinking-layer architecture design (#1488)

**Tests**

- test(inspector): add missing ArtifactRichTextCodec source + delegation (#710)
- test(inspector): extract ArtifactRichTextCodec + RTF round-trip tests (#710)
- test(runtime,auth): cover object workflow defs and docs auth paths (#664 #510)
- test(core): expand ingest/db/builder coverage and fix llm config precedence
- test(app_db): enforce lock for settings reads and conn ops (#709)
- test(gates): add duplicate handler/writer detector gate (#1419)

**Style**

- style: use the shared toolbar-height constant in MainToolbar preview (#1449)

**Chore**

- chore(session-end): update STATE + HISTORY for 2026-06-01 session 2
- chore(session-end): update STATE, MEMORY, HISTORY for 2026-06-01 SwiftUI worker session
- chore(wiring): allowlist bibliography attach endpoint (#1101)
- chore(wiring): allowlist new document prototype/page-range endpoints (#1377 #1378)

### 2026-05-31

**Features**

- feat(documents): add user-editable prototype assignment APIs (#1377)
- feat(#1268): per-node model comparison sheet in workflow editor
- feat(model-comparison): persist selected model onto workflow node (#1268)
- feat(claims): seed timeline dates from document metadata (#1373)
- feat(api): add kg review queue summary endpoint for badge polling (#1356)
- feat(#1420): Photos-style edit layer — icon-only toolbar + expandable inspector chain
- feat(#1402/#1383): DocumentCanvas — unify image+PDF viewer on existing ZoomableImagePreview stack
- feat: generate OpenAPI CLI command surface (#1408)
- feat(contracts): programmatic UI/CLI wiring-coverage gate
- feat(search): add opt-in int8 embedding quantization path (#876)
- feat(search): add BM25 lexical scoring and bge-m3 default embeddings (#875)
- feat(search): add alias-aware entity query expansion and rank bonus (#737)
- feat(remote-jobs): add SLURM bundle primitives for ACEnet runs (#657)
- feat(inspector): add side-by-side artifact comparison sheet (#343)
- feat(workflows): add cli_agent tool for claude/codex execution (#341)
- feat(flags): enable workflow authoring views in beta defaults (#248)
- feat(flags): reapply workflow execution release defaults (#252)
- feat(workflows): promote workflow authoring surface toward release defaults (#251)
- feat(workflows): promote workflow execution beta surfaces in release profile (#249)
- feat(workflows): promote batches feature to beta default (#254)
- feat(workflows): add selectable batch processing order in run sheet (#349)
- feat(workflows): re-enable batches sidebar surface behind feature flag (#282)
- feat(image-editor): support page navigation and compare workflows
- feat(image-editor): add A/B compare slider and side-by-side modes
- feat(workflows): add selection source node and honor workflow input source (#667, #348)
- feat(image-ux): collapse preview/edit into single image surface
- feat(workflows): surface model comparison UI and restore workflow modes API (#734, #433)
- feat(inspector): move image edits panel into inspector tab
- feat(workflows): add run-time model overrides + catalogue HITL ambiguity pause (#797, #1097)
- feat(workflows): add language identification tool (#756)
- feat(workflows): chunk long text inputs in shared LLM path (#801)
- feat(workflows): add pre-run cost estimate endpoint (#735)
- feat(scripts): spawn-worker.sh — one-command tmux milestone worker (venv + worktree + agent + claim-scoped prompt)
- feat: add claim-linked searchable annotation notes in inspector (#1187)
- feat: add stage variant inspector foundation in document inspector (#1174)
- feat: add stageable paleography A/B/C chain presets (#1175)
- feat(kg): surface standalone two-column entity digest with source annotation navigation (#1191)
- feat(images): make crop operation EXIF auto-orient aware (#1386)
- feat: add split image workflow tool (#1394)
- feat: add recombine segments workflow tool (#1392)
- feat: add segment image workflow tool (#1391)
- feat: add remove background image workflow tool (#1393)
- feat: add fuzzy clean image workflow tool (#1389)
- feat: add enhance image workflow tool (#1388)
- feat: add rotate image workflow tool (#1387)
- feat: ship prepare images workflow preset (#1390)
- feat: add OCR image preparation tool (#1390)
- feat: persist weighted corroboration counts (#903)
- feat: POST /api/kg/entities/{id}/bio — LLM biography generation (#1361)
- feat: persist document read star and flag state (#1381)
- feat: add uncertainty markers for transcription low-confidence spans (#1398)
- feat: add per-document workflow provenance (#1382)
- feat(chat): report document/context retrieval counts
- feat(research): report document/context counts for KG-augmented search
- feat(research): expose KG retrieval usage telemetry in search tool
- feat(chat): return KG retrieval usage telemetry
- feat(rag): expose graph traversal knobs in chat and researcher search
- feat(claims): resolve claim or SVO to source page/span anchors (#1364)
- feat(chat): add shared graph-aware retriever for KG-augmented RAG (#1156)
- feat: add UI help tooltips + fix inspector facet buttons (#1371, #1370)
- feat(entities): add GET /api/entities/{entity_id}/biography endpoint (#1352)
- feat(kg): global corroboration persist-back + recompute endpoint (#900)
- feat(nav): wire OntologyBrowser into app sidebar as Knowledge Graph mode (#498)

**Fixes**

- fix(#1436): make search endpoints scanner-visible via inline route comments (#1436)
- fix(#1438): make chat endpoints scanner-visible via inline route comments (#1438)
- fix(#1428): make image-editing endpoints scanner-visible via explicit /api/... paths
- fix(#1346): stop WebKit scroll position resetting on PDF navigation
- fix(#1366): surface per-page entities in Document Inspector for PDF reading context
- fix(#1421): use chevron.backward/forward SF Symbols in window toolbar back/forward buttons
- fix(cli): reject empty --doc values consistently (#1348)
- fix(kg): folder catalogue writes entities/claims per page doc_id, not folder (#1403 #1404)
- fix(#1405): keep WebKit/reading pane visible when a folder is selected
- fix(tests): seed claim in test_hermeneutics_api interpretation_crud (linking validation)
- fix(tests): seed referenced claims in hermeneutics interpretation tests — new linking validation requires existing claim
- fix(inspector): add explicit return in artifactTypeSection — let-binding made body multi-statement (#343 build fix)
- fix(workflow-inspector): surface feature-gated tools explicitly (#1220)
- fix(workflows): retire legacy catalogue preset during default seeding (#720)
- fix(workflows): gate workflow table mode behind advanced views flag (#286)
- fix(ci): make OpenAPI drift check key-order-insensitive (jq -S) — pydantic/fastapi version skew was failing CI on every run with cosmetic key reordering
- fix(ci): use built-in skipif(sys.platform) to skip Quartz-only PDF tests on Linux (marker hook wasn't catching them)
- fix(ingest): skip image sidecar files during folder ingest
- fix(image-editing): offload crop processing off event loop
- fix(ci): green main — skip Quartz-only PDF-vision tests on Linux, add pytest-timeout dep, regen openapi for #1175 paleography preset endpoint
- fix(spawn-worker): codex skills use $ prefix, claude uses / — apply to start + session-end
- fix(spawn-worker): bump agent-boot wait 6s->12s so the prompt lands after codex TUI is ready
- fix: hide noisy DATES metadata facet from inspector strip (#1369)
- fix: humanize internal artifact/node names in activity viewer (#1224)
- fix: default-expand artifact bodies and enforce minimum content height (#1374)
- fix: normalize inspector attribute-strip persistence toggles (#1375)
- fix: restore classic image preview surface alongside editor (#1383)
- fix: clamp persisted PDF reading pane width bounds (#1188)
- fix(inspector): restore parent PDF page artifacts (#1366)
- fix: display workflow image edits in preview editor (#1389)
- fix: preserve diacritics explicitly in transcribe prompt (#1397)
- fix: use fresh db handle for background folder ingest (#1216)
- fix: replace app db raw delete paths with typed wrappers (#1359)
- fix: skip malformed workflow provenance rows (#1382)
- fix(rag): enforce safe bounds for graph retrieval controls
- fix(research): preserve search relevance scores via shared retriever
- fix(workflows): upgrade Translate preset to use text_translate tool (#926)
- fix(security): restore library path allowlist; use /usr/local in security tests
- fix(activity): crash-safe zombie workflow_run recovery to stop DuckDB index FATAL bricking libraries (#1362)
- fix(db): early zombie-run guard in ActivityStore._init_database (#1362)
- fix(cli): consistent --doc/-d flag for kg citations, kg claims, artifacts list (#1348)
- fix(activity): wire recover_stale_runs() into get_activity_tracker() on first library open (#1350)
- fix(vision): render PDF pages to PNG before sending to LLM vision (#670)
- fix(ingest): add cycle/depth guard to _touch_ancestor_documents (#1349)
- fix(settings): add first-run guard + race fix for \$small/\$large model slots (#1344)
- fix(workflow): fail-loud on node exception + zombie run recovery (#1347)
- fix(ingest): fail loud on loader exceptions and folder-file failures (#881)
- fix(webkit): preserve scroll position on highlight/focus/tab changes (#1346)

**Refactors**

- refactor(paths): standardize engine state dir + legacy migration (#1341)
- refactor(workflows): use typed provider metadata in node picker (#768)
- refactor(research): route source search through shared graph-aware retriever

**Docs**

- docs(constitution): add 'Iterate, never replace' HARD RULE — build on existing code, don't rewrite/start-over (per Daniel)
- docs(swiftui): DocumentCanvas design — unify image+PDF viewer/editor, two-toolbar nav, SF-symbol edit chain (#1402 #1383 #1420)
- docs(state): integration sweep complete — harvest summary + re-implement list + spawn-worker tooling
- docs(session-end): transcript-quality eval + session history
- docs(verify): Preface KG rerun — 0/0 → 50 entities/50 claims; #1344+#1347 confirmed; new DuckDB zombie-row corruption bug
- docs(analysis): docs/ + agent-work/ review reports + KG-entity-ideas investigation
- docs(plan): graph-RAG in chat retrieval design (#1156) — 3-PR staged plan for review
- docs(state): morning report — 7 fixes shipped (empty-KG chain fixed end-to-end)
- docs(state): #1346 shipped + empty-KG root-cause diagnosis (active build night)
- docs(analysis): Preface KG-vs-chapter comparison, #1346 plan, all reality-check reports

**Tests**

- test: add generated CLI GET smoke harness (#1410)
- test(mind-palace): cover spatial connections and viewport routes (#512)
- test: shrink CLI wiring allowlist (#1409)
- test(search): remove unused imports in search explain route tests
- test(batch): cover control routes and failed-item detail (#492)
- test(chains): cover execute/status/cancel API flow (#491)
- test(workflows): cover editor import/prompt/create-node routes (#489)
- test(workflows): add release-gate coverage for rewrite/files tools (#490)
- test(workflow-execution): add release-gate API contract checks (#488)
- test(workflows): smoke-run all default preset graphs in e2e harness (#1287)
- test(workflows): assert cached flag on file_complete rerun (#708)
- test(claims): harden resolve-source selection behavior
- test(rag): lock graph knob behavior in shared retriever
- test(cli): fix stale kg-entities tests to match library-wide contract (#1351)

**Build**

- build: declare opencv image dependency (#1393)

**CI**

- ci: run only on main + PRs (not every branch) — stop ms/* worker pushes burning billing runs + spamming failures
- ci: download spaCy en + es models before pytest

**Chore**

- chore(wiring): allowlist model-comparison/compare-node/apply (#1268) — SwiftUI wiring backlog
- chore(wiring): allowlist 2 new backend endpoints (#1373 timeline dating, #1356 KG review summary) — SwiftUI wiring is backlog
- chore(wiring): allowlist new thread-pause endpoint (#1226) as frontend wiring backlog
- chore(integrate): register kg view files + sync schema after kg re-merge
- chore(openapi): sync schema after ms/settings-providers merge
- chore(integrate): register WorkflowRunProviderCache.swift + sync schema after ms/workflows merge
- chore(contracts): sync endpoints.json fixture with regenerated schema (paleography/bio/etc.)
- chore(xcode): register EntityDigestView.swift orphan referenced by #1191
- chore(xcode): register StageVariantInspector.swift (#1174)
- chore(openapi): regen schema for #1361 bio + #903 weighted support + #1386 auto_orient — fix CI drift
- chore(manager): image-tools suite merged (#1387-1394); update STATE re: remaining reviewer/Xcode work
- chore(manager): merge #1361 entity-bio + #903 corroboration; defer codex/1386 image-tools to integrator
- chore(manager): integration session — worker/1156 + backend/1382 merged; old-branch re-impl plan in STATE.md
- chore: align default transcription workflows to uncertainty markers (#1398)
- chore(session-end): record worker/1156 handoff summary
- chore(rag): add structured retrieval diagnostics logging
- chore(session-end): MEMORY lessons (#1362 rebuild, WindowServer GPU) + STATE next-session entry
- chore(deps): bump ws to 8.20.1 (Dependabot advisory #17)
- chore(openapi): regen for #900 triangulation recompute endpoint (NodeDef stays SPLIT)
- chore(docs): remove stale/superseded planning docs (superseded by GitHub issues + current state)

### 2026-05-30

**Features**

- feat: Mind Palace Phase 3 — full-library + link types + visible links (x-platform code paths) (#1297 follow-up)
- feat: full-featured MCP + scene_render hook for vision-multimodal agents
- feat: translation workflow + DeepL provider
- feat: edit and delete knowledge claims (CRUD + UI) (#1258)
- feat: bidirectional scroll sync between WebKit transcript and PDF (#1253)
- feat: promote mind_palace + research_agents to core tier (#1298)
- feat: MCP server follow-ups — notes tools + typed returns + CLI parity (#1301)
- feat: Cotypist-style onboarding step cards (#1289)
- feat: first-run onboarding window with step cards (#1300)
- feat: Mind Palace Phase 2 — drag-to-move + viewport persistence (#1297)
- feat: programmatic book structure (chapters/sections/subsections) (#1279)

**Fixes**

- fix(openapi): pin NodeDef emission to deterministic SPLIT form (#1275)
- fix(build): WorkflowServiceGenerated uses NodeDefInput/NodeDefOutput to match split openapi
- fix: revert NodeDef split — unify NodeDefInput/NodeDefOutput → NodeDef (#1275)
- fix: allow /tmp and /private/tmp in library path allowlist (#1275 adjacent)
- fix(build): resolve post-merge Swift trunk-red — concurrency, TextureResource, NodeDef split, ContentView complexity
- fix(build): resolve trunk-red Swift compile errors across KG + view-mode surfaces
- fix: register KGFocusState.swift in pbxproj (missing from #1307 merge)

**Docs**

- docs(state): overnight sweep complete — 18/18 milestones reality-checked, 23 verified-done closed; morning report
- docs(state): overnight reality-check tally — 9 milestones swept, 19 verified-done closed, #1345 P1 storm + #1344 root-caused
- docs(state): autonomous session checkpoint — trunk-red recovered, merges + audits done, build green
- docs(audit): milestone-audit proposals for all 17 content milestones (manager GH triage)
- docs(state): trunk-red recovery notes + RAM/venv corrections (manager session)
- docs(gh-conventions): PR policy (skip by default, gate via CI on every push), tiered CI strategy, GH-issues-not-filesystem rule, open-source self-doc plan
- docs(gh-conventions): clarify Documentation (end-user) vs Developer Experience (contributors/agents — docs+tooling) vs Website (publishes Documentation as static site)
- docs(gh-conventions): split Documentation (writing for humans) from Developer Experience (tooling); 20 active milestones
- docs(gh-conventions): final 23-label set (collapsed type:qa/question to status, dropped status:ready/done/in-progress, merged legacy-reenable→roadmap, dropped release-gate/duplicate/wontfix/etc)
- docs(gh-conventions): remove migration scaffolding
- docs(dispatch): bugtriage §8-10 — label backfill, Importers vs Source Archives, release-flow rule
- docs(gh-conventions): split Importers (tools) from Source Archives (specific collections); fix #520 Sparkle → App Shell; #296 → roadmap
- docs(gh-conventions): consolidate to 17 milestones — merge Hermeneutics+NER→KG, Translation→Workflows, PDF Viewer→Library&Reading Surface; clarify Chat (graph-RAG, LLM comparison) vs Researcher
- docs(gh-conventions): revised milestone set — 21 active, endpoint/UI split + 4 new (PDF Viewer, App Shell, CLI, Developer Experience), Onboarding → Library & Reading Surface, EPE dissolved
- docs(dispatch): f_docs lane brief — end-user docs with screenshots via computer-use MCP
- docs(dispatch): bugtriage §7 — license to add new feature milestones when needed
- docs(dispatch): bugtriage §6 — re-file ~593 closed issues + delete version milestones + clean up legacy labels
- docs(gh-conventions): move to agent-workflow/, abstract human operator, tier:* over owner:*
- docs(gh-conventions): canonical milestone + label set, branch + lane discipline
- docs(dispatch): bugtriage — auto-add ALL open issues to Project #5 first
- docs(dispatch): integrator brief expanded to drain all lane backlog (10 branches)
- docs(dispatch): integrator/reviewer/planner/bugtriage briefs + handoff additions
- docs(handoff): add Phase 0 — trunk-red + Opus merge errors for integrator lane
- docs(handoff): manager-resume brief synthesizing the 4 DONE lane proposals
- docs: Mind Palace Phase 3 design — spatial library + LinkType taxonomy + x-platform plan (#1297 follow-up)

**Tests**

- test: skip CrossLanguageGateTests on Xcode Cloud — Python gate lives in GitHub Actions Linux (.github/workflows/ci.yml). Avoids 5-10min pre-action venv setup on Mac runner.

**CI**

- ci: GH Actions Python gate — ruff + pytest (no embedding) + OpenAPI drift check on every push

**Chore**

- chore(bundle-id): com.fichero.fichero → app.fichero.fichero across 119 files
- chore: gitignore .kreuzberg/ cache (proper fix tracked in new issue)
- chore(session-end): GH hygiene marathon — 0.0.2→main, worktree path, milestones/labels canonical
- chore(scripts): use script-relative path in create-issues.py (drop /Users/danieltubb/code/fichero-0.0.2 hardcode)
- chore(branch): 0.0.2 → main as trunk; archive-main-2026-05-30 preserves old main
- chore(session-end): checkpoint state
- chore(session-end): checkpoint state + archive ~40-issue marathon to HISTORY.md
- chore: default Xcode Run scheme to FICHERO_FEATURE_TIER=dev so all features show in testing
- chore: openapi sync after batch 4
- chore: openapi sync after batch 3

### 2026-05-29

**Features**

- feat: honor default font size in KG claim card body text (#1323)
- feat: surface RealityKit view as folder/workspace view tab (#1321)
- feat: force-directed KG graph layout instead of chord diagram (#1320)
- feat: bucket date entities into collapsed section in KG browser (#1295)
- feat: CLI parity for KG/inspector ops (#1318)
- feat: cross-view focus binding for KG (v3) (#1307)
- feat: unify workspace into folder model; views available per folder (#1313)
- feat: statements + artifacts fetch buttons in inspector KG section (#1312)
- feat: citations_extract workflow tool + CLI (#1316)
- feat: page-image textures on RealityKit Mind Palace cards + tap selection (#1309)
- feat: split_chapters workflow tool + CLI (#1315)
- feat: show-all/load-more for truncated KG groups in inspector (#1311)
- feat: collapse 3 Swift KG read paths to single /documents/{id}/knowledge-graph endpoint (#1304)
- feat: $medium cloud tier in structured-output fallback chain (#1308)
- feat: re-enable Knowledge Graph as a sidebar nav target (mirrors mindPalace)
- feat: attribute KG entities at page level with rollup to parent
- feat: programmatic clean_text without LLM to fix context_overflow

**Fixes**

- fix: RealityKit Mind Palace renders page images + supports camera interaction (#1322)
- fix: KG focus-binding feedback loop — granular observation, drive-direction guard (#1319)
- fix: defer protected requests until auth token settles (no more 403 bursts) (#1283)
- fix: populate entity_ids[] on keyword claims (#1296)
- fix: preserve KG view state across navigation (v3) (#1306)
- fix: clickable source-page link in OntologyBrowser entity detail (#1305)
- fix: provider-aware LLM fallback log — local providers are free, not PAID remote
- fix: unblock SwiftUI build — single NodeDef schema + swiftlint sweep (#1302)
- fix: label digital-PDF text extraction as pdf_text not Apple Vision

**Refactors**

- refactor: retire KG sidebar mode (use inspector + WebKit + content-area path instead) (#1302)
- refactor: remove inspector Map tab (redundant with WebKit graph) (#1310)

**Docs**

- docs: SwiftUI endpoint coverage audit + missing wrappers (#1288)

**Tests**

- test: verify SVO claim rendering in inspector after #1304 collapse (#1314)

**Chore**

- chore: openapi sync after wave-5 merges
- chore: openapi sync after #1316+#1309
- chore: sync openapi.json after #1308 + #1305 merges
- chore: sync openapi.json after lane merges (rollup + clean_text + provenance)

### 2026-05-28

**Features**

- feat: add mind palace note MCP tools (#1301)
- feat: add document KG visualizations (#1257)
- feat: wire KG WebKit source navigation (#1302)
- feat: promote all dev-tier routers to release for 0.0.2 (#1298)
- feat: extract book index topics (#1278)
- feat: add oMLX provider
- feat(mcp): Mind Palace arrangement + KG read tools for the MCP server (#1269)
- feat: complete claim editing backend (#1258)
- feat: add citation usage extractor (#1277)
- feat(book-structure): add TOC-backed structure nodes (#1279)
- feat(mcp): expose Mind Palace tools so the AI can drive the palace (#1269)

**Fixes**

- fix: refresh folder timestamps during ingest (#1217)
- fix: sync KG WebKit scrolling with PDF pages (#1253)
- fix: add toolbar navigation history (#1261)
- fix: canonicalize NodeDef openapi export (#1275) + match Swift wrapper to split
- fix: canonicalize NodeDef OpenAPI export (#1275)
- fix(swift): handle NodeDef→NodeDefInput/Output split after oMLX openapi regen (#1298)
- fix: hide bare dates from default entity browser (#1295)
- fix: refresh startup auth context before protected requests (#1283)
- fix(llm): surface provider quota errors and fallback overrides
- fix(research): repair 4 FE↔BE wiring bugs found in post-merge review
- fix(research): integrate Researcher with Mind Palace trunk

**Docs**

- docs(state): KG-gen root cause — extraction model capability (Apple fails schema, OpenRouter capped)
- docs(state): checkpoint — integration+NodeDef-fix done; KG-gen needs single-page retry
- docs(state): overnight progress checkpoint — tier promotion + #1302 + KG-gen in flight
- docs: document ACENET remote backend tunnel (#1239)
- docs: audit backend routes hidden from SwiftUI (#1288)
- docs(state): overnight KG-generation goal on book chapters + guardrails (free/local model)
- docs(state): integrate-first priority, 15-min ticks, per-lane reconciliation notes
- docs(state): overnight integration runbook + MCP reconciliation decision
- docs(state): integration queue + promote-to-release directive + oMLX wiring
- docs(state): lane reconfig — Codex Pro live, 3 book-extraction tasks dispatched, Claude lanes parked till Saturday
- docs(state): late-morning handoff — Researcher merged+fixed, Mind Palace MCP shipped

**Tests**

- test(mind-palace): self-contained #Preview for SpatialNodeInspector (#1299)

**Chore**

- chore(session-end): checkpoint STATE/HISTORY handoff

### 2026-05-27

**Features**

- feat: wire Researcher mode — SidebarMode, nav, FeatureManager, env injection
- feat: ResearchModels, ResearchService, and Research pane views
- feat: browser-save endpoint + ResearchProject.library_destination_folder_id
- feat: Mind Palace full A1 — sidebar mode + RealityKit 3D canvas + 2D toggle
- feat: Mind Palace spatial space — Phase 1 (frontend, read-only, gated off)
- feat(workflows): add Translate + Translate Review tools + 2 presets (#926)
- feat(workflows): add Clean Up Text tool + preset
- feat: annotate image region from marquee selection (#1276)
- feat: Annotations tab in Document Inspector — list/add/delete + reveal (#1276)
- feat: add slipbox import CLI (#1231)
- feat: Annotation model + CRUD endpoints (#914)
- feat: AnnotationService Swift wrapper + DocumentAnnotation model (#1276)
- feat: rubber-band marquee crop + batch-apply across selection (#1265)
- feat: prev/next image navigation in the editor (#1265)
- feat: image editor surface — edit-chain controls + original/edited toggle (#469)
- feat: ImageEditingService wrapper + edit-chain model (#469 #1265)
- feat: add model comparison interface backend (#1268)
- feat(kg): EntityMergeSheet + EntitySplitSheet wired into OntologyBrowser (#1135)
- feat(kg): EditClaimSheet + claim update notification (#1135)
- feat(kg): add Map visualization to OntologyBrowser (#1267)
- feat: image segment (#468)
- feat: color-code KG entities vs search terms (#1052)
- feat(kg): add Timeline visualization to OntologyBrowser (#1267)
- feat: return rich search hit anchors (#1270)
- feat: image remove-background (#467)

**Fixes**

- fix(mind-palace): exhaustive viewMode switches + ViewportSaveRequest arg order
- fix(tests): update e2e harness assertions for #1291 single-file catalogue target (#1291 #1292)
- fix: #1294 — remove per-file artifact polling to eliminate GET loop
- fix: artifact provenance records source document, not model (#1292)
- fix: Stage-2 progress labels entities correctly, not as files (#1293)
- fix(import): route menu/file-picker import to Inbox, not invisible root
- fix(settings): filter Defaults model pickers by capability (#1290)
- fix(providers): derive cloud-model capabilities from registry (#1290)
- fix(kg): persist KG rows in two-stage catalogue path (#1285)
- fix: emit catalogue extraction progress events (#1281)
- fix: page status stays in-progress until whole pipeline completes (#1282)
- fix: Page Content pane top-aligned + full-height, drop redundant title (#1286)
- fix: flat macOS-style transcription render — drop cream gradient + rounded card (#1280)
- fix: use chat_structured_with_fallback in oneshot extract_all (#1284)
- fix: kg_writer is a no-op when extract_all writes KG inline (#1285)
- fix: guarantee NodeDef/EdgeDef as named OpenAPI components (#1275)
- fix: speed up slipbox Tinderbox text decoding (#1231)
- fix: persist claims from all docs when entity dedupes (#1266 regression)
- fix(backend): re-point claim entity_ids during entity merge (#1135)

**Docs**

- docs(security): document Researcher data-diode trust boundary
- docs: addenda — Mind Palace room↔sources binding + Researcher per-project tracking
- docs: Mind Palace + Researcher wireframes & design proposal
- docs: planner researcher + mind-palace feature-enablement proposal
- docs(audit): KG extraction quality audit — #1285 persistence verified
- docs(history): morning bug-fix batch + endpoint audit (#1285/#1284/#1281/#1282/#1280/#1286/#1288)
- docs: endpoint↔frontend coverage audit (codex53, #1288)
- docs: consolidate 0.0.2 landing — HISTORY + STATE (overnight+morning sprint)
- docs: book-structure extraction design — citation-usage, index→topics, chapters (f_planner)
- docs(state): 2026-05-27 morning handoff — merged suite, annotations sprint, Codex cap, rules

**Tests**

- test(kg): add test asserting keyword claims have non-empty entity_ids (#1296)
- test: use fraction bbox in crop_image test (matches the annotation contract)
- test: 18 unit tests for /api/annotations CRUD + crop helpers (#914)
- test(backend): route tests for entity curation merge/split/audit (#1135)

**Chore**

- chore: regen openapi for Artifact.source_document_id (#1292)
- chore(openapi): regenerate after #1268 merge (NodeDef stable via #1275 fix)
- chore(openapi): regenerate after annotations merge — restore NodeDef (#1275)
- chore(openapi): regenerate schema + Swift bindings for annotations (#914)
- chore(openapi): regenerate model comparison schema (#1268)
- chore(openapi): regenerate schema + Swift bindings after codex53 merge (#467 #468)
- chore(openapi): regenerate schema + Swift bindings after gpt-mini merge (#1270)
- chore(openapi): regenerate after #1266 merge — restore NodeDef (flaky emission)

### 2026-05-26

**Features**

- feat: image enhance operation (#466)
- feat: image rotate operation (#465)
- feat: image crop operation (#464)
- feat: xlsx records import with configurable column mapping (#1237)
- feat: add document export endpoints (#472)
- feat: per-document progress logging in extract_all (#1251)
- feat: researcher phase 1 (#1256)
- feat: image edit-chain storage and preview endpoint (#462, #463)
- feat: extend text_reflow with optional AI-pass + realistic fixtures (#1260)
- feat: per-document notes (#1259)
- feat: text reflow/cleanup tool (#1260)
- feat: inspector toggle in main toolbar + filterable attribute strip (#1229)
- feat: wire entity-type registry into extraction runtime (#1240)

**Fixes**

- fix: route image-only PDF pages to Apple OCR (#1274)
- fix: keep extract_all responsive during large PDFs (#1273)
- fix: regenerate OpenAPI schema — restore dropped NodeDef component (Swift build break)
- fix: surface all sources in inspector Content tab attribute strip (#1246)
- fix: trim redundant labels in reading surface (#1244)
- fix: clamp content-list pane min width to view-mode rail width (#1243)
- fix: require _EntitiesOnly fields in Apple grammar schema (#1272)
- fix: order whole-PDF transcript artifacts by page index (#1271)
- fix: strip RTF markup from page_content (#1252)
- fix: re-enable chat model comparison routes (#1262)
- fix: Page Content inspector panel always-expanded, flows below attributes (#1245)
- fix: include page-child claims in document knowledge view (#1249)
- fix: render parent PDF for page docs in widescreen center viewer (#1247)
- fix: guardrail fallback + incremental KG writes in two-stage (#1254 #1263)
- fix: two-stage extraction now writes KG rows (#1248)
- fix: address review feedback on #1240 registry extraction
- fix: repair WebKit knowledge pane crashes + reading-layout regressions (#1228)

**Docs**

- docs: append post-fix KG confirmation to PDF fidelity audit (8 entities on salas2015)
- docs(state): overnight progress ledger — 6 merges landed, KG silent-failure fix, lane status
- docs: PDF fidelity audit + KG evidential-model design (overnight findings)
- docs(state): overnight autonomous handoff — pace ~12h, hourly ticks, throttle lanes, merge backlog
- docs: researcher audit (#1256)
- docs(state): manager session status — #1229 + #1240 merged, #1230 in flight, imports held for Daniel
- docs: drop dangling docs/agent-workflow/TODO.md references
- docs: delete AUTONOMOUS-LOOP.md — superseded by autoloop README
- docs: fix CONSTITUTION typos + frame versioning as direction not state
- docs: tighten CONSTITUTION.md — leaner product framing
- docs: fix .claude/agent-briefing.md — dead paths, de-duplicate rules
- docs: rewrite USER.md — Daniel as creative director, focused on Fichero
- docs: delete SOUL.md — folded into CONSTITUTION, remove dangling refs
- docs: trim docs/CLAUDE.md — strip rotting stats, de-duplicate, fix contradictions
- docs: trim SOUL.md — keep the soul-level never, defer operational rules
- docs: trim USER.md — condense research stack, de-duplicate constraints
- docs: merge VISION into CONSTITUTION, delete VISION.md
- docs: trim AGENTS.md — remove stale refs and duplication

**Tests**

- test: add FicheroUITests target + launch & view-mode smoke tests (#1230)

**Style**

- style: unify reading-surface selectors + system-themed knowledge HTML (#1228)

**Chore**

- chore(openapi): regenerate schema + Swift bindings after codex53 lane merge (#1259 #462 #463 #464 #465 #466)
- chore(openapi): regenerate schema + Swift bindings after gpt-mini lane merge (#1274 #1256)
- chore(openapi): regenerate schema + Swift bindings after gpt lane merge (#1262 #472 #1273)
- chore(opus): session-end status — reading-surface sweep (#1247/#1245/#1243), #1230 held
- chore(session-end): record sonnet branch queue status
- chore: drop stale root artifacts, add image-editing epic plan
- chore: drop stale autoloop log, gitignore loop-logs/

### 2026-05-25

**Features**

- feat: add document knowledge web pane (#1228)
- feat: finish PDF loupe and workflow updates
- feat: PDF loupe overlay — Tasks 3–6 of #928
- feat: add loupe state management to PDFPageView
- feat: implement #874 — User-extensible entity types (registry + dynamic extraction)
- feat: implement user-extensible epistemic statuses and claim kinds registries (#1102)
- feat: filter audit log by document and artifact (#1089)
- feat: add first-class references storage (#1103)
- feat: add canonical bibliography sidecar ingest (#1101)
- feat: add OCR/HTR picker models (#1145)
- feat: add corpus search to transcription review (#1179)
- feat: add KG paragraph rendering endpoint (#1111)
- feat: add explicit kg writer workflow node (#1115)
- feat: add multi-provider NER abstraction (#1118)
- feat: add support for .iffy.json sidecar files during ingestion (#1085)
- feat: wire DisplayAttributesStrip into document inspector header (#1180)
- feat: add entity digest export endpoint (#1198)
- feat: claim row click syncs PDF to source page (#1204)
- feat: wire biography prose view into claims section (#1202)
- feat(nav): add Cmd+Shift+' forward shortcut (#1186)
- feat(nav): back/forward history in KG entity browser (#1186)
- feat(ui): JSON artifact structured inspector with View Raw toggle (#1181)
- feat: promote chains router to core tier; enable workflow chains by default (#1151)
- feat(swift): Phase 4 entity inspector UI — source groups view + NodeDef schema sync (#1183)
- feat(cli): add entity inspector command + client method (#1183)
- feat(gate): add OpenAPI freshness check to verify_python.sh; sync stale NodeDef-Input schema (#1201)

**Fixes**

- fix: harden provider validation and failure handling (#241)
- fix: normalize toolbar/header heights across panes to 44pt (#1213)
- fix: pause workflow on provider quota errors and fix activity enum mismatch (#1222)
- fix: map Activity Viewer file paths to document names (#1224)
- fix: inspector content pane now uses full available height (#1218)
- fix: inject ClaimFocusState environment object in DocumentInspector (#1210)
- fix: normalize transcribe language locales (#1227)
- fix: add overlap context to handle NER across page breaks (#971)
- fix: wire workflow interrupt hooks (#1097)
- fix: make digest 400 guard reachable (#1198)
- fix: raise search min_score default 0.45→0.55 to cut semantic noise floor (#1054)
- fix: cap runaway NER output (#1207)
- fix: expose entity digest API (#1198)
- fix: add per-step timing stats card to Activity Overview (#1048)
- fix: surface vision model errors as activity-log warnings instead of silent empty (#1208)
- fix: replace flat file list with doc×step grid in ActivityOverviewView (#1045)
- fix: mark files/folder query port required=False — workflow validation regression (#1118/#1179)
- fix: isolate test db path per pytest process (#1206)
- fix: override digest dependency in tests (#1198)
- fix: correct head command syntax in sync_openapi_schema.sh (#1205)
- fix: expose entity digest contract (#1198)
- fix: delete dead generated Python CLI client + its regen step (#1205)
- fix(openapi): remove orphan NodeDef-Input schema from both contracts and Swift client
- fix(ui): propagate maxHeight:.infinity through DocumentInspector to stop layout jumps (#1180)
- fix(scripts): strip redundant fichero/ prefix in add-swift-file.rb group navigation

**Refactors**

- refactor(swift): split QuickLookComponents.swift — extract preview + swipe views
- refactor(swift): split APIClient.swift + fix NodeDef schema variant references
- refactor: split PDFThumbnailView.swift (844→99 lines) into focused files
- refactor: split EntityDetailView.swift into focused extensions (file_length)

**Docs**

- docs: record codex backend handoff
- docs: record pronoun coreference verification
- docs: refresh backend queue verification note

**Tests**

- test: retrofit unit tests for #1102, #1198, #1208, #1179
- test: unit tests for library entity types route (#874)
- test: add unit tests for quota error detection and activity enum safety (#1222)
- test: pin catalogue-each fan-out preset (#1098)

**Style**

- style: split APIClient.swift (file_length) + fix ClaimSummaryCard access
- style: split ClaimSummaryCardView.swift (file_length)
- style: split LibraryView+ColumnConfig.swift (file_length)
- style: split LibraryViewComponents + LibraryView+DisplayModes (file_length)
- style: split AISettingsView.swift (file_length) — extract tabs + helpers
- style: fix W293 blank-line whitespace
- style: split ContentView+ViewBuilders.swift (file_length) — reading layout + helper views
- style: split ContentView+Actions.swift (file_length) — extract workflow actions
- style: fix W605 invalid escape sequences in docstrings
- style: replace large 3-member tuples with named structs (large_tuple)
- style: replace string-based KVO with NSKeyValueObservation in AttributedTextEditor
- style: fix multiple_closures_with_trailing_closure in SVO chip buttons
- style: fix identifier_name violations — wf→workflow, op→mergeOp

**Chore**

- chore(session-end): record coordination state
- chore: remove stray done-note accidentally included in #241 cherry-pick
- chore(session-end): PDF loupe Tasks 3–6 complete, Task 7 awaiting manual test
- chore(session-end): PDF loupe Task 1 complete, cursor tracking ready for Task 2
- chore(session-end): update STATE.md — #1224 complete, waiting for next assignment
- chore: ruff fix + openapi regen + archive processed done notes
- chore(session-end): file_length cleanup complete + NodeDef fix — 2026-05-25
- chore: regen OpenAPI schema — digest endpoint now in schema (#1198)
- chore: regen OpenAPI schema + Swift client — kg_render paragraph endpoint (#1111)
- chore(state): post-integration handoff — both lanes merged, 2 fix-forward + #1207 open
- chore(state): consolidation plan for integration sweep
- chore(session-end): frontend lane pause — 8 closed with evidence, #1180 fixed, #1045/#1048/#928 deferred
- chore(session-end): update history and state after #1111
- chore(session-end): update state after completing #1205 and #1085
- chore(session-end): manager handoff — startup check-in on codex/pi worker queues + post-merge serial verify
- chore(state): manager gate handoff — codex #1198 + pi #1205 mid-gate (1 small fix each)
- chore(session-end): manager entry point, worktree+MCP topology, durable lessons
- chore(state): durable agent-named worktree desks (fichero-codex / fichero-pi)
- chore(state): worktree topology + manager merge/review protocol; record for memory-runout
- chore(state): close #1147/#1148 (verified), file #1205 cleanup follow-up
- chore(state): manager triage — label 5 orphan issues, flag #1147/#1148 verify-and-close
- chore(session-end): update STATE/HISTORY — release checklist next, multi-agent split active
- chore: add .ai/inbox/ for inter-agent messaging
- chore(state): split agent strategy — frontend Claude / backend Codex, issues labelled
- chore(openapi): restore NodeDef-Input schema — Pydantic v2 artifact from field_validator(mode=before)
- chore(openapi): remove NodeDef-Input variant re-introduced by chains sync
- chore(openapi): sync schema after promoting chains router to core tier (#1151)
- chore(session-end): integrate overnight 4-phase plan into STATE/HISTORY/MEMORY
- chore(state): session-end — all 4 phases complete, branch clean
- chore(openapi): sync Swift client openapi.json — remove stale NodeDef-Input variant (#1201)

### 2026-05-24

**Features**

- feat: editable page content pane alongside PDF viewer (#1188)
- feat(inspector): add Map tab to document inspector for page-scoped KG graph (#1196)
- feat: enhance ClaimFocusState with syncClaimFocus method for bidirectional three-pane sync (#1197)
- feat(cli): add entity commands list, digest, biography, claims (#1193)
- feat: add claim focus integration to DocumentInspector for three-pane sync (#1197)
- feat: ClaimFocusState + partial bidirectional claim sync (#1197)
- feat: KG inspector Text mode — dense SVO prose digest (#1190)
- feat: five-pane reading layout — page list | PDF | content | inspector (#1189)
- feat: KG extractor: always include preposition in svo_verb (#1192)
- feat: persistent inspector layout — lift inspector to window-level HStack (#1199)
- feat: KnowledgeClaim claim_location/temporal_context/claim_speaker fields + entity platform prototypes (#1185)
- feat: entity platform prototypes + GitHub issues + autoloop queue
- feat: KG entity row visual polish + OCR noise suppression (#1168)

**Fixes**

- fix: remove duplicate entity app import in CLI
- fix: swiftlint implicit_optional_initialization + trailing_newline in ClaimFocusState/FeatureManager
- fix: review-correct worker output for #1193/#1197

**Docs**

- docs(state): align phased execution notes
- docs: prune stale planning docs + document the verify gate
- docs: replace stale MCP tool catalogue with a durable pointer
- docs: refresh agent docs to match 0.0.2 reality
- docs: dedupe jCodemunch policy from project CLAUDE.md
- docs: add xcodeproj-based new Swift file registration workflow

**Style**

- style: batch lint cleanup for search and inspector views
- style: batch lint cleanup for menu and workflow views
- style: clear ViewMenuCommands orphaned doc comment
- style: clear WorkflowStore orphaned doc comment
- style: normalize speaker comparison file endings
- style: clean EntityDigestView lint warnings
- style: fix ontology browser lint warning

**Chore**

- chore(state): sequence next session — deps → swiftlint → #1201 → KG entity library
- chore(session-end): STATE/MEMORY/HISTORY for #1188 + docs-hygiene sessions
- chore(session-end): update STATE + HISTORY for direct-Claude session
- chore(session-end): update STATE + HISTORY
- chore(session-end): checkpoint state
- chore(autoloop): reset #1194 — worker didn't finish
- chore(autoloop): mark #1195 done — committed by worker as 14505e85
- chore(autoloop): reset #1195 — worker didn't finish
- chore(cascade): #1196 verified already implemented
- chore(cascade): #1197 verified already implemented
- chore(cascade): mark #1198 blocked
- chore(cascade): #1200 flagged for review (cascade-review/1200-1779657499)
- chore(autoloop): reset #1200 — worker didn't finish
- chore(cascade): mark #710 blocked
- chore(cascade): #711 verified already implemented
- chore(cascade): #712 verified already implemented
- chore(cascade): mark #714 blocked
- chore(cascade): mark #958 blocked
- chore(cascade): #1193 verified already implemented
- chore: update STATE.md and HISTORY.md for session
- chore(session-end): checkpoint state — #1199/#1189/#1190 shipped, autoloop on openrouter
- chore: verify #1185 already shipped — close as fixed-but-not-closed
- chore(session-end): checkpoint state — entity platform prototypes + #1185 done

### 2026-05-23

**Features**

- feat: entity claim count badges + WorkflowEdge routeKey/routeMap sync (#1173)
- feat: batch verification harness for paleography pipeline (#1177)
- feat: pronoun antecedent annotation in two-stage extraction (#1173)
- feat: add Transcribe (Auto-Detect) workflow with route_map branching (#1178)
- feat: upgrade paleography + HTR presets to two-pass workflow (#1178)
- feat: add transcription profile workflows + classify_script tool (#1178)

**Fixes**

- fix: swallow CancellationError in artifact+KG inspector load (#1167)
- fix: auto-enable two-stage extraction for Apple + fix Stage 2 context truncation (#1172)
- fix: passthrough uses PDF text layer for absent or truncated transcription (#1170)
- fix: isolate catalogue narrative failure from successful KG extraction (#1169)

**Chore**

- chore: remove deprecated ast.Num/Str/NameConstant aliases from chaining.py
- chore(session-end): checkpoint state

### 2026-05-22

**Features**

- feat: add two-stage extraction for extract_all (issue #1172)

**Fixes**

- fix: defer sidebar tap fallback selection (#1165)
- fix: recover catalogue text inputs (#1166)
- fix: defer PDF page selection callbacks (#1164)
- fix: defer library API loads until backend ready (#1163)
- fix: reduce sidebar focused value churn (#1162)
- fix: upgrade liquidjs to >=10.25.7 for CVE-2026-41311

**Chore**

- chore(session-end): record autoloop handoff
- chore(autoloop): reset stale in_progress #958
- chore(cascade): mark #715 blocked
- chore: update STATE.md with completed fixes
- chore(cascade): #716 verified already implemented
- chore(cascade): mark #717 blocked
- chore(cascade): #718 verified already implemented
- chore(cascade): mark #719 blocked
- chore(cascade): #720 verified already implemented
- chore(cascade): #721 verified already implemented
- chore(cascade): mark #733 blocked
- chore(cascade): mark #734 blocked
- chore(cascade): mark #736 blocked
- chore(cascade): mark #737 blocked
- chore(cascade): mark #738 blocked
- chore(cascade): mark #739 blocked
- chore(cascade): mark #740 blocked
- chore(cascade): mark #741 blocked
- chore(cascade): mark #744 blocked
- chore(cascade): mark #751 blocked
- chore(cascade): mark #752 blocked
- chore(cascade): mark #753 blocked
- chore(cascade): #754 verified already implemented
- chore(cascade): mark #755 blocked
- chore(cascade): mark #756 blocked
- chore(cascade): mark #760 blocked
- chore(cascade): #799 verified already implemented
- chore(cascade): mark #801 blocked
- chore(cascade): mark #821 blocked
- chore(cascade): mark #854 blocked
- chore(cascade): mark #875 blocked
- chore(cascade): mark #876 blocked
- chore(cascade): mark #877 blocked
- chore(cascade): mark #878 blocked
- chore(cascade): #902 verified already implemented
- chore(cascade): mark #924 blocked
- chore(cascade): mark #938 blocked
- chore(cascade): mark #968 blocked
- chore(cascade): mark #969 blocked
- chore(cascade): mark #970 blocked
- chore(cascade): mark #972 blocked
- chore(cascade): mark #973 blocked
- chore(cascade): #974 verified already implemented
- chore(cascade): mark #975 blocked
- chore(cascade): #1072 verified already implemented
- chore(cascade): mark #1089 blocked
- chore(cascade): mark #1090 blocked
- chore(cascade): mark #1091 blocked
- chore(cascade): mark #1092 blocked
- chore(cascade): mark #1093 blocked
- chore(cascade): mark #1094 blocked
- chore(cascade): mark #1095 blocked
- chore(cascade): #1098 verified already implemented
- chore(cascade): mark #1100 blocked
- chore(cascade): mark #1103 blocked
- chore(cascade): mark #1115 blocked
- chore(cascade): mark #1118 blocked
- chore(cascade): #1124 verified already implemented

### 2026-05-21

**Features**

- feat: add document_id filter to KG entities endpoint for source-scoped aggregation (#1071)

**Fixes**

- fix: add render_top_entity formatter for CLI entity top command
- fix: update STATE.md with sidebar drag crash blocker (#713)
- fix: correct DocumentStore init parameter label in contract tests
- fix: swiftlint config paths for current project structure
- fix: correct DocumentListResponse envelope in all DocumentStore methods, add contract tests
- fix: decode DocumentListResponse envelope correctly in loadCollections and loadChildren

**Chore**

- chore(cascade): mark #1133 blocked
- chore(cascade): mark #1135 blocked
- chore(cascade): mark #1142 blocked
- chore(cascade): #1144 verified already implemented
- chore(cascade): mark #1145 blocked
- chore(cascade): mark #1146 blocked
- chore(cascade): mark #1147 blocked
- chore(cascade): mark #1148 blocked
- chore(session-end): update state after DocumentListResponse fix
- chore: remove obsolete CONTINUE.md
- chore(cascade): mark #1101 blocked
- chore(cascade): mark #926 blocked
- chore(cascade): mark #1059 blocked
- chore(cascade): #916 verified already implemented
- chore(cascade): mark #1102 blocked
- chore(cascade): mark #874 blocked
- chore(cascade): mark #1032 blocked
- chore(cascade): mark #928 blocked
- chore(cascade): #868 verified already implemented
- chore(cascade): mark #1111 blocked
- chore(cascade): mark #1044 blocked
- chore(cascade): mark #1085 blocked
- chore(cascade): mark #732 blocked
- chore(cascade): mark #1052 blocked
- chore(cascade): mark #735 blocked
- chore(cascade): mark #797 done — committed by worker
- chore(cascade): #768 verified already implemented
- chore: update STATE.md — verification gate complete, cascade loop ready

### 2026-05-20

**Features**

- feat: CrossLanguageGateTests + verify_all.sh — ⌘U gates the whole product

**Fixes**

- fix: update hermeneutics test assertions for envelope responses (refs #1149)
- fix: hermeneutics suggest_interpretations returns envelope not bare list
- fix: provide valid response shapes in mcp_server mock handlers
- fix: update default-workflows idempotency test for current preset names
- fix: update settings reset test for factory-default re-seed behavior
- fix: update integration test envelope assertions
- fix: update test_sources.py envelope assertions (refs #1155)
- fix: CLI 'workflow run --wait' never detected completion (envelope drift)
- fix: save_claim accepts svo_subject/svo_verb/svo_object (KG claim-write regression)
- fix(#1149): envelope-consistency sweep — providers/search/chat/models (final)

**Docs**

- docs: update verification-gate handoff — baseline at zero
- docs: implementation plan for unified cross-language verification gate
- docs: spec for unified cross-language verification gate

**Tests**

- test: xfail remaining dev-tier API tests (refs #1151, #1154)
- test: xfail dev-tier gated router tests (refs #1151, #1154)
- test: update stale unit tests for {items,count} envelopes + CacheEntry object + CLI output
- test: CLI contract test fails (not skips) on unhealthy engine + captures stderr
- test: live CLI<->engine contract test (CLI mirror of AppEngineContractTests)
- test: contract walker seeds via shared seed_test_library (one ground-truth lib)
- test: shared seeder shim so walker + CLI test reuse seed_test_library
- test: live app↔engine integration tests + fix test-host self-termination

**Chore**

- chore(session-end): checkpoint verification-gate state + next-session entry point
- chore: verification-gate handoff doc + verify_python.sh (Python gate, src-only lint)

### 2026-05-19

**Features**

- feat: make claim SVO display easier to read and click — tappable subject/verb/object chips (#1036)
- feat: add SVO-style fields to KnowledgeClaim for structured triples metadata (#730)
- feat: add PDF zoom toolbar mirroring image viewer's toolbar (#1024)

**Fixes**

- fix(#1149): envelope-consistency sweep — documents + workflows core
- fix(#1149): envelope-consistency sweep — KG/claims/curation cluster
- fix: entity list endpoints 500 — #1075 envelope migration left bodies returning bare lists
- fix: 3 backend bugs surfaced during live Catalogue.fichero session
- fix(#1144): type 6 envelope ListResponses with concrete element types
- fix: ContradictionEvidence typing + Swift envelope unwrap
- fix: ruff errors in threads.py + activity_store.py
- fix: resolve KG viewer page-child sourceDocumentId navigation (#1031)
- fix: re-apply #1036 SVO chips — pr_review LLM parser bug falsely rejected it
- fix: clear current node tracking when node completes to fix wrong running indicator in Activity Progress tab (#1040)

**Chore**

- chore(cascade): #1031 flagged for review (cascade-review/1031-1779204673)
- chore: gitignore cascade lock file
- chore(queue): mark #1024 done (shipped at 00dde49f); #958 in_progress
- chore(cascade): mark #1036 blocked
- chore(autoloop): mark #730 done — committed by worker as 0e7f5a77ab9a8a5543fb9ecc662be295e18f9f0e
- chore: mark #1045 blocked — free worker stubbed workflow fetch, needs scope split
- chore: mark #1048 blocked — free worker hallucinated twice on cross-cutting scope
- chore: complete the #1040 verify-only state flip iter 3 left at in_progress
- chore: verify #1040 already shipped — fix clears current node tracking when node completes
- chore(autoloop): unclaim stale #1040 left by mega-loop round 3 abort

### 2026-05-18

**Features**

- feat: auto-trigger KG embed + predictions post-workflow (#1008)
- feat: hermeneutic predicate vocabulary — controlled interpretive verbs (#1124)
- feat: add Catalogue Each workflow foundation for bulk fan-out (#1098)
- feat: add case_id grouping for catalogue artifacts (#1096)
- feat: add OCR cleanup workflow node (dehyphenate + rejoin columns + strip stamps) (#925)

**Fixes**

- fix: resolve merge→catalogue edge not rendering due to default port ID mismatch (#1042)
- fix: show immediate Starting… indicator before first SSE event (#764)
- fix: show page thumbnail in search result rows instead of generic icon (#1046)
- fix: clear detailDocument on sidebar folder click so inspector updates (#795)
- fix: correct loupe sourceRect coordinate mapping from view to image space (#783)
- fix: add 60s startup timeout to BackendConnectionView, Restart Engine button (#758)
- fix: log engine binary path at startup so multi-install users can identify which Fichero is running (#759)
- fix: guard GraphSimulation.step() against zero canvas size and NaN propagation (#998)
- fix: remove duplicate listScrollTarget on plain tap to stop first-click flash (#788)
- fix: persist pane widths via AppStorage so they survive app restarts (#1070)
- fix: persist KG entity pane width via AppStorage + ResizableDivider (#1034)
- fix: tighten workflow canvas node spacing (#1049)
- fix: console hygiene — NaN guards + FocusedValue multi-update (#961)

**Performance**

- perf: lazy-import torch/pykeen to cut cold-start time (#743)
- perf(workflows): move heavy langgraph imports to function-level

**Refactors**

- refactor: simplify Activity view from 8 tabs to 4 tabs (#1038)

**Docs**

- docs: add QA reviewer spawn prompts and wire gate into parallel-execution (#1061)

**Chore**

- chore(curator): refresh queue (30 issues, 2026-05-18)
- chore(autoloop): curator pass — refresh queue for Round 2
- chore(autoloop): mark #764 done in queue
- chore(autoloop): mark #743 done in queue
- chore(autoloop): unclaim stale in_progress #743 #764 before overnight Sonnet run
- chore(autoloop): refresh queue.md + curator history + continue sentinel
- chore: mark #750 done in queue
- chore: verify #750 already shipped — close as fixed-but-not-closed
- chore: verify #879 already shipped — close as fixed-but-not-closed
- chore(curator): refresh queue (40 issues, 2026-05-18)
- chore: curator pass — add #750/#768/#1061, promote #879/#743 to P1, refresh digest
- chore: mark #1008 done in queue
- chore: mark #745 done in queue
- chore: verify #745 already shipped — close as fixed-but-not-closed
- chore: mark #746 done in queue
- chore: verify #746 already shipped — close as fixed-but-not-closed
- chore: mark #747 done in queue
- chore: verify #747 already shipped — close as fixed-but-not-closed
- chore: upgrade Pillow>=12.2.0 and fastembed to fix 5 Pillow CVEs (#1043)
- chore(curator): refresh queue (38 issues, 2026-05-18)
- chore: mark #795 done in queue
- chore: mark #783 done in queue
- chore: mark #758 done in queue
- chore: mark #759 done in queue
- chore(curator): refresh queue (33 issues, 2026-05-18)
- chore: mark #788 done in queue
- chore: mark #1070 done in queue
- chore: mark #1034 done in queue
- chore: mark #1049 done in queue
- chore(curator): refresh queue (31 issues, 2026-05-18)
- chore: reconcile queue.md against git reality
- chore: mark #1115 blocked — architecture design needed for KG write separation
- chore: mark #971 blocked — architecture review needed
- chore: mark #1097 blocked — requires architecture review for HITL pattern
- chore: mark #1096 done
- chore: session-end-worker — #925 done
- chore: mark #984 done — SVO promotion verified already shipped

### 2026-05-17

**Features**

- feat: save per-chunk catalogue summaries as catalogue.chunk.N artifacts (#840)
- feat: add agent-autonomous-loop.py for curator/worker autonomous splits (#1999)
- feat: add library lifecycle CLI commands (add, remove, create, delete, open, close, list, reset) (#1130)
- feat: add library registry persistence (#1131)
- feat: add engine lifecycle CLI commands (status, start, stop, restart) (#1132)
- feat: add dedicated CLI formatters for Entity/Claim/Document/Artifact (#1141)

**Fixes**

- fix: Apple Vision OCR empty result — log + retry at .fast level (#834)
- fix: whitelist TestClient 'testserver' host in auth middleware loopback check (#841)
- fix: remove --continue flag from CLI invocation in agent-autonomous-loop.py
- fix: remove invalid --max-tasks option from Claude CLI invocation
- fix: audit raw SQL write-path bypasses in AppDatabase (#1112)
- fix: Cleanup: 3 minor write-path bypasses from the DuckDB audit (#1117)
- fix: complete list endpoint envelope standardization (#1075)
- fix: correct list endpoint response count calculations (#1075)
- fix: add typed response models and wire through CLI client (#1140)
- fix: expand CLI formatter field tuples for complete response coverage

**Tests**

- test: update test assertions for envelope response format (#1075)

**Chore**

- chore: mark issue #984 complete — SVO promotion already shipped
- chore: remove stale .venv symlink (was pointing at fichero-api/.briefcase-venv); real .venv now lives untracked at .venv/, ignored by .gitignore
- chore(session-end): 2026-05-17 — #840 shipped, trace-mcp → jcodemunch, .venv rebuilt
- chore: migrate from trace-mcp to jcodemunch + fix venv environment rot
- chore(curator): refresh queue (31 issues, 2026-05-17)
- chore: queue.md + digest.md refresh from autoloop smoke test (#834 done)
- chore: mark #841 complete in queue.md
- chore: enhance digest with explicit trace-mcp examples and warning for worker compliance
- chore: reorder queue to test simpler issue #841 first instead of complex #840
- chore(session-end): document 6 completed CLI/backend issues (#1140, #1141, #1132, #1131, #1130, #1075)
- chore: remove unused import in test_cli_library.py

### 2026-05-16

**Features**

- feat: generate typed Python client from openapi.json (#1139)
- feat(kg): probabilistic entity-match scoring (#988 step 3)
- feat: quotes_extract tool — attributed + unattributed quote KG extraction (#1099)
- feat: manually create entities + claims via CLI (#1134)
- feat: kg reset/rebuild + doc import CLI commands (#1130)
- feat(cli): entity similar command + search --in-doc/--in-folder scoping (#1125)
- feat(workflow): cancel endpoint + CLI workflow stop (#1127)
- feat(cli): scoped KG exploration — entity/claim at-page/at-doc/at-folder + entity context (#1125 MVP)
- feat(kg): manual claim creation auto-derives attribution + OpenAPI regen (#1123 Phase E)
- feat(kg): auto-derive speaker / quotation_kind / audience on every claim (#1123 Phase D)
- feat(kg): canonical-verb vocabulary + auto-populate predicate_canonical (#1123 Phase C)
- feat(kg): extend ClaimRelationType with five typed kinds + related_to (#1123 Phase B)
- feat(kg): attribution-taxonomy fields on KnowledgeClaim + Document (#1123 Phase A)

**Fixes**

- fix(cli): add document_id and document_name to formatter keys (#1137)
- fix(cli): correct entity_neighborhood endpoint path — /api/kg/graph/neighborhood (#1136)
- fix(workflows): use local PYPPETEER for mermaid diagram rendering, drop mermaid.ink dependency (#1025)
- fix(llm): pass permissive_guardrails to extractors to reduce Apple Intelligence guardrail false-positives (#1001)
- fix(transcribe): save empty artifact for blank PDF pages (#1082)
- fix(library): correct getArtifacts argument order (forceRefresh before includeDescendants)
- fix(inspector): show all SVOs per entity + filter tautological claims (#1109)
- fix(viewer): image viewer canvas grey so white-page scans are visible (#1066)
- fix(library): enable view-mode strip and split layouts by default (#1063)
- fix: Page Content panel fills full inspector height (#1062)
- fix: search result single-click now populates preview pane (#1053)
- fix: entity lozenges refresh after workflow completes (#1055)
- fix(workflow): node config shows Default instead of Select provider... (#1058)
- fix: fichero check all-green + db NULL→default coercion for enum fields
- fix(entities): move /top route before /{entity_id} to prevent FastAPI shadowing
- fix(vision): dedup page artifacts in _propagate_to_page_children on re-run (#1067)
- fix(search): apply min_score after RRF fusion + raise default to 0.45 (#1054)
- fix(settings): protect tier-alias defaults from empty-save deletion + add /repair endpoint (#1057)
- fix(cli): store workflow_id in graph state so --wait reports it correctly (#1079)
- fix(vision): save artifacts on page doc, not parent, in per-page fan-out (#1077)
- fix(vision): normalise Apple Vision provider/model to lowercase (#1078)
- fix(checkpointer): typed alist_threads — no more raw conn.execute in route (#1122)
- fix(kg): race recovery in upsert_entity Stage 4 (#1121)
- fix(kg): claim.entity_ids[] covers every entity mentioned, not just subject (#1119)
- fix(kg): entity quality — type conflicts, admin-qualifier dedup, event grounding (#1114)

**Refactors**

- refactor(hermeneutics): fold kg_interpretations.py into hermeneutics.py (#1126)
- refactor: module consolidation Wave 1 + CLI CRUD Wave 2

**Docs**

- docs(STATE): session continuation note + next-session pickup pointer

**Tests**

- test(kg): invariant violation logging tests for extractor round-trip (#1017)

**Chore**

- chore: commit pending config/doc changes before session
- chore(session-end): verify #1139 complete, queue #1140 next
- chore(session-end): Haiku loop rounds 1-4 — 16 issues fixed/closed, CLI typed client generated
- chore(worker-status): mark #1139 complete, next is #1140
- chore(session-end): archive Round 3 verification sweep + update state
- chore(session-state): update Round 4 queue entry point
- chore: update CONTINUE.md
- chore(session-end): archive Round 3 #1138 fix + update state
- chore(worker-status): mark #1138 complete — fastembed pooling already fixed in 44374c04
- chore(session-end): archive Round 3 #1137 fix + update next-session entry
- chore(worker-status): mark #1137 complete
- chore(session-start): Round 3 session checkpoint
- chore(session-end): update STATE.md with Round 3 queue status
- chore(worker-status): mark #1136 complete, note #1137-#1138 pending
- chore(session-start): session checkpoint
- chore(session-end): verify Round 2 backend complete, awaiting Daniel approval
- chore(session-end): archive backend loop session
- chore(session-end): Round 2 backend queue fully complete — awaiting Daniel approval
- chore(session-end): autonomous worker session checkpoint — Round 2 queue verified complete
- chore(session-end): Round 2 verification session — queue already complete, awaiting Daniel approval
- chore(session-end): Round 2 verification complete — 0.0.2 milestone backend work fully verified
- chore: Round 2 backend queue verification complete — all 6 issues verified as fixed
- chore(session-end): update STATE.md + HISTORY.md checkpoint
- chore(session-end): Round 2 verification — #1033 already fixed in 7ef16274, moving to #1030
- chore(session-end): backend queue Round 2 checkpoint — #1037 verified, next: #1033
- chore: Round 2 Queue — #1037 already fixed, moving to #1033
- chore: session-end documentation checkpoint
- chore(session-end): backend queue verified complete, state snapshot updated
- chore(session-end): autonomous session checkpoint — all 0.0.2 backend queue complete
- chore(session-end): checkpoint backend queue completion state
- chore(session-end): autonomous backend loop completed — 4 issues fixed, queue cleared
- chore(session-end): mark #988 complete, no more pending tasks
- chore(session-end): document #1017 completion
- chore: mark #1017 complete, next task #988
- chore: session checkpoint
- chore(session-end): archive #1025 completion, update next session entry point
- chore(session-end): #1099 complete — quotes_extract shipped
- chore(session-end): afternoon session checkpoint — #1063 #1066 #1109 fixes + KG review
- chore(schema): fold migrate_knowledge_claims_provider_model into base; document no-migration rule (#1128)
- chore(hygiene): delete stale security-findings, handoff, and planning files (#1129)
- chore(infra): wire graphify knowledge graph + cozempic guard hooks into project docs
- chore(session-end): wave 1 + #1120 retrospective checkpoint

### 2026-05-15

**Features**

- feat(kg): full SVO + provider/model + confidence + language on every claim
- feat(cli): type 8 client methods against backend Pydantic models (#1084 Wave 1)
- feat(cli): library bootstrap, --wait that actually waits, artifacts get, recursive import
- feat(cli): wire fichero.models typing into client.py (loud at the boundary)

**Fixes**

- fix(checkpointer): typed adelete_thread, drop raw DELETE in route (#1116)
- fix(db): Database.save() uses native DuckDB UPSERT (closes #1120 crash)
- fix(backend): preserve original filename on import + suppress langchain warning
- fix(cli): readable search results, --type validation, scrubbed terminal-state output
- fix(auth): make initialize_token idempotent — reuse existing .api-key (#1110)
- fix(workflows): write KG + artifacts on selected file when no folder container resolves
- fix(cli): workflow run sends selected_doc_ids, not files (#1074)
- fix(cli): _resolve_workflow uses attribute access (Workflow, not dict)
- fix(cli): unwrap the paginated envelope on /api/artifacts/document/{id}
- fix(cli): make kg commands usable + survive missing workflow checkpoints

**Docs**

- docs(STATE): subagent landing report + SVO live-verification caveat
- docs(STATE): working/not-working inventory + 3 subagents in flight
- docs(proposals): engine quality run #1, CLI/SwiftUI parity, maps import survey
- docs: refresh governance docs for one-engine/many-surfaces
- docs: STATE.md — manager pattern (delegate edits to subagents)
- docs: STATE.md — CLI↔SwiftUI endpoint parity is next-session item #3
- docs: restore loop #1 invariants in STATE.md "Don't break" (mea culpa)
- docs(cli): Phase 3 retry — full mutating flow + bug findings

**Chore**

- chore(scripts): add tail-backend-errors.sh
- chore(session-end): CLI typed, end-to-end verified, #1074/#1075 filed, plan written
- chore: commit pending config/doc changes before session

### 2026-05-14

**Features**

- feat(migrations): repair migration scrubs leaked kwarg-repr from existing KG rows (#1030)
- feat(api): server-composed entity summary on the inspector endpoint (#1050)
- feat(cli): rewrite MCP server as a thin FicheroClient wrapper
- feat(api): surface catalogue artifacts on the knowledge-graph endpoint (#1047)
- feat(api): include_children aggregates page-child KG onto parent PDF (#1069)
- feat(api): canonical document knowledge-graph endpoint (#1068)
- feat(cli): add typer command tree and output formatters
- feat(cli): add FicheroClient HTTP wrapper for the backend
- feat(db): wire DBWriter into workflow execution; migrate artifact writes (#1000 Phase 2)
- feat(db): single-writer DB queue infrastructure (#1000 Phase 2)
- feat(kg): surface graph-context merge candidates into review queue (#988)
- feat(kg): graph-context similarity merge-candidate generator (#988)

**Fixes**

- fix(workflows): born-digital PDF text layer beats stale cached OCR artifact (#1064)
- fix(workflows): add extract_all to CACHEABLE_TOOLS (#1065)
- fix(backend): DBWriter fails loud instead of deadlocking the backend (#1000)
- fix(library): remove filter + zoom controls from the library top toolbar (#1023)
- fix(workflow): remove manual Refresh button from workflow library toolbar (#1022)
- fix(llm): retry transient Apple decode failures on-device before paid fallback (#1027)
- fix(workflows): transcribe re-OCR'd born-digital PDFs in LLM vision mode (#1033)
- fix(extractors): keyword extractor over-extracts — salience bar + cap (#1051)
- fix(workflows): quality gate stops only when ALL pages are garbage (#1029)
- fix(workflows): quality gate — stop the run on garbage node output (#1029)
- fix(workflows): extract_all fail-fast on systemic errors + timing instrumentation (#1060, #1037)
- fix(workflows): run workflow execution off the main event loop (#1000 Phase 1)
- fix(engine): suppress lancedb's spurious fork-safety warning (#1028)
- fix(kg): cascade-delete orphaned claims when a source document is deleted (#1021)
- fix(kg): sanitize leaked kwarg-repr in extractor items (#1030)
- fix(kg): pass explicit utf-8 encoding to graph.serialize (#1026)
- fix(swiftui): stop mutating @State inside the graph Canvas render closure (#1019)
- fix(extractor): stop land-use categories and unnamed occurrences landing in concepts (#1009)
- fix(llm): make the Apple Intelligence → paid-cloud fallback loud (#1001)
- fix(extractor): make zero-entity pages visible in the activity log (#1003)
- fix(kg): off-load embed endpoints to worker thread so the event loop stays responsive (#1004)

**Docs**

- docs: whole-app SwiftUI-logic audit — three misplaced-logic clusters (#1072)
- docs(cli): Phase 3 live smoke test transcript + status note
- docs: SwiftUI KG-logic audit — backend endpoints to retire client-side logic (Phase B)
- docs: plan for fichero-cli — separate HTTP client to the backend
- docs: update STATE.md — #1027 shipped, #1025/#1054 triaged
- docs: update STATE.md — backend pipeline-trust cluster sweep (6 fixes)
- docs: parallel execution & review process — when to use teams vs subagents (#1061)
- docs: build the Swift app properly — Xcode MCP or shared DerivedData, keep ⌘R warm
- docs: mark Phase 2 DBWriter infrastructure built (#1000)
- docs: workflow execution architecture proposal — #1000 + scale path

**Tests**

- test(workflows): drop Catalogue (Mixed) test assertions (#1020)
- test(swiftui): static lint for SF Symbol names — #1017 layer 3
- test(extractor): surface KG-write invariant violations in the activity log (#1017)

**Chore**

- chore(session-end): autonomous loop iteration 5 — #1072 audit + #1030 backend repair shipped
- chore: commit pending config/doc changes before session
- chore(session-end): autonomous loop iteration 4 — #1047 + #1050 shipped, Phase B endpoint queue empty
- chore(session-end): autonomous loop iteration 3 — #1068 + #1069 shipped, Phase B in progress
- chore(session): commit scheduled-task lock + continue marker
- chore(session-end): autonomous loop iteration 2 — #1064 fixed, Phase A complete, Phase B audit written
- chore(session-end): overnight loop iteration 1 — #1000 + #1065 shipped
- chore(session-end): checkpoint — overnight loop handoff, 8 fixes + 10 bugs filed, #1000 deadlock diagnosed
- chore(session-end): archive session — backend fix sweep + #1000 Phase 1/2 + 0.0.2 bug inventory
- chore: regenerate openapi — #1021 delete_document docstring
- chore(workflows): remove catalogue_mixed.json — collapse to one Catalogue (#1020)
- chore: sync .claude/CLAUDE.md paths + commit openapi regen
- chore(session-end): record SF Symbol catalog + Canvas @State lessons
- chore(session-end): autonomous session — #1017 layer 3 + #1019 shipped
- chore(session-end): archive #1017 layer 2 + #988 step 1 to HISTORY
- chore(session-end): backend session — #1017 layer 2 + #988 step 1 shipped
- chore(session-end): autonomous backend bug sweep — #1004 #1003 #1009 closed, #1001 partial

### 2026-05-13

**Features**

- feat(ui): claim card source-link affordance + drop redundant tags + excerpt fallback (#1013, #1006)
- feat(kg): promote SVO triple to top-level KnowledgeClaim fields (#984)
- feat(kg): #989 biography view + #994 LazyVStack + #988 graph-context entity-resolution candidates
- feat(kg): claim card context-menu — set status / curation + delete (#901)
- feat(search): filename-match boost — promote docs whose name matches the query (#886)
- feat(kg): PDF highlight overlay on claim source navigation (#995 / Phase 4)
- feat(kg-viz): click an edge in the focus-neighborhood graph opens its source claim
- feat(kg-viz): rewrite graph view as focus-neighborhood with SVO-labeled edges (#976/#977/#983 Phase 5)
- feat(tier): promote /api/hermeneutics from dev → release for 0.0.2 ship (#997)
- feat(kg): wire claim-card source navigation — open the PDF + scroll to page (#978/#979/#982 Phase 2)
- feat(kg): rank-then-truncate in /neighborhood — keep most-connected neighbors (#993)
- feat(kg): library-scoped LRU cache for networkx + rdflib graphs (#990 / #992)
- feat(db): index knowledgeclaims + knowledgeentitys for sub-50ms per-doc queries (#991)
- feat(kg): claim card renders SPO from metadata + source-doc citation (#978/#979 Stage 2 partial)
- feat(kg): POST /api/kg/sparql — SPARQL query endpoint (#987 / #983 Stage 1c)
- feat(kg): expose networkx algorithm cluster — pagerank / communities / similar / components / triangles / clustering (#987 / #983 Stage 1b)
- feat(kg): GET /api/kg/graph/neighborhood/{entity_id} — focus + k-hop + SVO edges (#987 / #983 Stage 1a)
- feat(kg-viz): add Chart mode — entity-type distribution bar chart (#902)
- feat(kg-viz): pinch-zoom, drag-to-pan, zoom controls + kind-color legend
- feat(bibliography): wire metadata get/patch/extract endpoints (#974 prep)
- feat(inspector): Citations section on Info tab (#974 prep)
- feat(inspector): KG-RAG Related Claims panel on Info tab (#959)
- feat(citations): wire inbound/outbound citation graph endpoints (#974 prep)
- feat(ingest): preserve Kreuzberg structured outputs as artifacts (#885)
- feat(kg): add force-directed graph view to Ontology Browser (#902, partial #889)

**Fixes**

- fix(catalogue): surface 'no narrative produced' as result error (#1011)
- fix(workflow-execution): drop LangChain internal Runnable nodes from SSE stream (#1002)
- fix(kg): auto-refresh entity list on workflow completion; drop manual refresh button (#1007)
- fix(extractor): reject degenerate entity descriptions ('called', 'noted') (#1016)
- fix(ui): hide inspector column in Knowledge Graph view (#1014)
- fix(swiftui): surface actual HTTP status + content-type when storage thumbnail fetch fails (#1018)
- fix(workflows): rename catalogue leaf tool to 'Archival Summary' to disambiguate from Catalogue workflow (#1012)
- fix(api): return 503 with JSON instead of stuffing mermaid source in HTTP header (#999)
- fix(ui): drop embedded PDF zoom toolbar from PDFPageWithToolbar (#1010)
- fix(ui): EntityDetailView filter chips show only present status/kind values (#1005)
- fix(ui): replace nonexistent 'pickaxe' SF Symbol + guard empty icon strings (#1015)
- fix(library): add global default view mode for cross-window stickiness (#943)
- fix(extractor): rewrite first-person pronouns to author name when source_metadata has authors (#963)
- fix(layout): Activity / MCP Servers / Providers adopt shared listColumnWidth (#985 expand)
- fix(kg): alias dedup is case-folded + claim cards suppress empty-content rows (#986)
- fix(kg): drop redundant toolbar header + entity list fills column + adopts shared listColumnWidth (#981, #980, #985 partial)
- fix(tests): disable auth middleware in conftest + ruff F823 in catalogue
- fix(library): PDF page-child thumbnails resolve via selectedCollection (#927)

**Refactors**

- refactor(kg): consolidate duplicated helpers into _common module

**Docs**

- docs(kg): scaling review — does the design hold up at book/400-case?
- docs(kg): expand wireframes — 9 views + small-component sketches + interaction flows + phase plan + naming
- docs(kg): UX wireframes — source-anchored 3-pane layout
- docs(kg): comprehensive architecture review + staged plan

**Tests**

- test: monkeypatch FICHERO_BASE_PATH out of default-path tests
- test(conftest): isolate prod app.duckdb via FICHERO_BASE_PATH + singleton swap
- test(kg): /api/knowledge-graph/claims → /api/claims (1587a1b6 consolidation)
- test(api): same empty-query expectation update for test_api.py
- test: search empty/whitespace queries return recent docs, not 400
- test: catch up route tests with post-1587a1b6 KG consolidation
- test: remove tests for deleted KG namespaces

**Chore**

- chore: commit pending config/doc changes before session
- chore(session-end): kg-consolidation session wrap-up
- chore: bump CONTINUE timestamp
- chore(session-end): autonomous loop closed 4 more bugs (#1016, #1007, #1002, #1011)
- chore(history): archive 2026-05-13 autonomous session (4 bugs)
- chore(session-end): autonomous loop closed 4 more bugs (#999, #1012, #1014, #1018)
- chore(session-tracking): clear session-end marker, bump CONTINUE timestamp
- chore(session-end): autonomous loop closed 5 UI bugs (#1005, #1006, #1010, #1013, #1015)
- chore(session-start): restore sentinel + tick CONTINUE.md for autonomous loop
- chore(session-end): final tally — 21 bugs filed (#998-#1019); pivot to tooling next
- chore(session-end): record evening testing pass — 19 bugs filed (#998-#1016)
- chore(session-end): archive 2026-05-13 KG rebuild ledger; lean STATE pointing at #998/#999
- chore(state): final tally — 45 commits + 21 issues closed today
- chore(state): record evening KG rebuild — Phases 1+2+5 shipped
- chore(openapi): sync spec — pick up Stage 1 endpoints + algorithm cluster + SPARQL
- chore(state): session end — 19 commits, viz has list/graph/chart modes
- chore(state): final tally — 2404/2 tests, 15 commits, 4 issues closed today
- chore(state): record 2026-05-13 late autonomous run — 11 commits, 4 issues closed
- chore(state): record 2026-05-13 mid-day autonomous run — 2 streams shipped

### 2026-05-12

**Features**

- feat(ingest): add .odp/.html/.markdown/.htm/.xml + .srt/.vtt/.sbv to file_type map
- feat(settings): Defaults model picker filters by tier capability (#940)
- feat(library): PDF thumbnails show multi-page badge (paper-stack icon + page count) (#946)
- feat(kg): verbatim source_text per claim in DocumentInspector KG tab (#893)
- feat(kg): entity edit sheet — rename, retype, edit aliases (#901 PATCH side)

**Fixes**

- fix(app): periodic backend heartbeat surfaces offline state mid-session (#967)
- fix(workflow): defer per-page green checkmark until workflow.complete (#948)
- fix(inspector): artifact panels size to content via sizeThatFits (#960)
- fix(ingest): default auto_embed=True so text-bearing files are semantically searchable on drop (#881 follow-up)
- fix(ingest): default extract_text=True so .md/.txt files are searchable on import (#881)
- fix(sidebar): match content area tonally with windowBackgroundColor (#883)
- fix(workflow): Activity row appears optimistically on Run click (#944)
- fix(library): PDF preview scroll keeps the selected sidebar row visible (#929)
- fix(workflow): collapse Install + Reset Defaults into single Reset action (#930)
- fix(providers): preserve Apple model capability badges on re-add (#939)
- fix(settings): Defaults model picker resets + reloads on provider change (#936)
- fix(providers): API key field uses prompt: parameter so masked dots render inside the box (#934)
- fix(settings): Reset AI Defaults repopulates Apple Intelligence baseline (#933)
- fix(app_db): save_model idempotent on (provider_id, model_id) — kill duplicate-add (#937)
- fix(extract_all): throttle concurrent Apple Intelligence calls to 3 max (#962 follow-up)
- fix(extract_all): promote Apple Intelligence decode failures to AppleUnavailableError (#949 / #962)
- fix(transcribe): skip Apple Vision OCR when PDF has embedded text layer (#957)
- fix(kg-ui): OntologyBrowser toolbar layout + entity selection refresh
- fix(api): promote /api/kg/* from dev-tier to core (#967)
- fix(bootstrap): three Apple model rows + auto-populate AI Defaults on first run
- fix(ui+api): two quick wins from morning bug triage
- fix(workflows): include document_id in cache key — fixes Davidson ×6 (#896 root cause)

**Docs**

- docs(state): morning push summary — 12 fixes + 8 dedups
- docs(state): morning hand-off pointer — what landed overnight + smoke-test order
- docs(history): overnight session log — KG namespace consolidation + #896 root cause
- docs: update architecture overview for /api/kg/* namespace (post 1587a1b6)
- docs(state): two more issues closed — #896 + #891
- docs(state): refresh overnight session summary

**Tests**

- test(claim-dedup): regression tests for #896 within-page dedup guard
- test(cache): regression tests for #896 document_id disambiguation

**Chore**

- chore(session-end): 2026-05-12 afternoon hand-off — 4 fixes, 3 closed, #975 filed

### 2026-05-11

**Features**

- feat(kg): delete claim from context menu (#901 part 2)
- feat(kg): delete entity from OntologyBrowser context menu (#901 part 1)
- feat(kg): manual entity creation sheet — #916 first stroke
- feat(kg): heuristic prediction review sheet — accept/reject candidates
- feat(library): unify entity filter with KG ontology browser (#887)
- feat(kg): expandable claim cards show contradictions + evidence chain
- feat(kg): surface entity curation history + tools menu in OntologyBrowser
- feat(kg): wire EntityServiceGenerated to new /api/kg/* surfaces
- feat(workflows): annotations_source tool — iterate highlights as AI input (#914)
- feat(kg): consolidate graph routes — port BFS + metrics, deprecate old (#919 slice 5b)
- feat(kg): consolidate interpretations — taxonomy + deprecate old route (#919 slice 5b)
- feat(kg): #914 annotation cropping helpers + /api/annotations/{id}/crop
- feat(kg): extractor emits time_start/time_end + Toulmin grounds/warrant (#904, #907)
- feat(kg): entity_inspector + kg_search — UI velocity helpers for #902
- feat(kg): #907 Toulmin claim fields + aggregate document inspector endpoint
- feat(kg): #909 BibTeX / RIS / CSL JSON import + bulk BibTeX export
- feat(kg): #910 DOI + ISBN online metadata lookup
- feat(kg): #915 user-extensible classification registry
- feat(kg): #908 bibliographic metadata extraction (PDF + LLM cover pages)
- feat(kg): #906 document-to-document citation graph
- feat(kg): #918 Projects — named workspaces grouping sources + analysis
- feat(kg): #917 Zettelkasten — Note model + bidirectional NoteLink + CRUD
- feat(kg): #914 annotations — highlight, note, rating, bookmark, comment
- feat(kg): #904 temporal claims + #905 interpretation/framework CRUD
- feat(kg): #912 citation rendering — BibTeX / Chicago / APA / MLA
- feat(kg): #913 sub-page character anchors on KnowledgeClaim
- feat(kg): #903 source authority weighting in triangulation
- feat(kg): auto-retrain PyKEEN every 10 labelled review decisions (#899 / #377)
- feat(kg): mutation log + undo for entity / claim edits + deletes (#901)
- feat(kg): entity-match review queue — accept/reject pairs → training labels (#899 Phase D / #377)
- feat(kg): auto-rebuild kg.nt at end of catalogue runs (#899)
- feat(kg): Phase E — PyKEEN link prediction scaffolding (#899 / #377)
- feat(kg): NetworkX traversal + PATCH/DELETE for entities + DELETE for claims
- feat(kg): cross-source triangulation — support_count per SVO triple (#900)
- feat(kg): rebuild helper + POST /api/kg/rebuild endpoint (#899)
- feat(kg): wire spaCy NER pre-pass into the catalogue extractors (#899 Phase C integration)
- feat(kg): Phase C — spaCy deterministic NER pre-pass (#899)
- feat(kg): Phase A — rdflib RDF triple substrate (#899)
- feat(kg): Phase B — sentence-transformer entity vectors in LanceDB (#899)
- feat(kg): tap entity name in OntologyBrowser to scoped-search library (#882)
- feat(kg): tap a claim source quote to search the library for it (#893)
- feat(kg): filter strips for epistemic + ontological axes in EntityDetailView (#893)
- feat(kg): show verbatim source_excerpt on claim card + inspector (#893)
- feat(kg): epistemic + ontological status + verbatim source_text on every claim (#892)
- feat(kg): SVO claim composition — split context into verb + object (#730)
- feat(kg): MiniToolbar + filter menu on OntologyBrowser to match other modes
- feat(workflows): files_tool expands parent PDFs to per-page entries (#891)
- feat(kg): entity-type filter chips in OntologyBrowser (#498)
- feat(kg): wire OntologyBrowser into sidebar + content router (#498)
- feat(kg): wire AppViewMode.ontology + sidebar nav row (#498 phase 1)

**Fixes**

- fix(kg): defense-in-depth dedup at save_claim — within-page near-duplicates (#896)
- fix(kg): mark new fields required in schema so Apple Intelligence emits them (#894)
- fix(kg): hide library mode rail when viewMode is .ontology (#895)
- fix(kg): fuzzy entity match in upsert_entity collapses surface variants (#897)
- fix(kg): collapse near-duplicate claims within one extractor call (#896)
- fix(kg): CurationStateBadge switches on the right ClaimCurationState cases
- fix(workflows+pdf): per-page fast-path + defer zoom publish (#891 critical)
- fix(library): resolve parent PDF for page-child thumbnails + preview (#890)
- fix(transcribe): use pre-extracted page_content instead of re-OCRing (#884 follow-up)
- fix(kg): share kind-filter state between OntologyBrowser + KG inspector (#887 partial)
- fix(library): strip overlay styling from entityFilterMenu for toolbar (#883)
- fix(visual): bump MiniToolbar height 36pt → 44pt to match NSToolbar (#883)
- fix(library): entity-filter menu in toolbar primaryAction for all 4 views (#883)
- fix(visual): sidebar breathing room + MiniToolbar material (#883 partial)
- fix(kg): entity names in KG inspector tap-to-search (#882)
- fix(transcribe): text-format passthrough in vision_base (#884)

**Refactors**

- refactor(kg): consolidate /api/knowledge-graph/* into canonical /api/kg/* namespace (#919 5c)

**Docs**

- docs(state): overnight KG UI session wrap
- docs(state): 2026-05-12 overnight progress + tag-collision memory note
- docs(kg): full backend endpoint reference for tomorrow's Swift work
- docs(state): EOD totals — 683 tests passing, coverage 10.78%, OntologyBrowser shipped
- docs(state): 2026-05-11 autonomous day — OntologyBrowser + bug-fix sweep

**Tests**

- test(kg): integration tests for the inspector aggregate endpoints
- test(kg): live Apple Intelligence assertions for new fields, with telemetry
- test(kg): live SVO extraction smoke test against Apple Intelligence (#730)
- test(kg): cover OntologyBrowser filter helpers (#498)
- test(sidebar): cover SidebarItem+MoreFactories — chain/comparison/schedule/trigger/batch/activity
- test(comparison): cover ComparisonSummary + ComparisonHistoryResponse snake_case decode and Hashable
- test(workflow): cover WorkflowSupportTypes — OutputSchema/InputMapping/AgentType
- test(kg): lock AppViewMode.ontology routing (#498)
- test(sidebar): pin Date in WorkflowSidebarItem Hashable test
- test(state): cover SidebarState — expansion + persistence + reset
- test(run): cover Run + RunStatus — workflow execution record
- test(trace): cover Trace model — LangChain/LangGraph debug record
- test(sidebar): cover SidebarSearchTypes — SavedSearch + WorkflowSidebarItem
- test(types): cover DocumentStoreTypes + SidebarViewTypes
- test(workflow): cover WorkflowToolTypes — palette + node-config DTOs
- test(automation): cover AutomationServiceTypes Schedule + Trigger DTOs
- test(provider): cover ProviderServiceTypes DTOs + formatters

**Chore**

- chore(kg): remove dead ClaimInspector/EpistemologyGraph/PredictionReview view dirs (#889)
- chore(kg): remove dead KnowledgeGraphService + HermeneuticsService stubs
- chore: ruff cleanup on inspector aggregate tests
- chore(api): group hermeneutics under "knowledge-graph" tag
- chore(state): 2026-05-13 morning hand-off — backend ready for SwiftUI work
- chore(api): unregister hermeneutics + mind-palace + research routers (#919 5b)
- chore: ruff cleanup
- chore(api): strip duplicate router-level tags=["knowledge-graph"]
- chore(kg): ruff cleanup on citations route
- chore(kg): ruff cleanup on review_queue tests
- chore(state): 2026-05-12 autonomous-run hand-off — KG library rollup + triangulation
- chore(kg): ruff cleanup on spacy_ner.py (removed unused TYPE_CHECKING import)
- chore(kg): ruff cleanup on test_triples (removed unused pytest import)
- chore(session-end): 2026-05-11 evening — KG epistemology layer shipped
- chore(api): regenerate OpenAPI schema in dev tier — KG/Hermeneutics/Predictions now exposed

### 2026-05-10

**Features**

- feat(kg): GET /api/entities/{id}/drill-down — bundled three-rail entity detail (Phase 21)
- feat(kg): GET /api/entities/top — entry-point for 'who's in this archive?' (Phase 19)
- feat(kg): GET /api/documents/{id}/related — entities-shared neighbours (Phase 18)
- feat(sidebar): Saved Searches now lives below Workflows + Activity (Phase 16)
- feat(kg): /entities/{id}/documents + /entities/{id}/co-occurrence (Phase 15)
- feat(pdf): /api/documents/pdfs/backfill-pages — create missing page children (Phase 14)
- feat(search): library mode now has the toolbar search field too (Phase 13)
- feat(workflows): NER per-page (local) preset for text-file folders (Phase 12)
- feat(search): Run Workflow → On Selection works on search results (Phase 10)
- feat(search): keyword cloud — browse-by-tag in empty state (Phase 9)

**Fixes**

- fix(tests): all 9 previously-failing frontend tests now green (Phase 28)
- fix(search): single-phrase query now actually enforces the phrase (Phase 20)
- fix(search): case-insensitive recent-search dedup + marker-detection tests (Phase 17)
- fix(kg): correct claims table name + canonical_name field + KG integration test
- fix(search): marker-only embedding + lozenge entity-scoped search (Phase 11)

**Docs**

- docs(state): record Phase 28-34 test-coverage sweep + 472 green
- docs(handoff): final day-2 update — 91 tests, 21 phases, all KG endpoints documented
- docs(handoff): day-2 update with phase 11-17 commits
- docs(handoff): update with phase 8-10 commits + corrected feature status

**Tests**

- test(chain): cover WorkflowChain models + chain-execution DTOs
- test(dtos): cover CheckpointTypes + BatchTypes Codable contract
- test(mcp): cover MCPServer + MCPTransport validation and Codable
- test(workflow): cover WorkflowResponseTypes DTOs + execution state
- test(comparison): cover ModelComparisonTypes DTO contract
- test(registry): cover ItemTypeRegistry handler-injection contract
- test(frontend): ErrorModel + Workflow + InspectorTab v2 fix + contract regen (Phase 27)
- test(frontend): Event + LayoutMode + Document helpers + AnyCodable (Phase 26)
- test(frontend): Artifact + Note + CacheModel coverage (Phase 25)
- test(search): marker-only embed fallback differentiates docs (Phase 24)
- test(frontend): 27 new Swift unit tests + RecentSearchesStore extraction (Phase 22)
- test(search): extend integration tests + improve did-you-mean heuristic

### 2026-05-09

**Features**

- feat(search): reindex progress shows live document count (Phase 8)
- feat(search): recent-searches history with clickable replay (Phase 6)
- feat(search): folder scope + empty-query recents + suggestion display (Phase 5)
- feat(search): did-you-mean suggestions + re-embed on edit (Phase 4)
- feat(search): query parser — quoted phrases, field scopes, NOT exclusions (Phase 3)
- feat(search): live-as-you-type, sort menu, highlight rendering, result count (Phase 2)
- feat(search): unit-norm cosine + RRF + accent-insensitive (Phase 1)
- feat(paleography+ui): thinking-mode + review pass + unified search bar + lozenge color fix
- feat(search): entity-name bridge — match query against extracted artifacts
- feat(ingest): folder ingest defaults extract_text + auto_embed = True
- feat(workflows): add Spanish paleography preset (18th-19th century)
- feat(search): blue entity lozenges are tap-to-search
- feat(library+search): per-type entity columns + index health + Xcode-style mode strip
- feat(library): native column customization for table view (#519)
- feat(inspector): blue lozenges for artifact entities (#519)
- feat(library): list-view top-right entity-type filter menu
- feat(library+preview): scrolling lozenges + preview close-X + entity refinement
- feat(library): list-row thumbnail + matched mode-strip height
- feat(search): polish empty state + Save Search button (#481)
- feat(library): entity-rich Artifacts column + horizontal view-mode strip

**Fixes**

- fix(search): drop pure-semantic noise floor (~0.2% scores)
- fix(search): each mode owns its toolbar search — no root-level .searchable
- fix(search): remove duplicate .searchable inside SearchView
- fix(search): hybrid de-dup picks max(score), not first occurrence
- fix(ui+search): pane-toolbar coherence + always-visible toolbar search + dedupe pydantic validator
- fix(library): clear-filter escape + no row-click filter hijack + lozenge truncation
- fix(search): WindowState.libraryId is non-optional UUID
- fix(library): surgical row updates from processing poll (#518 follow-up)
- fix(library): drop bogus @ViewBuilder var artifactsColumn; scope badge to OWN artifacts (#519)

**Docs**

- docs: search rewrite handoff for morning bug-test session

**Tests**

- test(search): end-to-end integration test on a real Database (Phase 4)

**Chore**

- chore(lint): silence unused-import warning on transcribe_review
- chore(session-end): 2026-05-09 hand-off — visual bugs queued

### 2026-05-08

**Features**

- feat(search): wire .searchable input + Return-to-submit (#481)
- feat(features): re-enable list/table/map view modes (#517 part 1)
- feat(preview): swipe-to-navigate sibling documents (#593)
- feat(library): processing poll + Artifacts column (#518, #519)

**Docs**

- docs: audit 0.0.3 features against 0.0.2 — most already done
- docs: pivot to re-implementing 0.0.3 features on 0.0.2 paths

**Chore**

- chore(session-end): finalize 0.0.2 + release notes + merge plan

### 2026-05-07

**Features**

- feat(llm): collect_usage() context manager for cost tracking (#852)
- feat(llm): estimated token usage logging for Apple Intelligence (#843 item 3)
- feat(llm): include_raw + usage_metadata on LangChain calls (#844 item 8)

**Docs**

- docs(state): handoff brief for #868 LLMProvider refactor
- docs: collect_usage() primitive in dev standards + MEMORY
- docs(api): document post-#872 LLM stack architecture

**Tests**

- test(integration): LLM fallback chain end-to-end (#873 — first scoped piece)

**Chore**

- chore(session-end): checkpoint state after LLM-stack overhaul

### 2026-05-06

**Features**

- feat(catalogue): enable reasoning on narrative synthesis (#859)
- feat(llm): centralize timeout formulas in _compute_timeout (#855, #862, #867)
- feat(catalogue): per-section claim_context_caps via workflow config (#865)
- feat(llm): _pydantic_to_apple_schema fail-loud on unsupported shapes (#856)
- feat(extractors): keywords use Apple's contentTagging variant (#853)
- feat(llm): use_case parameter on chat_structured (#853)
- feat(apple): contentTagging useCase (#852/#853)
- feat(extractors): migrate per-section tools to chat_structured_with_fallback (#846)
- feat(apple): subprocess timeout + heuristic token estimator (#848 proactive)
- feat(apple): supportsLocale + permissive guardrails + chunked-retry on overflow (#848/#849/#850)
- feat(fm-bridge): typed GenerationError mapping + include_schema_in_prompt (#843)
- feat(extract_all): migrate to chat_structured_with_fallback (#799/#819)
- feat(llm): chat_structured() — provider-routed grammar-constrained output (#799/#819)
- feat(fm-bridge): add structured-output mode using DynamicGenerationSchema (#799)
- feat(inspector): KG entity rows link to source page (#833)
- feat(fm-bridge): pass temperature + max_tokens through to GenerationOptions (part of #819)
- feat(prompts): catalogue narrative v2 with abstract few-shot examples (#818)
- feat(prompts): versioned prompt registry + migrate catalogue narrative (#816)
- feat(evals): prompt evaluation harness scaffold (#817)
- feat(inspector): folder KG view aggregates descendants (#826 Swift half)
- feat(workflow-editor): \$small / \$large alias options in node provider picker (#814)

**Fixes**

- fix(fm-bridge): rename main.swift → FmBridge.swift to silence @main warning (#867)
- fix(llm): route unsupported_language to $large fallback (#868)
- fix(llm): revert OpenRouter dispatch to ChatOpenAI (#844 item 6 regression)
- fix(catalogue): cap claim_context to keep narrative prompt under ~5K chars
- fix(extract_all): partial chunk failure shouldn't abort workflow
- fix(llm): wall-clock timeout on LangChain ainvoke (#844 robustness)
- fix(cleanup): proactive Apple-context overflow check (#848 proactive)
- fix(llm): bump LangChain max_retries from 6 to 10 (#844)
- fix(cleanup): migrate to chat_structured_with_fallback (#845)
- fix(transcribe): retry empty vision responses, fail file if still empty
- fix(cleanup): people dedup must not merge possessive references
- fix(catalogue): per-page records + single-fire catalogue (#837 follow-up)
- fix(catalogue): remove user aggregate (Marshal) node — wire downstream directly to transcribe (#837 actual fix)
- fix(aggregate): cache-hit fast-path also reads parallel_results + 12 unit tests (#837)
- fix(aggregate): in-tool barrier for parallel-source completion (#837 actual fix)
- fix(cache): don't cache empty parallel results + ignore stale empty entries (#834 follow-up)
- fix(workflows): aggregator defers emission until all parallel sends land (#837 reopen)
- fix(extract_all): tolerate prose-wrapped JSON from frontier guardrail fallback (#838 follow-up)
- fix(workflows): abort run when a node returns {error}, propagate SystemicErrorDetected (#839)
- fix(llm): fall back to \$large when Apple Intelligence guardrail refuses (#838)
- fix(catalogue): wire text+data inputs, skip chunking on frontier, auto-upgrade preset (#836, #835)
- fix(library): stable .id on EditorView prevents first-click grid flash (#788)
- fix(inspector): long artifact rows grow to natural height (#822)

**Refactors**

- refactor(llm): convert apple_intelligence_supports_locale to async (#857)
- refactor(llm): get_langchain_model uses init_chat_model + ChatOpenRouter (#844 items 5-7)

**Docs**

- docs(state): log overnight LLM-stack overhaul completion
- docs(state): log overnight LLM-stack overhaul plan (#872)
- docs(llm): document _pydantic_to_apple_schema supported / unsupported shapes
- docs(api): structured-output development standard (#847)

**Tests**

- test(llm): fix mock signature for use_case kwarg
- test(llm): unit tests for apple_intelligence_supports_locale (#849)
- test(llm): unit tests for chat_structured + Apple-schema converter (#847)
- test(catalogue): point chat mocks at chat_with_fallback (#838 follow-up)

**Chore**

- chore(lint): drop unused functools import after #857
- chore(contracts): refresh openapi.json snapshot to match live Swift schema

### 2026-05-05

**Features**

- feat(settings): \$small / \$large model pickers in Defaults tab (#813)
- feat(claims): include_descendants param for folder-level KG aggregation (#826)
- feat(prompts): finish system/user split sweep across all LLM tools (#815)
- feat(extract_all): per-page extraction_error artifacts (#800, #829)
- feat(prompts): system/user split, Apple-style prompts, JSON artifacts (#815, #828, #825, #824)
- feat(extract_all): combined per-page extractor + auto vision_mode + Quartz race fix
- feat(lang): English/Spanish auto-detection from source text (#809)
- feat(presets): Catalogue (Small) + (Mixed) using \$small/\$large + barrier rewire (#812, #827)
- feat(settings): \$small / \$large model aliases for portable presets (#811)

**Fixes**

- fix(splash): Fichero icon renders flat, matches engine icon styling (#793)
- fix(grid+list): scroll restored-from-launch selection into view (#808)
- fix(grid): error/processing state survives single-file gallery navigation (#791)
- fix(grid): wide thumbnails clipped to cell rect, no overflow into neighbours (#789)
- fix: strengthen no-header in catalogue prompt + Swift lint cleanups
- fix(lang_detect): English-bias for mixed-language docs (#823)
- fix(inspector): drop dead nil-coalesce on context (non-optional String)

**Chore**

- chore(session-end): catalogue pipeline + inspector V2 wrap-up

### 2026-05-04

**Features**

- feat(catalogue): per-section page + folder cleanup tools (#803, #804)
- feat(catalogue): Phase E — multi-output catalogue (#805) + Phase B relabel + tests
- feat(catalogue): Phase A — per-page entity storage (#802)
- feat(catalogue,fm-bridge): chunked synthesis + bundled fm-bridge in package resources
- feat(llm): unified Apple provider dispatch — vision() routes apple-vision to OCR
- feat(catalogue,transcribe): consolidate to one preset each + prune orphans on reinstall
- feat(catalogue): explicit input ports + edges so NER→catalogue is visible in graph
- feat(catalogue): wire NER into prompt + Apple Intelligence preset + drop export node
- feat(catalogue): consolidate to 2 workflows + drop body sections from prompt
- feat(catalogue): align prompt with legacy Generic_Catalogue library_catalogue_entry step
- feat(catalogue): direct-markdown prompt + librarian-style schema (#794)
- feat(inspector): Knowledge Graph as top-level tab + reorder Content / KG / Info
- feat(library,sidebar): Cmd+` Go Up + per-doc/folder spinner in sidebar (#785, #786)

**Fixes**

- fix(catalogue): per-page sub-chunking + transcripts feed catalogue via merge_extracts
- fix(llm): find fm-bridge in bundled engine — was silently missing
- fix(catalogue): $APPLE_INTELLIGENCE sentinel resolves to provider_type, not app_db UUID
- fix(catalogue): drop Title section — would duplicate inspector chrome
- fix(vision): Pillow-normalize TIFs + downscale large images for Apple Vision (#796)
- fix(sidebar): doc/folder spinner replaces icon, not corner overlay (#785)
- fix(engine,library): bundle PyObjC for Apple Vision OCR + persist workflow status across nav (#790, #791)
- fix(sidebar): folder spinner reads currentDocuments + Activity uses ProgressView (#785)
- fix(workflow): stop wiping user-edited preset workflows on load (#780 root cause)
- fix(workflow,sidebar): wire SidebarItemRow run path + tighten autosave + diagnostics (#785, #780)
- fix(library,toolbar): disable layout picker on folders + scroll icon list to selection (#787)

**Docs**

- docs(state): 0.0.2 down to 6 release-pipeline issues — punt + ship pass

**Tests**

- test(catalogue): align unit tests with Phase E multi-output + single-preset shape

### 2026-05-03

**Features**

- feat(library): pinch-to-zoom on the icon grid resizes thumbnails live
- feat(inspector): always render Page Content panel — folders + empty docs editable

**Fixes**

- fix(library): single-click navigates into containers when sidebar hidden (#786)
- fix(library): split scroll target into minimal vs centered (#769, #784)
- fix(library,nav): per-doc spinner via batch run path + sidebar click collapses preview (#785)
- fix(inspector): stop stomping AppKit toggleRuler so Format > Text > Show Ruler updates label (#781)
- fix(library,menu): clamp pinch zoom to pane width + ruler menu uses Toggle for live checkmark (#781, #782)
- fix(inspector,library): wire ruler toggle (#781) + smooth+raise pinch zoom (#782)
- fix(library): pinch-to-zoom actually scales icons, not just column count
- fix(workflow): autosave on changes — model selection now persisted (#780)
- fix(library): single-click context-aware on EFFECTIVE layout + arrow-key scrolls into view
- fix(library): context-aware click model — preview-visibility drives single-click behavior
- fix(library): smooth layout transition + handleDoubleClick updates selection
- fix(llm): strip outer markdown code fences from chat() and vision() responses (#776)
- fix(image-viewer): apply fit-to-window in same NSView frame as image swap (#777)
- fix(library): handleBrowserSelectionChange no longer auto-opens preview (#778)
- fix(image-viewer): minimap flash on load (#771) + 100% zoom flash on doc switch (#773)
- fix(api-client): use multi-format date parser in ArtifactService (audit class F)
- fix(api): exclude_none=True on all update endpoints (audit pass)
- fix(api-client): typed-first reads in ImportService.convertToDocument (audit)
- fix(library): single-click no longer auto-syncs detailDocument (#772 real fix)
- fix(api-client): correct extraction for typed FileType enum + bbox array
- fix(api-client): typed-first reads for all OpenAPI Document fields
- fix(api-client): read parent_id from typed schema field + revert too-eager #772 click change
- fix(library): single-click highlights only; double-click activates inspector (#772)
- fix(api): updateDocument no longer mutates parent_id (#774 data corruption)
- fix(library): icon-grid arrow-key navigation no longer recenters viewport (#769)

**Docs**

- docs(state): update STATE.md after 2026-05-03 autonomous overnight session

### 2026-05-02

**Features**

- feat(workflow): rename via context menu in workflow library (#766)
- feat(auth): engine-side shared-secret token + Swift AuthTokenMiddleware (#742)

**Fixes**

- fix(build): use provider.name match instead of providerType (LLMProvider has no providerType field; OpenAPI migration tracked in #768)
- fix(inspector): include provider in panel-collapse-state storage key (#765)
- fix(workflow): hide catalog Apple provider when picker offers Apple Vision option (#761)
- fix(engine): rename Apple → Apple Intelligence + seed built-in models (#761, #762)
- fix(engine): self-clean orphan engines + auto-shutdown on parent death
- fix(api-client): read pageContent from typed schema field, not additionalProperties
- fix(install): kill orphan engine before relaunching moved copy + capture engine log (#757)
- fix(engine): move kreuzberg cache to ~/Library/Caches + ship .py edits in release builds

**Refactors**

- refactor(engine): rename briefcase entry-point package fichero_engine → engine

**Docs**

- docs(session): CHANGELOG + 2026-05-01 session-end sentinel
- docs(site): update fichero faq + index, drop how-its-made
- docs(session-end): MEMORY + HISTORY for 2026-05-01 session

**Chore**

- chore: gitignore Xcode coverage profile (default.profraw)
- chore(release): make OpenAPI sync self-skipping + remove --skip-openapi-sync flag
- chore: remove tracked .kreuzberg cache files (now lives in ~/Library/Caches/)
- chore(release): polish build-release-dmg + create-github-release scripts
- chore(xcode): normalize path quoting in project.pbxproj
- chore(ui): boot UX, RTF editor polish, AppInstaller alert trim
- chore(api): add Apple Intelligence probe to endpoint contract (#731)

### 2026-05-01

**Features**

- feat(onboarding): first-launch wizard for AI provider + import-mode setup
- feat(apple): availability probe via fm-bridge --probe + GET /providers/apple-intelligence/probe

**Fixes**

- fix(workflow): wire 'Reset Defaults' to actually reinstall + drop dead Swift templates (#722 part 1)
- fix(image-viewer): pinch-to-zoom flash to original on release (#748)
- fix(library): folder grid full-width on launch (#749)
- fix(inspector,workflow): RTF page-content save flicker + 2 UI polish
- fix(security): apply Bearer token to raw URLSession callsites (#742)

**Docs**

- docs(state): update STATE.md with today's session work + next-session guide

**Chore**

- chore(lint): suppress wizard's unavoidable line/file-length warnings + rename .ok to .connected
- chore(release): sync OpenAPI schema engine -> Swift client before xcodebuild

### 2026-04-29

**Features**

- feat(brand): rename app display name 'Fichero Research' -> 'Fichero'
- feat: rename to com.fichero.fichero (frontend) + com.fichero.fichero.engine (backend)

**Fixes**

- fix(settings): refresh providers + Apple as first-run default
- fix(sparkle): wire production EdDSA public key + dtubb/fichero-releases appcast URL

**Refactors**

- refactor: rename top-level dirs — fichero-api -> fichero-engine, fichero-swiftui -> fichero

**Docs**

- docs: honest feature list — distinguish 'shipping' from 'work-in-progress'
- docs: backdate initial release label to 2026.04.01 Alpha (Daniel's pick)
- docs: drop residual 0.0.3 reference in release notes (CalVer migration)
- docs: switch to CalVer + Alpha — 2026.04.29 release notes + 'how it's made' page

### 2026-04-28

**Features**

- feat(llm): Apple Intelligence (Foundation Models) provider via Swift bridge (#731)
- feat(kg): per-page entity extraction with provenance (#728)
- feat(workflow): split Transcribe into Apple Vision + cloud-LLM variants
- feat(inspector): click-to-copy entity names for cross-doc search (#728)
- feat(kg): catalogue reducer consumes existing claims (#727)
- feat(inspector): Knowledge Graph section reads from /api/entities (#728)
- feat(workflow): generify catalogue_composable defaults — drop archive-specific (#726)
- feat(kg): add generic places + organizations extractors (#728/#726)
- feat(kg): extractors dual-write KnowledgeEntity + KnowledgeClaim rows (#728)
- feat(kg): annotate extractor sections with EntityType (#728)
- feat(kg): entity_writer helpers — upsert_entity + save_claim (#728)
- feat(workflow): group Workflow Library list by folder_path (#724)

**Fixes**

- fix(settings): revert to user-configured-only models (Daniel's call)
- fix(workflow): cloud Catalogue defaults use vision_mode 'llm' not 'apple'
- fix(settings): Defaults model picker pulls full LiteLLM catalog (#728)
- fix(workflow): canvas nodes read icon/color from backend tool registry (#725)
- fix(workflow): list endpoint returns all workflows when folder_path omitted (#723)
- fix(workflow): dedupe default templates + group Run Workflow menu by folder_path (#722)
- fix(inspector): strict per-document scope for Artifacts tab (#721)

**Docs**

- docs(plan): typed entity storage — revised after backend audit (#728)
- docs(architecture): typed entity storage design (#728)
- docs(agents): document Pydantic + OpenAPI contract failure modes

**Tests**

- test(kg): API-level integration tests for /api/entities + /api/claims (#728)
- test(kg): comprehensive edge case coverage for extractor KG integration (#728)

**Chore**

- chore(session-end): Apple Intelligence shipped — STATE/MEMORY/HISTORY updated
- chore(session-end): typed entity storage shipped + per-page extraction + 0.0.3 issues filed
- chore(state): update STATE.md after typed entity storage shipping
- chore: drop unused pytest import in entity_writer tests
- chore(session-end): 0.0.2 polish day — folder inspector, catalogue reducer, scope fix, template dedupe

### 2026-04-27

**Fixes**

- fix(workflow): Catalogue (composable) emits unified Catalogue artifact (#720)
- fix(thumbnail): use 3:4 portrait aspect for grid thumbnails (#718)
- fix(folder-inspector): hide preview pane and route sidebar folder click to DocumentInspector (#712)
- fix(sidebar): #711 follow-up — Label→HStack, ForEach dropDestination, library-header drop, diagnostic logs (#713)
- fix(sidebar): unify icon/text + row-body drag via .draggable Transferable (#711)

**Chore**

- chore(session-end): inspector V2 Phase 2 + ruler/find menu + V1 removal

### 2026-04-26

**Features**

- feat: save per-page artifacts on PDF page-children (#701 part 1)
- feat(inspector V2 phase 2 part 2): RTF-editable artifact panels
- feat: PUT /artifacts/{id} backend + Swift wrapper for V2 panel editing
- feat(inspector V2 phase 2 part 1): per-panel delete + cleaner timestamps

**Fixes**

- fix(inspector V2): render RTF in read view, drop timestamp, grow height
- fix(inspector V2): hide static-metadata strip — top reserved for AI attributes
- fix(inspector V2): strict per-document scope so delete sticks across navigation
- fix(inspector V2): preserve ruler/tab edits — paragraph style triggers RTF encode
- fix(inspector V2): auto-save + always-visible action buttons
- fix: per-mode badges + ingest-mode-aware delete dialog (#603 part 2 finish)
- fix: render cache-hit indicator in Activity recent files (#700)
- fix: write explicit ingest_mode metadata + expose Document.IngestMode (#603 part 2)
- fix: grid thumbnails for PDF page-children fall back to parent doc path (#703)
- fix: sidebar context-menu Run Workflow uses SSE/executionObserver path (#694)

### 2026-04-25

**Features**

- feat: inspector V2 (Display Attributes + Artifact Panels) behind feature flag

**Fixes**

- fix: sidebar folder click now populates inspector (#696)
- fix: serialize app_db access with RLock — DuckDB pending-query crashes

### 2026-04-24

**Fixes**

- fix: defer @Binding write in AttributedTextEditor.updateNSView (font size change warning)
- fix: use OpenAPI-typed fields across all service update paths (#704 pattern audit)
- fix: use OpenAPI-typed DocumentUpdate fields instead of additionalProperties
- fix: provider-dedup cleanup leaves DuckDB with pending query (#704)
- fix: always show Audio defaults + remove Embeddings picker
- fix: skip Apple in LLM provider fallback — chat() doesn't support it yet (#704)
- fix: upsert on (name,type) for providers + collapse existing dupes (#704)
- fix: make LINK ingest-mode badge visible in sidebar (#603 Part 1)
- fix: expose per-section catalogue extractors in workflow palette (#697)
- fix: optimistic delete — row disappears immediately (#705)
- fix: strip Fichero storage hash prefix from filenames in Activity view (#698)
- fix: force non-terminal nodes to .completed when run ends (#699)
- fix: fall back to any configured provider when node has none (#704 Catalogue)

### 2026-04-23

**Features**

- feat: Catalogue (composable) preset using per-section extractors (#693)
- feat: visible fan-out / fan-in badges on workflow canvas edges (#692)
- feat: explicit Aggregate node for fan-in visualization (#691)
- feat: per-section catalogue extractor tools (#690)
- feat: write_file workflow tool (per-file + aggregate modes) (#689)
- feat: surface transcription artifacts + show model + save-to-file
- feat: cache transcription artifacts by provider+model, not just doc+type
- feat: locked default workflows with auto-update (#688)
- feat: reinstall-defaults endpoint + 3-node Catalogue preset + review cleanup

**Fixes**

- fix: surface PDF page→parent promotion with warning + metadata hint (#670.1)
- fix: apply EXIF orientation after SDR decode (HDR fix regression)
- fix: decode image viewer source as SDR (HDR still leaking through #688)
- fix: lock image viewer to SDR so iPhone HEIC HDR doesn't wash UI
- fix: RTF inspector loses selection updates due to false hasChanges (#673 root cause)
- fix: restore content-aware inspector refresh (#673 regression)
- fix: add is_system column migration for workflows table (#688)
- fix: plain-language labels for workflow input source toggle (#668)
- fix: debounce inspector refresh + cheap document signature (#673 #674)
- fix: unify context menu workflow execution to SSE path + fix Catalogue artifact refresh
- fix: builder skips edges with empty or dangling endpoints
- fix: preset edges use UI schema so they render in the workflow editor
- fix: merge CatalogueArtifactPreviews into DocumentInspectorArtifactsTab

**Docs**

- docs: update 0.0.2 release notes and feature overview (#662)

**Chore**

- chore(session-end): 2026-04-23 — catalogue workflow shipped, 0.0.2 reliability complete

### 2026-04-22

**Features**

- feat: render catalogue per-section artifacts as structured tables (#682)
- feat: seed default workflow presets on library creation (#681)
- feat: catalogue writes markdown to container folder's page_content
- feat: skip_if_artifact_exists + per-section catalogue artifacts (#678, #679)
- feat: rewrite catalogue tool for nine-section structured output (#678)
- feat: un-hide catalogue-relevant tools in v0.0.1 whitelist (#677)
- feat: Run Workflow submenu in grid + sidebar context menus (#669)
- feat: Library header navigation + Workflows nav row + activity fix + site draft (#644 #650 #651 #653)
- feat: add SF Symbol icons to all sidebar section headers (#651 #644)
- feat: add embeddings provider + model picker to Settings Defaults tab (#639)

**Fixes**

- fix: preserve user-edited page_content against workflow overwrites (#672)
- fix: preserve existing test behavior under default-workflow seeding
- fix: preserve edits across navigation and external refresh (#671)
- fix: preserve user-set RTF color and font on reload (#671)
- fix: files_tool expands folder IDs to file descendants
- fix: correct libraryWorkflows type to [WorkflowSidebarItem]
- fix: resolve workflowStore scope error in LibraryView context menu
- fix: batch items pass selected_doc_ids so files_tool resolves documents
- fix: prevent stale refresh from overwriting in-progress user saves
- fix: refreshLocalContent skips folder-membership check after workflow
- fix: content tab refreshes after workflow writes page_content (#666)
- fix: selected_doc_ids dropped by LangGraph + Starting… spinner on completed runs (#666)
- fix: completed activity runs show stable coarse timestamp, not ticking seconds
- fix: Files node shows 'uses library selection' banner when drop zone is empty (#666)
- fix: files_tool empty-list config short-circuits selected_doc_ids (#666)
- fix: don't navigate to Activity on workflow run — badge + doc spinners are enough
- fix: pass browserSelection to WorkflowEditor so Files node gets doc IDs (#666)
- fix: workflow list navigates into editor (Activity-style split layout)
- fix: transcription artifact save + page-level OCR propagation (#666)
- fix: suppress fastembed pooling warning + pin to <=0.5.1 (#640)
- fix: annotate PDFPageView.Coordinator @MainActor to resolve concurrency warnings (#641)
- fix: hide internal LangGraph node names in Activity Progress view (#654)
- fix: add zoom toolbar to PDF previews + AI Providers menu icon (#656 #569)
- fix: Activity row icon+style, ViewBuilder return, activity persistence (#655 #642 #648)
- fix: activity sidebar navigation + workflow first-click + elapsed 'ago' (#647 #646 #649)
- fix: exclude folder docs from workflow 'On Selection' target (#652)
- fix(pdf): sync thumbnail grid selection when swiping pages (#595)
- fix(pdf): switch to single-page + swipe navigation (#595)
- fix: sidebar row icon/text clicks unreliable — add simultaneousGesture (#645)
- fix: revert window-level drop to Transferable API to fix sidebar click regression (#645)
- fix: auto-route root-level file drops to Inbox (#598)
- fix: show real import error messages and fix root-level Finder drop (#598)
- fix: clean up fichero-drop temp dirs after COPY import (#626)
- fix: use COPY mode for temp-dir drop URLs so backend persists file (#626)
- fix: artifacts endpoint includes parent artifacts when querying a page doc (#633)
- fix: include filename + progress in per-file node log messages (#635)
- fix: cancelExecution archives to completedExecutions; ActivityLogView uses task(id:) for live→done transition
- fix: Activity Overview live card shows per-file document progress (#636)
- fix: filter LangGraph internal node names (_aggregate, branch:to:) from Console + Graph tabs (#628)
- fix: hide source-tool columns (Collection, Files) from Output Log — no per-file data (#632)
- fix: collection_tool respects selected_doc_ids — run on selection no longer runs whole folder (#634)
- fix: clean up cancelHandlers in endExecution + task(id:) for safe reload
- fix: Activity tabs now show live and archived execution data (#627 #629 #630 #631 #637)

**Tests**

- test: Swift coverage for catalogue previews and v0.0.1 tool allowlist
- test: backend coverage for catalogue, default workflows, skip-if-done
- test: end-to-end regression tests for files_tool selection (#666)
- test: add unit tests for #666 transcription-save fixes
- test: fix weak assertion and remove unused import in sources test

**Chore**

- chore(session-end): STATE.md — #672 closed, 0.0.2 reliability work complete
- chore(session-end): STATE.md — catalogue workflow landed
- chore(session-end): update STATE + HISTORY — #666 fix committed, server restart needed
- chore(session-end): #666 fixed — update STATE + HISTORY
- chore: update STATE.md — code tasks closed, release pipeline next
- chore: update STATE.md — non-blocking tasks + 0.0.3 merge plan
- chore(session-end): archive session — #643 #656 #569 #654 #641 #640 #607 #598 done
- chore: commit pending config/doc changes before session end
- chore: fix all SwiftLint violations (#643)
- chore: commit pending config/doc changes before session
- chore: update CONTINUE.md timestamp
- chore(session-end): archive session — #618 #602 done in 0.0.3; 0.0.2 still blocked
- chore(session-end): archive session — all 0.0.2 issues blocked
- chore(session-end): update STATE — all 0.0.2 issues blocked on Daniel input
- chore: update CONTINUE timestamp
- chore(session-end): update STATE + HISTORY — all 0.0.2 issues blocked on Daniel input
- chore(session-end): close #626, update STATE + HISTORY
- chore: session-start timestamp
- chore(session-end): close #639 #635 #633 batch, update STATE + HISTORY
- chore(session-end): close #627-637 batch, update STATE + HISTORY
- chore: clarify PR workflow — Claude creates and merges PRs
- chore: update branch discipline — PR workflow instead of direct push

### 2026-04-21

**Features**

- feat: Activity browser view (Option A) + artifact mid-run refresh

**Fixes**

- fix: text thumbnail for JSON and other text files (#625)
- fix: toolbar run workflow now navigates to Activity with live progress (#609)
- fix: sips JPEG fallback, file copy mode, sidebar ownProcess drag (#624 #626 #623)
- fix: three 0.0.2 bugs — artifacts, pickle, activity sidebar
- fix: seed Apple provider + pre-warm embeddings at startup
- fix: unify workflow execution to SSE path + fix activity layout (#609)
- fix: sync selectedDocument from detailDocument; add Run on Collection workflow option (#609)
- fix: pass selected_doc_ids to workflow execute so Files node receives UI selection (#609)
- fix: warn and fall through when selected_doc_ids present but library_path missing (#609)
- fix: files_tool resolves documents from UI selection via selected_doc_ids (#609)
- fix: bolder sidebar section headers with primary foreground (#614)

**Tests**

- test: strengthen selected_doc_ids skip test with documents assertion (#609)
- test: failing tests for files_tool selected_doc_ids resolution (#609)

**Chore**

- chore(session-end): update STATE.md — bug batch done, 6 issues closed
- chore(session-end): no-op session — all 0.0.2 tasks need Daniel on-device; write BLOCK.md
- chore(session-end): archive #614 session to HISTORY.md
- chore(session-end): STATE.md — #614 done, on-device sweep gate

### 2026-04-20

**Features**

- feat: hide icon-grid panel toggle (⌘⇧G) for focus mode (#616)
- feat: PDF scroll→grid/inspector sync behind feature flag (#591 #592)
- feat: ingest-mode badges + delete-copy (#603)
- feat: add ⏱ OSLog startup instrumentation (#619)
- feat: reorder saved searches and workflows in sidebar (#611)
- feat: between-row spacer drop targets for insertion-line drops (#607)

**Fixes**

- fix: add .mov drop debug logging + canLoadObject fallthrough fix (#600)
- fix: lower icon/list grid column minimum width 260→180 (#622)
- fix: PDF grid selection follows scrollbar drag (#591)
- fix: drop 'Global' library header row (#608)
- fix: Run Workflow enabled when preview document has selection (#609)
- fix: bump grid icon/map zoom cap from 3x to 5x (#604)
- fix: lower sidebar min width from 250 to 180 (#615)
- fix: route kreuzberg cache to app-data folder, not cwd (#589)
- fix: sidebar Delete context-menu actually fires confirmation (#613)
- fix: Inbox not reorderable + restore cross-hierarchy drop lines (#621, #606)
- fix: remove insertion-spacer rows from sidebar (#620)
- fix: Inbox not draggable (#621) + collapse spacer row padding (#620)

**Performance**

- perf: tighten backend health poll interval (#619)

**Tests**

- test: skip contract/endpoint tests when fixtures absent (#594)

**Chore**

- chore(session-end): checkpoint state — #591/#592 done, #616 remains
- chore: remove BLOCK.md — branches merged, autonomous loop resuming
- chore(session-end): checkpoint state — all autonomous items done, BLOCK.md written
- chore(session-end): checkpoint state — #603 + #591/#592 done, #616 remains
- chore(session-end): checkpoint state — #600 fixed, 4 autonomous items remain
- chore(state): #600 done, advance to #603
- chore(session-end): checkpoint state — #622 done, #594 closed, #619 instrumented, 17 issues remain
- chore(state): mark #594 closed and #619 instrumented in autonomous execution order
- chore(state): point #622 reference at cherry-picked SHA on 0.0.2
- chore(session-end): checkpoint state — #622 done, 19 issues remain
- chore: commit pending config/doc changes before session
- chore(state): tag 0.0.2 closeout plan as autonomous-safe vs needs-daniel
- chore(session-end): 0.0.2 closeout plan — 4 batches across 20 open issues
- chore(session-end): archive 0.0.2 bug sprint + PDF revert
- chore: update STATE.md with 0.0.2 bug sprint progress
- chore(session-end): checkpoint 2026-04-20 — spacer-row insertion drops landed

### 2026-04-18

**Features**

- feat: cross-hierarchy insertion drop on nested folder children + cycle guard (#607)
- feat: cross-hierarchy insertion-line drop in top-level unifiedRows (#607)
- feat: right-hover disclosure chevron on category section headers (#612)
- feat: native .onMove insertion lines + regression tests (#607, #612)
- feat: plain Return keyboard shortcut on Rename menu command (#612)

**Fixes**

- fix(backend): declare sort_order on Document model so reorder persists (#607)
- fix(backend): migrate documents.sort_order + skip thumbnails for non-image files
- fix: .selectionDisabled() on library + category header views (#612)
- fix: sidebarReorderedDocIds tolerates mixed-kind siblings (#607)
- fix: SidebarActions: Equatable (always true) — stops "multiple times per frame" (#612)
- fix: prevent library header from writing library:UUID to selectedItemId (#612)
- fix: remove double-tap rename gesture — it was swallowing single clicks (#612)
- fix(backend): create folder Document when importing into a parent (#610)
- fix: SidebarSelectionInfo: Equatable — reduces FocusedValue warnings (#612)
- fix: restore .tag(item.id) on top-level rows (#612)
- fix: drop foreground color overrides — native sidebar selection contrast (#612)
- fix: add selection binding to unified List — selection was dead (#612)
- fix: drop redundant row TapGesture — makes .draggable deterministic (#612)
- fix: sidebar drop — single .onDrop(of: [UTType]) on folderLabel (#612, #610)
- fix: move .draggable to label content, keep .dropDestination at body — #612
- fix: switch sidebar drop to .dropDestination (Transferable API) — #612, #610
- fix: move .onDrop to body level so folders are draggable (#612)
- fix: hoist .draggable to row-body level so macOS List's drag detection arms (#612)
- fix: convert rename double-tap to simultaneousGesture so drag can arm (#612)

**Performance**

- perf: cache thumbnails + display images in StorageServiceGenerated (#605, #612)
- perf: decode thumbnails off main thread — fixes click-then-wait (#605, #612)

**Refactors**

- refactor: inline sidebarDropRoute + urlLoadStrategy classifier helpers
- refactor: flatten per-category DisclosureGroups in library sections

**Style**

- style: SimpleSidebar-inspired section headers + native accent selection (#614)

**Chore**

- chore: remove debug HUD + drop instrumentation; file insertion-line limitation (#607)
- chore(debug): instrument sidebar drop handlers + .dropDestination fires (#607)
- chore(session-end): revert nested cross-hierarchy drop + checkpoint
- chore(session-end): checkpoint 2026-04-18 — sidebar overhaul
- chore(debug): add sidebar selectedItemId HUD (DEBUG only) (#612)
- chore: trim historical comment blocks + gate debug logs + reduce UTTypes
- chore: delete pre-unified mode-sidebar views (−1,112 LOC)
- chore: delete dead LibrarySidebarContent alt render path
- chore: fix swiftlint issues + add sidebar visual preview

### 2026-04-17

**Features**

- feat: sidebar folder/doc reorder via native .onMove insertion lines (#607)
- feat: native blue insertion line for sibling reorder via .onMove (#580)
- feat: VoiceOver labels on sidebar library headers (#584)
- feat: VoiceOver labels, hints, and expansion state on sidebar rows (#584)
- feat: Finder-style solid-fill sidebar drop highlight (#585)
- feat: cross-section folder drops in sidebar (#585, Step 9)
- feat: SidebarItemKind classifier for cross-section drop routing (#585)
- feat: sort sidebar documents by sortOrder first (#572, Step 11 partial)
- feat: double-click on sidebar label starts inline rename (#585)
- feat: add sortOrder to Swift Document model (#572)
- feat: PDF preview ↔ grid selection sync (#586)
- feat: PDFPageView supports scrollable multi-page mode (#578 refinement)

**Fixes**

- fix: replace outer .onTapGesture with .simultaneousGesture to restore drag (#612)
- fix: use loadFileRepresentation for content-only UTI drags (Finder .jpg)
- fix: optimistic accept + diagnostic logging for sidebar drops
- fix: grid refreshes immediately when a doc moves to a different folder
- fix: Finder JPG/folder drops no longer bounce back to source
- fix: leaves aren't drop targets + correct Finder UTI routing
- fix: unify sidebar drop handling into single .onDrop so Finder drags work
- fix: scope drop highlight to parent row only + tighten row density
- fix: use 3-param .dropDestination so isTargeted fires on internal drags (#598)
- fix: whole-row drop targets cover chevron and indent area (#598)
- fix: two real bugs found in sidebar code review (chain ID, drop-beside)
- fix: Actual Size button respects TIFF pixel dimensions, not DPI-logical size (#599)
- fix: image pinch-zoom sticks (#596, 2nd attempt — gate sync on gesture state)
- fix: accept all URL-producing drag sources, not just ones advertising public.fileURL (#600)
- fix: image pinch-zoom no longer snaps back to fit scale (#596)
- fix: restore inline sidebar drop modifiers (revert Step 6 extension)
- fix: case-insensitive sidebar file picker for uppercase extensions
- fix: PDF pinch-zoom no longer snaps back to fit scale (#588)
- fix: folder drops preserve folder URL (swap Transferable → NSItemProvider, #587)
- fix: PDF pages no longer nest as sidebar sub-rows (#581)
- fix: LibrarySectionHeader accepts Finder file drops at library root (#582)

**Refactors**

- refactor: extract URLLoadStrategy pure function + 7 unit tests
- refactor: extract sidebarDropRoute(for:) + 7 unit tests to pin routing
- refactor: hoist LibrarySectionHeader body into sub-ViewBuilders
- refactor: isolate sidebar drop logic into shape-specific modifiers (#585)
- refactor: extract extractActualId to free function, test real logic
- refactor: remove dead SidebarSectionHeader struct

**Docs**

- docs(agents): tighten SwiftUI testing loop + add agent-team delegation

**Style**

- style: Finder/Mail-style sidebar highlight — grey row + blue selected icon/text

**Chore**

- chore(audit): unify two straggler Logger subsystems missed in 51475b07
- chore(session-end): 2026-04-17 session 4 final — sidebar deep review + cleanup
- chore: unify Logger subsystems on com.tubb.Fichero (bundle id)
- chore: delete dead sidebar code from 2026-04-17 review
- chore(session-end): 2026-04-17 session 4 — 10+ commits, regressions reverted/refixed
- chore(deps): fix all 9 Dependabot alerts on site/ npm deps (#601)
- chore(session-end): 2026-04-17 session 3 (final) — 15 commits, sidebar core shipped
- chore(session-end): 2026-04-17 session 3 — sidebar plan drafted + 4.5 steps shipped
- chore(agents): make three-leg Swift check non-negotiable
- chore(session-end): 2026-04-17 session 2 — peekaboo MCP + AGENTS.md hardening
- chore: gitignore kreuzberg extraction cache (#589)
- chore(session-end): 2026-04-17 — 9 bugs closed, sidebar + PDF hardening

### 2026-04-16

**Features**

- feat: interactive PDFView in preview pane — text selection, copy, find (#578)
- feat: top-level sidebar .onInsert for library-root file drops (#571)
- feat: PDFs become containers; each page is its own Document (#568)

**Fixes**

- fix: remove .onInsert(of:) — SwiftUICore crash on folder drops (#571, #576)
- fix: drop-highlight covers full List row, not just label width (#571)
- fix: refresh() reloads selected collection's children too (#576 partial)
- fix: suppress iconsView container focus ring (#575)
- fix: auto-select newly created folder (#573)
- fix: PDF selection drills into pages, not single-item gallery (#577)
- fix: sidebar icon uses fileType before docType (#574)
- fix: sidebar drop-target highlight actually visible (#571 retest follow-up)
- fix: PDFs appear in sidebar with pages as children (#570)
- fix: use .formStyle(.grouped) on all settings tabs (#556)
- fix: row drop-highlight via .background + wire .onInsert between rows (#571)
- fix: sidebar drop highlight must use .listRowBackground, not .background (#571)
- fix: sidebar drop highlight + leaf-file sibling imports (#571)
- fix: magnifier shortcuts + allow zoom below 1x (#566, #567)
- fix: trackpad pinch-to-zoom in image preview (#562)
- fix: middle-truncate document names in icon grid (#559)
- fix: remove Quick Look, restore sidebar arrow keys, add Option+arrow pane cycling (#560 #563 #564 #565)
- fix: magnifier Y direction inverted — remove redundant Y-flip (#546)
- fix: workflow dispatch feedback + silence observer double-init log (#548 #552)
- fix: drag-drop refresh race + local PDF thumbnails (#551 #554)
- fix: inspector placement, focus ring, context menu, settings width, lib paths (#549 #550 #553 #555 #556 #557 #558)
- fix: crash on launch — orphaned .focusable()/.focused() in standard+widescreen layouts
- fix: SwiftLint function length, FeatureManager test, unused warnings
- fix: placeholder text, drag-drop ID, first-click focus, magnifier offset (#544-#547)
- fix: magnifier Y-offset, settings layout, import mode setting (#539 #541 #542)
- fix: remove full-window drop highlight — sidebar shows per-folder targeting (#540)
- fix: use overlay scroll bars and correct preview background (#538 #532)
- fix: subfolder selection — child rows now handle their own taps (#543)
- fix: icon list min width, magnifier shortcut, preview bg, menu order (#532 #534 #537)
- fix: restore preview document on relaunch from browserSelection
- fix: use global coordinate space in ResizableDivider to stop oscillation (#535)
- fix: eliminate jumpy inspector resize by removing .transition (#535)
- fix: widen ResizableDivider hit area + fix workflow toolbar color (#535 #536)
- fix: replace widescreen HSplitView with HStack + ResizableDivider (#533)
- fix: clip NSScrollView ruler via masksToBounds instead of disabling it
- fix: disable ruler in inspector text tab — caused horizontal line artifact
- fix: hide EditorView header bar in widescreen mode to eliminate top line
- fix: clip preview pane in widescreen mode to prevent toolbar line bleed
- fix: ensure centerContent fills available HStack width on first render (#529)
- fix: correct content width on restart and restore preview selection (#529)
- fix: animate inspector panel slide to match left sidebar transition (#529)
- fix: use fixed-width inspector with draggable divider instead of HSplitView (#529 #530)
- fix: replace .inspector() with HSplitView for reliable inspector panel (#529 #530)
- fix: move .inspector() outside NavigationSplitView detail column (#529 #530)
- fix: remove GeometryReader inspector width tracker — caused layout corruption (#530)

**Performance**

- perf: defer user library restoration off main thread + add startup timing logs

**Tests**

- test: guard 0.0.2 PDF-as-container behaviour with Swift unit tests
- test: add tests for drop handler ID, magnifier coords; document Xcode MCP tools
- test: add unit tests for inspector layout, file types, and selection (#525-#535)

**Chore**

- chore(session-end): #556 + #570 fixes, durable memory
- chore(session-end): sidebar drag-drop + bugs filed (#556 reopen, #569-572)
- chore(session-end): checkpoint state — PDF-as-container, magnifier, Swift tests
- chore(session-end): checkpoint state

### 2026-04-15

**Features**

- feat: add presentation file type (pptx, ppt) end-to-end
- feat: add spreadsheet file type (csv, xlsx, xls, ods) end-to-end
- feat: add csv, rtf, mobi cases to Swift FileType enum (#516)

**Fixes**

- fix: restore inspector tab bar, track inspector width, fix SwiftLint violations (#525-#531)
- fix: inspector blank space, sidebar highlight, tab title, content tab (#521-#524)
- fix: repair OpenAPI schema drift and drag/drop security-scoped access (#383)

**Tests**

- test: add backend image ingest metadata tests (#384)

**Chore**

- chore(session-end): #383/#384/#516 done — #385/#520 await Daniel manual test
- chore: update kreuzberg extraction cache
- chore(session-end): checkpoint state — 0.0.3 worktree ready, milestone workflow documented
- chore: document milestone-worktree pattern, two-ahead rule
- chore: restructure 0.0.2 scope — bugs + backend merge + Sparkle; search wiring stays in 0.0.3
- chore(session-end): checkpoint state — milestone restructure complete, bug priority rule wired

### 2026-04-14

**Fixes**

- fix(#460): remove duplicate X-Fichero-Library-Path header from migrations routes
- fix(#460): replace gt=0 with ge=1 in MigrationRunRequest for OpenAPI 3.0 compat
- fix(#460): add typed Pydantic response models to all route handlers
- fix(#460): local_models route — replace dict returns with typed Pydantic response models for OpenAPI schema generation
- fix(#460): ingest.py — add return type annotations to _resolve_default_db and _run_async
- fix(#460): llm.py — add return type annotation to get_langchain_model
- fix(#460): routes conventions pass — typed request/response models, return annotations
- fix(#460): main.py — remove redundant db_manager import in lifespan
- fix: resolve all 3 pre-existing test failures (#460)
- fix: update mock targets in test_providers.py after llm.py split (#460)
- fix: remove unused DocType import in iiif.py (ruff F401) (#460)
- fix: serialize TaskQueue DuckDB writes with threading.Lock — fixes 11 async test failures (#460)

**Refactors**

- refactor: split storage.py (1004 lines) into storage + storage_snapshots (#460)
- refactor: split workflows/tasks.py (1091 lines) into 3 modules (#460)
- refactor: split workflow_execution/core.py (1352 lines) into 3 modules (#460)
- refactor: split research_agents.py (1034 lines) into 4 focused modules (#460)
- refactor: split llm.py (1056 lines) into 3 files (#460)
- refactor: split workflows/registry.py (1062 lines) into 2 files (#460)
- refactor: split workflows/tools/llm_base.py (1078 lines) into 2 files (#460)
- refactor: split workflows/activity.py (1249 lines) into 3 files (#460)
- refactor: split graph_exploration.py (1259 lines) into 2 files (#460)
- refactor: split providers.py (1415 lines) into 3 focused modules (#460)
- refactor: split db.py (1447 lines) into 4 focused modules (#460)
- refactor: split mcp_server.py (2055 lines) into 4 focused modules (#460)
- refactor: split workflow_execution.py (2188 lines) into 4-module package (#460)
- refactor: split knowledge_graph.py (2378 lines) into 5-module package (#460)

**Docs**

- docs: milestone restructure + release process documentation

**Chore**

- chore: session planning — milestone restructure, new issues, STATE.md update
- chore(session-end): checkpoint state
- chore: update STATE.md — all tests green, 0.0.2 clean ahead of 0.0.1 release
- chore(session-end): checkpoint state — Swift client pipeline clean
- chore(session-end): checkpoint state after typed response model pass
- chore: remove old flat route files superseded by split subdirectories (#460)
- chore: update STATE.md and HISTORY.md after file-splitting pass

### 2026-04-13

**Features**

- feat(#460): wire 11 staged routes into dev feature tier

**Fixes**

- fix: canonical knowledge routes and test coverage — Annotated pattern, async tests (#460)
- fix(#460): surface swallowed exceptions with logger.debug
- fix(#460): promote inline stdlib imports to module level — round 3
- fix(#460): promote inline stdlib imports to module level — round 2
- fix(#460): promote inline stdlib imports to module level across 12 files
- fix(#460): workflow_execution, tasks — promote inline imports to module level
- fix(#460): remove pykeen optional fallback; archive legacy resources
- fix(#460): research tool, ingest route — promote datetime import to module level
- fix(#460): activity, claim_links, graph_exploration, providers, predictions, tasks, knowledge_graph, research_agents, search_explain — promote inline imports to module level
- fix(#460): action_library.py — remove deprecated Pydantic v1 class Config
- fix(#460): iiif.py — replace deprecated Pydantic v1 class Config with ConfigDict
- fix(#460): main.py, model_comparison.py — move late imports to module level
- fix(#460): core modules — consistency and standards pass
- fix(#460): artifacts, migrations, mcp_tools, workflows — standards pass
- fix(#460): storage.py — consistency and standards pass
- fix(#460): search.py, chat.py — consistency and standards pass
- fix(#460): folders.py — consistency and standards pass
- fix(#460): documents.py — consistency and standards pass
- fix(#460): main.py — consistency and standards pass
- fix: restore research_models.py and test file to HEAD-compatible versions
- fix: correct multilingual route prefix and repair task test regressions

**Docs**

- docs: update route tier docs — staged routes now wired as dev-tier
- docs(#460): update architecture docs to match reality; delete dead script
- docs: session-end 2026-04-13 — branch consolidation complete

**Tests**

- test: complete route coverage for all 6 remaining modules + fix iiif bug
- test: add route tests for 10 remaining modules + fix mcp_tools bugs
- test: add activity and local-models route tests
- test: add batch, migrations, and storage route tests
- test: add claim-links and background tasks route tests
- test: add comprehensive route test coverage + fix route ordering bugs

**Chore**

- chore(#460): remove detritus from fichero-api
- chore(session-end): checkpoint state
- chore: repo cleanup — agent-generic docs, remove stale files

### 2026-04-11

**Features**

- feat(#422): fix MCP tools router path to /api/mcp/tools/knowledge/*
- feat(#421): use multilingual-aware normalization in knowledge graph routes
- feat(#420): register tasks router in main.py
- feat: implement canonical FastAPI knowledge write path and route surface (#364)
- feat: add MCP knowledge adapter tests for issue #371
- feat: add multilingual baseline for claims/entities and cross-language retrieval (#370)
- feat: add reindex/repair jobs and metrics recomputation workers (#369)
- feat: add knowledge migration/backfill tooling with dry-run and rollback (#368)
- feat(#434): add search views API endpoints (table, grid, map)
- feat(#428): add IIIF image server API endpoints
- feat(#427): add graph traversal and subgraph extraction endpoints
- feat(#439): add interpretations workspace API endpoints
- feat(#436): add contradiction evidence API endpoints
- feat(#435): register review_queue router in main.py
- feat: optional latent inference track (PyKEEN) (#429)
- feat: NetworkX derived graph reasoning integration (#430)
- feat: human-in-the-loop orchestration policy for agent writes (#426)
- feat: advanced graph exploration backend (#431)
- feat: activity stream enhancements (#425)
- feat: search explanation backend (#438)
- feat: claim review queue backend (#440)
- feat: thin MCP adapters for canonical knowledge APIs (#422)
- feat: multilingual baseline for claims/entities and cross-language retrieval (#421)
- feat: background task system for reindex and metrics (#420)
- feat: migration framework CLI, tests, and fixes (#419)

**Fixes**

- fix: stabilize sources routes and harden backend security paths (#364)

**Docs**

- docs: archive session end
- docs: archive session end - no tasks, 5 PRs awaiting review
- docs: archive session end - no unblocked tasks, 5 PRs ready for review
- docs: archive session end summary
- docs: update STATE.md and HISTORY.md - 5 PRs ready for review (0.0.2 + 0.0.3)
- docs: archive session summary to HISTORY.md
- docs: update STATE.md and HISTORY.md - PR #455 ready for review
- docs: update STATE.md and HISTORY.md - Issue #364 complete, 0.0.2 milestone done
- docs: add MCP Knowledge Adapter pattern to MEMORY.md
- docs: update STATE.md and HISTORY.md - Issue #371 complete, 0.0.3 milestone done
- docs: update MEMORY.md with FastAPI route registration pattern, STATE.md cleanup
- docs: update STATE.md and HISTORY.md - Issue #370 complete
- docs: add session summary to HISTORY.md
- docs: update STATE.md - Issue #369 complete
- docs: update STATE.md - Issue #368 complete, branch ready for PR
- docs: update STATE.md for #434 completion
- docs: mark 0.1.0 milestone complete
- docs: update STATE.md for #428 completion
- docs: update STATE.md for #427 completion
- docs: mark 0.0.5 milestone complete
- docs: update STATE.md for #425 completion
- docs: mark 0.0.4 milestone complete, update STATE.md
- docs: update STATE.md for #438 completion
- docs: update STATE.md and HISTORY.md for #436 completion
- docs: update STATE.md and HISTORY.md for #435 completion
- docs: update STATE.md and HISTORY.md for #422 and 0.0.3 milestone completion
- docs: update STATE.md and HISTORY.md for #421 completion
- docs: update STATE.md and HISTORY.md for #420 completion
- docs: update STATE.md and HISTORY.md for #419 completion
- docs: update STATE.md with sources implementation status
- docs: sources implementation notes for #364
- docs: update STATE.md - 0.0.2 has 1 remaining issue (#364)
- docs: update STATE.md - 0.0.2 complete, next session plan
- docs: update MEMORY, STATE, HISTORY with #429 completion
- docs: update MEMORY, STATE, HISTORY with #430 completion

**Chore**

- chore: update CONTINUE.md
- chore: update CONTINUE.md timestamp
- chore(session-end): update STATE.md, HISTORY.md, MEMORY.md - complete canonical route pattern
- chore: commit pending config/doc changes before session
- chore: session-end update memory and state for backend-first loop
- chore: session-end 2026-04-12 - sources routes implementation
- chore(session-end): checkpoint state
- chore(session-end): update STATE.md, HISTORY.md, MEMORY.md for #426
- chore: update STATE/MEMORY after graph exploration (#431)
- chore: update STATE/MEMORY after contradiction triage (#436)
- chore: update STATE/MEMORY after activity stream enhancements (#425)
- chore: update STATE/MEMORY after interpretations workspace (#439)
- chore: update STATE/MEMORY after search explanation (#438)
- chore: update STATE/MEMORY after review queue (#440)
- chore: update STATE/MEMORY after MCP adapters (#422)
- chore(session-end): checkpoint state after multilingual baseline (#421)
- chore(session-end): checkpoint state [skip ci]

### 2026-04-10

**Features**

- feat: implement Agent Research (Layer 0) routes and models (#390)
- feat: migration framework with dry-run, rollback, audit trail (#419)
- feat: implement apply_prediction to create claim links from PyKEEN model

**Fixes**

- fix: Implement SSRF protection for Phase 4 research tools (#398)
- fix(security): Implement HIGH severity fixes for Phase 5 (#408)

**Docs**

- docs(session-end): update MEMORY, STATE, HISTORY for #419 migration work
- docs: PR #417 merged — 0.0.2 release complete
- docs: PR #417 conflicts resolved — ready for review
- docs: PR #417 has merge conflicts — needs resolution
- docs: PR #417 created — 0.0.2 release to main
- docs: all security issues closed — 0.0.2 milestone complete
- docs: close #391 — security review complete
- docs: update STATE with merged security PRs
- docs: ALL PHASES COMPLETE — 6 security PRs ready for merge (#415)
- docs: Phases 5&6 complete, ready for Phases 7&8 (#414)
- docs: Phase 3 complete, all security PRs ready (#413)
- docs: Phase 2 complete, ready for Phase 3 Security Hygiene (#412)
- docs: Phase 1 complete, ready for Phase 2 Architecture Compliance (#411)
- docs: update STATE.md — all PR branches rebased, Phase 1 unblocked
- docs: update STATE.md with Phase 0 pre-flight completion (#410)
- docs: Phase 0 pre-flight checklist report for security PRs (#410)
- docs: Session end — code quality review plan ready for automation
- docs: Add automated code quality review plan with GitHub issues (#416)
- docs: Update HISTORY.md with HIGH severity fixes
- docs: Log Phase 3 security audit — Phase 1-5 complete
- docs: Update STATE.md — Phase 1-5 security audits complete
- docs: Log Phase 2 security audit to HISTORY.md (#404)
- docs: Update STATE.md with Phase 2 security audit (#404)
- docs: Log Phase 1 security audit to HISTORY.md (#402)
- docs: Update STATE.md with Phase 1 security audit (#402)
- docs: Log Phase 5 security audit to HISTORY.md (#400)
- docs: Update STATE.md with Phase 5 Integration security audit (#400)
- docs: Log PR #399 creation to HISTORY.md
- docs: Update STATE.md with PR #399 reference
- docs: Log Phase 4 SSRF fixes to HISTORY.md
- docs: Update STATE.md with Phase 4 SSRF fixes completion status (#398)
- docs: Update STATE.md and MEMORY.md with Phase 4 SSRF security audit findings (#398)
- docs: STATE.md — next session entry point for Phase 4 SSRF review
- docs: Phase 1-5 systematic code review plan — GitHub issues updated
- docs: Phase 1-5 code review complete — comprehensive verification
- docs: update MEMORY.md and STATE.md to reflect 0.0.2 branch rename

**Tests**

- test: fix integration tests for missing endpoints and error handling (#391)
- test: fix batch integration tests activity assertion (#391)
- test: fix MCP workflow integration tests and sync OpenAPI schema (#391)

**Chore**

- chore(session-end): update MEMORY, STATE, HISTORY with backend task creation
- chore: update continue timestamp
- chore(session-end): archive release completion, next focus 0.0.1
- chore(session-end): archive release completion, lean STATE
- chore(session-end): archive conflict resolution, lean STATE
- chore(session-end): archive conflict detection, lean STATE
- chore(session-end): archive PR creation, lean STATE entry
- chore(session-end): archive final work, lean STATE entry
- chore(session-end): archive security merge, lean STATE entry
- chore(session-end): archive final phase, lean STATE entry
- chore(session-end): archive history, lean STATE for Phases 7&8
- chore(session-end): archive Phase 3, lean STATE entry point
- chore(session-end): archive history, lean STATE for Phase 3
- chore(session-end): archive to HISTORY, lean STATE entry point
- chore(session-end): archive branch rebase history, lean STATE.md entry point
- chore(session-end): archive Phase 0 completion, update STATE.md entry point (#410)
- chore: add continue timestamp
- chore: session-end auto-commit
- chore: commit pending config/doc changes before session
- chore: update STATE.md - Phase 5 complete, Issue #391 closed
- chore: update STATE.md - PR #397 closed, Issue #390 complete
- chore: update STATE.md with Phase 5 quality gates assessment (#391)
- chore: update STATE.md with integration test progress
- chore: update STATE.md with batch integration test fixes
- chore: update STATE.md session log
- chore: update STATE.md with Phase 5 progress
- chore(session-end): update HISTORY, MEMORY, and STATE for Phase 4 completion
- chore: rename planning branch to 0.0.2 for implementation
- chore(session-end): update STATE.md and MEMORY.md with branch context and skills relocation
- chore: update STATE.md — Phase 1 done, moving to Phase 2
- chore: apply ruff formatting to fichero_backend
- chore: apply ruff formatting to Python source files

### 2026-04-09

**Features**

- feat: persist PyKEEN prediction artifacts (#387)
- feat: wire PyKEEN prediction generation route (#387)

**Chore**

- chore: sync remaining worktree changes

### 2026-04-03

**Features**

- feat: add connection error UI and populate library size column (#313 #314 #315)
- feat: XMP sidecar support for image metadata ingestion (#361)
- feat: library snapshot and restore with DuckDB Parquet export (#363)
- feat: general mutation log with undo/rollback for KG entities (#362)
- feat: entity merge/split with full audit trail and undo (#367)

**Style**

- style: fix 8 SwiftLint violations across 4 SwiftUI view files (#395)

**Chore**

- chore: consolidate HISTORY.md — add #363/#361 to today and #392 to yesterday
- chore: add BLOCK.md — all remaining tasks require human input
- chore: update STATE.md after 2-task autonomous session
- chore: update CONTINUE.md timestamp
- chore: archive #367/#362 completion — merge/split/undo + mutation log/rollback done
- chore: update STATE.md — #367 merge/split/undo, #362 mutation log done
- chore: archive 2026-04-03 session to HISTORY.md
- chore: update STATE.md — #395 SwiftLint done, Phase 1 tracking corrected

### 2026-04-02

**Features**

- feat: add 4 MCP tools — predictions, circle navigation (#392)
- feat: add curated_only convenience filter to GET /claims endpoints
- feat: add entity alias-map endpoint and name/alias claim filter (#366)
- feat: add SourceMetadata model with citation validation (#365)
- feat: add Phase 1 SwiftUI views — OntologyBrowser, EpistemologyGraph, PredictionReview
- feat: add HermeneuticsServiceGenerated and InterpretationPanelView for Phase 2
- feat: add KnowledgeGraphServiceGenerated and ClaimInspectorView for Phase 1
- feat: Layer 0 — Research Agent workflow tools (Phase 4)
- feat: Entity alias-aware claim retrieval (#366)
- feat: Phase 4 — Research Agent MCP tools (Layer 0)
- feat: Phase 4 Layer 0 — Research Agents models, routes, and tests
- feat: Phase 3 — Mind Palace (Layer 6) models, routes, MCP tools, tests
- feat: Phase 2 — Hermeneutics layer (Layer 5) models, routes, and MCP tools
- feat: add 10 Knowledge Graph MCP tools for Phase 1
- feat: Phase 1 — migration, semantic search, and heuristic predictions

**Fixes**

- fix: rename single-letter coordinate vars to posX/posY/gridX/gridY
- fix: export OpenAPI schema with dev tier to include all 0.0.2 routes

**Docs**

- docs: add 0.0.2 feature gate map (#381)

**Style**

- style: refactor InterpretationPanelView and fix ClaimInspector lint errors

**Chore**

- chore: update CONTINUE.md timestamp
- chore: SwiftLint auto-fix — 88 sorted_imports violations across 101 SwiftUI files
- chore: update STATE.md — MCP tools added, OpenAPI synced, SwiftLint fixed (#392)
- chore: consolidate HISTORY.md — remove duplicate entries from repeated session-end calls
- chore: archive loop session — #365 SourceMetadata, #366 alias-map, SwiftLint fixes, curated_only filter
- chore: update STATE.md — SwiftLint fixes, curated_only filter, rules.json
- chore: add agent rules configuration
- chore: archive autonomous session — #381 gate map, #365 SourceMetadata, #366 alias-map, Phase 1 SwiftUI done
- chore: update STATE.md — 3 tasks completed in autonomous session
- chore: archive task-sync session — GitHub labels fixed, #387 status updated
- chore: update STATE.md — Phase 1 SwiftUI complete, next: PyKEEN wiring
- chore: commit pending config/doc changes before session
- chore: export OpenAPI schema with dev tier — all 0.0.2 routes
- chore: update STATE.md — session 2026-04-02 results
- chore: update STATE.md — Phase 4 workflow tools complete
- chore: update STATE.md — Phase 1-3 backend complete
- chore: sync OpenAPI schema after Phase 1 knowledge graph routes

### 2026-04-01

**Features**

- feat: add knowledge graph API foundation with models and routes

**Fixes**

- fix: three bugs in knowledge graph API tests and conftest
- fix: show connection error state in LibraryView when backend is unreachable
- fix: remove grey title bar, simplify inspector, fix workflow concurrency

**Chore**

- chore: commit pending state updates before autonomous session

### 2026-03-30

**Features**

- feat: add dev-tier knowledge graph API foundation
- feat: unify sidebar/activity behavior and stabilize 0.0.1 UX

**Fixes**

- fix: stabilize backend workflow runtime and clean log/deprecation noise
- fix: include provider langchain adapters in runtime deps
- fix: move langchain-openai into runtime dependencies
- fix: stabilize 0.0.1 gating, runtime env, and workflow reliability

**Refactors**

- refactor: unify workflow and batch runtime construction

**Docs**

- docs: restore knowledge graph roadmap planning after main sync

**Chore**

- chore: promote runtime-used deps out of optional set
- chore: enforce provider adapters as runtime dependencies

### 2026-03-29

**Chore**

- chore(session-end): update state, memory, and history

### 2026-03-27

**Features**

- feat: add workflow batch input source - collection or current selection

### 2026-03-25

**Features**

- feat: show folder contents grid in preview pane (#327)
- feat: add prompt preview panel to workflow node editor (#340)
- feat: add thinking mode selector to workflow node config UI
- feat: improve Settings Defaults UI with GroupBox layout and help text
- feat: unify vision engine into provider/model selector (#345)
- feat: add thinking mode to workflow LLM/vision tools (#339)
- feat: enable describe and rewrite workflow tools for 0.0.1
- feat: wire typography settings to inspector text editor (#324)
- feat: enable AI Providers & Models menu item for 0.0.1 (#333)
- feat: add font, line spacing, and margin settings with reset (#336)

**Fixes**

- fix: mount settings router so AI defaults endpoint is accessible
- fix: icon view scale, folder preview, and batch execute SSE error
- fix: Apple Vision OCR now handles PDF files
- fix: replace print() error logging with ErrorService in LibraryView (#331)
- fix: show actual file size in table Size column (#314) (#329)

**Docs**

- docs: session-end — OCR fix, font wiring, thinking mode, settings router

### 2026-03-24

**Features**

- feat: add connection error banner to Library view (#313)
- feat: enable 0.0.1 feature surface — workflows, activity, batches, UI fixes

**Fixes**

- fix: icon view default scale and preview pane loading on launch (#330)
- fix: center image using frame expansion instead of contentInsets (#322)
- fix: remove dangling FolderContentsGrid.swift reference from Xcode project

**Docs**

- docs: session-end — 8 PRs for 0.0.1 milestone issues
- docs: session-end — 0.0.1 UI and feature enablement session

**Chore**

- chore: update STATE.md after #314 session

### 2026-03-23

**Features**

- feat: add build/release skills, remove dev instructions from UI
- feat: add backend app icon for Briefcase build
- feat: styled installer DMG with app + Applications layout
- feat: add move-to-Applications prompt on first launch

**Fixes**

- fix: document viewer — gray background, non-overlay scrollbars, fit-to-window default (#317)
- fix: add backend app icon as icns for Briefcase
- fix: slim Briefcase bundle and use briefcase package
- fix: Briefcase build with Python 3.13 via dedicated venv
- fix: enable CopyFiles build phase for regular builds
- fix: use correct app icon with transparent background
- fix: disable app sandbox for DMG distribution
- fix: replace app icon with card-file cabinet, fix move-to-Applications

**Refactors**

- refactor: migrate bundle identifier from ca.tubb to com.tubb

**Docs**

- docs: session-end with GitHub issues #317-#320
- docs: add inspector panel fixes to next session
- docs: add document viewer fixes to next session
- docs: session-end — next focus is 0.0.1 feature surface
- docs: session-end state and memory update (build pipeline session)

### 2026-03-22

**Features**

- feat: add build/release pipeline and project site

### 2026-03-20

**Chore**

- chore: handoff — commit WIP before sync

### 2026-03-15

**Chore**

- chore: commit pending state changes before session

### 2026-03-13

**Fixes**

- fix: harden keyboard navigation and rich-text save flow (#279)

**Docs**

- docs: session-end state and memory update (#310 #311)

### 2026-03-11

**Features**

- feat: add tiered backend route registration for 0.0.1 (#233)

**Fixes**

- fix: gate providers menu surface by feature tier (#235)
- fix: enforce 0.0.1 frontend feature gates defaults (#232)

**Docs**

- docs: define workflow QA validation gates for 0.0.1 (#250)
- docs: add 0.0.1 manual QA checklist runbook (#238)
- docs: record autonomous completion of #220
- docs: record autonomous session blocker for GitHub CLI

**Tests**

- test: clean conftest imports for tiered routing checks (#233)

**Chore**

- chore: make Sparkle release config deterministic (#278)
- chore: commit pending config/doc changes before session

### 2026-03-10

**Features**

- feat: add default workflow templates install/reset flow (#291) (#303)

**Fixes**

- fix: rerun search when toolbar selects a saved query (#288)
- fix: gate Data menu workflow action behind release flags (#235)
- fix: enable minimal search in 0.0.1 release profile (#288)
- fix: harden sparkle release configuration checks (#278)
- fix: stabilize sidebar state manager and library singleton tests (#220)
- fix: clean orphan documents and keep API contracts in sync (#279)

**Docs**

- docs: refresh state handoff after 0.0.1 hardening pass (#279)

### 2026-03-09

**Features**

- feat: continue 0.0.1 UI hardening and feature gating (#279) (#300)
- feat: gate search and run-workflow-on-selection for post-0.0.1
- feat: make inspector content rich-text editable with persistence
- feat: make inspector text pane editable and persist page content

**Fixes**

- fix: widen inspector resize range for library and workflow panes (#220) (#302)
- fix: guard workflow files picker against cyclic folder trees (#292) (#301)
- fix: enable arrow-key navigation in library icon view
- fix: close remaining search command gating leaks
- fix: allow much wider right inspector resizing
- fix: harden workflow files picker against popover crashes (#292)
- fix: default library/search split to side-by-side layout
- fix: force image preview view to fill pane width
- fix: register files source tool for workflow execution
- fix: execute batches when applying workflow to selection
- fix: restore correct image centering in preview pane
- fix: resolve lint regressions in workflow and library views (#294) (#298)
- fix: run workflows on single selected document in library (#294) (#295)

**Docs**

- docs: record overnight #292 picker hardening progress
- docs: update state after rich-text inspector merge
- docs: refresh state and 0.0.1 triage after overnight merges

**Chore**

- chore: finalize 0.0.1 cleanup and workflow gating

### 2026-03-08

**Fixes**

- fix: stabilize files node picker flow in workflow editor (#292) (#293)

### 2026-03-04

**Fixes**

- fix: resolve ruff lint violations across backend source (#237) (#261)
- fix: add FeatureManager.swift to Xcode project target (#236) (#262)

**Docs**

- docs: add spatial knowledge layer roadmap and plan (#265) (#275)
- docs: update 0.0.1 scope for Providers and Workflows (#264)

### 2026-02-28

**Docs**

- docs: add full agent constitution — VISION, AGENTS, USER, SOUL

**Chore**

- chore: commit all in-progress work before merging to main

### 2026-02-23

**Features**

- feat: add Sort By section to View menu
- feat: E.3.7 — click status/type tag in list view to filter (#217)
- feat: E.3.6 — NetNewsWire-style pane nav with Left/Right arrows (#216)
- feat: E.3.4 — NetNewsWire-style inline filter bar (#214)
- feat: E.3.3 — sortable column headers in table view (#213)
- feat: zoom in/out for icon view and map view (#212)
- feat: inspector pane resizable via draggable divider (#211)
- feat: persist zoom scale per document in image preview (#199)
- feat: per-folder sort order persistence in LibraryView (#194)
- feat: per-folder view mode persistence + dedupe Action views (#193)

**Fixes**

- fix: scope focus indicator to list/table only, not full center column
- fix: make pane focus indicator visible — use full border stroke
- fix: pane focus nav + SwiftLint cleanup + remove dead LibraryViewToolbar
- fix: arrow key navigation + toolbar unification (#218, #219)
- fix: correct tap gesture order and prevent double handleTap on double-click
- fix: QA round 2 — focus rings, list arrow keys, 2-tab inspector, inspector max width
- fix: E.3.5 — use displayMode instead of viewMode for column config visibility (#215)
- fix: suppress spurious focus ring on inspector panel (#205)
- fix: map view shows all items with horizontal/vertical scrolling (#204)
- fix: restore last open view after collections load from API (#203)
- fix: list view clicks — use explicit tap handlers instead of List(selection:) (#202)
- fix: shift keyboard focus to content pane when tapping icon (#201)
- fix: SwiftLint violations 49→0 (A.5) — suppress all remaining structural warnings
- fix: SwiftLint violations 56→49 (A.4)
- fix: suppress 9 todo SwiftLint violations (A.3) 65→56
- fix: reduce SwiftLint violations 71→65 (B.11)

**Refactors**

- refactor: split LibraryView.swift into focused extension files

**Docs**

- docs: update progress.md — Phase G QA fixes recorded (#220)
- docs: update progress.md — Phase E complete, Phase F code review fixes recorded
- docs: mark all Phase E tasks done in progress tracker
- docs: mark E.1.4 done in progress tracker
- docs: mark E.1.3 done in progress tracker
- docs: mark E.1.2 done in progress tracker
- docs: mark E.1.1 done in progress tracker
- docs: add Phase E tasks from Daniel QA review (17 items)
- docs: record PR #200 in progress tracker
- docs: mark all tasks complete, close epic #180
- docs: mark B.11 and B.12 complete in progress tracker
- docs: mark B.10 per-folder sort order persistence done in progress tracker
- docs: mark B.9 per-folder view mode persistence done in progress tracker

### 2026-02-22

**Features**

- feat: add sort menu with persisted sort order to library view (#191)
- feat: persist inspector tab selection across sessions (#190)
- feat: add Tab key focus cycling between sidebar, content, inspector (#189)
- feat: add Action files to Xcode project and fix build errors
- feat: add arrow key navigation to LibraryView icon/grid mode (#188)
- feat: add Shift+click range selection and Cmd+click toggle to LibraryView (#187)
- feat: add type-to-select navigation to LibraryView (#186)
- feat: add inline document title editing to LibraryView (#185)
- feat: add keyboard shortcuts to LibraryView (Phase 4)

**Fixes**

- fix: resolve 261 SwiftLint violations (330→69)

**Refactors**

- refactor: extract IntegrationsService, WorkflowExecutionObserver, DragDropService (Batch 13)
- refactor: extract AppleScript, ProviderService, AutomationService (Batch 12)
- refactor: extract WorkflowStreamService and ModelComparisonService (Batch 11)

**Docs**

- docs: mark sort menu task B.8 complete in progress tracker
- docs: mark inspector tab persistence task B.7 complete in progress tracker
- docs: mark Tab key focus cycling task B.6 complete in progress tracker
- docs: mark arrow key navigation task B.5 complete in progress tracker
- docs: mark selection modifiers task B.4 complete in progress tracker
- docs: mark type-to-select task B.3 complete in progress tracker
- docs: mark inline editing task B.2 complete in progress tracker
- docs: update progress — keyboard shortcuts task complete
- docs: mark XCTest task C as done in progress tracker
- docs: update progress — 60 ActivityTypes + SidebarItem tests added for #182
- docs: mark XCTest SSE parsing task complete in progress tracker
- docs: update progress — SSE parsing tests added for #182
- docs: mark stale docs task complete in progress tracker
- docs: update stale docs with post-refactoring line counts and status
- docs: update progress — SwiftLint task complete, add post-refactoring tasks
- docs: update progress — Batch 13 complete, all batches done (35/37 files)
- docs: update progress — Batch 12 complete (32/37 files)
- docs: update progress — Batch 11 complete (29/37 files)

**Tests**

- test: add 60 unit tests for ActivityTypes and SidebarItem models
- test: add 29 SSE parsing tests for WorkflowStreamService

### 2026-02-20

**Features**

- feat: add fresh-context refactoring loop script

**Fixes**

- fix: make run-loop.sh compatible with tmux -CC and iTerm2

**Refactors**

- refactor: extract FicheroApp.swift and ActivityTypes.swift (Batch 10)
- refactor: extract LibraryManager.swift into extensions (577→198 lines)
- refactor(batch-9): split DocumentStore into extensions (#167)
- refactor(batch-9): split SidebarItem into domain groups (#168)
- refactor(batch-8): extract components from TriggerDetailView (#165)
- refactor(batch-7): extract components from ActivityProgressView (#163)
- refactor(batch-7): extract components from WorkflowExecutionRow (#164)
- refactor(batch-7): extract components from WorkflowInspector (#162)
- refactor(batch-6): extract components from ComparisonDetailView, SidebarView, AddProviderSheet
- refactor(batch-5): extract components from WorkflowOutputLog, ScheduleEditorView
- refactor(batch-4): extract components from ModelComparisonView, BatchDetailView, DynamicConfigView
- refactor(batch-3): extract components from ProvidersView, ChatInspector, ActivitySidebarContent
- refactor(batch-2): extract components from SidebarItemRow, WorkflowEditor, WorkflowChainListView
- refactor(batch-1): extract components from DocumentInspector, TriggerEditorView, SettingsView
- refactor: extract ChatView components to separate files
- refactor: extract SearchView components to separate files

**Docs**

- docs: update progress — Batch 10 complete (27/37 files)
- docs: update progress — Batch 9 fully complete (25/37 files)
- docs: add agent orchestration files
- docs: update progress — Batch 9 complete (24/37 files)
- docs: update progress — Batch 8 complete (21/37 files)
- docs: update progress — Batch 7 complete (20/37 files)
- docs: update progress — Batch 6 complete (17/37 files)
- docs: update progress — Batch 3 complete (9/37 files)
- docs: update progress — Batch 2 complete (6/37 files)
- docs: update progress — Batch 1 complete (3/37 files)
- docs: add session handoff guide for refactoring continuation
- docs: update refactoring session summary with Session 2 results
- docs: add refactoring session summary for 2026-02-19

**Chore**

- chore: add .mcp.json to gitignore (contains secrets)

### 2026-02-19

**Fixes**

- fix: auto-fix SwiftLint trailing whitespace violations

**Refactors**

- refactor: extract LibraryView components to separate files
- refactor: extract WorkflowLibraryView components to subfolder
- refactor: extract SidebarView methods to component files
- refactor(WorkflowEditor): extract view components, reduce from 1008 to 542 lines
- refactor(ImageViewer): extract components, reduce from 1035 to 288 lines
- refactor(NodePopover): Phase 5 - extract input mappings, reduce to 360 lines ✅
- refactor(NodePopover): Phase 4 - remove unused state and helpers, reduce to 441 lines
- refactor(NodePopover): Phase 3 - extract provider/model selector, reduce to 542 lines
- refactor(NodePopover): Phase 2 - extract 4 more configs, reduce to 620 lines
- refactor(ImageViewer): start extraction, create ImageZoomToolbar component
- refactor(NodePopover): extract 5 config views, reduce from 1144 to 804 lines
- refactor: fix SwiftLint violations and add comprehensive refactoring plan

**Chore**

- chore: remove backup file

### 2026-02-18

**Features**

- feat: add SwiftUI previews to 26 views and fix SwiftLint warnings

**Refactors**

- refactor: split workflow node preview from main view
- refactor: use generated model service in app state and catalog

**Style**

- style: clean editor and workflow node view lint debt
- style: resolve schedule editor and action picker lint warnings
- style: rename timezone loop variable for swiftlint
- style: normalize sidebar import menu closure syntax
- style: normalize main toolbar button closure syntax
- style: remove unused onChange closure parameter

### 2026-02-17

**Style**

- style: remove explicit nil defaults in workflow toolbar
- style: fix trailing comma in api endpoints list
- style: fix model service swiftlint style warnings
- style: resolve simple swiftlint warnings in content view extensions

### 2026-02-16

**Fixes**

- fix: replace deprecated coroutine callback check
- fix: migrate lancedb table checks to list_tables
- fix: replace broad pylint suppression with targeted fixes
- fix: make pylint errors-only baseline actionable
- fix: stabilize workflow and hierarchy tests on python 3.14
- fix: tolerate Kreuzberg API drift in document extraction
- fix: accept Swift nulls in workflow contract models
- fix: treat unresolved bookmark payloads as stale
- fix: preserve ingest file/folder not-found error precedence
- fix: restore legacy db fallback behavior for ingest tests

**Docs**

- docs: clarify backend script ownership and ignore local artifacts
- docs: add view-by-view manual QA matrix
- docs: refresh validation baseline after test stabilization
- docs: move code review notes out of xcodeproj
- docs: add codex human-in-the-loop QA issue templates

**Tests**

- test: register pytest async markers in pyproject
- test: harden workflow api smoke tests and remove bool returns
- test: align swift contract tests with generated workflow schema
- test: auto-run coroutine unit tests without pytest-asyncio
- test: align backend integration search assertions with tuple API
- test: provide library header for stats endpoint test
- test: restore mock_db fixture for API unit tests

**Style**

- style: trim trailing whitespace in content view extensions

**Chore**

- chore: remove remaining serious swiftlint errors
- chore: tighten gitignore for local/editor artifacts
- chore: exclude generated Swift services from SwiftLint
- chore: retire top-level ai folder into docs/agent-workflow

### 2026-02-12

**Features**

- feat: add Hugging Face Inference API support with thinking models

**Refactors**

- refactor: modernize Swift UI with improved sidebar and content view

**Docs**

- docs: update AI task tracking and Hugging Face integration docs

**Chore**

- chore: update Xcode project configuration and entitlements

### 2026-02-07

**Fixes**

- fix: update Hugging Face API endpoint to router.huggingface.co
- fix: resolve crash when adding Hugging Face models

### 2026-01-31

**Features**

- feat: Swift 6 migration, embedded backend, and app icon implementation

**Fixes**

- fix: resolve Swift 6 concurrency crash and backend lifecycle issues

### 2026-01-30

**Features**

- feat(frontend): add folder hierarchy support for workflows (TODO-129)
- feat(backend): add folder organization to workflows and chains
- feat(sidebar): flatten automation sidebar (TODO-128)
- feat(sidebar): implement universal creation (TODO-127)

**Docs**

- docs: Add TODO-132 for artifact label fixes
- docs: Add TODO-131 for workflow AI defaults fix

### 2025-12-27

**Features**

- feat: implement proper SwiftUI observable pattern (TODO-061)

**Fixes**

- fix: implement proper delete and rename with observer pattern
- fix: connect SidebarView to refreshCounter for UI updates
- fix: TODO-052 add UI refresh after rename
- fix: TODO-052 inline rename bug with modern SwiftUI patterns

**Refactors**

- refactor: implement ID-based selection (proper SwiftUI pattern)

### 2025-12-25

**Features**

- feat: implement tool registry system and SwiftUI canvas foundation
- feat: implement core workflow engine with LangGraph
- feat: confirm keyboard shortcuts for CRUD operations in sidebar
- feat: implement comprehensive sidebar error handling system
- feat: implement inline folder creation in sidebar
- feat: analyze and design enhanced search functionality
- feat: implement comprehensive logging system
- feat: implement comprehensive error handling system
- feat: integrate refactored sidebar components into Xcode project

**Fixes**

- fix: resolve API pytest issues and ensure background tests run properly
- fix: resolve XCTestPlan configuration issues

**Refactors**

- refactor: improve SidebarView dependency injection and UI structure
- refactor: implement MVVM pattern for sidebar state management

**Docs**

- docs: fix TODO.md formatting inconsistency
- docs: add final completion summary for TODO-022
- docs: update task completion status for TODO-022
- docs: add comprehensive ingest module documentation

**Tests**

- test: complete comprehensive unit tests for SidebarView components
- test: implement unit tests for SidebarView components

**Chore**

- chore: update TODO-013 status to completed

### 2025-12-24

**Features**

- feat: enhance drag and drop visual feedback in sidebar
- feat: implement new folder functionality in SidebarView
- feat: Implement inline rename functionality for sidebar items

**Fixes**

- fix: Revert incomplete workflow save implementation

**Docs**

- docs: add TODO-028 ingest documentation task\n\n- Create TODO-028 task folder with human_note.md, task.md, and context.md\n- Update TODO.md with new task entry\n- Move inbox item to task folder for processing
- docs: fix INBOX_WORKFLOW.md formatting and consistency
- docs: update README summaries and improve AI documentation structure

**Tests**

- test: complete file/folder import endpoint testing
- test: add comprehensive move endpoint tests
