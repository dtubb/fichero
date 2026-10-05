"""Kept exports: an up-to-date copy of the project's work in a folder outside it (#5485).

Spec: `docs/contributor_manual/specs/source/models-chains-and-projects.md`, section 7b, screen 3
(**Kept exported**). A project keeps any number of exports, each a **folder**, a **format** and
**one file per page or per document**. Writing goes through the one export path: the page formats
(ALTO, PAGE XML, TEI, hOCR) through `page_export.export_page`, Word through
`export_service.export_word_docx`, Markdown through `export_service.render_markdown_text`, plain
text as the page's derived text (`document_text`, reading order, furniture left out). The page
formats are one file per page only: their files describe one image.

A document is the node a page sits in (a multi-page file, a group or a folder); pages at the top
of the project form one document named after the project. Files are named by the page's file or
the document's name and the format's extension; two that would share a name take ` 2`, ` 3` in
the project's order.

One-way: the folder is never read back. Each file written is recorded (`kept_export_files`); a
later write overwrites only those (a hand edit to one is overwritten, as the spec says, and the
person is told so when the export is set up), and a file already in the folder that the export
did not write is left alone and listed (`in_the_way`). Nothing is ever deleted. A folder inside
the project's package, a system folder, or one that is not there is refused in one sentence.

Each write is one job (kind `write-kept-export`, the background `database` lane), so it is
throttled, paused and shown in Activity like all background work. "Write now" queues the whole
export. The work changing queues a rewrite of the pages it touched, after a quiet period, from two
places: every audited action that touches a page (`sync_folder.queue_rewrites`, the synced
folder's hook, which calls `queue_rewrites` here) and the end of each workflow step of a recipe
run (`recipes.runner.run`), for the pages that step worked on. No file watcher.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs

KIND = "write-kept-export"
#: How long a page must stay unchanged before its files are rewritten.
QUIET_SECONDS = 5.0
#: The page interchange formats, written one file per page by the exporter.
PAGE_FORMATS = ("alto", "pagexml", "tei", "hocr")
FORMATS = ("word", "markdown", "plain-text", *PAGE_FORMATS)
PER = ("page", "document")
_EXTENSIONS = {"word": ".docx", "markdown": ".md", "plain-text": ".txt"}
#: The unit key of the pages at the top of the project (no parent): one document, the project's.
_TOP = "top"


class KeptExportRefused(ValueError):
    """An export that cannot be kept, or written, said in one sentence."""


@dataclass
class _Unit:
    key: str
    #: The document's own name (its heading), and the file name's stem.
    name: str
    stem: str
    pages: list[Any] = field(default_factory=list)
    filename: str = ""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _package(db: Any) -> Path:
    return Path(db.path).parent


def _exports(db: Any) -> list[dict[str, Any]]:
    rows = db.execute_fetchall("SELECT id, folder, format, per, created_at FROM kept_exports "
                               "WHERE removed_at IS NULL ORDER BY created_at")
    return [{"id": r[0], "folder": r[1], "format": r[2], "per": r[3], "created_at": r[4]} for r in rows]


def _export(db: Any, export_id: str) -> dict[str, Any] | None:
    return next((e for e in _exports(db) if e["id"] == export_id), None)


def _refuse_folder(db: Any, folder: str) -> str:
    """The folder's resolved path, or refused: not a full path, not there, a system folder (the
    owner's folder pick's own check), or inside the project's package."""
    from fichero_server.security.path_security import OwnerFolderGrantRefused, owner_folder_grant_key

    try:
        resolved = Path(owner_folder_grant_key(folder))
    except OwnerFolderGrantRefused as exc:
        raise KeptExportRefused(str(exc)) from exc
    if not resolved.is_dir():
        raise KeptExportRefused(f"{resolved} is a file, not a folder.")
    if resolved.is_relative_to(_package(db).resolve()):
        raise KeptExportRefused("That folder is inside the project; choose one outside it.")
    return str(resolved)


