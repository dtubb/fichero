"""Compare readers, the engine's answer (#5900): `source.compare.readers-answer` and `source.compare.try-candidates-same-shape`.

ONE route, `GET /api/documents/{page_id}/compare-readers`: a page's own readings, or (`?try_stage=`) a stage Try's candidates, through
the one builder `compare_lines`. Fixtures are the disagreement tests' (a page, a pass of lines, readings with their artifacts)."""
from __future__ import annotations

from fichero_server.models import ContentRepresentation
from fichero_server.models.knowledge import ProvenanceKind
from tests.unit.api.test_where_the_readers_disagree_5665 import _lines, _page, _read


def _compare(client, page_id, query=""):
    r = client.get(f"/api/documents/{page_id}/compare-readers{query}")
    assert r.status_code == 200, r.text
    return r.json()


def _three_readers(db, texts=("Yten dixo el testigo", "Yten dixo el testigo", "Yten dixo al testigo")):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    for run, text in zip(("run-1", "run-2", "run-3"), texts, strict=True):
        _read(db, page, line, text, run=run)
    return page, line


def test_the_shape_every_reader_every_line_with_the_reading_id_and_a_picture_reference(db, client):
    page, line = _three_readers(db)
    body = _compare(client, page.id)
    assert len(body["readers"]) == 3 and {r["kind"] for r in body["readers"]} == {"reader"}
    assert (body["image_width"], body["image_height"]) == (2000, 3000)
    [only] = body["lines"]
    assert only["segment_id"] == line.id and only["order"] == 0 and only["differs"] is True
    assert len(only["readings"]) == 3 and all(r["representation_id"] for r in only["readings"])
    assert only["picture"] == f"/api/segments/{line.id}/picture", "a storage reference, never a local path"
    assert not only["picture"].startswith("/Users") and only["bbox"] is not None
    assert {w["text"]: w["agreement"] for w in only["words"]}["dixo"] == 1.0
    assert only["picked_by_person"] is False


def test_the_text_is_as_written_while_agreement_is_worked_out_on_the_normalised(db, client):
    written = "Yten  dixo el   testigo"
    page, _line = _three_readers(db, texts=(written, "Yten dixo el testigo", "Yten dixo el testigo"))
    [only] = _compare(client, page.id)["lines"]
    assert written in [r["text"] for r in only["readings"]], "the reader's own text, untouched"


def test_one_reader_lists_its_line_and_does_not_differ(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    _read(db, page, line, "Yten dixo el testigo")
    body = _compare(client, page.id)
    [only] = body["lines"]
    assert len(only["readings"]) == 1 and only["differs"] is False and only["agreement"] is None
    assert len(body["readers"]) == 1


def test_a_persons_reading_is_shown_as_the_one_that_counts(db, client):
    page, line = _three_readers(db)
    db.save(ContentRepresentation(document_id=page.id, segment_id=line.id, kind="transcription",
                                  content="Ytem dixo el testigo", source_anchor=line.anchor,
                                  provenance_kind=ProvenanceKind.human))
    body = _compare(client, page.id)
    [only] = body["lines"]
    assert any(r["kind"] == "person" for r in body["readers"])
    assert only["counting_reader_id"] == "person" and only["picked_by_person"] is True
    assert "Ytem dixo el testigo" in [r["text"] for r in only["readings"]]


def test_readers_narrows_and_only_differing_leaves_out_the_lines_where_they_agree(db, client):
    page, pass_row = _page(db)
    agreed, differing = _lines(db, page, pass_row, 2)
    for run in ("run-1", "run-2"):
        _read(db, page, agreed, "Yten dixo", run=run)
    _read(db, page, differing, "el testigo", run="run-1")
    _read(db, page, differing, "al testigo", run="run-2")
    everything = _compare(client, page.id)
    assert [line["differs"] for line in everything["lines"]] == [False, True]
    only = _compare(client, page.id, "?only_differing=true")
    assert [line["segment_id"] for line in only["lines"]] == [differing.id]
    first = everything["readers"][0]["id"]
    from urllib.parse import quote

    # a reader id carries a `#` (model#run): unencoded it starts the URL fragment and the filter never reaches the route
    narrowed = _compare(client, page.id, f"?readers={quote(first, safe='')}")
    assert [r["id"] for r in narrowed["readers"]] == [first]
    assert all(len(line["readings"]) == 1 and line["differs"] is False for line in narrowed["lines"])


def test_an_unknown_page_is_404_and_fewer_than_two_readers_is_200(db, client):
    assert client.get("/api/documents/nope/compare-readers").status_code == 404
    page, _pass = _page(db)
    body = _compare(client, page.id)
    assert body["readers"] == [] and body["lines"] == []


# --- a stage Try's candidates, the SAME answer ---------------------------------------------------------------------


def _try_result(monkeypatch, page_id):
    def reading(text, box):
        return {"kind": "transcription", "level": None, "text": text, "bbox": box}

    result = {"stage": "read", "candidates": [
        {"card": "kraken-a", "name": "Kraken A", "per_page": [{"id": page_id, "readings": [
            reading("Yten dixo", [0.1, 0.10, 0.8, 0.04]), reading("el testigo", [0.1, 0.20, 0.8, 0.04])]}]},
        {"card": "vision-b", "name": "Vision B", "per_page": [{"id": page_id, "readings": [
            reading("Yten dixo", [0.1, 0.11, 0.8, 0.04]), reading("al testigo", [0.1, 0.21, 0.8, 0.04])]}]},
    ]}
    from fichero_server.recipes import samples

    monkeypatch.setattr(samples, "read_result", lambda db, stage, recipe: result if stage == "read" else None)
    monkeypatch.setattr("fichero_server.recipes.project.read_project_setup", lambda library: {"recipe": None})


def test_a_try_gives_the_same_shape_with_the_candidates_as_readers_and_no_pick(db, client, monkeypatch):
    page, _pass = _page(db)
    _try_result(monkeypatch, page.id)
    body = _compare(client, page.id, "?try_stage=read")
    assert [(r["id"], r["label"], r["kind"]) for r in body["readers"]] == [
        ("kraken-a", "Kraken A", "candidate"), ("vision-b", "Vision B", "candidate")]
    assert [line["differs"] for line in body["lines"]] == [False, True], "lines matched by the box they cover"
    assert all(line["segment_id"] is None and line["picked_by_person"] is False for line in body["lines"])
    assert all(r["representation_id"] is None for line in body["lines"] for r in line["readings"]), "a try has no pick"


def test_a_stage_with_no_try_is_404(db, client, monkeypatch):
    page, _pass = _page(db)
    _try_result(monkeypatch, page.id)
    assert client.get(f"/api/documents/{page.id}/compare-readers?try_stage=names").status_code == 404
