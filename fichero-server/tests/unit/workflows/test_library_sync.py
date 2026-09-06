"""Unit tests for the resumable library-sync building blocks (keystone).

Covers the pure core of ``agent-work/design/hpc-remote-library-sync.md`` §2:
manifest build/serialize, add/change/delete diffing, and checkpoint-aware
resume — including the ugly cases (touched-but-unchanged file, cross-library
diff, duplicate content, resume after partial transfer).
"""

import pytest

from fichero_server.workflows.library_sync import (
    LibrarySyncError,
    SyncCheckpoint,
    SyncManifest,
    SyncObject,
    build_manifest_from_listing,
    diff_manifests,
    pending_objects,
)


def _obj(rel: str, sha: str, size: int = 100, kind: str = "file", mtime_ns: int = 1):
    return SyncObject(rel=rel, sha256=sha, size=size, kind=kind, mtime_ns=mtime_ns)


def _manifest(objects, *, library_id="lib-1", generation=1):
    return build_manifest_from_listing(
        library_id=library_id, generation=generation, objects=list(objects)
    )


# --- objects / manifests ----------------------------------------------------


def test_manifest_is_deterministic_and_sorted():
    a = _manifest([_obj("files/b.jpg", "hb"), _obj("files/a.jpg", "ha")])
    b = _manifest([_obj("files/a.jpg", "ha"), _obj("files/b.jpg", "hb")])
    assert [o.rel for o in a.objects] == ["files/a.jpg", "files/b.jpg"]
    assert a.to_json() == b.to_json()  # order-independent, stable serialization


def test_manifest_round_trips_through_json():
    m = _manifest(
        [_obj("db/fichero.parquet", "hdb", size=999, kind="db"), _obj("files/a.jpg", "ha")]
    )
    assert SyncManifest.from_json(m.to_json()) == m


def test_manifest_rejects_duplicate_rel():
    with pytest.raises(LibrarySyncError):
        _manifest([_obj("files/a.jpg", "h1"), _obj("files/a.jpg", "h2")])


def test_sync_object_validates_fields():
    with pytest.raises(LibrarySyncError):
        SyncObject(rel="", sha256="h", size=1)
    with pytest.raises(LibrarySyncError):
        SyncObject(rel="files/a", sha256="", size=1)
    with pytest.raises(LibrarySyncError):
        SyncObject(rel="files/a", sha256="h", size=-1)
    with pytest.raises(LibrarySyncError):
        SyncObject(rel="files/a", sha256="h", size=1, kind="bogus")


# --- diff -------------------------------------------------------------------


def test_diff_detects_add_change_delete():
    source = _manifest(
        [_obj("files/keep.jpg", "same"), _obj("files/edit.jpg", "new"), _obj("files/new.jpg", "n")]
    )
    dest = _manifest(
        [_obj("files/keep.jpg", "same"), _obj("files/edit.jpg", "old"), _obj("files/gone.jpg", "g")]
    )
    diff = diff_manifests(source, dest)
    assert [o.rel for o in diff.add] == ["files/new.jpg"]
    assert [o.rel for o in diff.change] == ["files/edit.jpg"]
    assert [o.rel for o in diff.delete] == ["files/gone.jpg"]
    assert {o.rel for o in diff.to_transfer()} == {"files/new.jpg", "files/edit.jpg"}


def test_diff_ignores_mtime_when_content_unchanged():
    # Same content + size, different mtime => NOT a change (must not re-send).
    source = _manifest([_obj("files/a.jpg", "h", size=10, mtime_ns=2000)])
    dest = _manifest([_obj("files/a.jpg", "h", size=10, mtime_ns=1000)])
    assert diff_manifests(source, dest).is_empty()


def test_diff_across_libraries_raises():
    source = _manifest([_obj("files/a.jpg", "h")], library_id="lib-A")
    dest = _manifest([_obj("files/a.jpg", "h")], library_id="lib-B")
    with pytest.raises(LibrarySyncError):
        diff_manifests(source, dest)


def test_clone_from_empty_transfers_everything():
    source = _manifest([_obj("files/a.jpg", "ha"), _obj("db/fichero.parquet", "hdb", kind="db")])
    empty = _manifest([], generation=0)
    diff = diff_manifests(source, empty)
    assert len(diff.to_transfer()) == 2
    assert not diff.delete


# --- checkpoint / resume ----------------------------------------------------


def test_pending_objects_first_run_is_everything():
    source = _manifest([_obj("files/a.jpg", "ha", size=10), _obj("files/b.jpg", "hb", size=20)])
    diff = diff_manifests(source, _manifest([], generation=0))
    plan = pending_objects(diff, SyncCheckpoint.empty("lib-1", 1))
    assert len(plan.pending) == 2
    assert plan.pending_bytes() == 30
    assert not plan.is_complete()


def test_pending_objects_resumes_after_partial_transfer():
    source = _manifest([_obj("files/a.jpg", "ha"), _obj("files/b.jpg", "hb")])
    diff = diff_manifests(source, _manifest([], generation=0))
    # 'ha' already landed before the interruption.
    checkpoint = SyncCheckpoint.empty("lib-1", 1).with_landed(_obj("files/a.jpg", "ha"))
    plan = pending_objects(diff, checkpoint)
    assert [o.rel for o in plan.pending] == ["files/b.jpg"]
    assert [o.rel for o in plan.done] == ["files/a.jpg"]


def test_pending_objects_complete_when_all_landed():
    source = _manifest([_obj("files/a.jpg", "ha")])
    diff = diff_manifests(source, _manifest([], generation=0))
    checkpoint = SyncCheckpoint.empty("lib-1", 1).with_landed(_obj("files/a.jpg", "ha"))
    plan = pending_objects(diff, checkpoint)
    assert plan.is_complete()
    assert not plan.pending


def test_duplicate_content_transferred_once():
    # Two different paths, identical content hash => transfer the bytes once.
    source = _manifest([_obj("files/a.jpg", "dup"), _obj("files/copy.jpg", "dup")])
    diff = diff_manifests(source, _manifest([], generation=0))
    plan = pending_objects(diff, SyncCheckpoint.empty("lib-1", 1))
    assert len(plan.pending) == 1
    assert len(plan.done) == 1  # the duplicate is not re-queued


def test_checkpoint_round_trips_and_is_idempotent():
    cp = SyncCheckpoint.empty("lib-1", 3).with_landed(_obj("files/a.jpg", "ha", size=5))
    # landing the same hash twice does not double-count bytes
    cp2 = cp.with_landed(_obj("files/a.jpg", "ha", size=5))
    assert cp2.bytes_done == 5
    assert SyncCheckpoint.from_json(cp.to_json()) == cp
