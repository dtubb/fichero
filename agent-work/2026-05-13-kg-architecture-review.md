# Fichero KG Architecture — Review + Plan (2026-05-13)

Daniel asked for a thorough review, not ad-hoc fixes. This document covers:

1. What we have (every layer, with file pointers)
2. Direct answers to your questions
3. What works, what doesn't, what's missing
4. Plan (front + back), staged by what unlocks what
5. Trade-offs + risks

---

## 1. What we have today

### 1.1 Data layer (sources of truth)

| Store | Path | What it holds |
|---|---|---|
| **DuckDB** (canonical) | per-library `.fichero/library.duckdb` | `KnowledgeEntity`, `KnowledgeClaim`, `KnowledgeClaimLink`, `DocumentCitation`, `InterpretiveFramework`, `Interpretation`, `PatternInstance`, `EntityMergeAudit`, `Note`, `Annotation`, all Documents + Artifacts + Sources |
| **LanceDB** (vectors) | per-library `.fichero/lance/` | Per-claim + per-entity embeddings (intfloat/multilingual-e5-large via FastEmbed, L2-normalized) |
| **rdflib** RDF graph | in-memory + on-disk `kg.nt` | Materialized triples — `foaf:Person`, `schema:Place/Organization/Event`, `skos:Concept`, claims as `rdf:Statement` reifications. **SPARQL-queryable.** |
| **networkx MultiDiGraph** | in-memory derived | Centrality, betweenness, shortest path, co-occurrence subgraphs. Derived from DuckDB. |
| **PyKEEN model** | per-library trained weights | KG embedding model (TransE / RotatE / etc) for link prediction. Endpoints `/api/kg/pykeen/train` + `/api/kg/pykeen/predict/{entity_id}`. |

So we already have a **5-store** stack: canonical rows + vectors + RDF + graph analytics + KG embeddings. That's roughly state-of-the-art for academic-history-grade KG work; very few research stacks have all five.

### 1.2 Extraction pipeline (entities/artifacts → claims with SVO)

**The flow:**

```
Ingest (PDF/image/text)
   → Document + Page children + Artifacts (loaders + Apple Vision OCR + Kreuzberg)
       → `extract_all` LangGraph node (LLM, any provider incl. Apple Intelligence)
           → structured-output JSON: per-section items
              { name, verb, object, source_text, claim_type, epistemic_status, grounds, warrant, ... }
                  → `_write_kg_rows`
                      → KnowledgeEntity rows + KnowledgeClaim rows
                          → metadata["subject" / "verb" / "object"] = <values>
                          → text = f"{name} {verb} {object}."
                          → source_char_start/end + source_bbox + source_excerpt + source_page_label
                          → kg.rebuild → rdflib triples + networkx graph + PyKEEN re-embed
```

**Files:**
- `fichero-engine/src/fichero/workflows/tools/extractors.py` — extract_all (`_run_extractor` line 843, `_write_kg_rows` line 1207, SVO at 1375-1456)
- `fichero-engine/src/fichero/kg/spacy_ner.py` — spaCy backbone for NER fallback
- `fichero-engine/src/fichero/kg/triples.py` — rdflib materialization + `sparql()` helper
- `fichero-engine/src/fichero/kg/graph.py` — networkx derived view
- `fichero-engine/src/fichero/kg/pykeen_predictor.py` — KG embeddings
- `fichero-engine/src/fichero/kg/rebuild.py` — orchestrator that refreshes all derived stores after extraction

**Apple Intelligence is supported as an LLM provider** for the extractor — `provider=apple_intelligence` routes the JSON schema to fm-bridge on host. Apple **Vision** (different framework) is used upstream for OCR.

### 1.3 KG API surface (post-1587a1b6 consolidation)

15 modules under `/api/kg/*`:

