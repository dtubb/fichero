"""What a file said survives the LIBRARY, not only the format harness (#5138).

Acceptance defects 4, 5, 6, 10 and 13 (`acceptance-2026-09-27.md`): the harness round trip passed
for some of these, because it never puts a library in the middle. Each test here imports a real
file through `format.import` (or the upload route the CLI uses), reads the rows or exports the
page, and checks against the file read with plain lxml.

What breaks without them: ALTO baselines silently gone (0 of 647 in the acceptance run),
SegmOnto block and line types gone, no way to trace a segment back to its element, a drop capital
stored as a `word`, and a PAGE export that invents regions for lines that had one.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.formats import read_page, write_page
from fichero_server.models import DocType, Document, FileType, Segment, Status
from fichero_server.page_export import page_from_library
from tests.unit.api.test_page_text_follows_the_file import CHINESE, CLM, SYRIAC, _import

CORPUS = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus"
BENEDICT = CORPUS / "escriptorium_latin-oldenglish_benedict-ctaiv-028.alto.xml"


def _elements(path: Path, name: str) -> list:
    root = etree.parse(str(path)).getroot()
    return [el for el in root.iter() if isinstance(el.tag, str) and etree.QName(el).localname == name]


def _rows(db, doc_id: str) -> list[Segment]:
    return [s for s in db.all(Segment) if s.document_id == doc_id and s.deleted_at is None]


def _tag_labels(path: Path) -> dict[str, str]:
    return {el.get("ID"): el.get("LABEL") for el in _elements(path, "OtherTag")}


def test_alto_baselines_survive_the_library_and_its_export(db):
    doc_id = _import(db, CLM)
    with_baseline = [el for el in _elements(CLM, "TextLine") if el.get("BASELINE")]
    lines = [s for s in _rows(db, doc_id) if s.kind == "line"]
    assert len(with_baseline) == len(lines) > 0
    assert all(s.baseline for s in lines), "a line lost its baseline on the way into the library"
    page, _ = page_from_library(db, doc_id)
    data, report = write_page("alto", page)
    assert data.count(b"BASELINE=") == len(with_baseline)
    assert "baseline" not in report.lost


def test_block_and_line_types_are_kept_as_the_files_own_names(db):
    """SegmOnto's `MainZone` block and Benedict's `LatinLine` lines -- as `kind_raw`, and written back."""
    labels = _tag_labels(BENEDICT)
    expected = Counter(
        labels[el.get("TAGREFS").split()[0]]
        for name in ("TextBlock", "TextLine") for el in _elements(BENEDICT, name)
        if el.get("TAGREFS") and el.get("TAGREFS").split()[0] in labels
    )
    assert {"MainZone", "LatinLine"} <= set(expected), expected
    doc_id = _import(db, BENEDICT)
    got = Counter(s.kind_raw for s in _rows(db, doc_id) if s.kind in ("region", "line") and s.kind_raw)
    assert got == expected
    page, _ = page_from_library(db, doc_id)
    data, _report = write_page("alto", page)
    back = read_page("alto", data)
    assert Counter(
        s.foreign["alto:tags"][0]["LABEL"] for s in back.segments if s.foreign.get("alto:tags")
    ) == expected


def test_every_segment_can_be_traced_to_the_element_it_came_from(db):
    doc_id = _import(db, CLM)
    source_ids = {el.get("ID") for name in ("TextBlock", "TextLine", "String") for el in _elements(CLM, name)}
    kept = {s.metadata.get("source_id") for s in _rows(db, doc_id)}
    assert source_ids <= kept


def test_a_page_export_invents_no_region_for_a_line_that_had_one(db):
    """The library's rows come back in DATABASE order; a line before its region used to get an
    invented `fichero {implicit:true;}` region (Syriac 3 became 15)."""
    doc_id = _import(db, SYRIAC)
    page, _ = page_from_library(db, doc_id)
    page.segments = list(reversed(page.segments))  # children before parents, as a database may return them
    data, _report = write_page("pagexml", page)
    assert data.count(b"implicit") == 0
    assert data.count(b"<TextRegion") == len(_elements(SYRIAC, "TextRegion"))


YOLO_LABELS = b"0 0.5 0.1 0.8 0.1\n2 0.1 0.3 0.1 0.1\n1 0.5 0.5 0.8 0.05\n"
CLASSES = b"MainZone\nDefaultLine\nDropCapitalZone\n"


def test_a_one_file_yolo_upload_uses_the_datasets_class_names(db, client):
    """The CLI's `import page` uploads the labels; the class file used to stay behind, so class 2
    (a drop capital) was stored as a `word` and its name nowhere."""
    doc = Document(name="000.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/000.jpg", status=Status.completed)
    db.save(doc)
    response = client.post(
        f"/api/documents/{doc.id}/import",
        params={"format": "yolo"},
        files={"file": ("000.txt", YOLO_LABELS, "text/plain"),
               "dataset": ("classes.txt", CLASSES, "text/plain")},
    )
    assert response.status_code == 200, response.text
    rows = _rows(db, doc.id)
    assert sorted(s.kind_raw for s in rows) == ["DefaultLine", "DropCapitalZone", "MainZone"]
    assert {s.kind_raw: s.kind for s in rows}["DropCapitalZone"] == "region"


def test_a_dataset_file_by_any_other_name_is_refused(db, client):
    doc = Document(name="001.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/001.jpg", status=Status.completed)
    db.save(doc)
    response = client.post(
        f"/api/documents/{doc.id}/import",
        params={"format": "yolo"},
        files={"file": ("000.txt", YOLO_LABELS, "text/plain"),
               "dataset": ("labels.csv", CLASSES, "text/plain")},
    )
    assert response.status_code == 422
    assert "classes.txt" in response.json()["detail"]


def test_an_upload_never_takes_class_names_from_a_file_it_did_not_send(db, client, tmp_path, monkeypatch):
    """SECURITY. An upload is spooled into a temp folder the ENGINE made; the folders above it are
    the engine's. The lookup used to walk two folders up, so a `data.yaml` somebody left or
    planted in the engine's temp directory named the classes of another person's upload -- on a
    shared engine, across users. Here one is planted one level above the upload's folder."""
    import tempfile

    engine_tmp = tmp_path / "engine-tmp"
    engine_tmp.mkdir()
    (engine_tmp / "data.yaml").write_text("names: [Planted0, Planted1, Planted2]\n", encoding="utf-8")
    monkeypatch.setattr(tempfile, "tempdir", str(engine_tmp))
    doc = Document(name="002.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/002.jpg", status=Status.completed)
    db.save(doc)
    response = client.post(
        f"/api/documents/{doc.id}/import",
        params={"format": "yolo"},
        files={"file": ("000.txt", YOLO_LABELS, "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert not any((s.kind_raw or "").startswith("Planted") for s in _rows(db, doc.id))
    assert response.json()["unknown_classes"] == [0, 1, 2]


def test_a_folder_import_still_finds_a_data_yaml_above_its_labels(db, tmp_path):
    """The other half: a FOLDER import's folders are the person's input, so walking up stays."""
    from fichero_server.actions.registry import ActionContext, registry

    (tmp_path / "data.yaml").write_text("names: [MainZone, DefaultLine, DropCapitalZone]\n", encoding="utf-8")
    labels = tmp_path / "labels" / "train" / "000.txt"
    labels.parent.mkdir(parents=True)
    labels.write_bytes(YOLO_LABELS)
    doc = Document(name="003.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/p/003.jpg", status=Status.completed)
    db.save(doc)
    result = registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(labels), "format": "yolo"},
                             ActionContext(actor="historian", is_bootstrap=True)).result
    assert result["unknown_classes"] == []
    assert "DropCapitalZone" in {s.kind_raw for s in _rows(db, doc.id)}


def test_the_imported_order_lists_every_line_under_its_block_in_file_order(db):
    """Q5, lines move in the Reader's text: a LINE can only be moved if the order has an entry for
    it. An import's as-written order used to hold the file's blocks alone; now every segment is in
    it, nested as the file nests it, in the file's order (`file_position`)."""
    from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry

    doc_id = _import(db, CLM)
    rows = {s.id: s for s in _rows(db, doc_id)}
    [order] = [o for o in db.all(ReadingOrder) if o.document_id == doc_id]
    entries = [e for e in db.all(ReadingOrderEntry) if e.order_id == order.id]
    assert {e.segment_id for e in entries} == set(rows)
    by_segment = {e.segment_id: e for e in entries}
    for entry in entries:
        segment = rows[entry.segment_id]
        parent = by_segment.get(segment.parent_segment_id) if segment.parent_segment_id else None
        assert entry.parent_entry_id == (parent.id if parent else None)
    lines = sorted((by_segment[s.id] for s in rows.values() if s.kind == "line"), key=lambda e: e.position)
    assert [rows[e.segment_id].metadata["file_position"] for e in lines] == sorted(
        rows[e.segment_id].metadata["file_position"] for e in lines
    )


CHEROKEE = Path(
    "/Users/danieltubb/Fichero Test Corpus/Cherokee and English - Cherokee Phoenix newspaper, 1828 "
    "(ALTO 2, inch1200)/cherokee-phoenix_1828030601_0002.xml"
)


@pytest.mark.parametrize("path", [CLM, CHINESE, CHEROKEE], ids=["clm-38r", "chinese-vertical", "cherokee-p2"])
def test_the_as_written_order_walks_the_page_exactly_as_file_position_does(db, path):
    """The order and the text must be one sequence: walking the as-written order (depth first, each
    level by position) visits the segments in exactly `file_position` order, on a two-column page, a
    vertical page and the densest real page. The Cherokee Phoenix p. 2 is the local corpus's (public
    domain, not vendored), so it runs where that folder exists."""
    if not path.exists():
        pytest.skip(f"{path.name} is in the local corpus only")
    from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry

    doc_id = _import(db, path)
    rows = {s.id: s for s in _rows(db, doc_id)}
    [order] = [o for o in db.all(ReadingOrder) if o.document_id == doc_id]
    children: dict[str | None, list] = {}
    for entry in (e for e in db.all(ReadingOrderEntry) if e.order_id == order.id):
        children.setdefault(entry.parent_entry_id, []).append(entry)
    walked: list[str] = []

    def walk(parent_id):
        for entry in sorted(children.get(parent_id, []), key=lambda e: e.position):
            walked.append(entry.segment_id)
            walk(entry.id)

    walk(None)
    assert len(walked) == len(rows)
    assert walked == sorted(rows, key=lambda sid: rows[sid].metadata["file_position"])


def test_a_page_export_s_reading_order_still_names_only_its_regions(db):
    """The nested entries must not leak into a format's reading order, which is of blocks."""
    doc_id = _import(db, SYRIAC)
    page, _choices = page_from_library(db, doc_id)
    data, _report = write_page("pagexml", page)
    assert data.count(b"RegionRefIndexed") == len(_elements(SYRIAC, "RegionRefIndexed"))
