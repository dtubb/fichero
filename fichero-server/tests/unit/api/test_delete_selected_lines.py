"""Deleting several selected lines is ONE audited step and ONE undo (`source.editor.delete-selected-lines`).

WHY: with lines selected there was no visible way to delete them; every surface now sends the one `segment.delete`
batch. If the batch were N calls, ⌘Z would bring the lines back one at a time; if it did not check versions, a line
changed since it was read would be deleted over the change. Through the real host on an imported page.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.models import ActionAudit, Segment
from tests.unit.api.test_page_text_follows_the_file import BOOT
from tests.unit.api.test_reader_directions import ARABIC, _import, _line_texts
from tests.unit.api.test_reader_line_map import _view


def _three(client, doc_id):
    lines = _view(client, doc_id)[0]["pages"][0]["lines"][:3]
    return lines, {line["segment_id"]: line["version"] for line in lines}


def test_a_multi_selection_deletes_in_one_audit_row_and_one_undo_brings_every_line_back(db, client):
    doc_id = _import(db, ARABIC)
    lines, versions = _three(client, doc_id)
    gone = [t for t in _line_texts(ARABIC) if t][:3]
    before = document_text(db, doc_id).text
    audits_before = len(db.query(ActionAudit))
    result = registry.invoke(db, "segment.delete", {"segment_ids": list(versions), "expected_versions": versions}, BOOT)
    assert len(db.query(ActionAudit)) == audits_before + 1, "one audit row for the whole selection"
    assert all(db.get(Segment, sid).deleted_at is not None for sid in versions)
    text = document_text(db, doc_id).text
    assert not any(t in text for t in gone)

    undo = client.post(f"/api/actions/audit/{result.audit_id}/undo")
    assert undo.status_code == 200, undo.text
    assert all(db.get(Segment, sid).deleted_at is None for sid in versions), "one undo restores every line"
    assert document_text(db, doc_id).text == before


def test_a_line_changed_since_it_was_read_refuses_the_whole_delete(db, client):
    doc_id = _import(db, ARABIC)
    _lines, versions = _three(client, doc_id)
    stale = {**versions, next(iter(versions)): 99}
    with pytest.raises(Exception, match="(?i)stale|version"):   # a typed stale refusal; nothing may have been deleted
        registry.invoke(db, "segment.delete", {"segment_ids": list(stale), "expected_versions": stale}, BOOT)
    assert all(db.get(Segment, sid).deleted_at is None for sid in versions)
