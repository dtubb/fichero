"""An imported page keeps the file it was read from, and says how it was made (#5149).

The maintainer asked to track the imported PAGE / ALTO file as its own thing and be able to see it.
The pass is a reading OF that file, so the file is the evidence: kept byte for byte in the library
package like every other library file, named in the pass the Inspector reads (its Making section),
and served back as it arrived.
"""

from __future__ import annotations

import base64
import hashlib

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import SegmentPass
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _imported_pass(client, doc_id: str) -> dict:
    body = client.get(f"/api/segments/document/{doc_id}").json()   # what the app's store reads
    return next(p for p in body["passes"] if not p["provisional"])


def test_the_pass_names_its_file_and_the_file_comes_back_byte_for_byte(db, client):
    doc_id = _import(db, SYRIAC)
    made = _imported_pass(client, doc_id)
    data = SYRIAC.read_bytes()
    assert made["import_file"] == SYRIAC.name
    assert made["import_checksum"] == hashlib.sha256(data).hexdigest()
    assert made["import_format"] == "pagexml"
    assert made["has_original"] is True

    original = client.get(f"/api/segments/passes/{made['id']}/original")
    assert original.status_code == 200, original.text
    body = original.json()
    assert base64.b64decode(body["content_base64"]) == data              # byte for byte
    assert body["media_type"] == "application/xml"
    assert body["file_name"] == SYRIAC.name and body["import_format"] == "pagexml"
    assert body["import_checksum"] == hashlib.sha256(data).hexdigest()


def test_a_pass_not_made_from_a_file_has_no_original(db, client):
    row = SegmentPass(document_id="doc-x", name="drawn by hand", provenance_kind="human")
    db.save(row)
    assert client.get(f"/api/segments/passes/{row.id}/original").status_code == 404


def test_a_stored_path_outside_the_package_s_files_is_never_served(db, client):
    doc_id = _import(db, SYRIAC)
    made = _imported_pass(client, doc_id)
    row = db.get(SegmentPass, made["id"])
    row.import_original = "../../etc/hosts"
    db.save(row)
    assert client.get(f"/api/segments/passes/{made['id']}/original").status_code == 404
