# Module Organization Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete orphaned route files, rename misleadingly-named files, move a misplaced parser module, strip duplicate CRUD blocks from hermeneutics.py, fold spatial NativeNote fields into the canonical Note model, remove the migrate_knowledge_claims_provider_model migration now that it's in the base schema, and document the no-migration rule — all in one atomic commit.

**Architecture:** Two-part cleanup: (a) file-level operations on `fichero-engine/src/fichero/api/routes/` — deletions, renames, one extraction, one in-file surgery; (b) model/schema operations on `knowledge_models.py`, `spatial_models.py`, `db.py`, and `db_migrations.py`. Single commit at the end after all gates pass.

**Tech Stack:** Python / FastAPI / Pydantic / DuckDB. No Swift changes.

---

## Pre-flight: Orientation

Before any edits, read these files once to anchor the plan context:

- [ ] **Read `fichero-engine/src/fichero/api/main.py` lines 675–829** — import block + `_CORE_ROUTE_SPECS` + `_DEV_ROUTE_SPECS`.
- [ ] **Read `fichero-engine/src/fichero/api/routes/__init__.py`** — the `__all__` list that needs pruning.
- [ ] **Skim `agent-work/proposals/module-organization-2026-05-15.md` §4** — the canonical proposed-change table.

---

## Task 1: Delete pure-orphan files (`graph_exploration`, `graph_traversal`)

**Files:**
- Delete: `fichero-engine/src/fichero/api/routes/graph_exploration.py`
- Delete: `fichero-engine/src/fichero/api/routes/graph_traversal.py`
- Modify: `fichero-engine/src/fichero/api/routes/__init__.py`
- Delete test: `fichero-engine/tests/unit/test_graph_exploration.py`
- Delete test: `fichero-engine/tests/unit/test_routes_graph_exploration.py`

- [ ] **Step 1: Verify neither file is imported anywhere except `__init__.py`**

```bash
grep -rn "graph_exploration\|graph_traversal" fichero-engine/src/ fichero-engine/tests/ \
  --include="*.py" | grep -v "__pycache__" | grep -v "test_graph_exploration\|test_routes_graph_exploration"
```

