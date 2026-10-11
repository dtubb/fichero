"""A project's Trash: what is in it and why, Put Back, and Empty Trash (`safety/trash.md`, #2077, #5243).

Each project is one database, so its Trash is that database's soft-deleted documents
(`safety.trash.one-per-project`). The routes live on the documents router
(`GET /api/documents/trash`, `POST /api/documents/{id}/restore`, `GET|POST /api/documents/trash/empty`);
the rules live here.

* **One item per thing deleted** (`safety.trash.lists-what-and-why`). A delete stamps one
  ``deleted_at`` on a whole subtree, so a trashed document is listed on its own only when its
  parent is live, gone, or was trashed LATER than it; otherwise it is counted in the item above.
* **Why**: deleted, or moved to another project. A move between projects soft-deletes its
  source through ``document.delete`` with ``moved_to`` (``DocumentDeleteParams.moved_to``:
  ``{project, transfer_id}``); the newest live ``document.delete`` row that trashed an item is
  read for it, and its time is the date of the move.
* **Put Back** (`safety.trash.put-back`) returns the item and what was deleted with it into its
  old folder, or into the project's Sources folder when that folder is in the Trash or gone.
* **Empty Trash** (`safety.trash.empty-is-one-step`, `safety.trash.empty-names-moved-items`) is
  one recorded action over everything in the Trash, snapshot first, with a preview that counts
  what will go and names the items a move sent here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from fichero_server.models import ActionAudit, DocType, Document

FromFolderState = Literal["top", "live", "in-trash", "gone"]


class TrashMovedTo(BaseModel):
    """Why a move's source is in the Trash: written by the transfer on its ``document.delete``."""

    project: str = Field(description="The project the items were moved to, by its name")
    transfer_id: str | None = Field(default=None, description="The transfer that moved them")


class TrashItem(BaseModel):
    id: str
    name: str
    doc_type: DocType
    deleted_at: datetime | None
    deleted_by: str | None
    item_count: int = Field(description="How many things inside it were deleted with it")
    from_folder_id: str | None = Field(description="The folder it was in")
    from_folder_path: str | None = Field(description="That folder's path, while the folder is live")
    from_folder_state: FromFolderState = Field(
        description="top: it was at the top of the project; live; in-trash: its folder is in the Trash too; gone"
    )
    from_where: str = Field(description="Where it was, in words")
    reason: Literal["deleted", "moved", "taken_back"]
    moved_to_project: str | None = None
    moved_on: datetime | None = None
    transfer_id: str | None = None
    why: str = Field(description="Why it is in the Trash, in words")
    document: Document


class TrashListResponse(BaseModel):
    items: list[TrashItem]
    count: int = Field(description="Items in this page")
    total: int = Field(description="Items in the Trash that this caller may see")
    withheld: int = 0


class PutBackResponse(BaseModel):
    restored_document_ids: list[str]
    folder_id: str | None = Field(description="Where it went back to; null is the top of the project")
    folder_name: str | None
    into_sources: bool = Field(description="True when its own folder could not take it back")
    folder_in_trash_id: str | None = Field(
        default=None, description="Its old folder, when that folder is in the Trash (offer to put it back too)"
    )
    message: str


class MovedGroup(BaseModel):
    project: str
    count: int
    moved_on: datetime | None
    sentence: str


class EmptyTrashPreview(BaseModel):
    items: int = Field(description="Things in the Trash, each counted once")
    documents: int = Field(description="Every document, page and folder that will be removed")
    statements: int = Field(description="Statements that rest on them and go with them")
    moved: list[MovedGroup] = Field(default_factory=list)
    sentence: str = Field(description="The question to ask before emptying")


class EmptyTrashResult(EmptyTrashPreview):
    deleted_document_ids: list[str] = Field(default_factory=list)
    entities_pruned: int = 0


# ---------------------------------------------------------------------------
# reading the Trash


def _all_documents(db: Any) -> dict[str, Document]:
    from fichero_server.api.routes.document.documents import _list_documents_raw

    return {doc.id: doc for doc in _list_documents_raw(db)}


def _is_top_level(doc: Document, by_id: dict[str, Document]) -> bool:
    parent = by_id.get(doc.parent_id) if doc.parent_id else None
    if parent is None or parent.deleted_at is None:
        return True
    return bool(doc.deleted_at and parent.deleted_at > doc.deleted_at)


def _top_level_of(doc: Document, by_id: dict[str, Document]) -> Document:
    current, seen = doc, set()
    while not _is_top_level(current, by_id) and current.id not in seen:
        seen.add(current.id)
        current = by_id[current.parent_id]
    return current


