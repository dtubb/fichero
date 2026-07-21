# Engine package reorg — staged plan (de-risks #2566)

**Status:** PLAN ONLY. No files are moved and no code is changed by this document.
**Scope:** `fichero-engine/src/fichero/` — reorganize the ~77 loose top-level
`*.py` modules into domain subpackages, staged and shim-protected so the
hundreds of import sites never break at once.
**Related:** #2569 (api/routes grouping) and #2594 (execution subsystem
consolidation) — sequenced at the end of this doc.

---

## 0. Key findings that shape the plan

Three facts discovered while surveying the tree change the risk calculus:

1. **The pattern is already proven in-repo.** The entire `importers/` domain has
   *already* been moved into `fichero/importers/` and each old top-level path
   left as a **module-aliasing shim**. Example — `fichero-engine/src/fichero/ingest.py`
   is one line:

   ```python
   from fichero.importers.ingest import *; import sys; sys.modules[__name__] = sys.modules["fichero.importers.ingest"]  # noqa
   ```

   This is the **canonical shim** for this reorg (see §3). It is domain-agnostic:
   the `sys.modules[__name__] = …` reassignment makes `fichero.ingest` an *alias
   for the same module object*, so `import *`-missed names, `isinstance`/identity
   checks, and `fichero.ingest.submodule` access all keep working.

2. **A second, weaker shim style is also present — do not copy it.**
   `knowledge_models.py` (blast **291**) and `hermeneutics_models.py` (blast 17)
   have already been moved into `knowledge/` but were shimmed with a bare
   `from fichero.knowledge.knowledge_models import *  # noqa` — **no `sys.modules`
   aliasing**. That re-exports public names but leaves `fichero.knowledge_models`
   a *distinct* module object (identity/`isinstance`/submodule access can diverge).
   Standardize every new shim on the stronger `importers` pattern; optionally
   upgrade these two weak shims while in the area.

3. **Packaging is auto-discovery — no package list to maintain.**
   `fichero-engine/pyproject.toml` uses `[tool.setuptools.packages.find]` with
   `where = ["src"]`. New subpackages are picked up automatically **provided each
   has an `__init__.py`**. One operational caveat: an **editable install must be
   re-run** (`pip install -e .`) after adding a brand-new subpackage dir, or the
   new package won't import in that environment.

4. **Only three Python guardrails are path-keyed** (see §4). The big Swift-side
   guardrails (`check_dead_files.py`, `check_folder_organization.py`,
   `check_duplicate_paths.py`) walk `SWIFT_ROOT` only and are **unaffected** by
   Python moves.

---

## 1. Domain map

Blast = number of files (engine `src` + `tests`) that import the module, counting
absolute (`from fichero.X`), relative (`from .X`, `from . import X`), and
`from fichero import X` forms. The Swift app (`fichero/`) contains no Python
imports of these modules, so engine-internal counts are the whole story.

Target packages: **`db/`** (persistence + paths), **`models/`** (pydantic domain
models), **`llm/`** (models, inference, prompts, language), **`mcp/`** (exists),
**`security/`** (auth, transport, sandbox), **`importers/`** (done),
plus two small proposed utility packages **`media/`** and **`core/`**.

### db/ — persistence & paths
| module | blast | confidence | note |
|---|---|---|---|
| `db.py` | **337** | high | **GOD-NODE** → `db/core.py`, shim mandatory |
| `app_db.py` | 65 | high | application DB (settings/accounts store), distinct from library db → `db/app.py` |
| `storage.py` | 47 | high | → `db/storage.py` |
| `db_manager.py` | 28 | high | → `db/manager.py` |
| `db_embeddings.py` | 27 | high | → `db/embeddings.py` (also on the `check_ai_model_metadata` list) |
| `paths.py` | 18 | med | path resolver; referenced by `check_model_download_location` docstring → `db/paths.py` or a dedicated `paths/`; **flag** |
| `library_paths.py` | 13 | med | → `db/library_paths.py`; **flag** (paths vs library concern) |
| `db_migrations.py` | 10 | high | → `db/migrations.py` (rename to avoid clashing with `migrations.py` below) |
| `migrations.py` | 5 | med | generic migration runner — distinct from `db_migrations.py`; **flag** name collision on move |
| `storage_snapshots.py` | 4 | high | → `db/storage_snapshots.py` |
| `library_bootstrap.py` | 3 | med | first-run library creation; **flag** (db vs a `bootstrap`/`lifecycle` home) |

