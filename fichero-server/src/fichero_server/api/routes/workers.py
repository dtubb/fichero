"""Dev workers from the API (dev-workflows.run.worker-start-stop, #6116): start a worker process, stop it, tell it.

Dev tier only (`features.yaml`, devWorkers). The work is `workflows.worker_process`; each call is an audited action.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database_for_write
from fichero_server.db import Database

router = APIRouter(prefix="/workers")

# The actions exist only on a dev-tier engine (devWorkers in features.yaml): `/api/actions/invoke` has no tier of
# its own and runs any registered name, so a release engine must not register them at all. Owner of the app only.
DEV = os.environ.get("FICHERO_FEATURE_TIER", "release").strip().lower() == "dev"


def _dev_action(name, model):
    def wrap(fn):
        if not DEV:
            return fn
        return action(name, model, domains=["job"], undoable=False, owner_only=True, owner_scope="app")(fn)
    return wrap


class WorkerStartParams(BaseModel):
    kind: str
    brief: str
    workdir: str
    timeout_s: float
    scenario: dict[str, Any] | None = None
    tmux_session: str = ""
    model: str = "sonnet"
    task: str = ""


class WorkerStopParams(BaseModel):
    job_id: str


class WorkerTellParams(BaseModel):
    task: str
    generation: int
    text: str


@_dev_action("worker.start", WorkerStartParams)
def _action_start(db: Database, params: WorkerStartParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.workflows import worker_process as wp

    job_id = wp.start(db, **params.model_dump())
    return {"job_id": job_id}, ChangeSpec(domains=["job"], target_ids=[job_id], after={"job_id": job_id, "kind": wp.KIND},
                                          emit_type="job.created")


@_dev_action("worker.stop", WorkerStopParams)
def _action_stop(db: Database, params: WorkerStopParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.workflows import worker_process as wp

    state = wp.stop(db, params.job_id)
    return {"job_id": params.job_id, "state": state}, ChangeSpec(
        domains=["job"], target_ids=[params.job_id], after={"job_id": params.job_id, "state": state}, emit_type="job.updated")


@_dev_action("worker.tell", WorkerTellParams)
def _action_tell(db: Database, params: WorkerTellParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.workflows import worker_process as wp

    wp.tell(db, params.task, params.generation, params.text)
    return {"task": params.task, "generation": params.generation}, ChangeSpec(domains=["job"], target_ids=[params.task])


def _invoke(db: Database, name: str, params: BaseModel, ctx: ActionContext) -> dict:
    from fichero_server.workflows.worker_process import StaleWorker

    try:
        return registry.invoke(db, name, params.model_dump(), ctx).result
    except StaleWorker as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", summary="Start a dev worker process, recorded as a job row")
async def start_worker(params: WorkerStartParams, db: Database = Depends(get_library_database_for_write),
                       ctx: ActionContext = Depends(action_context)) -> dict[str, str]:
    """Start a worker of `kind` (`claude` in a tmux window, or `fake`) in `workdir`. Through `worker.start`."""
    return _invoke(db, "worker.start", params, ctx)


@router.post("/tell", summary="Type a message into a task's current worker; refused for a stale generation")
async def tell_worker(params: WorkerTellParams, db: Database = Depends(get_library_database_for_write),
                      ctx: ActionContext = Depends(action_context)) -> dict[str, Any]:
    """Through `worker.tell`: 409 when `generation` is not the task's current worker."""
    return _invoke(db, "worker.tell", params, ctx)


@router.post("/{job_id}/stop", summary="Stop a worker: its whole process group")
async def stop_worker(job_id: str, db: Database = Depends(get_library_database_for_write),
                      ctx: ActionContext = Depends(action_context)) -> dict[str, str]:
    """Through `worker.stop`."""
    return _invoke(db, "worker.stop", WorkerStopParams(job_id=job_id), ctx)
