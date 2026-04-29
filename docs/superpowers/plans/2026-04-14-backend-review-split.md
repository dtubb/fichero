# Backend Review & File Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 11 failing background_tasks tests, then systematically review and split all Python backend files that exceed the 1000-line hard limit.

**Architecture:** Two-phase work — (1) fix DuckDB transaction concurrency in TaskQueue using a threading.Lock; (2) split 12 oversized files by natural responsibility boundaries, updating all imports and verifying tests pass after each split.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, DuckDB, APScheduler, pytest-asyncio

---

## File Map

### Phase 1 — Fix
- Modify: `fichero-engine/src/fichero/workflows/tasks.py` (934 lines)
- Test: `fichero-engine/tests/unit/test_background_tasks.py`

### Phase 2 — Splits (hard-limit files > 1000 lines)

| File | Lines | Split into |
|------|-------|-----------|
| `api/routes/knowledge_graph.py` | 2378 | Package: `knowledge_graph/` with `mutations.py`, `entities.py`, `claims.py`, `predictions.py`, `analysis.py`, `__init__.py` |
| `api/routes/workflow_execution.py` | 2188 | `workflow_execution.py` (core) + `workflow_threads.py` + `workflow_visualization.py` + `workflow_cache.py` |
| `mcp_server.py` | 2055 | `mcp_server.py` (server entry) + `mcp_document_tools.py` + `mcp_workflow_tools.py` |
| `db.py` | 1447 | `db.py` (core) + `db_migrations.py` (inline migration methods extracted) |
| `api/routes/providers.py` | 1415 | `providers.py` (catalog + CRUD) + `provider_models.py` (per-type model listing) + `provider_keys.py` (API key mgmt) |
| `api/routes/graph_exploration.py` | 1259 | `graph_exploration.py` (paths + neighborhood) + `graph_traversal.py` (traversal + subgraph + interpretations) |
| `workflows/activity.py` | 1249 | `workflows/activity_types.py` (enums + dataclasses) + `workflows/activity_store.py` (ActivityStore) + `workflows/activity.py` (ActivityTracker + public API) |
| `workflows/tools/llm_base.py` | 1078 | `workflows/tools/llm_base.py` (config + output parsing) + `workflows/tools/llm_prompting.py` (prompt building helpers) |
| `workflows/registry.py` | 1062 | `workflows/registry.py` (registration API) + `workflows/registry_builtins.py` (_register_builtin_tools) |
| `llm.py` | 1056 | `llm.py` (complete + stream) + `llm_models.py` (model info, cost, list) + `llm_embeddings.py` (embed functions) |
| `api/routes/research_agents.py` | 1034 | `research_projects.py` + `research_tasks_steps.py` + `research_notes.py` + `research_tools.py` |
| `storage.py` | 1004 | `storage.py` (thumbnails + cleanup + stats) + `storage_library.py` (snapshot + library ops, lines 675+) |

---

## Task 1: Fix background_tasks DuckDB concurrency (11 failing tests)

**Root cause:** `_save_task()` opens a fresh `duckdb.connect(db_path)` per call. APScheduler fires multiple `_execute_task` coroutines concurrently; each calls `_save_task` via `asyncio.to_thread`, spawning real OS threads that all open separate connections and race on `INSERT OR REPLACE` for the same `task_id` row, causing `TransactionContext Error: Conflict on tuple deletion!`.

**Fix:** Add a `threading.Lock` to serialize all write operations to the task DB.

**Files:**
- Modify: `fichero-engine/src/fichero/workflows/tasks.py`
- Test: `fichero-engine/tests/unit/test_background_tasks.py`

- [ ] **Step 1: Verify current failures**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_background_tasks.py -v 2>&1 | tail -20
```
Expected: 11 FAILED, 15 passed.

- [ ] **Step 2: Add threading.Lock to TaskQueue.__init__**

In `fichero-engine/src/fichero/workflows/tasks.py`, add `import threading` to the imports block (near the existing `import asyncio`):
```python
import threading
```

In `TaskQueue.__init__` (around line 140-148), add `self._db_lock` after `self._lock`:
```python
def __init__(self, db_path: str, database: Optional[Database] = None):
    self.db_path = db_path
    self.database = database
    self._tasks: dict[str, BackgroundTask] = {}
    self._scheduler: Optional[AsyncIOScheduler] = None
    self._running: bool = False
    self._lock = asyncio.Lock()
    self._db_lock = threading.Lock()   # serializes concurrent DB writes
    self._init_database()
