# Knowledge graph — how it is stored and how it is asked — Design Spec (#5261, #4975)

> Milestone: kg-store-and-query
> Manual: TBD — no user-facing section of its own; the manual's "Names and statements" section
> (see `kg-entities-and-statements.md`) must say that lists, counts and the neighbourhood of a
> name answer at once in a project of tens of thousands of pages, and what "rebuild the
> knowledge index" does when a person is told to run it.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-11-20), written from a review of the
> store and its queries with measurements on scratch libraries (section "Measured"). This spec
> owns HOW names, statements, their provenance and confidence are kept in DuckDB and how the
> routes, the CLI and the MCP tools read them at scale. It adds no record: `KnowledgeEntity` and
> `KnowledgeClaim` stay the two records (`kg-entities-and-statements.md`, section G); what is
> added is one DERIVED, rebuildable link table and the rule that a filter runs in the database.
> What the graph views show is in `../explore/networks.md`; the tables in `kg-tables.md`.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built · **[BROKEN]** code contradicts the line.

## Intent (the design)

A project of 5,000 pages holds about 50,000 statements and 12,000 names; one of 50,000 pages
about 500,000 statements and 125,000 names. A researcher clicking a name, a table asking for its
next page, or an agent calling `fichero_kg_neighborhood` should get an answer in well under a
second at either size, on a 16 GB laptop, with the engine's memory staying flat.

Today every one of those questions loads the WHOLE statements table into Python objects and
filters there. It is correct, and it takes 3 to 4 seconds per question at 5,000 pages and
16 to 20 seconds at 50,000 (section "Measured"); the same questions asked of DuckDB take 2 to
25 milliseconds. So the design is small: keep the two tables; keep them free of
secondary indexes (they corrupt under this workload); add one narrow derived table that says
which name is on which statement; and make every list, count, neighbourhood and path a SQL
question that reads only the rows it returns. No graph database, no graph extension.

Lives in: the engine's `db/__init__.py` (the `knowledge_*` readers), `db/migrations/schema.py`
(`migrate_knowledge_indices`), `knowledge/graph.py`, `knowledge/rebuild.py`,
`api/routes/kg/graph.py`, `api/routes/kg/search.py`, `api/routes/entity/entities.py`,
`api/routes/claim/claims.py`; `fichero-mcp/src/fichero_mcp/server.py` (the `fichero_kg_*`
tools); `fichero-server/tests/perf/`.

## Prior art (what we adopt)

- **Edge list in a columnar table, joins for hops.** The standard relational form of a graph: one
  row per (statement, name). DuckDB answers a neighbourhood as a hash join over it and a bounded
  walk as a recursive CTE (`WITH RECURSIVE … USING KEY` from DuckDB 1.3). Measured below; adopted.
- **SQL/PGQ (DuckPGQ).** The property-graph syntax of SQL:2023 as a DuckDB community extension.
  Not adopted: it is a community build that lags the engine (no build existed for the bundled
  DuckDB 1.5.5 on Apple silicon on the day of the review: the install answered 404), it would have
  to ship inside the app and be signed, and it adds syntax, not speed, over the join it compiles
  to. Looked at again if property-graph queries enter DuckDB's core.
- **A separate graph store.** Not adopted: a second store breaks "one source of truth", needs its
  own crash recovery and sharing rules, and the measured cost of the SQL form leaves nothing for
  it to win at this size.
- **networkx** stays for what has no SQL form: centrality, communities, PageRank over a SCOPE,
  on a cached graph that is built from link rows, never from hydrated models.
- **Apple's on-device index (Core Spotlight and the semantic index behind it).** Its format is
  not published. What is public, and what we take: an item is indexed by a stable identifier with
  a few small typed attributes, never a second copy of its content; an update or a delete names
  the identifier (or a whole domain) and touches only that item; indexing is incremental and put
  off until the machine is idle. Our derived link table follows the same three rules: ids only,
  rewritten per statement, rebuildable in the background.
