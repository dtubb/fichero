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


# --- `wide.compare.same-page-same-crop` and `wide.compare.price-and-time-per-candidate` (#5900, #6296) ---------------

def _real_page(db, tmp_path, with_crop=False):
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType, NodeRegion, Rendition

    path = tmp_path / "page.png"
    Image.new("RGB", (200, 100), "white").save(path)
    doc = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)
    if with_crop:
        cut = tmp_path / "crop.png"
        Image.new("RGB", (120, 80), "white").save(cut)
        db.save(Rendition(document_id=doc.id, role="crop", path=str(cut), pixel_width=120, pixel_height=80,
                          transform=NodeRegion(rect=[0.1, 0.1, 0.6, 0.8])))  # (20, 10) to (140, 90) of the 200 by 100 photograph
    return doc


def _two_candidates(monkeypatch, page_id, columns):
    from fichero_server.recipes import samples

    def reading(text, box):
        return {"kind": "transcription", "level": None, "text": text, "bbox": box}

    result = {"stage": "read", "project_pages": 300, "pages": [page_id, "p2", "p3"], "candidates": [
        {**columns[0], "card": "a", "name": "A", "per_page": [{"id": page_id, "readings": [reading("Yten dixo", [0.2, 0.30, 0.4, 0.2])]}]},
        {**columns[1], "card": "b", "name": "B", "per_page": [{"id": page_id, "readings": [reading("Yten dixo", [0.2, 0.30, 0.4, 0.2])]}]}]}
    monkeypatch.setattr(samples, "read_result", lambda db, stage, recipe: result)
    monkeypatch.setattr("fichero_server.recipes.project.read_project_setup", lambda library: {"recipe": None})


def test_wide_every_candidate_is_drawn_on_the_one_current_image_inside_the_page_box(db, client, tmp_path, monkeypatch):
    doc = _real_page(db, tmp_path, with_crop=True)
    _two_candidates(monkeypatch, doc.id, [{}, {}])
    body = _compare(client, doc.id, "?try_stage=read")
    assert body["frame"]["read_from"] == "rendition" and body["frame"]["followed"] is True
    assert (body["frame"]["image_width"], body["frame"]["image_height"]) == (120, 80)
    assert (body["image_width"], body["image_height"]) == (200, 100), "`bbox` stays in the photograph's pixels"
    [line] = body["lines"]
    assert line["bbox"] == [40.0, 30.0, 80.0, 20.0]
    # the photograph box (40,30,80,20) lies at (20,20) of the 120 by 80 crop that starts at (20, 10)
    assert [round(v) for v in line["frame_bbox"]] == [20, 20, 80, 20]


def test_wide_a_page_with_no_edit_or_rendition_is_the_photograph_and_boxes_do_not_move(db, client, tmp_path, monkeypatch):
    doc = _real_page(db, tmp_path)
    _two_candidates(monkeypatch, doc.id, [{}, {}])
    body = _compare(client, doc.id, "?try_stage=read")
    assert body["frame"]["read_from"] == "original" and body["frame"]["followed"] is True
    assert body["lines"][0]["frame_bbox"] == body["lines"][0]["bbox"]


def test_wide_a_frame_that_cannot_be_followed_is_the_photograph_and_says_so(db, client, tmp_path, monkeypatch):
    from fichero_server.models import ImageEditChain

    doc = _real_page(db, tmp_path)
    db.save(ImageEditChain(document_id=doc.id, operations=[{"op": "crop", "page": 1, "params": {"left": 0, "top": 0, "width": 10, "height": 10}}]))
    from fichero_server.media import current_image

    monkeypatch.setattr(current_image, "chain_map", lambda *a, **k: (_ for _ in ()).throw(current_image.Unmappable("an unrecorded edit")))
    monkeypatch.setattr(current_image, "resolve_edited_source", lambda *a, **k: tmp_path / "edited.png", raising=False)
    (tmp_path / "edited.png").write_bytes((tmp_path / "page.png").read_bytes())
    _two_candidates(monkeypatch, doc.id, [{}, {}])
    body = _compare(client, doc.id, "?try_stage=read")
    assert body["frame"]["followed"] is False and "photograph" in body["frame"]["note"]
    assert body["lines"][0]["frame_bbox"] is None


def test_wide_a_candidates_head_carries_its_error_rate_time_price_and_why_a_figure_is_missing(db, client, tmp_path, monkeypatch):
    doc = _real_page(db, tmp_path)
    measured = {"cer": 0.042, "seconds": 18.0, "local": True, "cost_usd": {"value": 0.0, "basis": "runs on this Mac", "measured": True}}
    unmeasured = {"cer": None, "seconds": None, "local": False, "cost_usd": {"value": 0.12, "basis": "estimate", "measured": False}}
    _two_candidates(monkeypatch, doc.id, [measured, unmeasured])
    a, b = _compare(client, doc.id, "?try_stage=read")["readers"]
    assert {k: a["measure"][k] for k in ("cer", "seconds", "cost_usd", "cost_basis", "local", "not_measured")} == {
        "cer": 0.042, "seconds": 18.0, "cost_usd": 0.0, "cost_basis": "runs on this Mac", "local": True, "not_measured": None}
    assert b["measure"]["cer"] is None and b["measure"]["cost_usd"] == 0.12 and b["measure"]["cost_basis"] == "estimate"
    assert "not measured: error rate and time" in b["measure"]["not_measured"]


def test_wide_a_candidates_head_scales_its_sample_figures_to_the_whole_project(db, client, tmp_path, monkeypatch):
    """`wide.compare.price-and-time-per-candidate`: pages an hour, the project's cost and hours, from the sample's seconds and cost and
    the project's page count, with the basis said; an unmeasured candidate has none of them and says why."""
    doc = _real_page(db, tmp_path)
    measured = {"cer": 0.04, "seconds": 18.0, "local": False, "cost_usd": {"value": 0.30, "basis": "measured", "measured": True}}
    unmeasured = {"cer": None, "seconds": None, "local": False, "cost_usd": {"value": None, "basis": "unknown", "measured": False}}
    _two_candidates(monkeypatch, doc.id, [measured, unmeasured])
    a, b = _compare(client, doc.id, "?try_stage=read")["readers"]
    a, b = _compare(client, doc.id, "?try_stage=read")["readers"]
    assert a["measure"]["seconds_per_page"] == 6.0 and a["measure"]["pages_per_hour"] == 600.0
    assert a["measure"]["project_pages"] == 300 and a["measure"]["project_hours"] == 0.5
    assert a["measure"]["project_cost_usd"] == 30.0 and "3 sample pages" in a["measure"]["project_basis"]
    assert all(b["measure"][k] is None for k in ("seconds_per_page", "pages_per_hour", "project_hours", "project_cost_usd"))
    assert b["measure"]["not_measured"]
