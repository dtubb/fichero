"""Once a page has lines, every reader's output ties to a line (`source.read.once-lines-exist-every-reading-ties-to-a-line`, #5721).

Spec: run Apple Vision, then a stub vision model, on a page with three lines: each pass has three readings tied to the
three segments. Page-level text with no line under it is never the step's result when lines exist, and the step says so
when it could only produce that.
WHY (2026-10-16, page 39_Hoja_549_Recto.JPG): Kraken's pass held 44 lines; the Apple Vision pass and the Qwen pass each
held the whole page as text with 0 segments.
Driven through the real Transcribe tool on the page Kraken found and read (the harness of the review tests); only the
vision call is a stub.
"""
from __future__ import annotations

import json

import pytest

from fichero_server.db.manager import db_manager
from tests.unit.workflows.test_review_corrects_the_lines_5654 import (  # noqa: F401
    _lines,
    _readings,
    page,
)

MODEL = ("mlx", "mlx-community/Qwen2.5-VL-3B-Instruct-4bit")


def _passes(pg):
    from fichero_server.models.segments import SegmentPass

    return [p for p in pg["db"].query(SegmentPass, document_id=pg["doc"].id) if p.deleted_at is None]


async def _read(pg, monkeypatch, *, provider, model, answer, **extra):
    """Transcribe the page with `provider`; `answer(n_images, call)` is what the stub vision call returns."""
    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.transcribe import transcribe

    calls = []

    async def vision(images, prompt, config, **kw):
        calls.append(len(images))
        shown = len(images) - (1 if str(prompt).startswith("Before the ") else 0)  # variant B: the page comes first, unread
        return answer(shown, len(calls))

    monkeypatch.setattr(llm, "vision", vision)
    result = await transcribe(
        inputs={"files": pg["src"]["files"], "documents": pg["src"]["documents"], "regions_first": False,
                **extra},
        state={"library_path": pg["library"], "task_id": f"run-{provider}"},
        llm_config=LLMConfig(provider=provider, model=model))
    assert not result.get("error"), result.get("error")
    result["calls"] = calls
    return result


def _tied(pg, words):
    """Per line: the readings whose text is one of `words`."""
    return [[r.content for r in _readings(pg, row) if r.content in words] for row in _lines(pg)]


@pytest.mark.asyncio
async def test_apple_vision_on_a_page_with_lines_reads_each_line_and_makes_no_second_pass_5721(page, monkeypatch):  # noqa: F811
    before = [p.id for p in _passes(page)]
    words = ["apple uno", "apple dos", "apple tres"]
    result = await _read(page, monkeypatch, provider="apple", model="apple-vision", force_ocr=True,
                         answer=lambda n, call: words[call - 1])
    assert result["calls"] == [1, 1, 1]  # one picture per line, not the page
    assert _tied(page, words) == [[w] for w in words]
    assert [p.id for p in _passes(page)] == before


@pytest.mark.asyncio
async def test_a_vision_model_on_a_page_with_lines_is_shown_each_line_and_its_words_land_on_them_5721(page, monkeypatch):  # noqa: F811
    before = [p.id for p in _passes(page)]
    words = ["qwen uno", "qwen dos", "qwen tres"]
    result = await _read(page, monkeypatch, provider=MODEL[0], model=MODEL[1], vision_mode="llm", force_ocr=True,
                         answer=lambda n, call: json.dumps(words[:n]))
    # three line pictures in one call, none twice; the whole page does not ride unless asked (`source.recipe.cloud-reads-lines-per-page`,
    # measured 2026-10-24: it made an answer come back out of order and cost twice as much)
    assert result["calls"] == [len(words)] and max(result["calls"]) <= 9
    assert _tied(page, words) == [[w] for w in words]
    assert [p.id for p in _passes(page)] == before


