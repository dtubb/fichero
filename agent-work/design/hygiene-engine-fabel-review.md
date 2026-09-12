# Engine & Python hygiene: fabel review

**Review date:** 2026-07-25  
**Branch reviewed:** `integration` at `ed66d9a77`  
**Criterion:** make the engine legible to a newcomer before the repository opens, without speculative rewrites. This is a read-only plan; no issue state was changed.

## Executive finding

The original reorganization is largely implemented. The current readability problem is no longer “50 loose modules and 89 flat routes”; it is the compatibility layer left behind after those moves. The source now has domain packages (`api/routes/{ai,auth,citation,claim,document,entity,ingest,interpretation,kg,library,mcp,research,search,system,workflow}`, plus `db`, `execution`, `importers`, `knowledge`, `llm`, `models`, `security`). What a newcomer sees first, however, is **91 exact `sys.modules` alias shims** plus **15 simple star-import shims** (106 compatibility files total). Of the exact aliases, **84 are old flat route paths** and seven are non-route aliases. Removing these repoint-first, in domain-owned batches, is the largest immediate hygiene win.

## 1. Current structural picture

### Package topology

The intended package map is visible and substantially coherent:

- API adapters: `fichero/api`, with implementation routes in the domain directories listed above.
- persistence: `fichero/db` (`app.py`, `embeddings.py`, `library_bootstrap.py`, `manager.py`, `storage.py`, `storage_snapshots.py`).
- pipeline execution: `fichero/execution/{batch,chaining,runner}.py`, alongside workflow definitions/tools in `fichero/workflows`.
- import boundary: `fichero/importers`.
- knowledge: implementation in `fichero/knowledge`, HTTP surface in `api/routes/kg`, with legacy `fichero/kg` aliases still present.
- model/provider infrastructure: `fichero/llm`, `fichero/models`.
- authentication/transport: `fichero/security` and `fichero/api/auth.py`.

This proves the broad direction of #2566, #2569 and #2594 is already in the tree. Remaining work is consolidation and cycle breaking, not another directory redesign.

### Dependency cycles: 4

`get_dependency_cycles` reports four strongly connected components:

1. **Integrations cycle (4 files):** `integrations/base.py`, `bookends.py`, `devonthink.py`, `tinderbox.py`. Provider implementations and their base/registry know about each other.
2. **Engine mega-cycle:** the large SCC crosses `actions`, `api/main.py`, route packages, `db`, `execution`, `importers`, `knowledge`, `llm`, `models`, `security`, and `workflows`. It includes compatibility paths such as `api/routes/activity.py`, `api/routes/claims.py`, `api/routes/kg_entity_curation.py`, and `workflows/batch.py`; deleting/repointing shims will shrink it, but the remaining cycle must be re-measured rather than assumed fixed.
3. **Local inference cycle (2 files):** `llm/local_inference.py` ↔ `llm/mlx_model_store.py`.
4. **Loader cycle (4 files):** `loaders/__init__.py`, `document_loader.py`, `pdf_loader.py`, `unified.py`. `loaders/__init__.py` already uses lazy PEP 562 exports to avoid eager startup imports, but the import graph remains cyclic.

### God modules / hotspots

The useful “god module” evidence is symbol-level, not merely file size. `get_repo_health` identifies:

- `workflows/tools/vision_base.py::process_vision` — cyclomatic complexity **301**, churn 59.
- `workflows/tools/extractors.py::_write_kg_rows` — complexity **290**, churn 57.
- `vision_base.py::process_vision._process_file` — complexity **210**.
- `workflows/tools/extract_all.py::extract_all` — complexity **143**.
- `workflows/tools/extractors.py::_run_extractor` — complexity **139**.

The old umbrella modules are also architectural nexus points: `models/__init__.py` anchors the largest tectonic plate and `llm/__init__.py` anchors the second. They intentionally re-export domain types/functions; new code should import the owning submodule directly, and shim removal should precede any attempted split.

### Tectonic map and drifters

`get_tectonic_map` finds eight plates, but two nexus plates dominate: one anchored by `models/__init__.py` (719 files) and one by `llm/__init__.py` (352 files). The reported hundreds of “drifters” are mostly source-vs-test coupling and therefore are **not** a literal move list. Actionable drifters are the compatibility paths whose physical directory no longer matches ownership:

- flat `api/routes/*.py` files that belong to a domain package (84 files),
- `api/routes/workflow_execution/runner.py` belonging to `execution/runner.py`,
- `workflows/{batch,chaining}.py` belonging to `execution/`,
- `citations/renderer.py` and `kg/*.py` belonging to `knowledge/`,
- the reciprocal-looking aliases `db/core.py`, `llm/core.py`, `models/core.py`, and model aliases under `knowledge/`.

