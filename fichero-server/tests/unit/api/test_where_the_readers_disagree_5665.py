"""Where the readers disagree (#5665), tested to the spec (docs/contributor_manual/specs/source/readings-and-apparatus.md:
`source.disagree.route`, `source.disagree.normalised-first`, `source.disagree.medoid-aligned`,
`source.disagree.agreement-not-accuracy`).

WHY: read a page with several readers (or one model sampled several times at temperature) and the words they
disagree on are where correction should go first. Through the route the app reads, on a real page, pass, lines and
readings: each reading a reader's (its page artifact names the model; its run, which sample).
"""
from __future__ import annotations

from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, SegmentPass, bbox_and_tile_from_anchor


def _page(db, width=2000, height=3000):
    page = Document(name="f. 1r", doc_type=DocType.file, file_type=FileType.image, status=Status.completed,
                    metadata={"width": width, "height": height})
    db.save(page)
    pass_row = SegmentPass(document_id=page.id, name="lines", provenance_kind=ProvenanceKind.workflow)
    db.save(pass_row)
    return page, pass_row


def _segment(db, page, pass_row, rect, kind="line", parent=None):
    anchor = SourceAnchor(document_id=page.id, rect=rect)
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    seg = Segment(document_id=page.id, pass_id=pass_row.id, kind=kind, anchor=anchor, parent_segment_id=parent,
                  bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile, doc_kind=f"{page.id}:{kind}",
                  provenance_kind=ProvenanceKind.workflow)
    db.save(seg)
    return seg


def _lines(db, page, pass_row, count):
    return [_segment(db, page, pass_row, [0.1, 0.1 + 0.05 * i, 0.8, 0.04]) for i in range(count)]


def _read(db, page, segment, text, *, model="Qwen2.5-VL-3B", run="run-1"):
    artifact = Artifact(document_id=page.id, artifact_type="transcription", provider="omlx", model=model,
                        content=text)
    db.save(artifact)
    db.save(ContentRepresentation(document_id=page.id, segment_id=segment.id, kind="transcription", content=text,
                                  source_anchor=segment.anchor, derived_from_artifact_id=artifact.id,
                                  producer_run_id=run, provenance_kind=ProvenanceKind.workflow))


def _disagreement(client, page_id):
    r = client.get(f"/api/documents/{page_id}/disagreement")
    assert r.status_code == 200, r.text
    return r.json()


def test_unanimous_lines_score_one(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    for run in ("run-1", "run-2", "run-3"):
        _read(db, page, line, "Yten dixo el testigo", run=run)

    body = _disagreement(client, page.id)

    assert len(body["readers"]) == 3 and body["page_agreement"] == 1.0
    assert body["normalised_as"] == "catmus-as-written"
    [only] = body["lines"]
    assert only["agreement"] == 1.0 and all(w["agreement"] == 1.0 for w in only["words"])
    assert [len(w["variants"]) for w in only["words"]] == [1, 1, 1, 1]
    assert {r["label"] for r in body["readers"]} == {"Qwen2.5-VL 3B (OCR), run 1", "Qwen2.5-VL 3B (OCR), run 2",
                                                     "Qwen2.5-VL 3B (OCR), run 3"}


def test_one_disagreeing_word_scores_fractionally_and_names_who_gave_what(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    _read(db, page, line, "Yten dixo el testigo", run="run-1")
    _read(db, page, line, "Yten dixo el testigo", run="run-2")
    _read(db, page, line, "Yten dixo al testigo", run="run-3")

    body = _disagreement(client, page.id)

    [only] = body["lines"]
    words = {w["text"]: w for w in only["words"]}
    assert abs(words["el"]["agreement"] - 2 / 3) < 1e-9
    assert [v["text"] for v in words["el"]["variants"]] == ["el", "al"], "most readers first"
    readers = {r["label"]: r["id"] for r in body["readers"]}
    assert words["el"]["variants"][1]["readers"] == [readers["Qwen2.5-VL 3B (OCR), run 3"]]
    assert words["dixo"]["agreement"] == 1.0
    assert abs(only["agreement"] - (3 + 2 / 3) / 4) < 1e-9
    assert only["text"][words["testigo"]["char_start"]:words["testigo"]["char_end"]] == "testigo"


def test_u_v_and_i_j_differences_are_not_disagreement(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    _read(db, page, line, "vna iusticia", run="run-1")
    _read(db, page, line, "una justicia", run="run-2")

    body = _disagreement(client, page.id)

    [only] = body["lines"]
    assert only["agreement"] == 1.0, only


def test_the_medoid_reading_is_the_reference(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    # The odd one out is read first: the reference must still be the reading most like the others.
    _read(db, page, line, "Xxxx yyy zz qqqqqqq", run="run-1")
    _read(db, page, line, "Yten dixo el testigo", run="run-2")
    _read(db, page, line, "Yten dixo el testigo", run="run-3")
    _read(db, page, line, "Yten dixo al testigo", run="run-4")

    body = _disagreement(client, page.id)

    readers = {r["label"]: r["id"] for r in body["readers"]}
    [only] = body["lines"]
    assert only["reference_reader"] == readers["Qwen2.5-VL 3B (OCR), run 2"]
    assert only["text"] == "Yten dixo el testigo"


def test_fewer_than_two_readings_answer_with_no_lines_and_an_unknown_page_is_404(db, client):
    page, pass_row = _page(db)
    [line] = _lines(db, page, pass_row, 1)
    body = _disagreement(client, page.id)
    assert body["lines"] == [] and body["page_agreement"] is None and body["readers"] == []

    _read(db, page, line, "Yten dixo el testigo")
    body = _disagreement(client, page.id)
    assert body["lines"] == [] and body["page_agreement"] is None and len(body["readers"]) == 1

    assert client.get("/api/documents/no-such-page/disagreement").status_code == 404


def test_words_the_reference_reading_places_carry_boxes_in_the_images_pixels(db, client):
    page, pass_row = _page(db, width=1000, height=2000)
    [line] = _lines(db, page, pass_row, 1)
    first = _segment(db, page, pass_row, [0.1, 0.1, 0.2, 0.04], kind="word", parent=line.id)
    second = _segment(db, page, pass_row, [0.4, 0.1, 0.3, 0.04], kind="word", parent=line.id)
    for run in ("run-1", "run-2"):
        _read(db, page, line, "dixo el", run=run)
        _read(db, page, first, "dixo", run=run)
        _read(db, page, second, "el", run=run)

    body = _disagreement(client, page.id)

    assert (body["image_width"], body["image_height"]) == (1000, 2000)
    [only] = body["lines"]
    assert [round(v) for v in only["words"][0]["bbox"]] == [100, 200, 200, 80]
    assert [round(v) for v in only["words"][1]["bbox"]] == [400, 200, 300, 80]
