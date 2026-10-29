"""A scope's template and its saved column choice (attributes-and-prototypes.md §3).

A template is the effective prototype's columns; the table and the export read it here. A person may
narrow a scope's columns (hide some, or show one kind's only): that is saved on the scope node as a
view (``metadata.column_choice``), never on a prototype, and ⌘Z undoes it (a snapshot restore).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.documents import (
    _document_or_404,
    _invert_document_prototype_snapshot,
    _run_document_write,
)
from fichero_server.db import Database
from fichero_server.models import Document
from fichero_server.models.prototype_template import apply_choice, template_for_rows

router = APIRouter()

CHOICE_KEY = "column_choice"


class ColumnChoice(BaseModel):
    hide: list[str] = Field(default_factory=list, description="Column keys left out of the table and the export.")
    only_kind: str | None = Field(None, description="Show this prototype's columns only.")


class TemplateColumn(BaseModel):
    key: str
    kind: str
    type: str = "text"
    source: str | None = None
    labels: dict[str, str] = {}
    label: str | None = None
    help: dict[str, str] = {}
    join: str | None = None
    format: str | None = None
    name_order: str | None = None
    inherits: bool = False
    months: dict[str, list[str]] = {}
    options: list[str] = []
    option_labels: dict[str, dict[str, str]] = {}
    group: str | None = None


class ScopeTemplate(BaseModel):
    columns: list[TemplateColumn]
    mixed: bool
    prototypes: list[str]
    choice: ColumnChoice | None = None


def _stored_choice(doc: Document) -> dict[str, Any] | None:
    found = (doc.metadata or {}).get(CHOICE_KEY)
    return found if isinstance(found, dict) and (found.get("hide") or found.get("only_kind")) else None


@router.get("/{doc_id}/template", response_model=ScopeTemplate)
async def get_scope_template(doc_id: str, db: Database = Depends(get_library_database)) -> ScopeTemplate:
    """The columns of a scope: its rows' effective prototype (the union when they differ), narrowed by the saved choice."""
    scope = _document_or_404(db, doc_id)
    rows = [d for d in db.query(Document, parent_id=scope.id) if d.deleted_at is None]
    rows.sort(key=lambda d: (d.sequence if d.sequence is not None else 0, d.name or ""))
    choice = _stored_choice(scope)
    template = apply_choice(db, template_for_rows(db, rows), choice)
    return ScopeTemplate(
        columns=[TemplateColumn(**vars(c)) for c in template.columns],
        mixed=template.mixed,
        prototypes=template.prototypes,
        choice=ColumnChoice(**choice) if choice else None,
    )


class ColumnChoiceAnswer(ScopeTemplate):
    """The scope's template after a choice, and the audited action that saved it (⌘Z undoes that row)."""

    audit_id: str | None = Field(None, description="The audited action: undoing it puts the previous choice back.")


async def _choose(doc_id: str, choice: dict[str, Any] | None, db: Database, ctx: ActionContext) -> ColumnChoiceAnswer:
    result = await _run_document_write(
        registry.invoke, db, "document.set_column_choice", {"doc_id": doc_id, "choice": choice}, ctx
    )
    template = await get_scope_template(doc_id, db)
    return ColumnChoiceAnswer(**template.model_dump(), audit_id=result.audit_id)


class ColumnChoiceParams(BaseModel):
    doc_id: str = Field(description="The scope node the choice is saved on")
    choice: ColumnChoice | None = Field(None, description="None clears the choice (back to the union)")


@action(
    "document.set_column_choice",
    ColumnChoiceParams,
    domains=["document"],
    undoable=True,
    invert=_invert_document_prototype_snapshot,
)
def _action_set_column_choice(db: Database, params: ColumnChoiceParams, ctx: ActionContext) -> tuple[dict, ChangeSpec]:
    from fichero_server.core.timeutil import utc_now

    scope = _document_or_404(db, params.doc_id)
    before = scope.model_dump(mode="json")
    meta = dict(scope.metadata or {})
    if params.choice and (params.choice.hide or params.choice.only_kind):
        meta[CHOICE_KEY] = params.choice.model_dump(mode="json")
    else:
        meta.pop(CHOICE_KEY, None)
    scope.metadata = meta
    scope.updated_at = utc_now()
    db.save(scope)
    spec = ChangeSpec(
        domains=["document"], target_ids=[scope.id], before={"documents": [before]},
        after={"document_ids": [scope.id]}, emit_type="document.updated", document_ids=[scope.id],
    )
    return {"document_id": scope.id, "choice": meta.get(CHOICE_KEY)}, spec


@router.put("/{doc_id}/column-choice", response_model=ColumnChoiceAnswer)
async def put_column_choice(
    doc_id: str,
    choice: ColumnChoice,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ColumnChoiceAnswer:
    return await _choose(doc_id, choice.model_dump(mode="json"), db, ctx)


@router.delete("/{doc_id}/column-choice", response_model=ColumnChoiceAnswer)
async def clear_column_choice(
    doc_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ColumnChoiceAnswer:
    return await _choose(doc_id, None, db, ctx)