```

- [ ] **Step 3: Wrap all DB write calls with _db_lock**

In `_save_task`, replace the inner `_save` function to use the lock:
```python
async def _save_task(self, task: BackgroundTask) -> None:
    """Save task to database."""

    def _save():
        with self._db_lock:
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO background_tasks (
                        task_id, task_type, name, status,
                        options, priority, timeout_seconds,
                        progress_current, progress_total, progress_message,
                        progress_updated_at,
                        result_success, result_message, result_details, result_error,
                        created_at, started_at, completed_at, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        task.task_id,
                        task.task_type.value,
                        task.name,
                        task.status.value,
                        json.dumps(task.config.options),
                        task.config.priority,
                        task.config.timeout_seconds,
                        task.progress.current,
                        task.progress.total,
                        task.progress.message,
                        task.progress.updated_at,
                        task.result.success if task.result else None,
                        task.result.message if task.result else None,
                        json.dumps(task.result.details) if task.result else None,
                        task.result.error if task.result else None,
                        task.created_at,
                        task.started_at,
                        task.completed_at,
                        task.error_message,
                    ],
                )
            finally:
                conn.close()

    try:
        await asyncio.to_thread(_save)
    except (asyncio.CancelledError, RuntimeError):
        _save()
```

- [ ] **Step 4: Run tests**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_background_tasks.py -v 2>&1 | tail -20
```
Expected: 26 passed, 0 failed.

- [ ] **Step 5: Run full suite + lint**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q 2>&1 | tail -10
ruff check fichero-engine/src/fichero/workflows/tasks.py
```
Expected: all passing, no ruff errors.

- [ ] **Step 6: Commit**
```bash
git add fichero-engine/src/fichero/workflows/tasks.py
git commit -m "fix: serialize TaskQueue DuckDB writes with threading.Lock — fixes 11 async test failures (#460)"
```

---

## Task 2: Split knowledge_graph.py → package (2378 lines)

**Files:**
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/` (new package)
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/__init__.py`
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/mutations.py` (~200 lines, lines ~315–488)
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/entities.py` (~550 lines, lines ~489–1180)
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/claims.py` (~550 lines, lines ~1181–1659)
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/predictions.py` (~440 lines, lines ~1660–2090)
- Create: `fichero-engine/src/fichero/api/routes/knowledge_graph/analysis.py` (~290 lines, lines ~2091–2378)
- Delete: `fichero-engine/src/fichero/api/routes/knowledge_graph.py`
- Verify: `fichero-engine/src/fichero/api/main.py` import still works

- [ ] **Step 1: Create the package directory and read the source**
```bash
mkdir -p fichero-engine/src/fichero/api/routes/knowledge_graph
```
Read `fichero-engine/src/fichero/api/routes/knowledge_graph.py` fully to understand all imports and models.

- [ ] **Step 2: Write __init__.py — combines all sub-routers**
```python
# fichero-engine/src/fichero/api/routes/knowledge_graph/__init__.py
"""Knowledge graph API routes — split by responsibility."""

from fastapi import APIRouter

from .mutations import router as mutations_router
from .entities import router as entities_router
from .claims import router as claims_router
from .predictions import router as predictions_router
from .analysis import router as analysis_router

router = APIRouter()
router.include_router(mutations_router)
router.include_router(entities_router)
router.include_router(claims_router)
router.include_router(predictions_router)
router.include_router(analysis_router)
```

- [ ] **Step 3: Write mutations.py**

Extract from the source file: shared imports block (pykeen, models, etc.), all models and routes in the `mutations` section (MutationLogResponse, UndoRequest, `/knowledge-mutations/undo`, `/knowledge-mutations`). Keep the PyKEEN compat shim and LanceDB table constants here since they're used across modules — move them to a `_constants.py` if shared.

File header:
```python
"""Knowledge graph mutation log routes (undo/redo, audit log)."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity,
    MutationLog, MutationOperationType,
    ClaimType, EntityType,
)

router = APIRouter()
```

Then paste all mutation-related models and routes.

- [ ] **Step 4: Write entities.py**

Extract entity CRUD, merge, split, audit, alias operations (lines ~489–1180):
```python
"""Knowledge graph entity CRUD, merge, split, and alias routes."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    EntityMergeAudit, EntityMergeOperationType, EntityType,
    KnowledgeEntity,
)
from fichero.multilingual import normalize_text as multilingual_normalize