@pytest.mark.asyncio
async def test_an_auto_reader_on_a_page_with_lines_ties_to_them_whichever_it_resolves_to_5721(page, monkeypatch):  # noqa: F811
    words = ["auto uno", "auto dos", "auto tres"]
    await _read(page, monkeypatch, provider="apple", model="apple-vision", vision_mode="auto", force_ocr=True,
                answer=lambda n, call: words[call - 1])
    assert _tied(page, words) == [[w] for w in words]


@pytest.mark.asyncio
async def test_a_reader_never_replaces_the_text_of_a_page_that_has_lines_5721(page, monkeypatch):  # noqa: F811
    from fichero_server.models import Document

    kept = page["db"].get(Document, page["doc"].id).page_content
    assert kept
    await _read(page, monkeypatch, provider="apple", model="apple-vision", force_ocr=True,
                answer=lambda n, call: f"otro {call}")
    assert page["db"].get(Document, page["doc"].id).page_content != "otro 1"


@pytest.mark.asyncio
async def test_a_page_that_has_text_and_no_instruction_to_read_again_is_not_read_5721(page, monkeypatch):  # noqa: F811
    """What a Transcribe did before stays: without `force_ocr` a page that has text is passed through, so the
    reader is not asked."""
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool

    fresh = await files_tool(inputs={}, state={"selected_doc_ids": [page["doc"].id], "library_path": page["library"]},
                             llm_config=LLMConfig(provider="", model=""))  # the page as the sources step now hands it on
    result = await _read({**page, "src": fresh}, monkeypatch, provider="apple", model="apple-vision",
                         answer=lambda n, call: "x")
    assert result["calls"] == []


@pytest.mark.asyncio
async def test_a_page_with_no_lines_read_by_a_model_says_its_text_is_tied_to_no_line_5721(page, monkeypatch, tmp_path):  # noqa: F811
    from PIL import Image

    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.tools.sources import files_tool

    path = tmp_path / "sin_lineas.png"
    Image.new("RGB", (400, 300), "white").save(path)
    bare = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db_manager.get_database(page["library"]).save(bare)
    src = await files_tool(inputs={}, state={"selected_doc_ids": [bare.id], "library_path": page["library"]},
                           llm_config=LLMConfig(provider="", model=""))
    bare_page = {**page, "doc": bare, "src": src}
    result = await _read(bare_page, monkeypatch, provider=MODEL[0], model=MODEL[1], vision_mode="llm",
                         force_ocr=True, answer=lambda n, call: "todo el texto de la pagina")
    assert any("tied to no line" in note and "sin_lineas.png" in note for note in result.get("notes", []))


async def _second_page_with_lines(pg, tmp_path):
    """A black page, its lines found and read by Kraken like the first, in the same library."""
    from PIL import Image

    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    path = tmp_path / "testamento_p2.png"
    Image.new("RGB", (400, 300), "black").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    pg["db"].save(doc)
    src = await files_tool(inputs={}, state={"selected_doc_ids": [pg["doc"].id, doc.id], "library_path": pg["library"]},
                           llm_config=LLMConfig(provider="", model=""))
    for extra in ({}, {"kraken_model": "kraken-mccatmus"}):
        done = await transcribe(
            inputs={"files": src["files"], "documents": src["documents"], "vision_mode": "kraken",
                    "regions_first": False, **extra},
            state={"library_path": pg["library"], "task_id": None}, llm_config=LLMConfig(provider="", model=""))
        assert not done.get("error"), done.get("error")
    return doc, src


