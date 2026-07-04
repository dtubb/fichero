"""Import Sergio Mosquera corpus + catalogue spreadsheet into a Fichero library."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero.importers.http_client import (
    ImporterHttpClient,
    ensure_remote_document,
    reset_local_library_if_loopback,
)
from fichero.ingest import detect_file_type
from fichero.loaders.xlsx_reader import read_xlsx_records

DEFAULT_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Sergio-Mosquera.fichero"
).expanduser()


def _resolve_required(path: Path | None, *, env_var: str, flag: str) -> Path:
    if path is not None:
        return path
    raw = os.environ.get(env_var)
    if raw:
        return Path(raw).expanduser()
    raise ValueError(
        f"No source path configured. Pass {flag} or set the {env_var} "
        f"environment variable to the corpus location."
    )


IMPORTABLE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".ods",
}
_FILENAME_KEYS = ("filename", "file", "image", "imagen", "archivo", "nombre_archivo")


@dataclass(frozen=True)
class SergioImportSummary:
    library_path: Path
    root_document_id: str
    imported_files: int = 0
    spreadsheet_rows: int = 0
    matched_rows: int = 0
    unmatched_rows: int = 0
    skipped_files: int = 0
    duplicate_filename_rows: int = 0
    errors: list[str] = field(default_factory=list)


def import_sergio_corpus_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path = DEFAULT_LIBRARY,
    source_root: Path | None = None,
    spreadsheet_path: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
    limit: int | None = None,
) -> SergioImportSummary:
    source_root = _resolve_required(
        source_root, env_var="FICHERO_SERGIO_SOURCE_ROOT", flag="--source-root"
    )
    spreadsheet_path = _resolve_required(
        spreadsheet_path, env_var="FICHERO_SERGIO_SPREADSHEET", flag="--spreadsheet-path"
    )
    library_path = library_path.expanduser().resolve()
    source_root = source_root.expanduser().resolve()
    spreadsheet_path = spreadsheet_path.expanduser().resolve()

    # ponytail: only local loopback engines may delete local libraries.
    reset_local_library_if_loopback(client, library_path, reset=reset)
    client.create_library(str(library_path))

    root = ensure_remote_document(
        client,
        name="Sergio Mosquera Notebooks",
        path=str(source_root),
        doc_type="folder",
        parent_id=None,
        metadata={"source_type": "sergio_import"},
    )
    files_parent = ensure_remote_document(
        client,
        name="Notebook Files",
        path=str(source_root),
        doc_type="folder",
        parent_id=root["id"],
        metadata={"source_type": "sergio_files"},
    )
    spreadsheet_parent = ensure_remote_document(
        client,
        name="Spreadsheet Catalogue",
        path=str(spreadsheet_path),
        doc_type="folder",
        parent_id=root["id"],
        metadata={"source_type": "sergio_catalogue_spreadsheet"},
    )

    errors: list[str] = []
    imported_files = 0
    skipped_files = 0
    imported_by_basename: dict[str, str] = {}

    if source_root.exists():
        for file_path in _iter_source_files(source_root):
            if limit is not None and imported_files >= limit:
                break
            if file_path.suffix.lower() not in IMPORTABLE_EXTENSIONS:
                skipped_files += 1
                continue
            try:
                existing = next(
                    (
                        doc
                        for doc in client.list_documents(parent_id=files_parent["id"])
                        if getattr(doc, "path", None) == str(file_path)
                    ),
                    None,
                )
                if existing is None:
                    created = client.import_file(file_path, parent_id=files_parent["id"])
                    imported_by_basename[file_path.name.lower()] = created.id
                else:
                    imported_by_basename[file_path.name.lower()] = existing.id
                imported_files += 1
            except Exception as exc:  # pragma: no cover
                errors.append(f"file:{file_path}: {exc}")
    else:
        errors.append(f"Source root not found: {source_root}")

    spreadsheet_rows = 0
    matched_rows = 0
    unmatched_rows = 0
    duplicate_rows = 0

    if spreadsheet_path.exists():
        rows = read_xlsx_records(spreadsheet_path)
        filename_key = _detect_filename_key(rows)
        seen_filenames: dict[str, int] = {}

        for index, row in enumerate(rows, start=2):
            spreadsheet_rows += 1
            filename = ""
            if filename_key:
                filename = str(row.get(filename_key, "")).strip()
            if filename:
                lookup = filename.lower()
                seen_filenames[lookup] = seen_filenames.get(lookup, 0) + 1
                if seen_filenames[lookup] > 1:
                    duplicate_rows += 1
            matched_doc_id = imported_by_basename.get(filename.lower()) if filename else None
            if matched_doc_id:
                matched_rows += 1
            else:
                unmatched_rows += 1

            title = str(row.get("title") or row.get("titulo") or row.get("name") or "").strip()
            row_doc_name = f"row-{index}: {title or filename or 'catalogue entry'}"
            ensure_remote_document(
                client,
                name=row_doc_name,
                path=f"xlsx://{spreadsheet_path.name}#row={index}",
                doc_type="file",
                file_type=str(detect_file_type(Path("row.json")).value),
                parent_id=spreadsheet_parent["id"],
                page_content=json.dumps(row, ensure_ascii=False),
                metadata={
                    "source_type": "sergio_catalogue_row",
                    "spreadsheet_row": index,
                    "spreadsheet_filename_key": filename_key,
                    "spreadsheet_filename_value": filename,
                    "matched_document_id": matched_doc_id,
                    "row_data": row,
                },
            )
    else:
        errors.append(f"Spreadsheet not found: {spreadsheet_path}")

    return SergioImportSummary(
        library_path=library_path,
        root_document_id=root["id"],
        imported_files=imported_files,
        spreadsheet_rows=spreadsheet_rows,
        matched_rows=matched_rows,
        unmatched_rows=unmatched_rows,
        skipped_files=skipped_files,
        duplicate_filename_rows=duplicate_rows,
        errors=errors,
    )


def _detect_filename_key(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    header_names = {k.strip().lower(): k for k in rows[0].keys()}
    for key in _FILENAME_KEYS:
        if key in header_names:
            return header_names[key]
    return None


def _iter_source_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts):
            yield path

__all__ = [name for name in dir() if not name.startswith("__")]