router = APIRouter()
```

- [ ] **Step 5: Write claims.py**

Extract claim CRUD + embedding routes (lines ~1181–1659):
```python
"""Knowledge graph claim CRUD, semantic embedding, and link routes."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    ClaimCurationState, ClaimRelationType, ClaimType,
    EpistemicStatus, InclusionScopeType,
    KnowledgeClaim, KnowledgeClaimLink, KnowledgeGraphInclusion,
)

KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"

router = APIRouter()
```

- [ ] **Step 6: Write predictions.py**

Extract PyKEEN prediction routes (lines ~1660–2090):
```python
"""Knowledge graph prediction routes (PyKEEN + heuristic)."""

from pathlib import Path
from typing import Any
import torch
import pykeen
import pykeen.models
from pykeen.pipeline import pipeline
from pykeen.predict import predict_target
from pykeen.triples import TriplesFactory
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    KnowledgePredictionRun, PredictionMetadata, PredictionModelType,
    KnowledgeEntity, KnowledgeClaim,
)

# PyKEEN compat shim
if not hasattr(pykeen.models.Model, "load_directory"):
    @classmethod
    def _load_directory_compat(cls, directory: str):
        model_file = Path(directory) / "trained_model.pkl"
        if not model_file.exists():
            raise FileNotFoundError(f"trained_model.pkl not found in {directory}")
        return torch.load(model_file, map_location="cpu")
    pykeen.models.Model.load_directory = _load_directory_compat

router = APIRouter()
```

- [ ] **Step 7: Write analysis.py**

Extract contradiction analysis and evidence chain routes (lines ~2091–2378):
```python
"""Knowledge graph analysis routes (contradictions, evidence chains)."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import (
    KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity,
)

router = APIRouter()
```

- [ ] **Step 8: Delete old flat file**
```bash
rm fichero-engine/src/fichero/api/routes/knowledge_graph.py
```

- [ ] **Step 9: Verify main.py import still works**

Check that `fichero-engine/src/fichero/api/main.py` imports `from fichero.api.routes.knowledge_graph import router` — this now resolves to the package `__init__.py` which is correct.

- [ ] **Step 10: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_knowledge_graph.py -v 2>&1 | tail -15
ruff check fichero-engine/src/fichero/api/routes/knowledge_graph/
```
Expected: all passing.
```bash
git add fichero-engine/src/fichero/api/routes/knowledge_graph/
git rm fichero-engine/src/fichero/api/routes/knowledge_graph.py
git commit -m "refactor: split knowledge_graph.py (2378 lines) into 5-module package (#460)"
```

---

## Task 3: Split workflow_execution.py (2188 lines)

**Natural split points:**
- Core execute/resume/status/stream (~lines 1–1095): keep in `workflow_execution.py`
- Thread history + list + delete (~lines 1095–1505): new `workflow_threads.py`
- Visualization + code export (~lines 1505–1890): new `workflow_visualization.py`
- Cache operations (~lines 1890–2188): new `workflow_cache.py`

**Files:**
- Modify: `fichero-engine/src/fichero/api/routes/workflow_execution.py` (keep ~1095 lines)
- Create: `fichero-engine/src/fichero/api/routes/workflow_threads.py`
- Create: `fichero-engine/src/fichero/api/routes/workflow_visualization.py`
- Create: `fichero-engine/src/fichero/api/routes/workflow_cache.py`
- Modify: `fichero-engine/src/fichero/api/main.py` (add new routers)

- [ ] **Step 1: Read workflow_execution.py fully** to understand shared helpers and which helpers each section needs.

- [ ] **Step 2: Write workflow_threads.py**

Header + shared imports + extract thread list/history/delete/run endpoints:
```python
"""Workflow thread management routes (list, history, delete, run info)."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.workflows.checkpointer import AsyncDuckDBCheckpointer
from fichero.workflows.activity import get_activity_tracker

logger = logging.getLogger(__name__)
router = APIRouter()
```

Paste: `ThreadListResponse`, `CheckpointSnapshot`, `CheckpointHistoryResponse`, and all routes `GET /threads`, `GET /threads/{id}/status`, `GET /threads/{id}/history`, `DELETE /threads/{id}`, `GET /threads/{id}/run`.

- [ ] **Step 3: Write workflow_visualization.py**

```python
"""Workflow visualization and code export routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.workflows.workflow_store import WorkflowStore
from fichero.workflows.builder import build_graph
from fichero.workflows.types import NodeDef, EdgeDef, WorkflowDef
from fichero.workflows.runtime import to_workflow_def

logger = logging.getLogger(__name__)
router = APIRouter()
```

Paste: `WorkflowVisualizationResponse`, `WorkflowCodeExportResponse`, and routes `GET /workflows/{id}/visualization`, `GET /workflows/{id}/visualization.png`, `GET /workflows/{id}/code`, `GET /threads/{id}/diagram.png`.

