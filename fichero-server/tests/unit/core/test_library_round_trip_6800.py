"""A library page exported, imported into a fresh page and read out of the library again differs only
in what the first export's loss report named (#6800, `source.format.undeclared-losses-are-declared`,
`source.format.round-trip-through-a-library`).

WHY: the format-to-format round trips passed while ALTO dropped every editorial fact and every name
and date with nothing said, because a reader fills the same hole its writer left; only a page that
goes through a library shows it. The page is the record-export page (three lines imported from PAGE
XML, a person, a place and a date standing on them) with a `deleted` and an `unclear` fact on its
first line, as in `test_export_names_what_it_drops_6800`.

Compared: the segments' kinds in order, the text of the reading written first, each outline, box and
baseline to a pixel, the editorial facts and the names and dates on each line. Who made each reading
is not compared (#6802). TEI's names are not compared: a TEI re-import makes no mentions (the reader
keeps only the tag names, in `foreign["tei-inline"]`), and whether that is a loss the export must
name is not settled.
"""

from __future__ import annotations

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.formats import write_page
from fichero_server.formats.tei import EDITORIAL_FACTS, RECORD_MARKS
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.page_export import page_from_library
from tests.unit.core.test_export_names_what_it_drops_6800 import NAMES, page  # noqa: F401  (fixture)
from tests.unit.core.test_export_reads_the_record import library  # noqa: F401  (fixture)

pytestmark = pytest.mark.source_model

BOOT = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
SUFFIX = {"alto": "alto.xml", "pagexml": "page.xml", "tei": "tei.xml"}
#: The page records no size, so every writer places it on a 1000x1000 grid (and names "page size"):
#: one pixel of the file is a thousandth of the page.
PIXEL = 1 / 1000


def _near(a, b) -> bool:
    if a is None or b is None:
        return a is b
    flat_a = [v for p in a for v in (p if isinstance(p, list) else [p])]
    flat_b = [v for p in b for v in (p if isinstance(p, list) else [p])]
    return len(flat_a) == len(flat_b) and all(abs(x - y) <= PIXEL for x, y in zip(flat_a, flat_b))


def _differences(sent, back, lost: set[str], names: bool) -> list[str]:
    out = []
    if [s.kind for s in sent.segments] != [s.kind for s in back.segments]:
        return [f"segments: {[s.kind for s in sent.segments]} became {[s.kind for s in back.segments]}"]
    for i, (a, b) in enumerate(zip(sent.segments, back.segments)):
        where = f"{a.kind} {i}"
        if a.readings[:1] != b.readings[:1]:
            out.append(f"{where} text: {a.readings[:1]} became {b.readings[:1]}")
        for what in ("rect", "polygon", "baseline"):
            if not _near(getattr(a, what), getattr(b, what)):
                out.append(f"{where} {what}: {getattr(a, what)} became {getattr(b, what)}")
        facts = [(f["kind"], f["start"], f["end"]) for f in a.foreign.get(EDITORIAL_FACTS) or []
                 if f"a '{f['kind']}' editorial mark" not in lost]
        came = [(f["kind"], f["start"], f["end"]) for f in b.foreign.get(EDITORIAL_FACTS) or []]
        if facts != came:
            out.append(f"{where} editorial facts: {facts} became {came}")
        if names and NAMES not in lost:
            marks = [(m["kind"], m["start"], m["end"]) for m in a.foreign.get(RECORD_MARKS) or []]
            came = [(m["kind"], m["start"], m["end"]) for m in b.foreign.get(RECORD_MARKS) or []]
            if marks != came:
                out.append(f"{where} names and dates: {marks} became {came}")
    return out


@pytest.mark.parametrize("name", ["alto", "pagexml", "tei"])
def test_a_library_page_comes_back_less_only_what_its_export_named(db, page, library, tmp_path, name):  # noqa: F811
    data, report = write_page(name, page)
    assert "page size" in report.lost, report.as_dict()   # the grid PIXEL is measured on
    path = tmp_path / f"acta.{SUFFIX[name]}"
    path.write_bytes(data)
    fresh = Document(name="acta.jpg", doc_type=DocType.file, file_type=FileType.image,
                     path=library["doc"].path, status=Status.completed)
    db.save(fresh)
    registry.invoke(db, "format.import", {"document_id": fresh.id, "path": str(path)}, BOOT)
    back, _ = page_from_library(db, fresh.id)
    assert _differences(page, back, report.lost, names=name != "tei") == [], report.as_dict()
