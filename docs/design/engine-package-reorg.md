# Engine package reorganization — staged plan

**Issues:** #2566 (top-level `src/fichero/` modules) + #2569 (`api/routes/` flattening)
**Status:** PROPOSAL (read-only analysis — no code moved)
**Scope guard:** Packaging only. **No behavior change.** OpenAPI surface, CLI, and the
full test suite (unit + contract walkers + endpoint-coverage guardrails) must stay green
at the end of *every* stage. This is reversible, incremental, and gateable.

---

## 1. Problem

`fichero-engine/src/fichero/` has **~65 loose top-level `.py` modules** sitting next to a
handful of well-formed subpackages (`actions/`, `api/`, `bibliography/`, `books/`,
`citations/`, `cli/`, `integrations/`, `kg/`, `loaders/`, `retrieval/`, `search/`,
`workflows/`). A contributor cannot tell from the tree where new code belongs — DB code,
LLM code, MCP servers, corpus importers, security primitives, and Pydantic model modules
are all dumped at the same level as god-nodes like `db.py` and `models.py`.

Separately, `api/routes/` is **89 route modules, essentially flat** (only
`workflow_execution/` is a subdir) despite obvious domain prefixes: 15× `kg_*`, 4×
`research_*`, plus `library*`, `search*`, `provider*`, `claim*`, `citation*`, `mcp_*`,
`local_*`. This is the single largest dumping-ground in the engine.

**Note on the existing guardrail:** `scripts/check_folder_organization.py` already enforces
a "max 18 files directly in a directory" rule — but **only for Swift** (`fichero/fichero`).
The Python engine is unguarded. This reorg should end by **extending that script to the
Python tree** (cap loose `.py` under `src/fichero/` and under `api/routes/`), so the flat
layout cannot silently regrow.

---

## 2. Blast-radius reality (measured via jcodemunch)

File-level importer counts (real = excluding stale `.claude/worktrees/*` index copies):

| Module | real importers | src importers | tests | Verdict |
|---|---:|---:|---:|---|
| `db.py` (`Database`) | **181** | 121 | 57 | **god-node — move last / never** |
| `models.py` | **175** | 114 | 59 | **god-node — move last / never** |
| `knowledge_models.py` (`KnowledgeClaim` = 173 symbol-importers) | **170** | 74 | 94 | **god-node — move last / never** |
| `llm.py` | **162** | 97 | 64 | **god-node — move last / never** |
| `app_db.py` | 30 | 23 | 7 | moderate |
| `ingest.py` | 25 (real) | ~9 | ~16 | moderate — **stays top-level** |
| `db_embeddings.py` | 17 | 7 | 10 | low |
| `db_manager.py` | 12 | 6 | 6 | low |
| `migrations.py` | 6 | 2 | 1 | low |
| `manifest_import.py` | 6 | 2 (`__main__`, `iiif_import`) | 2 | **leaf** |
| `mcp_manager.py` | 4 | 2 | 2 | **leaf** |
| `db_migrations.py` | 3 | 2 | 1 | low |
| `iiif/slipbox/sergio/cloud/tinderbox_import` | 3–4 each | 1 (`__main__`) | 1–2 | **leaf** |
| `mcp_full / mcp_server / mcp_simple / mcp_document_tools / mcp_kg_tools / mcp_research_tools` | **0** | 0 | 0 | **leaf (entry points)** |

Route modules (sample):

| Route module | real importers | who |
|---|---:|---|
| `kg_review.py` | 0 | (only `main._CORE_ROUTE_SPECS`) |
| `kg_graph.py` | 1 | `cli/client.py` (response model) |
| `research_crud.py` | 2 | sibling route + its test |
| `search.py` | 4 | `cli/client.py` + tests |
| `documents.py` | 5 | tests only |
| `providers.py` | 9 | `conftest` + tests (`get_app_database`) |
| `claims.py` | 10 | 3 sibling routes (`_descendant_doc_ids`) + tests |

**Key structural fact:** every route is registered in **one place** — `_CORE_ROUTE_SPECS`
in `api/main.py` (lines ~1234–1364), a list of `(router, prefix, [tags])` tuples, fed by a
single import block at the top of `main.py`. Route modules are otherwise imported almost
exclusively by their `test_routes_*` test and a few cross-route helpers
(`_descendant_doc_ids` from `claims`, `get_app_database` from `providers`) and response
models pulled by `cli/client.py`. **Routes are low-blast and funnel through one file.**

