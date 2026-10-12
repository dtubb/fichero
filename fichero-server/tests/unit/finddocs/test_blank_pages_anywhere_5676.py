"""`source.onboard.auto.blank-pages-not-read` (#5676): a blank page is caught wherever it falls, and a written page on
a dark ground is not taken for one.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, an end-to-end onboarding
on CACIQUES_INDIOS,17,D.5): of its four "Hoja_en_blanco" sheets only one page was caught as blank, and that one was a
written page shot on black. The ink was measured against the paper's median, which a broad ground around the sheet
becomes: the archive's placeholder (a white sheet photographed on grey) read as 6% ink, the page on black as 0%; and
only a blank right after a written page was caught. Blank is a proposal: a person who gives the page a kind has it
read. Pages drawn here, plus the real sheets from the test corpus when it is on this Mac (copied to a temp folder).
"""
from __future__ import annotations

import random
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from fichero_server.finddocs.job import blank_versos
from fichero_server.models import DocType, Document, FileType
from fichero_server.recipes import sorting

CORPUS = Path.home() / "Fichero Test Corpus" / "Colombia" / "CACIQUES_INDIOS,17,D.5"


def _sheet(path: Path, *, ground: int, written: bool, seed: str = "s") -> Path:
    """A cream sheet on a ground (0 black, 128 grey), with lines of dark strokes when written."""
    image = Image.new("L", (900, 1200), ground)
    draw = ImageDraw.Draw(image)
    draw.rectangle([150, 100, 750, 1120], fill=232)
    if written:
        rng = random.Random(seed)
        for row in range(160, 1060, 30):
            x = 180
            while x < 700:
                width = rng.randint(10, 40)
                draw.line([x, row, x + width, row + rng.randint(-3, 3)], fill=50, width=3)
                x += width + rng.randint(8, 18)
    image.save(path)
    return path


def _folder(db, paths: list[Path]) -> list[str]:
    folder = Document(name="CACIQUES_INDIOS,17,D.5", doc_type=DocType.folder)
    db.save(folder)
    ids = []
    for i, path in enumerate(paths):
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                       parent_id=folder.id, sort_order=i)
        db.save(doc)
        ids.append(doc.id)
    return ids


def test_a_blank_page_is_caught_wherever_it_falls_and_a_page_on_black_is_written(db, tmp_path):
    pages = [
        _sheet(tmp_path / "1_blank_first_on_grey.png", ground=128, written=False),
        _sheet(tmp_path / "2_written_on_black.png", ground=0, written=True, seed="a"),
        _sheet(tmp_path / "3_blank_after_written_on_black.png", ground=0, written=False),
        _sheet(tmp_path / "4_blank_after_blank_on_black.png", ground=0, written=False),
        _sheet(tmp_path / "5_written_on_grey.png", ground=128, written=True, seed="b"),
    ]
    ids = _folder(db, pages)
    assert blank_versos(db, ids) == {ids[0], ids[2], ids[3]}


@pytest.mark.skipif(not CORPUS.is_dir(), reason="the test corpus is not on this Mac")
def test_the_real_blank_sheets_are_caught_and_its_faintest_written_page_is_not(db, tmp_path):
    """Measured on the folder's sheets: the placeholder 0.007, its faintest written page (42, mostly bleed-through
    with a few faint lines and a note in the margin) 0.0175; the line is at 0.011."""
    here = tmp_path / "copies"
    here.mkdir()
    for name in ("2_Hoja_en_blanco.jpg", "42_Hoja_550_Verso.JPG", "51_Hoja_555_Recto.JPG"):
        shutil.copy(CORPUS / name, here / name)
    order = ["2_Hoja_en_blanco.jpg", "51_Hoja_555_Recto.JPG", "42_Hoja_550_Verso.JPG", "2_Hoja_en_blanco.jpg",
             "2_Hoja_en_blanco.jpg"]  # first, after a written page, and a blank after a blank
    ids = _folder(db, [here / name for name in order])
    assert blank_versos(db, ids) == {ids[0], ids[3], ids[4]}


def test_blank_is_a_proposal_a_person_can_undo(client, db, tmp_path):
    ids = _folder(db, [_sheet(tmp_path / "blank.png", ground=0, written=False)])
    assert sorting.kinds(db, ids, ["handwriting"]) == {ids[0]: "blank"}

    r = client.put(f"/api/documents/{ids[0]}", json={"attributes": {"material": "handwriting"}})
    assert r.status_code == 200, r.text
    assert sorting.kinds(db, ids, ["handwriting"]) == {ids[0]: "handwriting"}, "the person's kind is kept"
