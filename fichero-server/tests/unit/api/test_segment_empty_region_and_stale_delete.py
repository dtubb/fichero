"""An emptied region is kept and named by the validator; a stale delete refuses the whole call.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edge.empty-region` (a region with no
lines is kept and listed as empty) and `segment-editor.edge.stale` (every action is refused when the row changed
since it was read).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.models import Segment
from tests.unit.api.test_segments_validate import _clean_page, _kinds, _person, _problems

pytestmark = pytest.mark.source_model


def _delete(db, ids, versions):
    return registry.invoke(db, "segment.delete", {"segment_ids": ids, "expected_versions": versions}, _person())


def test_deleting_every_line_keeps_the_region_and_the_validator_names_it_empty(db, client):
    doc, _, region, first, second = _clean_page(db, client)
    versions = {sid: db.get(Segment, sid).version for sid in (first, second)}

    _delete(db, [first, second], versions)

    kept = db.get(Segment, region)
    assert kept is not None and kept.deleted_at is None
    assert ("empty-region", (region,)) in _kinds(_problems(client, doc))


def test_a_stale_version_refuses_the_whole_delete_and_deletes_nothing(db, client):
    _, _, _, first, second = _clean_page(db, client)
    versions = {first: db.get(Segment, first).version, second: db.get(Segment, second).version - 1}

    with pytest.raises(HTTPException) as refused:
        _delete(db, [first, second], versions)

    assert refused.value.status_code in (409, 422)
    for sid in (first, second):
        assert db.get(Segment, sid).deleted_at is None
