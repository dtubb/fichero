"""The synced folder: written as the work goes on, and read back (#4952, `specs/source/synced-folder.md`).

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

A folder imported with `mode: index` is **adopted** (`adopt`, `source.sync.adopt-existing-folder`):
it keeps its own layout, each layout file that became a page's pass is recorded with the checksum
it had when read, and work on that page is written back into the same file in the same format,
only while the file is unchanged since; a file changed meanwhile is left and reported. Nothing is
written on adopting: a file is rewritten only when its page changes.

Intake (`read`, a `read-from-folder` job per folder, `source.sync.intake-is-opt-in`) is off for
a made folder until switched on after its preview (`intake`), and on for an adopted one. It reads
back the files Fichero wrote or adopted: one changed outside comes in as a new pass through the
one import action (`format.import`), made by "edited outside Fichero" and named with the file's
time, and overwrites nothing (`source.sync.outside-edits-are-passes`). Each file records two
checksums: the file's (`sha256`) and the exporter's output for it (`exported_sha256`), both as of
Fichero's last write or read. A file changed whose page also changed since is a conflict: the
file's pass is kept beside the project's, the file is no longer written, and it is listed
(`source.sync.conflicts-kept-both`). A deleted file deletes nothing and is listed; it is written
again on the next change to its page (`source.sync.deleted-outside`). The folder is read when the
library opens, when intake is switched on, and when a write finds a file changed.

Files that ARRIVE in a folder with intake on are taken in by the same job: a file in Fichero's
formats carrying a source's lasting id where that source's file went missing is the same file,
renamed or moved (`source.sync.files-carry-ids`); new images, with any layout file beside them,
come in through the one import path (`import_file_set`, as a drop of files does:
`source.sync.one-import-path`, `source.sync.new-images-come-in`); any other file is listed and not
read (`source.sync.read-back-formats`). A folder with intake on is watched while the engine runs
(watchdog, as the automation triggers use), so it is read soon after anything in it changes.

Not built yet: running a subfolder's own recipe on what lands in it, settling a conflict, adopting
a TEI file spanning several images, restricted material, Rebuild Folder, and a folder of part of a
project.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.execution import jobs

logger = logging.getLogger(__name__)

KIND = "write-to-folder"
READ_KIND = "read-from-folder"
#: Who made a pass that came in from the folder: a file's edit carries no author. The working-pass
#: ladder passes such a pass over until a person chooses it.
from fichero_server.models.readings import FROM_SYNCED_FOLDER  # noqa: E402
from fichero_server.models.readings import OUTSIDE_FICHERO as OUTSIDE  # noqa: E402
#: How long a page must stay unchanged before its files are rewritten.
QUIET_SECONDS = 5.0
#: Formats a synced folder can hold for now: the exporter's validated XML formats.
FORMATS = ("pagexml", "alto", "tei")

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS sync_folders (id TEXT PRIMARY KEY, path TEXT NOT NULL, formats TEXT NOT NULL, "
    "created_at TIMESTAMP NOT NULL, untied_at TIMESTAMP)",
    # An adopted folder keeps its own layout: only its recorded files are written, in place.
    "ALTER TABLE sync_folders ADD COLUMN IF NOT EXISTS adopted BOOLEAN DEFAULT FALSE",
    "ALTER TABLE sync_folders ADD COLUMN IF NOT EXISTS intake BOOLEAN DEFAULT FALSE",
    # One row per file Fichero wrote, found in its way, or took in. `state`: written | in-the-way |
    # changed-outside | deleted-outside | conflict | taken-in | not-read-back.
    "CREATE TABLE IF NOT EXISTS sync_files (folder_id TEXT NOT NULL, rel_path TEXT NOT NULL, document_id TEXT, "
    "format TEXT, sha256 TEXT, written_at TIMESTAMP, state TEXT NOT NULL, PRIMARY KEY (folder_id, rel_path))",
    # The exporter's output for the file when Fichero last wrote or read it (null: same as sha256).
    "ALTER TABLE sync_files ADD COLUMN IF NOT EXISTS exported_sha256 TEXT",
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
    rows = db.execute_fetchall("SELECT id, path, formats, created_at, adopted, intake FROM sync_folders "
                               "WHERE untied_at IS NULL ORDER BY created_at")
    return [{"id": r[0], "path": r[1], "formats": json.loads(r[2]), "created_at": r[3], "adopted": bool(r[4]),
             "intake": bool(r[5])} for r in rows]


def _folder(db: Any, folder_id: str) -> dict[str, Any] | None:
    return next((f for f in _folders(db) if f["id"] == folder_id), None)


def _exported(db: Any, doc_id: str, fmt: str) -> str | None:
    """The checksum of what the exporter gives for this page and format now (None: nothing)."""
    from fichero_server.formats import FormatCannotWrite
    from fichero_server.page_export import ExportRefused, export_page

    try:
        return _sha(export_page(db, doc_id, fmt).data)
    except (ExportRefused, FormatCannotWrite):
        return None


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


def adopt(db: Any, folder: Path, read: list[tuple[Path, str, str]]) -> str:
    """Adopt a folder brought in by import (Index): record each file read as a page's pass, with
    its checksum at read, to be written back in place. Writes nothing now."""
    register_job_kinds()
    _ensure(db)
    folder_id = uuid.uuid4().hex
    formats = sorted({fmt for _path, _doc, fmt in read})
    # Adopting turns intake on: that is what adopting means.
    db.execute("INSERT INTO sync_folders (id, path, formats, created_at, adopted, intake) "
               "VALUES (?, ?, ?, ?, TRUE, TRUE)", [folder_id, str(folder), json.dumps(formats), utc_now()])
    for path, doc_id, fmt in read:
        _record(db, folder_id, Path(path).resolve().relative_to(folder).as_posix(), document_id=doc_id, fmt=fmt,
                sha=_sha(Path(path).read_bytes()), exported=_exported(db, doc_id, fmt), state="written",
                written=False)
    _watch(db, _folder(db, folder_id))
    return folder_id


def would_bring_in(db: Any, folder_id: str) -> dict[str, int]:
    """What intake would bring in now, counted by format: the files it keeps that changed outside."""
    folder = _folder(db, folder_id)
    if folder is None:
        raise KeyError(folder_id)
    counts: dict[str, int] = {}
    for rel, fmt, sha in db.execute_fetchall(
            "SELECT rel_path, format, sha256 FROM sync_files WHERE folder_id = ? "
            "AND state IN ('written', 'changed-outside')", [folder_id]):
        path = Path(folder["path"]) / rel
        if path.exists() and _sha(path.read_bytes()) != sha:
            counts[fmt] = counts.get(fmt, 0) + 1
    for _path, kind in _arrivals(db, folder):
        if kind is not None:  # what would not come in is not counted
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def _arrivals(db: Any, folder: dict[str, Any]) -> list[tuple[Path, str | None]]:
    """Files in the folder Fichero has no row for, each with what intake would take it in as:
    `images`, a read-back format's name, or None (not read back)."""
    from fichero_server.formats import format_for
    from fichero_server.importers.interchange_pairing import IMAGE_SUFFIXES

    root = Path(folder["path"])
    known = {r[0] for r in db.execute_fetchall("SELECT rel_path FROM sync_files WHERE folder_id = ?",
                                               [folder["id"]])}
    found = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if (not path.is_file() or any(part.startswith(".") for part in rel.parts)
                or path.name.endswith(".loss.json") or rel.as_posix() in known):
            continue
        if path.suffix.lower() in IMAGE_SUFFIXES:
            found.append((path, "images"))
            continue
        spec = format_for(path.name, path.read_bytes()) if path.suffix.lower() == ".xml" else None
        found.append((path, spec.name if spec is not None and spec.name in FORMATS else None))
    return found