- **DuckDB's own limits, already learned here.** Secondary (ART) indexes on tables that are
  updated and deleted in bulk went out of step with their rows (#1611, #5644, upstream
  duckdb#26828), and a single-row upsert of a NEW row inside a transaction holds memory until
  commit (upstream duckdb#26830). The design below needs neither.

## Measured (2026-11-20, scratch libraries, synthetic names and statements)

Ten statements a page, 2.5 names a page, a few names on very many pages. Laptop: Apple M1,
16 GB. Desktop: Apple M4, 24 GB. Times are one call, the engine function the route runs.

| Question | 5,000 pages (50,000 statements, 12,500 names), laptop | 50,000 pages (500,000 statements, 125,000 names), desktop |
|---|---|---|
| Statements list, first 200 (`GET /api/claims`) | 3.2 s | 15.8 s |
| Names list, first 50 (`GET /api/entities`) | 0.26 s | 1.9 s |
| One name's neighbourhood, 1 hop (`fichero_kg_neighborhood`) | 3.6 s (3.9 s for a name on 4,209 statements) | 17.0 s |
| Whole graph built for path, centrality (first call after any change) | 4.4 s | 20.1 s |
| The same graph, already cached | 0.6 ms | 0.6 ms |
| Statement count per name, as built (`/entities/top`, `/claim-counts`) | 64 ms | 367 ms |
| One name's pages, as built (`LIKE` over the id list) | 4 to 9 ms | 7 to 11 ms |
| Peak engine memory during these reads | 1.2 GB | 8.5 GB |
| Library file | 23 MB | 163 MB |
| **With the link table (SQL, no index):** build it from the statements | 65 ms | 97 ms (676,000 rows) |
| one name's statements | 0.3 to 2 ms | 2 to 8 ms |
| one name's neighbours with weights, 1 hop | 1.9 to 2.4 ms | 7 to 11 ms |
| reach within 3 hops (recursive CTE) | 5.5 ms | 12.7 ms |
| shortest path, at most 3 hops (recursive CTE) | 7 ms | 10.8 ms |
| top 30 names by statement count | 2.3 ms | 8.1 ms |
| names filtered by text, first 50 | 5.5 ms | 25 ms |
| A secondary index on the link table (not adopted) | no faster: 2.0 ms against 1.9 ms | 6.4 ms against 6.7 ms, and 550 ms to build |

Writing: 1,570 statements a second on the laptop and 2,670 on the desktop through `save_many`,
7,800 and 17,500 names a second. A page's ten statements cost 4 to 6 ms; the store is not what
makes extraction slow. The 744 tests of `tests/unit/kg`, `tests/unit/knowledge` and two files of
`tests/unit/db` (the canonical knowledge routes, the schema migrations) pass.

## Behaviors

### A. The store

- `kg.store.two-tables-are-the-record` — **[OK]** names live in `knowledgeentitys` and statements
  in `knowledgeclaims`, one column per model field, made and widened by `Database._ensure_table`;
  lists and nested values (names, dates, places, the attribution chain, `entity_ids`) are JSON
  text in their column. Pinned: `tests/unit/db/test_canonical_knowledge_routes.py`.
- `kg.store.provenance-and-confidence-are-on-the-row` — **[OK]** a statement carries its page
  (`source_document_id`), its stretch (`source_char_start`, `source_char_end`, `source_anchor`),
  its `confidence`, its `epistemic_status`, its `curation_state` and who made it
  (`attribution_chain`); a name carries its `source_supports` and `curation_state`. Built:
  `models/knowledge.py` (`KnowledgeClaim`, `KnowledgeEntity`). Pinned:
  `tests/unit/kg/test_entity_says_who_made_it_to_spec.py`.
- `kg.store.no-secondary-index-on-the-two-tables` — **[OK]** the two tables keep their primary key
  and no other index: `migrate_knowledge_indices` (`db/migrations/schema.py`) drops the six that
  once existed, because bulk rewrite of names and statements put them out of step with their rows
  (#1611; the same family as #5644). A new index on either table is refused in review until the
  upstream fault is closed. Pinned: `tests/unit/workflows/test_entity_index_corruption_guard.py`.
- `kg.store.bulk-writes-are-one-statement` — **[OK]** a step that writes many names or statements
  writes them through `Database.save_many`, new rows as a plain multi-row INSERT, so a
  transaction's memory stays small (`db/__init__.py::save_many`). Pinned:
  `tests/unit/db/test_new_rows_in_a_transaction_stay_small.py`.
- `kg.store.link-table-is-derived` — **[GAP]** (#4975, #6755) one derived table, `kg_mentions`, holds
  one row per name on a statement: the name's id, the statement's id, the statement's page, and
  the role (subject, object, named). It has no index and no column a person edits. It is written
  in the same transaction as the statement it describes (the statement's old rows deleted, its new
  rows inserted) and by nothing else. Code today: no such table; the link is the JSON list
  `entity_ids`, searched with `LIKE '%"id"%'` (`db/__init__.py::knowledge_claim_entity_id_values`,
  `knowledge_claims_for_entity_frontier`, `entity_document_link_rows`) or in Python.
  *Test:* `test_kg_mentions_follow_the_statement.py` (not yet written).
- `kg.store.link-table-rebuilds` — **[GAP]** (#6755, #5361) the link table can be thrown away:
  the knowledge rebuild (`/api/kg/rebuild`, `knowledge/rebuild.py`) remakes it in one statement
  from the statements table, and a project whose link table is missing or whose statement count
  disagrees with it is rebuilt when it opens, as a background job that the Activity pane shows.
  Code today: the rebuild remakes vectors, triples and predictions only.
  *Test:* `test_rebuild_remakes_the_link_table.py` (not yet written).
- `kg.store.edge-ends-are-ids` — **[GAP]** (#6756, #5032) a statement that joins two names
  stores both ends as ids when it is written: `subject_entity_id` and the object's id among its
  roles. Code today: the graph ignores `subject_entity_id`; it reads the verb and the object's
  TEXT from `metadata` (`knowledge/_common.py::extract_svo`) and finds the object by a lower-cased
  name lookup at every question (`knowledge/graph.py::build_graph`,
  `api/routes/kg/graph.py::neighborhood_impl`), so two names spelled alike share one end and
  which one is an accident of row order. *Test:*
  `test_an_edge_joins_ids_never_spellings.py` (not yet written).
- `kg.store.mention-rows-carry-the-segment` — **[GAP]** (#5488) when the mention on a segment
  stretch becomes the record of a name's tie to a page
  (`kg.one.mention-is-the-link`), the link table is derived from mentions and gains the segment
  id; nothing that reads the link table changes.

### B. Lists and counts

- `kg.query.filter-runs-in-the-database` — **[GAP]** (#4975, #4643) a list route turns its filters,
  its sort and its page into one SQL question and hydrates only the rows it returns. Code today:
  `list_claims_impl` (`api/routes/claim/claims.py`) reads every statement with `db.all` and
  filters in Python (3.2 s for the first 200 of 50,000); `list_entities_impl`
  (`api/routes/entity/entities.py`) reads every name, sorts in Python, then cuts the page;
  `search_kg` (`api/routes/kg/search.py`) reads both tables for one word. Only the page filter
  of the names list is in SQL (`query_in`). *Test:*
  `test_kg_lists_ask_the_database.py` (not yet written): the query ratchet counts
  rows read, not only statements run.
- `kg.query.pages-are-stable-and-counted` — **[GAP]** (#4975) a list has a stated sort with the id
  as the last key, so page N+1 never repeats or skips a row of page N, and its answer says how
  many rows match in all. Code today: the statements list has no ORDER BY (`Database.all` is
  `SELECT *`), `count` is the length of the page, and `limit` may be 25,000.
  *Test:* `test_kg_list_pages_never_repeat.py` (not yet written).
- `kg.query.confidence-and-maker-are-filters` — **[GAP]** (#5032) the statements list and the
  neighbourhood take a least confidence, a curation state and a maker (a person, a model, a
  rule), applied in the database. Code today: `curation_state`, `claim_type`,
  `epistemic_status`, `source_type` exist on the statements list, in Python; confidence and maker
  are returned on each row and cannot be asked for.
  *Test:* `test_kg_filters_by_confidence_and_maker.py` (not yet written).
- `kg.query.counts-come-from-the-link-table` — **[GAP]** (#4975, #6757) statements per name (the names
  table's badge, "top names"), pages per name and names per page are GROUP BY questions over the
  link table. Code today: `/api/entities/top` and `/api/entities/claim-counts` fetch every
  statement's id list and count with `json.loads` in Python (64 ms at 50,000 statements, and the
  whole dictionary of counts sent to the app); `top_entities` then reads names one `get` at a time.
  *Test:* `test_entity_counts_from_the_link_table.py` (not yet written).
- `kg.query.one-name-costs-what-it-returns` — **[PARTIAL]** (#4975) opening one name costs in
  proportion to that name's statements, not the project's. Built: the drill-down, documents and
  excerpt readers are single SQL scans (`entity_document_link_rows`,
  `knowledge_claim_excerpts_for_entity`), pinned by `tests/perf/test_entity_detail_perf.py`. Not
  built: the same for `GET /api/claims?entity_id=` (3.3 s at 50,000) and the digest
  (`entity_digest` reads every statement).

### C. Neighbourhood, paths, traversal

- `kg.query.neighbourhood-is-a-join` — **[GAP]** (#6758, #5551) the neighbourhood of a name to
  1 or 2 hops is asked of the link table (the name's statements, then the other names on them,
  weighted by the count of statements), ranked and cut in SQL; only the neighbours and edges
  returned are hydrated. The answer is the same as today's for the same data. Code today:
  `neighborhood_impl` reads every name and every statement on each call, with no cache (3.6 s at
  50,000 statements and 17 s at 500,000, whatever the name). *Test:*
  `test_neighbourhood_reads_only_its_rows.py` and a case in
  `test_kg_neighbourhood_perf.py` (not yet written).
- `kg.query.traverse-reads-real-links` — **[OK]** (#5551, #6759) `GET /api/kg/graph/traverse/{id}`
  walks statement-to-statement links. Code: the route and
  `knowledge/graph.py::contradiction_subgraph` read the fields `KnowledgeClaimLink` has
  (`claim_id`, `related_claim_id`, `relation_type`); the stand-in in
  `tests/unit/kg/test_kg_untested_symbols.py` is a `KnowledgeClaimLink`. The route still reads
  the whole statements table once per node visited (`kg.query.walks-are-bounded`). *Test:*
  `tests/unit/kg/test_traverse_with_a_real_claim_link.py`, on a real `Database`.
- `kg.query.path-is-bounded-and-shows-evidence` — **[PARTIAL]** (#5551, #5032) "how are these two
  connected" answers the shortest chain up to a stated number of hops, in either direction, each
  hop with the statements that make it. Built: `GET /api/kg/graph/path` over the cached directed
  graph (`shortest_path_entities`). Not built: the undirected question a researcher means, the
  hop limit, a path over a scope, and an answer without building the whole graph (a recursive CTE
  over the link table: 7 ms at 50,000 statements).
  *Test:* `test_path_between_two_names.py` (not yet written).
- `kg.query.walks-are-bounded` — **[GAP]** (#5551, #6758) every walk has a hop limit, a row limit and
  says when it was cut; none can run without end on a name that is on thousands of statements.
  Built today only for the neighbourhood (`truncated`).

### D. Whole-graph measures

- `kg.graph.cache-is-keyed-by-what-changed` — **[OK]** the networkx graph of a project is cached
  and rebuilt only when the count or the newest change of either table moves, or the Trash does
  (`knowledge/graph.py::_build_cached`, `_cache_signature`). Pinned:
  `tests/unit/kg/test_kg_untested_symbols.py` (the key),
  `tests/unit/api/test_trash_full_graph_leaves_it_out_5406.py` (the Trash).
- `kg.graph.built-from-rows-not-models` — **[GAP]** (#6760, #5551) the cached graph is built
  from the link table's rows (ids and counts) and the names' id, name and type, never by
  hydrating every statement into a model: 4.4 s and about 1 GB at 50,000 statements today for a
  graph of 12,500 nodes and 67,000 edges; 20 s and 8.5 GB at 500,000. *Test:* a case in `test_kg_graph_build_perf.py`
  (not yet written).
- `kg.graph.measures-take-a-scope` — **[GAP]** (#5551, #5032) centrality, PageRank, communities and
  co-occurrence take a scope (a folder, a box, a set of names) and are refused, with the reason,
  above a stated number of edges for the whole project; a long one is a job the Activity pane
  shows and a person can stop. Code today: every measure runs on the whole project inside the
  request; co-occurrence makes every pair of names in a document (285,000 edges from 50,000
  statements).
- `kg.graph.derived-stores-say-their-age` — **[GAP]** (#5361) the graph cache, the link table, the
  triple file and the vectors each answer when they were built and from how many statements, in
  one status route, so a stale one is seen and not guessed.

### E. Tools: CLI and MCP

- `kg.tools.four-reads-exist` — **[OK]** `fichero_kg_entities`, `fichero_kg_claims`,
  `fichero_kg_neighborhood` and `fichero_kg_search` map to `GET /api/entities`, `/api/claims`,
  `/api/kg/graph/neighborhood/{entity_id}` and `/api/kg/search`
  (`fichero-mcp/src/fichero_mcp/server.py::OPERATOR_ALIASES`). Pinned:
  `fichero-mcp/tests/test_tool_registry.py`.
- `kg.tools.answers-fit-an-agent` — **[GAP]** (#5453) a tool's answer is a page with a total and a
  next offset, small by default (50 rows), each statement with its page, stretch, confidence and
  maker; an agent can ask for the top names, a path between two names, and one name's statements
  without reading the whole table. Code today: the four tools inherit the routes above, so a call
  costs seconds at 5,000 pages and `limit` reaches 25,000 rows.
  *Test:* `test_kg_tools_page_and_count.py` (not yet written).

### F. Kept honest at scale

- `kg.scale.ratchet-at-project-size` — **[PARTIAL]** (#5261) the perf ratchet holds a case for each
  question in the table above at 5,000 pages (50,000 statements, 12,500 names), with a ceiling a
  regression breaks. Built: `tests/perf/test_entity_list_perf.py` (1,000 names, 2,000 statements)
  and `tests/perf/test_entity_detail_perf.py` (10,000 names, 60,000 statements, one name).
  Report-only, no ceiling yet, at 50,000 statements / 12,500 names: statements list and counts
  (`tests/perf/test_kg_claims_list_perf.py`),
  `tests/perf/test_kg_neighbourhood_perf.py`, `tests/perf/test_kg_graph_build_perf.py`. Not
  built: path, a ceiling on the four report-only cases, and the 50,000-page run on the build
  machine.
- `kg.scale.memory-stays-flat` — **[GAP]** (#5261) a knowledge read grows the engine's memory by
  the size of its answer, not of the project: 1.2 GB peak at 5,000 pages today, 8.5 GB at 50,000,
  more than a 16 GB laptop can give the engine beside a model.
  *Test:* `test_kg_reads_keep_memory_flat.py` (not yet written).

## Build order

### Stage 1 — What is broken, and the numbers that keep it fixed

#### Step 1.1 — Traverse and the contradiction graph read the link's real fields (built) (#6759)
- Behaviours: `kg.query.traverse-reads-real-links`
- Tests: test_traverse_with_a_real_claim_link.py, fichero-server/tests/unit/kg/test_kg_untested_symbols.py
- Size: S

#### Step 1.2 — The ratchet at project size (#5261)
- Behaviours: `kg.scale.ratchet-at-project-size`
- Tests: test_kg_neighbourhood_perf.py, test_kg_graph_build_perf.py, test_kg_claims_list_perf.py
- Size: S

### Stage 2 — The link table, and filters in the database

#### Step 2.1 — The derived link table, written with the statement and rebuilt on demand (#6755, #5361)
- Behaviours: `kg.store.link-table-is-derived`, `kg.store.link-table-rebuilds`
- Tests: test_kg_mentions_follow_the_statement.py, test_rebuild_remakes_the_link_table.py
- Depends on: 1.2
- Size: M

#### Step 2.2 — Lists page in SQL: filters, a stable sort, a total (#4975, #4643)
- Behaviours: `kg.query.filter-runs-in-the-database`, `kg.query.pages-are-stable-and-counted`, `kg.query.one-name-costs-what-it-returns`
- Tests: test_kg_lists_ask_the_database.py, test_kg_list_pages_never_repeat.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — Counts from the link table (#6757)
- Behaviours: `kg.query.counts-come-from-the-link-table`
- Tests: test_entity_counts_from_the_link_table.py
- Depends on: 2.1
- Size: S

#### Step 2.4 — The neighbourhood as a join; every walk bounded (#6758, #5551)
- Behaviours: `kg.query.neighbourhood-is-a-join`, `kg.query.walks-are-bounded`, `kg.scale.memory-stays-flat`
- Tests: test_neighbourhood_reads_only_its_rows.py, test_kg_neighbourhood_perf.py, test_kg_reads_keep_memory_flat.py
- Depends on: 2.1
- Size: M

### Stage 3 — Edges by id, paths, measures

#### Step 3.1 — A statement's two ends are ids, set when it is written (#6756, #5032)
- Behaviours: `kg.store.edge-ends-are-ids`
- Tests: test_an_edge_joins_ids_never_spellings.py
- Depends on: 2.1
- Size: M

#### Step 3.2 — The path between two names, bounded, with its evidence (#5551, #5032)
- Behaviours: `kg.query.path-is-bounded-and-shows-evidence`
- Tests: test_path_between_two_names.py
- Depends on: 3.1
- Size: M

#### Step 3.3 — The cached graph from rows; measures on a scope; derived stores say their age (#6760, #6866)
- Behaviours: `kg.graph.built-from-rows-not-models`, `kg.graph.measures-take-a-scope`, `kg.graph.derived-stores-say-their-age`
- Tests: test_kg_graph_build_perf.py, fichero-server/tests/unit/kg/test_graph.py
- Depends on: 3.1
- Size: M

### Stage 4 — Filters and tools

#### Step 4.1 — Confidence and maker as filters; the tools page and count (#5453, #6866)
- Behaviours: `kg.query.confidence-and-maker-are-filters`, `kg.tools.answers-fit-an-agent`
- Tests: test_kg_filters_by_confidence_and_maker.py, test_kg_tools_page_and_count.py
- Depends on: 2.2, 3.2
- Size: M

#### Step 4.2 — The link table follows the mention (after Step 1.5 of the overview spec) (#5488)
- Behaviours: `kg.store.mention-rows-carry-the-segment`
- Tests: test_kg_mentions_follow_the_statement.py
- Depends on: 2.1
- Size: S

## Test matrix (legs this surface touches)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | n | — | — |
| Backend (pytest) | y | the link table follows the statement; lists page, sort and count in SQL; traverse on real links; path and neighbourhood answers | `fichero-server/tests/unit/db/`, `tests/unit/api/`, `tests/unit/kg/` |
| Perf ratchet | y | each question of "Measured" at 5,000 pages under a ceiling; memory flat | `fichero-server/tests/perf/` |
| MCP | y | the knowledge tools page, count and carry provenance | `fichero-mcp/tests/` |
| UX (XCUITest) | n | the tables and the graph view are pinned by their own specs | — |

## Open questions for the owner

1. The neighbourhood today draws an edge between every two names on one statement when the
   object is not a known name. With ends stored as ids (Step 3.1), should "named on the same
   statement" stay as a third, weaker kind of edge, or go? (`explore.network.edge-rule-is-named`
   names the rules; this is which of them the default view draws.)
2. The ceiling for whole-project measures (`kg.graph.measures-take-a-scope`): proposed 200,000
   edges, above which a scope is asked for.

## Future (ideas, not scheduled)

- Property-graph queries (SQL/PGQ) once DuckDB carries them in core.
- The link table sorted by name id at rebuild, so DuckDB's zone maps skip most of it; worth
  measuring only past a million statements.
