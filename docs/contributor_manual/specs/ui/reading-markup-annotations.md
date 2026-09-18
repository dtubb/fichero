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
