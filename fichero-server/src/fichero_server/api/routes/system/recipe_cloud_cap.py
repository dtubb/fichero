"""The route that changes the project's cloud spend caps in place (#6295, `ai.where.cloud-spend-cap`): its own module, because
`recipes.py` is over a thousand lines. Registered under the same `/api/recipes` prefix and tag, so the contract is as it was."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database_for_write
from fichero_server.api.routes.document.format_import import ErrorDetail as _ErrorDetail
from fichero_server.api.routes.system.recipes import _library, normalise_answers, read_project_setup
from fichero_server.db import Database
from fichero_server.recipes.cloud_cap import CloudCapChange, CloudCapChanged

router = APIRouter(prefix="/recipes")


@router.put("/project/cloud-cap", response_model=CloudCapChanged, responses={422: {"model": _ErrorDetail,
                    "description": "the cap is refused, in one sentence"}})
async def change_cloud_cap(
    request: CloudCapChange,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> CloudCapChanged:
    """Set the project's monthly cloud cap (`answers.cloud_spend_cap_usd`) and/or its total cap
    (`answers.cloud_project_cap_usd`), and nothing else in its setup: Set Up's "Raise the cap to N" (#6295). One
    `project.save_setup`, so audited and undoable as one step; the answer names the audit row."""
    from fichero_server.llm import spend

    answers = dict(read_project_setup(_library(db)).get("answers") or {})
    if request.cap_usd is not None:
        answers[spend.CAP_KEY] = request.cap_usd
    if request.project_cap_usd is not None:
        answers[spend.PROJECT_CAP_KEY] = request.project_cap_usd
    if request.clear_project_cap:
        answers.pop(spend.PROJECT_CAP_KEY, None)
    try:
        done = registry.invoke(db, "project.save_setup", {"answers": normalise_answers(answers, strict=True)}, ctx)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CloudCapChanged(cap_usd=spend.cap_usd(str(_library(db))) or 0.0, project_cap_usd=spend.project_cap_usd(str(_library(db))),
                           audit_id=done.audit_id)
