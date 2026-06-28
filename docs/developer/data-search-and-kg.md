# Data Layer, Search, and Knowledge Graph Storage

## Table of Contents

- [Library Storage Model](#library-storage-model)
- [DuckDB and LanceDB](#duckdb-and-lancedb)
- [How Search Works Today](#how-search-works-today)
- [Knowledge Graph Storage and Entity Writing](#knowledge-graph-storage-and-entity-writing)

## Library Storage Model

Each user library is a `.fichero` package. The engine treats that package as the unit of user data.

Inside a library package:

- DuckDB stores structured records such as documents, artifacts, workflows, and activity data
- LanceDB stores vector-oriented data such as document embeddings and some KG embeddings

The allowlist and package-handling rules live in the backend, not just the frontend. That is why opening and saving libraries flows through backend-aware service layers.

## DuckDB and LanceDB

`db.py` is the central abstraction over both stores.

Current responsibility split:

- DuckDB: structured relational data
- LanceDB: vector tables and hybrid search support

The code and docs both describe Fichero as a dual-database design, and that is accurate in the current implementation.

## How Search Works Today

The current main search route is document-centric.

`POST /api/search`:

- parses the user query
- runs semantic and full-text document retrieval when there is free-text intent
- fuses retrieval results for hybrid ranking
- adds entity-artifact bridge behavior for scoped fields such as `people:` and `keywords:`
- enriches document hits with related KG ids when possible

The query parser in `fichero/search/query_parser.py` currently supports:

- quoted phrases
- scoped fields for `people`, `places`, `organizations`, `dates`, `events`, and `keywords`
- minus-prefixed exclusions
- plain free-text

It does not currently make `/api/search` a true "search everything" endpoint for claims and entities. Dedicated KG search routes exist separately under the dev-tier `/api/kg/*` namespace.

## Knowledge Graph Storage and Entity Writing

Knowledge-graph data is built around entities and claims.

The central write path for catalogue-style extraction is `workflows/tools/_entity_writer.py`. That helper centralizes:

- entity upsert logic
- fuzzy matching and dedup heuristics
- claim creation
- source-support and provenance details
- coordination between extractor output and persistent KG models

That module is load-bearing because it is the bridge from workflow extraction outputs into persistent `KnowledgeEntity` and `KnowledgeClaim` records.

This is also where contributor expectations should be set correctly:

- KG writing is not just "save whatever the model said"
- dedup, curation state, provenance, and source authority all matter
- there are separate vector and non-vector KG surfaces, and they are not all equally mature
