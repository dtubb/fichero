"""Find the Documents reads a page line by line, and runs at a person's priority inside a recipe (#5709), tested to the
spec: `finddocs.recipe-step` (docs/contributor_manual/specs/source/finding-documents.md).

WHY: after a fresh line-by-line read of CACIQUES_INDIOS,17,D.5, every page's text, derived from its line readings,
was one line (the derivation joins them with spaces), so no folio "1" was seen and four documents were proposed as
one. The step also took 27 minutes inside the recipe, against one alone: the recipe's child ran at BACKGROUND QoS
(e-cores, throttled disk) while 19 all-core embed jobs ran, and finished 0.26 s after the last of them.
"""

from __future__ import annotations

from fichero_server.actions.page_text_cache import _sha
from fichero_server.core.background_compute import set_utility_qos
from fichero_server.execution import jobs
from fichero_server.finddocs import job
from fichero_server.finddocs.propose import PageInput, _folio, _join
from fichero_server.models import DocType, Document, FileType
from fichero_server.models.segments import PageLineMap


def _read_page(db, name: str, lines: list[str]) -> Document:
    """A page whose text was derived from its line readings: joined with spaces, its line map saying where each
    line falls (as `actions/page_text_cache` stores them)."""
    text = " ".join(lines)
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, page_content=text)
    db.save(doc)
    spans, at = [], 0
    for n, line in enumerate(lines):
        spans.append({"segment_id": f"{doc.id}-line-{n}", "char_start": at, "char_end": at + len(line)})
        at += len(line) + 1
    db.save(PageLineMap(id=doc.id, text_sha=_sha(text), lines=spans))
    return doc


def test_a_page_read_line_by_line_is_read_as_its_lines(db):
    before = _read_page(db, "13_Hoja_536_Recto.JPG", ["3", "y en la ciudad de Santa Fe", "dixo que"])
    page = _read_page(db, "14_Hoja_536_Verso.JPG", ["1", "Sepan quantos esta carta vieren", "como yo"])

    assert job._text(db, page) == "1\nSepan quantos esta carta vieren\ncomo yo"
    first, second = (PageInput(id=d.id, text=job._text(db, d)) for d in (before, page))
    assert _folio(second) == 1
    assert _join(first, second).probability >= 0.5, "the numbering restarting is a boundary"


def test_a_page_text_a_person_wrote_is_read_as_written(db):
    """No line map for this text (a person's own edit): the text as it is."""
    page = _read_page(db, "p.jpg", ["a", "b"])
    page.page_content = "Their own\ntext"
    db.save(page)

    assert job._text(db, page) == "Their own\ntext"


def test_find_the_documents_runs_at_utility_qos_whoever_waits():
    job.register_job_kinds()

    assert jobs.KINDS[job.KIND].qos is set_utility_qos
