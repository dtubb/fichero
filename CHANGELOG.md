# Changelog

## 0.0.2 — Unreleased

- Added a Catalogue workflow that runs on any folder and produces a nine-section archival catalogue entry covering people, dates, rivers, legal references, mines, properties, events, keywords, and a summary narrative.
- Added Transcribe and Catalogue as locked default workflows that auto-update when the app launches; duplicate them to customize, originals stay protected.
- Added a folder inspector: click a folder in the sidebar to see its contents, metadata, and workflow artifacts in the right-hand panel.
- Added Run Workflow to the right-click context menu so you can execute a workflow directly on any document selection.
- Added structured artifact previews to the inspector Artifacts tab — catalogue sections (people, dates, rivers, etc.) render as readable tables.
- Improved the PDF preview with a zoom toolbar (zoom in/out, fit to window, 100%).
- Improved PDF page navigation with horizontal trackpad swipe.
- Improved sidebar section headers with system icons.
- Improved the AI Providers menu entry with an icon.
- Improved the Activity monitor to show human-readable workflow node names instead of internal IDs.
- Fixed sidebar drag-and-drop routing for files and folders dropped from Finder.
- Fixed the workflow first-click and activity run display.
- Fixed the document inspector showing stale transcription after workflow completion.
- Fixed Catalogue artifacts not appearing after a workflow run.

## 0.0.1 — Initial release

- Added the document library with folder organization and file import.
- Added semantic search via local vector embeddings.
- Added the AI workflow engine with visual node editor.
- Added support for 37+ file types including PDF, Word, images, audio, and video.
- Added support for local models (Ollama) and cloud providers (OpenAI, Anthropic, Google, and more).
- Added the embedded Python backend — no separate server to install or manage.
