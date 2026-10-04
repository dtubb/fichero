"""The synced folder, the write half (#4952, `specs/source/synced-folder.md`).

A project is tied to a folder on the engine's disk (`tie`); its outputs (PAGE, ALTO, TEI) are
written there by the exporter (`page_export.export_page`, the one export path:
`source.sync.out-is-the-exporters`) and kept current as the work goes on. Each source's files are
written by one job (kind `write-to-folder`, on the background `database` lane), so writing is
paused, throttled and shown like all background work (`source.sync.engine-side-and-throttled`,
`source.sync.paused-with-background-work`). A change to a page queues its job after a short quiet
period (`QUIET_SECONDS`): a run of corrections makes one rewrite, and only that page's files are
rewritten (`source.sync.outputs-follow-edits`).

A made folder's layout is Fichero's (`source.sync.fixed-layout`): one subfolder per format, one
file per source named `<title>--<lasting id><extension>`, its loss report beside it as
`<file>.loss.json`. Every file is written to a temporary file beside it and renamed into place
(`source.sync.atomic-writes`). Fichero records a checksum of each file it writes and overwrites
only a file it wrote and that is unchanged since: a file in the way that Fichero did not write is
left and reported, and a file changed outside is left and reported
(`source.sync.never-overwrites-a-stranger`). When the library opens, the folder is compared with
those checksums, so changes made while the engine was off are found (`rescan`,
`source.sync.rescan-after-downtime`).

Not built yet: intake (files coming in), reading edits back as passes, conflicts, adopting a
folder (Index), restricted material, Rebuild Folder, and a folder of part of a project.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs

KIND = "write-to-folder"
#: How long a page must stay unchanged before its files are rewritten.
QUIET_SECONDS = 5.0
#: Formats a synced folder can hold for now: the exporter's validated XML formats.
FORMATS = ("pagexml", "alto", "tei")

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sync_folders (id TEXT PRIMARY KEY, path TEXT NOT NULL, formats TEXT NOT NULL, "
    "created_at TIMESTAMP NOT NULL, untied_at TIMESTAMP)",
    # One row per file Fichero wrote or found in its way. `state`: written | in-the-way |
    # changed-outside | deleted-outside.
    "CREATE TABLE IF NOT EXISTS sync_files (folder_id TEXT NOT NULL, rel_path TEXT NOT NULL, document_id TEXT, "
    "format TEXT, sha256 TEXT, written_at TIMESTAMP, state TEXT NOT NULL, PRIMARY KEY (folder_id, rel_path))",
)
_ENSURED: set[str] = set()


def _ensure(db: Any) -> None:
    key = str(db.path)
    if key in _ENSURED:
        return
    for statement in _SCHEMA:
        db.execute(statement)
    _ENSURED.add(key)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _folders(db: Any) -> list[dict[str, Any]]:
    _ensure(db)
    rows = db.execute_fetchall("SELECT id, path, formats, created_at FROM sync_folders WHERE untied_at IS NULL "
                               "ORDER BY created_at")
    return [{"id": r[0], "path": r[1], "formats": json.loads(r[2]), "created_at": r[3]} for r in rows]


def _sources(db: Any) -> list[str]:
    """The project's sources: every live page or file (one without a working pass writes nothing)."""
    rows = db.execute_fetchall("SELECT id FROM documents WHERE doc_type IN ('file', 'page') AND deleted_at IS NULL")
    return [r[0] for r in rows]


def tie(db: Any, path: str, formats: list[str]) -> str:
    """Tie the project to a folder on the engine's disk, and queue its files."""
    from fichero_server.formats import format_named

    folder = Path(path)
    if not folder.is_absolute():
        raise ValueError(f"{path!r} is not a full path on the engine's disk")
    if not formats:
        raise ValueError("name at least one format to write")
    for name in formats:
        if format_named(name).name not in FORMATS:
            raise ValueError(f"a synced folder holds {', '.join(FORMATS)}; not {name!r}")
    folder.mkdir(parents=True, exist_ok=True)
    register_job_kinds()
    _ensure(db)
    folder_id = uuid.uuid4().hex
    db.execute("INSERT INTO sync_folders (id, path, formats, created_at) VALUES (?, ?, ?, ?)",
               [folder_id, str(folder), json.dumps(list(formats)), utc_now()])
    jobs.enqueue_many(db, KIND, [f"{folder_id}:{doc_id}" for doc_id in _sources(db)], started_by="sync")
    return folder_id


def untie(db: Any, folder_id: str) -> None:
    """Stop writing to the folder; its files stay on disk (`source.sync.untie-leaves-files`)."""
    _ensure(db)
    db.execute("UPDATE sync_folders SET untied_at = ? WHERE id = ? AND untied_at IS NULL", [utc_now(), folder_id])


