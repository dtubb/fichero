> **ARCHIVED 2026-06-27** — historical point-in-time verification (2026-06-07).
> The search-everything vision is tracked in #1824/#1833; the concrete index
> data-debt (dual entity-vector tables, manual claim embeddings, no rebuild
> endpoint) is tracked in #2709. Kept for provenance; line-refs may be stale.

# Search Audit

Verified on `2026-06-07` against the live backend at `http://127.0.0.1:8765` using the Marshall library at `~/code/marshall_diaries/Marshall.fichero`. The live backend was treated as read-only throughout this audit. PyKEEN training was verified only on a disposable clone of the Marshall library.

## Executive Summary

- `POST /api/search` is working for document search. It searches document embeddings plus keyword matching over the same indexed document text, then adds a narrow entity-artifact bridge and KG metadata enrichment. Code: `fichero-engine/src/fichero/api/routes/search.py:470`, `fichero-engine/src/fichero/db.py:1059`.
- It does **not** currently implement "search everything". It does not search claim embeddings, does not search entity vectors as part of `/api/search`, and its scope syntax only understands extracted artifact scopes like `people:` / `places:` / `keywords:`. Code: `fichero-engine/src/fichero/search/query_parser.py:8`, `fichero-engine/src/fichero/search/query_parser.py:32`.
- Marshall currently has document embeddings (`/api/search/stats` returned `{"indexed_count":449,"table_exists":true}`), but live entity semantic search and live claim semantic search both return `503` because their expected tables are absent.
- Marshall's offline clone contains:
  - `454` pages with content
  - `449` document embeddings
  - `1557` entities
  - `80` claims
  - `301` artifacts, all of type `transcription`
  - LanceDB tables: `embeddings` (`449` rows) and `kg_entities` (`15` rows)
- PyKEEN training works offline on the clone (`228` triples, `87` entities, `31` relations`, trained=True`), but `predict_for_subject()` returned no results for the live `Asprilla` entity because that entity never appears in the training triples.
- Bounded fix landed: entity semantic search now recognizes the existing `kg_entities` vector table as a valid source instead of hard-failing unless `kg_entity_embeddings` exists. Code: `fichero-engine/src/fichero/api/routes/kg_entity_curation.py`.

## 1. What `/api/search` Actually Does

### Route flow

`POST /api/search` is implemented in `fichero-engine/src/fichero/api/routes/search.py:470`.

The route:

1. Parses the query into free text, quoted phrases, exclusions, and entity-artifact scopes via `parse_query(...)`. Code: `fichero-engine/src/fichero/api/routes/search.py:544`, `fichero-engine/src/fichero/search/query_parser.py:78`.
2. Calls `db.search(...)` for semantic / fulltext / hybrid retrieval unless the query is a pure artifact-scope query such as `people:Asprilla`. Code: `fichero-engine/src/fichero/api/routes/search.py:551`, `fichero-engine/src/fichero/api/routes/search.py:563`.
3. Adds an entity-artifact bridge by scanning the `artifacts` table for `people`, `places`, `organizations`, `dates`, `events`, and `keywords`. Code: `fichero-engine/src/fichero/api/routes/search.py:329`, `fichero-engine/src/fichero/api/routes/search.py:590`.
4. Enriches matched document hits with `kg_claim_ids` and `kg_entity_ids` if claim/entity text matches the query. This is metadata enrichment on document hits, not claim/entity retrieval. Code: `fichero-engine/src/fichero/api/routes/search.py:648`, `fichero-engine/src/fichero/db.py:898`.

### What `db.search(...)` searches

`db.search(...)` is document-centric. Code: `fichero-engine/src/fichero/db.py:1059`.

- Semantic search:
  - Searches LanceDB table `embeddings`
  - Uses document/page vectors only
  - Skips parent file docs when indexed page children exist
  - Code: `fichero-engine/src/fichero/db.py:1110`
- Full-text search:
  - Also reads from LanceDB table `embeddings`
  - Performs folded substring/BM25-like ranking over the stored `text` field from document embeddings
  - Code: `fichero-engine/src/fichero/db.py:1161`
