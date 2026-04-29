"""Knowledge graph API routes — combined router from sub-modules.

Split by responsibility:
  mutations  — mutation log undo/list
  entities   — entity CRUD, merge, split, audit, semantic search
  claims     — claims CRUD, links, inclusion, overview, semantic search
  predictions — PyKEEN training + heuristic predictions
  analysis   — contradiction evidence and evidence chains
"""

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
