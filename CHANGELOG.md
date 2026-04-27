# Changelog

## 0.0.2 — Unreleased

- Added a Catalogue workflow that runs on any folder and produces a nine-section archival catalogue entry covering people, dates, rivers, legal references, mines, properties, events, keywords, and a summary narrative.
- Added Transcribe and Catalogue as locked default workflows that auto-update when the app launches; duplicate them to customize, originals stay protected.
- Added a folder inspector: click a folder in the sidebar to see its contents, metadata, and workflow artifacts in the right-hand panel.
- Added Run Workflow to the right-click context menu so you can execute a workflow directly on any document selection.
- Added structured artifact previews to the inspector Artifacts tab — catalogue sections (people, dates, rivers, etc.) render as readable tables.
- Added a redesigned document inspector (Tinderbox-style) with one panel per artifact: each panel is independently editable, has its own delete and save indicator, and shows the provider and model that produced it.
- Added equal-divide panel heights in the inspector — one panel fills the pane, two split it in half, three thirds, and so on; falls back to scrolling when there are too many to fit.
- Added the AppKit ruler and format strip (Styles, alignment, Spacing, Lists) above each editable artifact panel.
- Added View → Show / Hide Ruler (⌃⌘R) to toggle the ruler and format strip globally.
- Added View → Find in Artifact (⌘F) to search within the focused panel using the inline find bar.
- Added per-page PDF artifact storage so each page gets its own artifact row, not just the parent PDF.
- Added a cache-hit indicator to the Activity progress so you can see when a workflow reuses a prior result.
- Improved the PDF preview with a zoom toolbar (zoom in/out, fit to window, 100%).
- Improved PDF page navigation with horizontal trackpad swipe.
- Improved sidebar section headers with system icons.
- Improved the AI Providers menu entry with an icon.
- Improved the Activity monitor to show human-readable workflow node names instead of internal IDs.
- Fixed sidebar drag-and-drop routing for files and folders dropped from Finder.
- Fixed the workflow first-click and activity run display.
- Fixed the document inspector showing stale transcription after workflow completion.
- Fixed Catalogue artifacts not appearing after a workflow run.
- Fixed bold and other rich-text formatting being silently dropped when saving an artifact edit.
- Fixed deleted artifacts re-appearing after navigating away and back.
- Fixed duplicate provider entries (e.g. "My OpenAI") accumulating across launches.
- Fixed the Transcribe spinner getting stuck after all files completed.
- Fixed Activity run titles showing file paths and opaque IDs instead of readable workflow names.
- Fixed grid view falling back to placeholder icons instead of thumbnails.
- Fixed LINK / COPY / MOVE ingest-mode badges not appearing on document rows.
- Removed the legacy single-text inspector — the new per-artifact panel layout is the only inspector.

## 0.0.1 — Initial release

- Added the document library with folder organization and file import.
- Added semantic search via local vector embeddings.
- Added the AI workflow engine with visual node editor.
- Added support for 37+ file types including PDF, Word, images, audio, and video.
- Added support for local models (Ollama) and cloud providers (OpenAI, Anthropic, Google, and more).
- Added the embedded Python backend — no separate server to install or manage.