- [ ] **Step 4: Write workflow_cache.py**

```python
"""Workflow node result cache management routes."""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.workflows.cache import get_node_cache

logger = logging.getLogger(__name__)
router = APIRouter()
```

Paste: `CacheStatsResponse`, `CacheClearResponse`, and all `/cache` routes.

- [ ] **Step 5: Trim workflow_execution.py** to only contain: core models, SSE helpers, execute, resume, cancel, stream endpoints. Remove moved sections.

- [ ] **Step 6: Register new routers in main.py**

In `fichero-engine/src/fichero/api/main.py`, add imports and `app.include_router` calls for the three new routers under the same prefix as workflow_execution (likely `/api/workflow-execution` or similar — check current registration and match it).

- [ ] **Step 7: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_workflow_execution.py -v 2>&1 | tail -15
ruff check fichero-engine/src/fichero/api/routes/workflow_execution.py fichero-engine/src/fichero/api/routes/workflow_threads.py fichero-engine/src/fichero/api/routes/workflow_visualization.py fichero-engine/src/fichero/api/routes/workflow_cache.py
```
```bash
git add fichero-engine/src/fichero/api/routes/workflow_execution.py \
        fichero-engine/src/fichero/api/routes/workflow_threads.py \
        fichero-engine/src/fichero/api/routes/workflow_visualization.py \
        fichero-engine/src/fichero/api/routes/workflow_cache.py \
        fichero-engine/src/fichero/api/main.py
git commit -m "refactor: split workflow_execution.py (2188 lines) into 4 files (#460)"
```

---

## Task 4: Split mcp_server.py (2055 lines)

**Structure:** `FicheroAPIClient` + tool handlers (document, workflow, activity tools) + resource handlers + `main()`.

**Files:**
- Modify: `fichero-engine/src/fichero/mcp_server.py` (keep: server setup, tool/resource registration, main)
- Create: `fichero-engine/src/fichero/mcp_document_tools.py` (document + search + ingest tool handlers)
- Create: `fichero-engine/src/fichero/mcp_workflow_tools.py` (workflow + activity + action tool handlers)

- [ ] **Step 1: Read mcp_server.py fully** — identify exactly which tool handler functions fall into "document" vs "workflow/activity" categories by reading the `@server.call_tool` dispatch block.

- [ ] **Step 2: Write mcp_document_tools.py**

```python
"""MCP document and search tool handler implementations."""

from typing import Any
import mcp.types as types
# Import FicheroAPIClient — either re-export or move it here
```

Extract: `FicheroAPIClient` class, and handler functions for document-related tools (list_documents, get_document, search_documents, ingest_file, etc.).

- [ ] **Step 3: Write mcp_workflow_tools.py**

```python
"""MCP workflow and activity tool handler implementations."""

