"""One line pass per page, read many times (`source.model.one-line-pass`, #5487; ruled 2026-10-05, #5467).

Spec (source/source-model.md, "Every output comes into the page"): "Finding lines makes the pass;
reading, correcting and checking add readings to its segments; they never make a second line pass", and
Kraken's regions are kept as the lines' parents.

WHY: a reader that found its own lines on every run left a page with parallel flat line passes, each
with a slice of the page's words, and Kraken's regions thrown away; the Source view, the Segments list
and the export then disagreed about which lines the page has.

Driven through the real Transcribe tool (the `read-a-line` and `find-lines` paths of
`vision_base.process_vision`), the real conversion and the real readings. Only Kraken's segmenter and
reader (`kraken_runtime.segment_lines`, `read_given_lines`) and the vision model's answers are faked.
"""
from __future__ import annotations

import pytest

from fichero_server.db.manager import db_manager

WIDTH, HEIGHT = 400, 300
TEACHER = ("openrouter", "google/gemini-3-flash-preview")


def _poly(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


#: What Kraken's segmenter gives for the page: one text region holding two lines, and a third line in no region.
FOUND = {
    "width": WIDTH, "height": HEIGHT,
    "regions": [{"id": "r1", "type": "text", "polygon": _poly(10, 10, 390, 130)}],
    "lines": [
        {"baseline": [[20, 50], [380, 50]], "polygon": _poly(20, 20, 380, 60), "region": "r1"},
        {"baseline": [[20, 110], [380, 110]], "polygon": _poly(20, 80, 380, 120), "region": "r1"},
        {"baseline": [[20, 250], [380, 250]], "polygon": _poly(20, 220, 380, 260), "region": None},
    ],
}


@pytest.fixture
def page(test_package, tmp_path, monkeypatch):
    from PIL import Image

    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.models import DocType, Document, FileType

    library = str(test_package)
    db = db_manager.get_database(library)
    path = tmp_path / "SM_NPQ_C01_030.png"
    Image.new("RGB", (WIDTH, HEIGHT), "white").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    found = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **kw: found.append(1) or FOUND)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/mccatmus.mlmodel", ref))
    return {"library": library, "db": db, "doc": doc, "found": found}


async def _transcribe(page, **inputs):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    library, doc = page["library"], page["doc"]
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=LLMConfig(provider="", model=""))
    result = await transcribe(
        inputs={"files": src["files"], "documents": src["documents"], "vision_mode": "kraken",
                "regions_first": False, **inputs},
        state={"library_path": library, "task_id": None}, llm_config=LLMConfig(provider=TEACHER[0], model=TEACHER[1]))
    assert not result.get("error"), result.get("error")
    return result


def _passes(page):
    from fichero_server.models.segments import SegmentPass

    return [p for p in page["db"].query(SegmentPass, document_id=page["doc"].id) if p.deleted_at is None]


def _lines(page, pass_id):
    from fichero_server.api.routes.document.segment_readings import ordered_lines

    return ordered_lines(page["db"], pass_id)


def _counting(page, rows):
    from fichero_server.api.routes.document.segment_readings import counting_texts

    texts = counting_texts(page["db"], rows)
    return [texts.get(row.id, "") for row in rows]


def _kraken_reads(monkeypatch, texts):
    import fichero_server.llm.kraken_runtime as kraken_runtime

    seen = {}

    def read(image_path, model_path, lines, **kw):
        seen["lines"] = list(lines)
        return list(texts)

    monkeypatch.setattr(kraken_runtime, "read_given_lines", read)
    return seen


@pytest.mark.asyncio
async def test_finding_lines_keeps_krakens_regions_as_the_lines_parents(page):
    """source-model.md: "keep the regions a model found"; #5487: `detect_regions` threw Kraken's regions away.
    WHY: a line's region is where its column, its language and its reading order live; a flat list of lines
    loses which lines belong together."""
    from fichero_server.models import Segment

    await _transcribe(page)
    (made,) = _passes(page)
    rows = [s for s in page["db"].query(Segment, pass_id=made.id) if s.deleted_at is None]
    (region,) = [s for s in rows if s.kind == "region"]
    lines = _lines(page, made.id)
    assert len(lines) == 3
    assert [line.parent_segment_id for line in lines] == [region.id, region.id, None]
    assert region.kind_raw == "text"


