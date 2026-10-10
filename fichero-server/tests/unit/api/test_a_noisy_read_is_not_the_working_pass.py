"""A noisy machine read never takes a page from a sound one by default (#5654 item 2, `source.pass.working`).

WHY: on the demo (test project "Overnight 2026-10-10") page c01_012_right.jpg had a Kraken reading pass
and a NEWER Apple Vision "regions" pass: 656 order entries, Cyrillic noise, 250,355 characters. Newest
machine pass won (`newest-machine-unchosen`), so the page's working text was the noise, and the review
model timed out on it every run. The ranking now passes over a machine read that is longer than a page
can hold (`PAGE_TEXT_BOUND`) or mostly another script's letters than the project's: it comes after every
sound machine read. A page with one pass keeps it; a person's choice always wins.

Through the real paths: each read saved as a run saves it and made a pass by `convert_new_results`, the
project's languages saved by `write_project_setup`, a choice made by `pass.choose_working`; the answer
read back from the page's text (`GET /api/segments/document/{id}/text`) and the segments route.
"""

from __future__ import annotations

from pathlib import Path

import fichero_server.api.main  # noqa: F401  (registers every action)
import pytest
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.maintenance.project_conversion import convert_new_results
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.readings import (
    NOT_THE_PAGES_SCRIPT,
    PAGE_TEXT_BOUND,
    TOO_LONG_FOR_A_PAGE,
    doubtful_read,
)
from fichero_server.models.segments import SegmentPass
from fichero_server.recipes.project import write_project_setup

pytestmark = pytest.mark.source_model

PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
KRAKEN_LINES = ("En la ciudad de Quibdó a diez de octubre", "de mil setecientos años ante mí el escribano")
#: What Apple Vision's regions read made of the page: Cyrillic letters where the hand is Spanish.
CYRILLIC_NOISE = ("Вп лп снпбпб бе Ощнбб п бнег бе осшбге", "бе мнл ветесненшош пнощ пнше мн ел егсгнбпно")


def _page(db) -> Document:
    page = Document(name="c01_012_right.jpg", doc_type=DocType.file, file_type=FileType.image,
                    path="/demo/c01_012_right.jpg", status=Status.completed)
    db.save(page)
    return page


def _read(db, page: Document, provider: str, model: str, lines) -> str:
    """One machine read of the page, saved as a run saves it and made a pass (its text is its lines)."""
    boxes, content = [], ""
    for i, line in enumerate(lines):
        boxes.append(OCRGeometryBox(text=line, bbox=[0.1, 0.1 + i * 0.1, 0.8, 0.06], level="line",
                                    confidence=0.9, char_start=len(content), char_end=len(content) + len(line),
                                    provider=provider, model=model))
        content += line + "\n"
    db.save(Artifact(document_id=page.id, artifact_type="transcription", provider=provider, model=model,
                     content=content, ocr_geometry=OCRGeometryResult(provider=provider, text=content, boxes=boxes)))
    assert convert_new_results(db, page.id) == "converted"
    (made,) = [p for p in db.query(SegmentPass, document_id=page.id) if p.model == model]
    return made.id


def _working(client, page: Document) -> tuple[str | None, str | None]:
    """The working pass as the page's text and the canvas name it, asserted to be one pass."""
    text = client.get(f"/api/segments/document/{page.id}/text").json()
    marked = [p["id"] for p in client.get(f"/api/segments/document/{page.id}").json()["passes"] if p["working"]]
    assert marked == [text["pass_id"]], "the canvas and the text name different passes"
    return text["pass_id"], text["pass_basis"]


def test_a_newer_read_longer_than_a_page_does_not_take_the_page_from_kraken(db, client):
    """The demo's case by size alone (no project languages needed): the newer read holds more characters
    than any page, so the Kraken read stays the working text."""
    page = _page(db)
    kraken = _read(db, page, "kraken", "kraken-catmus", KRAKEN_LINES)
    huge = ["palabra " * 7000] * 2   # 112,000 characters
    vision = _read(db, page, "apple", "apple-vision-regions", huge)

    assert _working(client, page) == (kraken, "newest-machine-unchosen"), (
        f"the newer {vision} read, longer than a page, is still the working text")


def test_a_newer_read_in_another_script_does_not_take_a_spanish_page(db, client):
    """A Spanish project: the newer read's letters are mostly Cyrillic, so the Kraken read stays."""
    write_project_setup(Path(str(db.path)).parent, {"languages": ["es"]}, None)
    page = _page(db)
    kraken = _read(db, page, "kraken", "kraken-catmus", KRAKEN_LINES)
    _read(db, page, "apple", "apple-vision-regions", CYRILLIC_NOISE)

    assert _working(client, page)[0] == kraken


def test_with_no_project_script_the_newest_read_still_wins(db, client):
    """No setup names a language or a script: there is nothing to judge letters against, so a read of a
    page-sized text is never doubted for its script, and the newest wins as before."""
    page = _page(db)
    _read(db, page, "kraken", "kraken-catmus", KRAKEN_LINES)
    vision = _read(db, page, "apple", "apple-vision-regions", CYRILLIC_NOISE)

    assert _working(client, page)[0] == vision


def test_a_page_with_one_read_keeps_it_however_noisy(db, client):
    """WHY: the ranking orders passes, it never withholds one; a page's only read is its text."""
    write_project_setup(Path(str(db.path)).parent, {"languages": ["es"]}, None)
    page = _page(db)
    only = _read(db, page, "apple", "apple-vision-regions", CYRILLIC_NOISE)

    assert _working(client, page) == (only, "newest-machine-unchosen")


def test_a_persons_choice_of_the_noisy_read_wins(db, client):
    """The person's choice always wins, even of a read the ranking doubts."""
    write_project_setup(Path(str(db.path)).parent, {"languages": ["es"]}, None)
    page = _page(db)
    _read(db, page, "kraken", "kraken-catmus", KRAKEN_LINES)
    vision = _read(db, page, "apple", "apple-vision-regions", CYRILLIC_NOISE)
    registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": vision}, PERSON)

    assert _working(client, page) == (vision, "chosen")


def test_the_rule_in_plain_terms():
    """`doubtful_read`, the rule the ranking applies: the bound, the script test, and when it says nothing."""
    assert doubtful_read("x" * (PAGE_TEXT_BOUND + 1)) == TOO_LONG_FOR_A_PAGE
    assert doubtful_read("x" * PAGE_TEXT_BOUND) is None
    assert doubtful_read("\n".join(CYRILLIC_NOISE), {"Latn"}) == NOT_THE_PAGES_SCRIPT
    assert doubtful_read("\n".join(KRAKEN_LINES), {"Latn"}) is None
    # Fraktur is Latin letters; a mixed project accepts either; no script named, no test.
    assert doubtful_read("\n".join(KRAKEN_LINES), {"Latf"}) is None
    assert doubtful_read("\n".join(CYRILLIC_NOISE), {"Latn", "Cyrl"}) is None
    assert doubtful_read("\n".join(CYRILLIC_NOISE), set()) is None
    # A script its letters cannot name alone (Japanese mixes Han and kana): no judgement, never a guess.
    assert doubtful_read("\n".join(CYRILLIC_NOISE), {"Jpan"}) is None
    assert doubtful_read("") is None and doubtful_read(None) is None