from typing import Any
import mcp.types as types
```

Extract: handler functions for workflow execution, activity monitoring, action running.

- [ ] **Step 4: Trim mcp_server.py** — import handler functions from the two new modules, keep only: `server = Server("fichero")`, `@server.list_tools`, `@server.call_tool` (dispatch only), `@server.list_resources`, `@server.read_resource`, and `main()`.

- [ ] **Step 5: Test + lint + commit**
```bash
ruff check fichero-engine/src/fichero/mcp_server.py fichero-engine/src/fichero/mcp_document_tools.py fichero-engine/src/fichero/mcp_workflow_tools.py
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_mcp_tools.py -v 2>&1 | tail -10
```
```bash
git add fichero-engine/src/fichero/mcp_server.py fichero-engine/src/fichero/mcp_document_tools.py fichero-engine/src/fichero/mcp_workflow_tools.py
git commit -m "refactor: split mcp_server.py (2055 lines) into server + document/workflow handler modules (#460)"
```

---

## Task 5: Extract db.py migrations (1447 lines)

**db.py has ~400 lines of `_migrate_*` methods** (lines ~1077–1366) that are called only from `__init__`. These are pure schema-migration logic with no external callers — perfect for extraction.

**Files:**
- Create: `fichero-engine/src/fichero/db_migrations.py`
- Modify: `fichero-engine/src/fichero/db.py` (remove migration methods, import and delegate)

- [ ] **Step 1: Create db_migrations.py**

```python
"""DuckDB schema migration helpers for the Fichero database.

Called exclusively from Database.__init__ during connection setup.
Each function receives a live duckdb connection and applies incremental
schema changes idempotently.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


def migrate_workflow_table(conn: "duckdb.DuckDBPyConnection") -> None:
    """Migrate workflow table schema."""
    # paste full body of _migrate_workflow_table here (without self)
    ...


def migrate_saved_search_table(conn: "duckdb.DuckDBPyConnection") -> None:
    """Migrate saved search table schema."""
    ...


def migrate_provider_refs_table(conn: "duckdb.DuckDBPyConnection") -> None:
    """Migrate provider refs table schema."""
    ...


def migrate_activity_tables(conn: "duckdb.DuckDBPyConnection") -> None:
    """Migrate activity tables schema."""
    ...


def migrate_checkpoint_tables(conn: "duckdb.DuckDBPyConnection") -> None:
    """Migrate checkpoint tables schema."""
    ...
```

Paste the actual migration bodies from `db.py`, removing the `self.` prefix and passing `conn` explicitly (since `self.conn` becomes just `conn`).

- [ ] **Step 2: Update db.py** — replace the 5 `_migrate_*` method bodies with one-liner delegations:

```python
from fichero.db_migrations import (
    migrate_workflow_table,
    migrate_saved_search_table,
    migrate_provider_refs_table,
    migrate_activity_tables,
    migrate_checkpoint_tables,
)

# In __init__ or wherever migrations are called:
def _migrate_workflow_table(self) -> None:
    migrate_workflow_table(self.conn)

def _migrate_saved_search_table(self) -> None:
    migrate_saved_search_table(self.conn)
# ... etc
```

- [ ] **Step 3: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_db.py -v 2>&1 | tail -15
ruff check fichero-engine/src/fichero/db.py fichero-engine/src/fichero/db_migrations.py
```
```bash
git add fichero-engine/src/fichero/db.py fichero-engine/src/fichero/db_migrations.py
git commit -m "refactor: extract db.py migration methods to db_migrations.py — reduces db.py from 1447 to ~1000 lines (#460)"
```

---

## Task 6: Split providers.py (1415 lines)

**Three natural sections:**
- Catalog + user provider CRUD (lines 1–616): keep in `providers.py`
- Per-type model listing — extremely long provider model routes (lines ~394–616): extract to `provider_models.py`
- API key management + connection test (lines ~930–1060): extract to `provider_keys.py`

- [ ] **Step 1: Read providers.py fully** to identify the exact line boundaries and shared models.

- [ ] **Step 2: Write provider_models.py**

```python
"""Provider model listing routes — enumerate models available per provider type."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.providers import get_available_models

logger = logging.getLogger(__name__)
router = APIRouter()
```

Extract: `ModelResponse`, `UserModelResponse`, and all `GET /models/{provider_type}` routes.

- [ ] **Step 3: Write provider_keys.py**

```python
"""Provider API key management and connection test routes."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.keychain import get_keychain

logger = logging.getLogger(__name__)
router = APIRouter()
```

Extract: `APIKeyRequest`, `ConnectionTestResponse`, and routes for `/{type}/api-key`, `/{type}/test`.

- [ ] **Step 4: Trim providers.py** and add `include_router` calls or register the new routers in `main.py`.

- [ ] **Step 5: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_providers.py -v 2>&1 | tail -15
ruff check fichero-engine/src/fichero/api/routes/providers.py fichero-engine/src/fichero/api/routes/provider_models.py fichero-engine/src/fichero/api/routes/provider_keys.py
```
```bash
git add fichero-engine/src/fichero/api/routes/providers.py fichero-engine/src/fichero/api/routes/provider_models.py fichero-engine/src/fichero/api/routes/provider_keys.py fichero-engine/src/fichero/api/main.py
git commit -m "refactor: split providers.py (1415 lines) into providers + provider_models + provider_keys (#460)"
```

---

## Task 7: Split graph_exploration.py (1259 lines)

**Two sections:**
- Path finding + neighborhood queries (lines ~1–855): keep in `graph_exploration.py`
- Traversal + interpretation views + subgraph (lines ~855–1259): new `graph_traversal.py`

**Files:**
- Modify: `fichero-engine/src/fichero/api/routes/graph_exploration.py`
- Create: `fichero-engine/src/fichero/api/routes/graph_traversal.py`
- Modify: `fichero-engine/src/fichero/api/main.py`

- [ ] **Step 1: Read graph_exploration.py** — identify shared models between sections (GraphNode, GraphEdge, etc. used in both halves).

- [ ] **Step 2: Write graph_traversal.py**

```python
"""Graph traversal, interpretation views, and subgraph routes."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.knowledge_models import KnowledgeEntity, KnowledgeClaim, KnowledgeClaimLink

