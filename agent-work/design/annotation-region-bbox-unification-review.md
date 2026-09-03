# Annotations, regions, and bounding boxes: where the three paths diverged

**Date:** 2026-09-03 · **Lane:** markup-annotations · **Status:** partial unification landed; follow-ups listed

Daniel's reading of the symptoms was that "bounding boxes are fine" and annotations
were built on a different code path — across a region backend, a bounding-box backend,
and a spread backend that were never fully tied up. This is the map, what was actually
different, what has been converged, and what still needs a ticket.

The short version: **the coordinate conventions were never the problem.** All three
paths speak normalized `[x, y, w, h]`, top-left origin. What diverged is *frame
identity* — which pixels a rect was measured on — and *addressability* — how you name
one rect again later. Both failures live on the Swift write path, not in the server
contracts.

---

## The three paths

### 1. Regions — geometry boxes on an artifact

- One endpoint carries all four verbs: `PUT /api/artifacts/{id}/regions`
  (`api/routes/document/artifacts.py:1226`), with `op` ∈ `move | delete | add | combine`
  (`RegionEditOp`, `artifacts.py:1014`). There is no separate `add_region` /
  `move_region` path; the Swift `ArtifactService` method names are client-side sugar.
- Shape: `OCRGeometryBox.bbox` (`media/ocr_geometry.py:52`), documented normalized
  0..1, top-left, validated at `ocr_geometry.py:79`.
- Frame identity: `OCRGeometryResult.rendition_id` (`ocr_geometry.py:120`) — **one
  frame for the whole box set**, surfaced to clients as `geometry_rendition_id`.
- Storage: a JSON blob in the `artifacts.ocr_geometry` VARCHAR column. Boxes are
  **positional and have no ids** (`artifacts.py:1006`); every verb addresses them by
  list index.
- Undo: whole-artifact snapshot restore, plus an in-band `metadata["curation_log"]`
  that survives export (`artifacts.py:1187`).
- **Client display is FRAME-GATED**: `geometryFrameMatchesDisplay`
  (`ZoomableImagePreviewMac+Renditions.swift:96`) refuses to draw or select against
  pixels the boxes were not measured on. Match-or-skip, never transform.

### 2. Annotations — rows in their own table

- `POST/GET/PATCH/DELETE /api/annotations` (`api/routes/document/annotations.py:36`).
- Shape: `SourceAnchor.rect` (`models/anchors.py:208`). **Not** `bbox` — that field was
  removed server-side; the Swift `regionRect` is a computed fallback
  (`Services/AnnotationService.swift:172`).
- Frame identity: `SourceAnchor.rendition_id` (`anchors.py:198`) — **per annotation**,
  not per set. The model comment names a frameless rect as the defect the anchor type
  exists to remove.
- Storage: real rows in `annotations`, each with a stable id, scoped by
  `document_id`/`page_id`/`folder_id`.
- Undo: hard row delete + snapshot upsert; **no `curation_log`**, no `deleted_at`.

### 3. "Spread" — there is no third backend

Exhaustive grep finds no spread table, model, or endpoint. What exists is the **split**
path: `POST /api/images/{id}/split` (`api/routes/ingest/image_editing.py:1346`), whose
input is **absolute source pixels** (`ImageSplitRequest.bboxes`, `image_editing.py:140`),
converted at `image_editing.py:706` into a normalized rect **of the parent's frame** and
stored on `Document.region_in_parent` (a `NodeRegion`, `models/anchors.py:126`). Alone
of the three it uses a genuine soft delete (`deleted_at`). "Spread" otherwise names a
query tier (`db/node_levels.py`) and a client paging mode (`Models/LayoutMode.swift`) —
neither persists geometry.

So the honest count is **two geometry backends plus a pixel-space split path**, not
three parallel systems.

---

## The actual divergences