def trashed_items(db: Any) -> tuple[list[Document], dict[str, int], dict[str, Document]]:
    """The Trash's top-level documents (newest first), how many each carries, and every row."""
    by_id = _all_documents(db)
    trashed = [doc for doc in by_id.values() if doc.deleted_at is not None]
    tops: dict[str, Document] = {}
    counts: dict[str, int] = {}
    for doc in trashed:
        top = _top_level_of(doc, by_id)
        tops[top.id] = top
        if top.id != doc.id:
            counts[top.id] = counts.get(top.id, 0) + 1
    ordered = sorted(tops.values(), key=lambda d: (d.deleted_at, d.id), reverse=True)
    return ordered, counts, by_id


def deleted_with(db: Any, root: Document) -> list[str]:
    """The root and every descendant deleted with it (not one trashed on its own earlier)."""
    from fichero_server.api.routes.document.documents import (
        _descendant_document_ids,
        _get_document_row,
    )

    ids = []
    for doc_id in _descendant_document_ids(db, root.id, include_deleted=True):
        doc = _get_document_row(db, doc_id, include_deleted=True)
        if doc is None or doc.deleted_at is None:
            continue
        if doc.id == root.id or root.deleted_at is None or doc.deleted_at >= root.deleted_at:
            ids.append(doc.id)
    return ids


def _folder_path(folder: Document, by_id: dict[str, Document]) -> str:
    names, current, seen = [], folder, set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names.append(current.name)
        current = by_id.get(current.parent_id) if current.parent_id else None
    return " / ".join(reversed(names))


def _from_where(doc: Document, by_id: dict[str, Document]) -> tuple[FromFolderState, str | None, str]:
    if not doc.parent_id:
        return "top", None, "The top of the project"
    parent = by_id.get(doc.parent_id)
    if parent is None:
        return "gone", None, "A folder now gone"
    if parent.deleted_at is not None:
        return "in-trash", None, f"{parent.name}, a folder now in the Trash"
    path = _folder_path(parent, by_id)
    return "live", path, path


def _date_words(when: datetime | None) -> str:
    return f"{when.day} {when.strftime('%b %Y')}" if when else "an earlier date"


def moved_reasons(db: Any, doc_ids: list[str]) -> dict[str, tuple[TrashMovedTo, datetime]]:
    """For each id, the move that sent it to the Trash, if its newest live delete was a move."""
    if not doc_ids:
        return {}
    wanted = set(doc_ids)
    newest: dict[str, ActionAudit] = {}
    for row in db.query_json_list_intersects(ActionAudit, "target_ids", list(wanted)):
        if row.action_name != "document.delete" or row.undone:
            continue
        for target in wanted.intersection(row.target_ids or []):
            held = newest.get(target)
            if held is None or row.created_at > held.created_at:
                newest[target] = row
    reasons = {}
    for target, row in newest.items():
        moved = (row.params or {}).get("moved_to")
        if moved:
            reasons[target] = (TrashMovedTo.model_validate(moved), row.created_at)
    return reasons


def taken_back_reasons(db: Any, doc_ids: list[str]) -> dict[str, tuple[str, datetime, str]]:
    """For each id, the copy it came in by, when the newest thing that sent it to the Trash was that copy being
    undone (`document.untransfer`, #5663): (the project it was copied from, when, the transfer)."""
    from fichero_server.models.transfer import TransferRecord

    if not doc_ids:
        return {}
    wanted = set(doc_ids)
    newest: dict[str, ActionAudit] = {}
    for row in db.query_json_list_intersects(ActionAudit, "target_ids", list(wanted)):
        if row.action_name not in ("document.delete", "document.untransfer") or row.undone:
            continue
        for target in wanted.intersection(row.target_ids or []):
            held = newest.get(target)
            if held is None or row.created_at > held.created_at:
                newest[target] = row
    reasons = {}
    for target, row in newest.items():
        transfer_id = (row.after or {}).get("transfer_id") if row.action_name == "document.untransfer" else None
        record = db.get(TransferRecord, transfer_id) if transfer_id else None
        if record is not None and record.role.value == "target":
            reasons[target] = (Path(record.source_project).stem, row.created_at, transfer_id)
    return reasons