---

## 3. The shim pattern (keeps every stage green)

When a module moves from `fichero/foo.py` → `fichero/<group>/foo.py`, leave a
**re-export shim at the old path** so all existing import sites keep working untouched:

```python
# fichero/foo.py  — back-compat shim (#2566); delete after import sites migrate
from fichero.<group>.foo import *  # noqa: F401,F403
```

`import *` re-exports public names (and respects `__all__`). For the **few** modules whose
**underscore-prefixed** symbols are imported across files (e.g. `claims._descendant_doc_ids`,
`ingest._create_pdf_page_children`), the shim must name them explicitly:

```python
from fichero.api.routes.claims import _descendant_doc_ids  # noqa: F401
from fichero.api.routes.claims import *  # noqa: F401,F403
```

Per-stage rhythm:
1. **Move** the group's files into the new subpackage; add an `__init__.py`.
2. **Shim** each old path (wildcard, or explicit for underscore exports).
3. Run full gate (unit + contract walkers + endpoint coverage) — must be green on shims alone.
4. **Migrate** import sites to the new path, incrementally (each commit stays green).
5. **Drop** the shim once `find_importers`/`check_references` on the old path is empty.
6. Commit one group per stage; god-nodes never enter this loop (see §6).

This guarantees no "hundreds of import sites break at once" moment — the shim absorbs them.

---

## 4. Target layout

### 4a. `api/routes/` → domain subpackages (#2569)

Mirror the **OpenAPI tags already declared in `_CORE_ROUTE_SPECS`** — this pairs directly
with #2565 (explicit `operation_id`s + tags). "Read the API by domain" becomes one coherent
change across folder + tag + operation-id.

```
api/routes/
  kg/            kg_graph, kg_claim_analysis, kg_claim_search, kg_curation_rules,
                 kg_entity_curation, kg_inclusion, kg_mutations, kg_predictions,
                 kg_pykeen, kg_rebuild, kg_render, kg_review, kg_search, kg_sparql,
                 kg_triangulation            (15 modules)
  research/      research_agents, research_crud, research_notes, research_tools
  library/       library, library_entity_types, library_registry, folders, projects,
                 views, registries, classifications
  knowledge/     claims, claim_links, claim_curation, entities, entity_inspector,
                 annotations, notes, hermeneutics
  documents/     documents, document_inspector, ingest, artifacts, storage, sources,
                 export, iiif, image_editing
  search/        search, search_explain
  providers/     providers, provider_keys, provider_models, models, model_comparison,
                 local_inference, local_models, multilingual
  workflows/     workflows, workflow_execution/ (already a subpkg), orchestration,
                 batch, schedules, tasks, triggers, chains
  citations/     citations, citation_rendering, citation_usages, bibliography, references
  mcp/           mcp_servers, mcp_tools
  integrations/  integrations, mind_palace, mindpalace_render
  system/        auth_accounts, pairing, settings, migrations, activity, agent_memory,
                 actions, actions_registry, changes
```

(Exact bucketing is a detail to settle during the stage; the point is ~10 domain folders
keyed to tags, not 89 flat files.) Each moved route keeps a shim at its old path so
`test_routes_*` and `_CORE_ROUTE_SPECS` keep importing until migrated. **Every router stays
registered** — the contract endpoint walker and endpoint-coverage guardrails verify this.

### 4b. Top-level modules → subpackages (#2566)

```
db/         app_db, db_embeddings, db_manager, db_migrations, migrations
            (db.py itself stays top-level — god-node, see §6)
inference/  llm_embeddings, llm_mock, llm_models, local_inference, local_models,
  (or llm/) model_profiles, model_recommendations, providers, provider_validation, prompts
            (llm.py itself stays top-level — god-node)
mcp/        mcp_full, mcp_server, mcp_simple, mcp_manager, mcp_document_tools,
            mcp_kg_tools, mcp_research_tools
importers/  cloud_link_import, iiif_import, manifest_import, sergio_import,
            slipbox_import, source_archive_import, tinderbox_link_import
            (ingest.py stays top-level — 25 importers, core pipeline entry)
security/   authz, path_security, url_security, xml_security, keychain, bind_host,
  (or net/) remote_access_tls, remote_backend, discovery, multiuser, accounts
models/     hermeneutics_models, research_models, spatial_models
            (models.py + knowledge_models.py stay top-level — god-nodes)
```

