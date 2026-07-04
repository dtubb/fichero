# Silent-Fallback Audit Round 2

Scope: second-pass audit for the #2430 class of bugs on engine modules not covered in round 1.

- `fichero-engine/src/fichero/api/routes/documents.py:393-416`  
  Silent behavior: `_normalize_curated_items()` drops malformed curated workspace items with bare `continue` when an item is not a dict or is missing `id` / `target_type` / `target_id`. The caller gets a shorter list with no indication that saved workspace state was discarded.  
  Why it's wrong: this turns corrupt or partially-written curated state into an apparently valid empty/partial workspace, which is the same "data silently vanished" shape as #2430.  
  Fix: log loudly with the workspace document id and the rejected item payload shape, or raise on malformed persisted items so the caller surfaces workspace corruption instead of normalizing it away.

- `fichero-engine/src/fichero/api/routes/documents.py:580-609`  
  Silent behavior: `_points_from_metadata()` skips malformed `geo_points` entries with bare `continue`, and `float(lat)` / `float(lon)` coercion has no per-item error reporting path. A document with broken geo metadata quietly loses map points.  
  Why it's wrong: the UI sees "no geo data" or partial geo data instead of "stored geo metadata is malformed". That's silent data loss at read time.  
  Fix: wrap per-item coercion, log the document id / offending item, and either skip-loudly or raise a 422-style error when a write path stored invalid geo metadata.

- `fichero-engine/src/fichero/api/routes/documents.py:1288-1294`  
  Silent behavior: `related_documents()` catches any `knowledge_claim_entity_id_values()` failure, logs a warning, and returns `items=[]` / `count=0`.  
  Why it's wrong: a broken KG lookup is surfaced as "this document has no related documents", which is fabricated empty state.  
  Fix: raise an HTTP error (5xx or typed backend error) or return an explicit degraded-state payload; do not substitute a successful empty result for a failed query.

- `fichero-engine/src/fichero/api/routes/entities.py:805-809`  
  Silent behavior: `top_entities()` catches any failure from `knowledge_claim_entity_id_values()`, logs, and returns an empty entity cloud.  
  Why it's wrong: the browser cannot distinguish "no entities in this library" from "entity aggregation failed".  
  Fix: fail the endpoint loudly or add an explicit degraded/error field; do not return `count=0` on backend failure.

- `fichero-engine/src/fichero/api/routes/entities.py:818-821`  
  Silent behavior: `top_entities()` silently discards malformed `entity_ids` JSON rows with `except (TypeError, ValueError): continue`.  
  Why it's wrong: damaged claim rows disappear from the aggregate without any trace, biasing counts and hiding bad stored data.  
  Fix: log the claim/entity-id payload that failed to decode, or surface a data-integrity error instead of silently undercounting.

- `fichero-engine/src/fichero/api/routes/entities.py:871-875`  
  Silent behavior: `entity_claim_counts()` catches any lookup failure and returns `{}`.  
  Why it's wrong: the client sees "every badge count is zero / absent" rather than "count aggregation failed". This fabricates success.  
  Fix: raise/log loudly and surface an explicit error; do not return an empty counts map on query failure.

- `fichero-engine/src/fichero/api/routes/entities.py:880-883`  
  Silent behavior: `entity_claim_counts()` silently skips malformed serialized `entity_ids` values.  
  Why it's wrong: count totals become partial without any indication that persisted data is damaged.  
  Fix: log the bad payload and claim id if available, or fail the aggregate so the corruption is visible.

- `fichero-engine/src/fichero/api/routes/entities.py:1134-1138`  
  Silent behavior: `get_entity_documents()` catches any `entity_document_link_rows()` error and returns an empty document list.  
  Why it's wrong: "this entity appears in zero documents" is materially different from "document-link aggregation failed".  
  Fix: fail the endpoint loudly or return an explicit degraded-state marker instead of `items=[]`.

- `fichero-engine/src/fichero/api/routes/entities.py:1174-1178`  
  Silent behavior: `get_entity_co_occurrence()` catches any co-occurrence lookup failure and returns `items=[]` / `count=0`.  
  Why it's wrong: related-entity graph failures are flattened into "no related entities", hiding backend breakage.  
  Fix: surface the query failure as an error response or an explicit degraded payload.

- `fichero-engine/src/fichero/api/routes/entities.py:1187-1190`  
  Silent behavior: `get_entity_co_occurrence()` silently drops malformed `entity_ids` rows during JSON decode.  
  Why it's wrong: co-occurrence counts become partial with no signal that source data is corrupt.  
  Fix: log-loudly the bad payload (and source claim if available), or fail the aggregate.

