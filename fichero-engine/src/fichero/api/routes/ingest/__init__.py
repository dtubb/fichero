"""fichero.api.routes.ingest package — ingest.py moved to ingest/core.py (#2569)."""
from fichero.api.routes.ingest.core import *  # noqa
# `import *` only re-exports public names; restore private symbols reached by
# tests directly (budget-neutral: core.py already loads for router registration).
from fichero.api.routes.ingest.core import (  # noqa: F401
    _ingest_action_context,
    _MAX_TERMINAL_TASKS,
    _prune_tasks,
    _tasks,
    _TASK_TTL_SECONDS,
)
