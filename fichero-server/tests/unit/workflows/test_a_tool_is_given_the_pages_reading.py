"""A vision tool is given the page's own reading and boxes with the picture (#5026, slice 1).

WHY: Extract Table sent the model one downscaled image and a prompt, even when the page already
had a corrected reading and every line's box on screen beside it -- so the model re-misread
handwriting a person had fixed, and guessed a table's columns from pixels when the x positions of
the lines already said where they are. Ruled 2026-09-26: a tool is given SOME SEGMENTS (a page, a
region, a line), the text is the working pass's counting reading in reading order marked by its
maker, and it says how much it sends -- or that there is nothing and it works from the picture.
If this regresses, a tool works from pixels alone again, or reads a machine line where a person's
correction counts.

On the real Vienna Syriac folio (CC-BY-SA), imported through `format.import`; what the file says is
read with plain lxml.
"""

from __future__ import annotations

import asyncio

from lxml import etree

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import ContentRepresentation, DocType, Document, Segment
from fichero_server.tool_context import tool_context, with_page_context
from tests.fixture_paths import sample_file
from tests.unit.api.test_reader_directions import SYRIAC, _import

NS = "{*}"


def _file_lines():
    """(region box, line box, line text) for every TextLine with text, in file order, by lxml."""
    root = etree.parse(str(SYRIAC)).getroot()
    page = root.find(f"{NS}Page")
    width, height = float(page.get("imageWidth")), float(page.get("imageHeight"))

    def box(element):
        points = [tuple(map(float, p.split(","))) for p in element.find(f"{NS}Coords").get("points").split()]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        return (min(xs) / width, min(ys) / height, (max(xs) - min(xs)) / width, (max(ys) - min(ys)) / height)

    out = []
    for region in page.iter(f"{NS}TextRegion"):
        for line in region.iter(f"{NS}TextLine"):
            own = line.find(f"{NS}TextEquiv/{NS}Unicode")
            text = "".join(own.itertext()) if own is not None else ""
            if text.strip():
                out.append((box(region), box(line), text))
    return out


def _parse(context_text: str):
    return [tuple(part.strip() if i < 3 else part for i, part in enumerate(row.split(" | ", 3)))
            for row in context_text.splitlines()]


def _close(a, b, tol=0.002):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_the_whole_page_is_every_line_with_its_box_and_maker(db):
    doc_id = _import(db, SYRIAC)
    expected = _file_lines()
    got = tool_context(db, doc_id)
    rows = _parse(got.text)
    assert sorted(text for _r, _l, text in expected) == sorted(row[3] for row in rows)   # every line, nothing else
    for segment_id, box, maker, text in rows:
        line_box = next(lb for _r, lb, t in expected if t == text)
        assert _close(tuple(map(float, box.split())), line_box), (text, box, line_box)   # the file's own box
        assert maker == "file" and segment_id == db.get(Segment, segment_id).id
    assert got.statement.startswith(f"{len(expected)} line(s) of the page")


def test_a_region_brings_only_the_lines_inside_it(db):
    doc_id = _import(db, SYRIAC)
    expected = _file_lines()
    regions = [s for s in db.query(Segment, document_id=doc_id) if s.kind == "region"]
    region_box, _lb, _t = expected[0]
    region = next(r for r in regions if _close((r.bbox_x, r.bbox_y, r.bbox_w, r.bbox_h), region_box))
    got = _parse(tool_context(db, doc_id, [region.id]).text)
    assert [row[3] for row in got] == [t for rb, _lb, t in expected if rb == region_box]


def test_a_persons_correction_is_what_the_tool_reads_and_is_marked_as_a_persons(client, db):
    doc_id = _import(db, SYRIAC)
    first_id, _box, _maker, first_text = _parse(tool_context(db, doc_id).text)[0]
    counted = next(r for r in db.query(ContentRepresentation, segment_id=first_id))
    made = client.post("/api/actions/invoke", json={"name": "representation.create", "params": {
        "document_id": doc_id, "segment_id": first_id, "kind": "transcription",
        "content": first_text + " (corrected)", "corrects_representation_id": counted.id}})
    assert made.status_code == 200, made.text
    row = next(r for r in _parse(tool_context(db, doc_id).text) if r[0] == first_id)
    assert (row[2], row[3]) == ("person", first_text + " (corrected)")


