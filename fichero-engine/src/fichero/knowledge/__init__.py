"""Consolidated knowledge-layer package."""

# knowledge_models.py / hermeneutics_models.py relocated to fichero.models/
# (#2566, the user's 2026-07-21 ruling: single models/ package). Import from
# the new canonical location directly rather than bouncing through the
# local knowledge_models.py shim.
from fichero.models.knowledge import *  # noqa: F403
