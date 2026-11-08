"""One audited action per image operation (`image.ops.one-action-per-operation`, #6363).

Every name a page's edit chain accepts (`_OPERATION_MODELS`, `_PARAMETERLESS_OPERATIONS`) is an action `image.<name>`; the ones
that had a route and a hand-written action (rotate, straighten, crop, enhance, remove_background, segment, square, mark_blank)
keep it, and the rest are made here by one loop over the vocabulary, so a new chain name gets its action without a decorator.
Each writes exactly one chain row through `_render_and_append`, the path the editor's `PUT /edits` row already takes, and
`undo` puts the chain back as it was (`image.set_operations`). Imported last by `image_editing.py` so they register with the rest.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, create_model

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.routes.ingest.image_editing import (
    _OPERATION_MODELS,
    _PARAMETERLESS_OPERATIONS,
    _chain_ops_snapshot,
    _chain_result,
    _get_or_404_document,
    _image_chain_spec,
    _invert_image_chain,
    _render_and_append,
    _resolve_source_and_page,
)
from fastapi import Depends, HTTPException

from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database_for_write
from fichero_server.api.routes.ingest.image_editing import router
from fichero_server.db import Database


def _register(name: str, request_model: type[BaseModel]) -> None:
    params_model = create_model(
        f"{name.title().replace('_', '')}ImageActionParams", __base__=request_model, document_id=(str, ...), who=(str, "person")
    )

    def run(db: Database, params, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
        before = _chain_ops_snapshot(db, params.document_id)
        doc = _get_or_404_document(db, params.document_id)
        source_path, page = _resolve_source_and_page(db, doc, params.page)
        settings = params.model_dump(mode="json", exclude={"document_id", "page", "who"})
        chain = _render_and_append(db, params.document_id, source_path, {"op": name, "page": page, "params": settings, "who": params.who}, page)
        return _chain_result(chain), _image_chain_spec(params.document_id, before, [dict(op) for op in chain.operations])

    run.__name__ = f"_action_{name}"
    action(f"image.{name}", params_model, domains=["image"], undoable=True, invert=_invert_image_chain)(run)


class _PageOnly(BaseModel):
    page: int = Field(1, ge=1)


for _name in sorted(_OPERATION_MODELS.keys() | _PARAMETERLESS_OPERATIONS):
    if f"image.{_name}" not in registry.names():
        _register(_name, _OPERATION_MODELS.get(_name, _PageOnly))


class ImageOperationJobRequest(BaseModel):
    action: str = Field(description="An `image.<op>` action that takes a `document_id`, e.g. `image.remove_background`.")
    params: dict = Field(default_factory=dict, description="The action's settings; the page comes from the path.")


class ImageOperationJob(BaseModel):
    job_id: str


@router.post("/{document_id}/jobs", response_model=ImageOperationJob, status_code=202)
async def queue_image_operation_job(
    document_id: str,
    request: ImageOperationJobRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ImageOperationJob:
    """Ask for an image operation as a job (`image.ops.long-operation-is-a-job`, #6384): returns the job id at once; the operation
    runs on the images lane, reports through Activity, and is cancelled as any job is. The same action as the direct route."""
    import asyncio

    from fichero_server.image_op_job import queue_image_operation

    if not request.action.startswith("image.") or request.action not in registry.names():
        raise HTTPException(422, f"Not an image operation: {request.action}")
    params = {**request.params, "document_id": document_id}
    model = registry.get(request.action).params_model
    if "document_id" not in model.model_fields:
        raise HTTPException(422, f"{request.action} does not act on one page")
    try:
        model.model_validate(params)
    except Exception as exc:
        raise HTTPException(422, f"Invalid settings for {request.action}: {exc}") from exc
    _get_or_404_document(db, document_id)
    job_id = await asyncio.to_thread(queue_image_operation, db, request.action, params, started_by=ctx.actor)
    return ImageOperationJob(job_id=job_id)