def test_a_page_with_no_reading_says_the_tool_works_from_the_picture(db):
    page = Document(name="blank", doc_type=DocType.file)
    db.save(page)
    got = tool_context(db, page.id)
    assert got.segment_ids == [] and got.statement == "no reading on the page yet: the tool works from the picture alone"


def test_extract_table_sends_the_lines_with_the_picture(db, test_package, monkeypatch):
    """Through the tool itself: what reaches the model's prompt is the page's lines."""
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.table_extract import table_extract

    doc_id = _import(db, SYRIAC)
    image = str(sample_file("sample.jpg"))
    prompts: list[str] = []

    async def seen_by_the_model(images, prompt, config, **kwargs):
        prompts.append(prompt)
        return "a,b\n1,2"

    monkeypatch.setattr("fichero_server.llm.vision", seen_by_the_model)
    result = asyncio.run(table_extract(
        {"files": [image], "documents": [{"id": doc_id, "name": "folio", "path": image}], "save_to_db": False},
        {"library_path": str(test_package)}, LLMConfig(provider="mock", model="mock")))
    assert not result.get("error"), result
    [prompt] = prompts
    for _r, _lb, text in _file_lines():
        assert f"| file | {text}" in prompt
    assert "line(s) of the page" in prompt


def test_with_nothing_to_look_up_the_context_is_left_as_it_was():
    assert with_page_context("wired", [], ["x.jpg"], "") == "wired"


def test_a_machine_reading_is_marked_machine_though_a_person_started_the_run(db):
    """The maker is the SERVER-SET `provenance_kind`, not `created_by`: a reading a workflow wrote
    carries the name of the person who started the run in `created_by`, so reading the maker from
    it would pass a machine's line off as a person's -- the #4868/#4869 defect. A reading written
    inside a run is `workflow`, and the tool is told `machine`."""
    from fichero_server.actions.registry import ActionContext, registry

    doc_id = _import(db, SYRIAC)
    first_id, _box, _maker, first_text = _parse(tool_context(db, doc_id).text)[0]
    imported = next(r for r in db.query(ContentRepresentation, segment_id=first_id))
    run = ActionContext(actor="daniel", run_id="run-htr-1", is_bootstrap=True)
    made = registry.invoke(db, "representation.create", {
        "document_id": doc_id, "segment_id": first_id, "kind": "transcription",
        "content": first_text + " (machine)", "corrects_representation_id": imported.id}, run)
    written = db.get(ContentRepresentation, made.result["id"])
    assert (written.created_by, getattr(written.provenance_kind, "value", None)) == ("daniel", "workflow")
    row = next(r for r in _parse(tool_context(db, doc_id).text) if r[0] == first_id)
    assert (row[2], row[3]) == ("machine", first_text + " (machine)")   # read, and marked a machine's
    from fichero_server.tool_context import _maker
    assert _maker(written) == "machine"


def test_a_reading_that_never_recorded_its_maker_is_never_called_a_persons():
    """Rows written before provenance was recorded: a tool or model named means machine; nothing
    at all means `unrecorded` -- never a trusting `person`."""
    from types import SimpleNamespace

    from fichero_server.tool_context import _maker

    assert _maker(SimpleNamespace(provenance_kind=None, producer_tool="transcribe", producer_model=None)) == "machine"
    assert _maker(SimpleNamespace(provenance_kind=None, producer_tool=None, producer_model=None)) == "unrecorded"
    assert _maker(SimpleNamespace(provenance_kind="unknown", producer_tool=None, producer_model=None)) == "unrecorded"
