"""Workflow execution routes package.

Combines five sub-modules:
- core: execute, stream, resume, status
- threads: history, list, delete, run data
- comparison: diff two runs of the same input (#4341)
- visualization: Mermaid diagrams, PNG, Python code export
- cache: node result cache management
"""

from fastapi import APIRouter

from .core import router as core_router
from .threads import router as threads_router
from .comparison import router as comparison_router
from .visualization import router as visualization_router
from .cache import router as cache_router

router = APIRouter()
router.include_router(core_router)
router.include_router(threads_router)
router.include_router(comparison_router)
router.include_router(visualization_router)
router.include_router(cache_router)

__all__ = ["router"]
