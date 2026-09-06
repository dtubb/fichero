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
    assert set(objects) == {"files/00/a.jpg", "files/01/b.pdf"}
    assert objects["files/00/a.jpg"]["sha256"] == hashlib.sha256(b"alpha").hexdigest()
    assert objects["files/00/a.jpg"]["size"] == 5


def test_object_round_trips_bytes(client, test_package):
    content = b"page-image-bytes"
    _write(test_package, "files/x/y.jpg", content)

    resp = client.get("/api/library/sync/object", params={"rel": "files/x/y.jpg"})
    assert resp.status_code == 200
    assert resp.content == content


def test_object_rejects_non_files_rel(client, test_package):
    # The DuckDB itself is not a syncable "object" here — only files/ originals.
    resp = client.get("/api/library/sync/object", params={"rel": "fichero.duckdb"})
    assert resp.status_code == 400


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
