"""A model's read is checked before it lands (#5522).

Measured 2026-10-06 (Qwen2.5-VL-3B via MLX on a 16 GB M4): on a notarial page the model looped --
'Vtho Vntoré Vtho Vntoré ...', CER 1.10 against ground truth, longer than the page -- and the step
ended 'completed' and OVERWROTE the page's text. On a Fraktur page it stopped at ~70% of the text,
also 'completed'. A read that came back is not a read that is good.

WHY each test: a looping or cut-off read that reaches page_content replaces a person's or a better
model's reading with garbage, silently, and every later step (search, extraction, export) reads
the garbage. A flagged read must still land (a person can look at it and choose it), marked, never
as the page's text or its working reading, and the step must say what it caught. A CLEAN read must
land exactly as before -- the checker must not cost a good page its text.

Driven through the real Transcribe tool on a real library; only the model's answer is faked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.llm.read_guard import (
    LOOP_MIN_WORDS,
    REPETITION,
    TOO_LONG,
    TRUNCATED,
    ModelText,
    check_read,
    finish_reason_of,
    read_flag_of,
)

#: The measured loop, shaped as the model wrote it: a start of real text, then the loop.
LOOP = "En la ciudad de Santa Fe a diez dias del mes de mayo " + "Vtho Vntoré " * 60
#: A real notarial paragraph: formulae recur ("en la dicha ciudad", "dicho escribano") but never loop.
NOTARIAL = (
    "En la dicha ciudad de Santa Fe a diez dias del mes de mayo de mil y seiscientos años ante mi "
    "el escribano y testigos parecio presente Juan de Mosquera vecino de la dicha ciudad y dixo que "
    "otorgaba y otorgo su poder cumplido en la dicha ciudad a Pedro de Herrera vecino de la dicha "
    "ciudad para que en su nombre pueda parecer ante las justicias de la dicha ciudad y en la dicha "
    "ciudad cobrar lo que se le debe y dicho escribano doy fe y lo firmo de su nombre siendo testigos "
    "Alonso Perez y Diego Lopez vecinos de la dicha ciudad ante mi Francisco de Sotomayor escribano"
)
EARLIER = "La lectura anterior de esta pagina, revisada a mano."


class TestTheChecker:
    def test_the_measured_loop_is_flagged_as_repetition(self):
        flag = check_read(LOOP, model="Qwen2.5-VL-3B")
        assert flag is not None and flag.kind == REPETITION
        assert "Qwen2.5-VL-3B repeated itself" in flag.reason
        assert flag.measure["repeated_words"] >= LOOP_MIN_WORDS

    def test_a_notarial_page_whose_formulae_recur_is_clean(self):
        """WHY: a checker that flags ordinary legal prose would keep every notarial page off its text."""
        assert check_read(NOTARIAL) is None

    def test_a_loop_with_no_spaces_is_flagged(self):
        assert check_read("Начало " + "абв" * 20).kind == REPETITION

    def test_dotted_leaders_and_rules_are_not_a_loop(self):
        assert check_read("Capitulo primero .................................. 12\n" + "_" * 60) is None

    def test_more_text_than_the_lines_hold_is_too_long(self):
        flag = check_read(" ".join(f"w{i}" for i in range(800)), line_count=3)
        assert flag is not None and flag.kind == TOO_LONG
        assert "3 lines" in flag.reason

    def test_the_same_text_with_enough_lines_is_clean(self):
        assert check_read(" ".join(f"w{i}" for i in range(800)), line_count=40) is None

    @pytest.mark.parametrize("reason", ["length", "lengthlength", "max_tokens"])
    def test_the_models_own_ran_out_of_room_is_truncated(self, reason):
        assert check_read("Die ersten Zeilen", finish_reason=reason).kind == TRUNCATED

    def test_a_finished_answer_is_clean(self):
        assert check_read("Die ersten Zeilen", finish_reason="stop") is None


@pytest.mark.asyncio
async def test_vision_carries_the_models_finish_reason(monkeypatch):
    """WHY: without the reason on the answer, a page the model stopped short on looks finished."""
    from langchain_core.messages import AIMessage

    import fichero_server.llm as llm

    class Model:
        async def ainvoke(self, messages):
            return AIMessage(content="Die ersten Zeilen", response_metadata={"finish_reason": "length"})

    async def ready(config, capability):
        return None

    monkeypatch.setattr(llm, "get_langchain_model", lambda config: Model())
    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    text = await llm.vision(["data:image/png;base64,AAAA"], "read-guard finish reason probe",
                            config=llm.LLMConfig(provider="openai", model="gpt-4o", api_key="k"))
    assert text == "Die ersten Zeilen"
    assert finish_reason_of(text) == "length"


@pytest.mark.asyncio
async def test_vision_reads_a_full_ceiling_as_ran_out_of_room(monkeypatch):
    """WHY: a local MLX server reports no finish reason; an answer that used exactly its token
    ceiling is the same signal (the #5522 Fraktur page stopped at 70%)."""
    from langchain_core.messages import AIMessage

    import fichero_server.llm as llm

    class Model:
        async def ainvoke(self, messages):
            return AIMessage(content="Die ersten", usage_metadata={
                "input_tokens": 10, "output_tokens": 64, "total_tokens": 74})

    async def ready(config, capability):
        return None

    monkeypatch.setattr(llm, "get_langchain_model", lambda config: Model())
    monkeypatch.setattr(llm, "_ensure_managed_local_provider_ready", ready)
    text = await llm.vision(["data:image/png;base64,AAAA"], "read-guard ceiling probe",
                            config=llm.LLMConfig(provider="openai", model="gpt-4o", api_key="k", max_tokens=64))
    assert finish_reason_of(text) == "length"


def _page(db, tmp_path, page_content: str | None = EARLIER):
    from PIL import Image

    from fichero_server.models import DocType, Document, FileType

    path = tmp_path / "SM_NPQ_C01_007.png"
    Image.new("RGB", (32, 32), "white").save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   page_content=page_content)
    db.save(doc)
    return doc