@pytest.mark.asyncio
async def test_a_kraken_reader_reads_the_pages_lines_and_never_makes_a_second_pass(page, monkeypatch):
    """#5487: "Re-running a reader adds readings, never another line pass."
    WHY: every reader's words must land on the one set of lines the page has, so the Source view, the
    Segments list and the export read one page; a second run is a second reading of the same lines."""
    await _transcribe(page)
    (lines_pass,) = _passes(page)
    lines = _lines(page, lines_pass.id)
    assert page["found"] == [1]

    seen = _kraken_reads(monkeypatch, ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"])
    await _transcribe(page, kraken_model="kraken-mccatmus")
    assert [p.id for p in _passes(page)] == [lines_pass.id]  # no second line pass
    assert page["found"] == [1]  # the lines were not found again
    # Kraken read the pass's own lines, on their own baselines, in the page's pixels.
    assert [line["id"] for line in seen["lines"]] == [row.id for row in lines]
    assert [pt for point in seen["lines"][0]["baseline"] for pt in point] == pytest.approx([20, 50, 380, 50])
    assert _counting(page, lines) == ["el dicho escrivano", "vezino de la ciudad", "y lo firmo"]

    _kraken_reads(monkeypatch, ["El dicho escribano", "vecino de la ciudad", ""])
    await _transcribe(page, kraken_model="kraken-mccatmus")
    assert [p.id for p in _passes(page)] == [lines_pass.id]
    # The newer machine reading counts; the older one stays as history; a line read as nothing keeps its words.
    assert _counting(page, lines) == ["El dicho escribano", "vecino de la ciudad", "y lo firmo"]
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    first = readings_of_segment(page["db"], lines[0].id)
    assert sorted(r.content for r in first) == ["El dicho escribano", "el dicho escrivano"]
    assert {getattr(r.provenance_kind, "value", r.provenance_kind) for r in first} == {"workflow"}


@pytest.mark.asyncio
async def test_the_readings_name_their_reader_and_the_page_text_is_kept(page, monkeypatch):
    """WHY: a reading must say who read it (its page artifact's provider and model), and the run's page
    text is still the page's transcription; the artifact holds no second copy of the lines."""
    from fichero_server.api.routes.document.segment_readings import readings_of_segment
    from fichero_server.llm.working_lines import READ_ONTO_PASS
    from fichero_server.models import Artifact

    await _transcribe(page)
    (lines_pass,) = _passes(page)
    _kraken_reads(monkeypatch, ["uno", "dos", "tres"])
    await _transcribe(page, kraken_model="kraken-mccatmus")
    (art,) = [a for a in page["db"].query(Artifact, document_id=page["doc"].id) if a.content == "uno\ndos\ntres"]
    assert art.ocr_geometry is None and art.data[READ_ONTO_PASS] == lines_pass.id
    assert (art.provider, art.model) == ("kraken", "kraken-mccatmus")
    for row in _lines(page, lines_pass.id):
        (reading,) = readings_of_segment(page["db"], row.id)
        assert reading.derived_from_artifact_id == art.id


@pytest.mark.asyncio
async def test_a_vision_model_reads_the_pages_lines_too(page, monkeypatch):
    """#5487: `llm/line_reader.read_lines` read lines it had just found; now it reads the page's own.
    WHY: the teacher's words for each line must sit on the same lines Kraken's reader and a person read."""
    import fichero_server.llm as llm

    await _transcribe(page)
    (lines_pass,) = _passes(page)

    async def teacher(images, prompt, config, **_):
        return '["primera", null, "tercera"]' if len(images) == 3 else "[" + ", ".join(['"x"'] * len(images)) + "]"

    monkeypatch.setattr(llm, "vision", teacher)
    await _transcribe(page, lines_read_by="model")
    assert [p.id for p in _passes(page)] == [lines_pass.id]
    assert page["found"] == [1]
    assert _counting(page, _lines(page, lines_pass.id)) == ["primera", "", "tercera"]


@pytest.mark.asyncio
async def test_a_page_with_no_lines_finds_them_once_and_reads_them(page, monkeypatch):
    """#5487: "finding lines only when the page has none".
    WHY: the first reader of a bare page has to find its lines; that pass is then the page's one pass."""
    import fichero_server.llm.kraken_runtime as kraken_runtime

    payload = {**FOUND, "lines": [{**line, "text": t} for line, t in zip(FOUND["lines"], ["a", "b", "c"])]}
    monkeypatch.setattr(kraken_runtime, "recognize_lines", lambda image_path, model_path, **kw: payload)
    await _transcribe(page, kraken_model="kraken-mccatmus")
    (made,) = _passes(page)
    lines = _lines(page, made.id)
    assert _counting(page, lines) == ["a", "b", "c"]
    assert lines[0].parent_segment_id is not None

    _kraken_reads(monkeypatch, ["A", "B", "C"])
    await _transcribe(page, kraken_model="kraken-mccatmus")
    assert [p.id for p in _passes(page)] == [made.id]
    assert _counting(page, lines) == ["A", "B", "C"]
