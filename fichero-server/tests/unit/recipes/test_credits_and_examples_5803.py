"""#5803: every borrowed example credits its source with links (the item's page and the licence's deed), from the engine;
and a stage's example sentence describes the one shipped example page, not an invented deed."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from fichero_server.recipes import examples, stages

SHOWCASE = Path(__file__).resolve().parents[4] / "fichero" / "fichero" / "Resources" / "StageShowcase"


def _page(example_id: str) -> dict:
    return json.loads((SHOWCASE / f"{example_id}.json").read_text(encoding="utf-8"))


def test_every_example_record_has_a_source_url_and_a_licence_url():
    assert examples.EXAMPLE_RECORDS
    for key, record in examples.EXAMPLE_RECORDS.items():
        for field in ("source_url", "licence_url"):
            assert record[field].startswith("https://"), (key, field)
        assert record["short_credit"] and record["licence"] and record["title"]


def test_the_engine_record_is_the_one_the_app_ships():
    for key, record in examples.EXAMPLE_RECORDS.items():
        page = _page(key)
        assert (record["source_url"], record["licence_url"], record["short_credit"]) == (
            page["source"], page["licence_url"], page["short_credit"])


def test_the_stage_listing_carries_the_credit_with_both_links():
    listed = stages.listing(None)
    assert listed and all(s["example_credit"]["source_url"] and s["example_credit"]["licence_url"] for s in listed)
    assert {s["example_credit"]["short_credit"] for s in listed} == {"Example: BNE · DILE, CC BY-SA 4.0"}


def _facts(page: dict) -> list[str]:
    """What the page says and what the stages make of it."""
    out = [line["text"] for line in page["lines"]]
    out += [c["value"] for c in page["table"]] + [page["translation"]["text"], page["search"]["query"]]
    out += [d["value"] for d in page["dates"]] + [s["label"] for s in page["statements"]]
    out += [e["written"] for e in page["normalise"]] + [e["expanded"] for e in page["normalise"]]
    return out


@pytest.mark.parametrize("stage", stages.STAGES, ids=lambda s: s.id)
def test_every_quoted_word_in_an_example_sentence_is_on_the_example_page_or_made_of_it(stage):
    page = _page("dialogo-lengua-p18")
    text = "\n".join(line["text"] for line in page["lines"])
    facts = [f.casefold() for f in _facts(page)]
    for quoted in re.findall("“([^”]+)”", stage.example):
        needle = quoted.casefold()
        assert needle in text.casefold() or any(needle in f or f in needle for f in facts), (stage.id, quoted)


def test_no_example_describes_a_deed_or_two_columns_the_page_does_not_have():
    sentences = " ".join(s.example + " " + s.sentence for s in stages.STAGES).lower()
    for invented in ("deed", "left column", "two-column", "ledger", "juan de la cruz", "mosquera"):
        assert invented not in sentences, invented