router = APIRouter()
```

Extract: `TraverseRequest`, `TraversedNode`, `TraversedEdge`, `GraphTraversalResponse`, `InterpretationView`, `EntityInterpretationsResponse`, `SubgraphRequest` and their routes.

- [ ] **Step 3: Trim graph_exploration.py** to paths + neighborhood + metrics only.

- [ ] **Step 4: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_graph_exploration.py -v 2>&1 | tail -10
ruff check fichero-engine/src/fichero/api/routes/graph_exploration.py fichero-engine/src/fichero/api/routes/graph_traversal.py
```
```bash
git add fichero-engine/src/fichero/api/routes/graph_exploration.py fichero-engine/src/fichero/api/routes/graph_traversal.py fichero-engine/src/fichero/api/main.py
git commit -m "refactor: split graph_exploration.py (1259 lines) — extract traversal routes to graph_traversal.py (#460)"
```

---

## Task 8: Split workflows/activity.py (1249 lines)

**Three classes, clean boundaries:**
- Enums + dataclasses (lines 1–170): `activity_types.py`
- `ActivityStore` (lines 171–743): `activity_store.py`
- `ActivityTracker` + public API (lines 744–1249): keep in `activity.py`

**Files:**
- Create: `fichero-engine/src/fichero/workflows/activity_types.py`
- Create: `fichero-engine/src/fichero/workflows/activity_store.py`
- Modify: `fichero-engine/src/fichero/workflows/activity.py` (ActivityTracker + get_activity_tracker only)

- [ ] **Step 1: Write activity_types.py**

```python
"""Activity system enums and dataclasses (ActivityType, ActivityLevel, Activity, ActivityStats, ActivityFilter)."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
```

Paste all enum/dataclass definitions verbatim from the source.

- [ ] **Step 2: Write activity_store.py**

```python
"""ActivityStore — persistent DuckDB-backed activity log."""

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import Optional

import duckdb

from fichero.workflows.activity_types import (
    Activity, ActivityFilter, ActivityLevel, ActivityStats, ActivityType
)

logger = logging.getLogger(__name__)


class ActivityStore:
    ...
```

Paste the full `ActivityStore` class body.

- [ ] **Step 3: Rewrite activity.py** to import from the two new modules:

```python
"""ActivityTracker — high-level activity recording API.

Wraps ActivityStore with convenience methods and a global singleton per db_path.
"""

from fichero.workflows.activity_store import ActivityStore
from fichero.workflows.activity_types import (
    Activity, ActivityFilter, ActivityLevel, ActivityStats, ActivityType
)

__all__ = [
    "ActivityStore", "ActivityTracker",
    "Activity", "ActivityFilter", "ActivityLevel", "ActivityStats",
    "ActivityType", "get_activity_tracker", "close_activity_tracker",
]
```

Keep `ActivityTracker`, `get_activity_tracker`, `close_activity_tracker` in this file.

- [ ] **Step 4: Update imports** — search for any other file importing from `fichero.workflows.activity` and verify they still work (they should since `__all__` re-exports everything).
```bash
grep -r "from fichero.workflows.activity import\|from fichero.workflows import activity" fichero-engine/src/ --include="*.py" | grep -v "__pycache__"
```

- [ ] **Step 5: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_activity.py -v 2>&1 | tail -10
ruff check fichero-engine/src/fichero/workflows/activity.py fichero-engine/src/fichero/workflows/activity_store.py fichero-engine/src/fichero/workflows/activity_types.py
```
```bash
git add fichero-engine/src/fichero/workflows/activity.py fichero-engine/src/fichero/workflows/activity_store.py fichero-engine/src/fichero/workflows/activity_types.py
git commit -m "refactor: split workflows/activity.py (1249 lines) into types + store + tracker (#460)"
```

---

## Task 9: Split workflows/tools/llm_base.py (1078 lines)

**Two sections:**
- Config, output parsing, LLMResult (lines 1–580): keep in `llm_base.py`
- Prompt building helpers — `build_reference_section`, `match_to_reference`, `apply_reference_matching`, `build_thinking_preamble`, `build_context_section` (lines ~430–840): extract to `llm_prompting.py`

- [ ] **Step 1: Read llm_base.py fully** — note which functions are used by which tools.

- [ ] **Step 2: Write llm_prompting.py**

```python
"""LLM prompt construction helpers (reference sections, thinking preambles, context blocks).

Imported by llm_base.py and individual workflow tools that build complex prompts.
"""

from typing import Any


