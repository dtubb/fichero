"""A compiled query's PROSE never carries the dates its FILTERS already hold.

Daniel, 2026-09-01: the results bar read "Searched: “1948-01-01 to
1948-03-01”", which looked like a scope he had set on the open folder. It was
the query compiler echoing its own date extraction back into
`semantic_query` — the old system prompt spelled its example as
"1948-03-01 to 1948-03-31" and the model copied that phrasing into the prose.

The prompt now says the dates live in date_from/date_to and that
semantic_query must contain none; `strip_dates_from_semantic_query` enforces
it, because a prompt is guidance and this is a contract the UI reads.
"""

from __future__ import annotations

import re

import pytest

from fichero_server.retrieval.query_compiler import (
    CompiledQuery,
    _COMPILER_SYSTEM_PROMPT,
    compile_query,
    strip_dates_from_semantic_query,
)

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


class TestStripDates:
    def test_the_reported_range_is_removed(self) -> None:
        assert (
            strip_dates_from_semantic_query(
                "letters about mining 1948-01-01 to 1948-03-01"
            )
            == "letters about mining"
        )

    @pytest.mark.parametrize(
        "separator", ["to", "-", "–", "—", "until", "through"]
    )
    def test_every_range_separator(self, separator: str) -> None:
        out = strip_dates_from_semantic_query(
            f"mining 1948-01-01 {separator} 1948-03-31 correspondence"
        )
        assert out == "mining correspondence"

    def test_spanish_range_and_dangling_connective(self) -> None:
        # The corpora are largely Spanish; 'desde … hasta' must leave no
        # stranded preposition behind.
        assert (
            strip_dates_from_semantic_query(
                "cartas de minería desde 1948-01-01 hasta 1948-03-31"
            )
            == "cartas de minería"
        )

    def test_a_lone_date_goes_too(self) -> None:
        assert strip_dates_from_semantic_query("letters from 1948-03-01") == "letters"

    def test_a_query_that_is_only_a_range_scrubs_to_empty(self) -> None:
        assert strip_dates_from_semantic_query("1948-01-01 to 1948-03-01") == ""

    def test_a_date_free_query_is_untouched(self) -> None:
        assert (
            strip_dates_from_semantic_query("letters about the dam")
            == "letters about the dam"
        )

    def test_a_year_alone_survives(self) -> None:
        # '1948' is a real retrieval term a transcription can contain; only
        # ISO-formatted dates, which no transcription contains, are scrubbed.
        assert strip_dates_from_semantic_query("dam 1948 report") == "dam 1948 report"


class TestCompilerPrompt:
    def test_prompt_sends_dates_to_the_fields_not_the_prose(self) -> None:
        assert "date_from" in _COMPILER_SYSTEM_PROMPT
        assert "date_to" in _COMPILER_SYSTEM_PROMPT
        assert "semantic_query must contain NO dates" in _COMPILER_SYSTEM_PROMPT
        # The old prompt's bare "1948-03-01 to 1948-03-31" was the phrasing
        # the model copied; the example now names the fields it sets.
        assert "1948-03-01 to 1948-03-31" not in _COMPILER_SYSTEM_PROMPT


class TestCompileQueryScrubs:
    """The Daniel case end to end, with the LLM mocked to misbehave."""

    @pytest.mark.asyncio
    async def test_between_january_and_march_1948(self, monkeypatch) -> None:
        request = "letters about mining between January and March 1948"

        async def fake_chat_structured(**kwargs):
            # A plausible compiler output that leaks the range into the prose.
            return CompiledQuery(
                semantic_query="letters about mining 1948-01-01 to 1948-03-31",
                date_from="1948-01-01",
                date_to="1948-03-31",
            )

        import fichero_server.llm as llm_module

        monkeypatch.setattr(llm_module, "chat_structured", fake_chat_structured)
        monkeypatch.setattr(
            "fichero_server.retrieval.query_compiler._resolve_compiler_config",
            lambda db: object(),
        )

        compiled = await compile_query(db=None, query=request)

        assert not _ISO.search(compiled.semantic_query), compiled.semantic_query
        assert "to" not in compiled.semantic_query.split()
        assert compiled.semantic_query == "letters about mining"
        # The dates are not LOST — they moved to where the filters read them.
        assert compiled.date_from == "1948-01-01"
        assert compiled.date_to == "1948-03-31"

    @pytest.mark.asyncio
    async def test_prose_that_scrubs_to_nothing_falls_back_to_the_raw_words(
        self, monkeypatch
    ) -> None:
        request = "anything between January and March 1948"

        async def fake_chat_structured(**kwargs):
            return CompiledQuery(
                semantic_query="1948-01-01 to 1948-03-31",
                date_from="1948-01-01",
                date_to="1948-03-31",
            )

        import fichero_server.llm as llm_module

        monkeypatch.setattr(llm_module, "chat_structured", fake_chat_structured)
        monkeypatch.setattr(
            "fichero_server.retrieval.query_compiler._resolve_compiler_config",
            lambda db: object(),
        )

        compiled = await compile_query(db=None, query=request)
        # Never a blank retrieval query — the user's own words instead.
        assert compiled.semantic_query == request
