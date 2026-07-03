"""Link-only Tinderbox (.tbx) importer into the Fichero library model."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero.db import db_manager
from fichero.importers.http_client import ImporterHttpClient, ensure_remote_document
from fichero.models import DocType, Document, FileType, Status
from fichero.xml_security import iterparse_xml


@dataclass(frozen=True)
class TinderboxLinkImportSummary:
    library_path: Path
    tbx_path: Path
    root_document_id: str
    imported_notes: int = 0
    updated_notes: int = 0
    deleted_notes: int = 0
    skipped_notes: int = 0
    errors: list[str] = field(default_factory=list)


def import_tinderbox_links(
    *,
    library_path: Path,
    tbx_path: Path,
    reset: bool = False,
) -> TinderboxLinkImportSummary:
    library_path = library_path.expanduser().resolve()
    tbx_path = tbx_path.expanduser().resolve()

    _ensure_library_package(library_path)
    db = db_manager.get_database(library_path)

    root = _find_root_doc(db, tbx_path) or Document(
        name=f"Tinderbox: {tbx_path.stem}",
        path=str(tbx_path),
        doc_type=DocType.folder,
        status=Status.completed,
        metadata={"source_type": "tinderbox_link_import", "tbx_path": str(tbx_path)},
    )
    db.save(root, auto_embed=False)

    notes = parse_tinderbox_notes(tbx_path)
    note_ids = {note["id"] for note in notes}

    existing_docs = [
        doc
        for doc in db.query(Document, parent_id=root.id)
        if doc.doc_type == DocType.file and (doc.metadata or {}).get("source_type") == "tinderbox_note"
    ]
    existing_by_note_id = {
        str((doc.metadata or {}).get("tinderbox_id") or ""): doc
        for doc in existing_docs
        if (doc.metadata or {}).get("tinderbox_id")
    }

    imported = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for note in notes:
        note_id = note["id"]
        content = note.get("text") or ""
        url = note.get("url") or ""
        if url and not content.strip():
            skipped += 1
            continue

        metadata = {
            "source_type": "tinderbox_note",
            "tinderbox_id": note_id,
            "tinderbox_path": note.get("tb_path") or "",
            "tinderbox_tags": note.get("tags") or [],
            "tinderbox_prototype": note.get("prototype") or "",
            "tinderbox_attrs": note.get("attrs") or {},
            "tinderbox_modified": note.get("modified") or "",
            "link_only": True,
            "remote_reference": True,
        }

        existing = existing_by_note_id.get(note_id)
        try:
            if existing is None:
                doc = Document(
                    name=note.get("name") or f"Tinderbox note {note_id}",
                    path=f"tinderbox://{tbx_path.name}/{note_id}",
                    doc_type=DocType.file,
                    file_type=FileType.text,
                    parent_id=root.id,
                    status=Status.completed,
                    page_content=content,
                    metadata=metadata,
                )
                db.save(doc)
                imported += 1
            else:
                existing.name = note.get("name") or existing.name
                existing.path = f"tinderbox://{tbx_path.name}/{note_id}"
                existing.page_content = content
                existing.metadata = metadata
                existing.status = Status.completed
                db.save(existing)
                updated += 1
        except Exception as exc:  # pragma: no cover
            errors.append(f"note:{note_id}:{exc}")

    deleted = 0
    for doc in existing_docs:
        note_id = str((doc.metadata or {}).get("tinderbox_id") or "")
        if note_id and note_id not in note_ids:
            db.delete(doc)
            deleted += 1

    return TinderboxLinkImportSummary(
        library_path=library_path,
        tbx_path=tbx_path,
        root_document_id=root.id,
        imported_notes=imported,
        updated_notes=updated,
        deleted_notes=deleted,
        skipped_notes=skipped,
        errors=errors,
    )


def import_tinderbox_links_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path,
    tbx_path: Path,
    reset: bool = False,
) -> TinderboxLinkImportSummary:
    library_path = library_path.expanduser().resolve()
    tbx_path = tbx_path.expanduser().resolve()

    # ponytail: same-host reset is still local delete until the backend grows a
    # real remote library-reset endpoint.
    if reset and library_path.exists():
        shutil.rmtree(library_path)
    client.create_library(str(library_path))

    root = ensure_remote_document(
        client,
        name=f"Tinderbox: {tbx_path.stem}",
        path=str(tbx_path),
        doc_type="folder",
        parent_id=None,
        metadata={"source_type": "tinderbox_link_import", "tbx_path": str(tbx_path)},
    )

    notes = parse_tinderbox_notes(tbx_path)
    note_ids = {note["id"] for note in notes}

    existing_docs = [
        doc
        for doc in client.list_documents(parent_id=root["id"])
        if getattr(doc, "doc_type", None) == "file"
        and ((getattr(doc, "metadata", None) or {}).get("source_type") == "tinderbox_note")
    ]
    existing_by_note_id = {
        str((getattr(doc, "metadata", None) or {}).get("tinderbox_id") or ""): doc
        for doc in existing_docs
        if (getattr(doc, "metadata", None) or {}).get("tinderbox_id")
    }

    imported = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    for note in notes:
        note_id = note["id"]
        content = note.get("text") or ""
        url = note.get("url") or ""
        if url and not content.strip():
            skipped += 1
            continue

        payload = {
            "name": note.get("name") or f"Tinderbox note {note_id}",
            "path": f"tinderbox://{tbx_path.name}/{note_id}",
            "doc_type": "file",
            "file_type": "text",
            "parent_id": root["id"],
            "status": "completed",
            "page_content": content,
            "metadata": {
                "source_type": "tinderbox_note",
                "tinderbox_id": note_id,
                "tinderbox_path": note.get("tb_path") or "",
                "tinderbox_tags": note.get("tags") or [],
                "tinderbox_prototype": note.get("prototype") or "",
                "tinderbox_attrs": note.get("attrs") or {},
                "tinderbox_modified": note.get("modified") or "",
                "link_only": True,
                "remote_reference": True,
            },
        }

        existing = existing_by_note_id.get(note_id)
        try:
            if existing is None:
                client.request("POST", "/api/documents", json=payload)
                imported += 1
            else:
                client.request("PUT", f"/api/documents/{existing.id}", json=payload)
                updated += 1
        except Exception as exc:  # pragma: no cover
            errors.append(f"note:{note_id}:{exc}")

    deleted = 0
    for doc in existing_docs:
        note_id = str((getattr(doc, "metadata", None) or {}).get("tinderbox_id") or "")
        if note_id and note_id not in note_ids:
            client.request("DELETE", f"/api/documents/{doc.id}")
            deleted += 1

    return TinderboxLinkImportSummary(
        library_path=library_path,
        tbx_path=tbx_path,
        root_document_id=root["id"],
        imported_notes=imported,
        updated_notes=updated,
        deleted_notes=deleted,
        skipped_notes=skipped,
        errors=errors,
    )


def parse_tinderbox_notes(tbx_path: Path) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for event, elem in iterparse_xml(tbx_path, events=("end",)):
        tag = _local_name(elem.tag)
        if tag not in {"note", "item"}:
            continue
        attrs = _collect_attrs(elem)
        note_id = _pick(attrs, "id", "$ID", "ID")
        if not note_id:
            elem.clear()
            continue
        name = _pick(attrs, "$Name", "Name", "name") or f"Tinderbox note {note_id}"
        text = _pick(attrs, "$Text", "Text", "text") or ""
        tags_raw = _pick(attrs, "$Tags", "Tags", "$Keywords", "Keywords") or ""
        tags = [token.strip() for token in tags_raw.replace(";", ",").split(",") if token.strip()]
        notes.append(
            {
                "id": note_id,
                "name": name,
                "text": text,
                "tb_path": _pick(attrs, "$Path", "Path") or "",
                "prototype": _pick(attrs, "$Prototype", "Prototype") or "",
                "modified": _pick(attrs, "$Modified", "Modified") or "",
                "url": _pick(attrs, "$URL", "URL") or "",
                "tags": tags,
                "attrs": attrs,
            }
        )
        elem.clear()
    return notes


def _collect_attrs(elem: Any) -> dict[str, str]:
    attrs: dict[str, str] = {str(k): str(v) for k, v in elem.attrib.items()}
    for child in list(elem):
        child_tag = _local_name(child.tag)
        if child_tag != "attribute":
            continue
        key = child.attrib.get("name") or child.attrib.get("key") or child.attrib.get("Name")
        if not key:
            continue
        value = "".join(part for part in child.itertext()).strip()
        attrs[str(key)] = value
    return attrs


def _pick(attrs: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = attrs.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_root_doc(db: Any, tbx_path: Path) -> Document | None:
    for doc in db.all(Document):
        metadata = doc.metadata if isinstance(doc.metadata, dict) else {}
        if (
            doc.doc_type == DocType.folder
            and metadata.get("source_type") == "tinderbox_link_import"
            and metadata.get("tbx_path") == str(tbx_path)
        ):
            return doc
    return None


def _ensure_library_package(library_path: Path) -> None:
    library_path.mkdir(parents=True, exist_ok=True)
    (library_path / "files").mkdir(exist_ok=True)
    (library_path / "lance").mkdir(exist_ok=True)
    (library_path / "vectors").mkdir(exist_ok=True)

__all__ = [name for name in dir() if not name.startswith("__")]

__all__ = [
    'Any',
    'DocType',
    'Document',
    'FileType',
    'Path',
    'Status',
    'TinderboxLinkImportSummary',
    '_collect_attrs',
    '_ensure_library_package',
    '_find_root_doc',
    '_local_name',
    '_pick',
    'annotations',
    'dataclass',
    'db_manager',
    'field',
    'import_tinderbox_links',
    'iterparse_xml',
    'parse_tinderbox_notes',
]
