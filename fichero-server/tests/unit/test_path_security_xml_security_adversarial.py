from __future__ import annotations

from io import BytesIO
import os

import pytest

from fichero_server.security.path_security import (
    path_within_any_root,
    resolve_snapshot_record_path,
    resolve_under_allowed_roots,
    validate_stored_document_path,
)
from fichero_server.security.xml_security import iterparse_xml, parse_xml, reject_xml_entities


def test_resolve_under_allowed_roots_rejects_parent_traversal_escape(tmp_path):
    library_root = tmp_path / "library.fichero"
    library_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    escaped = library_root / ".." / outside.name

    assert resolve_under_allowed_roots(escaped, [library_root]) is None
    assert path_within_any_root(escaped, [library_root]) is False


def test_resolve_under_allowed_roots_rejects_symlink_escape(tmp_path):
    library_root = tmp_path / "library.fichero"
    files_root = library_root / "files"
    files_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.txt"
    target.write_text("secret", encoding="utf-8")
    link = files_root / "linked-secret.txt"
    os.symlink(target, link)

    assert resolve_under_allowed_roots(link, [library_root]) is None
    assert path_within_any_root(link, [library_root]) is False


def test_validate_stored_document_path_rejects_absolute_injection(tmp_path):
    library_root = tmp_path / "library.fichero"
    library_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="inside the library package"):
        validate_stored_document_path(str(outside), library_root)


def test_validate_stored_document_path_accepts_real_path_inside_allowed_root(tmp_path):
    library_root = tmp_path / "library.fichero"
    files_root = library_root / "files"
    files_root.mkdir(parents=True)
    stored = files_root / "page.jpg"
    stored.write_bytes(b"image")

    validate_stored_document_path(str(stored), library_root)

    assert resolve_under_allowed_roots(stored, [library_root]) == stored.resolve()


def test_resolve_snapshot_record_path_rejects_escape(tmp_path):
    snapshots_dir = tmp_path / "snapshots"
    snapshots_dir.mkdir()

    with pytest.raises(ValueError, match="relative to snapshots dir"):
        resolve_snapshot_record_path(snapshots_dir, "../outside.json")


def test_reject_xml_entities_rejects_xxe_external_entity():
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE data [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<data>&xxe;</data>
"""

    with pytest.raises(ValueError, match="entity declarations"):
        reject_xml_entities(payload)


def test_parse_xml_rejects_doctype_declaration():
    payload = b'<?xml version="1.0"?><!DOCTYPE data><data>nope</data>'

    with pytest.raises(ValueError, match="entity declarations"):
        parse_xml(BytesIO(payload))


def test_iterparse_xml_rejects_entity_expansion_bomb():
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<lolz>&lol2;</lolz>
"""

    with pytest.raises(ValueError, match="entity declarations"):
        list(iterparse_xml(BytesIO(payload), events=("start",)))


def test_parse_xml_accepts_benign_well_formed_xml():
    tree = parse_xml(BytesIO(b"<root><child id='1'>ok</child></root>"))

    root = tree.getroot()
    assert root.tag == "root"
    assert root.find("child").text == "ok"
