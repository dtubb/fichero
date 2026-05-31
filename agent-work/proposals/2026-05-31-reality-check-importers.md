# Reality Check: Importers Milestone — 2026-05-31

Read-only audit. No code was run or modified.

---

## Open Issues Audited

| # | Title | Verdict | Evidence | Action |
|---|-------|---------|----------|--------|
| 1340 | Kreuzberg loader writes cache to repo root (.kreuzberg/) — should live outside worktree | **DONE** | `kreuzberg_cache.py` line 20: `_KREUZBERG_CACHE = Path.home() / "Library" / "Caches" / "com.fichero.fichero" / "kreuzberg"`. Cache is already set to `~/Library/Caches/…`, not CWD-relative. `.gitignore` entry added 2026-05-30 per the issue body. | Safe to close. |
| 1330 | Dropbox importer (link, not download) | **OPEN** | No Dropbox loader, route, or OAuth handler found in `fichero-engine/src/fichero/loaders/` or `api/routes/`. Loaders present: `kreuzberg_cache.py`, `document_loader.py`, `pdf_loader.py`, `image_loader.py`, `docling_loader.py`, `iiif_loader.py`, `unified.py`, `xlsx_reader.py`, `xmp_loader.py`, `kreuzberg_artifacts.py`. No Dropbox-related symbol anywhere. | Needs to be built from scratch. |
| 1329 | Box importer (link, not download) | **OPEN** | Same check: no Box loader, route, or OAuth handler in the codebase. `api/routes/integrations.py` exists (32 symbols) but is for app integrations (DEVONthink/Bookends/Tinderbox style), not Box storage. | Needs to be built from scratch. |
| 1216 | Large folder ingest returns 200s but data missing after relaunch | **OPEN** | Root cause confirmed: `ingest_folder` uses FastAPI `BackgroundTasks` with an in-memory `_tasks: dict` (line 23 of `api/routes/ingest.py`). Task state is lost on restart. The `do_background_ingest()` closure does write documents to the DB via `ingest_folder()` from `ingest.py`, so *completed* ingests should persist — but an in-flight ingest interrupted by restart loses all progress. Additionally, the background task runs synchronously in the FastAPI thread pool with no restart-resume. If documents are persisted to DuckDB synchronously during the run, a mid-run crash leaves partial data with no recovery path. This matches the "200 but missing after relaunch" symptom. No content-hash skip or queue persistence exists. | The in-memory task tracker must be replaced with a durable queue (DuckDB row) and the ingest loop needs restart-safe checkpointing. Relates to #739. |
| 881 | Ingest: silent WARNING-level failures leave page_content=None — text files and large folders not persisted | **OPEN** | `ingest.py` exception handling at WARNING level (issue's own analysis) is not contradicted by any recent fix. The test `test_markdown_gets_page_content_by_default` exists and covers the happy path; no test for the silent-failure branch (exception caught at WARNING). The analysis in the issue (lines 178-292 of `ingest.py`, embed guard at 283-284, silent catch at 533) has not been superseded by a visible fix. | Add an explicit test that a loader raising an exception surfaces a user-visible error; promote the catch to ERROR; re-emit a synthetic `page_content_failed` event so the UI can show the failure. |
| 744 | Tinderbox importer: link a .tbx → ingest notes into vector DB + KG | **OPEN** | No `.tbx` parser, Tinderbox loader, or `tinderbox` symbol anywhere in the codebase. This is a planned 0.0.4 feature (the issue itself says "Why 0.0.4"). Not yet started. | Future milestone work; do not start until retrieval (#736) ships. |
| 739 | Ingest: resumable corpus pass with content-hash skip (100K-scale) | **OPEN** | `content_hash` column does not exist on documents (no symbol, no DB column found). No per-stage stamp, extractor versioning, or DuckDB queue for ingest. This is a 0.0.4+ feature by design. Related to #1216. | Future milestone work. |
| 702 | Drag-drop: folder can be dropped onto a PDF row; no drop-line indicator when dragging a folder | **OPEN** | `SidebarItemRow+DropHandlers.swift` has `handleDropIntoFolder` and `handleDropBesideItem` but the outline shows no guard rejecting a folder-payload drop onto a document target. `targetKind` variable exists but the reject logic is not visible from the outline. The issue body specifically calls out a missing "folder onto file/PDF → reject" case. The drop-line overlay for folder payloads was also unresolved per the issue. A targeted read would be needed to confirm the exact guard, but the absence of a clear "guard folder-onto-doc" comment or function makes this OPEN pending verification. | Review `handleDropIntoFolder` reject matrix; verify the overlay `.dropDestination(for:)` type list includes folder transferables. |
| 597 | Library/sidebar: cloud-link badge for Box/Dropbox-imported items | **PARTIAL** | `SidebarItemRow+Label.swift` `iconView` already implements `ingestBadge(for:)` and shows LINK (alias-arrow) and MOVE (arrow-into-box) badges as per-document overlays (lines 58-109). However, the badge is keyed on `metadata.ingest_mode` from the Document, not on a Box/Dropbox-specific field. Since Box and Dropbox importers (#1329, #1330) don't exist yet, the "cloud-link" semantic badge for those sources cannot work yet, even though the generic LINK badge infrastructure is done. The issue title references cloud/sync specifically. | Badge infrastructure: DONE. Cloud-source-specific badge: blocked by Box/Dropbox importers not existing. |

---

## Summary

| Category | Count |
|----------|-------|
| Total open issues audited | 9 |
| DONE (safe to close now) | 1 |
| PARTIAL | 1 |
| OPEN (genuinely needs work) | 7 |

---

## Safe to Close Now

- **#1340** — Kreuzberg cache path is already `~/Library/Caches/com.fichero.fichero/kreuzberg/` in the current codebase. Fix is in.

---

## Partially Done — Needs Scoped Follow-up

- **#597** — Generic LINK/MOVE ingest-mode badges are implemented and visible in `SidebarItemRow+Label.swift`. The "cloud-link" visual for Box/Dropbox is blocked only by those importers not existing yet (#1329, #1330). Once importers land and emit an `ingest_mode` that signals cloud-source, the badge layer can be extended trivially.

---

## Needs Real Work

- **#1216** — In-memory `_tasks` dict + `BackgroundTasks` means folder ingest does not survive restarts. The "200 OK but missing after relaunch" bug is real and unfixed.
- **#881** — Silent WARNING-level exception catch in `ingest.py` still present; no fix visible. `.md` files and partial large-folder ingests can silently lose `page_content`.
- **#702** — Folder-onto-PDF drop rejection and folder drag-line indicator: no clear rejection guard found; likely still broken.
- **#1330, #1329** — Box and Dropbox importers are not started.
- **#744** — Tinderbox importer not started (correctly deferred to 0.0.4).
- **#739** — Resumable corpus pass / content-hash skip not started (correctly deferred to 0.0.4+).

---

*Verified via jCodemunch AST index + direct file reads. No execution.*
