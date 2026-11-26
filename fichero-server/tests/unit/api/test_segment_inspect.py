"""`GET /api/segments/inspect`: the rows the Inspector's form draws for a selection, per level
(`source.editor.inspector-form-comes-from-the-engine`).

The app draws what comes back and sends the existing action for each control, so the rows, their
state (set on the segment, inherited, mixed across the selection) and their choices are decided
here, on real imported pages: a Syriac page (regions and lines) and a Latin ALTO page (words).
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from tests.unit.api.test_page_text_follows_the_file import CLM, SYRIAC, _import

DIRECTIONS = ["ltr", "rtl", "ttb", "btt", "alternating", "follows-baseline"]


def _page(client, doc_id: str) -> list[dict]:
    body = client.get(f"/api/segments/document/{doc_id}").json()
    real = next(p for p in body["passes"] if not p["provisional"])
    return [s for s in body["segments"] if s["pass_id"] == real["id"]]


def _of_kind(client, doc_id: str, kind: str) -> list[dict]:
    return sorted((s for s in _page(client, doc_id) if s["kind"] == kind), key=lambda s: s["anchor"]["rect"])


def _inspect(client, ids: list[str]) -> dict:
    sent = client.get("/api/segments/inspect", params={"segment_ids": ids})
    assert sent.status_code == 200, sent.text
    return sent.json()


def _rows(answer: dict) -> dict[str, dict]:
    return {row["key"]: row for row in answer["rows"]}


def _update(client, items: list[dict]):
    return client.post("/api/actions/invoke", json={"name": "segment.update_many", "params": {"updates": items}})


def test_a_region_has_the_region_rows_and_a_line_does_not_get_line_progression(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    line = _of_kind(client, doc_id, "line")[0]

    region_answer = _inspect(client, [region["id"]])
    assert region_answer["level"] == "region" and region_answer["count"] == 1
    assert [r["key"] for r in region_answer["rows"]] == ["type", "furniture", "language", "script", "direction", "line_progression"]

    line_answer = _inspect(client, [line["id"]])
    assert line_answer["level"] == "line"
    assert [r["key"] for r in line_answer["rows"]] == ["furniture", "language", "script", "direction"]


def test_a_word_has_the_three_facts_and_nothing_else(db, client):
    doc_id = _import(db, CLM)
    word = _of_kind(client, doc_id, "word")[0]
    answer = _inspect(client, [word["id"]])
    assert answer["level"] == "word"
    assert [r["key"] for r in answer["rows"]] == ["language", "script", "direction"]


def test_a_selection_of_two_levels_keeps_the_rows_both_have(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    line = _of_kind(client, doc_id, "line")[0]
    answer = _inspect(client, [region["id"], line["id"]])
    assert answer["level"] == "mixed" and answer["count"] == 2
    assert [r["key"] for r in answer["rows"]] == ["furniture", "language", "script", "direction"]


def test_a_fact_set_on_the_segment_is_set_and_one_it_does_not_state_is_inherited(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _of_kind(client, doc_id, "line")[:2]
    assert _update(client, [{"segment_id": first["id"], "expected_version": first["version"], "direction": "ttb"}]).status_code == 200

    stated = _rows(_inspect(client, [first["id"]]))["direction"]
    assert (stated["state"], stated["value"]) == ("set", "ttb")
    assert stated["inherited_from"] is None

    unstated = _rows(_inspect(client, [second["id"]]))["direction"]
    assert unstated["state"] == "inherited"
    assert unstated["value"] in DIRECTIONS
    assert unstated["inherited_from"], "an inherited fact says which level it came from"


def test_two_lines_that_differ_are_mixed_and_name_both_values(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _of_kind(client, doc_id, "line")[:2]
    assert _update(client, [
        {"segment_id": first["id"], "expected_version": first["version"], "direction": "ttb"},
        {"segment_id": second["id"], "expected_version": second["version"], "direction": "btt"},
    ]).status_code == 200
    row = _rows(_inspect(client, [first["id"], second["id"]]))["direction"]
    assert row["state"] == "mixed" and row["value"] is None
    assert sorted(row["values"]) == ["btt", "ttb"]


def test_two_lines_that_agree_are_one_set_value(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _of_kind(client, doc_id, "line")[:2]
    assert _update(client, [
        {"segment_id": first["id"], "expected_version": first["version"], "language": "syc"},
        {"segment_id": second["id"], "expected_version": second["version"], "language": "syc"},
    ]).status_code == 200
    row = _rows(_inspect(client, [first["id"], second["id"]]))["language"]
    assert (row["state"], row["value"]) == ("set", "syc")


def test_a_selection_where_only_some_state_the_fact_is_mixed(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _of_kind(client, doc_id, "line")[:2]
    assert _update(client, [{"segment_id": first["id"], "expected_version": first["version"], "script": "Syrc"}]).status_code == 200
    row = _rows(_inspect(client, [first["id"], second["id"]]))["script"]
    assert row["state"] == "mixed"


def test_the_choices_are_the_engines(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    rows = _rows(_inspect(client, [region["id"]]))
    assert [c["value"] for c in rows["direction"]["choices"]] == DIRECTIONS
    assert [c["value"] for c in rows["line_progression"]["choices"]] == ["ltr", "rtl", "ttb", "btt"]
    assert all(c["label"] for row in rows.values() for c in row["choices"])
    assert [c["value"] for c in rows["type"]["choices"]][:3] == ["main text", "heading", "marginalia"]
    assert rows["furniture"]["kind"] == "toggle"


def test_line_progression_is_set_on_a_region_through_update_many_and_undone(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    sent = _update(client, [{"segment_id": region["id"], "expected_version": region["version"], "line_progression": "rtl"}])
    assert sent.status_code == 200, sent.text
    row = _rows(_inspect(client, [region["id"]]))["line_progression"]
    assert (row["state"], row["value"]) == ("set", "rtl")
    assert next(s for s in _page(client, doc_id) if s["id"] == region["id"])["line_progression"] == "rtl"

    assert client.post(f"/api/actions/audit/{sent.json()['audit_id']}/undo").status_code == 200
    assert _rows(_inspect(client, [region["id"]]))["line_progression"]["state"] == "none"


def test_a_line_progression_the_engine_does_not_know_or_on_a_line_is_refused(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    line = _of_kind(client, doc_id, "line")[0]
    bad = _update(client, [{"segment_id": region["id"], "expected_version": region["version"], "line_progression": "sideways"}])
    assert bad.status_code == 422, bad.text
    on_a_line = _update(client, [{"segment_id": line["id"], "expected_version": line["version"], "line_progression": "rtl"}])
    assert on_a_line.status_code == 422, on_a_line.text


def test_a_region_type_is_written_to_kind_raw_and_leaves_kind_alone(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    sent = _update(client, [{"segment_id": region["id"], "expected_version": region["version"], "kind_raw": "heading"}])
    assert sent.status_code == 200, sent.text
    after = next(s for s in _page(client, doc_id) if s["id"] == region["id"])
    assert after["kind_raw"] == "heading" and after["kind"] == "region"
    row = _rows(_inspect(client, [region["id"]]))["type"]
    assert (row["state"], row["value"]) == ("set", "heading")


def test_furniture_reads_as_a_toggle_and_mixes(db, client):
    doc_id = _import(db, SYRIAC)
    first, second = _of_kind(client, doc_id, "line")[:2]
    assert _update(client, [{"segment_id": first["id"], "expected_version": first["version"], "is_furniture": True}]).status_code == 200
    assert _rows(_inspect(client, [first["id"]]))["furniture"]["value"] == "true"
    assert _rows(_inspect(client, [first["id"], second["id"]]))["furniture"]["state"] == "mixed"


def test_the_read_carries_line_progression_and_updated_at(db, client):
    doc_id = _import(db, SYRIAC)
    region = _of_kind(client, doc_id, "region")[0]
    assert "line_progression" in region and region["line_progression"] is None
    assert region["updated_at"], "the list read says when the row last changed"
    one = client.get(f"/api/segments/{region['id']}").json()["segment"]
    assert one["updated_at"] and "line_progression" in one


def test_an_unknown_id_is_left_out_and_counted_not_a_404(db, client):
    doc_id = _import(db, SYRIAC)
    line = _of_kind(client, doc_id, "line")[0]
    answer = _inspect(client, [line["id"], "no-such-segment"])
    assert answer["count"] == 1 and answer["withheld"] == 1


def test_an_empty_selection_is_refused(client):
    assert client.get("/api/segments/inspect").status_code == 422