def queue_rewrites(db: Any, document_ids: list[str]) -> None:
    """A change touched these pages: rewrite their files in every tied folder after the quiet period,
    in the change's own transaction. Cheap when nothing is tied."""
    if not document_ids:
        return
    folders = _folders(db)
    if not folders:
        return
    after = utc_now() + timedelta(seconds=QUIET_SECONDS)
    for folder in folders:
        for doc_id in dict.fromkeys(document_ids):
            jobs.enqueue(db, KIND, f"{folder['id']}:{doc_id}", started_by="sync", run_after=after)


def _layout(fmt: str, filename: str, doc_id: str, extension: str) -> str:
    stem = filename[: -len(extension)] if extension and filename.endswith(extension) else Path(filename).stem
    return f"{fmt}/{stem}--{doc_id}{extension}"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _record(db: Any, folder_id: str, rel: str, *, document_id: str | None, fmt: str | None, sha: str | None,
            state: str, written: bool) -> None:
    db.execute(
        "INSERT INTO sync_files (folder_id, rel_path, document_id, format, sha256, written_at, state) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (folder_id, rel_path) DO UPDATE SET document_id = excluded.document_id, "
        "format = excluded.format, sha256 = excluded.sha256, written_at = excluded.written_at, state = excluded.state",
        [folder_id, rel, document_id, fmt, sha, utc_now() if written else None, state])


def write(db: Any, subject: str) -> None:
    """The job: write one source's files into one folder, never over a file Fichero did not write."""
    from fichero_server.formats import FormatCannotWrite, format_named
    from fichero_server.page_export import ExportRefused, export_page

    folder_id, doc_id = subject.split(":", 1)
    folder = next((f for f in _folders(db) if f["id"] == folder_id), None)
    if folder is None:
        return  # untied meanwhile
    root = Path(folder["path"])
    for fmt in folder["formats"]:
        try:
            out = export_page(db, doc_id, fmt)
        except (ExportRefused, FormatCannotWrite):
            continue  # nothing to write for this source (no working pass)
        rel = _layout(fmt, out.filename, doc_id, format_named(fmt).file_extension)
        path = root / rel
        known = db.execute_fetchone("SELECT sha256, state FROM sync_files WHERE folder_id = ? AND rel_path = ?",
                                    [folder_id, rel])
        if path.exists():
            on_disk = _sha(path.read_bytes())
            if known is None or known[1] == "in-the-way":
                _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=None, state="in-the-way", written=False)
                continue  # not ours: left, and reported
            if known[0] != on_disk:
                _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=known[0], state="changed-outside",
                        written=False)
                continue  # changed outside since Fichero wrote it: left, and reported
            if on_disk == _sha(out.data):
                continue  # nothing this file holds has changed
        _atomic_write(path, out.data)
        report = {"format": out.format, "choices": out.choices.as_dict(), "losses": out.report.as_dict()["losses"]}
        _atomic_write(path.with_name(f"{path.name}.loss.json"), json.dumps(report, indent=1).encode("utf-8"))
        _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=_sha(out.data), state="written", written=True)


def rescan(db: Any) -> None:
    """On library open: compare each tied folder with the checksums Fichero recorded, so changes made
    while the engine was off are found (`source.sync.rescan-after-downtime`)."""
    for folder in _folders(db):
        root = Path(folder["path"])
        rows = db.execute_fetchall(
            "SELECT rel_path, sha256 FROM sync_files WHERE folder_id = ? AND state = 'written'", [folder["id"]])
        for rel, sha in rows:
            path = root / rel
            if not path.exists():
                db.execute("UPDATE sync_files SET state = 'deleted-outside' WHERE folder_id = ? AND rel_path = ?",
                           [folder["id"], rel])
            elif _sha(path.read_bytes()) != sha:
                db.execute("UPDATE sync_files SET state = 'changed-outside' WHERE folder_id = ? AND rel_path = ?",
                           [folder["id"], rel])


def status(db: Any) -> list[dict[str, Any]]:
    """Each tied folder: where, which formats, last written, files waiting to be written, and the
    files written, in the way, changed outside and deleted outside."""
    out = []
    for folder in _folders(db):
        rows = db.execute_fetchall("SELECT rel_path, state, written_at FROM sync_files WHERE folder_id = ? "
                                   "ORDER BY rel_path", [folder["id"]])
        by_state: dict[str, list[str]] = {}
        for rel, state, _written in rows:
            by_state.setdefault(state, []).append(rel)
        written_times = [r[2] for r in rows if r[2] is not None]
        pending = jobs.count_jobs(db, KIND, subject_prefix=f"{folder['id']}:")
        out.append({
            "id": folder["id"], "path": folder["path"], "formats": folder["formats"],
            "last_written": max(written_times) if written_times else None, "pending": int(pending),
            "files": by_state.get("written", []), "in_the_way": by_state.get("in-the-way", []),
            "changed_outside": by_state.get("changed-outside", []),
            "deleted_outside": by_state.get("deleted-outside", []),
        })
    return out


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    if KIND not in jobs.KINDS:
        jobs.register_kind(KIND, write, model=None, lane="database", name="Write to a synced folder")
