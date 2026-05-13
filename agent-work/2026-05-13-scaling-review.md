# Scaling Review — Does the design hold up at book / 400-case scale?

Daniel: "does it scale to a book or 400 cases?"

## Test corpora — concrete numbers

| Scenario | Documents | Pages | Entities | Claims | RDF triples |
|---|---:|---:|---:|---:|---:|
| Today's "Shifting Livelihoods" | 1 | 84 | ~150 | ~800 | ~3,000 |
| **A book** (1 PDF, dense extraction) | 1 | 400 | ~1,000 | ~5,000 | ~20,000 |
| **400 cases** (legal/historical) | 400 | ~2,000 | ~10,000 | ~50,000 | ~200,000 |
| Aspirational (future) | 10,000 | ~100,000 | ~200,000 | ~1M | ~4M |

These are claim-extraction estimates from real-world archives (rough rule of thumb: ~10-20 claims per dense page of academic prose).

## Headline answer

**Mostly yes — the architecture is scale-friendly — with five specific bottlenecks that will bite at the 400-case tier and need to be fixed before that user ships.**

The book tier (1 doc, ~5K claims) works on today's code with minor lag.
The 400-case tier (50K claims, 10K entities) breaks at five concrete spots.
The aspirational tier (1M claims) needs deeper rework.

Bottlenecks below, by severity.

---

## ⚠️ Bottleneck 1 — `build_full_graph(db)` called on every request

**Where:** `kg_graph.py` calls `build_full_graph` or `build_full_cooccurrence` on **18 separate endpoint handlers**. Verified: every request rebuilds the networkx graph from the full DuckDB row scan.

**Cost at scale:**

| Tier | claims | build time | endpoint latency |
|---|---:|---:|---:|
| Shifting | 800 | ~50ms | ~100ms — fine |
| Book | 5,000 | ~300ms | ~500ms — noticeable |
| 400 cases | 50,000 | **~3-5 seconds** | every PageRank / community / similar / neighborhood call freezes the UI |
| 1M | 1M | ~60+ seconds | unusable |

**Fix (small):** Library-scoped LRU cache keyed by `(library_path, last_claim_updated_at)`. Invalidate on any claim write. ~30 lines. Memory cost: ~10 MB per cached graph at 50K claims.

