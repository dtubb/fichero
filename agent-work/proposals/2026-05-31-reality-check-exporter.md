# Reality Check: Exporter Milestone — 2026-05-31

## Quick Summary

| Bucket | Count | Issue numbers |
|---|---|---|
| Safe to close now (DONE) | 2 | #472, #473 |
| Partial — backend done, Swift UI unwired | 2 | #470, #471 (sort of — see below) |
| Genuinely open — not implemented | 6 | #471, #474, #475, #476, #505, #506, #507, #508 |

**Safe to close now:** #472, #473 (markdown folder and Word .docx — both fully implemented backend + wired to OpenAPI client)

**Needs work (do not close):** #470 (async job model per spec not built), #471 (JSON format route missing), #474 (Excel missing), #475 (static HTML missing), #476 (Netlify missing), #505–#508 (release gates, prerequisites not all met)

---

## Per-Issue Classification

| # | Title | Verdict | Evidence |
|---|---|---|---|
| #470 | Export: shared export infrastructure and router | PARTIAL | Router exists (`/api/export/markdown-folder`, `/api/export/word`) and is mounted in `main.py`. BUT the async job pattern specified in the issue (`POST /api/export → {job_id}`, `GET /api/export/{job_id}`, `GET /api/export/{job_id}/download`, `ExportJob` model) is **not implemented** — current routes are synchronous, return results directly, and there is no `ExportJob` model anywhere in the codebase. Issue spec and implementation diverge. |
| #471 | Export: JSON format | OPEN | No `export_json` function, no `/api/export/json` route, and no JSON export type in `export_service.py` or `export.py`. `openapi.json` lists only `/api/export/markdown-folder` and `/api/export/word`. Not implemented. |
| #472 | Export: Markdown folder | DONE — close | `export_markdown_folder()` fully implemented in `fichero-engine/src/fichero/export_service.py` (lines 60–123). Route `/api/export/markdown-folder` mounted and in OpenAPI. Generated Swift client method `exportMarkdownFolderRouteApiExportMarkdownFolderPost` exists in `FicheroAPIClient`. Already closed in GitHub — confirm closure is correct. |
| #473 | Export: Word (.docx) | DONE — close | `export_word_docx()` fully implemented in `export_service.py` (lines 126–189), builds valid OOXML zip with image+text table layout. Route `/api/export/word` mounted and in OpenAPI. Generated Swift client method `exportWordRouteApiExportWordPost` exists. Issue is still OPEN in GitHub — **safe to close.** |
| #474 | Export: Excel (.xlsx) | OPEN | No `export_excel` function, no `/api/export/excel` route. `loaders/xlsx_reader.py` exists but is an *importer*, not an exporter. `openpyxl`/`xlsxwriter` not referenced in any export context. Not implemented. |
| #475 | Export: static HTML website | OPEN | No static HTML export route, no HTML template generator, no Lunr/Fuse search index builder anywhere in `fichero-engine/src/fichero/`. `#1334`/`#1336` (11ty static site, closed) are a higher-level concept — they do not add a `/api/export/html` format handler. Issue was closed NOT_PLANNED previously; prior audit (2026-05-30) recommends reopen. Backend format gap confirmed. |
| #476 | Export: Netlify deploy via GitHub account | OPEN | No Netlify or GitHub OAuth code anywhere in `fichero-engine/src/fichero/`. `integrations/` directory contains devonthink, tinderbox, bookends — no GitHub/Netlify integration. Not implemented. |
| #505 | [Release Gate] 0.4.0 - Export Basics (JSON + Markdown) | OPEN | Gate requires JSON (#471, missing) + Markdown (#472, done). Gate is half-met at best. |
| #506 | [Release Gate] 0.4.1 - Export Documents (Word + PDF) | OPEN | Word is done (#473). PDF has no implementation and no dedicated backend issue. Gate cannot pass. |
| #507 | [Release Gate] 0.4.2 - Export Spreadsheets (Excel) | OPEN | Excel (#474) not implemented. Gate blocked. |
| #508 | [Release Gate] 0.4.3 - Export Web + Netlify | OPEN | Static HTML (#475) and Netlify (#476) both unimplemented. Gate blocked. |