def set_intake(db: Any, folder_id: str, on: bool) -> None:
    """Switch intake on or off for a folder; switched on, the folder is read now."""
    if _folder(db, folder_id) is None:
        raise KeyError(folder_id)
    db.execute("UPDATE sync_folders SET intake = ? WHERE id = ?", [on, folder_id])
    if on:
        _watch(db, _folder(db, folder_id))
        _queue_read(db, folder_id)
    else:
        _unwatch(folder_id)


def _queue_read(db: Any, folder_id: str) -> None:
    register_job_kinds()
    jobs.enqueue(db, READ_KIND, folder_id, started_by="sync",
                 run_after=utc_now() + timedelta(seconds=QUIET_SECONDS))


def untie(db: Any, folder_id: str) -> None:
    """Stop writing to the folder; its files stay on disk (`source.sync.untie-leaves-files`)."""
    _ensure(db)
    db.execute("UPDATE sync_folders SET untied_at = ? WHERE id = ? AND untied_at IS NULL", [utc_now(), folder_id])
    _unwatch(folder_id)


def queue_rewrites(db: Any, document_ids: list[str], *, watched: bool = False) -> None:
    """A change touched these pages: rewrite their files in every tied folder after the quiet period,
    in the change's own transaction. Cheap when nothing is tied. `watched`: a person made the change
    and looks for it in the folder, so the rewrite goes first at utility QoS."""
    if not document_ids:
        return
    folders = _folders(db)
    if not folders:
        return
    after = utc_now() + timedelta(seconds=QUIET_SECONDS)
    for folder in folders:
        for doc_id in dict.fromkeys(document_ids):
            jobs.enqueue(db, KIND, f"{folder['id']}:{doc_id}", started_by="sync", run_after=after, watched=watched)


