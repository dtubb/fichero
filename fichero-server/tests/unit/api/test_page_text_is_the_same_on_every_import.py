"""The same file imported twice reads the same, in the file's order.

WHY: page text follows the default order, and before #5137's `file_position` that order ended
in a segment's id -- a random uuid minted per import. The acceptance run (2026-09-27) imported
Cherokee Phoenix p.2 twice and got two different texts of the same length: any rows whose
geometry tied were ordered by chance. A text that changes when nothing but the import changed
cannot be cited, diffed, or cached. If the order ever falls back to the id again, the lines
below (five boxes in one place, as a re-segmented line or a stacked gloss produces) come out
shuffled and these fail.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
import fichero_server.api.routes.document.content_representations  # noqa: F401  (registers pass.choose_working)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.db import db_manager
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.segments import SegmentPass

CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
WORDS = ["alpha", "beta", "gamma", "delta", "epsilon"]

# Five lines on ONE box: geometry cannot order them, only the file can.
_LINES = "".join(
    f'<TextLine id="l{i}"><Coords points="10,10 990,10 990,60 10,60"/>'
    f"<TextEquiv><Unicode>{word}</Unicode></TextEquiv></TextLine>"
    for i, word in enumerate(WORDS)
)
PAGE = (
    '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">'
    '<Page imageFilename="p.jpg" imageWidth="1000" imageHeight="1000">'
    '<TextRegion id="r"><Coords points="10,10 990,10 990,500 10,500"/>'
    f"{_LINES}</TextRegion></Page></PcGts>"
).encode()


def _import_into_a_fresh_library(tmp_path, name: str) -> str:
    db = db_manager.get_database(tmp_path / f"{name}.fichero", create=True)
    doc = Document(name="p.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/p.jpg", status=Status.completed)
    db.save(doc)
    source = tmp_path / f"{name}.page.xml"
    source.write_bytes(PAGE)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(source)}, CTX)
    [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc.id]
    registry.invoke(db, "pass.choose_working", {"document_id": doc.id, "pass_id": pass_row.id}, CTX)
    return document_text(db, doc.id).text


@pytest.fixture(autouse=True)
def _close(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    yield
    db_manager.close_all()


def test_two_imports_of_one_file_give_one_text_in_the_files_order(tmp_path):
    first = _import_into_a_fresh_library(tmp_path, "first")
    second = _import_into_a_fresh_library(tmp_path, "second")

    assert first == second
    positions = [first.index(word) for word in WORDS]
    assert positions == sorted(positions), first
