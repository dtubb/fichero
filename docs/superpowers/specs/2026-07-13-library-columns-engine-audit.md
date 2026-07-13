# Library columns — engine audit (#3696)

## Existing endpoints

| Need | Endpoint | What it returns | Batch suitability |
| --- | --- | --- | --- |
| Page of library items | `GET /api/documents?parent_id=&limit=&offset=` | `DocumentListResponse`: each node's id, hierarchy fields, and its own `bbox` (for a derived region/page). | Yes, for item rows and own-node bbox presence; it does not include related metadata or counts. |
| Entity mentions | `GET /api/entities?document_id=<id>` | `EntityListResponse`; entities inferred from claims for that document and descendants, plus entity `source_document_ids`. | One `document_id` only. A page requires one request per item. |
| Annotations | `GET /api/annotations?document_id=<id>` | Full annotation rows, including document/page/folder scope, `bbox`, ink/OCR provenance, and linked entity/note ids. | One document filter only. There is no repeated `document_id` or `document_ids` filter. |
| Notes | `GET /api/notes?linked_document_id=<id>` | Full note rows linked directly or through page/folder scope. | One linked document filter only. |
| Claims / claim bboxes | `GET /api/claims?source_document_id=<id>&include_descendants=true` | Claim rows, including `entity_ids` and `source_bbox`. | One source document only; also scans/filter rows in Python today. |
| Entity drill-down | `GET /api/entities/{entity_id}/documents` | Documents for one entity, with claim count and excerpt. | Reverse, one-entity lookup; not a library-item batch. |
| Search | `GET /api/kg/search?q=` | Text-query hits across entities, claims, notes, annotations. | Not an item-id lookup and does not group results by item. |

## Gaps

There is no one-call accessor for a supplied page of document/item IDs that groups entity mentions, annotations, notes, and bbox-derived counts by item. The Swift column browser can batch-load the `Document` rows, but populating its four proposed columns from current routes is N+1 for entities, annotations, and notes (and another N calls if claim `source_bbox` counts are wanted).

The existing data is already library-local and linkable: entities use claim `source_document_id` / `entity_ids` and `source_document_ids`; annotations carry `document_id`, `page_id`, and `folder_id`; notes carry direct and page/folder document links. Node-region bboxes are on `Document.bbox`; annotation bboxes are `Annotation.bbox`; provenance/claim bboxes are `KnowledgeClaim.source_bbox`. These are distinct counts and should not be collapsed ambiguously.

## Proposed batch endpoint

Add a read-only endpoint only if the UI needs these columns on a page at once:

`POST /api/library-items/columns`

```json
{
  "item_ids": ["doc-1", "doc-2"],
  "include_descendants": true
}
```

Return one row for every requested id (including zero-count rows), keyed by `item_id`:

```json
{
  "items": [
    {
      "item_id": "doc-1",
      "entities": [{"id": "entity-1", "name": "Rosario", "type": "person"}],
      "annotations": [{"id": "annotation-1", "kind": "highlight", "bbox": [0.1, 0.2, 0.3, 0.1]}],
      "notes": [{"id": "note-1", "title": "Context"}],
      "bbox_counts": {"node_regions": 2, "annotations": 1, "claims": 3}
    }
  ]
}
```

Implement it as set-based `IN` queries plus one in-memory grouping pass, preserving requested-item order. `include_descendants` should use the same descendant semantics as the current entity/claim routes so groups/stacks and split-page trees roll up consistently. It must not call the four existing per-item HTTP endpoints internally.
