---
status: DRAFT
title: Reading markup & annotations
spec: reading-markup-annotations
created: 2026-09-16
related: [reader-overlay-frame-identity]
---

# Reading markup & annotations

> Milestone: reading-markup-annotations
> Manual: TBD — the user manual's reading section needs "Marking up a source": highlighting, the
> check gesture (✓ → ✓✓ → ✓✓✓ → clear) and that it is a check rather than a star, notes and tags,
> reviewing your markup per page, and turning a highlight into a claim.

Reading is work: a reader highlights, checks/rates, notes, and tags a source, and that markup becomes
durable, queryable, and promotable into knowledge. This spec pins the annotation **data model and
behaviors** — kinds, the check cycle, the review representation, promotion to a claim, export. It is
the companion to [[reader-overlay-frame-identity]], which pins only WHERE a mark draws (the pixel
transform); this pins WHAT a mark is and how it behaves. Grounded in the ruling doc
`agent-work/design/reading-markup-coding-system.md` (Daniel, 2026-08-30).

## Intent (the design)

- One annotation record per mark, anchored to a source span or region, with a **closed** set of kinds.
- A **rating is a Check, not a star** — checking a line cycles ✓ → ✓✓ → ✓✓✓ → clear (the core reading
  gesture; ratings 1–3 render as check ticks, the model allows 1–5).
- Markup is reviewable as its own surface (grouped by page) and exportable as standards JSON-LD, and a
  highlight can be **promoted to a knowledge claim** while remaining a surface mark.

## Behaviors

