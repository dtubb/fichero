"""`source.editor.content-listed-newest-first-in-the-pane` (#6460): a line's readings come back newest first by `created_at`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import ContentRepresentation
from tests.unit.api.test_reading_levels import PAGE, PERSON, _write, line  # noqa: F401  (the corpus line fixture)

pytestmark = pytest.mark.source_model


def test_a_lines_readings_are_listed_newest_first(db, client, line):  # noqa: F811
    ids = [_write(db, line, text) for text in ("first", "second", "third")]
    base = datetime.now(timezone.utc) + timedelta(days=1)  # after the import's own reading
    for age, rid in enumerate(ids):  # the middle one is the newest by the clock, whatever the write order
        row = db.get(ContentRepresentation, rid)
        row.created_at = base + timedelta(hours=(10 if age == 1 else age))
        db.save(row)
    items = client.get(f"/api/segments/{line.id}/readings").json()["items"]
    stamps = [item["created_at"] for item in items]
    assert stamps == sorted(stamps, reverse=True)
    assert [i["content"] for i in items][0] == "second"