def _layout(fmt: str, filename: str, doc_id: str, extension: str) -> str:
    stem = filename[: -len(extension)] if extension and filename.endswith(extension) else Path(filename).stem
    return f"{fmt}/{stem}--{doc_id}{extension}"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _record(db: Any, folder_id: str, rel: str, *, document_id: str | None, fmt: str | None, sha: str | None,
            state: str, written: bool, exported: str | None = None) -> None:
    """One file's row. A row that is not a write keeps its last write time."""
    db.execute(
        "INSERT INTO sync_files (folder_id, rel_path, document_id, format, sha256, written_at, state, exported_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (folder_id, rel_path) DO UPDATE SET "
        "document_id = excluded.document_id, format = excluded.format, sha256 = excluded.sha256, "
        "written_at = coalesce(excluded.written_at, sync_files.written_at), state = excluded.state, "
        "exported_sha256 = excluded.exported_sha256",
        [folder_id, rel, document_id, fmt, sha, utc_now() if written else None, state, exported])


def write(db: Any, subject: str) -> None:
    """The job: write one source's files into one folder, never over a file Fichero did not write."""
    from fichero_server.formats import FormatCannotWrite, format_named
    from fichero_server.page_export import ExportRefused, export_page

    folder_id, doc_id = subject.split(":", 1)
    folder = _folder(db, folder_id)
    if folder is None:
        return  # untied meanwhile
    root = Path(folder["path"])
    if folder["adopted"]:
        _write_back(db, folder, root, doc_id)
        return
    for fmt in folder["formats"]:
        try:
            out = export_page(db, doc_id, fmt)
        except (ExportRefused, FormatCannotWrite):
            continue  # nothing to write for this source (no working pass)
        rel = _layout(fmt, out.filename, doc_id, format_named(fmt).file_extension)
        path = root / rel
        known = db.execute_fetchone("SELECT sha256, state, exported_sha256 FROM sync_files "
                                    "WHERE folder_id = ? AND rel_path = ?", [folder_id, rel])
        if known is not None and known[1] == "conflict":
            continue  # two versions wait for a person: neither is written over the other
        if path.exists():
            on_disk = _sha(path.read_bytes())
            if known is None or known[1] == "in-the-way":
                _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=None, state="in-the-way", written=False)
                continue  # not ours: left, and reported
            if known[0] != on_disk:
                _changed_outside(db, folder, rel, doc_id, fmt, known[0], known[2])
                continue  # changed outside since Fichero wrote it: left (and read, with intake on)
        if known is not None and known[0] is not None and (known[2] or known[0]) == _sha(out.data):
            continue  # nothing it holds changed since Fichero wrote it; a deleted one waits for a change
        _atomic_write(path, out.data)
        report = {"format": out.format, "choices": out.choices.as_dict(), "losses": out.report.as_dict()["losses"]}
        _atomic_write(path.with_name(f"{path.name}.loss.json"), json.dumps(report, indent=1).encode("utf-8"))
        _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=_sha(out.data), exported=_sha(out.data),
                state="written", written=True)


def _changed_outside(db: Any, folder: dict[str, Any], rel: str, doc_id: str, fmt: str, sha: str | None,
                     exported: str | None) -> None:
    """A write found the file changed outside: with intake on, the folder is read (the edit comes
    in, or is a conflict); with it off, the file is only reported."""
    if folder["intake"]:
        _queue_read(db, folder["id"])
    else:
        _record(db, folder["id"], rel, document_id=doc_id, fmt=fmt, sha=sha, exported=exported,
                state="changed-outside", written=False)


