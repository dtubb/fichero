# Image-Editing Epic — Implementation Plan

**Author:** planner lane (overnight) · **Date:** 2026-05-26 · **Branch context:** plan only, no code
**Issues woven:** #462 #463 #464 #465 #466 #467 #468 #469 (crop/rotate/enhance/remove-bg/segment/preview-chain/toggle) · #1161 (deskew/color-correct/split — needs-design) · #1176 (paleography parametric pipeline + transient cache) · #928 (PDF-page loupe parity) · #1265 (prev/next nav + rubber-band region select + batch-apply)

---

## 0. The one architectural decision that drives everything

**#462 (edit-op chain) and #1176 (parametric recipe + transient cache) are the same system. #1161's "deskew/color-correct/split" are just additional ops in that chain. Build the storage model once.**

Three issues describe the same non-destructive core in different words:

| Issue | Its words | Same thing |
|---|---|---|
| #462 | "ordered chain of operations", "applied on-the-fly" | the recipe |
| #1176 | "operation recipes", "recompute from original + recipe" | the recipe |
| #463 | "apply ops in order, return result bytes" | materialize the recipe |
| #1176 | "materialize derivatives on-demand into transient cache" | materialize + cache the recipe |

**Consequence:** the Phase-1 storage model must carry #1176's provenance fields **from day one** (`source_doc_id`, `recipe_hash`, `stage`, `variant`, `run_id`) because 0.0.x is no-migration (Rule #9 — schema lives in the Pydantic model, `_ensure_table` picks it up on fresh DBs; there is no ALTER path). If we ship #462 with the thin model and bolt #1176 on later, we either migrate (forbidden) or rebuild. So: **design the rich model now, leave the cache/pinning machinery for Phase 2.5.**

**#1161 disposition:** not a separate track. Its backend = `deskew` + `color_correct` ops added to the same chain (Phase 2). Its frontend = the editing overlay already covered by #469 + #1265. Its "split" = #468. **Recommend relabeling #1161 as an epic-tracker (or closing it as superseded) once the ops land** — do not implement it as a parallel pipeline.

**#1265 cross-stack catch:** batch-apply-across-files is a *frontend* feature that needs a *backend* endpoint (apply one op to N doc_ids). That endpoint does not exist in #462–#468 — it is called out as **Phase 2.5 step B2** so the Swift lane is not blocked.

---

## 1. Dependency graph

```
                 ┌─────────────────────────────────────────────┐
   BACKEND       │ P1  edit-chain storage (#462) + preview (#463)│  ← foundation, blocks all
                 └───────────────┬─────────────────────────────┘
                                 │
        ┌────────────────────────┼───────────────────────────────┐
        ▼                        ▼                                ▼
   P2 ops (#464 crop,      P2.5 cache+pin (#1176)          (ops are independent
   #465 rotate, #466       + batch-apply endpoint           of each other once
   enhance, #467 rmbg,     (#1265-backend)                  the chain exists)
   #468 segment/split,
   #1161 deskew/color)
        │                        │
        └────────────┬───────────┘
                     ▼   (backend contract stable → regen OpenAPI → Swift client)
   SWIFT   ┌─────────────────────────────────────────────────────┐
           │ P3  #928 PDF-page loupe parity (independent, can start│
           │     in parallel w/ P2) + #469 original↔edited toggle  │
           └───────────────┬─────────────────────────────────────┘
                           ▼
           ┌─────────────────────────────────────────────────────┐
           │ P4  #1265 prev/next nav + rubber-band marquee +       │
           │     batch-apply UX (needs P2.5-B2 endpoint)           │
           └─────────────────────────────────────────────────────┘
```

