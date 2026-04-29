# Changelog

All notable changes to Fichero. Versions are dated by ship day (calendar
versioning); pre-1.0 releases are Alpha.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## 2026.04.29 — Alpha

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

*This is the first public release. Earlier internal builds were never
distributed.*
