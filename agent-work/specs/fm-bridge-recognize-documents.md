# fm-bridge `--recognize-documents` — spec

Status: PROPOSED, awaiting lane-model-routing (protocol owner) and a build
window. Written 2026-09-04 by lane-mlx-catalog.

## Why this subcommand exists

macOS 26's `RecognizeDocumentsRequest` returns document structure — lines,
paragraphs and words, each with a region — where the old `VNRecognizeTextRequest`
returns words only. The engine calls the old API everywhere
(`vision_base.py:1734`). The new one is **Swift-only** (struct-based Vision
API); pyobjc cannot reach it, which is the entire reason a helper is needed.

It is the automatic, zero-byte geometry arm in the ratified split: Apple where
it works, Kraken (~1 GB, user-chosen) for the historical hands Apple cannot
see.

## Why fm-bridge rather than a new binary

fm-bridge already answers every packaging question a second binary would
reopen: it lives in `fichero_server/resources/bin`, is built by
`fichero-server/scripts/build_fm_bridge.sh` (with the `-target
arm64-apple-macos26.0` pin that a macOS-27 build host would otherwise break),
is staged by both engine entry points, is signed with the app, and is found by
the engine in every configuration. `--translate` joined it tonight by exactly
this route.

## Protocol

Follows the `--translate` precedent verbatim: **stdin JSON in, one JSON object
on stdout, `emitError(kind:)` on failure.**

Request:

    {"image_path": "/abs/path/page.jpg"}

Response:

    {
      "engine": "vision-recognize-documents",
      "pixel_frame": {"width": 2017, "height": 2000},
      "lines": [{"index": 0, "text": "…", "polygon": [[x, y], …], "bbox": [x, y, w, h]}],
      "words": [ … same shape … ]
    }

Every coordinate is **normalized 0..1, top-left origin**, flipped from Vision's
lower-left at the Swift boundary — the same place
`_vision_flip_bbox_to_top_left` does it on the Python side. A flip deferred to
the consumer is a half-page offset that looks like a bad model rather than a
bad convention.

`pixel_frame` is mandatory. Vision normalizes against the image it was handed;
a result that does not name that frame cannot be placed on a page with more
than one rendition (the bbox program's root cause).

`polygon` comes from `RecognizedTextObservation.boundingRegion.normalizedPoints`
— `NormalizedRegion` is a `Contour`, so the new API gives real quadrilaterals,
not just rectangles. Keeping the polygon makes the three-way comparison
polygon-to-polygon.

### Dispatch placement

Before the Apple Intelligence availability check, like `--translate`: Vision is
a different framework and works on machines with Apple Intelligence off.
Guard with `if #available(macOS 26.0, *)` and emit
`kind: "unavailable"` below that.

## The one operational hazard: cold start

Measured 2026-09-04 across six pages:

| | cold | warm |
|---|---|---|
| Caciques 533r (929x1346) | 168.1s | 1.7s → 0.7s |
| 1913_p05 (2017x2000) | 146.4s | 2.0s |
| blank 1000x1400 probe | 45.0s | 0.4s → 0.3s |

The multi-minute cost is a **one-time, system-wide** warm-up — not per-process
(a fresh process is fast once the system is warm), not per-page, and it does
not recur. But the first call on a cold machine can take **almost three
minutes**, and a per-page subprocess timeout sized for the warm case (seconds)
would kill it and report a Vision failure that is really a stopwatch failure.

Required of the caller: a generous first-call budget, or a `--warm-documents`
no-op invocation at engine start whose cost is paid once where nobody is
waiting on a page. Recommend the latter; it is three lines and makes every
subsequent timeout honest.

Also observed: 973 words cold vs 964 warm on the same page. The API is not
bit-deterministic across runs, so nothing downstream may assume stable counts.

## Quality caveat this arm must carry

On dense historical hands the new API finds almost nothing: 6 lines and 7 words
on Caciques 533r (~30 lines), 1 line on a 1927 diary page where Kraken found
12. Its results must be passed through `flag_sparse_geometry`
(`media/ocr_geometry.py`, landed in a564616fe) against a reference count from
the old Vision pass, so a page it cannot read is recorded as sparse rather than
as a page with six lines.

## Link cost

`import Vision` is a system framework, dynamically linked: no static bloat, and
the framework loads lazily on first use, so Apple Intelligence and Translation
paths pay nothing. A standalone build of the same code was 130 KB total.

## Test plan

- Golden-file test of the JSON shape against a committed synthetic probe image
  whose text positions are known (top marker y=0.03, bottom y=0.886) — this is
  what caught that the harness mapping was correct when the overlays looked
  wrong.
- The refusal path: pre-macOS-26 emits `kind: "unavailable"`, never an empty
  `lines` array.
- Sparse pass-through: a 6-box result against a 45-box reference is flagged.
