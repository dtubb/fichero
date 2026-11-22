"""A compiled search keeps a filter only if its words are in the question, and a date in the question is the date
written, not the day a page was imported (#6785, `search.ask.invents-no-filter`,
`search.ask.a-date-means-the-date-written`)."""

from __future__ import annotations

import re

import pytest

from fichero_server.models import DocType, Document, FileType
from fichero_server.retrieval.query_compiler import _COMPILER_SYSTEM_PROMPT, CompiledQuery, compile_query


def _model_returns(monkeypatch, compiled: CompiledQuery) -> None:
    async def fake_chat_structured(**kwargs):
        return compiled

    import fichero_server.llm as llm_module

    monkeypatch.setattr(llm_module, "chat_structured", fake_chat_structured)
    monkeypatch.setattr("fichero_server.retrieval.query_compiler._resolve_compiler_config", lambda db: object())


def test_the_instructions_carry_no_copyable_date() -> None:
    assert not re.search(r"\d{4}", _COMPILER_SYSTEM_PROMPT)


@pytest.mark.asyncio
async def test_a_date_the_question_does_not_state_is_dropped(monkeypatch) -> None:
    _model_returns(
        monkeypatch,
        CompiledQuery(semantic_query="who ran the mine", date_from="1948-03-01", date_to="1948-03-31"),
    )

    compiled = await compile_query(db=None, query="Who ran the mine at Condoto?")

    assert (compiled.date_from, compiled.date_to) == (None, None)


@pytest.mark.asyncio
async def test_a_date_whose_year_is_in_the_question_is_kept(monkeypatch) -> None:
    _model_returns(
        monkeypatch,
        CompiledQuery(semantic_query="letters", date_from="1935-01-01", date_to="1935-01-31"),
    )

    compiled = await compile_query(db=None, query="Which letters were written in January 1935?")

    assert (compiled.date_from, compiled.date_to) == ("1935-01-01", "1935-01-31")


@pytest.mark.asyncio
async def test_an_entity_and_a_type_the_question_does_not_name_are_dropped(monkeypatch) -> None:
    _model_returns(
        monkeypatch,
        CompiledQuery(semantic_query="who ran the mine", entities=["Condoto", "Bogotá"], doc_type="folder"),
    )

    compiled = await compile_query(db=None, query="Who ran the mine at Condoto?")

    assert compiled.entities == ["Condoto"]
    assert compiled.doc_type is None


def test_a_compiled_date_is_applied_as_the_written_date(client, db, monkeypatch) -> None:
    from fichero_server.api.routes.search import core as core_module
    from fichero_server.histdate import gregorian_to_jdn

    written = Document(
        id="written", name="Letter", doc_type=DocType.file, file_type=FileType.text,
        page_content="mining letter about the dam", date_jdn=gregorian_to_jdn(1935, 1, 10),
    )
    other = Document(
        id="other", name="Letter 2", doc_type=DocType.file, file_type=FileType.text,
        page_content="mining letter about the dam", date_jdn=gregorian_to_jdn(1940, 6, 1),
    )
    db.save_many([written, other], new=True)

    async def fake_compile(db_, query):
        return CompiledQuery(semantic_query="mining letter", date_from="1935-01-01", date_to="1935-01-31")

    monkeypatch.setattr(core_module, "compile_query", fake_compile)

    r = client.post(
        "/api/search",
        json={"query": "Which mining letter was written in January 1935?", "search_type": "fulltext",
              "min_score": 0.0, "compile": True},
    )

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["filters_applied"]["date_jdn_from"] == gregorian_to_jdn(1935, 1, 1)
    assert payload["filters_applied"]["date_jdn_to"] == gregorian_to_jdn(1935, 1, 31)
    assert "date_from" not in payload["filters_applied"]
    assert [row["document_id"] for row in payload["results"]] == ["written"]