- `fichero-engine/src/fichero/api/routes/entities.py:1261-1265`  
  Silent behavior: `entity_drill_down()` turns excerpt lookup failures into `claim_excerpts=[]`.  
  Why it's wrong: the endpoint now claims the entity has no representative excerpts when the excerpt query actually failed.  
  Fix: fail the drill-down request or add an explicit degraded field for the excerpt rail.

- `fichero-engine/src/fichero/api/routes/entities.py:1359-1363`  
  Silent behavior: `assemble_entity_biography()` converts biography document lookup failures into `doc_rows=[]`.  
  Why it's wrong: the biography bundle silently loses the source-document rail while still looking structurally valid.  
  Fix: raise/log loudly and mark the biography assembly partial instead of fabricating an empty document section.

- `fichero-engine/src/fichero/api/routes/entities.py:1381-1385`  
  Silent behavior: `assemble_entity_biography()` converts co-occurrence lookup failures into `raw_entity_id_values=[]`.  
  Why it's wrong: a backend failure becomes "no co-occurring entities", which is false data.  
  Fix: fail the assembly or return an explicit partial/degraded result indicator.

- `fichero-engine/src/fichero/api/routes/entities.py:1391-1394`  
  Silent behavior: `assemble_entity_biography()` silently drops malformed `entity_ids` rows while building co-occurrence counts.  
  Why it's wrong: the biography's related-entity rail undercounts without exposing corruption.  
  Fix: log or raise on malformed rows rather than `continue`.

- `fichero-engine/src/fichero/api/routes/claims.py:588-595`  
  Silent behavior: `assign_time_period_impl()` silently skips claims in the requested page range when `source_page_label` cannot be parsed by `_page_number()`.  
  Why it's wrong: a user asking to bulk-date a page range gets fewer claims updated than expected, with no indication that some source labels were unparsable.  
  Fix: count and surface `skipped_unparseable_page_label`, or fail when page-range filtering encounters malformed labels.

- `fichero-engine/src/fichero/importers/ingest.py:413-425`  
  Silent behavior: `_split_pdf_pages()` returns `[]` when Kreuzberg is unavailable or page extraction throws, which collapses "splitter failed" into the same value as "no page rows extracted".  
  Why it's wrong: downstream callers can silently fall back to unsplit import behavior instead of surfacing that page extraction broke.  
  Fix: return a typed failure object / raise, or at minimum distinguish dependency-missing / extraction-failed from a genuine empty result.

- `fichero-engine/src/fichero/importers/ingest.py:1000-1010`  
  Silent behavior: pre-indexing existing checksums is wrapped in a broad `except`, only debug-logged, and the import continues without dedupe acceleration.  
  Why it's wrong: checksum-skip logic quietly degrades off; duplicate imports become possible without the operator knowing skip protection failed.  
  Fix: warn loudly with the library path and disable the import unless the caller explicitly accepts degraded dedupe behavior.

- `fichero-engine/src/fichero/importers/iiif_import.py:451-454`  
  Silent behavior: `_import_annotations()` increments `skipped` and continues when a canvas external id cannot be mapped to a document id.  
  Why it's wrong: IIIF annotations are silently dropped from the import result; the caller only sees an aggregate skipped count with no per-annotation reason or failing id.  
  Fix: record structured skip reasons keyed by the missing `canvas_external_id`, or fail the import when declared annotation targets are absent.

- `fichero-engine/src/fichero/llm_models.py:44-48`  
  Silent behavior: `get_model_info()` swallows any LiteLLM exception and returns `None`.  
  Why it's wrong: callers cannot distinguish "model not present in registry" from "LiteLLM lookup failed", so provider/catalog failures get normalized into missing metadata.  
  Fix: log loudly with the model id and exception, and either raise or return a typed error/result object that preserves failure vs absence.

- `fichero-engine/src/fichero/llm_models.py:88-96`  
  Silent behavior: `estimate_cost()` swallows any LiteLLM pricing error and returns `0.0`.  
  Why it's wrong: this fabricates a valid zero-dollar cost for unknown/failed models, which is exactly the "fake successful value" variant of the silent-fallback bug class.  
  Fix: raise/log loudly and return `None` or a typed "cost unavailable" result; never substitute `0.0` for pricing failure.

- `fichero-engine/src/fichero/llm_models.py:63-68`  
  Silent behavior: `get_model_cost()` defaults missing token-price fields to `0` when LiteLLM has a partial model-cost record.  
  Why it's wrong: partial registry data becomes a fabricated free model instead of an explicit incomplete-pricing error.  
  Fix: treat missing `input_cost_per_token` / `output_cost_per_token` as unavailable and surface that explicitly instead of defaulting to zero.
