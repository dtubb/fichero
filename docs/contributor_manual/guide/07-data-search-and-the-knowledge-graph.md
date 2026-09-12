# 7. Data, Search, and the Knowledge Graph


### Library storage model

Each user library is a `.fichero` package — the unit of user data. Inside it, DuckDB stores structured records (documents, artifacts, workflows, activity) and LanceDB stores vector data (document embeddings, some KG embeddings). The `Database` class in the `db/` package is the central abstraction over both. Package-handling and allowlist rules live in the backend, which is why opening and saving libraries flows through backend-aware service layers. Never query the DuckDB or Lance files directly — everything goes through the db layer (and, from outside, through the API or the `fichero` CLI).

### How search works today

The main search route, `POST /api/search` (`api/routes/search/core.py`), is document-centric: it parses the query, runs semantic and full-text retrieval when there is free-text intent, fuses results for hybrid ranking, adds entity-artifact bridge behavior for scoped fields such as `people:` and `keywords:`, and enriches hits with related KG ids when possible.

The query parser (`search/query_parser.py`) supports quoted phrases, scoped fields (`people`, `places`, `organizations`, `dates`, `events`, `keywords`), minus-prefixed exclusions, and plain free-text. `/api/search` is *not* a “search everything” endpoint for claims and entities — dedicated KG search routes exist separately under the beta-tier `/api/kg/*` namespace.

### KG storage and entity writing

Knowledge-graph data is built around entities and claims. The central write path for catalogue-style extraction is `workflows/tools/_entity_writer.py`, which centralizes entity upsert, fuzzy matching and dedup heuristics, claim creation with claim-level dedup by a normalized subject-verb-object key plus cross-source corroboration folding (a repeated statement is not persisted once per mention, \#1803), source-support and provenance details, and the coordination between extractor output and the persistent models.

Set expectations correctly: KG writing is not “save whatever the model said.” Dedup, curation state, provenance, and source authority all matter, and the vector and non-vector KG surfaces are not all equally mature.