---

## Detail: What Is and Is Not Implemented

### Implemented (backend + OpenAPI)
- `POST /api/export/markdown-folder` → `export_markdown_folder()` in `export_service.py:60`
  - Outputs `index.md`, per-doc `.md` files, `assets/`, `knowledge-graph.md`
  - KG wikilinks placeholder (not rendered — see line 354)
- `POST /api/export/word` → `export_word_docx()` in `export_service.py:126`
  - Custom OOXML builder (no python-docx dependency), images in two-col table
  - Both routes: synchronous, no job queue, return result directly

### In generated Swift client (wired to OpenAPI)
- `exportMarkdownFolderRouteApiExportMarkdownFolderPost` — in `FicheroAPIClient/Client.swift:12926`
- `exportWordRouteApiExportWordPost` — in `FicheroAPIClient/Client.swift:13024`

### NOT wired in SwiftUI app
Neither export method is called anywhere in the Swift app source (`fichero/fichero/`). There is no `ExportView`, `ExportPanel`, `ExportSheet`, document context menu export action, or `ExportService` Swift file. The generated client methods exist but are never invoked. This means even the two "done" backend formats (Markdown + Word) have no UI entry point yet — they are backend-complete but frontend-incomplete.

### Missing formats (no backend, no route, no client)
- JSON export (`/api/export/json`)
- Excel export (`/api/export/excel`)
- PDF export (no issue exists; prior audit recommends creating one)
- Static HTML export (`/api/export/html`)
- Netlify deploy (`/api/integrations/github/auth` + push + Netlify webhook)

### Async export job model (specified in #470, not built)
Issue #470 specifies `POST /api/export → {job_id}`, poll at `GET /api/export/{job_id}`, download at `GET /api/export/{job_id}/download`, with `ExportJob` model (`queued|running|complete|failed`). None of this exists. Current implementation is synchronous fire-and-return. The `ExportJob` model is not in `models.py` or anywhere in the codebase. The existing task queue (`workflows/tasks.py`) is not used by export routes.

---

## Recommended Actions

### Close now (DONE, code confirmed)
```bash
gh issue close 473 --repo dtubb/fichero --reason completed \
  --comment "Backend implemented: export_word_docx() in export_service.py, route /api/export/word mounted, OpenAPI client generated. No SwiftUI UI yet (tracked separately)."
```

### #472 — Already closed, verify
Already closed in GitHub. Closure is correct — implementation confirmed.

### Keep open (genuinely needs work)
- **#470** — Needs async job model OR issue body should be revised to match the simpler synchronous implementation that shipped. Recommend revising the issue body to reflect the sync design and tracking async as a future enhancement.
- **#471** — JSON format not started
- **#474** — Excel format not started
- **#475** — Static HTML not started (reopen per prior audit)
- **#476** — Netlify not started
- **#505–#508** — Release gates, block on prerequisites

### SwiftUI gap (new sub-issue or task)
The two working backend formats (Markdown, Word) need a SwiftUI entry point:
- Context menu on document/folder: "Export as..." → format picker
- Panel/sheet to pick output path
- Call `exportMarkdownFolderRouteApiExportMarkdownFolderPost` / `exportWordRouteApiExportWordPost` via the generated client

This is the prerequisite for all four release gates (#505–#508).

---

## Key File Paths

| Path | Role |
|---|---|
| `fichero-engine/src/fichero/export_service.py` | Backend: markdown + word implementations |
| `fichero-engine/src/fichero/api/routes/export.py` | FastAPI router: 2 routes mounted |
| `fichero-engine/src/fichero/api/main.py` | Router registration (`export.router, "/api"`) |
| `fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json` | OpenAPI spec: 2 export paths defined |
| `fichero/fichero-api-client/.build/.../GeneratedSources/Client.swift` | Generated Swift client: 2 export methods |
| `fichero/fichero/` (entire SwiftUI app) | No export UI wired — zero calls to export client methods |
