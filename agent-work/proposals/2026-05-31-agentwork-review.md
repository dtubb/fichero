# agent-work/ Review — 2026-05-31

Read-only systematic review of agent-work/ (101 files). Files dated 2026-05-31
(reality-check-*, plan-*, preface-*) are excluded per instructions — they are
current working docs.

---

## Section A — NEW ISSUES

Issues proposed here are NOT already tracked in the open GitHub issue list.
The cross-check excluded: #900 (triangulation), #903 (authority), #916
(user-entities), #922 (hermeneutics), #924 (citation roles), #1124
(predicate vocab), #1187 (source-tied notes), #1203 (KG temporal/geo
filtering), #1266/#1267 (evidential model + timeline/map — evidential model
is already merged per the 2026-05-26 doc), #1277/#1278/#1279 (book structure
extraction — already filed per the 2026-05-27 doc), #1287 (workflow
regression harness — already filed), #1297 (Mind Palace Phase 2 — already
filed), #1156 (graph-RAG chat — already filed, plan written today).

### A1 — KG communities / Louvain / Leiden clustering endpoint
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-13-kg-architecture-review.md §3 Missing; 2026-05-13-scaling-review.md  
**Rationale:** `GET /api/kg/communities` (Louvain clustering of entities) is
listed as a missing backend endpoint in the 2026-05-13 architecture review.
networkx supports Louvain; the graph is already rebuilt on each extraction.
The existing `kg_graph.py` exposes centrality and neighborhood but not
communities as a clean endpoint. This is the "zoom-out" view described in the
KG visualization plan and is a prerequisite for a meaningful KG overview when
the library exceeds ~100 entities.  
**Acceptance:** `GET /api/kg/communities` returns entity clusters with
community_id, member_entity_ids, and a computed label. Capped at meaningful
libraries (>= 50 entities). Backed by networkx Louvain.  
**Not a dupe of:** #1203 (which is about temporal/geo filtering, not cluster
structure).

### A2 — SPARQL query endpoint: `POST /api/kg/sparql`
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-13-kg-architecture-review.md §3 Missing  
**Rationale:** rdflib is integrated and SPARQL-queryable via `kg/triples.sparql()`,
but there is no clean HTTP endpoint. The architecture review notes this as a
small gap (~20 min of work). `graph_exploration.execute_graph_query` is partial.
A clean SPARQL endpoint is the W3C-standard Cypher equivalent — critical for
power-user querying and for the Research workflow.  
**Note:** the 2026-05-28 backend-not-in-ui-audit already listed `kg_sparql.py`
as built and release-tier, with no Swift caller. This is the issue to add a
clean HTTP contract + Swift exposure.  
**Acceptance:** `POST /api/kg/sparql` accepts a SPARQL SELECT query + optional
timeout; returns rows as JSON. Size cap enforced. Not exposed in UI by default
(power-user tool), but documented.

### A3 — Entity bio / description generation from SVO statements
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-13-kg-rebuild-plan.md §Stage 2 ("entity.description"), 
2026-05-13-kg-ux-wireframes.md (entity card "About" section), 
2026-05-13-kg-architecture-review.md §4 Stage 6  
**Rationale:** Daniel explicitly wants entities to have a biography synthesized
from their SVO statements and cross-document extracts. The 2026-05-13 docs
describe this as "compose biography action that turns claims into prose" (bug
#989). The `kg_render.py` module exists (release-tier, no Swift caller per the
2026-05-28 audit) and is exactly where this belongs. There is no issue tracking
the "generate entity bio from claims via LLM" feature as a first-class action.  
**Acceptance:** `POST /api/kg/entities/{id}/bio` runs an LLM over the entity's
SVO claims + cross-document extracts and writes a prose `description` back.
Surfaced in the entity card as "Generate bio" button; result persists as
`entity.description`.

### A4 — Oxigraph as rdflib replacement (0.1.0 scalability)
**Milestone:** Infrastructure  
**Source:** 2026-05-13-scaling-review.md §Bottleneck 3  
**Rationale:** The scaling review explicitly identifies rdflib as the bottleneck
past ~500K triples (heap thrash, OOM risk). Oxigraph is a Rust-backed
drop-in SPARQL-compatible replacement: ~10x faster, 5x less memory.
`pip install oxigraph`; thin adapter. This is a deferred 0.0.3/0.1.0 task in
the review doc, not yet filed anywhere.  
**Acceptance:** rdflib Graph replaced by Oxigraph store; all existing
kg_sparql.py + kg/triples.py tests pass unchanged; performance verified on
a synthetic 100K-triple corpus.  
**Milestone:** Infrastructure (0.1.0)

