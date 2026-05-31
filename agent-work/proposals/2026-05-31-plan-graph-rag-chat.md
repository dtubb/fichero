# Plan: Graph-RAG Retrieval for Chat (#1156 family)

**Date:** 2026-05-31  
**Author:** Agent (read-only architecture pass)  
**Scope:** `fichero-engine/src/fichero/api/routes/chat.py` + new helper  
**Benefits both:** ChatView and ResearchChatPane (both consume POST /api/chat)

---

## 1. Current Retrieval Flow

### Entry point
`chat()` — `fichero-engine/src/fichero/api/routes/chat.py`, lines 262–399.

### What it does today (vector-only)
1. **Pinned-doc path** (when `request.document_ids` is set): loads those documents directly, reads `doc.page_content`, no search at all.
2. **Free search path** (no pinned docs): calls `db.search(query=..., search_type="hybrid", limit=max_sources)` — returns `SearchResult` objects with a `document_id` and `score`.
3. For each result: loads the `Document` row, reads `doc.page_content` or falls back to `_read_file_content(doc.path)`.
4. Assembles `context_docs = [{"id", "name", "content"}]` — raw document text, truncated to 1 000 chars per doc inside `_build_rag_prompt`.
5. `_build_rag_prompt` emits numbered `[Document N: name]` blocks, then the query.
6. Calls LLM, returns `ChatResponse(message, sources, conversation_id, model_used)`.

### What is missing
- No KG traversal of any kind. `KnowledgeClaim`, `KnowledgeEntity`, and the claim-graph edges are never touched during chat.
- Sources in `DocumentSource` are document-level; no claim-level citations.
- The `search_kg` route (text-substring search over entities/claims) and the `neighborhood` endpoint (BFS claim-graph traversal) exist and work but are never called from chat.

### Relevant existing infrastructure (ready to call)
| What | Where | Notes |
|---|---|---|
| `search_kg` | `kg_search.py::search_kg` | Text search returning `KGSearchHit` with `entity_id`, `document_id`, `score` |
| `neighborhood` | `kg_graph.py::neighborhood` | BFS k-hop traversal returning neighbors + `NeighborhoodEdge` (claim_id, source_document_id, source_page_label, predicate) |
| `build_full_graph` | `kg/graph.py` | Builds a cached `nx.MultiDiGraph` from all entities + claims; graph edges carry `claim_id`, `source_document_id`, `source_page_label` |
| `build_full_cooccurrence` | `kg/graph.py` | Undirected co-occurrence graph; entities sharing a source doc are connected |
| `KnowledgeClaim` | `knowledge_models.py` | Fields: `text`, `source_excerpt`, `source_document_id`, `source_page_label`, `entity_ids`, `metadata` (subject/verb/object) |
| `KnowledgeEntity` | `knowledge_models.py` | Fields: `canonical_name`, `entity_type`, `aliases`, `description` |
| `db.query(KnowledgeClaim)` / `db.query(KnowledgeEntity)` | `db.py` | Standard query API already used by `neighborhood` |

---

## 2. Proposed Graph-RAG Flow

The goal is to keep the existing vector search as the entry seed and extend it with KG-expansion and claim-level retrieval, then re-rank and assemble a richer context block before passing to the LLM.

### Step A — Vector seed (unchanged)
Run `db.search(query, search_type="hybrid", limit=seed_limit)` to get the initial set of relevant `document_id`s and scores. `seed_limit` can be slightly higher than the current `max_sources` (e.g. 2x) because the next steps will filter/rank.

### Step B — KG entity linking
For each seed document, look up which `KnowledgeEntity` ids appear in claims whose `source_document_id` matches. This maps seed documents to a set of "anchor entities". Also run `search_kg(q=user_query, types=["entity", "claim"])` as a parallel text sweep to catch entities mentioned by name in the query that might not rank highly via vector similarity.

Merge the entity sets: `anchor_entities = (entities from seed docs) | (entities matched by name in query)`.

### Step C — KG neighborhood expansion
For each anchor entity (capped at `max_entity_expansion`, e.g. 10 anchors), call the core logic of `neighborhood` (i.e. the BFS over `KnowledgeClaim.entity_ids` + `KnowledgeClaim.metadata` verb/object that `neighborhood` already implements) with `hops=1`. Collect:
- The claims that form the edges (each carries `source_document_id`, `source_page_label`, `text`, `source_excerpt`).
- The neighbor entity ids for potential further enrichment.

This is the graph expansion step. It pulls in structurally related claims that vector search may not rank — e.g. a claim about a person's institution might not be in the top-k document chunks but is directly linked in the KG.

