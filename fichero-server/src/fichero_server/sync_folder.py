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

A folder in mode `keep-arranged` (#5480, `source.onboard.keep-arranged`; the default is `index`) is
also arranged: its files sit where the project's own structure says. The project folder made by
importing the folder (its `path` is the folder) stands for the folder itself; each document under it
with its file in the folder belongs at `<the project folders between>/<its name>`. A document moved
or renamed in the project, or a folder renamed, queues one arrangement (`queue_arrangement`, kind
`arrange-folder`), which runs the audited, undoable `sync.arrange` action: every file it moves is
listed (from, to), and undo puts each one back. Files are moved and renamed only inside the folder,
never out of it, never over another file (a clash takes a numeric suffix, `name 2.jpg`), and none is
ever deleted; a folder that cannot be written to is refused in words and nothing moves. `plan`
is the dry run: what would move, shown before the first arrangement. A file the person moves by
hand inside the folder stays where they put it: the watcher finds it (by its checksum, where its
document's file went missing) and the project follows it (`follow_hand_moves`): its record takes
the new place, the document moves to the project folder of the same name (made if missing) and
takes the file's new name, and it is marked as placed by hand.

Not built yet: running a subfolder's own recipe on what lands in it, settling a conflict, adopting
a TEI file spanning several images, restricted material, Rebuild Folder, and a folder of part of a
project. Keep arranged by date or by a written rule (spec open question 10), and moving a layout
file (an adopted folder's `page/` XML) along with its image.
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
    # `index` (files stay where they are) or `keep-arranged` (#5480).
    "ALTER TABLE sync_folders ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'index'",
)
INDEX, KEEP_ARRANGED = "index", "keep-arranged"
MODES = (INDEX, KEEP_ARRANGED)
ARRANGE_KIND = "arrange-folder"
#: Project changes that can change where a file belongs (a move, a rename, an undo of either).
ARRANGING_ACTIONS = frozenset({"document.move", "document.update", "document.restore", "document.create"})
#: Who arranges, in the audit: the files move because the project changed, not by a person's hand.
ARRANGER = "Fichero, keeping the folder arranged"
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
    rows = db.execute_fetchall("SELECT id, path, formats, created_at, adopted, intake, mode FROM sync_folders "
                               "WHERE untied_at IS NULL ORDER BY created_at")
    return [{"id": r[0], "path": r[1], "formats": json.loads(r[2]), "created_at": r[3], "adopted": bool(r[4]),
             "intake": bool(r[5]), "mode": r[6] or INDEX} for r in rows]


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


def tie(db: Any, path: str, formats: list[str], mode: str = INDEX) -> str:
    """Tie the project to a folder on the engine's disk, and queue its files. Kept arranged, the
    folder must be one the project imported, and writable; it may hold no written formats."""
    from fichero_server.formats import format_named

    folder = Path(path)
    if not folder.is_absolute():
        raise ValueError(f"{path!r} is not a full path on the engine's disk")
    if mode not in MODES:
        raise ValueError(f"a synced folder is kept as {' or '.join(MODES)}; not {mode!r}")
    if not formats and mode != KEEP_ARRANGED:
        raise ValueError("name at least one format to write")
    for name in formats:
        if format_named(name).name not in FORMATS:
            raise ValueError(f"a synced folder holds {', '.join(FORMATS)}; not {name!r}")
    if mode == KEEP_ARRANGED:
        _refuse_unless_arrangeable(db, folder)
    folder.mkdir(parents=True, exist_ok=True)
    register_job_kinds()
    _ensure(db)
    folder_id = uuid.uuid4().hex
    db.execute("INSERT INTO sync_folders (id, path, formats, created_at, mode) VALUES (?, ?, ?, ?, ?)",
               [folder_id, str(folder), json.dumps(list(formats)), utc_now(), mode])
    jobs.enqueue_many(db, KIND, [f"{folder_id}:{doc_id}" for doc_id in _sources(db)], started_by="sync")
    if mode == KEEP_ARRANGED:
        _watch(db, _folder(db, folder_id))
        _queue_arrange(db, folder_id)
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
    if folder.get("mode") == KEEP_ARRANGED:  # a file that is a document's own file has not arrived
        known |= {rel for _doc, rel in _documents_in(db, root)}
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
    elif _folder(db, folder_id)["mode"] != KEEP_ARRANGED:  # an arranged folder is still watched for hand moves
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
    and looks for it in the folder, so the rewrite goes first at utility QoS. Every kept export
    (#5485) is rewritten from the same change."""
    if not document_ids:
        return
    from fichero_server import kept_export

    kept_export.queue_rewrites(db, document_ids, watched=watched)
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
    arranged = folder is not None and folder["mode"] == KEEP_ARRANGED
    if folder is None or not (folder["intake"] or arranged):
        return  # untied, or intake switched off, meanwhile
    root = Path(folder["path"])
    arrivals = _arrivals(db, folder)
    if arranged:
        arrivals = follow_hand_moves(db, folder, arrivals)
        if not folder["intake"]:
            return  # kept arranged without intake: hand moves are followed, nothing else comes in
    arrivals = _follow_renames(db, folder, arrivals)
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
        if folder["intake"] or folder["mode"] == KEEP_ARRANGED:
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
            "mode": folder["mode"],
            "intake": folder["intake"], "conflicts": by_state.get("conflict", []),
            "last_written": max(written_times) if written_times else None, "pending": int(pending),
            "files": by_state.get("written", []), "in_the_way": by_state.get("in-the-way", []),
            "changed_outside": by_state.get("changed-outside", []),
            "taken_in": by_state.get("taken-in", []), "not_read_back": by_state.get("not-read-back", []),
            "deleted_outside": by_state.get("deleted-outside", []),
        })
    return out


# ---------------------------------------------------------------------------------------------------
# Keep arranged (#5480): the folder follows the project's structure, and the project follows a hand.
# ---------------------------------------------------------------------------------------------------


def _documents_in(db: Any, root: Path) -> list[tuple[str, str]]:
    """Each live file document whose file is inside the folder: (document id, path in the folder)."""
    roots = {str(root), os.path.realpath(root)}
    found = []
    for doc_id, path in db.execute_fetchall("SELECT id, path FROM documents WHERE doc_type = 'file' "
                                            "AND deleted_at IS NULL AND path IS NOT NULL"):
        for base in roots:
            if path.startswith(base + os.sep):
                found.append((doc_id, Path(os.path.relpath(path, base)).as_posix()))
                break
    return found


def _anchor(db: Any, root: Path) -> str | None:
    """The project folder that stands for the folder itself: the one importing it made."""
    real = os.path.realpath(root)
    for doc_id, path in db.execute_fetchall("SELECT id, path FROM documents WHERE doc_type = 'folder' "
                                            "AND deleted_at IS NULL AND path IS NOT NULL ORDER BY created_at"):
        if os.path.realpath(path) == real:
            return doc_id
    return None


def _refuse_unless_arrangeable(db: Any, root: Path) -> None:
    """Refused in words: a folder that is not there, cannot be written to, or that no project folder
    came from (so the project has no structure for it)."""
    if not root.is_dir():
        raise ValueError(f"{root} is not a folder on the engine's disk, so it cannot be kept arranged.")
    if not os.access(root, os.W_OK):
        raise ValueError(f"Fichero cannot write to {root}, so it cannot keep it arranged: nothing was moved. "
                         "Make the folder writable, or keep it as Index.")
    if _anchor(db, root) is None:
        raise ValueError(f"No project folder came from {root}: import it with Index first, then keep it arranged.")


def _safe_name(name: str, fallback: str) -> str:
    name = name.replace("/", "-").replace("\0", "").strip()
    return fallback if name in ("", ".", "..") else name


def _belongs_at(db: Any, anchor: str, doc_id: str, rel: str, cache: dict[str, Any]) -> str | None:
    """Where the document's file belongs in the folder: the project folders between the anchor and
    the document, then the document's name (keeping its file's extension). None: the document is
    no longer under the anchor, so its file stays where it is (moves only inside the folder)."""
    from fichero_server.models import Document

    def get(i: str) -> Any:
        if i not in cache:
            cache[i] = db.get(Document, i)
        return cache[i]

    doc, current = get(doc_id), Path(rel)
    if doc is None:
        return None
    name = _safe_name(doc.name, current.name)
    if current.suffix and Path(name).suffix.lower() != current.suffix.lower():
        name += current.suffix
    parts, parent = [], doc.parent_id
    while parent != anchor:
        node = get(parent) if parent else None
        if node is None or node.deleted_at is not None:
            return None
        parts.append(_safe_name(node.name, "folder"))
        parent = node.parent_id
    return Path(*reversed(parts), name).as_posix()


def _suffixed(want: str, n: int) -> str:
    path = Path(want)
    return path.with_name(f"{path.stem} {n}{path.suffix}").as_posix()


def _is_suffixed_variant(rel: str, want: str) -> bool:
    """`name 2.jpg` beside `name.jpg`: a clash already resolved, not a file out of place."""
    import re

    current, wanted = Path(rel), Path(want)
    return current.parent == wanted.parent and re.fullmatch(
        rf"{re.escape(wanted.stem)} \d+{re.escape(wanted.suffix)}", current.name) is not None


def _free(root: Path, want: str, claimed: set[str], own: Path | None = None) -> str:
    """`want`, or the first `name N.ext` that is neither on disk nor claimed: never over a file."""
    n, candidate = 1, want
    while candidate in claimed or ((root / candidate).exists()
                                   and not (own is not None and own.exists() and os.path.samefile(root / candidate, own))):
        n += 1
        candidate = _suffixed(want, n)
    return candidate


def _unwritable(root: Path, moves: list[dict[str, str]]) -> str | None:
    """Words for why these moves cannot be made, or None."""
    dirs = {root}
    for move in moves:
        dirs.add((root / move["from_path"]).parent)
        target = (root / move["to_path"]).parent
        while not target.exists() and target != root:
            target = target.parent
        dirs.add(target)
    for directory in sorted(dirs):
        if directory.exists() and not os.access(directory, os.W_OK):
            return (f"Fichero cannot write to {directory}, so it cannot keep {root} arranged: nothing was moved. "
                    "Make the folder writable, or keep it as Index.")
    return None


def plan(db: Any, folder_id: str) -> tuple[list[dict[str, str]], str | None]:
    """The dry run: each move an arrangement would make now (document, from, to: paths in the
    folder), and words for why it would be refused, if it would be. Moves nothing."""
    folder = _folder(db, folder_id)
    if folder is None:
        raise KeyError(folder_id)
    root = Path(folder["path"])
    anchor = _anchor(db, root)
    if anchor is None:
        return [], f"No project folder came from {root}: import it with Index first, then keep it arranged."
    moves: list[dict[str, str]] = []
    claimed: set[str] = set()
    cache: dict[str, Any] = {}
    for doc_id, rel in sorted(_documents_in(db, root), key=lambda item: item[1]):
        if not (root / rel).exists():
            continue  # moved by hand and not yet followed: the read follows it
        want = _belongs_at(db, anchor, doc_id, rel, cache)
        if want is None or want == rel:
            continue
        if _is_suffixed_variant(rel, want) and ((root / want).exists() or want in claimed):
            continue
        target = _free(root, want, claimed, own=root / rel)
        if target == rel:
            continue
        claimed.add(target)
        moves.append({"document_id": doc_id, "from_path": rel, "to_path": target})
    return moves, _unwritable(root, moves)


def _inside(root: Path, rel: str) -> Path:
    """`rel` as a path inside the folder; refused if it would leave it."""
    norm = os.path.normpath(rel)
    if os.path.isabs(norm) or norm == ".." or norm.startswith(".." + os.sep) or norm == ".":
        raise ValueError(f"{rel!r} is not a path inside {root}: Fichero moves files only inside the folder.")
    return root / norm


def _move_no_overwrite(src: Path, dst: Path) -> None:
    """Move one file, never over another (a hard link fails if the name is taken)."""
    if dst.exists():
        if not os.path.samefile(src, dst):  # a case-only rename on a case-blind disk is the same file
            raise FileExistsError(dst)
        os.rename(src, dst)
        return
    try:
        os.link(src, dst)
    except FileExistsError:
        raise
    except OSError:  # a disk that cannot hard-link: checked above, renamed
        os.rename(src, dst)
        return
    os.unlink(src)


def _prune(directory: Path, root: Path) -> None:
    """Remove folders a move left empty, up to the tied folder (never it, never one holding anything)."""
    while directory != root and root in directory.parents:
        try:
            directory.rmdir()  # fails on a folder that holds anything: nothing is ever deleted
        except OSError:
            return
        directory = directory.parent


def _repoint(db: Any, folder_id: str, doc_id: str, root: Path, old_rel: str, new_rel: str, **marks: Any) -> None:
    """The document's record follows its file; so do the folder's own rows for it."""
    from fichero_server.models import Document

    doc = db.get(Document, doc_id)
    old_path, new_path = doc.path, str(root / new_rel)
    doc.path = new_path
    metadata = dict(doc.metadata or {})
    if metadata.get("source_path") in (old_path, str(root / old_rel)):
        metadata["source_path"] = new_path
    metadata.update(marks)
    doc.metadata = metadata
    db.save(doc)
    db.execute("UPDATE sync_files SET rel_path = ? WHERE folder_id = ? AND rel_path = ?", [new_rel, folder_id, old_rel])


def arrange(db: Any, folder_id: str, moves: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    """Make the moves (the plan's, or the ones given: an undo's), each only inside the folder and
    never over a file, and return the moves made. Refused in words (ValueError) if the folder cannot
    be written to: then nothing moves."""
    folder = _folder(db, folder_id)
    if folder is None:
        raise KeyError(folder_id)
    root = Path(folder["path"])
    if moves is None:
        if folder["mode"] != KEEP_ARRANGED:
            return []
        moves, refused = plan(db, folder_id)
    else:
        refused = _unwritable(root, moves)
    if refused:
        raise ValueError(refused)
    done, claimed = [], set()
    for move in moves:
        src, want = _inside(root, move["from_path"]), _inside(root, move["to_path"])
        if not src.is_file():
            continue  # gone, or moved by hand meanwhile: nothing to move
        target = _free(root, want.relative_to(root).as_posix(), claimed, own=src)
        dst = root / target
        dst.parent.mkdir(parents=True, exist_ok=True)
        _move_no_overwrite(src, dst)
        claimed.add(target)
        _repoint(db, folder_id, move["document_id"], root, move["from_path"], target)
        _prune(src.parent, root)
        done.append({"document_id": move["document_id"], "from_path": move["from_path"], "to_path": target})
    return done


def set_mode(db: Any, folder_id: str, mode: str) -> None:
    """Keep the folder as Index or Keep arranged. Switched to Keep arranged (after its preview: the
    person said yes), it is arranged now and watched for hand moves."""
    folder = _folder(db, folder_id)
    if folder is None:
        raise KeyError(folder_id)
    if mode not in MODES:
        raise ValueError(f"a synced folder is kept as {' or '.join(MODES)}; not {mode!r}")
    if mode == KEEP_ARRANGED:
        _refuse_unless_arrangeable(db, Path(folder["path"]))
    db.execute("UPDATE sync_folders SET mode = ? WHERE id = ?", [mode, folder_id])
    if mode == KEEP_ARRANGED:
        _watch(db, _folder(db, folder_id))
        _queue_arrange(db, folder_id)
    elif not folder["intake"]:
        _unwatch(folder_id)


def _queue_arrange(db: Any, folder_id: str) -> None:
    register_job_kinds()
    jobs.enqueue(db, ARRANGE_KIND, folder_id, started_by="sync",
                 run_after=utc_now() + timedelta(seconds=QUIET_SECONDS))


def queue_arrangement(db: Any, action_name: str) -> None:
    """A project change that can move where files belong: arrange each kept-arranged folder after
    the quiet period, in the change's own transaction. Cheap for any other action."""
    if action_name not in ARRANGING_ACTIONS:
        return
    for folder in _folders(db):
        if folder["mode"] == KEEP_ARRANGED:
            _queue_arrange(db, folder["id"])


def _context(db: Any, actor: str) -> Any:
    from fichero_server.actions.registry import ActionContext

    return ActionContext(actor=actor, library_path=str(Path(db.path).parent), is_bootstrap=True)


def _arrange_job(db: Any, folder_id: str) -> None:
    """The job: one audited `sync.arrange` when anything is out of place (none when nothing is)."""
    import fichero_server.api.routes.sync_folders  # noqa: F401  (registers sync.arrange)
    from fichero_server.actions.registry import registry

    folder = _folder(db, folder_id)
    if folder is None or folder["mode"] != KEEP_ARRANGED or not plan(db, folder_id)[0]:
        return
    registry.invoke(db, "sync.arrange", {"folder_id": folder_id}, _context(db, ARRANGER))


def follow_hand_moves(db: Any, folder: dict[str, Any], arrivals: list[tuple[Path, str | None]]
                      ) -> list[tuple[Path, str | None]]:
    """A file that arrived where a document's own file went missing, with the same checksum, is that
    file moved by hand: it stays where the person put it, and the project follows (its record, its
    project folder, its name), marked as placed by hand. The rest still arrive."""
    from fichero_server.importers.ingest import _file_checksum
    from fichero_server.models import Document

    root = Path(folder["path"])
    missing: dict[str, tuple[str, str]] = {}
    for doc_id, rel in _documents_in(db, root):
        if not (root / rel).exists():
            doc = db.get(Document, doc_id)
            checksum = (doc.metadata or {}).get("checksum") if doc else None
            if isinstance(checksum, str):
                missing.setdefault(checksum, (doc_id, rel))
    if not missing:
        return arrivals
    import fichero_server.api.routes.document.documents  # noqa: F401  (registers document.*)
    import fichero_server.api.routes.sync_folders  # noqa: F401  (registers sync.follow)
    from fichero_server.actions.registry import registry

    ctx, anchor, left = _context(db, FROM_SYNCED_FOLDER), _anchor(db, root), []
    for path, kind in arrivals:
        found = missing.pop(_file_checksum(path), None)
        if found is None:
            left.append((path, kind))
            continue
        doc_id, old_rel = found
        new_rel = path.relative_to(root).as_posix()
        registry.invoke(db, "sync.follow", {"folder_id": folder["id"], "document_id": doc_id,
                                            "from_path": old_rel, "to_path": new_rel}, ctx)
        if anchor is not None:
            _follow_in_project(db, registry, ctx, anchor, doc_id, Path(new_rel))
    return left


def _follow_in_project(db: Any, registry: Any, ctx: Any, anchor: str, doc_id: str, rel: Path) -> None:
    """The project follows the folder: the document takes the file's name and moves to the project
    folder named as the file's folder is (made if missing), so nothing would move it back."""
    from fichero_server.models import Document

    parent = anchor
    for part in rel.parent.parts:
        child = next((d for d in db.query(Document, parent_id=parent, name=part)
                      if d.doc_type == "folder" and d.deleted_at is None), None)
        parent = child.id if child is not None else registry.invoke(
            db, "document.create", {"name": part, "parent_id": parent, "doc_type": "folder"}, ctx).result["id"]
    doc = db.get(Document, doc_id)
    if doc.name != rel.name:
        registry.invoke(db, "document.update", {"doc_id": doc_id, "update": {"name": rel.name}}, ctx)
    if doc.parent_id != parent:
        registry.invoke(db, "document.move", {"doc_id": doc_id, "parent_id": parent}, ctx)


def follow(db: Any, folder_id: str, doc_id: str, old_rel: str, new_rel: str) -> None:
    """Record a hand move: the document's file is now at `new_rel`, placed there by hand."""
    folder = _folder(db, folder_id)
    if folder is None:
        raise KeyError(folder_id)
    root = Path(folder["path"])
    _inside(root, new_rel)
    _repoint(db, folder_id, doc_id, root, old_rel, new_rel, placed_by_hand=utc_now().isoformat())


def register_job_kinds() -> None:
    """Called by the scheduler before its first scan (`execution.jobs._KIND_MODULES`)."""
    if KIND not in jobs.KINDS:
        jobs.register_kind(KIND, write, model=None, lane="database", name="Write to a synced folder")
    if READ_KIND not in jobs.KINDS:
        jobs.register_kind(READ_KIND, read, model=None, lane="database", name="Read back a synced folder")
    if ARRANGE_KIND not in jobs.KINDS:
        jobs.register_kind(ARRANGE_KIND, _arrange_job, model=None, lane="database",
                           name="Keep a synced folder arranged")