### A5 — Claim entity_ids join table (replace JSON list)
**Milestone:** Infrastructure  
**Source:** 2026-05-13-scaling-review.md §Bottleneck 2  
**Rationale:** `entity_ids` is stored as a JSON list on `KnowledgeClaim`.
DuckDB cannot index this natively, so "claims for entity X" scans the full
claims table. The scaling review identifies this as the prerequisite for the
1M-entity aspirational tier. The fix is a `claim_entities(claim_id, entity_id)`
join table. Filed as a 0.0.3 candidate in the scaling review but not yet a
GitHub issue.  
**Acceptance:** new `claim_entities` join table, migration from JSON list on
first access (or rebuild), `GET /api/claims?entity_id=X` uses the join index.
KG extraction write path updated. Unit tests cover the join.  
**Milestone:** Infrastructure (0.1.0, not urgent until 50K+ claims)

### A6 — Hermeneutics / Interpretations surface in SwiftUI
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (hermeneutics listed as no
Swift caller), 2026-05-13-kg-architecture-review.md §1.4  
**Rationale:** `/api/hermeneutics` and `/api/kg/interpretations` are
release-tier, fully implemented backend routes with no Swift consumer. The
`InterpretiveFramework` + `Interpretation` + `PatternInstance` models are
built. Daniel's interest in "programmatic hermeneutics" is explicitly noted in
the task brief, and #1124 tracks the predicate vocabulary. This is the issue
to wire the hermeneutics surface into the entity / claim inspector.  
**Acceptance:** Interpretive Framework picker in the KG inspector; applying a
framework filters claim display by its interpretive lens. At minimum, read-only
display of frameworks and interpretations linked to a claim.  
**Note:** does NOT duplicate #922 (which is about the overall hermeneutics
milestone direction). This is the specific Swift wiring issue.

### A7 — KG review queue surfaced in OntologyBrowser
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (`kg_review.py` no Swift caller)  
**Rationale:** `kg_review.py` exposes an entity-match review queue (ambiguous
merge candidates, probabilistic match scores). It is release-tier and has no
Swift consumer. Entity deduplication is a known pain point. The review queue
is exactly the tool to surface uncertain matches for human curation.  
**Acceptance:** "Review Queue" tab or badge in OntologyBrowser showing
ambiguous entity matches with merge/reject actions. Feeds `kg_entity_curation`
merge/split endpoints already wired.

### A8 — KG mutations / audit history panel
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (`kg_mutations.py` no Swift caller)  
**Rationale:** `kg_mutations.py` exposes undo history for KG edits. This is
the undo / rollback surface for destructive entity curation decisions. No
Swift consumer exists. Related to but distinct from #1090 (artifact undo).  
**Acceptance:** Entity curation actions (merge, split, delete) show an undo
button pulling from `kg_mutations.py`; audit log accessible in a collapsible
section of the entity inspector.

### A9 — Draft paragraph / "Render" action from entity/claim views
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (`kg_render.py` no Swift caller)  
**Rationale:** `kg_render.py` is a release-tier module that can draft prose
from KG data. Combined with A3 (entity bio), this is the "generate explanation"
CTA. No Swift caller.  
**Acceptance:** "Draft paragraph" action on entity detail and claim inspector,
calling `kg_render.py` and displaying the result inline for copy/paste.

### A10 — Cross-source corroboration UI (triangulation panel)
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (`kg_triangulation.py` no
Swift caller)  
**Rationale:** `kg_triangulation.py` is a release-tier corroboration engine
(multi-source claim agreement). #900 tracks triangulation as a backend feature.
This is the specific issue to wire the triangulation results into the claim
inspector as a "Corroboration" section showing how many sources agree on a claim.  
**Not a dupe of:** #900 (which is the backend feature); this is the Swift UI surface.

### A11 — KG rebuild / repair action in OntologyBrowser
**Milestone:** KG & Hermeneutics  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (`kg_rebuild.py` no Swift caller)  
**Rationale:** `kg_rebuild.py` is a release-tier endpoint that re-materializes
the rdflib + networkx + PyKEEN derived views. If a user suspects stale KG state,
there is no in-app way to trigger a rebuild. The rebuild is slow (background
task), so it needs a progress indicator.  
**Acceptance:** "Rebuild KG" button in OntologyBrowser or advanced settings;
calls `POST /api/kg/rebuild`; shows background progress badge.

