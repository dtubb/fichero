"""A copy to another engine (another Mac running Fichero, or a server): package here, land there (#5657).

Spec: `source/moving-between-projects.md`, "Between machines (copy only)". Between machines a transfer is
always a copy: the source is never changed by it, beyond the record it keeps.

The same code as a copy on one engine, split in two halves (`transfer.machine.one-code-path`):

* **The sending engine packages** the set `plan.gather_set` reads from the source (the rows that travel, and
  what is cut or left behind), with the project vocabulary and the entities' authority links the landing side
  matches against, as ONE object of rows (`records.json`), beside each in-package original as an object of
  its own. The package is a `SyncManifest` of those objects by sha256 (`compute.package.is-a-sync-manifest`).
* **It pushes** through the library-sync core (`compute.transfer.one-core`): the far engine is asked which
  objects it lacks (`diff_manifests`, its `SyncCheckpoint`, `pending_objects`), only those are sent
  (`compute.transfer.only-what-is-missing`), each re-hashed on arrival (`land_object`,
  `compute.transfer.verified-on-arrival`). An interrupted send, sent again, moves only what had not arrived
  (`compute.transfer.resumes`): the far side keeps what arrived, keyed by the transfer's id.
* **The far engine lands** the package only once every object is there: the rows become a project of their own
  in its incoming folder, and `build_plan` + `copy_into_target` copy them in exactly as from an open project
  on one engine (new ids, entities matched as proposed merges, cuts listed, verified, all or nothing). What
  lands is stamped with the far engine's paired person (`compute.land.server-sets-the-maker`); every node
  records the machine and project it came from.

Auth is the existing device pairing (`transfer/machines.py`); versions must match (the contract's sha256).
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fichero_server.core.timeutil import utc_now
from fichero_server.models.transfer import (
    IncomingTransfer,
    TransferMode,
    TransferRecord,
    TransferResult,
    TransferRole,
    TransferState,
)
from fichero_server.workflows.library_sync import (
    LibrarySyncError,
    SyncCheckpoint,
    SyncManifest,
    SyncObject,
    build_manifest_from_listing,
    diff_manifests,
    pending_objects,
)
from fichero_server.workflows.library_sync_io import hash_file, land_object

RECORDS = "records.json"
LIBRARY_HEADER = "X-Fichero-Library-Path"
INCOMING = "/api/documents/transfer/incoming"
#: The project vocabulary the landing side matches by key or by name (`plan._Vocabulary`). Sent whole:
#: ponytail: these tables are small; only the records the set names, if one ever is not.
VOCABULARY = ("LibraryReadingKind", "LibraryReadingLevel", "LibraryLinkType", "ClassificationValue",
              "Hand", "Allograph", "InterpretiveFramework")


#: What a far peer may make this machine hold (`transfer.machine.incoming-bounded`): refused at open, before
#: anything is written, and again on every object. ponytail: constants; a setting if a person ever needs more.
MAX_OBJECT_BYTES = 512 * 1024 * 1024  # one object is read into memory on arrival
MAX_TRANSFER_BYTES = 20 * 1024 * 1024 * 1024
MAX_OBJECTS = 100_000
#: Left free on this disk after every open copy has arrived (`user-machine-always-useful`).
FREE_FLOOR_BYTES = 5 * 1024 * 1024 * 1024
#: An incoming copy nothing has arrived for or landed this long is abandoned the next time one opens.
STALE_AFTER_SECONDS = 7 * 24 * 3600
_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class TooBig(ValueError):
    """More than this machine takes from a peer, refused before anything is written."""


def _lock(target_db, transfer_id: str) -> threading.Lock:
    """One copy's objects, landing and abandoning never interleave."""
    key = f"{Path(target_db.path).parent}:{transfer_id}"
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


class VersionMismatch(ValueError):
    pass


class MachineTransferStopped(RuntimeError):
    """The send stopped; what arrived is kept on the far side, nothing landed, the source is unchanged."""


def contract() -> str:
    from fichero_server.api.contract_identity_generated import CONTRACT_SHA256

    return CONTRACT_SHA256


# =============================================================================================
# The sending side: the package
# =============================================================================================


def _outgoing(source_db, transfer_id: str) -> Path:
    return Path(source_db.path).parent / "transfers" / "outgoing" / transfer_id


