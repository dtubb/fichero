# Edit states as renditions — what landed, and the server half that did not

Daniel, 2026-09-03: "these should be a rendition so we can easily go back and
forth" (original ↔ edited, on the up/down swipe that already flips renditions).

## What landed (client, commit ce831ebd3)

`RenditionService.load` appends the document's edit STATES to the flip
sequence when it has a saved `ImageEditChain`:

- ids are `edit:<role>:<documentId>` — document-scoped because the content
  cache is keyed by rendition id alone;
- `contentData` branches on that id and renders through
  `GET /api/images/{id}/preview?apply_edits=true|false` instead of the
  rendition-bytes route;
- the synthetic `original` is added only when the engine staged no renditions
  (index 0 of a real list is already the untouched pixels);
- `hasOwnFrame` is computed from the chain: `crop`/`rotate`/`straighten`
  re-frame the render, an `enhance` does not, so node-frame OCR overlays keep
  drawing where they are still true;
- `preferredRenditionIndex` ranks `edited` first, so a page with saved edits
  opens on them; the sticky role still wins.

Cost: one `GET /edits` per document per session, inside the already-cached
`load`.

## What did NOT land: a materialised `edited` rendition row

The honest end state is server-side, for the standing reason that clients
render server state rather than each deciding it — the CLI, MCP and any web
client should see the same flip sequence.

Shape:

1. On every chain write (`set_operations_impl`, `_append_operation`,
   `clear_operations_impl`), render the chain for the affected page and write
   the bytes under `<library>/storage/renditions/<doc>/edited.<ext>` — NOT
   `$TMPDIR`, which is swept (`persist_workflow_renditions` documents the same
   rule). `_write_derived_image` currently writes to the temp dir and its
   `derived_path` is popped before save, so it is dead today; this replaces it.
2. Upsert ONE `Rendition` row per document with `role="edited"`,
   `is_materialized=True`, `transform` set when the chain re-frames, and
   pixel_width/height from the render. Clearing the chain deletes the row.
3. `order_renditions` places `edited` in the sequence; `RENDITION_ROLE_PREFERENCE`
   gains the role so every client agrees what "next" means.
4. The client then drops `RenditionService+EditStates` entirely — no sentinel
   ids, no preview-endpoint branch. That deletion is the acceptance test.

Why it was deferred on 2026-09-03: `api/routes/ingest/image_editing.py` was
owned by the concurrent PDF-source-resolution lane that night, and every write
path above lives in it. It is a one-file change once that lane lands.

Open question for Daniel: multi-page documents. A chain is per document with a
`page` on each op, so a materialised `edited` row is per (document, page) —
the preview flip is per page already, so the row should carry the page the
same way the staged renditions do.