def trash_listing(
    db: Any,
    keep_readable,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> TrashListResponse:
    tops, counts, by_id = trashed_items(db)
    tops, withheld = keep_readable(tops)
    page = tops[offset : offset + limit] if limit is not None else tops[offset:]
    reasons = moved_reasons(db, [doc.id for doc in page])
    taken = taken_back_reasons(db, [doc.id for doc in page])
    items = []
    for doc in page:
        state, path, where = _from_where(doc, by_id)
        moved = reasons.get(doc.id)
        count = counts.get(doc.id, 0)
        if doc.id in taken:
            source, when, transfer_id = taken[doc.id]
            to, on, moved = None, None, None
            why = f"Taken back: the copy from {source} was undone on {_date_words(when)}"
        elif moved:
            to, on = moved
            why = f"Moved to {to.project} on {_date_words(on)}"
        else:
            to, on = None, None
            why = "Deleted" + (f" by {doc.deleted_by}" if doc.deleted_by else "")
        items.append(
            TrashItem(
                id=doc.id,
                name=doc.name,
                doc_type=doc.doc_type,
                deleted_at=doc.deleted_at,
                deleted_by=doc.deleted_by,
                item_count=count,
                from_folder_id=doc.parent_id,
                from_folder_path=path,
                from_folder_state=state,
                from_where=where,
                reason="taken_back" if doc.id in taken else "moved" if moved else "deleted",
                moved_to_project=to.project if to else None,
                moved_on=on,
                transfer_id=taken[doc.id][2] if doc.id in taken else to.transfer_id if to else None,
                why=why,
                document=doc,
            )
        )
    return TrashListResponse(items=items, count=len(items), total=len(tops), withheld=withheld)


# ---------------------------------------------------------------------------
# Put Back


def put_back(db: Any, doc_id: str) -> tuple[PutBackResponse, dict[str, Any]]:
    """Restore a trashed item and what was deleted with it; returns the answer and the root's
    parent before (for the record). Lands in Sources when its own folder cannot take it."""
    from fichero_server.api.routes.document.documents import (
        _document_or_404,
        _get_document_row,
        restore_documents_impl,
    )
    from fichero_server.importers.sources_folder import SOURCES_FOLDER_NAME, ensure_sources_folder

    root = _document_or_404(db, doc_id, include_deleted=True)
    ids = deleted_with(db, root) if root.deleted_at is not None else [root.id]
    parent_before = root.parent_id
    parent = _get_document_row(db, root.parent_id, include_deleted=True) if root.parent_id else None
    folder_in_trash = parent.id if parent is not None and parent.deleted_at is not None else None
    into_sources = (
        root.deleted_at is not None
        and bool(root.parent_id)
        and (parent is None or folder_in_trash is not None)
    )

    restored = restore_documents_impl(db, doc_ids=ids)
    if into_sources:
        sources_id, _made = ensure_sources_folder(db)
        # In-transaction read: the committed row still carries the trash mark just cleared.
        moved = db.get(Document, root.id)
        moved.parent_id = sources_id
        db.save(moved)
        folder_id, folder_name = sources_id, SOURCES_FOLDER_NAME
        why = "its folder is in the Trash" if folder_in_trash else "its folder is gone"
        message = f"Put back in {SOURCES_FOLDER_NAME}: {why}."
    else:
        folder_id = parent.id if parent is not None else None
        folder_name = parent.name if parent is not None else None
        message = f"Put back in {folder_name}." if folder_name else "Put back at the top of the project."
    answer = PutBackResponse(
        restored_document_ids=restored,
        folder_id=folder_id,
        folder_name=folder_name,
        into_sources=into_sources,
        folder_in_trash_id=folder_in_trash,
        message=message,
    )
    return answer, {"root_id": root.id, "parent_id": parent_before}


# ---------------------------------------------------------------------------
# Empty Trash


def _all_trashed_ids(db: Any) -> tuple[list[Document], list[str]]:
    tops, _counts, by_id = trashed_items(db)
    return tops, [doc.id for doc in by_id.values() if doc.deleted_at is not None]


def empty_preview(db: Any) -> EmptyTrashPreview:
    """What Empty Trash would remove, in numbers, and the moves it would make permanent."""
    from fichero_server.knowledge.trash_visibility import claims_resting_on

    tops, all_ids = _all_trashed_ids(db)
    statements = len(claims_resting_on(db, set(all_ids)))
    reasons = moved_reasons(db, [doc.id for doc in tops])
    groups: dict[str, list[datetime]] = {}
    for moved_to, on in reasons.values():
        groups.setdefault(moved_to.project, []).append(on)
    moved = []
    for project, dates in sorted(groups.items()):
        on = min(dates)
        moved.append(
            MovedGroup(
                project=project,
                count=len(dates),
                moved_on=on,
                sentence=(
                    f"{len(dates)} of these {'was' if len(dates) == 1 else 'were'} moved to {project} "
                    f"on {_date_words(on)}; emptying makes {'that move' if len(dates) == 1 else 'those moves'} permanent."
                ),
            )
        )
    n = len(tops)
    sentence = (
        "The Trash is empty."
        if n == 0
        else f"Delete {n} {'item' if n == 1 else 'items'} for good? This cannot be undone."
    )
    return EmptyTrashPreview(
        items=n, documents=len(all_ids), statements=statements, moved=moved, sentence=sentence
    )


def empty_trash(db: Any) -> EmptyTrashResult:
    """Remove everything in the Trash. The caller has taken the snapshot first."""
    from fichero_server.api.routes.document.documents import purge_document_impl

    preview = empty_preview(db)
    tops, _all = _all_trashed_ids(db)
    deleted: list[str] = []
    pruned = 0
    for top in tops:
        ids, _claims, entities, _docs, _artifacts = purge_document_impl(db, top.id, library_path=None)
        deleted.extend(ids)
        pruned += entities
    return EmptyTrashResult(
        **preview.model_dump(), deleted_document_ids=deleted, entities_pruned=pruned
    )
