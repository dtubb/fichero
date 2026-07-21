"""Research Agents API routes (dev tier, Layer 0 — Agent Research).

Sub-routers:
  research_crud   — Project / Plan / Task / Step CRUD
  research_notes  — Search Sources / Notes / Checklists
  research_tools  — Sandboxed web-search, browser-navigate, document-fetch
"""

from fastapi import APIRouter

from fichero.api.routes.research.crud import router as crud_router
from fichero.api.routes.research.notes import router as notes_router
from fichero.api.routes.research.tools import router as tools_router

router = APIRouter()

router.include_router(crud_router)
router.include_router(notes_router)
router.include_router(tools_router)
