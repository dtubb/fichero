"""MCP Tools Routes

The one MCP-only endpoint: an agent's verdict on a proposal. The knowledge entity/claim wrappers that stood here
duplicated `/api/entities` and `/api/claims` and are retired (`research.mcp-knowledge-endpoints-unwired`, #1439).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.main import get_library_database_for_write
from fichero_server.api.auth import request_actor
from fichero_server.api.routes.auth.accounts import _require_authenticated_or_bootstrap
from fichero_server.db import Database

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["mcp-tools"],
    dependencies=[Depends(_require_authenticated_or_bootstrap)],
)


class MCPCheckVerdictRequest(BaseModel):
    """An agent's verdict on one proposal (`source.check.*`). No trust and no checker: the server's."""

    model_config = ConfigDict(extra="forbid")

    layer: str = Field(description="readings, claims or entities")
    target_id: str
    verdict: str = Field(description="confirm, correct or reject")
    reasons: str
    correction: dict[str, Any] | None = None
    segment_id: str | None = None


@router.post("/check/verdicts")
async def mcp_check_verdict(
    request: MCPCheckVerdictRequest,
    db: Database = Depends(get_library_database_for_write),
    actor: str = Depends(request_actor),
) -> dict[str, Any]:
    """MCP tool endpoint: record an agent's verdict through `check.verdict`, the same action a person's goes
    through. Written from this route, so it is an agent's: trust `model`, never a person's
    (`source.check.model-never-a-person`), and a reject moves a statement no further than `shortlisted`."""
    from pathlib import Path

    import fichero_server.api.routes.check  # noqa: F401  (registers check.verdict)

    ctx = ActionContext(actor=actor, library_path=str(Path(db.path).parent), via_mcp=True)
    try:
        return registry.invoke(db, "check.verdict", request.model_dump(), ctx).result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