async def _transcribe(library, doc):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    config = LLMConfig(provider="omlx", model="Qwen2.5-VL-3B")
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=config)
    return await transcribe(inputs={"files": src["files"], "documents": src["documents"],
                                    "vision_mode": "llm", "force_ocr": True},
                            state={"library_path": library}, llm_config=config)


def _transcriptions(db, doc):
    from fichero_server.models import Artifact

    return [a for a in db.query(Artifact, document_id=doc.id) if a.artifact_type == "transcription"]


def _fake_model(monkeypatch, answer):
    import fichero_server.llm as llm

    async def model(images, prompt, config, **_):
        return answer

    monkeypatch.setattr(llm, "vision", model)


@pytest.mark.asyncio
async def test_a_looping_read_lands_flagged_and_the_page_keeps_its_text(test_package, tmp_path, monkeypatch):
    from fichero_server.models import Document

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    _fake_model(monkeypatch, ModelText(LOOP, "stop"))

    result = await _transcribe(library, doc)

    assert not result.get("error"), result.get("error")
    assert db.get(Document, doc.id).page_content == EARLIER, "a looping read overwrote the page's text"
    saved = _transcriptions(db, doc)
    assert len(saved) == 1 and saved[0].content == LOOP.strip(), "the flagged read must still land, to be looked at"
    assert read_flag_of(saved[0])["kind"] == REPETITION
    assert result["results"][0]["read_flag"]["kind"] == REPETITION
    assert len(result["notes"]) == 1
    note = result["notes"][0]
    assert "repeated itself" in note and "kept the earlier reading" in note, note
    assert result["records"] == [], "a flagged read must feed nothing downstream"


@pytest.mark.asyncio
async def test_a_read_the_model_cut_short_lands_flagged(test_package, tmp_path, monkeypatch):
    from fichero_server.models import Document

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    _fake_model(monkeypatch, ModelText("Die ersten Zeilen der Seite", "length"))

    result = await _transcribe(library, doc)

    assert db.get(Document, doc.id).page_content == EARLIER
    assert read_flag_of(_transcriptions(db, doc)[0])["kind"] == TRUNCATED
    assert "stopped before the end" in result["notes"][0]