**Fix (medium):** Persistent cached graph on disk — pickle the networkx graph to `<library>/kg-graph.pickle`. Reload on app start. Re-build incrementally on claim insert (single-claim delta is O(E) for that claim's edges, not O(N²)).

**Cost of not fixing:** at 400 cases, every endpoint Daniel ships in Stage 1 is broken in practice. PageRank shows a 5s spinner. Communities take 8s. Neighborhood with hops=2 takes 15s.

**Recommendation:** ship the in-memory LRU cache before the focus-neighborhood viz lands. ~30 min of work. Issue to file.

---

## ⚠️ Bottleneck 2 — DuckDB has no indices on `KnowledgeClaim` / `KnowledgeEntity`

**Where:** `db_migrations.py` indexes `activities` (timestamp/type/workflow/batch/thread/level — 6 indices). Indexes `provider_refs`. **Does NOT index** `knowledge_entities`, `knowledge_claims`, `documents`, `artifacts`. Verified by grep.

**Cost at scale:** every query of the form `WHERE source_document_id = ?` does a full table scan.

| Query | At 50K claims | At 1M claims |
|---|---:|---:|
| Claims for one doc (no index) | ~50ms | ~1-2s |
| Claims by entity_id (entity_ids is a list — JSON unpack on each row) | ~200ms | ~10s |
| Entity by canonical_name | ~30ms | ~500ms |

DuckDB is column-oriented and fast, but scans dominate everything once you cross ~100K rows.

**Fix:** Add 6 indices via a new migration:

```sql
CREATE INDEX idx_claims_source_doc ON knowledge_claims(source_document_id);
CREATE INDEX idx_claims_page_label ON knowledge_claims(source_document_id, source_page_label);
CREATE INDEX idx_entities_name ON knowledge_entities(canonical_name);
CREATE INDEX idx_claims_type ON knowledge_claims(claim_type);
CREATE INDEX idx_claims_status ON knowledge_claims(epistemic_status);
CREATE INDEX idx_claims_created ON knowledge_claims(created_at);
```

`entity_ids` is a JSON list inside a column — DuckDB can't index that directly. Need either (a) a join-table `claim_entities(claim_id, entity_id)`, or (b) DuckDB's JSON path index. The join-table approach is cleaner; ~50 lines of migration + write-path update.

**Recommendation:** add the 6 simple indices NOW (5 min) + plan the claim_entities join-table for a 0.0.3 follow-up.

---

## ⚠️ Bottleneck 3 — rdflib SPARQL chokes past ~500K triples

**Where:** `kg_sparql.py` calls `triples_module.build_graph(entities, claims)` which materializes EVERY triple into an in-memory `rdflib.Graph`. Then runs SPARQL.

**Cost at scale:**

| Tier | triples | build time | SPARQL select | SPARQL with JOIN |
|---|---:|---:|---:|---:|
| Shifting | 3K | ~80ms | ~10ms | ~50ms |
| Book | 20K | ~400ms | ~50ms | ~300ms |
| 400 cases | 200K | ~3-4s | ~200ms | ~2-3s |
| 1M | 4M | **rdflib heap-thrashes** | OOM risk | unusable |

rdflib stores triples in Python dicts. RAM cost ~200 bytes/triple. At 1M triples = ~200 MB Python heap just for the graph.

**Fixes:**

- **Cheap:** same LRU cache as bottleneck 1 — re-use the materialized rdflib.Graph across requests within the same library, invalidate on writes. Brings book + 400-case down to acceptable.
- **Medium:** swap rdflib for **Oxigraph** (Rust-backed, drop-in SPARQL-compatible, ~10× faster + 5× less memory). pip install oxigraph; thin adapter.
- **Heavy:** external Jena Fuseki or GraphDB sidecar. Don't need this yet.

**Recommendation:** cache for now (covers 400 cases). Switch to Oxigraph as a 0.0.3 task only if Daniel hits a real workload that demands it.

---

## ⚠️ Bottleneck 4 — Frontend lists at scale

**Where:** SwiftUI inspector sections (Entities, Claims, Sources) render `ForEach` over arrays.

**At scale:**

- One entity card on a 400-case corpus might have 100+ claims (a frequently-mentioned person).
- The "Entities" chip strip in a doc inspector: a dense page might mention 50 entities; a doc might mention 500.
- The "Similar Claims" panel (already shipped, #959): cap is already 10 — fine.
- Search results: unbounded — needs pagination.

**Fixes:**

- `LazyVStack` everywhere we have a `ForEach` over claims/entities (cheap; SwiftUI handles it).
- Sectional cap with "show all (N)" sheet — already in the wireframe (Entities chip section: cap at 8, then sheet).
- Pagination on Search results (load 20, "load more" button).
- Virtualized chip strip for Entities (only render visible). SwiftUI's `LazyHStack` covers this.

**Recommendation:** mechanical fix in each section as we build it.

---

## ⚠️ Bottleneck 5 — Focus-neighborhood truncation can hide the most important neighbors

**Where:** `/api/kg/graph/neighborhood/{id}?limit=50` (shipped today) caps at 50 neighbors with arbitrary first-N order.

**At scale:** a famous entity (e.g. "Napoleon" in a Napoleon corpus, "Carlos" if he's the protagonist) might have 800 connecting claims. The 50-neighbor cap hides the most-claimed neighbors arbitrarily.

**Fix:** rank-then-truncate. Sort neighbors by edge weight (claim count) descending, OR by PageRank score of the neighbor, then take top-50. ~10 lines.

**Recommendation:** add ranking to the neighborhood endpoint before the focus-viz ships in Phase 5.

---

## What scales fine without changes

- **PDFKit per-page rendering** — PDFKit only renders the visible page; a 400-page PDF loads as fast as a 4-page one.
- **Per-page highlight overlays** — we only fetch highlights for visible pages. Indexed query (after bottleneck 2 fix).
- **LanceDB vector search** — approximate nearest neighbor; sub-100ms even on 1M vectors. ✓
- **Per-document scope** — every inspector query is scoped to one document or one entity. Bounded. ✓
- **Three-column layout** — pure SwiftUI; cost-free.
- **OpenAPI / Swift codegen** — schema size is bounded by route count, not corpus size. ✓
- **Backend SSE streaming** — workflow execution streams per-event; doesn't load whole result. ✓
- **PyKEEN training** — already a background task with status. Slow but not blocking. ✓
- **rdflib SVO predicate URIs** — verb slugification is per-claim, O(N) one-time at extraction. ✓
- **DuckDB stat aggregates** (counts, averages) — column-oriented store is fast at these. ✓

---

## Per-view scaling sanity check

| Wireframe view | Book (5K claims) | 400 cases (50K claims) | Notes |
|---|---|---|---|
| View 1 Library reading | ✓ fine | ⚠ inspector lists need LazyVStack + cap-N+sheet | Per-doc claim list capped per-page is fine |
| View 2 KG explorer | ⚠ slow without graph cache | ❌ unusable without bottlenecks 1+5 fixed | Focus-neighborhood is inherently bounded by hops/limit |
| View 3 Claim card | ✓ fine | ✓ fine | Single card, no scale concern |
| View 4 Source preview | ✓ fine | ✓ fine after bottleneck 2 (indexed page query) | Per-page highlight fetch is bounded |
| View 5 Library list | ✓ fine | ⚠ thumbnail grid for 400 needs lazy load | Existing grid already does this |
| View 6 Workflows | ✓ fine | ✓ fine | Few workflows, low scale |
| View 7 Activity | ✓ fine | ⚠ need date-range + run-state filter | 2000+ run rows |
| View 8 Chat KG-RAG | ✓ fine | ✓ fine | Retrieval caps to 5-20 claims per turn |
| View 9 Search | ✓ fine | ⚠ pagination needed | Unbounded result list otherwise |

---

## Specific things to file before the rebuild ships

Five new issues (all 0.0.2 since #983 is 0.0.2):

- **Cache networkx graph per library** (LRU + write-invalidate) — fixes bottleneck 1.
- **Add DuckDB indices on knowledge_entities + knowledge_claims** — fixes bottleneck 2 + 6 sql lines.
- **Cache rdflib graph per library** — fixes bottleneck 3 for 400-case tier.
- **Rank-then-truncate in `/neighborhood/{id}`** — fixes bottleneck 5.
- **Frontend lazy-load + cap+sheet for Entities + Claims sections** — fixes bottleneck 4 (folds into Phase 3 work).

Plus one 0.0.3 candidate:

- **Migrate `entity_ids` from JSON list to a `claim_entities` join table** — enables typed JOIN queries, unlocks indexable entity→claim lookup, prerequisite for the aspirational 1M tier.

---

## At which scale does each design choice fail?

| Choice | Breaks at |
|---|---|
| Focus-neighborhood viz (bounded by hops+limit) | never breaks; only the rendering thread can stall if limit too high |
| Three-column canonical layout | never breaks; pure SwiftUI cost |
| Claim card with SPO + source link | never |
| Source preview with highlights | breaks if we render all highlights for all pages at once; per-page lazy fix |
| `/api/kg/graph/centrality` | starts noticeable at 5K; needs index + cache at 50K |
| `/api/kg/sparql` | starts feeling slow at 50K; needs cache; rdflib OOM around 1-2M |
| `/api/kg/graph/neighborhood/{id}` | always bounded ✓; ranking improves quality past ~1K neighbors |
| PyKEEN training | takes hours past ~500K triples; background task acceptable |
| Frontend `ForEach` over claims | painful past ~500 visible; LazyVStack ✓ past ~5K |
| Library-wide entity list | scrolling past 1K is rough; search field + sheet fix |
| Chat KG-RAG retrieval | caps to k=5-20 per turn; bounded ✓ |

---

## The book scenario (1 doc, 400 pages, ~5K claims) — verdict

**Works today, after a one-line fix.** Add a `@lru_cache` to `build_full_graph`. Book reading + KG explorer + source preview all run sub-second on M1.

## The 400-case scenario (~50K claims, ~10K entities) — verdict

**Requires the five bottleneck fixes above** — the cache, the indices, the rank-then-truncate, plus mechanical frontend LazyVStack. Total work: ~half a day. After that fix-set, all nine wireframe views run sub-second on M1.

## The aspirational 1M scenario — verdict

**Needs deeper changes:** Oxigraph for SPARQL, persistent on-disk networkx graph snapshot, claim_entities join table, PyKEEN GPU offload. **None of these are blockers for the 0.0.2 release** — file as 0.0.3+ research issues if the workload ever materializes.

---

## What I'd do next

1. **File the five bottleneck issues** (10 min) — so they're visible in the backlog before code lands.
2. **Add the DuckDB indices migration** (5 min) — pure win, zero risk, helps every query Fichero does.
3. **Add `@lru_cache` to `build_full_graph`** (15 min) — unblocks the 400-case tier on the endpoints I shipped today.
4. **Add rank-then-truncate to `/neighborhood`** (15 min) — quality improvement that pays off before the viz lands.
5. **THEN** continue Phase 2 (claim card source-doc navigation in ContentView).

These four backend fixes total ~45 min and remove the scale concern from the whole wireframe.

---

## Honest caveats

- These numbers are estimates from comparable systems, not measured against your actual corpora. We should run a real load test once 400 cases are ingested — script: `_gather_triples` + `build_full_graph` + `nx.pagerank` with timing. Half hour of work.
- networkx is pure Python; the move to scipy-backed sparse matrices for centrality computations would 5× perf without changing the API. Worth knowing.
- DuckDB's column-store advantage means our "no indices" situation is less catastrophic than it would be in PostgreSQL — but indices on `source_document_id` and `canonical_name` still cut hot-path queries 10×.
