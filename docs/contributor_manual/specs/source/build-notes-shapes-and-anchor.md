# Source Model — Build notes: shapes on the anchor, and where the retirement begins (slice 7)

> Milestone: source-model
> Manual: TBD — none of its own; engineering notes behind `segments-and-geometry.md`.
>
> **Status: DRAFT.** Engineering detail for the engine worker. The maintainer does not need to
> read this file; the design is in `segments-and-geometry.md` ("Shape", "Its picture") and the
> foundation (`source.builds-on-the-anchor`). No behaviours of its own. Counts were taken on
> disk on 2026-09-19 by a code worker (`grep`, source and tests apart); they are sizes, not
> exact lists, and the worker re-counts before editing. Ids keep the code's current nouns.

## Slice 7 — shapes beyond the rectangle (#4925)

**Pins:** `source.segment.shape-kinds`, `source.segment.curved-baseline`,
`source.segment.picture-by-shape`, the pictures part of `source.derived.recomputable`, and the
first step of `source.builds-on-the-anchor`.

### The size of the retirement, before anyone edits

| Type | Engine source | Engine tests | Swift app | Swift tests | Elsewhere | Fate |
|---|---|---|---|---|---|---|
| `OCRGeometryBox` (its own `bbox`) | 56 references in 7 files | 79 in 19 files | 33 in 13 files | 21 | 1 schema in the OpenAPI contract | **Stays as the old block's format**, read only through the guarded reader (slice 6). It is retired by *writers* moving to passes, tool by tool, after this slice. Not touched here |
| `AgentNoteSourceAnchor` | 9 in 2 files (`models/__init__.py`, `api/routes/system/agent_memory.py`) | 5 (the contract file only) | 0 | 0 | the generated CLI surface; the contract | **Retired in this slice** (small, contained) |
| `NodeRegion` | 39 in 9 files | 70 | 1 | 0 | | **Not retired.** It says where a node sits in its parent. For awareness only |
| direct use of `Artifact.ocr_geometry` | 67 in 15 files (heaviest: `api/routes/document/artifacts.py` 18, `workflows/tools/vision_base.py` 8, `workflows/tools/diary_entries.py` 8, `workflows/tools/llm_base.py` 7) | 23 files | 11 in 5 files (`OCRGeometrySelection`, `Artifact`, `ArtifactPanel+Regions`, `ZoomableImagePreviewMac+Regions`, `ArtifactService`) | | | Readers go behind `read_ocr_geometry` in slice 6; app readers go to the segment store in app slice A |

The five busiest files for `OCRGeometryBox`: `media/ocr_geometry.py` (21),
`media/geometry_merge.py` (11), `tests/unit/media/test_ocr_geometry_helpers.py` (9),
`tests/unit/workflows/test_ocr_geometry_addressing.py` (8),
`tests/unit/workflows/test_diary_entries.py` (8). `.bbox` appears 78 times in engine source and
49 in the app, but that count mixes boxes, node regions, documents and annotations: an upper
bound, not a list.

**So this slice retires one small type and widens the anchor; it does not touch the 56 + 33
box references.** Saying so plainly is the point of the table.

### `SourceAnchor` gains shapes (additive)

`SourceAnchor` is `extra="allow"` and already has `rect`, `polygon` (closed, three points or
more), `rotation`, `rendition_id`, a character span, `granularity` and `refines`. It is in the
OpenAPI contract as two schemas (`SourceAnchor-Input`, `SourceAnchor-Output`), so the app has two
generated types and, after app slice A, one hand-written `SourceAnchorValue`.

New, all optional, so every stored anchor stays valid:

- `shapes: list[AnchorShape] | None`, where `AnchorShape` is `{ kind: "rect" | "polygon" |
  "path" | "point" | "time", points: list[list[float]] | None, t_start: float | None, t_end:
  float | None }`. `path` is an open line (two points or more); `point` is one `[x, y]`; `time`
  uses seconds and carries no points. When `shapes` is absent the anchor means what it means
  today (`rect`, or `polygon`). When present, `rect` is **the bound of the area shapes, worked
  out by the engine**; a client that sends both and they disagree is refused.
- `media_ref: str | None`: the recording a `time` shape belongs to (the field only; recordings
  are a later slice).
