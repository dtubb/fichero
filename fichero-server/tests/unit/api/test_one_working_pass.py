"""One working pass, chosen in ONE place (#5467, `source.pass.working`).

WHY: a page's working pass was picked twice in the engine. `document_text` (the page's text, the
Order list, the text cache, export) ranked the page's real passes; the segments route, which the
canvas draws from, ranked them PLUS the provisional passes of unconverted results, with a rule of its
own, and only among the passes its (possibly filtered) response held. So for the same page the
Preview could name one pass and the text another. The rule now lives in `resolve_working_pass`, and
every surface reads `working_pass`. If a second ranking ever comes back, these cases split.

The ruling each case pins: a person's choice > a person's work > a PDF text layer > the newest; an
import has no rank of its own; an unconverted result counts only if a person corrected it or the page
has no pass at all. Through the real routes: the segments route (`working`), the page's text
(`GET /api/segments/document/{id}/text`), the Order list (`GET /api/reading-orders/document/{id}`:
the working pass's as-written order first) and export (`choices.pass_id`).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.page_text_cache import DERIVATION_STAMP, ensure_current
from fichero_server.actions.registry import registry
from fichero_server.core.timeutil import utc_now
from fichero_server.maintenance.project_conversion import convert_new_results
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, Document
from tests.unit.api.test_an_import_has_no_rank_of_its_own import (
    PAGE_A, PERSON, TEXT_ONLY_TEI, _import, _machine_run, _page,
)
from tests.unit.api.test_preview_draws_the_pass_the_strip_lists import (
    _page_with_words, _run_result_not_yet_a_pass,
)

pytestmark = pytest.mark.source_model


def _every_surface(client, doc_id: str) -> str | None:
    """The working pass as each surface names it, asserted to be ONE pass; returns it."""
    passes = client.get(f"/api/segments/document/{doc_id}").json()["passes"]
    marked = [p for p in passes if p["working"]]
    assert len(marked) <= 1, "two passes marked working"
    drawn = marked[0]["id"] if marked else None

    text = client.get(f"/api/segments/document/{doc_id}/text").json()
    assert text["pass_id"] == drawn, f"the canvas draws {drawn}, the text reads {text['pass_id']}"
    if marked:
        assert text["pass_basis"] == marked[0]["working_basis"], "same pass, different reason"

    orders = client.get(f"/api/reading-orders/document/{doc_id}").json()["orders"]
    as_written = [o["pass_id"] for o in orders if o["kind"] == "as-written"]
    if drawn in as_written:
        assert as_written[0] == drawn, "the Order tab lists another pass's lines first"

    export = client.get(f"/api/documents/{doc_id}/export/tei")
    if drawn is None or drawn.startswith("legacy:"):
        # Nothing to write: no pass, or a result not yet made rows. Refused, never an empty page.
        assert export.status_code != 200, export.text
    else:
        assert export.status_code == 200, export.text
        assert export.json()["choices"]["pass_id"] == drawn, "export writes another pass"
    return drawn


def _basis(client, doc_id: str) -> str | None:
    return client.get(f"/api/segments/document/{doc_id}/text").json()["pass_basis"]


def test_a_persons_choice(db, client):
    """WHY: a live choice outranks everything, here an older import over a newer run."""
    doc_id = _page(db)
    imported = _import(db, doc_id, PAGE_A)
    _machine_run(db, doc_id)
    registry.invoke(db, "pass.choose_working", {"document_id": doc_id, "pass_id": imported}, PERSON)
    assert _every_surface(client, doc_id) == imported and _basis(client, doc_id) == "chosen"


def test_a_persons_work(db, client):
    """WHY: a pass a person made outranks a newer machine run (2026-09-03: a drawn region vanished)."""
    doc_id = _page(db)
    mine = registry.invoke(db, "segment.pass_create", {"document_id": doc_id, "name": "mine"}, PERSON).result["id"]
    _machine_run(db, doc_id)
    assert _every_surface(client, doc_id) == mine and _basis(client, doc_id) == "human-touched"


def test_a_pdf_text_layer(db, client):
    """WHY: the file's own text layer is the author's words, so it outranks a newer machine reading."""
    page = _page_with_words(db)  # converted; not a text layer
    layer = Artifact(document_id=page.id, artifact_type="text_geometry", provider="pdf", model="text-layer",
                     content="Dear Sir ", created_at=utc_now() + timedelta(minutes=1),
                     ocr_geometry=OCRGeometryResult(provider="pdf", text="Dear Sir ", boxes=[OCRGeometryBox(
                         text="Dear Sir", bbox=[0.1, 0.5, 0.3, 0.05], level="line", confidence=1.0,
                         char_start=0, char_end=8, provider="pdf", model="text-layer")]))
    db.save(layer)
    assert convert_new_results(db, page.id) == "converted"
    _machine_run(db, page.id)  # newer than both
    drawn = _every_surface(client, page.id)
    assert _basis(client, page.id) == "text-layer"
    assert drawn == next(p["id"] for p in client.get(f"/api/segments/document/{page.id}").json()["passes"]
                         if p["source_artifact_id"] == layer.id)


def test_the_newest(db, client):
    """WHY: with no choice, no person's work and no text layer, the newest machine pass is shown,
    labelled unchosen in a strict project."""
    doc_id = _page(db)
    _machine_run(db, doc_id)
    newer = _machine_run(db, doc_id)
    assert _every_surface(client, doc_id) == newer and _basis(client, doc_id) == "newest-machine-unchosen"


def test_an_import_has_no_rank(db, client):
    """WHY: #5443 -- an older import never outranks a later run."""
    doc_id = _page(db)
    _import(db, doc_id, PAGE_A)
    run = _machine_run(db, doc_id)
    assert _every_surface(client, doc_id) == run


