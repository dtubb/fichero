"""Consolidated knowledge-layer package."""

# knowledge_models.py / hermeneutics_models.py relocated to fichero_server.models/
# (#2566: single models/ package) and their local alias modules were deleted in
# #4078. Import from fichero_server.models.knowledge / models.hermeneutics
# directly; this package only re-exports the knowledge models for convenience.
from fichero_server.models.knowledge import *  # noqa: F403
