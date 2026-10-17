"""`source.job.find-statements.candidates` (#5637, ruled 2026-10-17): the parser by default, a text model offered.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: Find statements was parser-or-nothing: with
no text model installed the step had no model and Start skipped it. Now the free local candidate (the parser's triples)
runs where no text model is installed, and a text model is offered beside it; where one is installed the rules take it.
Through `assemble` with explicit cards (no store, no network).
"""
from __future__ import annotations

from fichero_server.recipes.assemble import Answers, Card, assemble

PARSER = Card("spacy:svo/es_core_news_sm@bundled", {"spacy": "es_core_news_sm", "version": "bundled"},
              frozenset({"find-statements"}), frozenset({"Latn"}), frozenset({"es"}),
              frozenset({"handwriting", "print", "typescript"}), size_gb=0.01)
MODEL = Card("mlx:text/qwen3-8b@store", {"hf": "mlx-community/Qwen3-8B-4bit", "revision": "main"},
             frozenset({"find-statements"}), None, None, frozenset(), size_gb=4.5, memory_gb=6.0, installed=True)
ANSWERS = Answers(purposes=("statements",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}),
                  materials=("print",), material="print", mac_memory_gb=32)


def _statements(*cards: Card) -> dict:
    return next(s for s in assemble(ANSWERS, [*cards])["steps"] if s["job"] == "find-statements")


def test_with_no_text_model_the_free_parser_runs_and_a_model_is_offered():
    """source.job.find-statements.candidates: "where no text model is installed ... the free local candidates run at
    Start, and a text model is offered beside them"."""
    step = _statements(PARSER)

    assert step["model"] == PARSER.pin and step["runs_on"] == "this-mac", step
    assert any("text model can be chosen" in r for r in step["reasons"]), step["reasons"]


def test_with_a_text_model_installed_the_rules_take_it_over_the_parser():
    """source.job.find-statements.candidates: "where a text model is installed here, the rules take it"."""
    assert _statements(PARSER, MODEL)["model"] == MODEL.pin


def test_the_shipped_cards_default_the_statements_step_to_the_parser(tmp_path, monkeypatch):
    """source.job.find-statements.candidates: through the cards the route uses, an empty model store gives the parser."""
    from fichero_server.recipes.discovery import known_cards

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    step = next(s for s in assemble(ANSWERS, known_cards(ANSWERS))["steps"] if s["job"] == "find-statements")

    assert step["model"].get("spacy") == "es_core_news_sm" and not step.get("gap"), step