def test_a_shapeless_newest_pass(db, client):
    """WHY: a pass whose lines have no shapes (a facsimile-free TEI) is still a pass, ranked by date;
    every surface names it, so the app cannot quietly draw an older shaped pass in its place."""
    doc_id = _page(db)
    _machine_run(db, doc_id)
    tei = _import(db, doc_id, TEXT_ONLY_TEI)
    assert _every_surface(client, doc_id) == tei


def test_an_unconverted_result_nobody_corrected_does_not_take_the_page(db, client):
    """WHY: #5463 -- newest by date, an uncorrected run's result took the canvas while the list and
    the text read the real pass."""
    page = _page_with_words(db)
    _run_result_not_yet_a_pass(db, page)
    drawn = _every_surface(client, page.id)
    assert drawn is not None and not drawn.startswith("legacy:")


def test_an_unconverted_result_a_person_corrected_takes_it_on_every_surface(db, client):
    """WHY: a person's work is never hidden behind a machine's. The segments route said so and the
    text did not (it ranked real passes only): the disagreement this resolves, toward the ruling."""
    page = _page_with_words(db)
    result = _run_result_not_yet_a_pass(db, page, by_a_person=True)
    assert _every_surface(client, page.id) == f"legacy:{result.id}"
    assert _basis(client, page.id) == "human-touched"
    # Its words are not rows yet, so nothing derives: the stored page text stands, never blanked by
    # the Reader's re-derivation of a stale cache (`ensure_current`, here forced by a missing stamp).
    doc = db.get(Document, page.id)
    doc.page_content = "12. 1940 TUESDAY FEBRUARY"
    doc.metadata = {k: v for k, v in (doc.metadata or {}).items() if k != DERIVATION_STAMP}
    db.save(doc)
    assert ensure_current(db, [page.id]) == []
    assert db.get(Document, page.id).page_content == "12. 1940 TUESDAY FEBRUARY"


def test_an_unconverted_result_on_a_page_with_no_pass_is_named_everywhere(db, client):
    """WHY: an unconverted page draws its result's boxes; the text used to say "no pass" for the same
    page. Converting it must change nothing you can see, so it is named before and after."""
    page = _page(db)
    result = _run_result_not_yet_a_pass(db, db.get(Document, page))
    assert _every_surface(client, page) == f"legacy:{result.id}"
    assert convert_new_results(db, page) == "converted"
    converted = _every_surface(client, page)
    assert converted is not None and not converted.startswith("legacy:")


def test_a_filtered_segments_read_marks_the_same_pass(db, client):
    """WHY: the route used to rank only the passes its response held, so `?artifact_id=` of an older
    result could mark that one working on a page whose working pass is another."""
    page = _page(db)
    older = _run_result_not_yet_a_pass(db, db.get(Document, page))
    newer = _run_result_not_yet_a_pass(db, db.get(Document, page))
    newer.created_at = utc_now() + timedelta(minutes=10)
    db.save(newer)
    assert _every_surface(client, page) == f"legacy:{newer.id}"
    filtered = client.get(f"/api/segments/document/{page}", params={"artifact_id": older.id}).json()["passes"]
    assert [p["working"] for p in filtered] == [False]