- `baseline` stays on `Segment` (slice 3), as a line of two points or more, with
  `baseline_kind: "baseline" | "topline" | "centerline"` (Kraken's three).

**Validation is for each kind, and the rectangle's rules do not loosen.** `validate_rect`
(`models/anchors.py`; called from `NodeRegion._check_rect`, `SourceAnchor._check_rect`, and
twice in `media/region_math.py`) keeps every rule it has: four finite numbers; inside the image
for normalised space; width and height above zero; `x + width` and `y + height` not past the
edge. New validators sit beside it: `validate_points` (finite; inside the image), a path needs
two points, a polygon three, a point exactly one, a time span `0 <= t_start < t_end`. **A
fixture test asserts that every rectangle `validate_rect` refused before this slice is still
refused** (zero width; off the right edge; not a number).

**The derived box.** For area shapes, the bound of all of them. For a lone point, a box of zero
width and height at the point: allowed in `Segment.bbox_*` (engine-written) and **never** put
into `SourceAnchor.rect`, which stays unset for a point. For a `time` shape, no box.

**Kinds.** `ANCHOR_GRANULARITIES` (`models/anchors.py`; nineteen words, among them glyph, word,
line, paragraph, column, block, figure, table, marginalia, footnote, header, entry, page,
spread) is documented but read by nothing. It becomes the **seed of the one kinds list**
(`source.segment.open-kinds`): `Segment.kind` and `SourceAnchor.granularity` draw from it, and
SegmOnto's zone and line names are added to it as data. One list, as the design says.

### Retiring `AgentNoteSourceAnchor`

It is a subset of `SourceAnchor` (`document_id`, `page_id`, `char_start`, `char_end`) plus
`expediente` and `page_label`. `api/routes/system/agent_memory.py` takes and returns it. Agents
already call this route, so the wire must not break:

- The route's request model accepts a `SourceAnchor`; the old two extra keys are accepted and
  carried in the anchor's allowed extras (`SourceAnchor` is `extra="allow"`), and returned as
  they were. A request in the old shape still validates (test with a recorded old request).
- The class is deleted; stored agent notes need no migration (the stored JSON is already a
  valid `SourceAnchor` with extras).
- The OpenAPI contract loses one schema; the CLI regenerates; `check_openapi_client_parity.py`
  must pass. No Swift code uses the type.

### A segment's picture, cut to its shape

`media/region_crops.py` (`materialize_region_crop`) crops a rectangle and stores the crop as a
`Rendition`, and already refuses (`RegionCropUnavailable`) when a region was measured on a
different image than the one in hand. This slice extends **that** machinery; it does not add a
second cropper.

- `segment_picture(db, segment_id, *, size, margin, straighten, mask) -> stored image ref`:
  resolves the segment (through `resolve_segment`), takes the image named by its anchor's
  `rendition_id`, crops to the derived box plus margin, **masks outside the polygon** when
  `mask` is true (transparent), and, for a line with a baseline when `straighten` is true,
  resamples along the baseline so the line is level (what a recogniser wants).
- Route: `GET /api/segments/{segment_id}/picture?size=&margin=&straighten=&mask=`, answering
  with a storage reference the app fetches through the existing storage routes. **Never a local
  path** (the engine may be remote).
- A picture is a worked-out thing: cached, keyed by segment id, segment version, rendition id
  and the four options; made again when the version changes; never the record. Absent, not
  faked, when the image is missing or the segment's image is not the one available
  (`RegionCropUnavailable`, reused).
- Making pictures is throttled background work when done in bulk (a training export), and
  bounded when done on request.
- `economy_htr.crop_line_strips` (padded rectangles, per Apple Vision line box) is the existing
  line cropper. It is **replaced by this function** where it is called, not kept beside it.

**Refusals** (typed, each tested): shapes and `rect` that disagree; a path of one point; a
polygon of two; a point outside the image; a time span with no `media_ref`; a picture asked of a
provisional (`legacy:`) id is allowed (it is a read) but a picture asked across images with no
alignment is refused with `RegionCropUnavailable`.

**Tests, by behaviour.**
- `source.segment.shape-kinds`: a point, a path, a polygon, two polygons, and a time span each
  store and read back; the old-rectangle fixture still refuses what it refused; an anchor saved
  before this slice (no `shapes`) still reads and means the same.
- `source.segment.curved-baseline`: a five-point baseline round-trips; a Kraken line converted
  in slice 6 keeps its baseline and its polygon.
- `source.segment.picture-by-shape`: a triangle's picture is transparent outside the triangle;
  a tilted line's picture is level when straightened (the baseline's end points share a row,
  within a pixel); the same options twice return the same stored picture; a version bump makes
  a new one.
- `source.builds-on-the-anchor` (first step): an agent note sent in the old shape is accepted
  and returned unchanged; `AgentNoteSourceAnchor` no longer exists in the code or the contract.
- Old library: opens twice, no error, nothing rewritten.

**Nothing here needs the maintainer.** Two things for the manager: the agent-memory route is
called by agents today, so the old request shape must keep working (above); and
`economy_htr`'s cropper being replaced touches a shipped workflow tool, so its own tests move
with it.