- `markup.kinds.closed-vocabulary` **[OK]** — an annotation's `kind` is one of `highlight, note,
  rating, bookmark, comment, line, underline, strikethrough`; an unknown kind is rejected
  (`AnnotationKind`, knowledge.py:1328). Pinned: `test_annotation_list_schema.py`, `test_annotations.py`.
- `markup.rating.bounded-1-5` **[OK]** — create/patch reject a `rating` outside `[1,5]`
  (annotations.py:69,254). Pinned: `test_annotations.py`, `test_routes_annotations_actions.py`.
- `markup.check.cycle` **[OK]** — checking a line with no rating creates `rating=1`; re-checking
  advances 1→2→3; a fourth check clears (deletes) the mark: ✓ → ✓✓ → ✓✓✓ → clear
  (ZoomableImagePreviewMac+Annotations.swift; RegionInteractionLayer.swift). Pinned:
  `AnnotationCheckCycleTests` (the pure progression `AnnotationCheckCycle.next`).
- `markup.rating.renders-as-check` **[OK]** — in the annotations representation a `rating` labels as
  "Check" and displays `"✓" * rating`, never a star (views.py:352,403). Pinned: `test_routes_views.py`.
- `markup.review.grouped-by-page` **[OK]** — `?representation=annotations` returns entries grouped per
  page, in page order with a document-level group last, each cited "p. N" (views.py:361). Pinned:
  `TestAnnotationsRepresentation.test_entries_group_by_page_and_cite_it`.
- `markup.list.min-rating-filter` **[OK]** — `GET …/annotations?min_rating=k` returns only annotations
  with `rating >= k` (annotations.py:212,232). Pinned: `test_annotations.py`.
- `markup.delete.soft-reversible` **[OK]** — deleting an annotation is soft and undoable via restore,
  round-tripping the same record (annotations.py:327,344). Pinned: `test_routes_annotations_actions.py`.
- `markup.promote-to-claim` **[OK]** — `POST …/annotations/{id}/promote-to-claim` yields a
  `KnowledgeClaim` while the annotation persists as a distinct surface mark (annotations.py:569).
  Pinned: `test_routes_annotations_actions.py`.
- `markup.promote-to-artifact` **[GAP]** (#579) an annotation (highlight, underline, margin
  note, pin-point) should also be promotable to a first-class, queryable, workflow-addressable
  `Artifact` — distinct from `markup.promote-to-claim` above, which promotes to a
  `KnowledgeClaim`, a different model entirely. Verified NOT built: `Artifact`
  (`models/__init__.py:672-687`) is scoped to AI/ML PROCESSING outputs (transcription, entity
  extraction, summaries, segmentation suggestions) — no annotation→`Artifact` conversion path
  exists anywhere in `annotations.py`. A highlight surviving a PDF re-ingest, becoming
  full-text-searchable, or being addressable by a workflow ("all highlights from this paper")
  are real capabilities `markup.promote-to-claim` doesn't provide (a claim is a KG proposition,
  not a workflow input). Not built.
- `markup.export.w3c-annotationpage` **[OK]** — `GET …/{doc}/annotations.jsonld` emits a valid W3C
  AnnotationPage; a span-within-region uses `refinedBy`/`refines` (documents.py:1295). Pinned:
  `tests/unit/api/test_routes_iiif.py` (`test_manifest_is_presentation3_and_points_at_annotation_page`
  and the anchor-export tests below it) — the test existed already, just uncited here.
- `markup.tags.coding` **[OK]** — `Annotation.tags: list[str]` exists (knowledge.py:1428) and marks
  carry tags; the design ruling's "code and query by tag" is built:
  `api/routes/document/annotations.py:~211` (`tag: str | None = Query(...)` param) and `:~230`
  (`if tag is not None: rows = [r for r in rows if tag in (r.tags or [])]`). Pinned:
  `TestAnnotationList.test_list_filter_by_tag`.
- `markup.review.library-wide` **[GAP]** (#4718) — the per-document `annotations` representation exists, but a
  LIBRARY-WIDE review surface (all checked/rated lines across sources) is still queued (a
  ruling from the design doc's numbered list, not a GitHub issue number).
- `markup.images-support-full-kind-set` **[OK]** — images get the SAME annotation tools PDF
  pages do: highlight (with underline/strikethrough sub-modes), note (inline text entry), line,
  bookmark, and the check-cycle rating — not a narrower subset.
  `ZoomableImagePreviewMac+Annotations.swift`'s `createAnnotation`/`requestAnnotation` handle all
  of `.highlight, .note, .line, .bookmark`; word-snap box-gating (`AnnotationWordSnap.gatedRects`)
  anchors highlight/underline/strikethrough/bookmark to recognized text the same way on images as
  on PDF pages, and refuses (with a stated reason) a drag over box-less canvas rather than saving
  an unanchored mark. The image-annotation request describing a narrower subset predates this
  build-out and reads as satisfied by it, not a remaining gap — flagged for verify-close in the
  triage rather than closed here.
  Pinned: `AnnotationBoxGateTests` (4 cases: word-snap anchoring, line-only geometry anchoring,
  box-less-canvas refusal, empty-geometry refusal), `AnnotationCheckCycleTests` (the rating half,
  already cited above).
- `markup.inspector-bottom-tool-placement` **[GAP]** (#2038) — annotation/markup/rotate/image-edit
  tools should live as CONTEXTUAL TOOLS at the inspector's bottom, scoped to the shown object,
  rather than scattered across surfaces. Verified: the annotation tools that exist today
  (`requestAnnotation`'s highlight/note/line/bookmark) are armed from the reader toolbar per that
  code's own doc comment (`ZoomableImagePreviewMac+Annotations.swift:9`), not an inspector-bottom
  contextual strip — #2038 asks for a placement this spec's existing behaviors don't cover (a
  UI-chrome question, not a data-model one).

- `markup.comment-tied-to-citation` — **[GAP]** (#2102) a comment/annotation should be tied to a
  CITATION specifically (a comment about a cited passage), not only to a bare source region.
  Most of #2102's own ask ("annotation mode: highlights/notes/comments on a page, region-
  anchored, stored hermeneutically") reads as already covered by behaviors above, not a
  remaining gap: the closed kind vocabulary already includes `comment`
  (`markup.kinds.closed-vocabulary`), region-anchoring is built
  (`markup.images-support-full-kind-set` above, plus the PDF-side equivalent), and
  `markup.promote-to-claim` is the "stored hermeneutically, alongside claims with provenance"
  mechanism #2102 asks for — those parts are verify-close candidates, not decided here. **This
  ONE sub-claim is confirmed NOT built, not just unverified:** `Annotation`
  (`models/knowledge.py:1352-1391`) anchors to a document/page/region/rendition — there is no
  `citation_id`-shaped field anywhere on it, so a comment cannot be linked to a specific
  citation today, only to the source region it happens to sit on. Not built.
- `markup.annotations-list-fills-its-column` — **[GAP]** (#1970, redirected from the legacy
  "UX - Library & Reading Surface" milestone while folding `library-view-modes.md`'s pass 2)
  the Source Annotations list should fill its column's full width/height (matching how the
  entities list renders in the same inspector), and single-click select should reliably work
  — reported broken. Not verified as built.
- `markup.paragraph-anchored-checkmark` — **[GAP]** (#2255, legacy milestone fold, 2026-09-19)
  a robust, cross-platform checkmark anchored to a whole PARAGRAPH (`anchor_kind=paragraph`,
  `paragraph_index`) rather than a character span, so the check gesture works on iOS/iPadOS,
  which cannot reliably produce a sub-range text selection the way macOS can. Verified at HEAD:
  `Annotation`'s anchoring fields have no `paragraph_index`/paragraph-shaped `anchor_kind` —
  every anchor today is a document/page/region/rendition span. Not built. The same issue's
  third ask — an LLM driving a highlight the OTHER direction, via a generic `FocusedRegion`
  driver — has a reusable component to build on now that didn't exist when this issue was
  filed: this session's own claim-source-reveal work (`kg.read.sentence-opens-source-highlighted`
  in `kg-readable-representation.md`) built exactly a user-driven region/passage highlighter;
  whether it generalizes to an LLM-initiated highlight (the opposite direction) is not
  investigated here.
- `markup.pencilkit-handwriting-to-ocr` — **[GAP]** (#2255) iPad Pencil ink converted to text via
  Apple Vision (local) or a remote VLM, with provenance recording which method produced it.
  Verified at HEAD: no `PencilKit`/`PKCanvasView` reference exists anywhere in
  `fichero/fichero/`. Not built, not started.
- `markup.face-to-entity-linking` — **[GAP]** (#2103) detecting faces in an image and tying each
  one to a KG entity (caption-derived, recognition-derived, or manually assigned), stored the
  same source-anchored way a text claim is (bbox/region + provenance: who/why/when/method).
  Verified at HEAD: no face-detection code (`VNDetectFace` or equivalent) exists anywhere in the
  server or the app. Not built, not started — this is a new capability, not an extension of an
  existing one.
- `markup.immersive-full-screen-reading` — **[PARTIAL]** (#3548) a distraction-free full-screen
  reading mode with chrome that auto-reveals/fades, plus the ability to mark a paragraph while
  reading. Verified at HEAD: `ImmersiveReaderView` (`Views/Reader/Page/Immersive/`) IS built —
  black-background full-screen presentation, auto-hiding controls, page-turn animation, prev/
  next navigation, translations and renditions all fold onto the existing `DocumentCanvas`
  rather than a parallel viewer, exactly as the issue asked ("do NOT rebuild the reader"). But
  the mark it adds is PAGE-scoped, not paragraph-scoped:
  `markCurrentPage(kind:label:)` (`ImmersiveReaderView+Interactions.swift`) calls
  `AnnotationStore.addNote(scope: .page(document.id), text: "", kind:)` — always an empty
  `text`, so there is no actual note-TAKING while immersive, only a page-level star/bookmark
  stamp. No test file exists for `ImmersiveReaderView` or its interactions. PARTIAL, not OK: the
  full-screen half is built; the paragraph-anchored mark and real note-taking the issue's own
  title asks for are not.

## Test matrix

| Behavior | Test | State |
|---|---|---|
| kinds.closed-vocabulary | test_annotation_list_schema.py, test_annotations.py | ✅ |
| rating.bounded-1-5 | test_annotations.py, test_routes_annotations_actions.py | ✅ |
| check.cycle | AnnotationCheckCycleTests (new, Swift) | ✅ |
| rating.renders-as-check | test_routes_views.py | ✅ |
| review.grouped-by-page | test_routes_views.py::TestAnnotationsRepresentation::test_entries_group_by_page_and_cite_it | ✅ |
| list.min-rating-filter | test_annotations.py | ✅ |
| delete.soft-reversible | test_routes_annotations_actions.py | ✅ |
| promote-to-claim | test_routes_annotations_actions.py | ✅ |
| export.w3c-annotationpage | test_routes_iiif.py (`test_manifest_is_presentation3_and_points_at_annotation_page`) | ✅ |
| tags.coding | test_annotations.py::TestAnnotationList::test_list_filter_by_tag | ✅ |
| review.library-wide | — | ❌ [GAP] |
| images-support-full-kind-set | AnnotationBoxGateTests, AnnotationCheckCycleTests | ✅ |
| inspector-bottom-tool-placement | — | ❌ [GAP] |
| promote-to-artifact | — | ❌ [GAP] |
| comment-tied-to-citation | — | ❌ [GAP] |
| annotations-list-fills-its-column | — | ❌ [GAP] |

## Open questions

1. Tag/coding query: the endpoint shape (`?tag=`, multiple tags AND/OR, a tag vocabulary?).
2. Library-wide review: is it a workspace (a `PaneList` of the annotations representation across the
   library) or a dedicated view? (Ties to panes-workspaces.)
3. Ratings 4–5: the model allows them but the check gesture only reaches 3 — are 4–5 reachable, and how?

## References

- `agent-work/design/reading-markup-coding-system.md` (rulings)
- Engine: `fichero-server/src/fichero_server/models/knowledge.py` (AnnotationKind/Annotation), `api/routes/document/annotations.py`,
  `api/routes/system/views.py` (annotations representation), `api/routes/document/documents.py` (jsonld export)
- Client: `fichero/fichero/Models/AnnotationStore.swift`, `Services/AnnotationService+*.swift`,
  `Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Annotations.swift` (check cycle)
