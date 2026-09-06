"""Unit tests for the on-disk library-sync I/O layer (design §2.1/§2.3).

Temp-dir only — no engine, no DB, no network.
"""

import hashlib

import pytest

from fichero_server.workflows.library_sync import LibrarySyncError, SyncObject
from fichero_server.workflows.library_sync_io import (
    build_package_manifest,
    hash_file,
    iter_file_objects,
    land_object,
)


def _write(root, rel, content: bytes):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_iter_file_objects_lists_and_hashes_originals(tmp_path):
    _write(tmp_path, "files/00/a.jpg", b"alpha")
    _write(tmp_path, "files/01/b.pdf", b"bravo-bravo")
    objects = iter_file_objects(tmp_path)
    rels = {o.rel for o in objects}
    assert rels == {"files/00/a.jpg", "files/01/b.pdf"}
    a = next(o for o in objects if o.rel == "files/00/a.jpg")
    assert a.sha256 == hashlib.sha256(b"alpha").hexdigest()
    assert a.size == 5


def test_iter_file_objects_skips_derived_caches(tmp_path):
    _write(tmp_path, "files/a.jpg", b"x")
    _write(tmp_path, "files/vectors/index.lance", b"derived")
    _write(tmp_path, "files/thumbnails/a.png", b"derived")
    rels = {o.rel for o in iter_file_objects(tmp_path)}
    assert rels == {"files/a.jpg"}


def test_iter_file_objects_empty_when_no_files_dir(tmp_path):
    assert iter_file_objects(tmp_path) == []


def test_build_package_manifest_folds_in_db_object(tmp_path):
    _write(tmp_path, "files/a.jpg", b"content")
    db = SyncObject(rel="db/fichero.parquet", sha256="dbhash", size=42, kind="db")
    manifest = build_package_manifest(
        package_root=tmp_path, library_id="lib-1", generation=7, db_object=db
    )
    assert manifest.generation == 7
    rels = {o.rel for o in manifest.objects}
    assert rels == {"files/a.jpg", "db/fichero.parquet"}
    assert any(o.kind == "db" for o in manifest.objects)


def test_hash_file_matches_hashlib(tmp_path):
    path = _write(tmp_path, "files/big.bin", b"z" * 3_000_000)  # spans chunks
    sha, size = hash_file(path)
    assert sha == hashlib.sha256(b"z" * 3_000_000).hexdigest()
    assert size == 3_000_000


def test_land_object_writes_atomically_and_verifies(tmp_path):
    data = b"payload"
    obj = SyncObject(
        rel="files/x/y.jpg", sha256=hashlib.sha256(data).hexdigest(), size=len(data)
    )
    landed = land_object(tmp_path, obj, data)
    assert landed.read_bytes() == data
    assert not any(p.name.endswith(".synctmp") for p in tmp_path.rglob("*"))


def test_land_object_rejects_hash_mismatch(tmp_path):
    obj = SyncObject(rel="files/x.jpg", sha256="deadbeef", size=4)
    with pytest.raises(LibrarySyncError):
        land_object(tmp_path, obj, b"nope")
    assert not (tmp_path / "files/x.jpg").exists()


def test_land_object_rejects_path_escape(tmp_path):
    data = b"evil"
    obj = SyncObject(
        rel="../escape.jpg", sha256=hashlib.sha256(data).hexdigest(), size=len(data)
    )
    with pytest.raises(LibrarySyncError):
        land_object(tmp_path, obj, data)