| Module | What it exposes |
|---|---|
| `kg_search` | Free-text search over claims |
| `kg_claim_search` | Vector-based similar-claim search (LanceDB) — used by today's RelatedClaimsPanel |
| `kg_claim_analysis` | Contradictions + evidence chain |
| `kg_entity_curation` | Merge / split / audit + semantic entity search |
| `kg_graph` | Centrality, co-occurrence, traverse, path, metrics |
| `kg_predictions` | Heuristic link prediction |
| `kg_pykeen` | Train + predict via PyKEEN |
| `kg_review` | Review queue for ambiguous matches |
| `kg_mutations` | PATCH/DELETE entity, DELETE claim |
| `kg_interpretations` | Interpretive frameworks (#37) |
| `kg_inclusion` | Library/folder/document scope rules |
| `kg_citations` | Per-doc citation graph (inbound/outbound) |
| `kg_triangulation` | Multi-source claim corroboration |
| `kg_rebuild` | Rebuild RDF + networkx + PyKEEN |
| `graph_exploration` (legacy) | `execute_graph_query` — custom queries (partial SPARQL exposure) |

**SPARQL is supported under the hood** but not exposed as a clean HTTP endpoint yet. `graph_exploration.execute_graph_query` is partial.

### 1.4 Hermeneutics + Epistemology layer

`hermeneutics_models.py` defines:
- `InterpretiveFramework` (a named lens — e.g. "post-colonial reading")
- `Interpretation` (an interpretive act applied to a claim or entity)
- `PatternInstance` (recognized motifs)
- `HermeneuticCircleState` (back-and-forth navigation state)
- `HermesSuggestionRequest/Response` (LLM-driven interpretive suggestions)

This already exists. It's the "epistemology" layer Daniel mentioned. Surfaced via `/api/kg/interpretations` and `/api/hermeneutics`.

### 1.5 Frontend (SwiftUI)

- `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/` — the KG center pane (1407 lines in OntologyBrowser.swift, includes today's ForceDirectedGraphView + EntityKindChartView).
- `fichero/fichero/Views/Library/DocumentInspector/` — the right inspector (1005 lines main + 4 subfiles, ~3100 LOC total). Today added: `RelatedClaimsPanel`, `CitationGraphPanel` to Info tab.
- `fichero/fichero/Services/ArtifactServiceGenerated.swift` — hosts `EntityServiceGenerated` with 17+ KG methods.

**Status: usable but several broken surfaces (#976–#982).**

---

## 2. Direct answers to your questions

### "How are SVO KG data generated from entities/artifacts?"

**Workflow path:** A document goes through `extract_all`, a LangGraph node that takes the page text (+ Apple Vision OCR output for handwriting/tables) and prompts an LLM with a structured-output schema. The LLM emits items like:

```json
{
  "name": "Carlos",
  "verb": "served as",
  "object": "the alcalde of Popayán",
  "source_text": "Carlos served as alcalde for two terms",
  "claim_type": "fact",
  "epistemic_status": "confirmed",
  "grounds": null, "warrant": null
}
```

`_write_kg_rows` composes `claim.text = f"{name} {verb} {object}."` and saves SVO into `claim.metadata["subject" / "verb" / "object"]`.

**Do we need a workflow for that?** ✅ Already exists. Daniel uses it via the Catalogue workflow (#181) which fans out per-file.

### "Is this Apple Vision?"

Two different Apple frameworks:

- **Apple Vision** — OCR / text recognition / handwriting. Used at the loader level for image documents and handwritten PDFs. (`workflows/tools/handwriting.py`, `loaders/image_loader.py`)
- **Apple Intelligence** (Foundation Models via fm-bridge) — Local LLM. Available as one of many providers for the extractor. When `provider=apple_intelligence` is chosen, the JSON schema goes to the on-device model instead of OpenAI/Anthropic/etc.

### "Are there KG embedding models?"

Yes — **PyKEEN** is integrated (`kg/pykeen_predictor.py` + `/api/kg/pykeen/*` routes). It trains TransE/RotatE-style embeddings over the RDF triples and supports link prediction ("what entity is most likely connected to X with relation 'wrote'?"). Plus we have **vector embeddings** per claim and per entity (FastEmbed e5-large, LanceDB) for semantic similarity — different model class, complementary purpose.

### "Cypher-like query — do we have something similar?"

**Yes: SPARQL.** rdflib is integrated (`kg/triples.py:sparql()`), the triples are materialized to `kg.nt` after each extraction run. SPARQL is the W3C standard equivalent of Neo4j's Cypher. Functionally equivalent for KG queries; less ergonomic than Cypher, more interoperable with academic linked-data tooling.

**What's missing:** a clean HTTP endpoint that accepts a SPARQL query string and returns results. `graph_exploration.execute_graph_query` is partial. **Adding a `POST /api/kg/sparql` would be small.**

### "What if we want to visualize the whole thing?"

Doesn't scale — period. The standard patterns for large KGs (>10k entities):

1. **Server-side aggregation** — pre-compute Louvain / Leiden communities (networkx has these). Return a supernode graph (~100 nodes). Frontend renders the supernodes; clicking one fetches its contents.
2. **Server-side layout** — compute force-directed / hyperbolic positions once on the backend (matplotlib / graphviz / sigma.js layout libraries), send static (x, y) tuples. Frontend just renders. Eliminates client-side physics entirely.
3. **Level-of-detail (LOD)** — zoom-out shows clusters; zoom-in pulls inside-cluster nodes via a `/neighborhood/{cluster_id}` endpoint.
4. **Focus-neighborhood view** — never render the whole graph. Always show "focus entity + k-hop neighbors." This is what Tinderbox Hyperbolic and Neo4j Bloom Explore do. The "whole graph" is unreachable; you navigate it node by node.

**For 1M entities specifically:** the only viable visualization is **(a)** a 2D scatter (no edges) of UMAP/t-SNE projections of the entity vectors — gives the "shape of the corpus" without any graph rendering work, OR **(b)** the focus-neighborhood view + a cluster-summary overview, never both at once.

---

## 3. What works / what doesn't / what's missing

### Works
- Backend KG extraction: clean, multi-layer (DuckDB + LanceDB + rdflib + networkx + PyKEEN).
- KG endpoints: 15 modules, comprehensive coverage.
- Vector search over claims via `kg_claim_search`.
- Entity curation: merge / split / audit / undo.
- Interpretation + framework layer: built but UI-side underused.
- Citation graph: per-doc inbound/outbound exposed (`#974`-prep methods I added today are usable).
- Per-claim provenance: `source_document_id`, `source_page_label`, `source_char_start/end`, `source_bbox` — everything needed for "back to source."

### Doesn't work
- **Graph viz at corpus scale.** Force-directed O(N²) physics on main thread, beachballs at ~30+ entities. (#976)
- **Claim card hides the structure.** Renders `claim.text` (composed prose) but ignores the SVO metadata that's already there. The card looks like loose text. (#978/#979)
- **No source navigation.** Claim card has `sourceDocumentId` but no "open source" affordance. The whole point of the KG (back to source) is one tap away from working but the wiring isn't there. (#978/#982)
- **KG/Entity terminology confusion.** OntologyBrowser is mis-labeled "Knowledge Graph" — it's an *entity browser*. The actual KG = the claim set. Inspector should distinguish "Entities" tab from "Claims" tab. (Daniel's prompt)

### Missing
- **`POST /api/kg/sparql`** — clean Cypher-equivalent query endpoint. Small.
- **`GET /api/kg/neighborhood/{entity_id}?hops=1`** — focused-neighborhood query for the new viz. Backed by networkx (already in memory). Small.
- **`GET /api/kg/communities`** — Louvain/Leiden clustering for zoom-out. networkx has both. Small.
- **Server-side graph layout** (force-directed positions cached) — for "render large graph without melting the client." Medium.
- **Subject/verb/object as typed top-level fields** on `KnowledgeClaim` (#984). Quality-of-life.
- **DocumentInspector "Claims" tab** — claims where `source_document_id == this.doc.id`. Daniel's #982 ask. Small.
- **KG RAG for chat** — combine vector search + KGE link prediction to feed claim context into LLM chat. Medium — needs a chat-layer integration.

---

## 4. Plan — staged delivery

### Stage 0 — Triage (no code, just decisions)

Before touching code:
- **Confirm:** is the goal to make today's broken viz usable, OR rip-and-replace with the focus-neighborhood model? (Strong recommendation: rip-and-replace. Today's graph mode is fundamentally the wrong primitive for the data.)
- **Confirm scope:** are we still inside 0.0.2 polish, or has this become a 0.0.3 architectural rework? (Strong recommendation: 0.0.3. Scope of #982 + #976 redesign + the neighborhood API is more than a bug-fix milestone.)

### Stage 1 — Backend surface for the new viz

Three small endpoints unblock the right frontend:

- **`GET /api/kg/neighborhood/{entity_id}?hops=1&limit=50`** — returns entity + k-hop neighbors + the connecting claims (with SVO). Implemented over networkx (already in memory after `rebuild_kg`). ~30 min.
- **`POST /api/kg/sparql`** — accepts query string, returns rows. Thin wrapper over `kg/triples.sparql()`. ~20 min.
- **`GET /api/kg/communities`** — Louvain clustering of entities. ~20 min.

Plus **#984** (SVO promoted to top-level fields) — quality-of-life, defer until viz proves the data shape.

### Stage 2 — Claim card + entity detail (small, high-impact UX fixes)

- Read SVO from `claim.metadata` and render `subject **verb** object` instead of `claim.text`. **NO fallback to `claim.text` per Daniel: "we want to show the KG, not mix stuff up. if KG is absent, we generate it."** When SVO is absent → skip the card or show a "regenerate KG" CTA.
- Add `entity.description` to the entity detail header (Carlos was missing biographical content).
- Add source-doc citation line + open-source button on every claim card.
- Default-collapse the verbatim excerpt.

### Stage 3 — Focus-neighborhood visualization

Replace the broken global force-directed graph with a Tinderbox-hyperbolic / Neo4j-Explore-style focus view:
- User picks a focus entity (search or click in entity list).
- Frontend calls `GET /api/kg/neighborhood/{id}?hops=1`.
- Render: focus at center, neighbors radially, edges labeled with the claim's verb.
- Predicate filter checkboxes (per your Tinderbox screenshot).
- Hover/click reveals labels; default-hide except focus + top-K-degree neighbors.

### Stage 4 — DocumentInspector reorganization (per #982)

- Rename today's KG sections. Add a **Claims** section to Info tab showing `claims WHERE source_document_id == this.doc.id`.
- Add an **Entities** section showing distinct entities mentioned in this doc's claims.
- The OntologyBrowser stays as the library-wide "explorer" mode.
- Center pane always shows a source preview when navigation came from a claim → tap claim, doc opens with span highlighted.

### Stage 5 — KG-RAG for chat

- Compose chat context from: (vector-similar claims) ∪ (PyKEEN-predicted related entities) ∪ (SPARQL-filtered by user-specified framework or scope).
- New service: `RAGContextBuilder` that takes a chat query and returns the top-N most-relevant claims + their source spans.
- Inject as system-prompt prefix in the chat workflow.

### Stage 6 — Whole-corpus visualization (the "1M entities" view)

- Server-side: compute UMAP projection of the entity vectors → cached `(x, y)` per entity.
- Frontend: `Map` mode renders a 2D scatter of all entities (Metal-accelerated point cloud), colored by kind, sized by claim-count. No edges.
- Click → focus-neighborhood view zooms in.
- This is the "explore the entire thing" view Daniel wants.

---

## 5. Trade-offs + risks

- **PyKEEN training is slow** (minutes for small libraries, hours for large). It's a periodic task, not an on-demand call. Need to be honest about that in the UI ("KG predictions last trained 4 hours ago").
- **SPARQL endpoint adds attack surface.** Need query timeouts + result-size caps. Standard practice; not hard.
- **Louvain on small graphs is meaningless.** Don't expose community view until libraries hit ~100+ entities.
- **Server-side layout caching means re-running on every claim add.** Cheap for small graphs, expensive at scale. Need an invalidation strategy. Defer this until we know we need it.
- **The DocumentInspector reorg is intrusive.** Today's panels (Related Claims, Citations) work; moving them to a new tab risks regressions. Recommend: add the new tab alongside, migrate gradually, deprecate the old surfaces only after the new ones are validated.

---

## 6. What I want to do next

Wait for your sign-off on:
1. **Move to 0.0.3 for this work?** (or are we doing it in 0.0.2)
2. **Rip-and-replace** the current Graph + Chart modes, or **patch them first** while building the focus-neighborhood view alongside?
3. **First concrete piece** — pick one:
   - Stage 1 backend (neighborhood + SPARQL + communities endpoints) — opens the door for everything else
   - Stage 2 claim card (most-asked UX fix, can ship today)
   - Stage 4 DocumentInspector reorg (gets us to source preview faster)
   - Stage 3 viz redesign (most visible payoff, longest path)

My recommendation: **Stage 1 backend endpoints first (~1 hr), then Stage 2 claim card (~1 hr), then Stage 3 viz redesign (~3-4 hrs).** Stage 4 reorg can run in parallel with Stage 3.

Standing by.