**Critical path:** P1 → P2 (at least crop+rotate) → OpenAPI regen → P3 (#469) → P4.
**Parallelizable:** #928 (P3) can start immediately on the Swift lane — it's view-chrome parity, no backend dependency. P2.5 cache can land any time after P1.

---

## 2. Phases

Effort key: **S** ≈ ½–1 day · **M** ≈ 1–2 days · **L** ≈ 3+ days. Each step is one commit.

### Phase 1 — Edit-chain storage + preview foundation
**Lane:** backend (Python/FastAPI) · **Effort:** M · **Issues:** #462, #463, schema-half of #1176 · **Blocks:** everything

| # | Commit-sized step | Files |
|---|---|---|
| 1.1 | `ImageEditOp` + `ImageEditChain` Pydantic models **with provenance fields** (`source_doc_id`, `recipe_hash`, `stage`, `variant`, `run_id`, `created_at`, `updated_at`). `op` is a `Literal` enum seeded with `crop`,`rotate`,`enhance`,`remove_background`,`segment`,`deskew`,`color_correct` (declare all op names now; implement bodies later). | `fichero-engine/src/fichero/models/` (new `image_edits.py` or extend existing models module) |
| 1.2 | Register table via `_ensure_table` path — confirm DuckDB column mapping for `list[ImageEditOp]` (JSON column). No ALTER. | `fichero-engine/src/fichero/db.py` (verify, likely no edit if model auto-registers) |
| 1.3 | `recipe_hash` helper (stable hash of ordered ops+params) — the cache key + dedup key. Unit-tested in isolation. | `image_edits.py` |
| 1.4 | CRUD routes: `POST/GET/DELETE /api/docs/{doc_id}/edits`, `POST .../edits/reset`. Append-only (new chain version on add); old versions retained for undo. | new `api/routes/image_edits.py` + register in router list |
| 1.5 | `apply_chain(source_bytes, chain) -> bytes` pipeline skeleton — dispatch table `op -> fn`, **reuse `ImageLoader._load_pil` for source→PIL**; only `crop` wired as proof, others raise `NotImplementedError`. Runs in `asyncio.to_thread` (PIL is sync — see #1000 main-loop-blocking lesson). | `api/routes/image_edits.py` or `workflows/tools/_image_ops.py` |
| 1.6 | Preview route `GET /api/docs/{doc_id}/preview?edited=true|false`. `false` → reuse `storage.py::get_display_image` path; `true` → load source via IIIF/storage layer, `apply_chain`, return jpeg/png. | `api/routes/storage.py` (or `image_edits.py`) |
| 1.7 | Tests: chain CRUD round-trip, reset, recipe_hash stability, preview returns original vs edited bytes. Regen OpenAPI (`scripts/sync_openapi_schema.sh`), commit `openapi.json`. | `fichero-engine/tests/unit/` |

**Risk:** source-byte loading path. `storage.py` serves *display* and *source* separately; confirm which the apply pipeline should start from (full-res source, not display thumbnail). Decision: apply on **source**, downscale only for preview response if needed.

### Phase 2 — Individual operations
**Lane:** backend · **Effort:** M (crop/rotate) + M (enhance/rmbg) + L (segment/split) · **Issues:** #464, #465, #466, #467, #468, ops-half of #1161 · **Depends:** P1

Each op = one commit: implement `apply_op` body + params validation + unit test. **Port logic from `fichero_archive/_archive/fichero_legacy/tools/{crop,rotate,enhance,remove_background,segment,split}.py`** and reuse the existing `_annotation_input.py::crop_image` / `crop_pdf_page` primitives where they already exist.

| # | Step | Source to port |
|---|---|---|
| 2.1 | `crop` op (#464) — PIL `Image.crop`; auto-crop = OpenCV contour bbox | legacy `crop.py` + existing `_annotation_input.crop_image` |
| 2.2 | `rotate` op (#465) — PIL `Image.rotate(expand=)`; snap-to-90° within 5° | legacy `rotate.py` |
| 2.3 | `enhance` op (#466) — `ImageEnhance.{Contrast,Brightness,Sharpness}`; CLAHE for `doc_type='handwritten'` | legacy `enhance.py` |
| 2.4 | `deskew` + `color_correct` ops (#1161) — Hough/projection deskew; adaptive threshold. **Default params from user settings, not hardcoded** (#1152 / standing principle). | legacy + `~/code/archive` |
| 2.5 | `remove_background` op (#467) — OpenCV GrabCut primary, optional `rembg`; **forces PNG output** → preview must emit PNG when this op is in chain | legacy `remove_background.py` |
| 2.6 | segment/split (#468) — **architectural, own sub-plan.** Segments are *views* (byte-range / page-index child doc records), not file copies. Routes `POST /segment`, `GET /segments`, `POST /recombine`. Touches the Document parent/child model (god node — `get_blast_radius` on `Document` first). | legacy `segment.py`/`split.py`/`recombine_segments.py` |

**Risk (2.6):** segment/split mutates the document tree (creates child docs), unlike crop/rotate which only append to a chain. It is the one op that is *not* purely a recipe entry. Treat as a separate milestone (GitHub already isolates it: "0.3.2 - Wire: Image Segmentation"). Do crop/rotate/enhance/rmbg first; segment last.

### Phase 2.5 — Cache, pinning, provenance, batch endpoint
**Lane:** backend · **Effort:** M · **Issues:** cache-half of #1176, backend-half of #1265 · **Depends:** P1 (can run parallel to P2)

| # | Step | Notes |
|---|---|---|
| B1 | Transient derivative cache keyed `(doc_id, recipe_hash)` with TTL eviction + pin flag. Mirror the existing **`LibrarySnapshot` pin pattern in `storage.py`** for the pinning API shape. Cache dir under `run_id/stage/variant`. | #1176 acceptance: re-run = cache hit; unpinned evictable |
| B2 | **Batch-apply endpoint** `POST /api/docs/edits/batch` — body `{doc_ids: [...], op: {...}, region?: {x,y,w,h}}` → append same op to N chains. **This unblocks #1265 frontend.** | not in original issues — surfaced by this plan |
| B3 | Provenance query route — list derivatives + recipe for a doc (#1176 "provenance queryable"). | reads the fields added in 1.1 |

### Phase 3 — SwiftUI viewing parity + edit toggle
**Lane:** Swift/Xcode (owns the one Xcode) · **Effort:** S (#928) + M (#469) · **Issues:** #928, #469 · **Depends:** #928 none; #469 needs P1.6 + OpenAPI regen

| # | Step | Files |
|---|---|---|
| 3.1 | **#928 — PDF-page loupe/magnifier parity (start now, parallel to P2).** Mirror the existing image chrome onto PDF pages: reuse `ZoomableImagePreview` / `MagnifierPanel` / `ImageZoomToolbar` over `PageContentPane`. Treat "PDF page = rendered image." Note #928 dep on #783 (loupe fix) — confirm #783 status first. | `Views/Library/PageContentPane.swift`, `Views/Library/ImageViewer/*`, `MagnifierPanel.swift` |
| 3.2 | #469 — original↔edited toggle button in preview toolbar; flips `?edited=` query param on the preview fetch. Non-destructive (no write). | `ImageViewerComponents.swift` (`ZoomableImagePreview`), `ImageZoomToolbar.swift` |
| 3.3 | #469 — edit-chain inspector panel: list ops with per-op remove + "Reset all edits". Wire to P1.4 CRUD via generated client (use OpenAPI-typed fields — Rule #4). New `.swift` files → register with `scripts/add-swift-file.rb` (Rule #10). | `Views/Library/Inspector/` (new edit-chain panel), `Services/*Generated.swift` wrapper |
| 3.4 | Three-leg check: swiftlint + Xcode build + RunAllTests (mandatory, no exceptions). | — |

### Phase 4 — Nav + rubber-band + batch-apply UX
**Lane:** Swift/Xcode · **Effort:** L · **Issue:** #1265 · **Depends:** P3 + P2.5-B2

| # | Step | Files |
|---|---|---|
| 4.1 | Prev/next navigation buttons stepping between images **and between PDF pages**, paired with the document inspector — move through a doc/folder while editing. Reuses #928's "page = image" surface. | `PageContentPane.swift`, ContentView/LibraryView nav state, `DocumentInspector` |
| 4.2 | Rubber-band (marquee) region select overlay on image/page → yields `{x,y,w,h}` in image coordinates (reuse the magnifier's coordinate-mapping math — see `MagnifierCoordinateTests`). | new marquee overlay view over `TrackingImageView` |
| 4.3 | Batch-apply: take current op+region, apply across a multi-file selection via P2.5-B2 endpoint. Progress + undo affordance. | new batch-apply controller + `*Generated.swift` wrapper |
| 4.4 | Three-leg check. | — |

---

## 3. Lane / sequencing summary

| Phase | Lane | Effort | Gating |
|---|---|---|---|
| P1 storage+preview | backend | M | none — start first |
| P2 ops | backend | M+M+L | after P1 |
| P2.5 cache+batch endpoint | backend | M | after P1, parallel to P2 |
| P3.1 #928 parity | Swift | S | **none — start in parallel with P2** |
| P3.2–3.3 #469 toggle | Swift | M | after P1.6 + OpenAPI regen |
| P4 #1265 nav/marquee/batch | Swift | L | after P3 + P2.5-B2 |

**Recommended dispatch order:** P1 (backend) ‖ P3.1 #928 (Swift) → P2 crop/rotate + P2.5 (backend) → regen OpenAPI → P3.2/3.3 #469 (Swift) → P2 enhance/rmbg/segment (backend) → P4 #1265 (Swift).

**Worker model tier:** P1/P2.5/P2-segment are architectural → frontier (Sonnet+ for backend per cascade-selection memory). P2 crop/rotate/enhance are port-from-legacy → medium. P3.1 #928 is mechanical view-mirroring → medium. P4 marquee/coordinate math → frontier.

## 4. Top risks
1. **Schema-now-or-migrate-later** (P1.1): ship the full provenance model in the first commit or violate Rule #9. **Highest-leverage decision in the plan.**
2. **Source vs display bytes** (P1.6): apply ops on full-res source, not the display thumbnail, or edits degrade quality.
3. **segment/split is not a recipe op** (P2.6): it mutates the Document tree (child docs). `get_blast_radius` on `Document` before touching. Keep it last / its own milestone.
4. **PNG-mode propagation** (P2.5): remove-bg forces RGBA/PNG; preview response format must follow the chain, not assume JPEG.
5. **#1265 batch endpoint gap**: not in any existing issue — file it (P2.5-B2) or the Swift lane stalls.
6. **#928 ↔ #783 ordering**: #928 says fix loupe (#783) first. Confirm #783 status before 3.1.

## 5. Issue housekeeping recommended
- File a new backend issue for **P2.5-B2 batch-apply endpoint** (blocks #1265).
- Relabel **#1161** as epic-tracker / superseded-by #462+#468+#469 (its scope is fully absorbed).
- Confirm **#783** (loupe fix) status — gates #928.
- #928 currently on milestone "0.0.2"; the rest are 0.3.x / 0.0.3. Confirm whether #928 ships in 0.0.2 standalone (it can — pure Swift, no epic dependency).
