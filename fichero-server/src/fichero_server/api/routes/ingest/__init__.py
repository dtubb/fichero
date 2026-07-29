"""fichero_server.api.routes.ingest package — ingest.py moved to ingest/core.py (#2569)."""
from fichero_server.api.routes.ingest.core import *  # noqa
# `import *` only re-exports public names; restore private symbols reached by
# tests directly (budget-neutral: core.py already loads for router registration).
#
# Note: `_tasks` (the mutable task-registry dict) is deliberately NOT re-exported
# here — it lives on `ingest.core` and tests that monkeypatch it must target
# `ingest.core._tasks`, since a separate binding here would go stale on patch.
from fichero_server.api.routes.ingest.core import (  # noqa: F401
    _ingest_action_context,
    _MAX_TERMINAL_TASKS,
    _prune_tasks,
    _TASK_TTL_SECONDS,
)