Do not move files based solely on the tectonic drifter label; use it to confirm that these already-declared aliases are architectural leftovers.

## 2. Triage of the 10 open milestone issues

| Issue | Verdict | Source-grounded reason / rewrite |
|---|---|---|
| **#3759 audit registry/debug/workflow stream ownership** | **CLOSE-AS-DONE** | The decisions are now encoded. `GET /api/registry/open` is a live-registry diagnostic with tests in `tests/unit/test_library_registry.py` and remains Swift-unwired in `ui_wiring_allowlist_swiftui.json`. `/api/storage/debug/{doc_id}` is explicitly CLI-allowlisted as debug-only. The workflow stream is no longer unwired: `fichero/__main__.py:2189` calls `request_stream`, `tests/unit/test_cli_commands.py:964` verifies it, and `workflow_execution/core.py` returns its canonical URL. The stale allowlist prose saying the CLI polls should be corrected as part of the shim/contract cleanup, not kept as an ownership question. |
| **#3752 collection everywhere** | **KEEP** | Not done. `api/main.py:1457` registers `/api/folders`; `api/routes/document/folders.py` exposes `/{entity_type}/folders`; `DocType.folder` remains pervasive in DB, importers, routes and workflows. This is a semantic API + persisted-value migration, explicitly separate from mechanical hygiene. Keep as one serialized cross-stack batch after shim cleanup. |
| **#3740 inverse actions for 16 engine mutations** | **REWRITE** | The inventory is stale. Evidence of completed action routing includes `content_representations.py:create_revision → registry.invoke`; image action functions (`_action_crop`, `_action_split_image`, `_action_unsplit_image`) returning `ChangeSpec`; `batch_apply_image_operation` and `undo_batch_image_operation`; and chat workspace endpoints invoking the registry. Rewrite as a narrow residual audit of only surfaces still lacking `registry.invoke`/inverse registration—especially authority settings/linking and PyKEEN review handlers—then add engine tests. Do not retain the original “16” claim. |
| **#2594 consolidate execution** | **CLOSE-AS-DONE** | `fichero/execution/{runner,batch,chaining}.py` exists. Old `api/routes/workflow_execution/runner.py` and `workflows/{batch,chaining}.py` are one-line compatibility shims. The implementation move is complete; shim retirement belongs in the proposed execution-shim issue below. |
| **#2577 top-level component layout decision** | **CLOSE-AS-WRONG (for this milestone)** | This is repository/product architecture, not engine/Python hygiene. It spans Swift app, CLI, external MCP and web. Move/recreate under a top-level architecture milestone only after the external components have concrete build/package boundaries. Keeping it here makes “backend hygiene cleaned up” unfinishable. |
| **#2576 top-level external fichero-mcp** | **CLOSE-AS-WRONG (for this milestone)** | The engine already has internal MCP code (`fichero/mcp`) and API routes (`api/routes/mcp`). Designing an external authenticated HTTPS client is a separate product/security deliverable, not source hygiene. Track with external MCP/product work, not M177. |
| **#2569 group flat API routes** | **REWRITE** | Domain packages are implemented, so the original refactor is done. The remaining 84 zero-symbol flat files are exact aliases to the domain implementations. Rewrite the issue to “repoint all internal/test imports and remove flat route compatibility aliases,” split by domain as below. |
| **#2566 reorganize loose modules** | **REWRITE** | The packages in the proposal now exist (`db`, `llm`, `models`, `security`, `importers`, etc.). The remaining work is the alias inventory, direct-import policy, cycle removal and targeted hotspot extraction. Replace the broad reorg with the concrete shim/cycle issues below; do not launch another big-bang move. |
| **#2562 top-level CLI + HTTPS verification** | **REWRITE** | The typed client exists at `fichero/cli/client.py`, and the CLI directly supports workflow SSE. But its `DEFAULT_BASE_URL` is still `http://127.0.0.1:8765`, and `FicheroClient.__init__` constructs plain `httpx.Client` with no certificate/pinning configuration. Rewrite to the verifiable transport question: reconcile this HTTP default with the documented pinned-HTTPS contract and add a real loopback round-trip test. Defer “top-level split” to #2577’s successor. |
| **#2561 separate GitHub identity** | **CLOSE-AS-WRONG (for this milestone)** | Operational governance, not engine/Python source. `AGENTS.md` already specifies model-authored commits and manager-owned merges. Any remaining bot-account/token decision belongs to repository governance. |

