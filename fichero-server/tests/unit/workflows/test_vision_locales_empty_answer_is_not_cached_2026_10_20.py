"""Fable runner review #17: a first ask of Vision's locales that failed (empty) was cached for the whole session, so
`validate_vision_language` passed any string through and Vision silently read in its default locale. An empty answer is
asked again; an answer is kept (`source.read.vision-locale`)."""
from __future__ import annotations

from fichero_server.workflows.tools import vision_base


def test_an_empty_answer_is_asked_again_and_a_real_one_is_kept(monkeypatch):
    monkeypatch.setattr(vision_base, "_locales_asked", None)
    answers = iter([frozenset(), frozenset({"es-ES", "en-US"}), frozenset({"never-asked"})])
    monkeypatch.setattr(vision_base, "_ask_vision_locales", lambda: next(answers))

    assert vision_base._supported_vision_locales() == frozenset()
    assert not vision_base.supported_locales_are_known()
    assert vision_base._supported_vision_locales() == frozenset({"es-ES", "en-US"})
    assert vision_base.supported_locales_are_known()
    assert vision_base._supported_vision_locales() == frozenset({"es-ES", "en-US"})  # kept: not asked a third time