### A12 — Notes / backlinks in Document Inspector and entity inspector
**Milestone:** Library & Reading Surface  
**Source:** 2026-05-28-backend-not-in-ui-audit.md (notes.py — no Swift caller,
highest-priority #1 in that doc's recommendations)  
**Rationale:** `notes.py` is a release-tier module with full CRUD for
per-document and per-claim free-text notes. There is no Swift consumer.
Notes/backlinks is the most direct way to make Fichero feel like a
research workspace rather than only a document browser.  
**Acceptance:** "Notes" section in Document Inspector; "Add note" button on
claim cards and entity details; notes searchable via `/api/search`.

### A13 — AppDatabase raw-SQL DELETE cleanup (#1112 companion)
**Milestone:** Infrastructure (Developer Experience)  
**Source:** agent-work/audit-1112-raw-sql-bypasses.md  
**Rationale:** The 2026-05-17 audit found 5 raw SQL DELETE statements in
`app_db.py` bypassing the Pydantic-typed write path. #1117 fixed 3 in
`activity_store.py` and `cache.py`. The 4 AppDatabase methods
(delete_provider, delete_setting, delete_model, delete_mcp_server) still need
the same treatment. Each is a single-function fix following the #1117 pattern.  
**Acceptance:** All 4 raw DELETE paths replaced with typed wrapper methods;
unit tests cover each delete path.  
**Note:** Audit report at agent-work/audit-1112-raw-sql-bypasses.md is the
implementation spec.

### A14 — networkx graph LRU cache per library (scaling fix)
**Milestone:** Infrastructure  
**Source:** 2026-05-13-scaling-review.md §Bottleneck 1  
**Rationale:** `build_full_graph` is called on 18 endpoint handlers and
rebuilds the graph from a full DuckDB scan on every request. The fix is a
library-scoped LRU cache (keyed by library path + last_claim_updated_at),
invalidated on any claim write. ~30 lines. The scaling review estimates this
is required before the 400-case tier (50K claims) is usable — without it,
neighborhood/community/PageRank calls take 3-5 seconds each.  
**Acceptance:** `build_full_graph` wrapped in an LRU cache; cache invalidated
on claim write; demonstrated sub-500ms for a 10K-claim library.

### A15 — Mind Palace backend `GET /api/mind_palace/library_snapshot` endpoint
**Milestone:** Mind Palace  
**Source:** agent-work/proposals/2026-05-30-mindpalace-phased-plan.md §P1  
**Rationale:** The phased plan for Mind Palace "whole library" view requires a
new backend endpoint (`GET /api/mind_palace/library_snapshot`) that returns
nodes for every Document + KnowledgeEntity and edges from every KnowledgeClaim.
This is the data plumbing for Phase 1 of Mind Palace as Spatial Library
(#1343). The endpoint is explicitly called out as the first child ticket in
the P1 plan. Not yet a GitHub issue.  
**Acceptance:** `GET /api/mind_palace/library_snapshot?include_children=false`
returns nodes (one per Document + KnowledgeEntity) and edges (one per
KnowledgeClaim, predicate → link_subtype). Paginatable.

### A16 — Graph-RAG chat: extract BFS helper from neighborhood (cleanup PR)
**Milestone:** Chat  
**Source:** agent-work/proposals/2026-05-31-plan-graph-rag-chat.md §PR 1  
**Rationale:** The graph-RAG chat plan (today's architecture doc for #1156)
calls for extracting the BFS inner loop from `kg_graph.py::neighborhood` into
a shared `_bfs_claims` helper — a cleanup prerequisite before the main
graph-RAG PR. This is a small, safe refactor (behavior unchanged, just
extracted). The plan identifies it as PR 1 of 3. Not yet a sub-issue of #1156.  
**Acceptance:** `_bfs_claims(db, entity_ids, hops)` extracted; `neighborhood`
delegates to it; existing neighborhood tests still pass; unit test covers the
helper directly.

### A17 — Map import: sidecar `.iffy.json` → Document metadata
**Milestone:** Importers  
**Source:** agent-work/proposals/maps-import-survey-2026-05-15.md  
**Rationale:** Daniel's southern-Colombia map archive has 2,266 images/PDFs
and 497 `.iffy.json` sidecar files with metadata. The survey (2026-05-15)
scoped what it would take to import these, with sidecar metadata landing on
the `Document`. Not yet a GitHub issue and not tracked anywhere in the open
backlog. This is a concrete data-import task with a well-defined input shape.  
**Acceptance:** Fichero ingest can read `.iffy.json` sidecars alongside images
and populate `Document.source_metadata` from them; 2133 JPG images from the
maps archive importable.

---

## Section B — NEW MILESTONE PROPOSALS

### B1 — Security milestone
**Verdict:** PROPOSE as a future milestone, but evidence in agent-work/ is thin.
The 2026-05-13 docs mention SPARQL query timeouts and result-size caps as
security concerns. The 2026-05-14 workflow execution architecture doc mentions
SSRF guard in research tools (`_safe_http_get`). The 2026-05-28 backend audit
mentions keeping orchestration/agent-write policy gated (#1151). #969 tracks
"harden the local token path." There is no dedicated security audit doc in
agent-work/ — the security surface identified is:
- SPARQL endpoint: query timeout + result size caps (A2 above)
- SSRF guard in research web-fetch tools (already implemented, needs tests)
- Token path hardening (#969)
- Agent write policy / human-in-loop (#1151 / planned 0.1.0 issue)
- Remote backend auth (Tailscale / mTLS, #969)

**Proposal:** a **Security** milestone is warranted but should be scoped
around 0.1.0 timing (when remote access and multi-user are needed). The
concrete items above can seed it. Do NOT create it now — too few issues
to justify a milestone before 0.1.0 planning.

### B2 — KG Visualization milestone
**Verdict:** PROPOSE as a sub-milestone of KG & Hermeneutics, not a
separate top-level milestone.
The 2026-05-13-kg-ux-wireframes.md and 2026-05-26-kg-evidential-model.md
together define a complete KG visualization suite: focus-neighborhood graph
(already underway), Timeline view (EvidentialDateRange → SwiftUI Canvas spans),
MapKit map (EvidentialPlace → map overlays), and whole-corpus UMAP scatter
(deferred). These are interconnected — they share a single
`selectedClaimId/entityId/timeFilter/placeFilter` state. Rather than a
separate milestone, these should be issues within KG & Hermeneutics, gated
on the evidential model (#1266 — reportedly merged) and the KG API read
surfaces (#1267 or equivalent).

The natural grouping of open visualization work:
1. Focus-neighborhood graph phase 2 (predicate filters, edge labels) — link
   to existing issues under KG & Hermeneutics.
2. KG Timeline view — new issue (not yet filed; #1203 is temporal *filtering*,
   not a timeline renderer).
3. KG MapKit view — new issue (maps with EvidentialPlace geometry).
4. A2 (SPARQL console, power-user).

**Proposal:** file two new issues:
- "KG Timeline view: EvidentialDateRange → SwiftUI Canvas lane renderer"
  (SwiftUI, M, feeds from #1266 data; aligns with #1267 if that covers UI)
- "KG MapKit view: EvidentialPlace → MapKit overlays" (SwiftUI, M)

These should be children of whatever tracks #1267, not a new milestone.

### B3 — Programmatic Hermeneutics milestone
**Verdict:** Already exists as "KG & Hermeneutics" milestone. Do not create a
new one. The concrete features Daniel described map directly to existing or
proposed issues:
- Quotes/provenance/certainty/triangulation → #900 (corroboration), #903
  (authority), #1266 (evidential model with basis/confidence), A10 (triangulation UI)
- Ontology on quotes / controlled predicate vocab → #1124
- Entity bio from SVO → A3 (proposed above)
- Cross-document provenance → A6 (hermeneutics surface)

The KG & Hermeneutics milestone already contains the right container.
The gap is that several of these issues lack SwiftUI counterparts (A6, A10, A3).

---

## Section C — STALE FILES TO DELETE

Files that are superseded, one-off audit outputs that have been acted on, or
pure historical planning docs with no forward value. Daniel should execute
these deletions.

### C1 — `agent-work/SOURCES-IMPLEMENTATION-NOTES.md`
**Reason:** Documents implementation of `sources.py` routes for issue #364 —
noted as having route-registration bugs and pending decisions. Issue #364 is
long closed (0.0.2 shipped). The "known issues" listed are resolved. No future
reference value.

### C2 — `agent-work/proposals/plan-review-2026-04-01.md`
**Reason:** An April 2026 code-review of an early KG API plan with 7 "critical
issues" (endpoint structure conflicts, missing Swift models, no migration
strategy). All of these concerns were resolved through the 0.0.2 milestone work
(OpenAPI codegen, model consolidation, no-migration rule). Pre-dates the current
architecture; the concerns it raises are either fixed or irrelevant. Historical
only.

### C3 — `agent-work/proposals/sidebar-review-2026-04-17.md`
**Reason:** A hookup audit of `SidebarItemRow+DropHandlers.swift` and related
files from April 2026, identifying dead code (`handleInsertBetweenChildren`,
`SidebarServices`, etc.). This review was done on a much earlier version of the
sidebar that has since been substantially reworked (#580 and later). The
specific dead-code findings are either already removed or obsolete. No actionable
forward value.

### C4 — `agent-work/proposals/sidebar-robustness-plan.md`
**Reason:** Companion to the sidebar review above; appears to be a robustness
plan from April 2026. Same era and same obsolescence risk as C3. Check if any
items remain open before deleting, but likely superseded by the 0.0.2 KG/UX
overhaul.

### C5 — `agent-work/proposals/opus-status.md` + `sonnet-status.md`
**Reason:** These appear to be agent status snapshots from a specific session.
No durable content — agent status is transient. Safe to delete.

### C6 — `agent-work/proposals/fichero-cli-smoke.md` + `fichero-cli-status.md`
**Reason:** CLI smoke test outputs and a CLI status snapshot from the fichero-cli
development loop. The CLI has shipped and issues #1348 etc. track remaining
work. These are session artifacts, not durable documentation.

### C7 — `agent-work/proposals/duckdb-write-audit-2026-05-15.md`
**Reason:** The v1 DuckDB write audit; superseded by `duckdb-typed-audit-2026-05-15-v2.md`
(the v2 audit). If v2 is kept, v1 is redundant.

### C8 — `agent-work/proposals/engine-quality-2026-05-15.md`
**Reason:** A one-off quality comparison run from 2026-05-15 that found a bug
(Catalogue workflow stopping after transcribe; F2 — provider string inconsistency).
Both bugs are now fixed (the transcribe/extract issue was #1285-era work). The
audit served its purpose. Stale run artifact.

### C9 — `agent-work/proposals/2026-05-26-pdf-extraction-fidelity.md`
**Reason:** A single-session PDF fidelity audit run against specific PDFs in
`~/Desktop/PDFS`. Belcher 2019 stalled; others showed 0 KG entities (pre-#1285
fix). The #1285 fix is merged. This was a one-off run artifact, not a design
document. No forward value.

### C10 — `agent-work/proposals/2026-05-27-kg-extraction-quality-audit.md`
**Reason:** The post-#1285 extraction quality audit that verified 38 entities
and 45 claims are written. Served its purpose as a verification of the fix.
Filed #1295 and #1296 as follow-up issues. The verification is done. Historical
run artifact.

### C11 — `agent-work/proposals/cli-renderer-design-1141.md` + `cli-swiftui-parity-2026-05-15.md`
**Reason:** CLI renderer and CLI/SwiftUI parity design docs from the fichero-cli
development phase. The CLI is built. If the specific renderer designs are not
referenced by any open issues, these are historical planning docs.

### C12 — `agent-work/proposals/four-agent-worktree-topology.md`
**Reason:** A 2026-05-25 decision document on the 2-extra-worktree shape
(fichero-codex + fichero-pi). The decision is made and the worktrees are
set up. The document's value was in capturing the reasoning at the time; the
topology is now stable institutional knowledge in MEMORY.md/STATE.md. Safe
to delete.

### C13 — `agent-work/worker-status.md`
**Reason:** Backend worker status tracker for rounds 1-4 of the 0.0.2
autonomous loop. All round 1-3 items are checked done. Round 4 partially done.
This is a historical session tracker — open items should be tracked in GitHub
issues, not here. The ongoing status belongs in STATE.md.

### C14 — `agent-work/verification-gate-handoff.md`
**Reason:** A 2026-05-20 handoff doc written at the context-budget limit.
The update from 2026-05-21 says "BASELINE IS AT ZERO FAILURES." The handoff
was completed. Historical session artifact.

### C15 — `agent-work/HISTORY-worker.md`
**Check before deleting:** likely a historical log of worker sessions. If it
contains decisions not captured in MEMORY.md, preserve. If it's a pure log,
delete.

### C16 — `agent-work/queue.md`
**Check before deleting:** if this is an active task queue, keep. If it
mirrors the GitHub issue list and is stale, delete.

### C17 — `agent-work/proposals/2026-05-14-workflow-execution-architecture.md`
**Keep with note:** This is a substantial architectural proposal for workflow
execution (the DBWriter + thread-per-workflow model). DBWriter was built
(`db_writer.py` with unit tests). The proposal's Phase 2-4 scale path is not
yet implemented. Keep as a reference for the 0.0.3 scale work, but note it is
partially implemented.

### C18 — `agent-work/proposals/module-organization-2026-05-15.md`
**Reason:** A 2026-05-15 audit of route module organization against the
canonical layering docs. The KG consolidation it discusses (the `1587a1b6`
namespace consolidation) is done. If the audit's recommendations are captured
in architecture docs, this is historical.

### C19 — `agent-work/0.0.3-0.1.0-backend-issues.md`
**Reason:** This document was the source for creating 21 GitHub issues (#419-#440).
The ISSUES-CREATED.md confirms those issues are created. The source document
is now redundant — GitHub is the source of truth. Safe to delete once Daniel
confirms the GitHub issues are correct.

---

## Section D — NOTABLE TOOLS / FRAMEWORKS / VISUALIZATION IDEAS

Ideas extracted from the agent-work/ corpus that are not yet in GitHub issues
but align with Daniel's stated interests. For Daniel's awareness during roadmap
planning.

### D1 — Oxigraph (SPARQL backend replacement)
**Source:** 2026-05-13-scaling-review.md  
Rust-backed SPARQL store, drop-in rdflib replacement. ~10x faster, 5x less
memory. `pip install pyoxigraph`. Relevant when libraries exceed ~500K triples
(the 1M-entity aspirational tier). Low adoption risk — thin adapter pattern.
See A4 above.

### D2 — Sigma.js / Graphviz / server-side layout
**Source:** 2026-05-13-kg-architecture-review.md §2 "Visualize the whole thing"  
For large KG visualization, server-side force-directed layout (positions cached
server-side, client just renders (x, y) tuples) eliminates client-side physics
entirely. The review cites matplotlib / Graphviz / sigma.js layout libraries
as the backend compute option. Not currently used in Fichero but relevant if
the focus-neighborhood view needs to scale past ~500 nodes. Sigma.js is a
JavaScript graph renderer that could underpin the WebKit knowledge pane (#1228).

### D3 — UMAP / t-SNE 2D scatter for "shape of corpus"
**Source:** 2026-05-13-kg-architecture-review.md §4 Stage 6  
"For 1M entities specifically: a 2D scatter (no edges) of UMAP/t-SNE
projections of the entity vectors gives the 'shape of the corpus' without any
graph rendering work." This is the visualization approach for the whole-corpus
view — a Metal-accelerated point cloud colored by entity type, sized by
claim-count. LanceDB already stores per-entity vectors. The missing piece is
a server-side UMAP job + a cached `(entity_id, x, y)` projection endpoint.
Highly relevant to the "KG map" visualization Daniel asked about.

### D4 — Tinderbox Hyperbolic / Neo4j Bloom focus-neighborhood as the UX model
**Source:** 2026-05-13-kg-ux-wireframes.md  
The architecture review and wireframes explicitly model the focus-neighborhood
view on Tinderbox Hyperbolic and Neo4j Bloom Explore: focus entity at center,
neighbors radially, edges labeled with predicate verbs, checkbox predicate
filters at the bottom. This is already the design intent for the KG graph
view. Worth naming explicitly in the relevant GitHub issues.

### D5 — PyKEEN link prediction for "what is this entity likely connected to?"
**Source:** 2026-05-13-kg-architecture-review.md §1.2  
PyKEEN is already integrated (TransE / RotatE embeddings, `/api/kg/pykeen/train`
+ `/predict`). The key UX idea: "Predictions last trained 4 hours ago —
Re-train?" inline banner. The training is slow (minutes for small libraries,
hours for large), so it must be a background task with status visibility.
The `kg_pykeen.py` is release-tier but has no Swift consumer (#1288 audit).
Wiring the training trigger + stale-model banner is the UX work.

### D6 — phyllotaxis (golden-angle spiral) layout for initial Mind Palace placement
**Source:** agent-work/proposals/2026-05-30-mindpalace-spatial-library.md  
The Mind Palace Phase 1 plan uses a deterministic client-side phyllotaxis
layout (golden-angle spiral, seeded by entity ID hash) as a placeholder before
backend layout authority is implemented. Deterministic means same input → same
positions, so re-opens stay stable. Good interim approach; the comment in the
plan explicitly marks it as a TODO for backend takeover in Phase 4.

### D7 — AnchorEntity(.plane) for iPhone tabletop AR
**Source:** agent-work/proposals/2026-05-30-mindpalace-spatial-library.md,
2026-05-30-mindpalace-phased-plan.md  
The cross-platform RealityKit renderer design is well-thought-out: Phase 1
(Mac) uses PerspectiveCamera; Phase 3 (iPhone AR) swaps in
AnchorEntity(.plane(.horizontal)) for tabletop placement; Phase 4 (Vision Pro)
drops the camera (system manages). The critical insight: `InputTargetComponent`
+ `targetedToAnyEntity()` + `HoverEffectComponent` work identically on all
three platforms — no platform-specific gesture code needed. The Phase 1 work
must fix the NSColor → Material.Color issue now to keep the iOS/visionOS path
open (blocking issue identified in 2026-05-30-post-collapse-review.md).

### D8 — Book structure: TOC → chapter/section range model (no re-parenting)
**Source:** agent-work/proposals/2026-05-27-book-structure-extraction.md  
The book structure design (#1279) is careful about a constraint not found
elsewhere: do NOT re-parent page Document rows under chapter rows, because
pages have `path=None` and artifacts live on the parent. Model structure as
sequence ranges, not tree mutations. This is a non-obvious architectural
decision that should be in MEMORY.md for any agent touching the book structure
feature.

### D9 — EvidenceBasis enum: asserted / source_anchored / inferred
**Source:** agent-work/proposals/2026-05-26-kg-evidential-model.md  
The evidential model introduces a three-way basis taxonomy: `asserted`
(explicitly stated in source text), `source_anchored` (bounded from source
document metadata, not from the claim text), `inferred` (derived by model
from context). This is a key conceptual distinction for provenance — a date
inferred from a document's publication date is *not* the same as a date
stated in the claim text. The `source_anchored` basis should display
differently in the UI (hatched/ghosted rendering vs. solid). Whether this
model is fully implemented in the current codebase (post-#1266 merge) needs
verification.

### D10 — Attribution chain: asserter → reporter → recorder → source_document
**Source:** agent-work/proposals/2026-05-26-kg-evidential-model.md  
The evidential model proposes an ordered `AttributionStep` chain keeping
"who said it" separate from "who reported/recorded it." This is directly
relevant to Daniel's hermeneutics interest — an LLM-extracted fact from a
colonial source that was itself reported by a colonial administrator is NOT
the same as a direct assertion. The chain makes provenance explicit. This
is part of the #1266 schema (whether fully implemented or still proposal-stage
needs verification by checking the current `knowledge_models.py`).

---

## Meta-notes for Daniel

**Files explicitly excluded from this review** (current working docs, not
stale): all `2026-05-31-reality-check-*.md`, `2026-05-31-plan-*.md`,
`2026-05-31-preface-kg-comparison.md`, `2026-05-30-milestone-audit-*.md`,
`2026-05-30-mindpalace-*.md`, `2026-05-30-post-collapse-review.md`,
`2026-05-30-issue-triage.md`, `2026-05-30-closed-issue-refile-log.txt`,
`HISTORY-worker.md` and `queue.md` (check before deleting),
`digest.md` (active working digest — keep),
`2026-05-14-workflow-execution-architecture.md` (keep — partially
implemented, Phase 2-4 still pending),
`2026-05-27-feature-enablement-researcher-mindpalace.md` (keep — architectural
reference for the Researcher + Mind Palace enablement work),
`2026-05-27-book-structure-extraction.md` (keep — design spec for #1277/#1278/#1279),
`2026-05-26-kg-evidential-model.md` (keep — design spec for #1266/#1267).

**The `classify_issues.py` and `kg_audit_runner.py` scripts** in agent-work/
root: check if these are still referenced. If they were one-off tools used
during 0.0.2, consider moving to `scripts/` or deleting.

**`dispatch/` subdirectory:** all four files are dated 2026-05-30 (current
working batch docs for the manager's dispatch system). Not stale — keep.

**`handoff/2026-05-30-manager-resume.md`:** active session handoff — keep.
