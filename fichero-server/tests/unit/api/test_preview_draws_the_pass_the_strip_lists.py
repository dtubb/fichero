"""Preview draws the words the Segments list lists, with a newer run's result beside them (#5463).

The maintainer, on a diary page: the Segments list showed the page's Apple Vision words, every box
switch was on, and Preview drew none of them, while a Detect Segments (Kraken) run was going. The
list reads the page's order (`GET /api/reading-orders/document/{id}`) and the text reads
`document_text`; both take the working pass from the REAL passes only. The canvas reads the
`working` mark on `GET /api/segments/document/{id}`, which also counted a result not yet made a pass
(a run's result between its save and its conversion, or one whose conversion failed). Newest by
date, that result took the mark, so Preview drew the run's boxes, not the words listed beside them.

Through the calls the app makes. The segment list's answer is recorded for the app's test
(`ImportedPageDrawsItsBoxesTests.testTheWordsTheSegmentsListListsAreDrawnBesideAnUnconvertedRun`),
which plays it through the real Preview. Rewrite with FICHERO_UPDATE_FIXTURES=1.
"""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.maintenance.project_conversion import convert_new_results
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.core.timeutil import utc_now
from tests.unit.api.test_imported_page_draws_its_boxes import FIXTURES, _stable

ROUTE_FIXTURE = FIXTURES / "diary_words_beside_an_unconverted_run.route.json"
WORDS = ["12.", "1940", "TUESDAY", "FEBRUARY"]


def _stable_ids(body: dict) -> dict:
    """`_stable`, then every id it does not know (the results' artifact ids, random per run) as a token."""
    tokens: dict[str, str] = {}

    def walk(value):
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value):
            return tokens.setdefault(value, f"artifact-{len(tokens) + 1:04d}")
        if isinstance(value, str) and re.match(r"\d{4}-\d\d-\d\dT", value):
            return "2026-09-27T12:00:00Z"
        return value

    return walk(_stable(body))


def _page_with_words(db) -> Document:
    """A diary page with Apple Vision's words, made a pass the way every new result is."""
    page = Document(name="IMG_011_part_2.jpg", doc_type=DocType.file, file_type=FileType.image,
                    path="/diary/IMG_011_part_2.jpg", status=Status.completed)
    db.save(page)
    boxes, content = [], ""
    for i, word in enumerate(WORDS):
        boxes.append(OCRGeometryBox(
            text=word, bbox=[0.1 + i * 0.2, 0.1, 0.15, 0.05], level="word", confidence=1.0,
            char_start=len(content), char_end=len(content) + len(word), provider="apple", model="apple-vision",
        ))
        content += word + " "
    db.save(Artifact(document_id=page.id, artifact_type="transcription", provider="apple", model="apple-vision",
                     content=content, ocr_geometry=OCRGeometryResult(provider="apple", text=content, boxes=boxes)))
    assert convert_new_results(db, page.id) == "converted"
    return page


def _run_result_not_yet_a_pass(db, page: Document, *, by_a_person: bool = False) -> Artifact:
    """Kraken's lines for the page, saved and NOT converted: the state between a run's save and its
    conversion, or after a conversion that failed (the result stays readable from its boxes)."""
    lines = [OCRGeometryBox(
        text="", bbox=[0.1, 0.1 + i * 0.1, 0.7, 0.06], level="line",
        provider="user" if by_a_person else "kraken", source="manual" if by_a_person else None,
        metadata={"polygon_px": [[100, 100 + i * 100], [800, 100 + i * 100], [800, 160 + i * 100], [100, 160 + i * 100]],
                  "baseline_px": [[100, 150 + i * 100], [800, 150 + i * 100]],
                  "pixel_frame": {"width": 1000, "height": 1000}},
    ) for i in range(3)]
    result = Artifact(document_id=page.id, artifact_type="regions", provider="kraken", model="kraken-blla", content="",
                      ocr_geometry=OCRGeometryResult(provider="kraken", text="", boxes=lines),
                      created_at=utc_now() + timedelta(minutes=5))
    db.save(result)
    return result


