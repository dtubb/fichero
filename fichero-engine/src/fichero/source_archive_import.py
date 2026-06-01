"""One-off source-archive importers for release/demo corpora."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero.db import db_manager
from fichero.ingest import IngestMode, ingest_file
from fichero.models import DocType, Document, Status

DEFAULT_NEWTON_SOURCE = Path(
    "/Users/danieltubb/Library/CloudStorage/Box-Box/Newton C Marshall Diary"
).expanduser()
DEFAULT_NEWTON_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Newton-C-Marshall.fichero"
).expanduser()

DEFAULT_ISTMINA_LIBRARY = Path(
    "~/Library/Application Support/Fichero/Istmina-Mineria.fichero"
).expanduser()
DEFAULT_ISTMINA_TRANSCRIPT = Path(
    "/Users/danieltubb/Library/CloudStorage/Box-Box/JPG files (minería hasta 1980)/"
    "Istmina_Minería 1980_Completo_Transcripcion"
).expanduser()
DEFAULT_ISTMINA_SPREADSHEET = Path(
    "/Users/danieltubb/Library/CloudStorage/Box-Box/JPG files (minería hasta 1980)/"
    "Workflow/05 Added to spreadsheet"
).expanduser()
DEFAULT_ISTMINA_REVIEW = Path(
    "/Users/danieltubb/Library/CloudStorage/Box-Box/JPG files (minería hasta 1980)/"
    "Workflow/04 Transcribed and catalogued, awaiting human check"
).expanduser()

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
    source_path: Path = DEFAULT_NEWTON_SOURCE,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
    return _import_roots(
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
    transcript_root: Path = DEFAULT_ISTMINA_TRANSCRIPT,
    spreadsheet_root: Path = DEFAULT_ISTMINA_SPREADSHEET,
    review_root: Path = DEFAULT_ISTMINA_REVIEW,
    reset: bool = False,
    auto_embed: bool = True,
) -> SourceArchiveImportSummary:
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
