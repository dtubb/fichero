# Drag and drop — engine audit (#3702)

## Existing actions

| Drop operation | Existing endpoint/action | What it does | Fit |
| --- | --- | --- | --- |
| Entity → entity | `POST /api/kg/entity-curation/merge` (`entity.merge` audited action) | Absorbs selected entity IDs into one survivor, repoints claims, writes `EntityMergeAudit`, and supports the existing unmerge path. | Direct fit for a user-confirmed merge drop. |
| Library item → folder/item in the **same** library | `PUT /api/documents/{doc_id}/move?parent_id=` (`document.move` audited action) | Reparents one document-tree node after validating the new parent. | Direct fit only for same-library hierarchy drops. |
| Entity → page/region | `PATCH /api/claims/{claim_id}` can replace a pre-existing claim's `entity_ids`, `source_document_id`, and `source_bbox`; `POST /api/claims` can create a claim with those fields. | Changes or creates a proposition, not a standalone mention. Both require claim content/identity. | Not a direct drag-drop fit. |
| Entity biography data | `GET /api/entities/{entity_id}/biography` | Returns structured entity, claims, source-document links, and co-occurrences as JSON. | Usable as input to a client-generated file, but not a downloadable backend file. |
| Whole-library entity text/Markdown | `GET /api/entities/digest?format=markdown\|text` | Renders the visible entity graph for a library as a text response. | Not per entity and not an attachment/file export. |
| LLM biography generation | `POST /api/kg/entities/{entity_id}/bio` | Generates and persists LLM prose in the entity description with provenance/audit path. | Generation only; does not export a file. |

## Gaps

1. **Entity → page/bbox mention:** no endpoint accepts `{entity_id, document_id, bbox?}` and records an explicit manual mention. Reusing claim creation would fabricate a claim or require the UI to choose/edit one first.
2. **Item → another library move/copy:** `document.move` is only a parent change in the current library. Ingest `copy`/`move` modes operate on filesystem paths, not existing document-tree items and their linked annotations/notes/entities/claims. Library-registry merge code transfers whole-library material; it is not a per-item user action.
3. **Drag entity biography/summary to desktop:** no per-entity attachment/download route exists. The structured biography JSON and whole-library digest are related read endpoints, but neither represents an exported entity file with a filename/content-disposition.
4. **Citations:** no generic citation drop action was found that adds a citation/mention to a page region, transfers one citation-bearing item cross-library, or exports one citation/entity summary. Citation export routes cover citation collections, not these target-specific drops.

## Minimal new endpoints

Only add these when the Swift interactions need the engine to own the mutation/file:

| Need | Minimal endpoint | Notes |
| --- | --- | --- |
| Explicit manual mention | `POST /api/entities/{entity_id}/mentions` body `{document_id, bbox?, page_index?, note?}` | Persist an auditable, undoable mention anchor without inventing a `KnowledgeClaim`; validate document and normalized bbox. |
| Cross-library transfer | `POST /api/library-items/{item_id}/transfer` body `{target_library_path, mode: "copy"\|"move", target_parent_id?}` | Must copy the item subtree and remap linked annotations/notes/entities/claims atomically or report a per-item failure. Do not overload same-library `document.move`. |
| Entity file export | `GET /api/entities/{entity_id}/export?format=markdown\|text\|json` | Build from the existing `assemble_entity_biography`; return an attachment with a deterministic filename. The Swift client can otherwise write the already-available JSON itself. |

Entity merge and same-library reparent require no new engine endpoint. Citation-specific additions should wait until the Swift drop target specifies whether a drop means attach an existing citation, create a citation record, or merely navigate to it.
