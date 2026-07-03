"""One-off source-archive importers for release/demo corpora."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero.db import db_manager
from fichero.importers.http_client import ImporterHttpClient, ensure_remote_document
from fichero.ingest import IngestMode, ingest_file
from fichero.models import DocType, Document, Status

# Library packages default to the standard macOS Application Support location.
# Source-corpus locations are user/machine specific and are NOT hardcoded: pass
# the path explicitly, or set the matching environment variable. If neither is
# provided the import raises with a clear message (no silent fallback).
DEFAULT_NEWTON_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Newton-C-Marshall.fichero"
).expanduser()
DEFAULT_ISTMINA_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Istmina-Mineria.fichero"
).expanduser()
DEFAULT_ARCHIVO_JUDICIAL_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Archivo-Judicial-Medellin.fichero"
).expanduser()
DEFAULT_GHC_LIBRARY = Path(
    "~/Library/Application Support/Fichero/GHC-Catalogued-Materials.fichero"
).expanduser()
DEFAULT_CHOTA_PACIFIC_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Chota-Pacific-Maps.fichero"
).expanduser()


def _resolve_required(path: Path | None, *, env_var: str, flag: str) -> Path:
    """Return an explicit path, else the env-var path, else raise loudly."""
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
    ".csv",
    ".json",
}


@dataclass(frozen=True)
class SourceArchiveImportSummary:
    provider: str
    library_path: Path
    root_documents: int = 0
    files_imported: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


def import_newton_marshall_diary(
    *,
    library_path: Path = DEFAULT_NEWTON_LIBRARY,
    source_path: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    source_path = _resolve_required(
        source_path, env_var="FICHERO_NEWTON_SOURCE", flag="--source-path"
    )
    return _import_roots(
        provider="newton_marshall_diary",
        corpus_name="Newton C Marshall Diary",
        library_path=library_path,
        roots={"diary_materials": source_path},
        reset=reset,
        auto_embed=auto_embed,
    )


def import_newton_marshall_diary_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path = DEFAULT_NEWTON_LIBRARY,
    source_path: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    source_path = _resolve_required(
        source_path, env_var="FICHERO_NEWTON_SOURCE", flag="--source-path"
    )
    return _import_roots_via_http(
        client,
        provider="newton_marshall_diary",
        corpus_name="Newton C Marshall Diary",
        library_path=library_path,
        roots={"diary_materials": source_path},
        reset=reset,
        auto_embed=auto_embed,
    )


def import_istmina_mineria(
    *,
    library_path: Path = DEFAULT_ISTMINA_LIBRARY,
    transcript_root: Path | None = None,
    spreadsheet_root: Path | None = None,
    review_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    transcript_root = _resolve_required(
        transcript_root, env_var="FICHERO_ISTMINA_TRANSCRIPT", flag="--transcript-root"
    )
    spreadsheet_root = _resolve_required(
        spreadsheet_root, env_var="FICHERO_ISTMINA_SPREADSHEET", flag="--spreadsheet-root"
    )
    review_root = _resolve_required(
        review_root, env_var="FICHERO_ISTMINA_REVIEW", flag="--review-root"
    )
    return _import_roots(
        provider="istmina_mineria",
        corpus_name="Istmina Mineria 1980",
        library_path=library_path,
        roots={
            "transcriptions": transcript_root,
            "added_to_spreadsheet": spreadsheet_root,
            "awaiting_human_check": review_root,
        },
        reset=reset,
        auto_embed=auto_embed,
    )


def import_istmina_mineria_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path = DEFAULT_ISTMINA_LIBRARY,
    transcript_root: Path | None = None,
    spreadsheet_root: Path | None = None,
    review_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    transcript_root = _resolve_required(
        transcript_root, env_var="FICHERO_ISTMINA_TRANSCRIPT", flag="--transcript-root"
    )
    spreadsheet_root = _resolve_required(
        spreadsheet_root, env_var="FICHERO_ISTMINA_SPREADSHEET", flag="--spreadsheet-root"
    )
    review_root = _resolve_required(
        review_root, env_var="FICHERO_ISTMINA_REVIEW", flag="--review-root"
    )
    return _import_roots_via_http(
        client,
        provider="istmina_mineria",
        corpus_name="Istmina Mineria 1980",
        library_path=library_path,
        roots={
            "transcriptions": transcript_root,
            "added_to_spreadsheet": spreadsheet_root,
            "awaiting_human_check": review_root,
        },
        reset=reset,
        auto_embed=auto_embed,
    )


def import_archivo_judicial_medellin(
    *,
    library_path: Path = DEFAULT_ARCHIVO_JUDICIAL_LIBRARY,
    catalogue_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    catalogue_root = _resolve_required(
        catalogue_root, env_var="FICHERO_ARCHIVO_JUDICIAL_CATALOGUE", flag="--catalogue-root"
    )
    return _import_roots(
        provider="archivo_judicial_medellin",
        corpus_name="Archivo Judicial de Medellin",
        library_path=library_path,
        roots={"catalogue": catalogue_root},
        reset=reset,
        auto_embed=auto_embed,
    )


def import_archivo_judicial_medellin_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path = DEFAULT_ARCHIVO_JUDICIAL_LIBRARY,
    catalogue_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    catalogue_root = _resolve_required(
        catalogue_root, env_var="FICHERO_ARCHIVO_JUDICIAL_CATALOGUE", flag="--catalogue-root"
    )
    return _import_roots_via_http(
        client,
        provider="archivo_judicial_medellin",
        corpus_name="Archivo Judicial de Medellin",
        library_path=library_path,
        roots={"catalogue": catalogue_root},
        reset=reset,
        auto_embed=auto_embed,
    )


def import_ghc_catalogued_materials(
    *,
    library_path: Path = DEFAULT_GHC_LIBRARY,
    acenet_root: Path | None = None,
    catalogued_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    acenet_root = _resolve_required(
        acenet_root, env_var="FICHERO_GHC_ACENET_ROOT", flag="--acenet-root"
    )
    catalogued_root = _resolve_required(
        catalogued_root, env_var="FICHERO_GHC_CATALOGUED_ROOT", flag="--catalogued-root"
    )
    return _import_roots(
        provider="ghc_catalogued_materials",
        corpus_name="GHC Catalogued Materials",
        library_path=library_path,
        roots={
            "acenet_imports": acenet_root,
            "already_catalogued": catalogued_root,
        },
        reset=reset,
        auto_embed=auto_embed,
    )


def import_ghc_catalogued_materials_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path = DEFAULT_GHC_LIBRARY,
    acenet_root: Path | None = None,
    catalogued_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    acenet_root = _resolve_required(
        acenet_root, env_var="FICHERO_GHC_ACENET_ROOT", flag="--acenet-root"
    )
    catalogued_root = _resolve_required(
        catalogued_root, env_var="FICHERO_GHC_CATALOGUED_ROOT", flag="--catalogued-root"
    )
    return _import_roots_via_http(
        client,
        provider="ghc_catalogued_materials",
        corpus_name="GHC Catalogued Materials",
        library_path=library_path,
        roots={
            "acenet_imports": acenet_root,
            "already_catalogued": catalogued_root,
        },
        reset=reset,
        auto_embed=auto_embed,
    )


def import_chota_colombian_pacific_maps(
    *,
    library_path: Path = DEFAULT_CHOTA_PACIFIC_LIBRARY,
    source_root: Path | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    source_root = _resolve_required(
        source_root, env_var="FICHERO_CHOTA_PACIFIC_SOURCE", flag="--source-root"
    )
    return _import_roots(
        provider="chota_colombian_pacific_maps",
        corpus_name="Chota Valley + Colombian Pacific Maps",
        library_path=library_path,
        roots={"maps_southern_colombia": source_root},
        reset=reset,
        auto_embed=auto_embed,
    )


def _import_roots(
    *,
    provider: str,
    corpus_name: str,
    library_path: Path,
    roots: dict[str, Path],
    reset: bool,
    auto_embed: bool,
) -> SourceArchiveImportSummary:
    library_path = library_path.expanduser().resolve()
    resolved_roots = {name: path.expanduser().resolve() for name, path in roots.items()}

    if reset and library_path.exists():
        shutil.rmtree(library_path)
    _ensure_library_package(library_path)
    db = db_manager.get_database(library_path)

    root_doc = Document(
        name=corpus_name,
        path=str(next(iter(resolved_roots.values()))),
        doc_type=DocType.folder,
        status=Status.completed,
        metadata={"source_type": provider},
    )
    db.save(root_doc)

    imported = 0
    skipped = 0
    warnings: list[str] = []

    for label, root_path in resolved_roots.items():
        child = _folder_doc(
            db,
            name=label.replace("_", " ").title(),
            path=str(root_path),
            parent_id=root_doc.id,
            metadata={"source_type": provider, "archive_root": label},
        )
        if not root_path.exists():
            warnings.append(f"missing_root:{label}:{root_path}")
            continue

        for file_path in _iter_source_files(root_path):
            if file_path.suffix.lower() not in IMPORTABLE_EXTENSIONS:
                skipped += 1
                continue
            try:
                ingest_file(
                    file_path,
                    mode=IngestMode.LINK,
                    parent_id=child.id,
                    extract_metadata=True,
                    extract_text=True,
                    auto_embed=auto_embed,
                    save=True,
                    db=db,
                    package_path=library_path,
                )
                imported += 1
            except Exception as exc:  # pragma: no cover
                warnings.append(f"file:{file_path}:{exc}")

    return SourceArchiveImportSummary(
        provider=provider,
        library_path=library_path,
        root_documents=1 + len(resolved_roots),
        files_imported=imported,
        skipped=skipped,
        warnings=warnings,
    )


def _import_roots_via_http(
    client: ImporterHttpClient,
    *,
    provider: str,
    corpus_name: str,
    library_path: Path,
    roots: dict[str, Path],
    reset: bool,
    auto_embed: bool,
) -> SourceArchiveImportSummary:
    del auto_embed
    library_path = library_path.expanduser().resolve()
    resolved_roots = {name: path.expanduser().resolve() for name, path in roots.items()}

    # ponytail: same-host reset is still local delete until the backend grows a
    # real remote library-reset endpoint.
    if reset and library_path.exists():
        shutil.rmtree(library_path)
    client.create_library(str(library_path))

    root_doc = ensure_remote_document(
        client,
        name=corpus_name,
        path=str(next(iter(resolved_roots.values()))),
        doc_type="folder",
        parent_id=None,
        metadata={"source_type": provider},
    )

    imported = 0
    skipped = 0
    warnings: list[str] = []

    for label, root_path in resolved_roots.items():
        child = ensure_remote_document(
            client,
            name=label.replace("_", " ").title(),
            path=str(root_path),
            doc_type="folder",
            parent_id=root_doc["id"],
            metadata={"source_type": provider, "archive_root": label},
        )
        if not root_path.exists():
            warnings.append(f"missing_root:{label}:{root_path}")
            continue

        existing_by_path = {
            getattr(doc, "path", None): doc.id
            for doc in client.list_documents(parent_id=child["id"])
        }
        for file_path in _iter_source_files(root_path):
            if file_path.suffix.lower() not in IMPORTABLE_EXTENSIONS:
                skipped += 1
                continue
            try:
                if str(file_path) not in existing_by_path:
                    created = client.import_file(file_path, parent_id=child["id"])
                    existing_by_path[str(file_path)] = created.id
                imported += 1
            except Exception as exc:  # pragma: no cover
                warnings.append(f"file:{file_path}:{exc}")

    return SourceArchiveImportSummary(
        provider=provider,
        library_path=library_path,
        root_documents=1 + len(resolved_roots),
        files_imported=imported,
        skipped=skipped,
        warnings=warnings,
    )


def _iter_source_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root).parts):
            yield path


def _ensure_library_package(library_path: Path) -> None:
    library_path.mkdir(parents=True, exist_ok=True)
    (library_path / "files").mkdir(exist_ok=True)
    (library_path / "lance").mkdir(exist_ok=True)
    (library_path / "vectors").mkdir(exist_ok=True)


def _folder_doc(db, *, name: str, path: str, parent_id: str, metadata: dict[str, Any]) -> Document:
    doc = Document(
        name=name,
        path=path,
        doc_type=DocType.folder,
        parent_id=parent_id,
        status=Status.completed,
        metadata=metadata,
    )
    db.save(doc)
    return doc

__all__ = [name for name in dir() if not name.startswith("__")]

__all__ = [
    'Any',
    'DEFAULT_ARCHIVO_JUDICIAL_LIBRARY',
    'DEFAULT_CHOTA_PACIFIC_LIBRARY',
    'DEFAULT_GHC_LIBRARY',
    'DEFAULT_ISTMINA_LIBRARY',
    'DEFAULT_NEWTON_LIBRARY',
    'DocType',
    'Document',
    'IMPORTABLE_EXTENSIONS',
    'IngestMode',
    'Path',
    'SourceArchiveImportSummary',
    'Status',
    '_ensure_library_package',
    '_folder_doc',
    '_import_roots',
    '_iter_source_files',
    '_resolve_required',
    'annotations',
    'dataclass',
    'db_manager',
    'field',
    'import_archivo_judicial_medellin',
    'import_chota_colombian_pacific_maps',
    'import_ghc_catalogued_materials',
    'import_istmina_mineria',
    'import_newton_marshall_diary',
    'ingest_file',
    'os',
    'shutil',
]