def build_reference_section(references: list[dict[str, Any]], ...) -> str:
    ...
```

Paste verbatim: `build_reference_section`, `match_to_reference`, `apply_reference_matching`, `build_thinking_preamble`, `build_context_section`.

- [ ] **Step 3: Update llm_base.py** — remove moved functions, add import:
```python
from fichero.workflows.tools.llm_prompting import (
    build_reference_section,
    match_to_reference,
    apply_reference_matching,
    build_thinking_preamble,
    build_context_section,
)
```

- [ ] **Step 4: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q 2>&1 | tail -5
ruff check fichero-engine/src/fichero/workflows/tools/llm_base.py fichero-engine/src/fichero/workflows/tools/llm_prompting.py
```
```bash
git add fichero-engine/src/fichero/workflows/tools/llm_base.py fichero-engine/src/fichero/workflows/tools/llm_prompting.py
git commit -m "refactor: split llm_base.py (1078 lines) — extract prompt helpers to llm_prompting.py (#460)"
```

---

## Task 10: Split workflows/registry.py (1062 lines)

**Two sections:**
- Public API: `register_tool`, `get_tool`, `get_tool_def`, `list_tools`, etc. (lines 1–242)
- `_register_builtin_tools()` — the 800-line function registering all 30+ tools (lines 248–1062)

**Files:**
- Modify: `fichero-engine/src/fichero/workflows/registry.py` (keep public API + thin `_register_builtin_tools` that delegates)
- Create: `fichero-engine/src/fichero/workflows/registry_builtins.py`

- [ ] **Step 1: Write registry_builtins.py**