def keep(db: Any, folder: str, fmt: str, per: str) -> str:
    """Keep an export, and queue its first write. Returns its id."""
    if fmt not in FORMATS:
        raise KeptExportRefused(f"An export is kept as {', '.join(FORMATS)}; not {fmt!r}.")
    if per not in PER:
        raise KeptExportRefused(f"An export is one file per page or per document; not {per!r}.")
    if fmt in PAGE_FORMATS and per != "page":
        raise KeptExportRefused(f"{fmt} describes one image, so it is written one file per page.")
    resolved = _refuse_folder(db, folder)
    register_job_kinds()
    export_id = uuid.uuid4().hex
    db.execute("INSERT INTO kept_exports (id, folder, format, per, created_at) VALUES (?, ?, ?, ?, ?)",
               [export_id, resolved, fmt, per, utc_now()])
    jobs.enqueue(db, KIND, export_id, started_by="kept export")
    return export_id


def remove(db: Any, export_id: str) -> None:
    """Stop keeping the export; the files it wrote stay in the folder."""
    if _export(db, export_id) is None:
        raise KeyError(export_id)
    db.execute("UPDATE kept_exports SET removed_at = ? WHERE id = ? AND removed_at IS NULL", [utc_now(), export_id])


def write_now(db: Any, export_id: str) -> str:
    """Queue one write of the whole export, which a person waits on. Returns the job id."""
    if _export(db, export_id) is None:
        raise KeyError(export_id)
    register_job_kinds()
    return jobs.enqueue(db, KIND, export_id, started_by="kept export", watched=True)


def queue_rewrites(db: Any, document_ids: list[str], *, watched: bool = False) -> None:
    """The work on these pages changed: rewrite their files in every kept export after the quiet
    period, in the change's own transaction. Cheap when nothing is kept."""
    if not document_ids:
        return
    exports = _exports(db)
    if not exports:
        return
    register_job_kinds()
    ids = list(dict.fromkeys(document_ids))
    parents: dict[str, str | None] = {}
    if any(e["per"] == "document" for e in exports):
        marks = ", ".join("?" for _ in ids)
        parents = dict(db.execute_fetchall(f"SELECT id, parent_id FROM documents WHERE id IN ({marks})", ids))
    after = utc_now() + timedelta(seconds=QUIET_SECONDS)
    for export in exports:
        keys = ids if export["per"] == "page" else [parents.get(i) or _TOP for i in ids if i in parents]
        for key in dict.fromkeys(keys):
            jobs.enqueue(db, KIND, f"{export['id']}:{key}", started_by="kept export", run_after=after,
                         watched=watched)


def _stem(name: str | None, fallback: str) -> str:
    from fichero_server.page_export import export_stem

    stem = export_stem(PurePosixPath(name).name if name else None, fallback)
    stem = stem.replace("/", "-").replace(":", "-").replace("\0", "").strip()
    return fallback if stem in ("", ".", "..") else stem


def _extension(fmt: str) -> str:
    from fichero_server.formats import format_named

    return _EXTENSIONS.get(fmt) or format_named(fmt).file_extension


def _units(db: Any, export: dict[str, Any]) -> list[_Unit]:
    """The export's files, in the project's order, each with its pages and its name."""
    from fichero_server.export_service import _collect_documents
    from fichero_server.models import DocType, Document

    _root, documents = _collect_documents(db, target_id=None, recursive=True)
    pages = [d for d in documents if d.doc_type in (DocType.file, DocType.page)]
    units: dict[str, _Unit] = {}
    for page in pages:
        if export["per"] == "page":
            units[page.id] = _Unit(page.id, page.name, _stem(page.path or page.name, page.id), [page])
            continue
        key = page.parent_id or _TOP
        if key not in units:
            parent = db.get(Document, page.parent_id) if page.parent_id else None
            name = parent.name if parent is not None else _package(db).stem
            units[key] = _Unit(key, name, _stem(name, key))
        units[key].pages.append(page)
    used: set[str] = set()
    extension = _extension(export["format"])
    for unit in units.values():
        filename, n = f"{unit.stem}{extension}", 2
        while filename.lower() in used:
            filename, n = f"{unit.stem} {n}{extension}", n + 1
        used.add(filename.lower())
        unit.filename = filename
    return list(units.values())


def _text(db: Any, page_id: str) -> str | None:
    """The page's text as the record has it, in reading order; None when nothing is read."""
    from fichero_server.api.routes.document.segment_readings import document_text

    try:
        derived = document_text(db, page_id)
    except LookupError:
        return None
    if derived.pass_id is None:
        return None
    return derived.text.strip() or None


