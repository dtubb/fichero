# Backend Route Module Organisation Audit — 2026-05-15

Branch `0.0.2`. Working dir: `/Users/danieltubb/code/fichero-0.0.2`.
Scope: read-only audit of `fichero-engine/src/fichero/api/routes/` (~70 modules)
against the canonical layering in `docs/architecture/`. No moves, no edits —
only this proposal.

---

## 1. The Intended Layering (quoted)

From `docs/architecture/api/overview.md`, "API Route Tiers":

> Routes are registered at startup based on the `FICHERO_FEATURE_TIER`
> environment variable (`release` | `dev`, default `release`).

Two tiers:

- **Core Routes (always registered — 23 total)** — the SwiftUI app's daily
  surface (documents, folders, ingest, claims, claim_links, entities,
  multilingual, review_queue, search, settings, sources, models, storage,
  tasks, workflows, workflow_execution, etc.).
- **Dev-Tier Routes** — KG analytics + curation under `/api/kg/*` after the
  `1587a1b6` namespace consolidation, plus interpretation/spatial/research
  layers and "staged" features.

The doc also explicitly documents the 2026-05-12 KG consolidation:

> KG analytics + curation surfaces live under `/api/kg/*` after the
> 1587a1b6 namespace consolidation. The old monolithic
> `/api/knowledge-graph/*` sub-package and the stand-alone
> `/api/interpretations` router were deleted; their unique features
> were ported into focused single-purpose modules below.

And `KG_ENDPOINTS.md` is explicit that:

- `/api/kg/graph/*` is the **single** graph-analytics surface (centrality,
  cooccurrence, path, traverse, metrics).
- `/api/kg/interpretations/*` is the **single** interpretation-CRUD
  surface; `/api/interpretations` is gone.
- `/api/kg/pykeen/*` is the **single** PyKEEN train+predict surface.

What `docs/CLAUDE.md` declares is the *normalised* picture. What's actually
in `routes/` is partly post-consolidation, partly stale.

---

## 2. Current Route Inventory (grouped by inferred domain)

Source of truth for what is *actually mounted*:
`fichero-engine/src/fichero/api/main.py` lines 743–828. Modules absent from
those tables are imported only — not registered. They are dead code.

### A. Document plane (always-on; no overlap suspected)