### Step D — Merge + rank
Combine:
- **Vector-seeded document excerpts** (step A) — scored by `db.search` relevance.
- **Graph-expanded claims** (step C) — scored by hop distance (hop-1 > hop-2) × claim text relevance to query.

Deduplicate by `source_document_id` + `source_page_label`. Re-rank by a combined score:
```
combined_score = w_vector * vector_score + w_kg * kg_score
```
where `w_vector=0.7`, `w_kg=0.3` as a conservative starting point. Cap the merged set at `max_context_items` (default: 8).

### Step E — Context assembly with claim citations
Build a structured context block for the LLM prompt with two sections:

```
DOCUMENT EXCERPTS (from vector search):
[Excerpt 1: <doc name>, page <label>]
<excerpt text>

KNOWLEDGE GRAPH CLAIMS (structurally related):
[Claim 1: <doc name>, page <label>] <claim text>
[Claim 2: <doc name>, page <label>] <claim text>
```

Extend `DocumentSource` or add a parallel `ClaimSource` response model to expose claim-level citations to the caller (SwiftUI can then render them separately).

### Step F — LLM call (same as today)
Feed merged context to `_build_rag_prompt` (updated to handle both excerpt and claim blocks). No change to LLM plumbing.

---

## 3. Files / Functions to Change

### New helper module (one file)
**`fichero-engine/src/fichero/api/routes/chat_kg_retrieval.py`** (new)

Functions to write:
- `entities_from_seed_docs(db, document_ids: list[str]) -> set[str]` — queries `KnowledgeClaim` where `source_document_id in document_ids`, returns `entity_ids` as a flat set.
- `entities_from_query(db, query: str) -> set[str]` — calls `db.query(KnowledgeEntity)`, does a cheap name/alias substring match (reuse `_score` from `kg_search.py`), returns ids.
- `expand_entities_to_claims(db, entity_ids: set[str], hops: int = 1, max_claims: int = 50) -> list[KnowledgeClaim]` — BFS over `KnowledgeClaim.entity_ids` (the inner loop already exists verbatim in `neighborhood`; extract it).
- `merge_and_rank_context(seed_docs: list[dict], kg_claims: list[KnowledgeClaim], query: str, max_items: int = 8) -> list[ContextItem]` — dedup + score + cap.
- `build_graph_rag_prompt(query: str, context_items: list[ContextItem]) -> str` — replaces `_build_rag_prompt` for the graph-RAG path.

`ContextItem` is a small dataclass: `{kind: "excerpt"|"claim", doc_name, doc_id, page_label, text, score}`.

### Modified files
| File | Change |
|---|---|
| `chat.py::chat` | After vector seed, call `chat_kg_retrieval.assemble_graph_rag_context(db, seed_doc_ids, query, flag=request.use_graph_rag)`. If flag off, fall through to existing path unchanged. |
| `chat.py::_build_rag_prompt` | Keep for the non-graph-RAG path; `build_graph_rag_prompt` in the new module handles the KG path. |
| `chat.py::ChatRequest` | Add `use_graph_rag: bool = False` field (feature flag, defaults off). |
| `chat.py::ChatResponse` / `DocumentSource` | Add optional `page_label: str | None` and `claim_text: str | None` to `DocumentSource` so claim-level citations can flow back to SwiftUI. |
| `kg_graph.py::neighborhood` BFS loop | Extract the BFS inner loop into a shared function (used by both `neighborhood` and the new retrieval helper). This is a refactor, not a feature change — do it in the same PR or a preceding cleanup PR. |

### No changes needed
- `kg_search.py` — used as-is.
- `kg/graph.py` — `build_full_graph` / `build_full_cooccurrence` can be used for future hop-2+ expansion but are not required for the initial 1-hop implementation.
- All Swift / OpenAPI client code — `DocumentSource` gains nullable fields which are backward-compatible in Pydantic and Swift Codable.

---

## 4. Data Flow Diagram

```
POST /api/chat (query Q)
        |
        v
db.search(Q, hybrid)  ──────────────────────────────────────────────> seed_docs [D1..Dn]
        |                                                                        |
        v                                                                        v
entities_from_query(Q)            entities_from_seed_docs(seed_doc_ids)
        |                                                   |
        └──────────────── anchor_entities ─────────────────┘
                                  |
                                  v
                expand_entities_to_claims(anchor_entities, hops=1)
                                  |
                                  v
                         kg_claims [C1..Cm]  (each carries source_document_id, page_label, text)
                                  |
                                  v
              merge_and_rank_context(seed_docs, kg_claims, Q, max_items=8)
                                  |
                                  v
                    context_items: [ContextItem, ...]
                                  |
                                  v
                   build_graph_rag_prompt(Q, context_items)
                                  |
                                  v
                              llm.invoke(prompt)
                                  |
                                  v
                    ChatResponse(message, sources=[DocumentSource+ClaimSource])
```