def _render(db: Any, export: dict[str, Any], unit: _Unit) -> bytes | None:
    """The unit's file, or None when it has nothing to write (no page of it is read)."""
    fmt = export["format"]
    if fmt in PAGE_FORMATS:
        from fichero_server.formats import FormatCannotWrite
        from fichero_server.page_export import ExportRefused, export_page

        try:
            return export_page(db, unit.pages[0].id, fmt).data
        except (ExportRefused, FormatCannotWrite):
            return None
    texts = {page.id: _text(db, page.id) for page in unit.pages}
    read = [page for page in unit.pages if texts[page.id]]
    if not read:
        return None
    single = export["per"] == "page"
    if fmt == "plain-text":
        return ("\n\n".join(texts[p.id] for p in read) + "\n").encode("utf-8")
    if fmt == "markdown":
        from fichero_server.export_service import render_markdown_text

        title = read[0].name if single else unit.name
        sections = [(None if single else p.name, texts[p.id]) for p in read]
        return render_markdown_text(title, sections).encode("utf-8")
    from fichero_server.export_service import export_word_docx

    with tempfile.TemporaryDirectory(prefix="fichero-kept-export-") as scratch:
        out = Path(scratch) / "out.docx"
        export_word_docx(db, out, overwrite=True, package_path=_package(db), include_knowledge_graph=False,
                         documents=read, title=read[0].name if single else unit.name,
                         text_for=lambda doc: texts[doc.id] or "")
        return out.read_bytes()


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _record(db: Any, export_id: str, rel: str, sha: str | None, state: str) -> None:
    db.execute(
        "INSERT INTO kept_export_files (export_id, rel_path, sha256, written_at, state) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (export_id, rel_path) DO UPDATE SET sha256 = excluded.sha256, "
        "written_at = coalesce(excluded.written_at, kept_export_files.written_at), state = excluded.state",
        [export_id, rel, sha, utc_now() if state == "written" else None, state])


def _put(db: Any, export: dict[str, Any], rel: str, data: bytes) -> None:
    """Write one file: over a file this export wrote, never over one it did not."""
    path = Path(export["folder"]) / rel
    known = db.execute_fetchone("SELECT state FROM kept_export_files WHERE export_id = ? AND rel_path = ?",
                                [export["id"], rel])
    if path.exists():
        if known is None or known[0] != "written":
            _record(db, export["id"], rel, None, "in-the-way")
            return  # not this export's: left alone, and listed
        if _sha(path.read_bytes()) == _sha(data):
            return  # already what it would write
    _atomic_write(path, data)
    _record(db, export["id"], rel, _sha(data), "written")


def write(db: Any, subject: str) -> None:
    """The job: write the export (subject `<id>`), or one of its files (`<id>:<page or document>`)."""
    export_id, _, key = subject.partition(":")
    export = _export(db, export_id)
    if export is None:
        return  # removed meanwhile
    folder = Path(export["folder"])
    if not folder.is_dir():
        raise KeptExportRefused(f"{folder} is not there any more; choose the export's folder again.")
    for unit in _units(db, export):
        if key and unit.key != key:
            continue
        data = _render(db, export, unit)
        if data is not None:
            _put(db, export, unit.filename, data)


def status(db: Any) -> list[dict[str, Any]]:
    """Each kept export: its folder, format and per, the files it wrote, files in its way, files
    waiting to be written and when it last wrote."""
    out = []
    for export in _exports(db):
        rows = db.execute_fetchall("SELECT rel_path, state, written_at FROM kept_export_files "
                                   "WHERE export_id = ? ORDER BY rel_path", [export["id"]])
        written = [r[2] for r in rows if r[2] is not None]
        out.append({
            "id": export["id"], "folder": export["folder"], "format": export["format"], "per": export["per"],
            "files": [r[0] for r in rows if r[1] == "written"],
            "in_the_way": [r[0] for r in rows if r[1] == "in-the-way"],
            "pending": jobs.count_jobs(db, KIND, subject_prefix=export["id"]),
            "last_written": max(written) if written else None,
        })
    return out


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    if KIND not in jobs.KINDS:
        jobs.register_kind(KIND, write, model=None, lane="database", name="Write a kept export")