def make_package(source_db, items: list[str], transfer_id: str) -> tuple[SyncManifest, dict[str, Path]]:
    """The package's manifest, and where each object's bytes are here (by sha256). The rows are written once
    per transfer, so a resumed send offers the very same objects."""
    from fichero_server.knowledge.authorities import SAME_AS
    from fichero_server.transfer.plan import _package_relative, gather_set

    package = Path(source_db.path).parent
    out = _outgoing(source_db, transfer_id)
    records_path = out / RECORDS
    if not records_path.exists():
        plan = gather_set(source_db, items)
        rows: dict[str, list[dict[str, Any]]] = {
            name: [row.model_dump(mode="json") for row in found.values()] for name, found in plan.rows.items()}
        for name in VOCABULARY:
            have = {r["id"] for r in rows.get(name, [])}
            rows.setdefault(name, []).extend(
                r.model_dump(mode="json") for r in source_db.all(plan.models[name]) if r.id not in have)
        entities = set(plan.rows.get("KnowledgeEntity", {}))
        have = {r["id"] for r in rows.get("TypedLink", [])}
        rows.setdefault("TypedLink", []).extend(
            link.model_dump(mode="json") for link in source_db.query(plan.models["TypedLink"], link_type=SAME_AS)
            if link.from_id in entities and link.id not in have and link.deleted_at is None)
        files = sorted({_package_relative(package, doc.path).as_posix() for doc in plan.rows["Document"].values()
                        if _package_relative(package, doc.path) is not None})
        header = {"items": list(items), "package_root": str(package), "files": files,
                  "cuts": [c.model_dump(mode="json") for c in plan.cuts],
                  "left_behind": [lb.model_dump(mode="json") for lb in plan.left_behind]}
        out.mkdir(parents=True, exist_ok=True)
        tmp = records_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"transfer": header, "rows": rows}, sort_keys=True), encoding="utf-8")
        tmp.replace(records_path)
    header = json.loads(records_path.read_text(encoding="utf-8"))["transfer"]
    where: dict[str, Path] = {}
    objects: list[SyncObject] = []
    for rel, path in [(RECORDS, records_path), *((f, package / f) for f in header["files"])]:
        sha, size = hash_file(path)
        objects.append(SyncObject(rel=rel, sha256=sha, size=size, kind="db" if rel == RECORDS else "file"))
        where[sha] = path
    return build_manifest_from_listing(library_id=transfer_id, generation=1, objects=objects,
                                       produced_at=utc_now().isoformat()), where


def _say(response) -> str:
    try:
        return str(response.json().get("detail") or response.status_code)
    except ValueError:
        return f"HTTP {response.status_code}"


def send(source_db, *, items: list[str], machine, target_project: str, target_parent_id: str | None,
         transfer_id: str, actor: str) -> TransferResult:
    """Push the package to the far engine and have it land there. Raises `MachineTransferStopped`."""
    import httpx

    from fichero_server.transfer import machines

    source_name = Path(source_db.path).parent.stem
    far_name = f"{machine.name}: {Path(target_project).stem}"
    record = source_db.get(TransferRecord, transfer_id)
    if record is None:
        record = TransferRecord(id=transfer_id, role=TransferRole.source, state=TransferState.sending,
                                mode=TransferMode.copy, source_project=str(Path(source_db.path).parent),
                                target_project=f"{machine.name}:{target_project}", items=list(items), created_by=actor)
        source_db.save(record)  # the mirror journal, before anything is sent
    manifest, where = make_package(source_db, items, transfer_id)
    total, sent = len({o.sha256 for o in manifest.objects}), 0
    header = {LIBRARY_HEADER: target_project}
    far = machines.client(machine.url, machine.token)
    try:
        opened = far.post(INCOMING, headers=header, json=IncomingTransfer(
            transfer_id=transfer_id, manifest=json.loads(manifest.to_json()), source_machine=machines.this_machine(),
            source_project=str(Path(source_db.path).parent), contract=contract()).model_dump())
        if opened.status_code != 200:
            raise MachineTransferStopped(f"{machine.name} refused the copy: {_say(opened)}")
        for sha in opened.json()["missing"]:
            arrived = far.put(f"{INCOMING}/{transfer_id}/objects/{sha}", headers={**header, "Content-Type": "application/octet-stream"},
                              content=where[sha].read_bytes())
            if arrived.status_code != 200:
                raise MachineTransferStopped(f"an object did not arrive whole: {_say(arrived)}")
            sent += 1
        landed = far.post(f"{INCOMING}/{transfer_id}/land", headers=header, json={"target_parent_id": target_parent_id})
        if landed.status_code != 200:
            raise MachineTransferStopped(f"landing it there failed and was rolled back: {_say(landed)}")
    except (httpx.HTTPError, OSError, MachineTransferStopped) as exc:
        reason = str(exc) or type(exc).__name__
        record.error, record.updated_at = reason, utc_now()
        source_db.save(record)
        raise MachineTransferStopped(
            f"The copy to {far_name} stopped ({reason}). {sent} of {total} objects were sent this time; what "
            f"arrived is kept there. Nothing has landed there and {source_name} is unchanged. Send again "
            f"(resume {transfer_id}) to send only the rest.") from exc
    finally:
        far.close()
    result = TransferResult.model_validate(landed.json())
    result.objects_sent, result.machine, result.source, result.target = sent, machine.name, source_name, far_name
    record.state, record.error, record.updated_at = TransferState.done, None, utc_now()
    record.result = result.model_dump(mode="json")
    source_db.save(record)
    shutil.rmtree(_outgoing(source_db, transfer_id), ignore_errors=True)
    return result