### models/ — pydantic domain models
| module | blast | confidence | note |
|---|---|---|---|
| `models.py` | **505** | high | **GOD-NODE (highest)** → `models/core.py`, shim mandatory |
| `knowledge_models.py` | 291 | — | **already moved** to `knowledge/` (weak shim) — reconcile, don't re-move |
| `research_models.py` | 12 | med | still loose → `models/research.py` (or `research/` package); **flag** overlap with existing `knowledge/` model home |
| `hermeneutics_models.py` | 17 | — | **already moved** to `knowledge/` (weak shim) |
| `canvas_models.py` | 9 | med | spatial/canvas models — issue called this `spatial_models.py` (**does not exist**; this is it) → `models/canvas.py` |

> **Reconciliation note:** the issue's `models/` group partly *already exists* as
> `knowledge/` (`knowledge_models`, `hermeneutics_models` live there). Decide one
> home: either fold `models.py`/`research_models.py`/`canvas_models.py` into
> `knowledge/`, or create `models/` and move the two knowledge ones into it.
> Do **not** create a `models/` that half-duplicates `knowledge/`.

### llm/ — models, inference, prompts, language
| module | blast | confidence | note |
|---|---|---|---|
| `llm.py` | **311** | high | **GOD-NODE** → `llm/core.py`, shim mandatory |
| `providers.py` | 32 | high | → `llm/providers.py` (on `check_ai_model_metadata` list) |
| `prompts.py` | 13 | high | → `llm/prompts.py` |
| `model_profiles.py` | 12 | high | → `llm/model_profiles.py` |
| `local_inference.py` | 11 | high | → `llm/local_inference.py` |
| `local_models.py` | 10 | high | → `llm/local_models.py` |
| `mlx_runtime.py` | 8 | med | issue omitted mlx_*; clearly inference → `llm/mlx_runtime.py` |
| `multilingual.py` | 7 | high | → `llm/multilingual.py` |
| `lang_detect.py` | 7 | high | → `llm/lang_detect.py` |
| `language_coverage.py` | 6 | high | → `llm/language_coverage.py` |
| `provider_validation.py` | 6 | high | → `llm/provider_validation.py` |
| `mlx_model_store.py` | 5 | med | → `llm/mlx_model_store.py` |
| `model_recommendations.py` | 4 | high | → `llm/model_recommendations.py` |
| `orchestration_policy.py` | 4 | med | model-orchestration policy → `llm/orchestration_policy.py`; **flag** (could be execution) |
| `pykeen_inference.py` | 4 | low | KG-embedding inference → **kg/** not llm/; **flag** (kg vs llm) |
| `llm_embeddings.py` | 4 | high | → `llm/embeddings.py` (on `check_ai_model_metadata` list) |
| `llm_models.py` | 3 | high | → `llm/models.py` |
| `llm_mock.py` | 3 | high | → `llm/mock.py` |
| `graph_reasoning.py` | 1 | low | KG reasoning → **kg/** not llm/; **flag** (kg vs llm) |

> Naming caution: `llm_models.py`, `model_profiles.py`, `model_recommendations.py`
> and `local_models.py` all collapse toward `models` — pick clear leaf names
> inside `llm/` to avoid a confusing `llm/models.py` vs top-level `models/`.

### security/ — auth, transport, sandbox
| module | blast | confidence | note |
|---|---|---|---|
| `authz.py` | 50 | high | per-library ACL authorizer → `security/authz.py`, shim advised (>20) |
| `accounts.py` | 48 | high | password/session primitives → `security/accounts.py`, shim advised |
| `keychain.py` | 16 | high | → `security/keychain.py` |
| `path_security.py` | 12 | high | → `security/path_security.py` |
| `remote_access_tls.py` | 10 | high | transport → `security/remote_access_tls.py` (or a `net/` split) |
| `bind_host.py` | 10 | high | loopback bind → `security/bind_host.py` |
| `xml_security.py` | 9 | high | → `security/xml_security.py` |
| `multiuser.py` | 8 | high | → `security/multiuser.py` |
| `security_scoped_access.py` | 7 | high | → `security/security_scoped_access.py` |
| `url_security.py` | 6 | high | → `security/url_security.py` |
| `remote_backend.py` | 4 | med | transport → `security/remote_backend.py`; **flag** (net vs security) |
| `discovery.py` | 3 | med | Bonjour discovery → `security/discovery.py` or `net/`; **flag** |

> Optional split: `authz`/`accounts`/`multiuser`/`keychain`/`*_security` → `security/`,
> and `remote_*`/`bind_host`/`discovery` → `net/`. Keeping one `security/` package
> is simpler and recommended for the first pass.

### importers/ — ALREADY DONE (verify only)
`ingest`, `iiif_import`, `manifest_import`, `cloud_link_import`,
`slipbox_import`, `sergio_import`, `source_archive_import`, `tinderbox_link_import`
— all moved into `importers/` with strong module-aliasing shims. **No move.**
Use these as the reference implementation and regression check that the pattern holds.

### Proposed small utility packages (judgment — not in the issue)
| module | blast | target | note |
|---|---|---|---|
| `image_ops.py` | 6 | `media/` | image ops |
| `ocr_geometry.py` | 8 | `media/` | OCR geometry |
| `geo.py` | 3 | `media/` | geo/coords |
| `errors.py` | **49** | `core/` (or STAY) | high blast — shim mandatory if moved; **recommend defer/stay** |
| `logging.py` | 10 | `core/` | shadows stdlib name; util |
| `perf.py` | 6 | `core/` | perf timers |
| `utf16_offsets.py` | 7 | `core/` | text offsets |
| `bookmarks.py` | 8 | `core/` or a feature pkg | **flag** (feature vs util) |
| `export_service.py` | 8 | feature pkg / stay | **flag** |
| `node_aliases.py` | 7 | `models/` or `kg/` | node model; **flag** |
| `node_prototypes.py` | 6 | `models/` or `kg/` | node model; **flag** |
| `spatial_arrange.py` | 3 | `models/canvas` or `execution` | **flag** |
| `verification_targets.py` | 1 | `execution`/`workflows` | **flag** |

### Stay top-level (do not move)
`__init__.py`, `__main__.py`. Also **recommend keeping `errors.py` top-level**
for now (blast 49, pure utility, no domain pull — moving it is high risk for
near-zero clarity gain).

---

## 2. Blast-radius ranking (risk order)

```
505  models.py            GOD-NODE  ── shim mandatory
337  db.py                GOD-NODE  ── shim mandatory
311  llm.py               GOD-NODE  ── shim mandatory
291  knowledge_models.py  (already moved; weak shim — reconcile)
 65  app_db.py            shim mandatory
 50  authz.py             shim advised
 49  errors.py            shim mandatory IF moved (recommend: don't move)
 48  accounts.py          shim advised
 47  storage.py           shim advised
 33  ingest.py            (already moved)
 32  providers.py         shim advised
 28  db_manager.py        shim advised
 27  db_embeddings.py     shim advised
 18  paths.py             shim advised
 ...
 <10 everything else      shim optional but cheap — add it anyway
```

**Shim threshold:** any module with **blast ≥ 10** gets a shim; god-nodes
(`db`, `models`, `llm`, plus `knowledge_models`) get a shim **and** a dedicated
gated stage of their own (one PR each). Modules under 10 can move without a shim
in principle, but since the shim is one line, **add it to every moved module** —
it costs nothing and lets the import-rewrite step be lazy/incremental.

---

## 3. Shim strategy (the exact pattern)

For every moved module, leave the old top-level path as a one-line
**module-aliasing shim** (the proven `importers` pattern):

```python
# fichero-engine/src/fichero/db.py  (after db.py → db/core.py)
from fichero.db.core import *; import sys; sys.modules[__name__] = sys.modules["fichero.db.core"]  # noqa
```

Why this exact form and not a bare `import *`:
- `from … import *` alone re-exports only `__all__`/public names and creates a
  **separate** module object. Identity checks, `isinstance` against classes
  imported the "old" way, and `fichero.db.SOMESUBMODULE` access can silently
  diverge — the failure mode seen with the weak `knowledge_models` shim.
- `sys.modules[__name__] = sys.modules["<newpath>"]` makes the old name a true
  alias: `fichero.db is fichero.db.core` → **one object, zero divergence.**

**Package `__init__.py` for god-nodes.** When `db.py` becomes the package
`db/` with `db/core.py`, the shim above lives at the *old* file location
`fichero/db.py` — but that path is now shadowed by the new `db/` directory
(you can't have both `db.py` and `db/`). Resolution: put the re-export in
**`db/__init__.py`** instead, so `from fichero.db import Database` resolves via
the package:

```python
# fichero-engine/src/fichero/db/__init__.py
from fichero.db.core import *  # noqa
# optionally, explicit public surface:
from fichero.db.core import Database, connect, ...  # noqa
```

For a *non*-god-node moved into an existing package (e.g. `providers.py` →
`llm/providers.py`), keep the top-level file as the aliasing shim (there's no
directory collision because `llm/` is the package and `providers.py` stays a
file at top level). Use the one-liner form.

**Deletion of shims** is a *later, separate* cleanup PR (rewrite remaining
importers, then `git rm` the shim, gated) — never in the same PR as the move.

---

## 4. Guardrail repointing

Path-keyed Python guardrails that will break or go stale on these moves:

| script | what it keys on | breaks on | fix |
|---|---|---|---|
| `scripts/check_ai_model_metadata.py` | hardcoded `TARGET_FILES` tuple: `db_embeddings.py`, `llm.py`, `llm_embeddings.py`, `providers.py` (reads each file) | **db/ and llm/ stages** | repoint `TARGET_FILES` to new paths (`db/embeddings.py`, `llm/core.py`, `llm/embeddings.py`, `llm/providers.py`) in the same PR as the move |
| `scripts/check_emit_change_coverage.py` | hardcoded `…/api/routes/*.py::handler` and `…/workflows/*.py` path strings | **#2569 (routes) and #2594 (workflows)** — not the #2566 db/models/llm stages | repoint the path strings when the corresponding routes/workflows files move |
| `scripts/check_model_download_location.py` | rglobs `engine_src` for all `*.py` (functionally robust — auto-discovers moved files); only the **docstring** names `fichero/paths.py` | nothing functional; docstring goes stale if `paths.py` moves | update the docstring reference when `paths.py` moves (cosmetic) |

**Not affected** (walk `SWIFT_ROOT` or don't key engine module paths):
`check_dead_files.py`, `check_folder_organization.py`, `check_duplicate_paths.py`,
`check_silent_write_swallow.py`, `check_python_comment_hygiene.py`, and the rest
of the Swift-side `check_*.py`.

**Packaging guardrail:** none explicit, but after creating each **new** package
dir, run `pip install -e fichero-engine` in the test venv so setuptools
auto-discovery (`packages.find`, `where=["src"]`) registers it. Confirm every new
dir has an `__init__.py`.

---

## 5. Safe move sequence (low → high blast; one domain per PR)

Each stage = **one PR/commit**, gated by the **full engine pytest suite**
(reliable once #4039's shared-app poison + perf hang are addressed —
use `--ignore=tests/perf` meanwhile) **plus all `scripts/check_*.py`** run under
the engine venv with the worktree on `PYTHONPATH`.

| # | stage | domain | max blast | why here |
|---|---|---|---|---|
| 0 | **verify** | `importers/` (done) | 33 | no move; confirm shims resolve — establishes the baseline & pattern |
| 1 | **FIRST move** | `mcp/` (7 loose `mcp_*.py` → existing `mcp/`) | 6 | lowest blast, self-contained, target package already exists |
| 2 | | `media/` (`image_ops`, `ocr_geometry`, `geo`) | 8 | tiny, isolated, new pkg |
| 3 | | `core/` (`logging`, `perf`, `utf16_offsets`; **not** `errors`) | 10 | small utils; leave high-blast `errors` top-level |
| 4 | | `security/` (auth + net) | 50 | coherent domain; `authz`/`accounts` are the tall poles → shims |
| 5 | | `llm/` (non-god leaves first, then `llm.py`) | 311 | GOD-NODE stage; split into 5a leaves, 5b `llm.py`+`__init__` shim |
| 6 | | `db/` (leaves first, then `db.py`) | 337 | GOD-NODE stage; 6a leaves, 6b `db.py` → `db/core.py`+`__init__` shim |
| 7 | | `models/` (reconcile with `knowledge/`, then `models.py`) | 505 | highest blast; do LAST; 7a reconcile knowledge/, 7b `models.py` |

Interleave-able independent tracks (separate PRs, any time after stage 1):
- **#2569** api/routes grouping — low blast (imported by `api/main.py` router
  registration), but touches `check_emit_change_coverage.py`. Good early filler.
- **#2594** execution consolidation — do **after** the `workflows/` suite is
  green and after routes settle, since it moves
  `api/routes/workflow_execution/runner.py` into the execution package.

---

## 6. Per-domain recipe (template + specifics)

**Generic recipe per stage:**
1. `git mv fichero-engine/src/fichero/<mod>.py fichero-engine/src/fichero/<pkg>/<leaf>.py`
   (and `touch fichero-engine/src/fichero/<pkg>/__init__.py` if the package is new).
2. Rewrite in-tree references (engine `src` + `tests`):
   ```bash
   grep -rlE "fichero\.<mod>\b" fichero-engine/src fichero-engine/tests \
     | xargs sed -i '' -E 's/fichero\.<mod>\b/fichero.<pkg>.<leaf>/g'
   ```
   (Optional — the shim means you *can* defer rewrites; but rewriting now keeps
   the shim thin and lets it be deleted sooner.)
3. Add the aliasing shim at the old path (§3), OR the package-`__init__`
   re-export for god-nodes.
4. Repoint any guardrail from §4 that names the moved path, in the same PR.
5. `pip install -e fichero-engine` if a new package dir was created.
6. Gate: full engine pytest (`--ignore=tests/perf` until #4039) + all
   `scripts/check_*.py` under the engine venv. Push only if 0 failed.

**Stage 1 — mcp/ (FIRST):**
- `git mv` these into the existing `mcp/`: `mcp_server.py mcp_simple.py mcp_full.py
  mcp_manager.py mcp_kg_tools.py mcp_document_tools.py mcp_research_tools.py`
  → `mcp/server.py mcp/simple.py mcp/full.py mcp/manager.py mcp/kg_tools.py
  mcp/document_tools.py mcp/research_tools.py` (drop the redundant `mcp_` prefix).
- Shims at old paths (one-liner each). Rewrite the ≤6 importers of `mcp_manager`.
- Guardrails: none path-keyed. Gate + push. Smallest possible blast radius.

**Stage 4 — security/:** move all 12 modules; **shim `authz` and `accounts`**
(blast 50/48). No path-keyed guardrail. Consider the `security/` vs `net/` split
question but default to one `security/`.

**Stage 5 — llm/:** two sub-commits.
- 5a: move the 18 leaf modules (`providers`, `prompts`, `model_profiles`, `mlx_*`,
  `local_*`, `multilingual`, `lang_detect`, …) into `llm/`, shim each,
  **repoint `check_ai_model_metadata.py` TARGET_FILES** for `providers.py`,
  `llm_embeddings.py`. Park `pykeen_inference`/`graph_reasoning` for a `kg/`
  decision (flagged — don't force into llm/).
- 5b: `llm.py` → `llm/core.py`; `llm/__init__.py` re-exports; repoint the
  `llm.py` entry in `check_ai_model_metadata.py`. Gate hard (blast 311).

**Stage 6 — db/:** two sub-commits.
- 6a: leaves (`storage`, `db_manager`, `db_embeddings`, `db_migrations`→`migrations`,
  `migrations`→`runner`, `storage_snapshots`, `app_db`, `paths`, `library_paths`).
  Resolve the `db_migrations.py`/`migrations.py` **name collision** by renaming
  (`db/migrations.py` + `db/migration_runner.py`). Repoint
  `check_ai_model_metadata.py` for `db_embeddings.py`; update
  `check_model_download_location.py` docstring for `paths.py`.
- 6b: `db.py` → `db/core.py`; `db/__init__.py` re-exports. Gate hard (blast 337).

**Stage 7 — models/ (LAST):**
- 7a: **reconcile with `knowledge/`.** Decide the single home. Upgrade the weak
  `knowledge_models.py`/`hermeneutics_models.py` shims to the aliasing form while
  here. Place `research_models.py`, `canvas_models.py`.
- 7b: `models.py` → chosen `…/core.py`; `__init__` re-exports. Gate hardest
  (blast 505) — this is the single riskiest move; do it alone, nothing else in
  the PR.

---

## 7. Sequencing with #2569 and #2594

- **#2569 (api/routes → subpackages):** independent of the god-node moves; the
  route modules are wired through `api/main.py`'s `include_router` lines, not
  hundreds of call sites. Can run as early as stage 1. Its only guardrail cost is
  `check_emit_change_coverage.py` path strings + the endpoint-coverage/contract
  walkers (every route must stay registered). Pair with #2565 (API naming) so
  tag/operation_id/folder land as one "API reads by domain" change.
- **#2594 (execution consolidation):** run **after** `workflows/` is stable and
  after routes settle. It pulls `api/routes/workflow_execution/runner.py` up into
  an `execution/` package alongside the workflow defs, with `batch` as a run mode.
  Shim the old runner path; gate the full workflows suite; repoint the
  `workflows/…` entries in `check_emit_change_coverage.py`.

---

## 8. Risk summary

The dominant risk is the three god-nodes (`models` 505, `db` 337, `llm` 311) and
the already-half-moved `knowledge_models` (291); a naive move would break
hundreds of import sites in one commit. That risk is fully mitigated by the
module-aliasing shim already proven in the `importers/` domain (`sys.modules`
reassignment, not a bare `import *`), which keeps every old import path working as
a true alias while call sites are rewritten lazily and deleted in a later pass.
Sequencing low-blast, self-contained domains first (mcp → media → core →
security) validates the mechanics and the gate before any god-node is touched;
each god-node then moves alone, leaves-before-core, in its own fully-gated PR
(full engine suite once #4039's shared-app poison and perf hang are handled, plus
all `scripts/check_*.py`). Only three Python guardrails are path-keyed and each
has a one-line repoint in the same PR as its move; packaging is auto-discovery so
no package list drifts. Residual hazards to watch: the `db_migrations`/`migrations`
name collision, the `models/` vs existing `knowledge/` home decision, and the
handful of flagged kg-vs-llm modules (`pykeen_inference`, `graph_reasoning`) that
should not be forced into `llm/`.