def _write_back(db: Any, folder: dict[str, Any], root: Path, doc_id: str) -> None:
    """An adopted folder: rewrite the page's own files in place, in their own format, each only
    while it is unchanged since Fichero read or last wrote it (a deleted one is written again). No
    loss report beside: the folder is the person's layout, not Fichero's."""
    from fichero_server.formats import FormatCannotWrite
    from fichero_server.page_export import ExportRefused, export_page

    rows = db.execute_fetchall("SELECT rel_path, format, sha256, exported_sha256 FROM sync_files "
                               "WHERE folder_id = ? AND document_id = ? AND state IN ('written', 'deleted-outside')",
                               [folder["id"], doc_id])
    for rel, fmt, sha, exported in rows:
        path = root / rel
        if path.exists() and _sha(path.read_bytes()) != sha:
            _changed_outside(db, folder, rel, doc_id, fmt, sha, exported)
            continue  # edited meanwhile: left as the person left it
        try:
            out = export_page(db, doc_id, fmt)
        except (ExportRefused, FormatCannotWrite):
            continue
        if (exported or sha) == _sha(out.data):
            continue  # nothing it holds changed since; a deleted one waits for the next change
        _atomic_write(path, out.data)
        _record(db, folder["id"], rel, document_id=doc_id, fmt=fmt, sha=_sha(out.data), exported=_sha(out.data),
                state="written", written=True)


def read(db: Any, folder_id: str) -> None:
    """The intake job: read back the folder's files that changed outside. Each comes in as a new
    pass; one whose page also changed since is a conflict, both kept; a deleted one is listed."""
    folder = _folder(db, folder_id)
    if folder is None or not folder["intake"]:
        return  # untied, or intake switched off, meanwhile
    root = Path(folder["path"])
    arrivals = _follow_renames(db, folder, _arrivals(db, folder))
    rows = db.execute_fetchall(
        "SELECT rel_path, document_id, format, sha256, exported_sha256, state FROM sync_files WHERE folder_id = ? "
        "AND state IN ('written', 'changed-outside', 'deleted-outside')", [folder_id])
    for rel, doc_id, fmt, sha, exported, state in rows:
        path = root / rel
        if not path.exists():
            if state != "deleted-outside":
                _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=sha, exported=exported,
                        state="deleted-outside", written=False)
            continue  # deletes nothing in the project
        on_disk = _sha(path.read_bytes())
        if on_disk == sha:
            if state != "written":  # put back as it was
                _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=sha, exported=exported, state="written",
                        written=False)
            continue
        now = _exported(db, doc_id, fmt)
        project_changed = now is not None and now != (exported or sha)
        if not _bring_in(db, path, doc_id, fmt):
            _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=sha, exported=exported,
                    state="changed-outside", written=False)
            continue  # unreadable as it stands: listed, and read again next time
        if project_changed:
            _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=sha, exported=exported, state="conflict",
                    written=False)
        else:
            _record(db, folder_id, rel, document_id=doc_id, fmt=fmt, sha=on_disk, exported=now, state="written",
                    written=False)
    _take_in(db, folder, arrivals)


def _follow_renames(db: Any, folder: dict[str, Any], arrivals: list[tuple[Path, str | None]]
                    ) -> list[tuple[Path, str | None]]:
    """A file in a read-back format that carries the lasting id of a source whose file in this
    folder is missing is that file, renamed or moved: its row follows it. The rest still arrive."""
    from fichero_server.formats import read_page

    root, left = Path(folder["path"]), []
    for path, kind in arrivals:
        moved = False
        if kind in FORMATS:
            try:
                source = read_page(kind, path.read_bytes()).identity.get("fichero-source")
            except Exception:  # noqa: BLE001 -- a file that does not read is an arrival like any other
                source = None
            for (rel,) in db.execute_fetchall(
                    "SELECT rel_path FROM sync_files WHERE folder_id = ? AND document_id = ? AND format = ? "
                    "AND state IN ('written', 'changed-outside', 'deleted-outside', 'conflict')",
                    [folder["id"], source, kind]) if source else []:
                if not (root / rel).exists():
                    db.execute("UPDATE sync_files SET rel_path = ?, state = CASE WHEN state = 'deleted-outside' "
                               "THEN 'written' ELSE state END WHERE folder_id = ? AND rel_path = ?",
                               [path.relative_to(root).as_posix(), folder["id"], rel])
                    moved = True
                    break
        if not moved:
            left.append((path, kind))
    return left


def _take_in(db: Any, folder: dict[str, Any], arrivals: list[tuple[Path, str | None]]) -> None:
    """New files in the folder: images and the layout files beside them through the one import path
    (linked where they are), anything else listed and not read."""
    from fichero_server.actions.registry import ActionContext
    from fichero_server.api.routes.ingest.core import import_file_set

    root = Path(folder["path"])
    taking = [path for path, kind in arrivals if kind is not None]
    docs = []
    if taking:
        ctx = ActionContext(actor=FROM_SYNCED_FOLDER, library_path=str(Path(db.path).parent), is_bootstrap=True)
        docs, _report = import_file_set(db, taking, ctx, mode="link")
    by_path = {str(Path(d.path).resolve()): d.id for d in docs if d.path}
    for path, kind in arrivals:
        _record(db, folder["id"], path.relative_to(root).as_posix(), document_id=by_path.get(str(path.resolve())),
                fmt=kind if kind in FORMATS else None, sha=_sha(path.read_bytes()),
                state="taken-in" if kind is not None else "not-read-back", written=False)