- Hybrid:
  - Fuses semantic and full-text by reciprocal-rank fusion
  - Code: `fichero-engine/src/fichero/db.py:1219`

This means `/api/search` is fundamentally "search document text". The entity bridge is bolted on after retrieval and only works if entity-like information exists in `artifacts` rows of the supported types.

### Scope support today

The query parser only recognizes these scoped fields:

- `people`
- `places`
- `organizations`
- `dates`
- `events`
- `keywords`

Code: `fichero-engine/src/fichero/search/query_parser.py:8`, `fichero-engine/src/fichero/search/query_parser.py:32`.

There is no support for `claims:` or `entities:` or an explicit include/scope array in the request model. `SearchRequest` only exposes generic search controls plus `filters`. Code: `fichero-engine/src/fichero/api/routes/search.py:396`.

## 2. Live Verification Against `:8765`

### Search works for document text

Live `search/stats` on Marshall returned:

```json
{"indexed_count":449,"table_exists":true}
```

Live CLI query:

```bash
PYTHONPATH=../fichero-engine/src ../fichero/.venv/bin/python -m fichero \
  --library ~/code/marshall_diaries/Marshall.fichero \
  --json search Marshall --limit 5
```

Returned `5` page results, for example:

- `NCM_Diary_19240101-19241231_IMG_001`
- `NCM_Diary_1925IMG_001`
- `NCM_Diary_1923IMG_001`

Those are page hits with transcript excerpts and no KG ids attached.

Live query:

```bash
... --json search Asprilla --limit 5
```

also returned page hits from page text, for example `NCM_Diary_1925IMG_054_part_2`, but again with empty `kg_claim_ids` and `kg_entity_ids`.

Conclusion: `/api/search` is operational for document/page text retrieval.

### KG search is separate and substring-based

Live CLI query:

```bash
PYTHONPATH=../fichero-engine/src ../fichero/.venv/bin/python -m fichero \
  --library ~/code/marshall_diaries/Marshall.fichero \
  --json kg search Asprilla --limit 10
```

returned:

- `1` entity hit: `Asprilla`
- `5` annotation hits
- `0` claim hits
- `0` note hits

That behavior matches `GET /api/kg/search`, which is a separate mixed-type KG substring search over entities, claims, notes, and annotations. Code: `fichero-engine/src/fichero/api/routes/kg_search.py:49`.

This is not wired into `/api/search`.

### Artifact-scope search is not enough for Marshall

Live request:

```json
{"query":"people:Asprilla","limit":5,"min_score":0.0}
```

returned zero results.

That is expected from the current implementation because the scope bridge only scans `people`/`places`/etc artifact rows, and Marshall currently has no such artifacts. The offline clone shows all `301` artifacts are `transcription`.

### Claim scope does not exist

Live request:

```json
{"query":"claim:Asprilla","limit":5,"min_score":0.0}
```

returned ordinary document hits, not claim hits. The parser does not recognize `claim:` as a scope, so it falls through as plain text. Code: `fichero-engine/src/fichero/search/query_parser.py:32`.

## 3. What Gets Embedded, and When

### Document embeddings

Documents/pages are auto-embedded on ingest when text exists:

- `ingest_file(..., auto_embed=True)` defaults to on. Code: `fichero-engine/src/fichero/ingest.py:194`.
- `ingest_folder(..., auto_embed=True)` defaults to on. Code: `fichero-engine/src/fichero/ingest.py:804`.
- `db.save(..., auto_embed=...)` supports embedding on save. Code: `fichero-engine/src/fichero/db.py:447`.
- Manual rebuild exists at `POST /api/search/reindex`. Code: `fichero-engine/src/fichero/api/routes/search.py:776`.
- Manual single-doc embedding exists at `POST /api/search/embed/{doc_id}`. Code: `fichero-engine/src/fichero/api/routes/search.py:801`.