---

## 5. Feature Flag Strategy

`ChatRequest.use_graph_rag: bool = False` (backend) + `ChatRequest.useGraphRag: Bool = false` (Swift).

- Default `false` — existing behavior is exactly preserved until the flag is flipped.
- SwiftUI `ChatView` and `ResearchChatPane` both send `ChatRequest`; both benefit when the flag is enabled.
- The `Researcher` persona can default to `true` since it is graph-oriented; the plain chat pane can leave it `false` until the feature is validated.
- Remove the flag once the graph-RAG path is validated in a staging review (no A/B permanent flag needed).

---

## 6. Test Strategy

All new retrieval logic lives in `chat_kg_retrieval.py`, making it fully unit-testable without FastAPI or LLM.

### Unit tests (new file: `fichero-engine/tests/unit/test_chat_kg_retrieval.py`)
- `test_entities_from_seed_docs`: seed a `FakeDatabase` with two claims referencing doc A; assert both entity ids are returned.
- `test_entities_from_query_name_match`: insert entity "Darwin" + alias "Charles Darwin"; query "darwin" returns the entity id.
- `test_expand_entities_to_claims_hop1`: 3 entities, 2 claims linking entity-1 to entity-2 and entity-2 to entity-3; expanding from entity-1 at hop=1 should return only the 2 claims touching entity-1.
- `test_merge_and_rank_context_dedup`: same `(doc_id, page_label)` from a vector hit and a claim hit should appear once, scored as max(vector_score, kg_score).
- `test_merge_and_rank_context_cap`: verify `max_items` is respected.
- `test_build_graph_rag_prompt_sections`: assert the prompt contains both "DOCUMENT EXCERPTS" and "KNOWLEDGE GRAPH CLAIMS" sections when both types are present.

### Integration / contract tests
- Extend `fichero-engine/tests/integration/test_chat_endpoint.py` (if it exists) or add a new one: POST to `/api/chat` with `use_graph_rag=true` against a library that has at least one entity and one claim; assert `sources` is non-empty and at least one source has a non-null `page_label`.
- The existing `test_citations_extract.py` suite already validates the claim → source_document_id link and does not need modification.

---

## 7. Risks and Scope Estimate

### Risks
| Risk | Severity | Mitigation |
|---|---|---|
| BFS over all claims is O(claims × anchor_entities) — could be slow on large libraries | Medium | Cap `max_entity_expansion=10`, `max_claims=50`, and log elapsed time; add an index on `KnowledgeClaim.entity_ids` if needed (separate issue) |
| Entity linking via name match on query produces false positives | Low-Medium | Use a score threshold (e.g. > 0.3); the merged ranking step demotes low-confidence hits anyway |
| Claim text quality is variable (short, noisy extractions) | Low | Claims have `source_excerpt` (verbatim source text) which is richer; prefer `source_excerpt` over `text` in the prompt |
| Extracting the BFS loop from `neighborhood` requires refactoring a tested function | Low | Extract to a private `_bfs_claims(db, entity_ids, hops)` helper; existing `neighborhood` delegates to it — behavior unchanged, just refactored |
| OpenAPI schema change for `DocumentSource` + new `ChatRequest` field | Low | Nullable additions are backward-compatible; regenerate `openapi.json` + Swift client as usual |

### Scope estimate
| PR | Contents | Effort |
|---|---|---|
| PR 1 (cleanup) | Extract `_bfs_claims` helper from `neighborhood`; keep `neighborhood` behavior unchanged; unit test the helper | ~0.5 day |
| PR 2 (core graph-RAG) | New `chat_kg_retrieval.py`, update `chat.py` (flag + prompt assembly), update `DocumentSource`, unit tests | ~1.5 days |
| PR 3 (Swift flag) | Add `useGraphRag` to `ChatRequest` Swift model; enable for Researcher pane; regenerate client | ~0.5 day |

**Total: ~2.5 days, 3 PRs.** The flag means PR 2 can ship and be tested before PR 3 flips it on in the UI.

---

## 8. Out of Scope for This Plan

- Community-level context injection (communities from `kg_graph.py::communities`) — potential future enhancement.
- Streaming chat responses — orthogonal concern, same plan applies.
- Persistent conversation KG context (e.g. tracking entities mentioned across turns) — a larger follow-on.
- PyKEEN link-prediction-based expansion (`kg_pykeen.py`) — adds complexity; revisit after baseline graph-RAG is validated.