| | Region boxes | Annotations | Split |
|---|---|---|---|
| Rect space | normalized only | normalized **or pixel** (`AnchorSpace`) | pixels in, normalized out |
| Zero-area rect | **accepted** (`ocr_geometry.py:87`) | rejected (`anchors.py:104`) | rejected |
| Frame id | per box SET | per row | field exists, never written |
| Addressed by | list **index** | stable **id** | parent + `split_source_id` |
| Undo | snapshot + curation log | snapshot, no log | soft delete |
| **Display frame gate** | **yes** | **no** (until today) | n/a |

Three validators exist for one shape: `OCRGeometryBox._validate_bbox`
(`ocr_geometry.py:79`) and `validate_rect` (`anchors.py:67`, shared by `SourceAnchor`
and `NodeRegion`). `ocr_geometry.py` does not call `validate_rect`.

### The two that were actually hurting

**(a) Every annotation ever written claimed the node's own frame.**
`AnnotationService.wireAnchor` (`Services/AnnotationService+Create.swift`) constructed a
`SourceAnchorInput` with `documentId`, `pageId`, `space`, `rect` — and dropped
`renditionId`, which the generated client and the engine have both carried all along.
The preview *opens on the preferred rendition* (background-removed > enhanced > original,
`ZoomableImagePreviewMac+Renditions.swift:9`), so the common case is that Daniel is
marking up a rendition. Every one of those marks was recorded as if drawn on the base
page, and then drawn on every other rendition too, because the mark layer had no gate.

**(b) The word snap read ungated geometry.** `createAnnotation` snapped highlights to
`ocrGeometry.wordBoxes` directly rather than `frameMatchedGeometryBoxes`, so a highlight
could hug word boxes measured on a rendition that was not on screen.

### The one that is structural

**Regions have no identity, so annotations cannot reference them.** The link between a
saved annotation and the region under it is a **1% float-extent comparison** —
`RegionInteractionLayer.sameExtent(_:_:tolerance: 0.01)`. That is what stands in for a
foreign key. Move a region through the region backend and every annotation bound to it
silently detaches. Ratings compound this: a ✓→✓✓ transition is implemented as delete +
recreate, burning an annotation id and two audit rows per click.

---

## What was unified in this pass (iterate, not replace)

1. **Annotations name their frame on write.** `renditionId` threaded
   `AnnotationStore.addNote` → `AnnotationService.addNote` → `wireAnchor`, and passed by
   every writer on the image surface (drag-drawn marks, selection highlights, the check
   tool). The engine already accepted it; this was a client-only gap.
2. **Annotations read their frame back.** `DocumentAnnotation.renditionId` →
   `AnnotationMark.renditionId`.
3. **Annotations are frame-gated like regions.** `annotationFrameMatchesDisplay` routes
   through the *same* `overlayFrameMatches` matrix `geometryFrameMatchesDisplay` uses —
   one predicate, so a highlight and the region box under it cannot disagree about
   whether the page on screen is theirs.
4. **The word snap reads the frame-matched geometry**, the same set the region overlay
   draws and selects from.
5. **"Same place" now means same frame** in the check tool's cycle, on both the click
   path and the selection path.
6. **The inspector's annotation row lights its mark on the page**, the annotation twin
   of `RegionSelection` driving the region overlay.

Tests: `Tests/Unit/general/Views/Preview/AnnotationFrameIdentityTests.swift`.

---

## Verified against the real library (2026-09-03, scratch APFS clone)

The original `Marshall Diaries.fichero` was never opened. A copy-on-write
clone plus its WAL (the WAL mattered — the package had not been checkpointed
since 16:13, so every write from that evening lived in it) was queried
in-process through the real FastAPI routers. Findings:

| Question | Answer |
|---|---|
| Annotations carrying a rect | **12 of 12** |
| Annotations carrying a `rendition_id` | **0 of 12** |
| Geometry artifacts | 955 |
| Geometry artifacts with `provider: "user"` | **0** |
| Artifact providers | `manifest-importer` 794, `apple` 155, `openrouter` 6 |
| `artifact.regions_edit` in the audit trail | 2, ever |
| Writes during the evening session | **one `document.move`** |

Three things follow, and two of them corrected what code-reading alone had
suggested:

1. **The frame-identity finding is confirmed outright.** Every annotation in
   the real library claims the node's own frame, because the client never
   sent one.