## 3. Compatibility shims: accurate inventory and removal order

### Count

There are **106 compatibility files detected by code shape**:

- **91 exact module-object aliases** using `sys.modules[__name__] = sys.modules[...]`.
- **15 simple `from new.path import *` shims** without the module-object assignment.

The previously remembered “~62” was an earlier snapshot. The current exact-alias route layer alone is 84 files.

### Exact-alias route shims: 84 by domain

| Owning domain | Count | Old flat files |
|---|---:|---|
| system | 14 | `actions`, `actions_registry`, `activity`, `agent_memory`, `bookmarks`, `changes`, `chat`, `locations`, `migrations`, `projects`, `registries`, `settings`, `storage`, `views` |
| kg | 15 | `kg_claim_analysis`, `kg_claim_search`, `kg_curation_rules`, `kg_entity_curation`, `kg_graph`, `kg_inclusion`, `kg_mutations`, `kg_predictions`, `kg_pykeen`, `kg_rebuild`, `kg_render`, `kg_review`, `kg_search`, `kg_sparql`, `kg_triangulation` |
| document | 9 | `annotations`, `artifacts`, `classifications`, `content_representations`, `document_inspector`, `documents`, `folders`, `notes`, `sources` |
| ai | 8 | `local_inference`, `local_models`, `model_comparison`, `models`, `multilingual`, `provider_keys`, `provider_models`, `providers` |
| workflow | 7 | `batch`, `chains`, `orchestration`, `schedules`, `tasks`, `triggers`, `workflows` |
| citation | 5 | `bibliography`, `citation_rendering`, `citation_usages`, `citations`, `references` |
| auth | 4 | `auth_accounts`, `authz`, `pairing`, `sandbox_access` |
| library | 4 | `library_entity_types`, `library_items`, `library_links`, `library_registry` |
| research | 4 | `research_agents`, `research_crud`, `research_notes`, `research_tools` |
| claim | 3 | `claim_curation`, `claim_links`, `claims` |
| ingest | 3 | `export`, `iiif`, `image_editing` |
| mcp | 3 | `integrations`, `mcp_servers`, `mcp_tools` |
| entity | 2 | `entities`, `entity_inspector` |
| interpretation | 2 | `canvas`, `hermeneutics` |
| search | 1 | `search_explain` |

**Total: 84.** `ingest/__init__.py`, `library/__init__.py`, and `search/__init__.py` are package façades, not old flat files; treat them separately and remove only after callers no longer rely on private re-exports.

### Non-route exact aliases: 7

- `db/core.py → fichero_server.db`
- `llm/core.py → fichero_server.llm`
- `models/core.py → fichero_server.models`
- `knowledge/hermeneutics_models.py → models.hermeneutics`
- `knowledge/knowledge_models.py → models.knowledge`
- `workflows/batch.py → execution.batch`
- `workflows/chaining.py → execution.chaining`

### Simple star-import shims: 15

- execution: `api/routes/workflow_execution/runner.py`.
- renderer: `citations/renderer.py`.
- knowledge legacy paths (12): `kg/_common.py`, `entity_vectors.py`, `graph.py`, `ner.py`, `paragraph.py`, `probabilistic_scorer.py`, `pykeen_predictor.py`, `rebuild.py`, `spacy_ner.py`, `triangulation.py`, `triples.py`, plus the `kg` legacy surface discovered by the same import shape.
- package façade imports should be audited separately rather than blindly deleted.

### Repoint-first order

For every batch: (1) enumerate importers/tests, (2) change them to the canonical package, (3) update path-keyed guardrails, (4) prove no references to old path, (5) delete aliases, (6) run domain tests plus all `scripts/check_*.py`; only the manager runs the consolidated full gate.

Recommended order:

1. **Leaf API domains in parallel:** citation+claim; auth+mcp; research+interpretation; library+entity+search. These have disjoint implementation/test surfaces.
2. **Document and ingest** after #3752 is explicitly held, because `folders.py` will otherwise collide with the collection migration.
3. **AI routes** independently of execution.
4. **System routes** as one slice because `api/main.py`, action registry and startup registration form a shared center.
5. **KG routes and old `fichero/kg`** as one protected slice. Preserve `api/routes/kg/sparql.py`, `knowledge/triples.py` and rdflib; delete only old import paths after callers move.
6. **Workflow + execution aliases** together, then close #2594.
7. **Core/model aliases** (`db/core`, `llm/core`, `models/core`, knowledge model aliases) last; their blast radius is highest.
8. Re-run `get_dependency_cycles`; only then address the residual integrations, local-inference and loaders cycles.

