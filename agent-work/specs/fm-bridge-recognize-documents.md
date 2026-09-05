# fm-bridge `--recognize-documents` — spec

Status: ACCEPTED by lane-model-routing (protocol owner) 2026-09-04, written to
their four requirements; implemented in `fichero-server/bin/fm-bridge/FmBridge.swift`,
compile-verified, awaiting their diff review and a build window.

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

## Protocol requirements (lane-model-routing, as owner)

1. **Error kinds reuse the existing vocabulary.** `json` for a bad payload,
   `unavailable` for pre-macOS-26, `not_found` for a missing or unreadable
   image, `vision` for anything the framework raises. The Python side maps
   kind → typed exception and an unknown kind degrades to a generic
   RuntimeError, so inventing a kind is a silent downgrade rather than a new
   behaviour.
2. **`elapsed_ms` in every success payload.** With 168s cold and 0.7s warm on
   the same page, elapsed time is the only way the caller can tell a cold start
   from something being wrong.
3. **`image_path` is bridge-internal.** Fine between engine and subprocess on
   one machine; it must NEVER surface in an API request. The engine may be
   remote from the client, and a path that leaks outward is a path that
   resolves on the wrong machine.
4. **Never an empty result where a failure occurred.** A page with no text and
   a page that failed must not look alike. This is the property the whole
   bridge is built on.

**Timeouts are not this spec's business.** `_compute_timeout(config, kind)`
already takes a typed kind, and recognition gets its own rather than borrowing
the chat budget. The requirement is only: generous first call, seconds
thereafter. The number belongs in that function.

**Non-determinism is caller-facing.** The same page returned 973 words cold and
964 warm. Nothing may cache or diff on word count, and any artifact provenance
recording "N words" is a this-run-only fact. Two runs of one page differing is
not an OCR regression.

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

`--warm-documents` exists for this, and the caller owns it
(lane-model-routing): fire-and-forget, NEVER awaited on the engine boot path —
a 168s blocking start is worse than the bug it fixes — and never fatal. On an
already-warm machine it costs ~0.3s, so running it every start is fine.

**The warm-up must go through a temporary FILE, not an in-memory CGImage.**
Measured 2026-09-04: a CGImage warm-up returned `available: true` in 0.4s and
left the next real page paying 48.6s anyway. `perform(on: CGImage)` and
`perform(on: URL)` are different paths and only the second is what recognition
uses. A warm-up that does not warm the path in question is worse than none,
because it reports success and changes nothing.

**The prediction was tested, and the warm-up FAILED ITS PURPOSE.** Later the
same night the machine went cold again and the sequence was measured directly:

    --warm-documents           45,530 ms   (it DID pay the cold cost)
    --recognize-documents      51,310 ms   (the next real page paid it AGAIN)
    --recognize-documents         572 ms   (same page, now warm)
    --recognize-documents         387 ms

So the file-based warm-up is a genuine improvement over the CGImage one — that
returned in 0.4s while cold, proving it never touched the expensive path, while
this one pays 45s exactly as predicted. But paying it did not spare the next
page, which is the entire point. Warming is evidently NOT global across images:
something per-image — dimensions or an internal model variant is the obvious
suspect, and neither is confirmed — is re-paid on the first call for a page
unlike the warm-up's 64x64 PNG.

**Consequence: as specified, `--warm-documents` is the worst of both worlds** —
it costs 45s on a cold machine and still leaves the first real page paying full
price. It must NOT be wired as-is. Options, none yet measured:

1. Warm with an image the size of a real page rather than 64x64, and re-measure
   the same four-step sequence.
2. Abandon warming and give recognition a first-call timeout generous enough to
   absorb ~170s, treating cold start as a cost rather than a thing to hide.

Option 2 is honest and cheap and needs no new code; option 1 is better if it
works, and one measurement settles it. The subcommand stays in the binary
(dormant, no consumer) so that measurement is possible without another build.

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