@pytest.mark.asyncio
async def test_a_page_whose_lines_came_back_empty_keeps_its_page_text_in_a_run_of_several_pages_5721(  # noqa: F811
        page, monkeypatch, tmp_path):
    """Two pages, both with lines: the model answers line by line on the white page and in prose on the black one.
    The black page is read whole (its text kept, for the tie); the white page keeps its lines' readings."""
    import base64
    import io

    from PIL import Image

    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Artifact
    from fichero_server.workflows.tools.transcribe import transcribe

    black, src = await _second_page_with_lines(page, tmp_path)

    async def vision(images, prompt, config, **kw):
        if prompt == "PAGE":
            return "texto de la pagina negra"
        first = images[0] if isinstance(images[0], str) else ""
        data = base64.b64decode(first.split(",", 1)[-1])
        dark = Image.open(io.BytesIO(data)).convert("RGB").getpixel((0, 0))[0] < 128
        return "prosa sin json" if dark else json.dumps(["blanca uno", "blanca dos", "blanca tres"][: len(images)])

    monkeypatch.setattr(llm, "vision", vision)
    before = {a.id for a in page["db"].query(Artifact, document_id=black.id)}
    result = await transcribe(
        inputs={"files": src["files"], "documents": src["documents"], "regions_first": False,
                "vision_mode": "llm", "force_ocr": True, "prompt": "PAGE"},
        state={"library_path": page["library"], "task_id": "run-multi"},
        llm_config=LLMConfig(provider=MODEL[0], model=MODEL[1]))
    assert not result.get("error"), result.get("error")
    assert _tied(page, ["blanca uno", "blanca dos", "blanca tres"]) == [["blanca uno"], ["blanca dos"], ["blanca tres"]]
    by_file = {r["file"].rsplit("/", 1)[-1]: r["text"] for r in result["results"]}
    assert by_file["testamento_p2.png"] == "texto de la pagina negra"
    made = [a for a in page["db"].query(Artifact, document_id=black.id)
            if a.artifact_type == "transcription" and a.id not in before]
    assert len(made) == 1, "the failed line pass leaves no empty transcription behind the page-level one"
    assert (made[0].content or "").strip() == "texto de la pagina negra"
    assert all(page["db"].get(Artifact, a) is not None for a in result["artifacts"]), "no deleted id is handed on"
    notes = result.get("notes", [])
    assert any("testamento_p2.png" in n and "did not read line by line" in n for n in notes), notes


@pytest.mark.asyncio
async def test_a_run_where_only_some_pages_have_lines_reads_every_page_whole_and_says_which_has_no_lines_5721(  # noqa: F811
        page, monkeypatch, tmp_path):
    """source.read.once-lines-exist-every-reading-ties-to-a-line, owed: "a run of several pages where only some have
    lines reads them page-level". One page has lines, one has none: both are read as pages (no line call), each keeps its
    text, and the note names the page that has no line."""
    from PIL import Image

    from fichero_server import llm
    from fichero_server.llm import LLMConfig
    from fichero_server.models import Artifact, DocType, Document, FileType
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    path = tmp_path / "sin_lineas.png"
    Image.new("RGB", (400, 300), "white").save(path)
    bare = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    page["db"].save(bare)
    src = await files_tool(inputs={}, state={"selected_doc_ids": [page["doc"].id, bare.id], "library_path": page["library"]},
                           llm_config=LLMConfig(provider="", model=""))
    prompts = []

    async def vision(images, prompt, config, **kw):
        prompts.append(prompt)
        return "texto de la pagina"

    monkeypatch.setattr(llm, "vision", vision)
    result = await transcribe(
        inputs={"files": src["files"], "documents": src["documents"], "regions_first": False,
                "vision_mode": "llm", "force_ocr": True, "prompt": "PAGE"},
        state={"library_path": page["library"], "task_id": "run-mixed"},
        llm_config=LLMConfig(provider=MODEL[0], model=MODEL[1]))
    assert not result.get("error"), result.get("error")
    assert prompts == ["PAGE", "PAGE"], "every page is read whole, none line by line"
    assert [r["text"] for r in result["results"]] == ["texto de la pagina"] * 2
    assert any("sin_lineas.png" in n and "tied to no line" in n for n in result.get("notes", []))
    assert not any("read each of the page's lines" in n for n in result.get("notes", []))
    assert [a for a in page["db"].query(Artifact, document_id=bare.id) if a.artifact_type == "transcription"]
