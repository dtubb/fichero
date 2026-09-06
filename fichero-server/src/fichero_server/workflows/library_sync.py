"""Resumable library-sync building blocks (the keystone).

Pure, testable core for cloning/syncing a ``.fichero`` library to another
computer over the *existing* transport (loopback + ``tailscale serve`` +
SPKI-TLS + device token) — see
``agent-work/design/hpc-remote-library-sync.md``.

This module intentionally starts as pure building blocks, exactly the way
``workflows/remote_jobs.py`` did for the Slurm path: no I/O, no routes, no
network. It computes what to transfer and what remains after an interruption;
the routes, the sync daemon, and the CLI are later slices gated behind this
core.

Model (design §2):

- A :class:`SyncManifest` is a deterministic listing of every syncable object
  in a library at one ``generation`` — the DuckDB image (as a Parquet bundle)
  and the original files under ``files/``. Renditions and vectors are derivable
  caches and are *not* listed by default (they regenerate on the target).
- Each :class:`SyncObject` is identified by ``sha256`` + ``size``. ``mtime_ns``
  is only a fast-skip hint, never trusted for equality.
- :func:`diff_manifests` yields rsync's three sets — **add / change / delete** —
  computed by us so the transfer rides our authenticated HTTP transport rather
  than shelling out to ``rsync``.
- A :class:`SyncCheckpoint` records which object hashes have already landed on
  the destination. :func:`pending_objects` subtracts it so an interrupted
  transfer resumes by moving only what is still missing — the same done-marker
  discipline ``remote_jobs.py`` uses for sparse Slurm resubmission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json


class LibrarySyncError(ValueError):
    """A manifest/checkpoint is malformed or two manifests are incomparable."""


# =============================================================================
# Objects and manifests (design §2.1)
# =============================================================================


@dataclass(frozen=True)
class SyncObject:
    """One syncable object in a library.

    ``rel`` is the library-relative path (e.g. ``files/00/ab….jpg`` or the
    synthetic ``db/fichero.parquet`` for the exported DB bundle). ``sha256`` +
    ``size`` are the object's identity; ``mtime_ns`` is a fast-skip hint only.
    ``kind`` is ``"file"`` for originals or ``"db"`` for the relational image,
    so the far side lands each through the right path.
    """

    rel: str
    sha256: str
    size: int
    kind: str = "file"
    mtime_ns: int = 0

    def __post_init__(self) -> None:
        if not self.rel.strip():
            raise LibrarySyncError("SyncObject.rel must be non-empty")
        if not self.sha256.strip():
            raise LibrarySyncError(f"SyncObject {self.rel!r} has empty sha256")
        if self.size < 0:
            raise LibrarySyncError(f"SyncObject {self.rel!r} has negative size")
        if self.kind not in {"file", "db"}:
            raise LibrarySyncError(
                f"SyncObject {self.rel!r} has unknown kind {self.kind!r}"
            )

    def identity(self) -> tuple[str, int]:
        """The (sha256, size) pair that defines object equality across peers."""
        return (self.sha256, self.size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rel": self.rel,
            "sha256": self.sha256,
            "size": self.size,
            "kind": self.kind,
            "mtime_ns": self.mtime_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncObject":
        return cls(
            rel=str(data["rel"]),
            sha256=str(data["sha256"]),
            size=int(data["size"]),
            kind=str(data.get("kind", "file") or "file"),
            mtime_ns=int(data.get("mtime_ns", 0) or 0),
        )


@dataclass(frozen=True)
class SyncManifest:
    """A point-in-time listing of a library's syncable objects (design §2.1).

    ``generation`` is a monotonic counter (a DuckDB row-version or snapshot
    sequence) so a peer can cheaply ask "is there anything newer than N?".
    Objects are keyed by ``rel`` within a manifest; two objects with the same
    ``rel`` is a malformed manifest and raises.
    """

    library_id: str
    generation: int
    objects: tuple[SyncObject, ...] = ()
    produced_at: str = ""

    def __post_init__(self) -> None:
        if not self.library_id.strip():
            raise LibrarySyncError("SyncManifest.library_id must be non-empty")
        if self.generation < 0:
            raise LibrarySyncError(
                f"SyncManifest.generation must be >= 0: {self.generation}"
            )
        seen: set[str] = set()
        for obj in self.objects:
            if obj.rel in seen:
                raise LibrarySyncError(f"duplicate object rel in manifest: {obj.rel!r}")
            seen.add(obj.rel)

    def by_rel(self) -> dict[str, SyncObject]:
        """Index this manifest's objects by their library-relative path."""
        return {obj.rel: obj for obj in self.objects}

    def total_bytes(self) -> int:
        return sum(obj.size for obj in self.objects)

    def to_json(self) -> str:
        return json.dumps(
            {
                "library_id": self.library_id,
                "generation": self.generation,
                "produced_at": self.produced_at,
                "objects": [obj.to_dict() for obj in self.objects],
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text: str) -> "SyncManifest":
        data = json.loads(text)
        return cls(
            library_id=str(data["library_id"]),
            generation=int(data["generation"]),
            objects=tuple(
                SyncObject.from_dict(o) for o in data.get("objects", [])
            ),
            produced_at=str(data.get("produced_at", "")),
        )


def build_manifest_from_listing(
    *,
    library_id: str,
    generation: int,
    objects: list[SyncObject],
    produced_at: str = "",
) -> SyncManifest:
    """Assemble a manifest from an already-computed object listing (pure).

    The caller (a later I/O slice) walks ``files/`` and the exported DB bundle,
    hashing each object, and hands the results here. Objects are sorted by
    ``rel`` so the manifest — and thus its ``to_json`` — is deterministic for a
    given library state, which keeps diffs and content hashes stable.
    """
    ordered = sorted(objects, key=lambda o: o.rel)
    return SyncManifest(
        library_id=library_id,
        generation=generation,
        objects=tuple(ordered),
        produced_at=produced_at,
    )


# =============================================================================
# Diff (design §2.1 — add / change / delete)
# =============================================================================


@dataclass(frozen=True)
class ManifestDiff:
    """The rsync-style delta between a source and a destination manifest.

    ``add`` — objects present at the source, absent at the destination.
    ``change`` — objects present at both ``rel`` but with a different identity
    (content changed). ``delete`` — objects present only at the destination
    (removed at the source). ``add`` + ``change`` is what must be transferred to
    bring the destination up to the source; ``delete`` is what to prune after.
    """

    add: tuple[SyncObject, ...] = ()
    change: tuple[SyncObject, ...] = ()
    delete: tuple[SyncObject, ...] = ()

    def to_transfer(self) -> tuple[SyncObject, ...]:
        """Objects the destination must fetch/receive (adds + changes)."""
        return self.add + self.change

    def transfer_bytes(self) -> int:
        return sum(obj.size for obj in self.to_transfer())

    def is_empty(self) -> bool:
        return not (self.add or self.change or self.delete)


def diff_manifests(source: SyncManifest, dest: SyncManifest) -> ManifestDiff:
    """Compute what must move to make ``dest`` match ``source`` (pure, design §2.1).

    Compares by library-relative path, then by ``(sha256, size)`` identity —
    ``mtime_ns`` is deliberately ignored (a touched-but-unchanged file must not
    be re-sent). Raises if the two manifests are for different libraries, which
    would be a caller bug (never silently sync across libraries).
    """
    if source.library_id != dest.library_id:
        raise LibrarySyncError(
            "cannot diff manifests from different libraries: "
            f"{source.library_id!r} vs {dest.library_id!r}"
        )
    src = source.by_rel()
    dst = dest.by_rel()
    add: list[SyncObject] = []
    change: list[SyncObject] = []
    for rel, obj in src.items():
        existing = dst.get(rel)
        if existing is None:
            add.append(obj)
        elif existing.identity() != obj.identity():
            change.append(obj)
    delete = [obj for rel, obj in dst.items() if rel not in src]
    return ManifestDiff(
        add=tuple(sorted(add, key=lambda o: o.rel)),
        change=tuple(sorted(change, key=lambda o: o.rel)),
        delete=tuple(sorted(delete, key=lambda o: o.rel)),
    )


# =============================================================================
# Checkpoint + resume (design §2.3 — structural resumability)
# =============================================================================


@dataclass(frozen=True)
class SyncCheckpoint:
    """The destination's record of which object hashes have already landed.

    Persisted (a tiny JSON/DuckDB row) after each object lands and re-hashes
    clean, so an interrupted transfer resumes by moving only what is still
    missing. ``generation`` is the source generation this checkpoint is
    progressing toward; a checkpoint for a stale generation is discarded by the
    caller and rebuilt.
    """

    library_id: str
    generation: int
    objects_done: frozenset[str] = field(default_factory=frozenset)
    bytes_done: int = 0

    def with_landed(self, obj: SyncObject) -> "SyncCheckpoint":
        """Return a new checkpoint recording ``obj`` as landed (immutably)."""
        if obj.sha256 in self.objects_done:
            return self
        return SyncCheckpoint(
            library_id=self.library_id,
            generation=self.generation,
            objects_done=self.objects_done | {obj.sha256},
            bytes_done=self.bytes_done + obj.size,
        )

    def has(self, obj: SyncObject) -> bool:
        return obj.sha256 in self.objects_done

    def to_json(self) -> str:
        return json.dumps(
            {
                "library_id": self.library_id,
                "generation": self.generation,
                "objects_done": sorted(self.objects_done),
                "bytes_done": self.bytes_done,
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text: str) -> "SyncCheckpoint":
        data = json.loads(text)
        return cls(
            library_id=str(data["library_id"]),
            generation=int(data["generation"]),
            objects_done=frozenset(str(h) for h in data.get("objects_done", [])),
            bytes_done=int(data.get("bytes_done", 0) or 0),
        )

    @classmethod
    def empty(cls, library_id: str, generation: int) -> "SyncCheckpoint":
        return cls(library_id=library_id, generation=generation)


@dataclass(frozen=True)
class SyncPlan:
    """What remains to be transferred, given a diff and a checkpoint.

    ``pending`` is the resume set — the objects to move now. ``done`` is what the
    checkpoint already covers (skipped this run). ``pending`` + ``done`` == the
    diff's transfer set, so progress is exact: a fully-covered checkpoint yields
    an empty ``pending`` and the transfer is complete.
    """

    pending: tuple[SyncObject, ...] = ()
    done: tuple[SyncObject, ...] = ()

    def pending_bytes(self) -> int:
        return sum(obj.size for obj in self.pending)

    def is_complete(self) -> bool:
        return not self.pending


def pending_objects(diff: ManifestDiff, checkpoint: SyncCheckpoint) -> SyncPlan:
    """Subtract a checkpoint from a diff to get the resume set (pure, design §2.3).

    An object whose hash is already in the checkpoint is a no-op this run
    (skipped, counted as ``done``); everything else is ``pending``. Called on
    every (re)start: the first run has an empty checkpoint (all pending); a run
    resumed after interruption carries the landed hashes and moves only the
    remainder. De-duplicates by hash so two objects with identical content are
    transferred once.
    """
    pending: list[SyncObject] = []
    done: list[SyncObject] = []
    seen_pending: set[str] = set()
    for obj in diff.to_transfer():
        if checkpoint.has(obj):
            done.append(obj)
        elif obj.sha256 not in seen_pending:
            seen_pending.add(obj.sha256)
            pending.append(obj)
        else:
            # identical content already queued this run — land once, skip dupes
            done.append(obj)
    return SyncPlan(pending=tuple(pending), done=tuple(done))