#: One watcher for every synced folder with intake on, while the engine runs.
_observer: Any = None
_watches: dict[str, Any] = {}
_watch_lock = threading.Lock()


def _watch(db: Any, folder: dict[str, Any] | None) -> None:
    """Watch a folder with intake on: anything changing in it queues a read after the quiet period
    (the job's own `run_after`, so a burst of changes makes one read)."""
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    global _observer
    if folder is None or not Path(folder["path"]).is_dir():
        return
    key, folder_id = jobs._key(db), folder["id"]

    class Changed(FileSystemEventHandler):
        def on_any_event(self, event: Any) -> None:
            if event.is_directory or event.event_type not in ("created", "modified", "moved", "deleted"):
                return
            name = Path(getattr(event, "dest_path", "") or event.src_path).name
            if name.startswith(".") or name.endswith(".loss.json"):
                return  # a temporary file being written, or a loss report
            from fichero_server.db.manager import db_manager

            # One watcher serves every folder: an error here must not end it for all of them.
            try:
                library = db_manager.open_database(key)
                if library is not None:  # closed: it is read again when it opens
                    _queue_read(library, folder_id)
            except Exception:  # noqa: BLE001 -- logged; the folder is read again on open
                logger.warning("synced folder %s: a change could not be queued", folder_id, exc_info=True)

    with _watch_lock:
        if folder_id in _watches and _observer is not None and _observer.is_alive():
            return
        if _observer is None or not _observer.is_alive():
            _observer = Observer()
            _observer.daemon = True
            _observer.start()
            _watches.clear()  # what the old one watched is watched again as each folder asks
        _watches[folder_id] = _observer.schedule(Changed(), folder["path"], recursive=True)


def _unwatch(folder_id: str) -> None:
    with _watch_lock:
        watch = _watches.pop(folder_id, None)
        if watch is not None and _observer is not None:
            _observer.unschedule(watch)


def _bring_in(db: Any, path: Path, doc_id: str, fmt: str) -> bool:
    """The file as a new pass, through the one import action, made by "edited outside Fichero" and
    named with the file's time. A version that came in before is not brought in twice. False when
    the import refuses the file (say, broken XML): the folder goes on."""
    from fastapi import HTTPException

    import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
    from fichero_server.actions.registry import ActionContext, registry

    when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    ctx = ActionContext(actor=OUTSIDE, library_path=str(Path(db.path).parent), is_bootstrap=True)
    try:
        registry.invoke(db, "format.import", {"document_id": doc_id, "path": str(path), "format": fmt,
                                              "name": f"{path.name}, {OUTSIDE} {when}"}, ctx)
    except HTTPException as exc:
        if exc.status_code != 409:  # 409: this very version came in before
            logger.warning("synced folder: %s did not come in: %s", path, exc.detail)
            return False
    return True


def rescan(db: Any) -> None:
    """On library open: compare each tied folder with the checksums Fichero recorded, so changes made
    while the engine was off are found (`source.sync.rescan-after-downtime`)."""
    for folder in _folders(db):
        if folder["intake"]:
            _watch(db, folder)
            _queue_read(db, folder["id"])  # handled as though seen live
            continue
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
            "id": folder["id"], "path": folder["path"], "formats": folder["formats"], "adopted": folder["adopted"],
            "intake": folder["intake"], "conflicts": by_state.get("conflict", []),
            "last_written": max(written_times) if written_times else None, "pending": int(pending),
            "files": by_state.get("written", []), "in_the_way": by_state.get("in-the-way", []),
            "changed_outside": by_state.get("changed-outside", []),
            "taken_in": by_state.get("taken-in", []), "not_read_back": by_state.get("not-read-back", []),
            "deleted_outside": by_state.get("deleted-outside", []),
        })
    return out


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    if KIND not in jobs.KINDS:
        jobs.register_kind(KIND, write, model=None, lane="database", name="Write to a synced folder")
    if READ_KIND not in jobs.KINDS:
        jobs.register_kind(READ_KIND, read, model=None, lane="database", name="Read back a synced folder")
