"""`source.model.trained-card-keeps-its-release` (#5683).

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY (2026-10-11, the MCP onboarding walk):
the trained Mosquera reader, taught on Sergio's notebooks, showed open_licence true and languages ["en"] (its base's
README) in the recipe's candidates, while its own card said not for release. Sergio's pages may train a model; it is
never released. A model is landed in a temp store the way training lands one; nothing is converted or loaded.
"""
from __future__ import annotations

from fichero_server.recipes.discovery import installed_cards
from fichero_server.training.mlx_landing import land_vision_student
from tests.unit.training.test_vision_student_lands import CARD, _fake_convert, _job_output, store  # noqa: F401


def _card_for(store, card):
    model_id = land_vision_student(_job_output(store.root.parent), job_id="j1", name="mosquera", card=card,
                                   convert=_fake_convert)
    # The base's README, as a converted base carries it: it names English.
    (store.trained_dir(model_id) / "README.md").write_text("---\nlanguage: en\nlicense: apache-2.0\n---\n")
    (found,) = [c for c in installed_cards(()) if c.pin["hf"] == store.spec(model_id).repo_id]
    return found


def test_a_model_not_for_release_says_so_and_never_takes_its_bases_language(store, monkeypatch):
    monkeypatch.setattr(store, "spec", _with_vision(store.spec))
    card = _card_for(store, CARD)
    assert "not for release" in card.licence
    assert card.languages is None, "its base's English is not the reader's"
    assert card.open_licence is True, "the person's own reader stays usable in their own projects"


def test_a_model_its_card_releases_is_open_with_its_own_languages(store, monkeypatch):
    monkeypatch.setattr(store, "spec", _with_vision(store.spec))
    card = _card_for(store, {**CARD, "not_for_release": False, "languages": ["es"]})
    assert "not for release" not in card.licence and card.languages == frozenset({"es"})


def _with_vision(spec_of):
    """The landed student reads pages: its spec says so (a converted Qwen2.5-VL does)."""
    from dataclasses import replace

    def spec(model_id):
        s = spec_of(model_id)
        return s if "vision" in s.capabilities else replace(s, capabilities=(*s.capabilities, "vision"))

    return spec
