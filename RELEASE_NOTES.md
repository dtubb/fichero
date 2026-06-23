# Fichero — Release Notes

Dated releases, newest first. Written in the style of a short "what's new" — grouped **New / Improved / Security / Fixed**.

---

## 2026-06-23

**New — Knowledge Graph layer.** Catalogue workflows now write structured entity rows (people, places, organizations, events, dates, keywords) into a queryable knowledge graph alongside the human-readable artifact. Same data, two views: the markdown for reading, the typed graph for searching, cross-referencing, and future cross-document navigation. Each claim carries page-level provenance — every entity row knows which page of which document it came from.

**New — Four catalogue workflows out of the box.** *Catalogue* runs the full nine-section archival entry in one cloud LLM pass. *Catalogue (composable)* fans the work out across six per-section extractors (people / places / organizations / events / dates / keywords) so you can swap or customize any one. *Catalogue (Apple Intelligence)* runs the same pipeline entirely on-device using Apple's Foundation Models — zero cloud calls, no API quota, full privacy. Plus two Transcribe variants: *Transcribe (Apple Vision)* (on-device OCR) and *Transcribe* (cloud vision LLM, better for handwriting and historical scripts).

**New — Per-page entity extraction.** When a workflow processes multi-page documents, each page is extracted separately and each extracted entity carries its source page label. The substrate is ready for cross-document views ("show me every page that mentions María Angel") in upcoming releases.

**Improved — Workflow Library.** Folder grouping in the list (Transcribe, Catalogue), generic extractors by default (archive-specific extractors like rivers, mines, properties remain available as draggable tools, but no longer ship in the default workflow), and proper SF Symbol icons for every node on the canvas instead of generic gears.

**Improved — Settings.** Defaults model picker reads from configured providers; folder inspector when nothing is selected; thumbnail aspect ratios respect document orientation in the grid.

**Security — Engine API now requires a per-launch shared-secret token.** The embedded engine binds to `127.0.0.1` (loopback only — not reachable from the internet or the local network, with or without a token) and additionally requires `Authorization: Bearer <token>` on every request. The token is generated fresh at engine startup and written to `~/Library/Application Support/Fichero/.api-key` (mode `0600`). This closes the remaining gap of other apps on the same Mac being able to hit the API. Migration to a Unix domain socket (tighter filesystem-permission-based isolation) is planned for 0.0.3.

**Fixed** — Workflow Library list endpoint returning empty after Reset Defaults. Workflow templates duplicating on every install. Catalogue (composable) reducer running a duplicate extraction pass instead of consuming claims. Several inspector and sidebar bugs from earlier internal builds.

---

<!-- EARLIER RELEASES — to be filled in by day from git history.
     Range: from the SwiftUI/Python migration (~2025-11, the first SwiftUI-app + FastAPI
     commit — the worker finds the exact pivot) to the present. ~4,453 commits / 127 days.
     A codex/local lane (free — saves weekly Claude budget) mines `git log` + closed GitHub
     issues per day and writes one dated ## YYYY-MM-DD section, newest-first, in the same
     New / Improved / Security / Fixed style as the 2026-06-23 entry above. Skip pure-internal
     days or fold them into a terse "Under the hood" line — these are user-facing notes, not a
     changelog. See the tracking issue for the full codex brief. -->