| File | Mount | Purpose |
|---|---|---|
| `documents.py` | `/api/documents` | Document CRUD + hierarchy |
| `folders.py` | `/api/folders` | Folder hierarchy |
| `ingest.py` | `/api/ingest` | LINK + COPY ingestion pipeline |
| `artifacts.py` | `/api/artifacts` | Per-doc artifact metadata |
| `storage.py` | `/api/storage` | File path / thumb / archive ops |
| `library.py` | `/api/library` | Bootstrap a fresh `.fichero` package (#1075) |
| `iiif.py` | `/api/iiif` | IIIF Image API server (dev) |
| `bibliography.py` | `/api/bibliography` | Stored metadata + DOI/ISBN resolve + BibTeX I/O |
| `citations.py` | `/api/citations` | Document↔document `DocumentCitation` graph (#906) |
| `kg_citations.py` | `/api/citations` | BibTeX *render* per style (chicago/apa/mla) — note path collision |
| `sources.py` | `/api/sources` | Bibliographic source rows (#364) |
| `classifications.py` | `/api/classifications` | User-extensible epistemic_status / claim_type registry (#915) |

### B. Knowledge graph — "domain primitives"

| File | Mount | Purpose |
|---|---|---|
| `entities.py` | `/api/entities` | KnowledgeEntity CRUD + alias / drill-down / co-occurrence |
| `claims.py` | `/api/claims` | KnowledgeClaim CRUD |
| `claim_links.py` | `/api` (paths under `/claims` and `/claim-links`) | KnowledgeClaimLink (supports / contradicts / refines) |
| `annotations.py` | `/api/annotations` | User annotations + promote-to-claim (#914) |
| `notes.py` | `/api/notes` | Zettelkasten Note + NoteLink + backlinks (#917) |
| `projects.py` | `/api/projects` | Research project memberships (#918) |
| `entity_inspector.py` | `/api/entities/{id}/inspector` | Aggregate entity inspector (one-call surface) |
| `document_inspector.py` | `/api/documents/{id}/inspector` | Aggregate document inspector |

### C. Knowledge graph — `/api/kg/*` (post-consolidation)

| File | Mount | Purpose |
|---|---|---|
| `kg_search.py` | `/api/kg/search` | Mixed-type semantic search (entities + claims + notes + annotations) |
| `kg_claim_search.py` | `/api/kg/claim-search` | Claim embed + semantic similarity |
| `kg_claim_analysis.py` | `/api/kg/claim-analysis` | Contradiction + evidence-chain |
| `kg_entity_curation.py` | `/api/kg/entity-curation` | Merge/split with audit trail + entity semantic search |
| `kg_graph.py` | `/api/kg/graph` | NetworkX analytics — centrality, traverse, path, cooccurrence, metrics (#376) |
| `kg_triangulation.py` | `/api/kg/triangulation` | Cross-source SVO support (#900) |
| `kg_predictions.py` | `/api/kg/predictions` | Heuristic prediction generator + run-management (`/heuristic`, run list, apply) |
| `kg_pykeen.py` | `/api/kg/pykeen` | PyKEEN train + predict (#377) |
| `kg_review.py` | `/api/kg/review` | Entity-pair review queue (post-PyKEEN merge candidates) |
| `kg_mutations.py` | `/api/kg/mutations` | Mutation log + undo (#901) |
| `kg_inclusion.py` | `/api/kg/inclusion` | Declarative scope rules |
| `kg_interpretations.py` | `/api/kg/interpretations` | Interpretation + Framework CRUD (canonical, #905) |
| `kg_rebuild.py` | `/api/kg/rebuild` | Rebuild kg.nt + vector materialisations |
| `kg_sparql.py` | `/api/kg/sparql` | SPARQL query endpoint |

### D. Hermeneutics / spatial / research overlays

| File | Mount | Purpose |
|---|---|---|
| `hermeneutics.py` | `/api/hermeneutics` | PatternInstance + hermeneutic-circle navigation + LLM Hermes suggestions. **Also** carries a duplicate `/frameworks` and `/interpretations` CRUD (see §3). |
| `mind_palace.py` | `/api/mind-palace` | Spatial workspace — rooms / nodes / connections / stacks / native notes (Layer 6) |
| `research_agents.py` | `/api/research` | Umbrella router |
| `research_crud.py` | (mounted via `research_agents`) | Project / Plan / Task / Step CRUD |
| `research_notes.py` | (mounted via `research_agents`) | Search sources / notes / checklists |
| `research_tools.py` | (mounted via `research_agents`) | Sandboxed web-search / browser / fetch with SSRF guard |

### E. Search

| File | Mount | Purpose |
|---|---|---|
| `search.py` | `/api/search` | Full-text + vector search; saved-search CRUD; views (table/map/grid) |
| `search_query.py` | (no router) | Pure parser for the `search.py` query syntax — imported, not mounted |
| `search_explain.py` | `/api/search` (dev tier) | Algorithm explanation surface |

### F. Workflow plane

| File | Mount | Purpose |
|---|---|---|
| `workflows.py` | `/api/workflows` | Workflow CRUD, tools listing, codegen |
| `workflow_execution/` (package — `core/runner/threads/cache/visualization/schemas`) | `/api/workflow-execution` | Execute / status / threads / SSE / visualization |
| `activity.py` | `/api` | Activity feed / stats / streaming |
| `batch.py` | `/api` | Bulk workflow execution |
| `chains.py` | `/api` (dev) | Sequential workflow chaining (`workflows/chaining.py` API surface) |
| `tasks.py` | `/api/tasks` | Async background task queue |

### G. Automation triggers

| File | Mount | Purpose |
|---|---|---|
| `actions.py` | `/api/actions` | Action library (pre-built workflow snippets) — dev tier |
| `triggers.py` | `/api` (dev) | File-watcher event triggers (`workflows/file_watcher.py`) |
| `schedules.py` | `/api/schedules` | Cron-style schedules (`workflows/scheduler.py`) |

### H. Models / providers / integrations

| File | Mount | Purpose |
|---|---|---|
| `providers.py` | `/api/providers` | Provider CRUD |
| `provider_keys.py` | (under providers prefix) | API key management + connection test |
| `provider_models.py` | (under providers prefix) | Provider model discovery |
| `models.py` | `/api/models` | AI model management |
| `local_models.py` | `/api` (dev) | Whisper / embeddings / spaCy management |
| `model_comparison.py` | `/api` (dev) | Multi-model response comparison |
| `mcp_tools.py` | `/api/mcp/tools` | MCP tool adapters (always on) |
| `mcp_servers.py` | `/api` (dev) | MCP server lifecycle |
| `integrations.py` | `/api` (dev) | DEVONthink / Bookends / Tinderbox sync |
| `orchestration.py` | `""` (dev) | Orchestration policy rules |

### I. Cross-cutting

| File | Mount | Purpose |
|---|---|---|
| `multilingual.py` | `/api/multilingual` | Language detection + cross-language search + transliteration |
| `migrations.py` | `/api/migrations` | DB schema migrations |
| `chat.py` | `/api/chat` | RAG chat |
| `settings.py` | `""` | App settings |
| `review_queue.py` | `/api/claims` (!) | **Claim** curation state machine — transition / shortlist / curate / reject. Despite its name, this is *not* an entity-pair queue. |

### J. Stale / orphaned (imported but NOT registered)

These files exist in the directory and are listed in
`fichero/api/routes/__init__.py`, but `main.py`'s `_CORE_ROUTE_SPECS` and
`_DEV_ROUTE_SPECS` do not include them. They serve no live traffic.

| File | Lines | Why it's stale |
|---|---:|---|
| `graph_exploration.py` | 911 | Pre-`kg_graph` exploration surface (multi-entity neighbourhood + paths-between). The `overview.md` table still claims it covers "compound queries not in `kg_graph`" — that claim is no longer true; main.py drops it entirely. |
| `graph_traversal.py` | 377 | Was `include_router`'d by `graph_exploration.py`. Dead with its parent. |
| `graph_reasoning.py` | (registered, dev-tier, prefix `""`) | Ranks routes via NetworkX directly. `kg_graph.py` is the canonical NetworkX surface. Likely duplicate; needs decision. |
| `predictions.py` | 420 | Standalone PyKEEN training-job + heuristic + stored-prediction surface mounted at `/api/predictions/*` (paths hardcoded in decorators, no router prefix). Functionally subsumed by `kg_pykeen.py` + `kg_predictions.py`. |
| `orchestration.py` | (registered, dev-tier, prefix `""`) | Ports likely overlap with `mcp_servers` / staged area. Needs decision but currently registered. |

`graph_exploration.py` + `graph_traversal.py` together = **1,288 lines of
unreferenced code**. That's the single biggest deletion candidate.

---

## 3. Conflict / Overlap Matrix

Verdicts: **CONSOLIDATE** = same domain, merge; **CLARIFY** = adjacent, rename
or document boundary; **SEPARATE** = genuinely different, document and leave.

### 3.1 `kg_graph` vs `graph_exploration` vs `graph_reasoning` vs `graph_traversal`

**Verdict: CONSOLIDATE → delete `graph_exploration.py`, `graph_traversal.py`,
`graph_reasoning.py`. `kg_graph.py` is canonical.**

`kg_graph.py` (12 GET endpoints under `/kg/graph`) is the only one in the
KG_ENDPOINTS doc (#376 reference). `graph_exploration.py` and
`graph_traversal.py` are *not registered* anywhere in `main.py`; they were
quietly dropped during the May 12 consolidation but the source files were not
deleted. The `overview.md` table at lines 93–94 still references them as
"uniquely covers compound queries / custom subgraph" — that comment is
obsolete. `graph_reasoning.py` is still registered at the *empty* prefix
under tag `graph-reasoning`; it was the original NetworkX surface that
`kg_graph.py` was supposed to replace. If `kg_graph.py` truly covers
everything (which the doc asserts), `graph_reasoning.py` should follow
exploration/traversal into the trash. **Open question:** are any of
`graph_reasoning`'s 9 endpoints (centrality / communities / etc.) absent
from `kg_graph`? Diff the route paths: `git log -- fichero-engine/src/fichero/api/routes/graph_reasoning.py`.

### 3.2 `predictions` vs `kg_predictions` vs `kg_pykeen`

**Verdict: CONSOLIDATE → delete `predictions.py`. Keep `kg_pykeen` (KGE) +
`kg_predictions` (heuristic) as separate, well-named cousins.**

Three files, two different ideas:

- `kg_pykeen.py` (88 lines, 2 routes): canonical PyKEEN train + predict
  under `/kg/pykeen` — matches `KG_ENDPOINTS.md`.
- `kg_predictions.py` (287 lines): heuristic generator + prediction-run
  list + apply, under `/kg/predictions`. Heuristics live next to learned
  predictions because they share the `KnowledgePredictionRun` row. Different
  *generator*, same *output schema*.
- `predictions.py` (420 lines, 13 routes at `/api/predictions/*`):
  pre-consolidation PyKEEN-only surface. Includes a `/heuristic` route that
  duplicates `kg_predictions`'s `/heuristic`, plus train / training-jobs /
  generate / store / verify endpoints. Registered at empty prefix in dev
  tier. **No SwiftUI caller** uses `/api/predictions/*` — the inspector
  hits `/api/kg/pykeen/*` and `/api/kg/predictions/*` (per KG_ENDPOINTS).

So `predictions.py` is the lone heir of the pre-`/kg` namespace and should be
deleted; its training-job management features need to be ported into
`kg_pykeen.py` first if any are missing (it has training-jobs, model
deletion, and a stored-prediction *verify* endpoint that `kg_pykeen` does
not — these are real features, not just duplicates). Audit:
`git log -- fichero-engine/src/fichero/api/routes/predictions.py`.

`kg_predictions` and `kg_pykeen` are correctly two files: heuristic vs
learned. Both belong.

### 3.3 `hermeneutics` vs `kg_interpretations`

**Verdict: CLARIFY → strip the duplicate `/frameworks` and `/interpretations`
CRUD from `hermeneutics.py`; keep PatternInstance + circle-state +
suggestions there. Treat `kg_interpretations` as the canonical interpretation
CRUD.**

`hermeneutics.py` (579 lines) declares **three** sub-resources:
1. `/frameworks/*` (5 routes) — InterpretiveFramework CRUD
2. `/interpretations/*` (5 routes) — Interpretation CRUD
3. `/patterns/*` (5 routes) + `/circle-state/*` (4 routes) + `/suggestions`
   (1 route) — actually hermeneutic features

`kg_interpretations.py` (268 lines) declares **two** sub-resources:
1. `/frameworks/*` (5 routes) — same shape as #1 above
2. `""` (Interpretation CRUD, 6 routes) — same shape as #2 above

The KG_ENDPOINTS doc canonicalises `/api/kg/interpretations/*` (lines 79–91).
`docs/api/overview.md` line 88 says `hermeneutics` is "PatternInstance +
hermeneutic circle." So the framework + interpretation endpoints in
`hermeneutics.py` are leftover duplication from when hermeneutics owned the
whole interpretation domain. They're *both registered today* (#3 above is
unique to hermeneutics; #1 and #2 collide on Pydantic models but at different
prefixes — `/api/hermeneutics/frameworks` vs `/api/kg/interpretations/frameworks`).
Keeping both means SwiftUI can write to one and read from the other and miss
data. **Decision needed:** confirm the SwiftUI client only consumes
`/api/kg/interpretations/*` (it should — that's what KG_ENDPOINTS says); if
yes, delete the `/frameworks` + `/interpretations` blocks from
`hermeneutics.py`.

### 3.4 `review_queue` vs `kg_review` vs `kg_entity_curation`

**Verdict: SEPARATE but RENAME `review_queue` → `claim_curation`.**

Three different review surfaces:

- `review_queue.py` mounts under `/api/claims` and is the **claim curation
  state machine** (transition / shortlist / curate / reject — the curation
  pipeline #915 references). It piggybacks on the `/claims` prefix because
  it acts on `KnowledgeClaim.curation_state`, which is correct, but the
  filename "review_queue" makes it sound like the entity-pair queue.
- `kg_review.py` (`/api/kg/review`) is the **entity-pair review queue** for
  PyKEEN merge candidates (#899 Phase D). Distinct workflow, distinct
  schema (`EntityMergeCandidate`).
- `kg_entity_curation.py` (`/api/kg/entity-curation`) is the **manual
  merge/split executor with audit trail** + entity-semantic search. Acts on
  what `kg_review` proposes.

These are three legitimate concerns. The bug is the name `review_queue.py`
when its routes live under `/claims` and operate on claims. Recommend
renaming the file to `claim_curation.py`.

### 3.5 `claim_links` vs `claims` vs `kg_claim_search` vs `kg_claim_analysis`

**Verdict: SEPARATE — all four belong, names are fine.**

- `claims.py` — KnowledgeClaim CRUD primitives.
- `claim_links.py` — KnowledgeClaimLink edges (supports / contradicts /
  refines). Edges deserve their own router because the schema and the
  `/related` traversal are non-trivial.
- `kg_claim_search.py` — semantic claim search (LanceDB embed + similar).
  Distinct from FT search in `search.py`.
- `kg_claim_analysis.py` — contradiction + evidence-chain analytics. Consumes
  links + classifications, not just CRUD.

Could the latter two be one file? `kg_claim_search` is 3 routes,
`kg_claim_analysis` is 2 routes. Five routes + ~500 lines combined would fit
one module under `/api/kg/claims/*` (search + analysis as siblings). Low
priority — current split is defensible.

### 3.6 `mind_palace` vs `notes` vs `annotations`

**Verdict: SEPARATE — three different abstractions.**

- `annotations.py` — *user annotations on a document* (highlights, kind, tag,
  rating; promote-to-claim).
- `notes.py` — *Zettelkasten Notes* (free-standing knowledge atoms with
  bidirectional NoteLink, backlinks).
- `mind_palace.py` — *spatial workspace* (3D rooms, nodes, stacks,
  connections; "method of loci"). Has its own NativeNote inside the spatial
  context.

The `NativeNote` in `mind_palace.py` is suspicious — is it the same as
`notes.py`'s `Note`, just with x/y/z fields? **Read before consolidating:**
`git log -- fichero-engine/src/fichero/spatial_models.py` and grep for
`NativeNote`. If it's truly a different model, leave alone. If it's a
spatial-ised `Note`, the spatial layer should reference Notes by id rather
than carrying its own copy.

### 3.7 `search` vs `search_query` vs `search_explain`

**Verdict: SEPARATE — current organisation is correct; one renaming nit.**

- `search.py` is 1,218 lines and 14 routes — the user-facing surface.
- `search_query.py` is **not a router** (zero `@router` decorators); it's a
  query-parser module imported by `search.py`. It's misfiled under
  `routes/`. Should live in `fichero/search/` or `fichero/parsers/`. Keeps
  appearing in inventories as if it were a route.
- `search_explain.py` is the dev-tier algorithm explanation surface — also
  prefixed `/search` but with tag `search-explain`. Genuinely separate
  concern (debugging the ranker).

**Action:** move `search_query.py` out of `routes/`. It's not a route.

### 3.8 `chains` vs `workflows`

**Verdict: SEPARATE — `chains` is the orchestration layer above `workflows`.**

`workflows.py` is single-workflow CRUD. `chains.py` is *sequential
chaining of workflows* (the `workflows/chaining.py` business module). Two
different artefacts — a Workflow vs a Chain — and the SwiftUI Automation
sidebar surfaces them separately. Names could be clearer (`workflow_chains.py`?)
but the boundary is real.

### 3.9 `actions` vs `triggers` vs `schedules`

**Verdict: SEPARATE — three orthogonal automation primitives.**

- `actions.py` — pre-built action library (workflow snippets / templates).
- `triggers.py` — file-watcher event triggers (something happens on disk).
- `schedules.py` — cron-style schedules (something happens at a time).

These are the three "Automation" sidebar tabs. Correctly split.

### 3.10 `citations` vs `kg_citations` vs `bibliography`

**Verdict: CLARIFY → these *look* identical from filenames; they are not.**

- `bibliography.py` — bibliographic *metadata* on a document (DOI/ISBN
  resolve, BibTeX import/export of the source data).
- `citations.py` — `DocumentCitation` graph (#906): which doc cites which
  doc, inbound/outbound traversal.
- `kg_citations.py` — *citation rendering* (chicago/apa/mla/bibtex strings
  for one or many docs). Mounted at `/api/citations` (path collision with
  `citations.py` — coexists because they use disjoint sub-paths).

The names are misleading: `citations` is a *graph*, `kg_citations` is a
*formatter*. Recommend renaming `kg_citations.py` → `citation_rendering.py`
(or fold its 3 read endpoints into `bibliography.py`, since it's bib export).

### 3.11 `multilingual` — top-level concern or a property?

**Verdict: CLARIFY but LEAVE — it's a top-level *service* surface.**

`multilingual.py` is registered as a core route. Its 6 routes are:
detect language, normalise text, transliterate, cross-language entity search,
cross-language claim search, transliterate-aware lookup. These operate on
*arbitrary text* the client supplies, not on stored documents. So it is not
"a property of documents" in the schema sense — it's a callable service
layer, similar to how `models.py` is a service over LiteLLM rather than a
property of anything. **Leave as-is.** The fact that *language* shows up as
a column on Document, Claim, Entity is orthogonal — the `multilingual`
endpoint set is the service that *populates* those columns.

### 3.12 `entity_inspector` + `document_inspector` mounted under `knowledge-graph` tag

`document_inspector.py` and `entity_inspector.py` mount on `/api/documents/{id}/inspector`
and `/api/entities/{id}/inspector` respectively (correctly), but main.py tags
them with `knowledge-graph` — which makes them appear in OpenAPI under the
KG group, not the documents/entities groups. Cosmetic, but it bites Swift's
generated client grouping. **Verdict: CLARIFY** — change the tag to match
the actual prefix-owner.

---

## 4. Proposed Reorganisation

Minimal moves. Each is independently revertable. Blast radius measured by
`grep -rE "from fichero.api.routes.<module>|routes\.<module>" fichero-engine/`.

### Deletions (highest confidence)

| From | Action | Why | Blast radius |
|---|---|---|---|
| `routes/graph_exploration.py` | DELETE (911 lines) | Not registered in `main.py`. `routes/__init__.py` re-exports it; remove that line. | 1 import in `routes/__init__.py`. |
| `routes/graph_traversal.py` | DELETE (377 lines) | Only consumer is `graph_exploration.py`, deleted above. | 1 import inside `graph_exploration.py`. |
| `routes/predictions.py` | DELETE (420 lines) **after** porting `training-jobs`, `models DELETE`, and `stored/{id}/verify` endpoints into `kg_pykeen.py` / `kg_predictions.py` if the SwiftUI training UI uses them. | Pre-consolidation duplicate. No SwiftUI caller per parity audit. | 1 import in `routes/__init__.py`; 1 entry in `_DEV_ROUTE_SPECS`. |
| `routes/graph_reasoning.py` | DELETE conditionally — first diff its endpoints against `kg_graph.py` and port any unique ones. | Pre-consolidation NetworkX surface. | 1 import in `routes/__init__.py`; 1 entry in `_DEV_ROUTE_SPECS`. |

### Renames

| From | To | Why | Blast radius |
|---|---|---|---|
| `routes/review_queue.py` | `routes/claim_curation.py` | The file mounts under `/api/claims`, transitions `KnowledgeClaim.curation_state`, and is unrelated to the entity-pair queue in `kg_review.py`. Its filename is the single most misleading name in `routes/`. | 2 imports (`__init__.py`, `main.py`). URL paths unchanged. |
| `routes/kg_citations.py` | `routes/citation_rendering.py` | Function is *rendering*, not graph. Removes the head-fake against `citations.py` (which is the actual citation graph). | 2 imports. URL paths unchanged. |

### Extractions (move to non-routes location)

| From | To | Why | Blast radius |
|---|---|---|---|
| `routes/search_query.py` | `fichero/search/query_parser.py` (or similar) | Has zero `@router` decorators. It's a parser, not a route. Misfiled. | 2 importers — `routes/search.py` and `routes/search_explain.py` (both `from fichero.api.routes.search_query import parse_query`). Update those two import paths. |

### Surgery inside files

| File | Change | Why |
|---|---|---|
| `routes/hermeneutics.py` | Delete the `/frameworks/*` (5 routes) and `/interpretations/*` (5 routes) blocks. Keep `/patterns/*`, `/circle-state/*`, `/suggestions`. | `kg_interpretations.py` is the canonical CRUD per `KG_ENDPOINTS.md`. SwiftUI consumes `/api/kg/interpretations/*`. |
| `routes/__init__.py` | Drop the dead module re-exports. | Cosmetic but it confuses linters and IDE jump-to. |
| `api/main.py` lines 757–759 | Change tag for `document_inspector` + `entity_inspector` from `["knowledge-graph"]` to `["documents"]` / `["entities"]`. | Aligns OpenAPI grouping with URL prefix; helps the Swift OpenAPI generator land them in the right service file. |
| `docs/architecture/api/overview.md` lines 92–94 | Remove the `graph_exploration` and `graph_traversal` rows (or document them as deleted). | Doc currently lies about what's mounted. |

**Total moves proposed: 4 deletions, 2 renames, 1 extraction, 4 in-file
edits — 11 atomic changes.** All changes preserve existing URL paths
(except the deletions, which were already serving 404).

---

## 5. CLI / MCP Coverage Gap (post-reorganisation)

Cross-referenced against `agent-work/proposals/cli-swiftui-parity-2026-05-15.md`.
The existing CLI typed coverage is concentrated on `documents`, `artifacts`,
`workflows.list`, `workflow_execution.run/status`, `activity.recent`,
`bibliography.*`. Once the reorganisation above lands, the *domains* with
**no CLI access today** are:

### Tier-1 unlock — touches engine-quality verification

1. **`workflow_execution`** — `run` and `status` exist as `cli-untyped`. Typing
   `ExecuteAcceptedResponse` and `ExecutionStatusResponse` is the single
   highest-value Wave-2 typing target: every other CLI verification flow
   (does the workflow finish? what's the activity log say?) starts here.
2. **`document_inspector`** — `cli-untyped`. The aggregate inspector is the
   one-call surface KG_ENDPOINTS recommends; typing it gives the CLI a
   single command that lets a parent agent verify "does this document have
   claims, entities, annotations?" without N small calls.
3. **`activity`** — `recent` is `cli-untyped`. The full activity feed is the
   only programmatic way to confirm a workflow finished without polling
   `/status` (per MEMORY.md `project_workflow_checkpoint_races_activity`).
4. **`kg_search` / `kg_graph` / `kg_triangulation`** — entirely
   `cli-missing`. Engine-quality work depends on querying the KG; a
   `fichero kg search`, `fichero kg graph centrality`, and
   `fichero kg triangulation` trio unlocks per-library introspection.
5. **`claims`, `entities`, `claim_links`** — primitives with no CLI surface.
   At minimum `entities list / get` and `claims list / get` are needed for
   any human-readable verification of an extraction run.

### Tier-2 unlock — admin / library management

6. `library` (`POST /api/library` bootstrap) — already a `fichero` CLI gap;
   filing on the parity audit.
7. `ingest.file` / `ingest.folder` / `ingest.status` — currently `cli-missing`.
8. `workflows` mutations (create / update / delete / duplicate / import /
   export) — `cli-missing`.
9. `providers` and `models` (set keys, validate, list models) — cli-missing
   admin surface.

### Tier-3 — defer

`kg_pykeen` train/predict, `kg_predictions` apply, `kg_review` accept/reject,
`mind_palace`, `research_*`, `iiif`, `mcp_servers`, `triggers`, `schedules`,
`actions`, `chains`, `model_comparison`, `local_models`, `integrations`,
`orchestration`, `search.views`. These are SwiftUI-side workflows; no CLI
verification gain.

**Recommended Wave-2 typing order** (fastest unlock per hour invested):

1. `workflow_execution.run` / `.status` — type both response models, keep
   the same method signatures.
2. `activity.recent` + `activity.list` — typed `list[ActivityResponse]`.
3. `document_inspector.get` — typed `DocumentInspectorResponse`.
4. `entity_inspector.get` — typed `EntityInspectorResponse`.
5. `kg_search` — typed mixed-hits response.
6. `entities.list` / `entities.get`, `claims.list` / `claims.get` — basic
   typed list/get pair for both primitives.

After (1)–(6) the CLI can run a workflow, watch it finish, and inspect what
it produced — engine-quality verification end-to-end.

---

## 6. Things That Are Correctly Placed (don't churn)

Equally important — the routes that already match the canonical layering:

- **All `/api/kg/*` modules added in the May 12 consolidation** —
  `kg_search`, `kg_claim_search`, `kg_claim_analysis`, `kg_entity_curation`,
  `kg_graph`, `kg_triangulation`, `kg_pykeen`, `kg_predictions`, `kg_review`,
  `kg_mutations`, `kg_inclusion`, `kg_interpretations`, `kg_rebuild`,
  `kg_sparql`. Each has one prefix, one purpose, one Pydantic schema family.
  These are the model the rest of `routes/` should aspire to.
- **`workflow_execution/` package** — already split into
  `core/runner/threads/cache/visualization/schemas`. Good shape.
- **`research_*` split** — `research_agents` is an umbrella, sub-routers
  are `research_crud`, `research_notes`, `research_tools`. Documented in the
  module docstring. Don't change.
- **`provider*` split** — `providers` + `provider_keys` + `provider_models`
  is intentional and matches the SwiftUI provider settings surface.
- **`document_inspector` / `entity_inspector`** — the aggregate single-call
  pattern is exactly what KG_ENDPOINTS says is the right shape; only the
  OpenAPI tag is wrong.
- **`annotations` / `notes` / `projects` / `claims` / `claim_links` /
  `entities`** — clean CRUD primitives, each one Pydantic family per file.
- **`actions` / `triggers` / `schedules`** — three orthogonal automation
  primitives, correctly split, mapped 1:1 to the SwiftUI Automation sidebar.
- **`bibliography` / `citations` / `sources` / `classifications`** — though
  the `kg_citations` rendering surface needs renaming (above), the four
  *separate* bibliographic concerns are correctly distinct files.
- **`workflows.py` + `workflow_execution/` + `chains.py` + `batch.py`** —
  clean separation between *defining* a workflow, *executing* one, *chaining*
  them, and *bulk*-running them.
- **`migrations.py`** — separate concern, correctly isolated.
- **`mcp_tools.py` (always on, /api/mcp/tools) vs `mcp_servers.py`
  (dev-tier, lifecycle)** — different concerns, correct split.

---

## Uncertainty / where I need Daniel's call

1. **`graph_reasoning.py`** — is *registered* (dev-tier, prefix `""`), unlike
   `graph_exploration` / `graph_traversal`. Need to diff its 9 endpoints
   against `kg_graph.py`'s 12 endpoints and confirm full coverage before
   deletion. `git log -- fichero-engine/src/fichero/api/routes/graph_reasoning.py`
   should tell us why it survived the May 12 consolidation.
2. **`predictions.py` unique features** — `/training-jobs/*` and
   `/stored/*/verify` are not present in `kg_pykeen.py`. Need to confirm
   whether the SwiftUI PyKEEN settings UI uses these (likely #377 follow-up)
   before deletion. `git log -- fichero-engine/src/fichero/api/routes/predictions.py`.
3. **`hermeneutics.py` duplicate CRUD** — need to grep the SwiftUI client to
   confirm zero callers of `/api/hermeneutics/frameworks` and
   `/api/hermeneutics/interpretations`. If anything calls them, the
   pruning becomes a co-ordinated SwiftUI + backend change, not a backend-only
   one. Search: `grep -rE "/api/hermeneutics/(frameworks|interpretations)" fichero/fichero/`.
4. **`mind_palace.NativeNote` vs `notes.Note`** — same Pydantic shape with
   spatial fields, or a different model? Decide whether spatial Notes
   should reference `notes.Note` by id.