**Stays at top level** (genuinely cross-cutting or god-node): `__init__`, `__main__`,
`db.py`, `models.py`, `knowledge_models.py`, `llm.py`, `ingest.py`, `errors`, `logging`,
`paths`, `perf`, `storage`, `storage_snapshots`, `export_service`, `graph_reasoning`,
`ocr_geometry`, `language_coverage`, `lang_detect`, `multilingual`, `bookmarks`,
`orchestration_policy`, `pykeen_inference`, `spatial_arrange`, `library_bootstrap`.

> Stale-index note: `db_writer.py` appears in the jcodemunch index but was **removed** in
> commit `4ee6b3be` ("remove redundant DBWriter"). Do not include it.

---

## 5. Staged migration order (low blast → high)

| Stage | Group | Modules | Concentrated churn | Risk |
|---|---|---|---|---|
| **1** | **`api/routes/` domain folders** | 89 routes → ~10 subpkgs | `main.py` import block + `_CORE_ROUTE_SPECS`; `test_routes_*` renames | **low** (one registration file; shims cover tests) |
| 2 | `mcp/` | 7 modules | ~2 src sites (`mcp_servers` route, `workflows/tools/mcp.py`) | **lowest churn** (6 of 7 have 0 importers) |
| 3 | `importers/` | 7 modules | `__main__.py` CLI wiring + per-module test | low (leaf; `ingest` excluded) |
| 4 | `security/` | ~11 modules | measure per-file first (`authz` is a chokepoint) | low–moderate |
| 5 | `inference/` (`llm/`) | ~10 modules | provider/model routes + tests | moderate |
| 6 | `db/` | 5 modules (`app_db` busiest at 30) | DB consumers + tests | moderate |
| 7 | `models/` | 3 small model modules | model importers + tests | moderate |
| — | guardrail | extend `check_folder_organization.py` to Python | new test only | trivial |

God-nodes (`db.py`, `models.py`, `knowledge_models.py`, `llm.py`) are **not** in any stage.

---

## 6. God-node verdict — MOVE LAST or NEVER

`db.py` (181), `models.py` (175), `knowledge_models.py` (170), `llm.py` (162) each have
**100–180 import sites**. Moving any one of them touches more files than the entire rest of
this plan combined, for **zero clarity gain** — every contributor already knows these four
are the spine (CLAUDE.md even lists them as "top god nodes").

**Recommendation: do NOT move them.** They are the package's well-known anchors; a flat
`fichero.db`, `fichero.models`, `fichero.knowledge_models`, `fichero.llm` is *more*
discoverable than a nested path. If a future maintainer insists on nesting (e.g. `db/core.py`),
it must go in **with a permanent re-export shim** at the old path (`from fichero.db.core import *`)
that is **never dropped** — the import-site churn to retire it is not worth it. The *satellite*
modules around each god-node (`db_*`, `llm_*`, the small `*_models`) are what move into
`db/`, `inference/`, `models/`; the anchor file stays put.

---

## 7. First-stage recommendation

**Start with Stage 1: `api/routes/` domain folders (#2569).** It is the best first move on
both axes:

- **Highest clarity win** — collapses the single biggest dumping ground (89 flat files) into
  ~10 tag-aligned domains, and the tags already exist in `_CORE_ROUTE_SPECS`.
- **Low, *centralized* blast radius** — registration is one file (`main.py`); the only other
  importers are `test_routes_*` (absorbed by shims) and a few helper/model imports. The
  contract endpoint walker + endpoint-coverage guardrail give a hard, automatic "every route
  still registered" gate.
- **Strategic pairing** — lands together with #2565 (operation_ids + tags) as one coherent
  "API organized by domain" change.

If a *purely mechanical, near-zero-risk* warm-up is wanted first, **Stage 2 (`mcp/`)** has the
absolute lowest churn (6 of 7 modules have zero importers) and is a safe rehearsal of the
shim workflow before tackling the 89-file route move. Either is a valid opener; **routes is
the highest-value first stage**, `mcp/` the lowest-risk.

---

## 8. Gate checklist (run at the end of every stage)

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/contracts/ \
  fichero-engine/tests/integration/test_contract_endpoint_walk.py
ruff check fichero-engine/src/
bash fichero-engine/scripts/sync_openapi_schema.sh   # OpenAPI must be byte-identical
python3 scripts/check_duplicate_paths.py
python3 scripts/check_folder_organization.py          # extend to Python in final stage
```

OpenAPI staying byte-identical is the proof that route grouping changed **packaging only**,
not the wire surface.
