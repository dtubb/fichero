"""A statement carries its when and where, or says nothing about them (#4670).

Daniel: "John Smith was a movie star, in New York, in 1933" — tie dates and
places to every SVO statement the page supports them for, not just to the
dates section. The claim model has carried `time_start`/`time_end` and
`claim_geo` all along; what was missing was an extraction contract that filled
them, and a rule for when it must not.

The rule is the grounding contract from #4666, applied to the scope: a place
must be on the page, and a date's year must be on the page. A scope the text
does not support is DROPPED while the claim stays — the assertion was
grounded, only its when/where was invented, and a fact with no date is honest
where a fact with the wrong one is not.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import extract_all
from fichero_server.workflows.tools.extract_all import (
    _EntityClaims,
    _date_is_on_the_page,
    _extract_claims_for_entity,
)

PAGE = (
    "Andres otorgo poder cumplido en Merida a diez dias del mes de abril "
    "de 1560 anos, ante el escrivano publico."
)


class TestDateGrounding:
    """A normalised date never appears verbatim, so the YEAR is what is
    checkable: four digits the transcription either contains or does not."""

    @pytest.mark.parametrize("date", ["1560", "1560-04-10", "1560/1561"])
    def test_a_year_on_the_page_grounds_the_date(self, date):
        assert _date_is_on_the_page(date, PAGE)

    @pytest.mark.parametrize("date", ["1842", "1842-04-10", "1842/1843"])
    def test_a_year_that_is_not_on_the_page_does_not(self, date):
        assert not _date_is_on_the_page(date, PAGE)

    def test_a_date_with_no_year_scopes_nothing_and_is_left_alone(self):
        # "04" restricts nothing on a timeline; there is nothing to refuse.
        assert _date_is_on_the_page("04", PAGE)
        assert _date_is_on_the_page("", PAGE)

    def test_the_check_fails_open_with_no_page_text(self):
        assert _date_is_on_the_page("1999", "")
        assert _date_is_on_the_page("1999", None)


def _run(monkeypatch, claim: dict):
    async def fake(**kwargs):
        return _EntityClaims(subject="Andres", claims=[{**claim}])

    monkeypatch.setattr(extract_all, "chat_structured_with_fallback", fake)
    return asyncio.run(
        _extract_claims_for_entity(
            PAGE,
            "Andres",
            "person",
            LLMConfig(provider="fake", model="fake"),
            "instructions",
            asyncio.Semaphore(1),
        )
    )


BASE = {
    "subject": "Andres",
    "verb": "otorgo",
    "object": "poder cumplido",
    "source_text": "Andres otorgo poder cumplido",
}


class TestScopeReachesTheClaim:
    def test_a_grounded_date_and_place_ride_the_claim(self, monkeypatch):
        claims = _run(monkeypatch, {**BASE, "date": "1560-04-10", "place": "Merida"})
        assert claims[0]["date_normalized"] == "1560-04-10"
        assert claims[0]["claim_location"] == "Merida"

    def test_an_ungrounded_place_is_dropped_and_the_claim_survives(
        self, monkeypatch
    ):
        claims = _run(monkeypatch, {**BASE, "place": "Santa Fe de Bogota"})
        assert len(claims) == 1, "the assertion was grounded; only its where was not"
        assert claims[0]["claim_location"] == ""
        assert claims[0]["verb"] == "otorgo"

    def test_an_ungrounded_date_is_dropped_and_the_claim_survives(
        self, monkeypatch
    ):
        claims = _run(monkeypatch, {**BASE, "date": "1842"})
        assert len(claims) == 1
        assert claims[0]["date_normalized"] == ""

    def test_a_claim_with_no_scope_at_all_is_still_a_claim(self, monkeypatch):
        claims = _run(monkeypatch, BASE)
        assert claims[0]["date_normalized"] == ""
        assert claims[0]["claim_location"] == ""

    def test_an_ungrounded_assertion_is_still_rejected_outright(self, monkeypatch):
        # Scope is forgiving; the assertion is not. A verb and object that are
        # not on the page were composed, not read.
        claims = _run(
            monkeypatch,
            {**BASE, "verb": "fue nombrado", "object": "gobernador de la provincia"},
        )
        assert claims == []