2. **Bug 2 is a NEVER-SAVED bug, not a never-restored one.** No artifact or
   annotation row was created during the session where regions "disappeared".
   Drawing a marquee persists nothing; persistence needs the explicit promote
   gesture (pencil badge, double-click a marquee, or the context menu), and
   `clearEphemeralRegionState()` discards marquees on document change. Daniel
   drew, switched view, and there was nothing to come back to.
3. **`createRegionsArtifact` has never once produced a row here.** With only
   two `regions_edit` calls ever and no `provider: "user"` artifact, the
   region verbs have essentially never persisted anything in this library —
   and when they did, the boxes went into an artifact a machine pass had
   already written, via the `if let existing = ocrGeometryArtifactId` branch.

Consequence for the ladder fix: the artifact-level `provider: "user"` signal
covers only the bootstrap path, which is the rare one. The per-box signal
(`provider: "user"` / `source: "manual"`, which the engine has always
stamped) is the one that matches reality — and the Swift mirror was dropping
it in `OCRGeometry.init(generated:)`, the same defect shape as `wireAnchor`
dropping `rendition_id`. That is fixed; the boxes are now visible as
hand-drawn. It is deliberately NOT used to reorder the ladder, because the
lean list omits geometry and hunting for curation would cost a round-trip per
candidate on every page load.

---

## Follow-ups that need their own tickets

1. **Give region boxes stable ids.** The blocker is stated in the code
   (`artifacts.py:1006`): inventing ids at one call site would fork the geometry
   contract. Add `box_id` to `OCRGeometryBox`, preserve it through `_validated_box` and
   the `combine` path, then give `SourceAnchor` a `region_id` and delete `sameExtent`.
   This is the fix that makes region↔annotation a real relation.
2. **One rect validator.** Make `OCRGeometryBox._validate_bbox` delegate to
   `anchors.validate_rect`. Behaviour change: zero-area boxes currently accepted would
   start failing, so existing geometry needs a sweep first.
3. **Ratings should mutate, not re-create.** `annotation.update` exists; the check cycle
   should use it.
4. **The split path never sets `NodeRegion.rendition_id`** (`image_editing.py:728`), and
   `region_math.require_original_frame` refuses to compose any rect that names one — so
   the composition path only works for the null case. Splitting a rendition is
   unrepresentable today.
5. **The PDF surface's mark layer is still ungated** (`PDFPageWithToolbar.swift:179`).
   The image surface is fixed; the PDF twin needs the same predicate.
6. **Region membership is not a query.** `list_annotations` has no "has anchor" filter;
   the client fetches every annotation and filters in memory on `hasRegion`. Fine at
   Marshall-diaries scale, not fine indefinitely.
7. **Ephemeral marquees look like data loss — and this is the CONFIRMED cause of the
   reported bug, so it should be ticketed first.** Drawing a region creates a marquee
   that is discarded on document change unless explicitly promoted (pencil badge /
   double-click / context menu). The real library shows the promote path has run twice,
   ever. Daniel's own ruling — "if we draw it, we should be able to save it" — argues
   the draw itself should persist, or the impermanence should be unmistakable on screen.
   This is a design decision, not a defect to patch unilaterally.
8. **Hand-drawn regions land in machine artifacts.** `promoteMarquees` appends to
   whichever artifact the ladder picked, so a person's boxes end up inside a machine
   transcription and the artifact's provenance keeps saying `apple`. They should go to
   the user's own artifact. This changes what the combine/delete verbs can address by
   index, so it needs its own pass.

---

## What this does NOT explain

The markup bands landing "down and to the right" of the pointer was **not** an
annotation-vs-region divergence. That was a scale error in the shared overlay framing:
`DrawnImageFrame.compute` framed to `scrollView.bounds` while the normalized visible
window came from `documentVisibleRect`, which is clipped to the clip view — ~17pt apart
under legacy scrollers. Fixed separately, with a round-trip test against real AppKit
views. Both layers were wrong together, which is why regions "looked fine": they were
wrong by the same 2% as everything else on the page, and only a drag makes a 2% error
legible.