@pytest.mark.asyncio
async def test_a_clean_read_lands_as_the_pages_text(test_package, tmp_path, monkeypatch):
    from fichero_server.models import Document

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    _fake_model(monkeypatch, ModelText(NOTARIAL, "stop"))

    result = await _transcribe(library, doc)

    assert db.get(Document, doc.id).page_content == NOTARIAL
    saved = _transcriptions(db, doc)
    assert len(saved) == 1 and read_flag_of(saved[0]) is None
    assert result["notes"] == []
    assert "read_flag" not in result["results"][0]


@pytest.mark.asyncio
async def test_a_line_that_loops_flags_the_teachers_page(test_package, tmp_path, monkeypatch):
    """The line path (Kraken finds lines, the model reads each one) is checked too: one line read
    as a loop marks its box, and the page's reading lands flagged."""
    import fichero_server.llm as llm
    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult
    from fichero_server.models import Document
    from fichero_server.workflows.tools.sources import files_tool
    from fichero_server.workflows.tools.transcribe import transcribe

    library = str(test_package)
    db = db_manager.get_database(library)
    doc = _page(db, tmp_path)
    lines = OCRGeometryResult(text="", provider="kraken", model="blla", source="kraken-blla", boxes=[
        OCRGeometryBox(text="", bbox=[0.05, 0.1 + 0.3 * i, 0.9, 0.2], level=OCRGeometryLevel.LINE,
                       metadata={"polygon_px": [[1, 2 + 10 * i], [30, 2 + 10 * i], [30, 9 + 10 * i], [1, 9 + 10 * i]]})
        for i in range(2)])
    monkeypatch.setattr(kraken_runtime, "segment_to_geometry", lambda image_path, rendition_id=None: lines)

    async def teacher(images, prompt, config, **_):
        return '["en la ciudad de Santa Fe", "%s"]' % ("Vtho Vntoré " * 30).strip()

    monkeypatch.setattr(llm, "vision", teacher)
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=llm.LLMConfig(provider="", model=""))
    result = await transcribe(
        inputs={"files": src["files"], "documents": src["documents"], "vision_mode": "kraken",
                "lines_read_by": "model"},
        state={"library_path": library}, llm_config=llm.LLMConfig(provider="openrouter", model="teacher"))

    saved = _transcriptions(db, doc)[0]
    assert read_flag_of(saved)["measure"]["lines_flagged"] == 1
    assert [read_flag_of(b) is not None for b in saved.ocr_geometry.boxes] == [False, True]  # raw-geometry-ok: the result just made
    assert db.get(Document, doc.id).page_content == EARLIER
    assert "on 1 of its 2 lines" in result["notes"][0]


def test_a_flagged_result_is_not_the_working_pass(test_package):
    """WHY: the Reader, search and export read the working pass. A newer flagged result must not
    take the page from the older clean one; a person can still choose it."""
    from fichero_server.api.routes.document.segment_readings import working_pass
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
    from fichero_server.models import Artifact, DocType, Document, FileType
    from fichero_server.models.segments import legacy_pass_id

    db = db_manager.get_database(str(test_package))
    doc = Document(name="p.png", doc_type=DocType.file, file_type=FileType.image, path="/p/p.png")
    db.save(doc)
    now = datetime.now(timezone.utc)

    def result(text, created_at, data=None):
        art = Artifact(document_id=doc.id, artifact_type="transcription", content=text, data=data,
                       provider="omlx", model="Qwen2.5-VL-3B", created_at=created_at,
                       ocr_geometry=OCRGeometryResult(text=text, provider="omlx", boxes=[OCRGeometryBox(text=text, bbox=[0.1, 0.1, 0.5, 0.05])]))
        db.save(art)
        return art

    clean = result("en la ciudad", now - timedelta(hours=1))
    flagged = result(LOOP, now, data={"read_flag": check_read(LOOP).as_data()})

    assert working_pass(db, doc.id).pass_id == legacy_pass_id(clean.id)
    assert flagged.id != clean.id