The embedding model is FastEmbed-backed `intfloat/multilingual-e5-large`, normalized before storage. Code: `fichero-engine/src/fichero/db_embeddings.py:19`, `fichero-engine/src/fichero/db_embeddings.py:159`.

Marshall clone evidence:

- `454` pages have non-empty content
- `449` document embeddings exist

The gap is plausibly explained by `MIN_CONTENT_LENGTH = 10` in `db.embed(...)`. Several shortest Marshall pages have only values like `DIARY` or `MEMORANDA` and are under or near that threshold. Code: `fichero-engine/src/fichero/db.py:63`, `fichero-engine/src/fichero/db.py:824`.

### Entity embeddings

There are two different entity-vector code paths:

1. Batch embed route:
   - `POST /api/kg/entity-curation/semantic/embed`
   - Writes LanceDB table `kg_entity_embeddings`
   - Code: `fichero-engine/src/fichero/api/routes/kg_entity_curation.py:31`, `fichero-engine/src/fichero/api/routes/kg_entity_curation.py:309`
2. Automatic entity vector indexing:
   - `entity_vectors.index_entity(...)`
   - Writes LanceDB table `kg_entities`
   - Called from entity creation/update/rebuild paths
   - Code: `fichero-engine/src/fichero/kg/entity_vectors.py:51`, `fichero-engine/src/fichero/kg/rebuild.py:67`, `fichero-engine/src/fichero/workflows/tools/_entity_writer.py:1072`, `fichero-engine/src/fichero/api/routes/entities.py:731`

Marshall clone evidence:

- `1557` entity rows exist in DuckDB
- LanceDB table `kg_entities` exists with only `15` rows
- LanceDB table `kg_entity_embeddings` does not exist on the live engine

Live evidence before the fix:

```http
GET /api/kg/entity-curation/semantic?q=Asprilla&limit=5
503 Entity embeddings not yet indexed. POST /kg/entity-curation/semantic/embed first.
```

Interpretation:

- Entity vectors are **not** comprehensively embedded in Marshall.
- Some entity vectors do exist (`kg_entities`, `15` rows), likely from entity upsert/rebuild paths.
- The live semantic endpoint could not see them because it only checked for `kg_entity_embeddings`.

### Claim embeddings

Claim embeddings are entirely manual today:

- `POST /api/kg/claim-search/embed` writes `kg_claim_embeddings`
- `GET /api/kg/claim-search` reads `kg_claim_embeddings`
- Code: `fichero-engine/src/fichero/api/routes/kg_claim_search.py:27`, `fichero-engine/src/fichero/api/routes/kg_claim_search.py:56`, `fichero-engine/src/fichero/api/routes/kg_claim_search.py:79`

Live evidence on Marshall:

```http
GET /api/kg/claim-search?q=Asprilla&limit=5
503 Claim embeddings not yet indexed. POST /kg/claim-search/embed first.
```

Marshall clone evidence:

- `80` claim rows exist
- No `kg_claim_embeddings` table exists

So claims are present, but not embedded.

## 4. PyKEEN Status

### Live API status

Live read-only endpoints on Marshall returned:

- `GET /api/kg/pykeen/training-jobs` → `{"items":[],"count":0}`
- `GET /api/kg/pykeen/stored` → `{"items":[],"count":0}`
- `GET /api/kg/pykeen/predict/<Asprilla-id>?top_k=5` → `{"items":[],"count":0}`

So on the running engine, PyKEEN is effectively dormant for this library.

### Code paths

The active `/api/kg/pykeen/*` routes use `fichero.kg.pykeen_predictor`, not `fichero.pykeen_inference`. Code: `fichero-engine/src/fichero/api/routes/kg_pykeen.py:47`, `fichero-engine/src/fichero/api/routes/kg_pykeen.py:79`.

`fichero.pykeen_inference` still exists and supports in-memory training job bookkeeping, but it is not what the current train/predict routes call. Code: `fichero-engine/src/fichero/pykeen_inference.py:121`.

### Offline clone verification

On a disposable clone of Marshall, this succeeded:

- `train_model(..., model_name="TransE", embedding_dim=32, num_epochs=5)`
- Output: `trained=True`, `triples=228`, `entities=87`, `relations=31`

Code for training/predict:

- triple gathering: `fichero-engine/src/fichero/kg/pykeen_predictor.py:63`
- train: `fichero-engine/src/fichero/kg/pykeen_predictor.py:86`
- predict: `fichero-engine/src/fichero/kg/pykeen_predictor.py:174`

However, `predict_for_subject()` returned zero predictions for the live `Asprilla` entity id. The follow-up probe showed:

- `Asprilla` exists as an entity row
- `Asprilla` does **not** appear in the raw training triples
- therefore `Asprilla` is absent from the trained triples factory vocabulary

That explains the empty prediction response: the predictor exits early when the subject id is not in the trained entity vocabulary.

Conclusion:

- PyKEEN can train technically.
- PyKEEN predict is not broadly useful on Marshall in its current data state.
- Whether an entity can receive predictions depends on whether it actually participates in `_gather_triples(...)`.

## 5. Coverage Gap: Why This Is Not Yet "Search Everything"

Today there are three separate search surfaces:

1. `/api/search`
   - document/page search
   - optional artifact bridge for `people`/`places`/etc
2. `/api/kg/search`
   - substring search across entities/claims/notes/annotations
3. `/api/kg/entity-curation/semantic` and `/api/kg/claim-search`
   - dedicated semantic routes for entities and claims

None of these is the requested "search everything, but choose what to search" surface.

To reach that target cleanly, the backend needs:

1. A first-class scope/include contract on `SearchRequest`.
   - Example: `include: ["content", "entities", "claims"]`
   - Optional narrower selectors like `entity_types`
2. A unified `/api/search` merger that can combine:
   - document hits from `db.search(...)`
   - entity semantic hits and/or KG substring hits
   - claim semantic hits and/or KG substring hits
3. A result model that can represent mixed hit types.
   - The current `SearchResult` is document-shaped.
   - `KGSearchHit` is closer, but separate and substring-only.
4. Reliable background indexing rules.
   - document embeddings already auto-happen on ingest when text exists
   - entity embeddings need one canonical table/path
   - claim embeddings need an automatic trigger or an explicit rebuild step
5. UI-visible scope wiring.
   - The backend needs a stable request contract before Swift can expose a scope selector without hard-coding query syntax tricks.

The main architectural problem is not ranking. It is that the indexed/searchable stores are fragmented by type and lifecycle.

## 6. Bounded Fix Landed

I landed one safe backend fix:

- `GET /api/kg/entity-curation/semantic` now falls back to the existing `kg_entities` table when `kg_entity_embeddings` is absent.
- Regression test added to lock that behavior.

Files:

- `fichero-engine/src/fichero/api/routes/kg_entity_curation.py`
- `fichero-engine/tests/unit/test_embed_endpoints_nonblocking.py`

Why this fix and not more:

- It is low-risk and matches existing library state: Marshall already had `kg_entities`.
- It avoids a false `503` for libraries that already contain entity vectors via upsert/rebuild.
- It does **not** attempt a risky redesign of mixed-result search or claim auto-embedding.

What it does **not** solve:

- Marshall still has only `15` entity vectors for `1557` entities.
- Claim embeddings are still absent and still manual.
- `/api/search` still does not unify content + entities + claims.

## 7. Recommended Next Steps

1. Canonicalize entity vector storage.
   - Pick one entity vector table name and use it everywhere.
   - Right now `kg_entities` and `kg_entity_embeddings` both exist in code.
2. Add a claim/entity rebuild endpoint or extend KG rebuild.
   - Document reindex exists.
   - Entity/claim semantic indexes need the same operational story.
3. Extend `SearchRequest` with `include`/`scope`.
   - Default to `["content", "entities", "claims"]`
   - Keep it explicit; do not overload query syntax for core UI behavior.
4. Introduce a mixed-hit response model for `/api/search`.
   - Without that, "search everything" will keep collapsing non-document hits into document-only shapes.
5. Only after the above, wire the Swift scope selector.