def test_the_canvas_s_working_pass_is_the_one_the_segments_list_and_the_text_read(db, client):
    page = _page_with_words(db)
    _run_result_not_yet_a_pass(db, page)

    listing = client.get(f"/api/segments/document/{page.id}")          # SegmentStore.load's call
    assert listing.status_code == 200, listing.text
    body = listing.json()
    [words_pass] = [p for p in body["passes"] if not p["provisional"]]
    [run] = [p for p in body["passes"] if p["provisional"]]
    # WHY: the run's result IS newer, so the newest-machine rule picks it if it is a candidate here --
    # and it is not one anywhere else. Exactly one pass carries the mark, and it is the words' pass.
    assert run["created_at"] > words_pass["created_at"]
    assert [p["id"] for p in body["passes"] if p["working"]] == [words_pass["id"]]
    assert words_pass["working_basis"] == "newest-machine-unchosen"

    # The same pass the Segments list lists (its order is the as-written order shown first) ...
    orders = client.get(f"/api/reading-orders/document/{page.id}").json()["orders"]
    assert orders[0]["kind"] == "as-written" and orders[0]["pass_id"] == words_pass["id"]
    # ... and the page's text reads.
    assert client.get(f"/api/segments/document/{page.id}/text").json()["pass_id"] == words_pass["id"]

    listed = [s for s in body["segments"] if s["pass_id"] == words_pass["id"]]
    assert sorted(s["text"] for s in listed) == sorted(WORDS) and all(s["kind"] == "word" for s in listed)

    stable = _stable_ids(body)
    if os.environ.get("FICHERO_UPDATE_FIXTURES") == "1":
        ROUTE_FIXTURE.write_text(json.dumps(stable, indent=1, ensure_ascii=True) + "\n")
    assert json.loads(ROUTE_FIXTURE.read_text()) == stable, "the app's fixture drifted from the engine's answer"


def test_once_the_run_s_result_is_a_pass_every_surface_moves_to_it_together(db, client):
    """WHY: the fix is not "an unconverted result never wins" but "the canvas follows the same rule":
    converted, the newer run is the working pass for the canvas, the list and the text alike."""
    page = _page_with_words(db)
    _run_result_not_yet_a_pass(db, page)
    assert convert_new_results(db, page.id) == "converted"

    body = client.get(f"/api/segments/document/{page.id}").json()
    [working] = [p for p in body["passes"] if p["working"]]
    assert {s["kind"] for s in body["segments"] if s["pass_id"] == working["id"]} == {"line"}
    assert client.get(f"/api/reading-orders/document/{page.id}").json()["orders"][0]["pass_id"] == working["id"]
    assert client.get(f"/api/segments/document/{page.id}/text").json()["pass_id"] == working["id"]


def test_a_page_with_no_pass_yet_still_marks_its_unconverted_result(db, client):
    """WHY: an unconverted page draws its results' boxes and must say which is working, or converting it
    would change the answer on screen (test_segment_conversion_action)."""
    page = Document(name="loose.jpg", doc_type=DocType.file, file_type=FileType.image,
                    path="/diary/loose.jpg", status=Status.completed)
    db.save(page)
    _run_result_not_yet_a_pass(db, page)
    body = client.get(f"/api/segments/document/{page.id}").json()
    assert [p["provisional"] for p in body["passes"] if p["working"]] == [True]


def test_an_unconverted_result_a_person_corrected_still_counts_beside_real_passes(db, client):
    """WHY: `source.pass.working` -- a pass a person touched outranks a newer machine run; leaving a
    corrected result out of the candidates would hide the person's boxes behind the machine's."""
    page = _page_with_words(db)
    _run_result_not_yet_a_pass(db, page, by_a_person=True)
    body = client.get(f"/api/segments/document/{page.id}").json()
    [working] = [p for p in body["passes"] if p["working"]]
    assert working["provisional"] is True and working["working_basis"] == "human-touched"
