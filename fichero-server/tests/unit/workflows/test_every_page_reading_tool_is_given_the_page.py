"""Every vision tool that reads a page's text is given the page from ONE builder (#5026, slice 2).

WHY: page context was built twice -- `tool_context` (slice 1, lines with boxes and makers) and
transcribe_review's `_existing_transcription_context` (the page text, else the newest
transcription, as one string), used by review and analyze. Two builders give two answers to "what
does this page say". The old one is gone; before it went, what it sent was pinned here, and the
builder carries at least that: the page's text, a Transcribe run's artifact on a page with no
segments (the newest one), and nothing at all when there is nothing. If this regresses, a review
of a page transcribed moments ago works from the picture alone, or a tool reads a stale draft.

Each tool is run end to end with the model call captured: what reaches the prompt is asserted.
Real data: the Vienna Syriac folio (CC-BY-SA) through `format.import`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Artifact, DocType, Document
from fichero_server.core.timeutil import utc_now
from fichero_server.tool_context import tool_context
from tests.fixture_paths import sample_file
from tests.unit.api.test_reader_directions import SYRIAC, _import


def _no_space(text: str) -> str:
    return "".join(text.split())


def _bare_page(db, **fields) -> str:
    page = Document(name="a page with no segments", doc_type=DocType.file, **fields)
    db.save(page)
    return page.id


def _transcription(db, doc_id: str, content: str, minutes_ago: int) -> Artifact:
    art = Artifact(document_id=doc_id, artifact_type="transcription", content=content,
                   created_at=utc_now() - timedelta(minutes=minutes_ago))
    db.save(art)
    return art


# -- what the old helper sent, pinned, and the builder carries at least that --------------------

def test_a_page_with_segments_its_text_is_every_character_of_the_lines(db):
    """Old: the payload's `page_content` (the page text). New: the lines; the same characters."""
    doc_id = _import(db, SYRIAC)
    page_text = db.get(Document, doc_id).page_content
    assert page_text.strip()
    got = tool_context(db, doc_id)
    lines = [row.split(" | ", 3)[3] for row in got.text.splitlines()]
    assert _no_space("".join(lines)) == _no_space(page_text)


def test_a_page_with_no_segments_gets_its_newest_transcription(db):
    """Old: the newest transcription artifact. A Transcribe run writes one and no segments."""
    doc_id = _bare_page(db)
    _transcription(db, doc_id, "an older draft", minutes_ago=10)
    newest = _transcription(db, doc_id, "the newest draft of the page", minutes_ago=1)
    got = tool_context(db, doc_id)
    assert got.plain and got.text == "the newest draft of the page"
    assert got.statement.endswith(f"from its newest transcription ({newest.id})")


def test_a_page_with_no_segments_and_page_text_gets_the_page_text_first(db):
    doc_id = _bare_page(db, page_content="the page's own text")
    _transcription(db, doc_id, "a machine draft", minutes_ago=1)
    got = tool_context(db, doc_id)
    assert (got.plain, got.text) == (True, "the page's own text")


def test_a_page_with_nothing_says_so(db):
    got = tool_context(db, _bare_page(db))
    assert not got.plain and got.statement == "no reading on the page yet: the tool works from the picture alone"


# -- each tool, end to end, with the model call captured --------------------------------------

def _run(tool, db, test_package, monkeypatch, doc_id: str, **extra) -> str:
    from fichero_server.llm import LLMConfig

    image = str(sample_file("sample.jpg"))
    prompts: list[str] = []

    async def seen_by_the_model(images, prompt, config, **kwargs):
        prompts.append(prompt)
        return "a,b\n1,2"

    monkeypatch.setattr("fichero_server.llm.vision", seen_by_the_model)
    inputs = {"files": [image], "documents": [{"id": doc_id, "name": "folio", "path": image}],
              "save_to_db": False, "skip_if_artifact_exists": False, **extra}
    result = asyncio.run(tool(inputs, {"library_path": str(test_package)}, LLMConfig(provider="mock", model="mock")))
    assert not result.get("error"), result
    [prompt] = prompts
    return prompt


def _tools():
    from fichero_server.workflows.tools.analyze import analyze
    from fichero_server.workflows.tools.convert import convert
    from fichero_server.workflows.tools.describe import describe
    from fichero_server.workflows.tools.table_extract import table_extract
    from fichero_server.workflows.tools.transcribe_review import transcribe_review

    return {"transcribe_review": transcribe_review, "analyze": analyze, "describe": describe,
            "convert": convert, "table_extract": table_extract}


@pytest.mark.parametrize("name", ["transcribe_review", "analyze", "describe", "convert", "table_extract"])
def test_the_tool_sends_the_pages_lines(name, db, test_package, monkeypatch):
    doc_id = _import(db, SYRIAC)
    prompt = _run(_tools()[name], db, test_package, monkeypatch, doc_id)
    for row in tool_context(db, doc_id).text.splitlines():
        assert row in prompt, (name, row)


@pytest.mark.parametrize("name", ["transcribe_review", "analyze"])
def test_the_tool_sends_a_bare_pages_newest_transcription(name, db, test_package, monkeypatch):
    """The case the old helper existed for: Transcribe today, review or analyse tomorrow."""
    doc_id = _bare_page(db)
    _transcription(db, doc_id, "an older draft", minutes_ago=10)
    _transcription(db, doc_id, "the newest draft of the page", minutes_ago=1)
    prompt = _run(_tools()[name], db, test_package, monkeypatch, doc_id)
    assert "the newest draft of the page" in prompt and "an older draft" not in prompt


def test_a_wired_draft_wins_over_the_page(db, test_package, monkeypatch):
    """A draft wired from the step before is the thing to review; the page is not added to it."""
    doc_id = _import(db, SYRIAC)
    prompt = _run(_tools()["transcribe_review"], db, test_package, monkeypatch, doc_id,
                  context="a wired draft from the step before")
    assert "a wired draft from the step before" in prompt
    assert tool_context(db, doc_id).text.splitlines()[0] not in prompt