```python
"""Built-in tool registration for the Fichero workflow registry.

Called once at startup from registry.py. Registers all 30+ built-in workflow tools.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.workflows.registry import register_tool


def register_builtin_tools(register_tool_fn) -> None:
    """Register all built-in tools. Called from registry._register_builtin_tools()."""
    register_fn = register_tool_fn
    # paste full body of _register_builtin_tools here, replacing `register_tool(` with `register_fn(`
    ...
```

- [ ] **Step 2: Trim registry.py** `_register_builtin_tools`:

```python
from fichero.workflows.registry_builtins import register_builtin_tools

def _register_builtin_tools():
    register_builtin_tools(register_tool)
```

- [ ] **Step 3: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q 2>&1 | tail -5
ruff check fichero-engine/src/fichero/workflows/registry.py fichero-engine/src/fichero/workflows/registry_builtins.py
```
```bash
git add fichero-engine/src/fichero/workflows/registry.py fichero-engine/src/fichero/workflows/registry_builtins.py
git commit -m "refactor: extract registry built-in registrations to registry_builtins.py — reduces registry.py to ~250 lines (#460)"
```

---

## Task 11: Split llm.py (1056 lines)

**Three sections:**
- Core LLM complete/stream + LLMConfig + key resolution (lines 1–470): keep in `llm.py`
- Embeddings (`_get_langchain_embeddings`, `embed`) (lines 470–580): extract to `llm_embeddings.py`
- Model info + cost estimation + provider listing (lines 580–1056): extract to `llm_models.py`

**Files:**
- Modify: `fichero-engine/src/fichero/llm.py`
- Create: `fichero-engine/src/fichero/llm_embeddings.py`
- Create: `fichero-engine/src/fichero/llm_models.py`

- [ ] **Step 1: Write llm_embeddings.py**

```python
"""LLM embedding functions — text-to-vector via LangChain/LiteLLM."""

from typing import Any

from fichero.llm import LLMConfig, _resolve_api_key


def _get_langchain_embeddings(config: LLMConfig):
    ...

def embed(text: str | list[str], config: LLMConfig) -> list[float] | list[list[float]]:
    ...
```

- [ ] **Step 2: Write llm_models.py**

```python
"""LLM model metadata — capabilities, cost estimation, provider model lists."""

from typing import Any


def get_model_info(model: str) -> dict[str, Any] | None:
    ...

def get_model_cost(model: str) -> dict[str, float] | None:
    ...

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    ...

def list_models_for_provider(provider: str) -> list[dict[str, Any]]:
    ...
```

- [ ] **Step 3: Update llm.py** — remove moved functions, add re-exports for backward compat:
```python
from fichero.llm_embeddings import _get_langchain_embeddings, embed  # noqa: F401
from fichero.llm_models import get_model_info, get_model_cost, estimate_cost, list_models_for_provider  # noqa: F401
```

- [ ] **Step 4: Check callers** — grep for `from fichero.llm import` and verify each caller still works:
```bash
grep -r "from fichero.llm import\|from fichero import llm" fichero-engine/src/ --include="*.py" | grep -v __pycache__
```

- [ ] **Step 5: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q 2>&1 | tail -5
ruff check fichero-engine/src/fichero/llm.py fichero-engine/src/fichero/llm_embeddings.py fichero-engine/src/fichero/llm_models.py
```
```bash
git add fichero-engine/src/fichero/llm.py fichero-engine/src/fichero/llm_embeddings.py fichero-engine/src/fichero/llm_models.py
git commit -m "refactor: split llm.py (1056 lines) into llm + llm_embeddings + llm_models (#460)"
```

---

## Task 12: Split api/routes/research_agents.py (1034 lines)

**Four natural CRUD groups:**
- Projects (lines ~52–141)
- Plans + Tasks + Steps (lines ~142–388)
- Sources + Notes + Checklists (lines ~388–770)
- External tools (web-search, browser-navigate) (lines ~770–1034)

**Files:**
- Create: `fichero-engine/src/fichero/api/routes/research_projects.py`
- Create: `fichero-engine/src/fichero/api/routes/research_tasks_steps.py`
- Create: `fichero-engine/src/fichero/api/routes/research_notes.py`
- Create: `fichero-engine/src/fichero/api/routes/research_tools_routes.py`
- Modify: `fichero-engine/src/fichero/api/main.py` (replace single router with 4)
- Delete: `fichero-engine/src/fichero/api/routes/research_agents.py`

Each new file follows the same pattern:
```python
"""Research [entity] CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.research_models import ResearchProject, ResearchPlan, ...

router = APIRouter()
```

- [ ] **Step 1: Read research_agents.py fully** to understand shared models and which models each section needs.

- [ ] **Step 2: Write all 4 new route files** — paste the appropriate models and routes into each.

- [ ] **Step 3: Update main.py** — replace the `research_agents` router with the 4 new routers, using the same prefix.

- [ ] **Step 4: Delete old file**
```bash
git rm fichero-engine/src/fichero/api/routes/research_agents.py
```

- [ ] **Step 5: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_research_agents.py -v 2>&1 | tail -15
ruff check fichero-engine/src/fichero/api/routes/research_projects.py fichero-engine/src/fichero/api/routes/research_tasks_steps.py fichero-engine/src/fichero/api/routes/research_notes.py fichero-engine/src/fichero/api/routes/research_tools_routes.py
```
```bash
git add fichero-engine/src/fichero/api/routes/research_projects.py \
        fichero-engine/src/fichero/api/routes/research_tasks_steps.py \
        fichero-engine/src/fichero/api/routes/research_notes.py \
        fichero-engine/src/fichero/api/routes/research_tools_routes.py \
        fichero-engine/src/fichero/api/main.py
git rm fichero-engine/src/fichero/api/routes/research_agents.py
git commit -m "refactor: split research_agents.py (1034 lines) into 4 focused route files (#460)"
```

---

## Task 13: Review storage.py (1004 lines — borderline)

storage.py is at 1004 lines but has two clearly separable sections already visible in the grep output:
- Thumbnail/display generation, cleanup, stats (lines 1–677)
- Library snapshot operations (lines ~678–1004)

- [ ] **Step 1: Read storage.py lines 675–1004** to determine if `snapshot_library` and related functions warrant a split or if the file is coherent enough to leave as-is given the 1000-line threshold.

- [ ] **Step 2 (if splitting):** Create `storage_library.py` with snapshot/export functions.

- [ ] **Step 3: Test + lint + commit**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/test_routes_storage.py -v 2>&1 | tail -10
ruff check fichero-engine/src/fichero/storage.py
```
```bash
git add fichero-engine/src/fichero/storage.py
# Add storage_library.py if split was done
git commit -m "refactor: storage.py — split library snapshot functions to storage_library.py (#460)"
```

---

## Task 14: Final verification

- [ ] **Step 1: Full test suite**
```bash
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q 2>&1 | tail -10
```
Expected: all tests passing (was 1774 passing before; should be same or more).

- [ ] **Step 2: Lint everything**
```bash
ruff check fichero-engine/src/
```
Expected: zero errors.

- [ ] **Step 3: Verify no file exceeds 1000 lines**
```bash
find fichero-engine/src/fichero -name "*.py" | xargs wc -l | sort -rn | head -20
```
Expected: all files < 1000 lines.

- [ ] **Step 4: Close issue**
```bash
gh issue comment 460 --body "All Phase 2 file splits complete. All files under 1000-line hard limit. 1774+ tests passing."
```
