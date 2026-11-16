"""#6451 / #6455: a segment list row says why its `text` is the shown reading, its level and who read it, so the label needs no second request.

`counting_basis` (why it counts, or "none"), `counting_level` and `read_by` come from the same counting answer the page's text uses. Where NO reading counts,
the row names the newest person's reading and says "none"; its `text` is not claimed. On the recorded Syriac page.
"""
from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_editorial_facts import _first_line
from tests.unit.api.test_page_text_follows_the_file import SYRIAC, _import


def _row(client, doc_id: str, segment_id: str) -> dict:
    return next(s for s in client.get(f"/api/segments/document/{doc_id}").json()["segments"] if s["id"] == segment_id)


def test_a_row_carries_the_basis_level_and_maker_of_its_shown_reading(db, client):
    doc_id = _import(db, SYRIAC)
    line, reading = _first_line(client, doc_id)
    row = _row(client, doc_id, line["id"])
    assert row["text"] == reading["content"]
    assert row["counting_basis"] and row["counting_basis"] != "none"
    assert row["counting_level"] == reading["level"]
    assert row["read_by"] == (reading["producer_model"] or reading["created_by"])


def test_a_row_where_two_people_disagree_says_none_and_names_the_newest_reading(db, client):
    from fichero_server.actions.registry import registry
    from tests.unit.api.test_document_derived_text import _artifact, _convert, _make_doc, _person
    from fichero_server.api.routes.document.segment_conversion import converted_pass_id, live_rows_in_order

    doc = _make_doc(db)
    artifact = _artifact(db, doc)
    _convert(client, artifact.id)
    rows = live_rows_in_order(db, converted_pass_id(artifact.id))
    for content in ("en el nõbre", "en el nomine"):
        registry.invoke(db, "representation.create", {
            "document_id": doc.id, "segment_id": rows[1].id, "kind": "transcription", "content": content,
        }, _person())
    row = _row(client, doc.id, rows[1].id)
    assert row["counting_basis"] == "none"
    assert row["read_by"] == "historian"