## 4. Dead-code candidates (with caveat)

`find_dead_code` reports 110 files at confidence 1.0, but many are false positives caused by dynamic FastAPI registration, resource loading and compatibility aliases. Treat zero-import results as **candidate evidence**, never deletion authority.

High-confidence deletion candidates **after reference checks**:

- the 84 flat route alias files: zero-symbol, declared moved, canonical implementation exists; delete after repointing internal/test imports.
- the 7 exact non-route aliases and 15 simple star-import aliases: same condition, but sequence later due to higher blast radius.
- `db/core.py`, `llm/core.py`, `models/core.py`: especially confusing reciprocal façades for newcomers; delete only after all importers use owning modules.
- `knowledge/{hermeneutics_models,knowledge_models}.py`: models live in `models/`; repoint and remove.

**Do not delete based on the dead-code report:**

- `api/routes/kg_sparql.py` is merely the old flat shim; the canonical `api/routes/kg/sparql.py` is live in `api/main.py:1520`, exposes a documented W3C SPARQL endpoint, materializes an rdflib graph, and is called through `mcp/full.py::kg_sparql`.
- `knowledge/triples.py` imports rdflib and describes DuckDB as canonical storage with rdflib as the queryable projection. This is Daniel’s desired W3C query layer. Keep and strengthen tests/documentation.
- default workflow JSON is loaded as package data, so zero Python importers are expected.
- dynamically registered workflow tools and route modules need registry/router proof before any deletion.

Potential follow-up candidates such as `core/logging.py`, `mcp/ui_control.py`, `workflows/task_workers.py`, and individual workflow tools should be **flagged for runtime/registry checks**, not placed in a deletion issue yet.

## 5. Proposed issue set (do not file yet)

### Domain-parallel shim slices

1. **Remove flat route shims: citation and claim**  
   Repoint all source/test imports from the eight old flat citation/claim modules to `api.routes.citation.*` and `api.routes.claim.*`, update path-keyed guardrails, prove zero legacy references, then delete the aliases. Preserve API paths and OpenAPI operation IDs.

2. **Remove flat route shims: auth and MCP**  
   Own only the four auth and three MCP flat aliases plus their tests. Repoint before deleting, keep internal MCP behavior unchanged, and do not mix in the external MCP product design.

3. **Remove flat route shims: research and interpretation**  
   Repoint the four research and two interpretation aliases. This slice owns only those domain routes/tests and must not touch system chat or knowledge routes.

4. **Remove flat route shims: library, entity and search**  
   Repoint four library, two entity and one search flat aliases. Audit the `library/__init__.py` and `search/__init__.py` façades separately; do not delete a façade while private test imports remain.

5. **Remove flat route shims: AI providers and local models**  
   Repoint the eight AI flat aliases. Keep this disjoint from the `llm/local_inference.py` cycle issue: route imports only in this slice.

6. **Remove flat route shims: document and ingest**  
   Repoint nine document and three ingest aliases, but exclude `folders.py` until #3752’s collection migration order is settled. Own image/import route tests; do not alter semantics.

7. **Remove flat route shims: system/startup**  
   Repoint the 14 system aliases and update `api/main.py` registration imports once. Because this touches the central router/action surface, run after leaf-domain batches have landed.

8. **Remove flat route shims: knowledge graph while preserving W3C SPARQL**  
   Repoint the 15 `kg_*` route aliases and the legacy `fichero/kg` import paths to `api.routes.kg.*` / `knowledge.*`. Explicitly retain and test `api/routes/kg/sparql.py`, `knowledge/triples.py`, rdflib serialization/query behavior, and `mcp/full.py::kg_sparql`.

9. **Retire workflow/execution compatibility paths**  
   Repoint `api/routes/workflow_execution/runner.py`, `workflows/batch.py`, `workflows/chaining.py`, and the seven flat workflow route aliases to `execution.*` / `api.routes.workflow.*`; delete aliases and re-measure the engine SCC. This is the completion issue for #2594.

10. **Retire core/model compatibility façades**  
    Repoint `db/core.py`, `llm/core.py`, `models/core.py`, and the two knowledge-model aliases. Require a blast-radius report first; do this only after route shim removal so failures are attributable.

### Cycle and clarity slices

11. **Break integration-provider import cycle with a leaf registry**  
    Remove the SCC among `integrations/base.py`, `bookends.py`, `devonthink.py`, and `tinderbox.py` by making the base contract independent of concrete providers and placing provider registration/composition in one leaf module. Preserve behavior and add an import-cycle regression check.

