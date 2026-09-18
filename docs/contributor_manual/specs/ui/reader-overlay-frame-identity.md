---
status: DRAFT
title: Reader overlay frame identity
spec: reader-overlay-frame-identity
created: 2026-09-16
---

# Reader overlay frame identity

> Milestone: reader-overlay-frame-identity
> Manual: TBD — this is invisible when it works, so the manual needs only the consequence, in the
> transcribing section: if you crop, rotate, or straighten a page, your existing highlights and
> boxes stay on the same ink — and what to do if one ever looks displaced.

Highlights, region/word boxes, and OCR "readings" must draw over the **same pixels they were
measured on**. When they don't, they "end up in the wrong spot" (CD, 2026-09-16). This spec fixes
the identity rule that decides whether an overlay is still valid on a given rendition, and locks the
invariant with tests.

## Why the transform is NOT the problem

All three overlays already convert their normalized `[x,y,w,h]` through ONE shared mapping,
`BoundingBoxGeometry.viewRect(normalized:in:visible:)`, framed to the same
`PreviewImageGeometry` (`visible` window + `drawnFrame`). The pointer/click path maps in through the
same two rects, so "the click hits the box it covers" holds by construction. The 2026-09-03
unification (`agent-work/design/annotation-region-bbox-unification-review.md`) settled the transform;
the coordinate conventions were never the defect. **Do not add a second transform.**

## The rule: an overlay is valid only on a frame it was measured on

A normalized box is valid on a rendition **iff that rendition has not re-framed the pixels** since the
box was measured. The overlay frame-gate (`overlayFrameMatches`, one predicate for all three layers)
draws when the frames match and **skips** (blank) when they don't — it never re-projects. The gate is
only as correct as the answer to "did this rendition re-frame?" — carried by `hasOwnFrame`.

## Behaviors

- `frame.reframing-ops-gated` **[OK 2026-09-17]** — `DocumentRendition.frameChangingOps` lists EVERY
  engine op that moves pixels: `crop`, `auto_crop_border`, `rotate`, `straighten`, `flip_horizontal`,
  `flip_vertical`, `auto_deskew`. An edited page built from any of them computes `hasOwnFrame: true`,
  so node-frame overlays SKIP it rather than draw over re-framed pixels. (Flips + auto-crop were
  missing → the reported bug; a flip mirrors `x→1−x−w`, so edge words were maximally wrong while
  centred ones looked fine. `auto_deskew` was ALSO missing until 2026-09-17 — same class of bug, one
  op over: it rotates by a detected angle through the same dispatch branch as `rotate`/`straighten`,
  `media/image_ops.py:253-254`, produced by `workflows/tools/deskew_images.py`.) Pinned by
  `RenditionEditStatesTests.frameHonesty` + `.frameChangingOpsCoversEngineReframingSet`.
- `frame.same-frame-ops-draw` **[OK]** — enhance-family ops (`enhance`, `grayscale`, `denoise`,
  `remove_background`, `adaptive_binarize`, `sharpen`) keep the frame, so overlays keep drawing. Same
  tests.
- `frame.engine-authoritative` **[GAP]** (#4681) — the client list is a hand-maintained MIRROR of the
  engine's op vocabulary (`api/routes/ingest/image_editing.py` for the op registry/validation,
  `media/image_ops.py` for the actual pixel dispatch — not `ingest/image_editing.py`, which doesn't
  exist at that path). It can fall behind again (that is exactly how `auto_deskew` went missing: it
  isn't even in `image_editing.py`'s `_OPERATION_MODELS`/`_PARAMETERLESS_OPERATIONS` validation set,
  only in `image_ops.py`'s dispatch and the workflow that appends it to a saved chain). Target: the
  engine stamps `frame_status` (`same`/`reframed`/`unknown`) on each rendition it produces (the
  interactive editor path does not today — only the importer manifest does), and the client reads
  that one field, deleting `frameChangingOps`.
- `frame.fail-closed` **[GAP]** (#4714) — an op the client does not recognize should count as
  `hasOwnFrame: true` (skip = blank) rather than `false` (draw), so a future engine op can never
  silently misplace overlays. Today the default is draw (false).
- `frame.pdf-marks-gated` **[GAP]** (#4715) — saved annotation MARKS on the PDF surface
  (`PDFPageWithToolbar.swift`) are not frame-gated (follow-up #5 from the 2026-09-03 review). PDF OCR
  boxes themselves are handled (rotation + cropBox offset).

## Test matrix

| Behavior | Test | State |
|---|---|---|
| reframing-ops-gated | `RenditionEditStatesTests.frameHonesty`, `.frameChangingOpsCoversEngineReframingSet` | ✅ |
| same-frame-ops-draw | `RenditionEditStatesTests.frameHonesty` | ✅ |
| transform is single & correct | `BoundingBoxGeometryTests`, `PreviewImageGeometryTests`, `PreviewPointerRoundTripTests`, `AnnotationFrameIdentityTests` | ✅ (pre-existing) |
| engine-authoritative | — | ❌ needs engine `frame_status` stamping |
| fail-closed | — | ❌ |
| pdf-marks-gated | — | ❌ |

## Open questions

1. Should `segment`, `remove_background`, `split` be audited as reframing? (Assumed same-frame today.)
2. Where does the engine stamp `frame_status` — in `image_editing.py`'s produced rendition rows, and
   is it backfilled for existing edited libraries?
3. Fail-closed default: does inverting to "unknown ⇒ skip" ever blank a legitimately-valid overlay?

## References

- `agent-work/design/annotation-region-bbox-unification-review.md` (the canonical prior analysis)
- Fix: `fichero/fichero/Services/RenditionService+EditStates.swift` (`frameChangingOps`)
- Gate: `fichero/fichero/Views/Preview/ImageViewer/ZoomableImagePreviewMac+Renditions.swift`
  (`overlayFrameMatches`)
- Transform: `fichero/fichero/Models/BoundingBoxGeometry.swift`, `Models/PreviewImageGeometry.swift`