# =============================================================================================
# The receiving side: what arrives, and the landing
# =============================================================================================


def _incoming_root(target_db) -> Path:
    return Path(target_db.path).parent / "transfers" / "incoming"


def _incoming(target_db, transfer_id: str) -> Path:
    """The copy's folder, confined: an id is 32 hex characters, never a path (`..`, `/`)."""
    if not isinstance(transfer_id, str) or not _ID.fullmatch(transfer_id):
        raise LookupError(f"No copy {transfer_id!r} is arriving here.")
    return _incoming_root(target_db) / transfer_id


def _opened(target_db, transfer_id: str) -> tuple[IncomingTransfer, SyncManifest, Path, Path]:
    where = _incoming(target_db, transfer_id)
    try:
        opened = IncomingTransfer.model_validate_json((where / "opened.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LookupError(f"No copy {transfer_id} is arriving here.") from None
    name = Path(opened.source_project).name
    package = where / "package" / (name if name not in ("", ".", "..") else "source.fichero")
    return opened, SyncManifest.from_json(json.dumps(opened.manifest)), where / "checkpoint.json", package


def _checkpoint(path: Path, manifest: SyncManifest) -> SyncCheckpoint:
    if path.exists():
        return SyncCheckpoint.from_json(path.read_text(encoding="utf-8"))
    return SyncCheckpoint.empty(manifest.library_id, manifest.generation)


def missing(target_db, transfer_id: str) -> list[str]:
    _, manifest, checkpoint_path, _ = _opened(target_db, transfer_id)
    empty = SyncManifest(library_id=manifest.library_id, generation=manifest.generation)
    pending = pending_objects(diff_manifests(manifest, empty), _checkpoint(checkpoint_path, manifest)).pending
    return [obj.sha256 for obj in pending]


def objects(target_db, transfer_id: str) -> int:
    return len(_opened(target_db, transfer_id)[1].objects)


def _check_manifest(manifest: SyncManifest) -> None:
    """Every object named as the package lays out (the rows, or an original under `files/`), each within the
    limits, the whole within the limits."""
    if len(manifest.objects) > MAX_OBJECTS:
        raise TooBig(f"{len(manifest.objects)} objects; this machine takes at most {MAX_OBJECTS} in one copy")
    for obj in manifest.objects:
        parts = obj.rel.split("/")
        if not _SHA.fullmatch(obj.sha256) or "\\" in obj.rel or (
                obj.rel != RECORDS and (parts[0] != "files" or len(parts) < 2 or any(p in ("", ".", "..") for p in parts))):
            raise LibrarySyncError(f"the object {obj.rel!r} is not one a copy's package holds")
        if obj.size > MAX_OBJECT_BYTES:
            raise TooBig(f"{obj.rel} is {obj.size} bytes; this machine takes at most {MAX_OBJECT_BYTES} in one object")
    if manifest.total_bytes() > MAX_TRANSFER_BYTES:
        raise TooBig(f"the copy is {manifest.total_bytes()} bytes; this machine takes at most {MAX_TRANSFER_BYTES}")


def _declared(where: Path) -> int:
    try:
        opened = IncomingTransfer.model_validate_json((where / "opened.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return sum(int(o.get("size", 0) or 0) for o in opened.manifest.get("objects", []))


def sweep_stale(target_db, *, now: float | None = None) -> list[str]:
    """Abandon every incoming copy nothing arrived for (and that did not land) in `STALE_AFTER_SECONDS`;
    returns their ids. Run whenever a copy opens here."""
    root, now = _incoming_root(target_db), time.time() if now is None else now
    removed = []
    for where in (root.iterdir() if root.is_dir() else ()):
        if not where.is_dir():
            continue
        latest = max((p.stat().st_mtime for p in where.rglob("*")), default=where.stat().st_mtime)
        if now - latest > STALE_AFTER_SECONDS:
            shutil.rmtree(where, ignore_errors=True)
            removed.append(where.name)
    return removed


def open_incoming(target_db, request: IncomingTransfer) -> list[str]:
    """Open (or reopen, to resume) a copy arriving here; returns the objects still missing. Refused before
    anything is written: another version, a malformed or oversized package, or too little room on this disk
    for it and every other copy still arriving."""
    if request.contract != contract():
        raise VersionMismatch("The two machines run different versions of Fichero: update both, then copy again.")
    manifest = SyncManifest.from_json(json.dumps(request.manifest))  # malformed: LibrarySyncError
    if manifest.library_id != request.transfer_id or RECORDS not in manifest.by_rel():
        raise LibrarySyncError("the manifest is not this transfer's package")
    _check_manifest(manifest)
    sweep_stale(target_db)
    where = _incoming(target_db, request.transfer_id)
    root = _incoming_root(target_db)
    others = sum(_declared(w) for w in (root.iterdir() if root.is_dir() else ()) if w.is_dir() and w != where)
    free = shutil.disk_usage(Path(target_db.path).parent).free
    if others + manifest.total_bytes() + FREE_FLOOR_BYTES > free:
        raise TooBig(f"this disk has {free} bytes free; the copy needs {manifest.total_bytes()} with "
                     f"{others} for other copies arriving, and {FREE_FLOOR_BYTES} kept free")
    opened_path = where / "opened.json"
    if opened_path.exists():
        before = IncomingTransfer.model_validate_json(opened_path.read_text(encoding="utf-8"))
        if before.manifest.get("objects") != request.manifest.get("objects"):
            raise LibrarySyncError("this transfer was opened here with another package")
    else:
        where.mkdir(parents=True, exist_ok=True)
        opened_path.write_text(request.model_dump_json(), encoding="utf-8")
    return missing(target_db, request.transfer_id)


def expected_size(target_db, transfer_id: str, sha256: str) -> int:
    """The size the manifest declared for this object: the most a PUT of it may carry."""
    _, manifest, _, _ = _opened(target_db, transfer_id)
    sizes = {o.size for o in manifest.objects if o.sha256 == sha256} if _SHA.fullmatch(sha256 or "") else set()
    if not sizes:
        raise LookupError(f"No object {sha256} belongs to the copy {transfer_id}.")
    return max(sizes)


def receive(target_db, transfer_id: str, sha256: str, data: bytes) -> None:
    """One object arrives: re-hashed, landed under its name in the incoming package, recorded as arrived."""
    with _lock(target_db, transfer_id):
        _receive(target_db, transfer_id, sha256, data)


def _receive(target_db, transfer_id: str, sha256: str, data: bytes) -> None:
    _, manifest, checkpoint_path, package = _opened(target_db, transfer_id)
    objects = [o for o in manifest.objects if o.sha256 == sha256]
    if not objects:
        raise LookupError(f"No object {sha256} belongs to the copy {transfer_id}.")
    if len(data) != objects[0].size:
        raise LibrarySyncError(f"{len(data)} bytes arrived for an object of {objects[0].size}")
    checkpoint = _checkpoint(checkpoint_path, manifest)
    for obj in objects:
        land_object(package, obj, data)  # a damaged object raises and is not recorded: it is sent again
        checkpoint = checkpoint.with_landed(obj)
    tmp = checkpoint_path.with_suffix(".tmp")
    tmp.write_text(checkpoint.to_json(), encoding="utf-8")
    tmp.replace(checkpoint_path)


def abandon(target_db, transfer_id: str) -> int:
    """Remove what arrived of a copy that will not land; returns how many objects were removed."""
    with _lock(target_db, transfer_id):
        where = _incoming(target_db, transfer_id)
        if not where.exists():
            raise LookupError(f"No copy {transfer_id} is arriving here.")
        _, manifest, checkpoint_path, _ = _opened(target_db, transfer_id)
        removed = len(_checkpoint(checkpoint_path, manifest).objects_done)
        shutil.rmtree(where)
        return removed


def _materialise(package: Path, opened: IncomingTransfer):
    """The arrived rows as a project of their own, its originals where its rows say they are."""
    from fichero_server.db import Database

    payload = json.loads((package / RECORDS).read_text(encoding="utf-8"))
    header, rows = payload["transfer"], payload["rows"]
    for name in ("fichero.duckdb", "fichero.duckdb.wal"):
        (package / name).unlink(missing_ok=True)  # a landing that failed before: its rows are made again
    for sub in ("lance", "storage", "files"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    db = Database(path=package / "fichero.duckdb")
    models = {model.__name__: model for model in db._all_schema_models()}
    root = header["package_root"].rstrip("/") + "/"
    with db.transaction():
        for name, dumps in rows.items():
            for dump in dumps:
                if name == "Document" and isinstance(dump.get("path"), str) and dump["path"].startswith(root):
                    old, new = dump["path"], str(package / dump["path"][len(root):])
                    dump["path"] = new
                    meta = dump.get("metadata") or {}
                    dump["metadata"] = {k: (new if v == old else v) for k, v in meta.items()}
                db.save(models[name].model_validate(dump))
    return db, header


def land(target_db, transfer_id: str, *, target_parent_id: str, parent_to_make, actor: str,
         audit_id: str) -> TransferResult:
    with _lock(target_db, transfer_id):
        return _land(target_db, transfer_id, target_parent_id=target_parent_id, parent_to_make=parent_to_make,
                     actor=actor, audit_id=audit_id)


def _land(target_db, transfer_id: str, *, target_parent_id: str, parent_to_make, actor: str,
          audit_id: str) -> TransferResult:
    """Land a copy whose every object has arrived: all or nothing, by the one copy code. Raises `TransferFailed`
    (rolled back there, the objects kept for another try) or ValueError (objects still missing)."""
    from fichero_server.models.transfer import TransferCut, TransferLeftBehind
    from fichero_server.transfer.copy import copy_into_target
    from fichero_server.transfer.plan import build_plan

    opened, _, _, package = _opened(target_db, transfer_id)
    left = missing(target_db, transfer_id)
    if left:
        raise ValueError(f"{len(left)} objects of this copy have not arrived yet; nothing lands until all have.")
    scratch, header = _materialise(package, opened)
    source = f"{opened.source_machine}:{opened.source_project}"
    try:
        plan = build_plan(scratch, target_db, items=header["items"], target_parent_id=target_parent_id,
                          transfer_id=transfer_id, audit_id=audit_id, actor=actor)
        plan.parent_to_make = parent_to_make
        plan.cuts[:0] = [TransferCut.model_validate(c) for c in header["cuts"]]
        plan.left_behind[:0] = [TransferLeftBehind.model_validate(lb) for lb in header["left_behind"]]
        linked: list[str] = []
        sources = plan.rows["Document"]
        for kind, row in plan.built:
            if kind != "Document":
                continue
            came = row.metadata["transferred_from"]
            came.update(machine=opened.source_machine, project_path=opened.source_project)
            original = sources[came["node"]]
            if came["node"] in plan.linked_files:
                # A path on the SOURCE machine: never this machine's path, or a peer could point a node at any
                # file here and have it served. Kept only as words until a person relinks it.
                row.metadata = {k: v for k, v in row.metadata.items() if v != original.path}
                row.metadata["linked_elsewhere"] = {"machine": opened.source_machine, "path": original.path}
                row.path = None
                linked.append(f"{original.name}: linked file; the original stays at {original.path} on "
                              f"{opened.source_machine} and may not open here")
        result = copy_into_target(scratch, target_db, plan, mode=TransferMode.copy, actor=actor)
    finally:
        scratch.close()
    record = target_db.get(TransferRecord, transfer_id)
    record.source_project = source
    result.source, result.machine, result.linked_elsewhere = Path(opened.source_project).stem, opened.source_machine, linked
    record.result = result.model_dump(mode="json")
    target_db.save(record)
    shutil.rmtree(_incoming(target_db, transfer_id), ignore_errors=True)
    return result


def new_transfer_id() -> str:
    return uuid.uuid4().hex
