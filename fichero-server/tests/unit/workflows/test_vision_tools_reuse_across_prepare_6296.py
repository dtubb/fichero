# ruff: noqa: F811  (the imported `page` fixture is the test parameter)
"""Owner ruling 2026-11-01 (review 10): after Prepare changes a page's image, a tool that answers about the picture as a whole
(describe, caption, tags, faces ...) reuses its saved result; the page IS straightened. A result made from a person's edit
answers only that edit; a whole-page transcription still reads again. Stubbed model, counted sends, real tool configs.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest
from fichero_server.media import find_page as fp
from fichero_server.media import turn_by_text as tt
from fichero_server.media.current_image import current_page_image
from fichero_server.models import Document, Rendition
from fichero_server.recipes import page_crop
from fichero_server.recipes.prepare_run import run_prepare
from tests.unit.workflows.test_every_step_sends_the_edited_image_6296 import EDITS, _set_edits, _size_of_uri
from tests.unit.workflows.test_every_step_sends_the_edited_image_6296 import page  # noqa: F401  (fixture)
from tests.unit.workflows.test_prepare_keeps_read_pages_from_paying_again_6296 import ruled

_REAL_FIND_PAGE = fp.find_page
TOOLS = ["describe", "caption", "tags", "classify", "layout", "objects", "quality", "scene", "style", "faces", "colors", "safety",
         "diagram"]


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setattr(fp, "find_page_vision", lambda image: None)
    monkeypatch.setattr(fp, "find_page", lambda image: None)
    monkeypatch.setattr(tt, "read_lines", lambda image, db_path=None: [])
    monkeypatch.setattr(page_crop, "_has_text", lambda *a: True)


async def _send(page, monkeypatch, tool, artifact_type=None):
    """One real `process_vision` run with the tool's own config: the pictures the model was sent."""
    import fichero_server.llm as llm
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.vision_base import process_vision

    config = importlib.import_module(f"fichero_server.workflows.tools.{tool}").TOOL_CONFIG if tool else None
    if artifact_type:  # a whole-page transcription, for the contrast
        from fichero_server.workflows.tools.vision_base import VisionToolConfig

        config = VisionToolConfig(artifact_type=artifact_type, supports_apple_vision=False, update_page_content=False,
                                  trigger_embedding=False, skip_if_artifact_exists=True)
    sent = []

    async def model(images, prompt, config, **_):
        sent.extend(_size_of_uri(i) for i in images)
        return "una hoja rayada"

    monkeypatch.setattr(llm, "vision", model)
    result = await process_vision(
        files=[page["path"]], documents=[page["doc"].model_dump(mode="json")], prompt="p", library_path=page["library"],
        llm_config=LLMConfig(provider="openrouter", model="m"), task_id="t", tool_config=config, vision_mode="llm",
        save_to_db=True)
    assert not result.get("error"), result.get("error")
    return sent


def _run(page, monkeypatch, tool, artifact_type=None):
    return asyncio.new_event_loop().run_until_complete(_send(page, monkeypatch, tool, artifact_type))


def _prepare(page):
    run_prepare(page["db"], [page["doc"].id], "run", {}, paper=[], operations=None)
    return sorted(r.role for r in page["db"].query(Rendition, document_id=page["doc"].id))


def _kind(page):
    return current_page_image(page["db"], page["db"].get(Document, page["doc"].id)).kind


@pytest.mark.parametrize("tool_name", TOOLS)
def test_a_result_is_reused_after_prepare_straightens_the_page(page, monkeypatch, tool_name):
    ruled(4.0).save(page["path"])
    assert len(_run(page, monkeypatch, tool_name)) == 1  # the first run pays
    assert _run(page, monkeypatch, tool_name) == []  # the control: unchanged page, nothing sent
    assert "deskewed" in _prepare(page) and _kind(page) == "rendition"  # the page IS straightened
    assert _run(page, monkeypatch, tool_name) == []  # no second payment


def test_a_whole_page_transcription_of_a_cut_page_still_reads_again_after_prepare(page, monkeypatch):
    from tests.unit.media.test_find_page import scan

    scan().save(page["path"])
    monkeypatch.setattr(fp, "find_page", _REAL_FIND_PAGE)
    assert len(_run(page, monkeypatch, None, "transcription")) == 1
    assert "crop" in _prepare(page)
    assert len(_run(page, monkeypatch, None, "transcription")) == 1  # a read is for the image it was made from (Case B limit)


def test_a_result_made_from_a_persons_edit_does_not_answer_another_image(page, monkeypatch):
    _set_edits(page, EDITS)
    assert len(_run(page, monkeypatch, "describe")) == 1  # read from the edited picture
    assert _run(page, monkeypatch, "describe") == []  # the same edit: reused
    _set_edits(page, [])  # Undo: the photograph, which that result was not made from
    assert len(_run(page, monkeypatch, "describe")) == 1


def test_a_result_from_the_photograph_does_not_answer_a_persons_edit(page, monkeypatch):
    ruled(4.0).save(page["path"])
    assert len(_run(page, monkeypatch, "describe")) == 1
    _set_edits(page, EDITS)
    assert len(_run(page, monkeypatch, "describe")) == 1  # the person's edit is the last word
    _set_edits(page, [])
    assert _run(page, monkeypatch, "describe") == []  # back on the photograph: its own result


def test_a_result_is_reused_after_a_cut(page, monkeypatch):
    from tests.unit.media.test_find_page import scan

    scan().save(page["path"])
    monkeypatch.setattr(fp, "find_page", _REAL_FIND_PAGE)  # the real contour finder cuts this scan
    assert len(_run(page, monkeypatch, "describe")) == 1
    assert "crop" in _prepare(page)
    assert _run(page, monkeypatch, "describe") == []