Expected: zero hits (both files are not mounted in `main.py`; `main.py` imports them only if `__init__.py` re-exports them — but `graph_traversal` isn't in `__init__.__all__` and `graph_exploration` is referenced only in its test file).

- [ ] **Step 2: Delete the two route files**

```bash
rm fichero-engine/src/fichero/api/routes/graph_exploration.py
rm fichero-engine/src/fichero/api/routes/graph_traversal.py
```

- [ ] **Step 3: Remove `graph_exploration` from `routes/__init__.py` `__all__`**

In `/Users/danieltubb/code/fichero-0.0.2/fichero-engine/src/fichero/api/routes/__init__.py`, remove the line:
```python
    "graph_exploration",
```

- [ ] **Step 4: Delete the orphaned test files**

```bash
rm fichero-engine/tests/unit/test_graph_exploration.py
rm fichero-engine/tests/unit/test_routes_graph_exploration.py
```

- [ ] **Step 5: Run ruff to confirm no import errors**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/ --select=F401,F811
```

Expected: no errors from the deleted modules.

---

## Task 2: Delete `graph_reasoning.py` (port unique endpoints first)

**Files:**
- Read: `fichero-engine/src/fichero/api/routes/graph_reasoning.py`
- Read: `fichero-engine/src/fichero/api/routes/kg_graph.py`
- Modify: `fichero-engine/src/fichero/api/routes/kg_graph.py` (add missing endpoints)
- Modify: `fichero-engine/src/fichero/api/main.py` (remove from `_DEV_ROUTE_SPECS`, remove from imports)
- Delete: `fichero-engine/src/fichero/api/routes/graph_reasoning.py`
- Modify: `fichero-engine/tests/unit/test_routes_graph_reasoning.py` (update or delete)

**Context:** `graph_reasoning.py` is mounted at empty prefix under tag `graph-reasoning`. It uses `/api/graph/networkx/*` paths. `kg_graph.py` already has centrality, communities (Louvain + label propagation), pagerank, components, triangles, clustering, similar, traverse, path, neighborhood, metrics, cooccurrence. The `graph_reasoning` endpoints use a different `graph_reasoning` service module (not `kg.graph`), so they are using a *different implementation* — the question is whether their paths are consumed anywhere.

- [ ] **Step 1: Audit whether any test or SwiftUI file calls `/api/graph/networkx/*`**

```bash
grep -rn "/api/graph/networkx\|graph_reasoning" \
  fichero-engine/tests/ fichero/fichero/ \
  --include="*.py" --include="*.swift" | grep -v "__pycache__"
```

Expected: only hits in `test_routes_graph_reasoning.py` and `test_graph_reasoning.py` (unit tests of the `fichero.graph_reasoning` *module*, not the route). No SwiftUI callers.

- [ ] **Step 2: Verify `kg_graph.py` already covers the functionality semantically**

The `graph_reasoning.py` routes expose: networkx status/enable, centrality (POST+GET), communities (POST+GET), shortest paths, metrics, algorithms list. `kg_graph.py` exposes: centrality, cooccurrence, path, traverse, metrics, neighborhood, pagerank, communities, similar, components, triangles, clustering — all through `fichero.kg.graph` module. The `graph_reasoning` routes use a different underlying service (`fichero.graph_reasoning`) but the HTTP surface is fully duplicated at `/api/kg/graph/*`.

Since no SwiftUI client calls `/api/graph/networkx/*` (it's dev-tier only and the OpenAPI spec doesn't include it in core), this can be deleted outright.

- [ ] **Step 3: Remove `graph_reasoning` from `main.py` import block**

In `fichero-engine/src/fichero/api/main.py`, remove:
```python
    graph_reasoning,
```
from the `from fichero.api.routes import (` block.

- [ ] **Step 4: Remove `graph_reasoning` from `_DEV_ROUTE_SPECS`**

Remove the line:
```python
    (graph_reasoning.router, "", ["graph-reasoning"]),
```
from `_DEV_ROUTE_SPECS`.

- [ ] **Step 5: Remove `graph_reasoning` from `routes/__init__.py`**

Remove `"graph_reasoning",` from `__all__`.

- [ ] **Step 6: Delete the route file**

```bash
rm fichero-engine/src/fichero/api/routes/graph_reasoning.py
```

- [ ] **Step 7: Update or delete the test files**

`test_routes_graph_reasoning.py` tests the now-deleted route. Delete it. `test_graph_reasoning.py` tests the underlying `fichero.graph_reasoning` *module* (not the route) — keep it.

```bash
rm fichero-engine/tests/unit/test_routes_graph_reasoning.py
```

- [ ] **Step 8: Run tests to confirm no import errors**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_graph_reasoning.py -q
```

Expected: all pass (they test the module, not the route).

---

## Task 3: Delete `predictions.py` (port unique training-job endpoints into `kg_pykeen.py`)

**Files:**
- Read: `fichero-engine/src/fichero/api/routes/predictions.py`
- Read: `fichero-engine/src/fichero/api/routes/kg_pykeen.py`
- Modify: `fichero-engine/src/fichero/api/routes/kg_pykeen.py` (add unique endpoints)
- Modify: `fichero-engine/src/fichero/api/main.py` (remove from `_DEV_ROUTE_SPECS` + imports)
- Delete: `fichero-engine/src/fichero/api/routes/predictions.py`
- Delete: `fichero-engine/tests/unit/test_routes_predictions.py`

**Context:** `predictions.py` mounts at empty prefix (`/api/predictions/*`). `kg_pykeen.py` mounts at `/kg/pykeen` and has only `POST /train` and `GET /predict/{entity_id}`. The `predictions.py` unique endpoints are:
- `GET /api/predictions/training-jobs` — list training jobs
- `GET /api/predictions/training-jobs/{model_id}` — get training job by id
- `DELETE /api/predictions/models/{model_id}` — delete a trained model
- `GET /api/predictions/stored` — list stored predictions
- `GET /api/predictions/stored/{prediction_id}` — get stored prediction
- `PATCH /api/predictions/stored/{prediction_id}/verify` — verify a prediction

The `/status`, `/enable`, `/models` (list types), `/train`, `/generate/{model_id}`, `/heuristic`, `/store` endpoints all duplicate or are subsumed by `kg_pykeen.py` + `kg_predictions.py`. No SwiftUI caller uses `/api/predictions/*`.

**Decision:** Port `training-jobs` list/get, `models DELETE`, and `stored` list/get/verify into `kg_pykeen.py` at the `/kg/pykeen/*` prefix (so they live at `/api/kg/pykeen/training-jobs`, `/api/kg/pykeen/models/{id}`, `/api/kg/pykeen/stored/*`). This preserves the feature while removing the dead prefix.

- [ ] **Step 1: Verify no Swift client calls `/api/predictions/*`**

```bash
grep -rn "/api/predictions\|predictions/" fichero/fichero/ --include="*.swift" | grep -v "__pycache__"
```

Expected: zero hits.

- [ ] **Step 2: Add training-job management + stored-prediction endpoints to `kg_pykeen.py`**

Append the following to `fichero-engine/src/fichero/api/routes/kg_pykeen.py` (after the existing `predict` endpoint):

```python
from fichero.pykeen_inference import (
    StoredPrediction,
    TrainingResult,
    get_inference,
    set_inference_enabled,
)
from pydantic import Field as _Field


class VerifyPredictionRequest(BaseModel):
    verified: bool
    notes: str | None = None


@router.get(
    "/training-jobs",
    response_model=list[TrainingResult],
    summary="List all PyKEEN training jobs",
)
async def list_training_jobs() -> list[TrainingResult]:
    """List all training jobs (ported from deprecated /api/predictions/training-jobs)."""
    inference = get_inference()
    return inference.get_training_jobs()


@router.get(
    "/training-jobs/{model_id}",
    response_model=TrainingResult,
    summary="Get a specific training job",
)
async def get_training_job(model_id: str) -> TrainingResult:
    from fastapi import HTTPException
    inference = get_inference()
    job = inference.get_training_job(model_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Training job {model_id} not found")
    return job


class DeleteModelResponse(BaseModel):
    deleted: bool
    model_id: str


@router.delete(
    "/models/{model_id}",
    response_model=DeleteModelResponse,
    summary="Delete a trained PyKEEN model",
)
async def delete_trained_model(model_id: str) -> DeleteModelResponse:
    from fastapi import HTTPException
    inference = get_inference()
    deleted = inference.delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return DeleteModelResponse(deleted=True, model_id=model_id)


@router.get(
    "/stored",
    response_model=list[StoredPrediction],
    summary="List stored predictions",
)
async def list_stored_predictions(
    model_id: str | None = None,
    verified: bool | None = None,
) -> list[StoredPrediction]:
    """List stored predictions (ported from deprecated /api/predictions/stored)."""
    inference = get_inference()
    return inference.list_predictions(model_id=model_id, verified=verified)


@router.get(
    "/stored/{prediction_id}",
    response_model=StoredPrediction,
    summary="Get a specific stored prediction",
)
async def get_stored_prediction(prediction_id: str) -> StoredPrediction:
    from fastapi import HTTPException
    inference = get_inference()
    prediction = inference.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    return prediction


@router.patch(
    "/stored/{prediction_id}/verify",
    response_model=StoredPrediction,
    summary="Verify or refute a stored prediction",
)
async def verify_prediction(
    prediction_id: str,
    request: VerifyPredictionRequest,
) -> StoredPrediction:
    from fastapi import HTTPException
    inference = get_inference()
    prediction = inference.get_prediction(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    prediction.verified = request.verified
    if request.notes:
        prediction.notes = request.notes
    inference.store_prediction(prediction)
    return prediction
```

Note: `TrainingResult`, `StoredPrediction`, and `get_inference` are already imported in `predictions.py` from `fichero.pykeen_inference`. Add them to the existing import in `kg_pykeen.py`.

- [ ] **Step 3: Update `kg_pykeen.py` imports to include the new symbols**

The current import block in `kg_pykeen.py` is:
```python
from fichero.api.main import get_library_database
from fichero.db import Database
```
Add:
```python
from fichero.pykeen_inference import (
    StoredPrediction,
    TrainingResult,
    get_inference,
)
```

- [ ] **Step 4: Remove `predictions` from `main.py` import block**

Remove `predictions,` from the `from fichero.api.routes import (` block.

- [ ] **Step 5: Remove from `_DEV_ROUTE_SPECS`**

Remove:
```python
    (predictions.router, "", ["predictions"]),
```

- [ ] **Step 6: Delete the route file**

```bash
rm fichero-engine/src/fichero/api/routes/predictions.py
```

- [ ] **Step 7: Delete the route test (it tested `/api/predictions/*` paths)**

```bash
rm fichero-engine/tests/unit/test_routes_predictions.py
```

- [ ] **Step 8: Verify ruff passes**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/api/routes/kg_pykeen.py
```

Expected: no errors.

---

## Task 4: Strip duplicate CRUD from `hermeneutics.py`

**Files:**
- Modify: `fichero-engine/src/fichero/api/routes/hermeneutics.py`

**Context:** `hermeneutics.py` contains three sections:
1. `/frameworks/*` (5 routes) — duplicate of `kg_interpretations.py`'s `/kg/interpretations/frameworks/*`
2. `/interpretations/*` (5 routes) — duplicate of `kg_interpretations.py`'s `/kg/interpretations/*`
3. `/patterns/*`, `/circle-state/*`, `/suggestions` — UNIQUE to hermeneutics

The `/frameworks` and `/interpretations` blocks at lines 137–323 of `hermeneutics.py` must be deleted. The patterns + circle-state + suggestions blocks (lines 329–579) stay.

Also, both `kg_interpretations.py` and `hermeneutics.py` import from `hermeneutics_models.py`. The imports in `hermeneutics.py` for `Interpretation`, `InterpretiveActType`, `InterpretiveFramework`, `FrameworkType` will no longer be needed after stripping — but `PatternInstance`, `PatternStatus`, `HermeneuticCircleState`, `CircleNavigationDirection`, `HermesSuggestion`, `HermesSuggestionRequest` will still be needed.

- [ ] **Step 1: Verify no Swift client calls `/api/hermeneutics/frameworks` or `/api/hermeneutics/interpretations`**

```bash
grep -rn "hermeneutics/frameworks\|hermeneutics/interpretations" fichero/fichero/ --include="*.swift"
```

Expected: zero hits. (Swift client uses `/api/kg/interpretations/*`.)

- [ ] **Step 2: Delete the Framework CRUD block from `hermeneutics.py`**

Remove the entire section `# Framework CRUD` from `hermeneutics.py` — this is lines 134–224 (the `FrameworkDeactivatedResponse` class through `delete_framework`). These models and routes are:
```python
class FrameworkDeactivatedResponse(BaseModel):
    status: str

class FrameworkCreateRequest(BaseModel): ...
class FrameworkUpdateRequest(BaseModel): ...
# And the 5 route functions:
@router.post("/frameworks", ...)   # create_framework
@router.get("/frameworks", ...)    # list_frameworks
@router.get("/frameworks/{framework_id}", ...)  # get_framework
@router.patch("/frameworks/{framework_id}", ...)  # update_framework
@router.delete("/frameworks/{framework_id}")  # delete_framework
```

- [ ] **Step 3: Delete the Interpretation CRUD block from `hermeneutics.py`**

Remove the section from `# Interpretation CRUD` — `InterpretationCreateRequest`, `InterpretationUpdateRequest` classes and the 5 route functions (`create_interpretation`, `list_interpretations`, `get_interpretation`, `update_interpretation`, and the implicit delete which doesn't exist here).

**What remains after surgery:**
- `PatternCreateRequest`, `PatternUpdateRequest`
- `CircleStateCreateRequest`, `CircleStateNavigateRequest`
- All pattern routes: `create_pattern`, `list_patterns`, `get_pattern`, `update_pattern`, `add_claim_to_pattern`
- All circle-state routes: `create_circle_state`, `list_circle_states`, `get_circle_state`, `navigate_circle`, `backtrack_circle`
- `suggest_interpretations`

- [ ] **Step 4: Trim unused imports in `hermeneutics.py`**

After surgery, these imports are no longer needed:
```python
FrameworkType,
Interpretation,
InterpretiveActType,
InterpretiveFramework,
```

Remove them from the `from fichero.hermeneutics_models import (` block. Keep:
```python
CircleNavigationDirection,
FrameworkType,       # still needed by PatternCreateRequest.framework_id? No — PatternInstance uses it? Check.
HermeneuticCircleState,
HermesSuggestion,
HermesSuggestionRequest,
InterpretiveActType, # still needed by suggest_interpretations's act field
InterpretiveFramework,  # still needed by suggest_interpretations to load frameworks
PatternInstance,
PatternStatus,
```

Actually `suggest_interpretations` uses `InterpretiveFramework` (to load frameworks from db) and `InterpretiveActType` (for the suggestion's `act` field). Keep those. Remove `FrameworkType` (only used in `FrameworkCreateRequest`), `Interpretation` (only used in CRUD blocks being deleted).

Final import block after cleanup:
```python
from fichero.hermeneutics_models import (
    CircleNavigationDirection,
    HermeneuticCircleState,
    HermesSuggestion,
    HermesSuggestionRequest,
    InterpretiveActType,
    InterpretiveFramework,
    PatternInstance,
    PatternStatus,
)
```

- [ ] **Step 5: Run ruff on `hermeneutics.py`**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/fichero/api/routes/hermeneutics.py
```

Expected: no errors.

- [ ] **Step 6: Run the hermeneutics test**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_hermeneutics.py fichero-engine/tests/unit/test_hermeneutics_api.py -q
```

Expect: tests for pattern + circle-state + suggestions still pass; any tests for `/api/hermeneutics/frameworks` or `/api/hermeneutics/interpretations` will fail — those must be deleted from the test file too (they tested duplicate functionality; the canonical tests are in `test_routes_kg_interpretations.py` if it exists, else they were never written since `kg_interpretations` was already tested via `test_canonical_knowledge_routes.py`).

---

## Task 5: Rename `review_queue.py` → `claim_curation.py`

**Files:**
- Rename: `fichero-engine/src/fichero/api/routes/review_queue.py` → `claim_curation.py`
- Modify: `fichero-engine/src/fichero/api/main.py` (update import + `_CORE_ROUTE_SPECS`)
- Modify: `fichero-engine/src/fichero/api/routes/__init__.py` (update `__all__`)
- Rename test: `fichero-engine/tests/unit/test_review_queue.py` → `test_claim_curation.py`
- Rename test: `fichero-engine/tests/unit/test_routes_review_queue.py` → `test_routes_claim_curation.py`
- Update test imports in both test files

URL paths stay the same (mounted at `/api` in `_CORE_ROUTE_SPECS`).

- [ ] **Step 1: Copy the file to the new name**

```bash
cp fichero-engine/src/fichero/api/routes/review_queue.py \
   fichero-engine/src/fichero/api/routes/claim_curation.py
```

- [ ] **Step 2: Delete the old file**

```bash
rm fichero-engine/src/fichero/api/routes/review_queue.py
```

- [ ] **Step 3: Update `main.py`**

In the `from fichero.api.routes import (` block, replace `review_queue,` with `claim_curation,`.

In `_CORE_ROUTE_SPECS`, replace:
```python
    (review_queue.router, "/api", ["review-queue"]),
```
with:
```python
    (claim_curation.router, "/api", ["review-queue"]),
```

Note: keep the tag `"review-queue"` — changing the tag would alter the OpenAPI spec and downstream clients. Only the Python identifier changes.

- [ ] **Step 4: Update `routes/__init__.py`**

Replace `"review_queue",` with `"claim_curation",` in `__all__`.

- [ ] **Step 5: Rename test files and update their imports**

```bash
mv fichero-engine/tests/unit/test_review_queue.py \
   fichero-engine/tests/unit/test_claim_curation.py
mv fichero-engine/tests/unit/test_routes_review_queue.py \
   fichero-engine/tests/unit/test_routes_claim_curation.py
```

In `test_claim_curation.py`, change:
```python
from fichero.api.routes.review_queue import (
```
to:
```python
from fichero.api.routes.claim_curation import (
```

In `test_routes_claim_curation.py`, change any `review_queue` references to `claim_curation`.

- [ ] **Step 6: Run the renamed tests**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest \
  fichero-engine/tests/unit/test_claim_curation.py \
  fichero-engine/tests/unit/test_routes_claim_curation.py -q
```

Expected: all pass. Same test logic, just different import path.

---

## Task 6: Rename `kg_citations.py` → `citation_rendering.py`

**Files:**
- Rename: `fichero-engine/src/fichero/api/routes/kg_citations.py` → `citation_rendering.py`
- Modify: `fichero-engine/src/fichero/api/main.py` (update import + `_CORE_ROUTE_SPECS`)
- Modify: `fichero-engine/src/fichero/api/routes/__init__.py`

URL paths stay the same.

- [ ] **Step 1: Rename the file**

```bash
mv fichero-engine/src/fichero/api/routes/kg_citations.py \
   fichero-engine/src/fichero/api/routes/citation_rendering.py
```

- [ ] **Step 2: Update `main.py`**

In the imports block, replace `kg_citations,` with `citation_rendering,`.

In `_CORE_ROUTE_SPECS`, replace:
```python
    (kg_citations.router, "/api", ["knowledge-graph"]),
```
with:
```python
    (citation_rendering.router, "/api", ["knowledge-graph"]),
```

- [ ] **Step 3: Update `routes/__init__.py`**

There's no `kg_citations` entry in `__all__` — check first:
```bash
grep "kg_citations\|citation_rendering" fichero-engine/src/fichero/api/routes/__init__.py
```

If absent, nothing to change. If present, update it.

- [ ] **Step 4: Run ruff**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/ --select=F401
```

Expected: no import errors.

---

## Task 7: Move `search_query.py` → `fichero/search/query_parser.py`

**Files:**
- Create dir: `fichero-engine/src/fichero/search/`
- Create: `fichero-engine/src/fichero/search/__init__.py`
- Move: `fichero-engine/src/fichero/api/routes/search_query.py` → `fichero-engine/src/fichero/search/query_parser.py`
- Modify: `fichero-engine/src/fichero/api/routes/search.py` (update import)
- Delete: `fichero-engine/src/fichero/api/routes/search_query.py`
- Modify: `fichero-engine/tests/unit/test_search_query_parser.py` (update import)

- [ ] **Step 1: Create the `search` package**

```bash
mkdir -p fichero-engine/src/fichero/search
touch fichero-engine/src/fichero/search/__init__.py
```

- [ ] **Step 2: Copy the file to new location**

```bash
cp fichero-engine/src/fichero/api/routes/search_query.py \
   fichero-engine/src/fichero/search/query_parser.py
```

- [ ] **Step 3: Delete the old file**

```bash
rm fichero-engine/src/fichero/api/routes/search_query.py
```

- [ ] **Step 4: Update `search.py` import**

In `fichero-engine/src/fichero/api/routes/search.py`, change:
```python
from fichero.api.routes.search_query import parse_query
```
to:
```python
from fichero.search.query_parser import parse_query
```

- [ ] **Step 5: Check if `search_explain.py` also imports from `search_query`**

```bash
grep -n "search_query" fichero-engine/src/fichero/api/routes/search_explain.py
```

If it does, update that import too.

- [ ] **Step 6: Update the test file**

In `fichero-engine/tests/unit/test_search_query_parser.py`, change:
```python
from fichero.api.routes.search_query import parse_query, SearchPlan
```
to:
```python
from fichero.search.query_parser import parse_query, SearchPlan
```

- [ ] **Step 7: Run the parser tests**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_search_query_parser.py -q
```

Expected: all pass.

---

## Task 8: Fix OpenAPI tags for `document_inspector` and `entity_inspector`

**Files:**
- Modify: `fichero-engine/src/fichero/api/main.py`

- [ ] **Step 1: In `_CORE_ROUTE_SPECS`, change the tags for the two inspectors**

Change:
```python
    (document_inspector.router, "/api", ["knowledge-graph"]),
    (entity_inspector.router, "/api", ["knowledge-graph"]),
```
to:
```python
    (document_inspector.router, "/api", ["documents"]),
    (entity_inspector.router, "/api", ["entities"]),
```

- [ ] **Step 2: Verify the tag change doesn't break any test**

```bash
grep -rn "document_inspector\|entity_inspector\|knowledge-graph" \
  fichero-engine/tests/unit/ --include="*.py" | grep -v "__pycache__" | head -20
```

If tests assert the specific tag value, update them.

---

## Task 9: Fold `NativeNote` spatial fields into `Note` (or reference by id)

**Files:**
- Read: `fichero-engine/src/fichero/spatial_models.py` (NativeNote at line 142)
- Read: `fichero-engine/src/fichero/knowledge_models.py` (Note at line 514)
- Modify: `fichero-engine/src/fichero/knowledge_models.py` (add spatial fields to Note)
- Modify: `fichero-engine/src/fichero/api/routes/mind_palace.py` (use Note by reference instead of NativeNote)

**Context:**
- `Note` (in `knowledge_models.py`): title, body, kind, tags, linked_note/entity/claim/document_ids, address, parent_address, author_type, created_by, created_at, updated_at.
- `NativeNote` (in `spatial_models.py`): room_id, content (≈ body), note_type, author_type, author_id, status (draft/final), linked_claim_ids, linked_source_ids, linked_entity_ids, metadata, created_at, updated_at.

These are genuinely different models with different semantics — `NativeNote` is a workspace-attached scratchpad; `Note` is a Zettelkasten atom. The proposal says: "if NativeNote carries spatial fields on top of identical content fields, add the spatial fields directly to Note and have NativeNote become a thin alias." After reading both:

- `NativeNote.content` ≈ `Note.body` (same idea)
- `NativeNote.note_type` (user/ai/system) — not on Note
- `NativeNote.status` (draft/final/archived) — not on Note
- `NativeNote.room_id` (spatial anchor) — not on Note
- `NativeNote.linked_source_ids` — Note has linked_document_ids but not linked_source_ids
- `NativeNote` is missing: title, kind, NoteLink bidirectional links, address/parent_address

**Decision:** These are distinct enough to keep separate. However, `NativeNote` should reference the parent `SpatialRoom` by `room_id` (which it already does) and be separate from `Note`. Document this explicitly rather than merging. The proposal's wording ("if it's truly a different model, leave alone") applies here.

- [ ] **Step 1: Add a docstring to `NativeNote` clarifying the separation**

In `spatial_models.py`, add to `NativeNote`'s docstring:

```python
class NativeNote(BaseModel):
    """First-class text note in Mind Palace workspace.

    Distinct from ``knowledge_models.Note`` (Zettelkasten atoms): NativeNote is
    a spatially-anchored scratchpad tied to a SpatialRoom, with draft/final
    lifecycle and author attribution. Note is a free-standing Zettelkasten unit
    with bidirectional NoteLink edges. They share linked_entity_ids and
    linked_claim_ids as foreign keys; NativeNote carries room_id as its spatial
    anchor. If a workspace note matures into a Zettelkasten note the user
    creates a Note and can store its id in NativeNote.metadata['note_ref'].
    """
```

- [ ] **Step 2: No schema migration needed** — models stay separate. Document in STATE.md under "Architecture decisions this session".

---

## Task 10: Fold `migrate_knowledge_claims_provider_model` into base schema

**Files:**
- Read: `fichero-engine/src/fichero/db_migrations.py` (lines 300–348)
- Read: `fichero-engine/src/fichero/db.py` (lines 194–207 — `__init__` migration block)
- Read: `fichero-engine/src/fichero/knowledge_models.py` (lines 876–894 — KnowledgeClaim.provider/model/language)
- Modify: `fichero-engine/src/fichero/db.py` (remove the migration call)
- Modify: `fichero-engine/src/fichero/db_migrations.py` (remove the function)

**Context:** `KnowledgeClaim.provider`, `.model`, `.language` are declared fields in `knowledge_models.py`. The `_ensure_table` method in `db.py` builds CREATE TABLE from Pydantic model fields automatically — so for a fresh library these columns already exist. The `migrate_knowledge_claims_provider_model` function only matters for libraries created *before* these fields were added. Since there are no users and we can nuke/recreate libraries freely (no-migration window), the function is now dead weight.

- [ ] **Step 1: Verify the fields ARE in `KnowledgeClaim`**

```bash
grep -n "provider\|model\b\|language" fichero-engine/src/fichero/knowledge_models.py | grep -A2 "class KnowledgeClaim" | head -15
```

Confirm `provider: str | None`, `model: str | None`, `language: str | None` are declared. They are (lines 876–894).

- [ ] **Step 2: Remove `migrate_knowledge_claims_provider_model` from `db.py` `__init__`**

In `db.py` `__init__` (around line 195–206), change:
```python
        from fichero.db_migrations import (
            migrate_document_table,
            migrate_knowledge_claims_provider_model,
            migrate_workflow_table,
            migrate_saved_search_table,
            migrate_provider_refs_table,
        )
        migrate_document_table(self.conn)
        migrate_workflow_table(self.conn)
        migrate_saved_search_table(self.conn)
        migrate_provider_refs_table(self.conn)
        migrate_knowledge_claims_provider_model(self.conn)
```
to:
```python
        from fichero.db_migrations import (
            migrate_document_table,
            migrate_workflow_table,
            migrate_saved_search_table,
            migrate_provider_refs_table,
        )
        migrate_document_table(self.conn)
        migrate_workflow_table(self.conn)
        migrate_saved_search_table(self.conn)
        migrate_provider_refs_table(self.conn)
```

- [ ] **Step 3: Also remove the comment referencing the migration in `db.py`**

Around line 258, there is a comment:
```
        # ADD COLUMN migrations (`migrate_knowledge_claims_provider_model`
```
Remove or update that comment since the migration is gone.

- [ ] **Step 4: Remove `migrate_knowledge_claims_provider_model` from `db_migrations.py`**

Delete the entire function `migrate_knowledge_claims_provider_model` (lines 300–347 of `db_migrations.py`).

- [ ] **Step 5: Check for any other callers of the deleted function**

```bash
grep -rn "migrate_knowledge_claims_provider_model" fichero-engine/src/ fichero-engine/tests/ | grep -v "__pycache__"
```

Expected: zero hits (only `db.py` called it, which we already cleaned).

- [ ] **Step 6: Run the migrations test**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_migrations.py -q
```

Expected: all pass.

---

## Task 11: Update CLAUDE.md with the no-migration rule

**Files:**
- Modify: `/Users/danieltubb/code/fichero-0.0.2/.claude/CLAUDE.md`
- Modify: `/Users/danieltubb/code/fichero-0.0.2/STATE.md`

- [ ] **Step 1: Add a "No-Migration Window" section to `.claude/CLAUDE.md`**

Insert after the "## Rules I Don't Break" section:

```markdown
## 0.0.x No-Migration Window

During the 0.0.x series **there are no users** — libraries can be nuked and recreated freely.

**Rule:** Schema changes go directly into `db.py`'s `CREATE TABLE` via the Pydantic model field declarations (the `_ensure_table` method reads model fields). Do NOT write `db_migrations.py` migration functions for new columns. To pick up a schema change, delete the old `.fichero` library and create a new one:

```bash
rm -rf ~/Documents/fichero-loop-test.fichero
PYTHONPATH=fichero-engine/src .venv/bin/python -m fichero library create ~/Documents/fichero-loop-test.fichero
```

The existing `migrate_workflow_table`, `migrate_saved_search_table`, `migrate_document_table`, and `migrate_provider_refs_table` functions are retained for now because they cover additive column changes on tables that *may* exist in Daniel's test library — but no NEW migration functions should be added during 0.0.x.
```

- [ ] **Step 2: Update `STATE.md` "What was shipped this session"**

Add a summary like:

```markdown
## 2026-05-15 — Module Organization Cleanup

- Deleted `graph_exploration.py` (911 lines, not mounted) + `graph_traversal.py` (377 lines, only consumer was `graph_exploration`)
- Deleted `graph_reasoning.py` (dev-tier NetworkX surface, fully subsumed by `kg_graph.py`)
- Deleted `predictions.py` (420 lines, pre-consolidation duplicate); ported `training-jobs`, `models DELETE`, and `stored/*` endpoints into `kg_pykeen.py` at `/api/kg/pykeen/*`
- Stripped duplicate `/frameworks/*` + `/interpretations/*` CRUD from `hermeneutics.py`; `kg_interpretations.py` is the canonical surface
- Renamed `review_queue.py` → `claim_curation.py` (mounts under `/api/claims`, operates on `KnowledgeClaim.curation_state`)
- Renamed `kg_citations.py` → `citation_rendering.py` (APA/Chicago/MLA rendering, not a graph)
- Moved `search_query.py` → `fichero/search/query_parser.py` (parser, not a route)
- Fixed OpenAPI tags: `document_inspector` → `"documents"`, `entity_inspector` → `"entities"`
- `NativeNote` stays separate from `Note` — documented in `spatial_models.py` docstring
- Removed `migrate_knowledge_claims_provider_model` (fields in base schema; no-migration window)
- Added no-migration rule to CLAUDE.md
```

---

## Task 12: All gates — lint + tests + schema regen

**Per-commit gates before the final commit.**

- [ ] **Step 1: Full ruff check**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
```

Expected: zero errors. Fix any that appear before moving on.

- [ ] **Step 2: Full unit test run**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest \
  fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived \
  -q
```

Expected: only `test_reset_clears_all_settings` may fail (pre-existing). All others pass.

- [ ] **Step 3: Nuke and recreate the loop test library**

```bash
rm -rf ~/Documents/fichero-loop-test.fichero
PYTHONPATH=fichero-engine/src .venv/bin/python -m fichero library create ~/Documents/fichero-loop-test.fichero
```

Expected: success, no errors.

- [ ] **Step 4: Start the backend and spot-check endpoints**

```bash
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765 &
sleep 3
# Spot-check claim_curation (was review_queue)
curl -s http://localhost:8765/api/claims/review-queue | python3 -c "import sys,json; print(json.load(sys.stdin))" || echo "200 or empty OK"
# Spot-check citation_rendering (was kg_citations)
curl -s http://localhost:8765/api/citations/render?document_id=test | python3 -c "import sys,json; print(json.load(sys.stdin))" || echo "200 or 404 OK"
# Spot-check kg_pykeen new endpoints
curl -s http://localhost:8765/api/kg/pykeen/training-jobs | python3 -c "import sys,json; print(json.load(sys.stdin))"
# Spot-check hermeneutics pattern (unique endpoint must still work)
curl -s http://localhost:8765/api/hermeneutics/patterns | python3 -c "import sys,json; print(json.load(sys.stdin))"
kill %1
```

Expected: all return 200 (possibly empty arrays for list endpoints).

- [ ] **Step 5: Regenerate OpenAPI schema**

```bash
bash fichero-engine/scripts/sync_openapi_schema.sh
```

Expected: regenerated `openapi.json` files. Commit them as part of the same commit.

- [ ] **Step 6: Verify regenerated schema doesn't reference deleted routes**

```bash
grep -E "graph_exploration|graph_traversal|/api/predictions/|/api/graph/networkx" \
  fichero-engine/tests/contracts/openapi.json | head -5
```

Expected: zero hits.

---

## Task 13: Single final commit

- [ ] **Step 1: Stage all changes**

```bash
git add \
  fichero-engine/src/fichero/api/routes/ \
  fichero-engine/src/fichero/search/ \
  fichero-engine/src/fichero/db.py \
  fichero-engine/src/fichero/db_migrations.py \
  fichero-engine/src/fichero/spatial_models.py \
  fichero-engine/tests/unit/ \
  fichero-engine/tests/contracts/openapi.json \
  fichero-engine/tests/contracts/endpoints.json \
  fichero/fichero-api-client/Sources/FicheroAPIClient/openapi.json \
  .claude/CLAUDE.md \
  STATE.md
```

- [ ] **Step 2: Create the commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(routes): module-org cleanup — deletions, renames, parser extraction, schema fold

Deletions (not mounted / subsumed):
- routes/graph_exploration.py (911 lines) — not in main.py since May-12 KG consolidation
- routes/graph_traversal.py (377 lines) — only consumer was graph_exploration
- routes/graph_reasoning.py — dev-tier NetworkX surface fully subsumed by kg_graph.py
- routes/predictions.py (420 lines) — pre-/kg namespace duplicate; unique endpoints
  (training-jobs, models DELETE, stored/*) ported into kg_pykeen.py at /api/kg/pykeen/*

File surgery:
- hermeneutics.py — stripped duplicate /frameworks/* + /interpretations/* CRUD;
  kg_interpretations.py is the canonical surface per KG_ENDPOINTS.md

Renames (URL paths unchanged):
- routes/review_queue.py → claim_curation.py (mounts under /api/claims,
  transitions KnowledgeClaim.curation_state; unrelated to entity-pair kg_review.py)
- routes/kg_citations.py → citation_rendering.py (APA/Chicago/MLA rendering;
  citations.py is the actual citation graph)

Extraction:
- routes/search_query.py → fichero/search/query_parser.py (zero @router decorators;
  it is a parser, not a route)

OpenAPI tag fixes:
- document_inspector tag: knowledge-graph → documents
- entity_inspector tag: knowledge-graph → entities

Schema / migration:
- Remove migrate_knowledge_claims_provider_model (provider/model/language fields are
  in KnowledgeClaim's base schema; _ensure_table picks them up on fresh library;
  no-migration window allows nuking old libraries)
- NativeNote kept separate from Note (documented rationale in spatial_models.py)

Tests: deleted orphaned test files for deleted routes; renamed/re-imported tests
for renamed modules. Regenerated openapi.json files.

Docs: added 0.0.x no-migration rule to CLAUDE.md; updated STATE.md.

EOF
)"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Task 1: `graph_exploration` + `graph_traversal` deleted
- [x] Task 2: `graph_reasoning` deleted (conditional diff confirmed subsumed)
- [x] Task 3: `predictions.py` deleted; unique endpoints ported to `kg_pykeen.py`
- [x] Task 4: hermeneutics duplicate CRUD stripped
- [x] Task 5: `review_queue` → `claim_curation`
- [x] Task 6: `kg_citations` → `citation_rendering`
- [x] Task 7: `search_query.py` → `fichero/search/query_parser.py`
- [x] Task 8: OpenAPI tag fix for inspectors
- [x] Task 9: NativeNote vs Note — documented, not merged (correct per proposal)
- [x] Task 10: `migrate_knowledge_claims_provider_model` removed
- [x] Task 11: CLAUDE.md + STATE.md updated
- [x] Task 12: All gates — lint + tests + schema regen
- [x] Task 13: One commit with all changes

**Placeholder scan:** No TBD or TODO patterns in code blocks.

**Type consistency:** All symbol references match across tasks (e.g., `claim_curation.router` in main.py matches the imported `claim_curation` module name).