12. **Break local-inference/model-store cycle**  
    Separate the shared protocol/data needed by `llm/local_inference.py` and `llm/mlx_model_store.py` into a dependency-neutral module; neither implementation may import the other. Add cold-import tests.

13. **Break loader package cycle without eager imports**  
    Preserve the intentional lazy PEP 562 startup behavior in `loaders/__init__.py`, while eliminating the SCC with `document_loader.py`, `pdf_loader.py`, and `unified.py`. Test that importing the cache/startup path does not load the heavy unified stack.

14. **Extract bounded phases from vision and extraction hotspots**  
    Split only the proven hotspots (`process_vision`, `_write_kg_rows`, `_process_file`, `extract_all`, `_run_extractor`) into named phases with unchanged public functions and characterization tests. This is readability work, not a framework rewrite.

15. **Reconcile typed CLI transport with the pinned-HTTPS contract**  
    `FicheroClient.DEFAULT_BASE_URL` is HTTP and `httpx.Client` has no pin/verify configuration despite project docs declaring HTTPS pinning. Decide the supported CLI transport, implement fail-closed verification if HTTPS is canonical, and add a real loopback round-trip covering health, a typed request and workflow SSE. Keep packaging/top-level relocation out of scope.

16. **Audit residual direct mutations after action migration**  
    Replace #3740’s stale 16-item list with a generated/current inventory. Confirm which authority settings/linking and PyKEEN review handlers still bypass `registry.invoke`; route only the residual mutations through registered actions with `ChangeSpec`, inverse or an explicit non-invertible reason, and engine-side audit/undo tests.

17. **Document the canonical Python import map for contributors**  
    Add one concise contributor page mapping API, db, execution, importers, knowledge, llm, models, security and workflows; state that internal code imports owning submodules, compatibility façades are forbidden, and route directories match OpenAPI domains. Generate/check the shim count so aliases cannot silently return.

## 6. Sequencing and disjoint worker ownership

### Wave 0 — decisions, serial

- Rewrite/close the milestone issues per §2.
- Hold #3752 as a later semantic migration.
- Land the canonical-import map and a shim-detection guard. This establishes the rule before deletions.

### Wave 1 — parallel, disjoint leaf slices

Workers may run concurrently with these exact ownership boundaries:

- A: `api/routes/citation*`, `api/routes/claim*`, their tests.
- B: `api/routes/auth*`, `api/routes/mcp*`, their tests.
- C: `api/routes/research*`, `api/routes/interpretation*`, their tests.
- D: `api/routes/library*`, `api/routes/entity*`, `api/routes/search*`, their tests.
- E: `api/routes/ai*` flat aliases and AI route tests only.

No Wave-1 worker edits `api/main.py`; canonical registrations already exist there. If a test file spans two domains, assign that file to one worker and have the other omit it.

### Wave 2 — parallel with explicit exclusions

- F: document+ingest aliases/tests, **excluding folders/collection**.
- G: KG route + `fichero/kg` aliases/tests, including W3C preservation.
- H: workflow/execution aliases/tests.
- I: integrations cycle only.
- J: loaders cycle only.

These surfaces are disjoint. The local-inference cycle waits because it overlaps AI/LLM imports.

### Wave 3 — serial nexus work

1. system/startup aliases (`api/main.py` owner).
2. core/model aliases (`db`, `models`, `llm`, knowledge-model aliases).
3. local-inference cycle.
4. re-run dependency-cycle and tectonic analysis; write residual findings from current data.

### Wave 4 — semantic / behavioral work

1. residual direct mutations (#3740 rewrite).
2. CLI HTTPS round-trip.
3. #3752 collection migration as its own DB/OpenAPI/Swift batch.
4. hotspot extraction, one public function at a time with characterization tests.

The manager consolidates batches and runs the full backend + guardrail gate once their leaf tests are green. No worker should share a file with another live slice.

## Definition of “backend hygiene cleaned up”

- no internal or test imports use a deleted compatibility path;
- zero flat route alias files remain (or each retained façade has a documented external compatibility contract and removal date);
- canonical import map is documented and guardrailed;
- four current dependency cycles are either eliminated or reduced to a measured, documented residual with an owner;
- W3C SPARQL/rdflib remains live and tested;
- CLI transport documentation and implementation agree;
- broad reorg issues are closed/replaced by bounded domain slices;
- full engine suite plus every `scripts/check_*.py` guardrail is green before integration.
