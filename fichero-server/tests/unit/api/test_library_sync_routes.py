"""Loopback round-trip tests for the pull-only library-sync routes.

In-process TestClient (no engine spawn, no network). Exercises the real routes
through the real read dependency (overridden to the test package by the
``client`` fixture), so the manifest → object round-trip and the path-safety
guards are covered end to end. Design: hpc-remote-library-sync §2.2.
"""

import hashlib


def _write(pkg, rel, content: bytes):
    path = pkg / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_manifest_lists_files_with_hashes(client, test_package):
    _write(test_package, "files/00/a.jpg", b"alpha")
    _write(test_package, "files/01/b.pdf", b"bravo-bravo")

    resp = client.get("/api/library/sync/manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["library_id"]  # move-stable UUID minted by the identity migration
    objects = {o["rel"]: o for o in body["objects"]}
    assert {"files/00/a.jpg", "files/01/b.pdf"} <= set(objects)  # + a db object
    assert objects["files/00/a.jpg"]["sha256"] == hashlib.sha256(b"alpha").hexdigest()
    assert objects["files/00/a.jpg"]["size"] == 5


def test_object_round_trips_bytes(client, test_package):
    content = b"page-image-bytes"
    _write(test_package, "files/x/y.jpg", content)

    resp = client.get("/api/library/sync/object", params={"rel": "files/x/y.jpg"})
    assert resp.status_code == 200
    assert resp.content == content


def test_object_rejects_non_files_non_db_rel(client, test_package):
    # Only files/ originals and the DB image are syncable; a vector dir is not.
    resp = client.get("/api/library/sync/object", params={"rel": "lance/data.lance"})
    assert resp.status_code == 400


def test_manifest_includes_openable_db_image(client, test_package):
    _write(test_package, "files/a.jpg", b"x")
    body = client.get("/api/library/sync/manifest").json()
    objects = {o["rel"]: o for o in body["objects"]}
    assert "fichero.duckdb" in objects
    db = objects["fichero.duckdb"]
    assert db["kind"] == "db"
    assert db["size"] > 0 and db["sha256"]


def test_end_to_end_clone_produces_openable_library(client, test_package, tmp_path):
    """The whole point: pull a library over loopback and OPEN the clone.

    Drives the same manifest → diff → fetch → land steps the CLI does, against
    the in-process routes, then opens the cloned fichero.duckdb to prove it is a
    real, populated database — an openable clone, not just a pile of bytes.
    """
    from fichero_server.core.duckdb_session import connect_utc
    from fichero_server.workflows.library_sync import (
        SyncCheckpoint,
        SyncManifest,
        SyncObject,
        diff_manifests,
        pending_objects,
    )
    from fichero_server.workflows.library_sync_io import (
        build_package_manifest,
        land_object,
    )

    _write(test_package, "files/doc/p1.jpg", b"page-one")

    body = client.get("/api/library/sync/manifest").json()
    remote = SyncManifest(
        library_id=body["library_id"],
        generation=body["generation"],
        objects=tuple(SyncObject.from_dict(o) for o in body["objects"]),
    )

    dest = tmp_path / "clone.fichero"
    (dest / "files").mkdir(parents=True)
    local = build_package_manifest(
        package_root=dest, library_id=remote.library_id, generation=0
    )
    plan = pending_objects(
        diff_manifests(remote, local),
        SyncCheckpoint.empty(remote.library_id, remote.generation),
    )
    for obj in plan.pending:
        data = client.get("/api/library/sync/object", params={"rel": obj.rel}).content
        land_object(dest, obj, data)

    # The clone has the original file and an openable DB.
    assert (dest / "files/doc/p1.jpg").read_bytes() == b"page-one"
    assert (dest / "fichero.duckdb").exists()
    conn = connect_utc(str(dest / "fichero.duckdb"), read_only=True)
    try:
        tables = [t[0].lower() for t in conn.execute("SHOW TABLES").fetchall()]
    finally:
        conn.close()
    assert any("document" in t for t in tables)  # real schema → genuinely openable


def test_db_image_round_trips_and_matches_manifest_hash(client, test_package):
    body = client.get("/api/library/sync/manifest").json()
    db = next(o for o in body["objects"] if o["kind"] == "db")
    resp = client.get("/api/library/sync/object", params={"rel": "fichero.duckdb"})
    assert resp.status_code == 200
    # The served bytes must hash to exactly what the manifest advertised, or a
    # content-addressed clone would reject them on landing.
    assert hashlib.sha256(resp.content).hexdigest() == db["sha256"]
    assert len(resp.content) == db["size"]


def test_object_rejects_path_escape(client, test_package):
    resp = client.get(
        "/api/library/sync/object", params={"rel": "files/../../etc/passwd"}
    )
    assert resp.status_code == 400


def test_object_404_for_missing_file(client, test_package):
    resp = client.get(
        "/api/library/sync/object", params={"rel": "files/nope.jpg"}
    )
    assert resp.status_code == 404
