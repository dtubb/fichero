"""Find Lines offers only models that can find lines; a cloud model added by hand is not one (#5838,
`source.find.candidates-fit-the-step`)."""
from __future__ import annotations

import pytest

from fichero_server.recipes import samples
from fichero_server.recipes.assemble import Card


def _opus() -> Card:
    return Card(id="anthropic:opus@row", pin={"cloud": "anthropic", "model": "opus"},
                jobs=frozenset({"read-a-page", "correct"}), scripts=None, languages=None, material=frozenset(),
                runs_on="cloud:anthropic", open_licence=True, licence="", note="Opus (Anthropic)",
                source="installed", offered_only=True)


def test_comparing_a_model_that_cannot_find_lines_is_refused_in_words(monkeypatch):
    from fichero_server.recipes import discovery

    opus = _opus()
    monkeypatch.setattr(discovery, "known_cards", lambda *a, **k: [opus])
    monkeypatch.setattr(discovery, "discover", lambda *a, **k: ([], []))
    from fichero_server.api.routes.system import recipes as routes
    from fichero_server.recipes.assemble import Answers

    monkeypatch.setattr(routes, "_answers", lambda answers: Answers(
        purposes=("transcribe",), languages=frozenset({"es"}), scripts=frozenset({"Latn"}), materials=("handwriting",)))
    setup = {"answers": {}, "recipe": {}}

    with pytest.raises(ValueError) as refused:
        samples._cards_for(setup, {"id": "lines", "job": "find-lines"}, [opus.id])

    words = str(refused.value)
    assert "Opus (Anthropic) cannot do the step lines (find-lines)" in words
    assert "Kraken and Apple Vision" in words and "cloud vision models cannot find lines" in words
