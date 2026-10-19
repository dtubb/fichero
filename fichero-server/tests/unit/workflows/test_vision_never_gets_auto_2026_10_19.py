"""Apple Vision was called with the literal language 'auto' on Find Lines (owner, 2026-10-19; `source.read.vision-locale`):
the project says es, which is es-ES; with no language at all Vision detects it itself; and a locale it lacks is said in
words, never as the dump of every locale the Mac supports."""
from __future__ import annotations

import pytest

from fichero_server.workflows.tools import vision_base
from fichero_server.workflows.tools.transcribe import _resolve_transcribe_language


@pytest.mark.parametrize("stated", ["auto", "unknown", "und", "AUTO"])
def test_no_language_stated_is_left_to_vision_not_passed_as_a_word(stated):
    assert vision_base.normalize_vision_language(stated) == "auto"
    assert vision_base.validate_vision_language(stated) == "auto"  # never refused as an unsupported locale


def test_auto_turns_on_vision_language_detection_and_a_locale_is_set():
    class Request:
        def __init__(self):
            self.calls = []

        def setAutomaticallyDetectsLanguage_(self, on):
            self.calls.append(("detect", on))

        def setRecognitionLanguages_(self, languages):
            self.calls.append(("languages", languages))

    auto, spanish = Request(), Request()
    vision_base.set_vision_languages(auto, "auto")
    vision_base.set_vision_languages(spanish, "es-ES")
    assert auto.calls == [("detect", True)] and spanish.calls == [("languages", ["es-ES"])]


def test_the_projects_language_is_the_one_a_page_that_states_none_is_read_in():
    resolution = _resolve_transcribe_language("auto", [], "es")
    assert vision_base.normalize_vision_language(resolution.language) == "es-ES"


def test_a_locale_this_mac_lacks_is_said_in_words_without_the_dump(monkeypatch):
    monkeypatch.setattr(vision_base, "_supported_vision_locales", lambda: frozenset({"en-US", "fr-FR"}))
    with pytest.raises(ValueError) as caught:
        vision_base.validate_vision_language("es")
    assert str(caught.value) == "Apple Vision can't read Spanish on this Mac. Choose another reader for this step."


def test_set_up_saved_languages_are_the_projects_language_when_no_fact_row_was_written(tmp_path, monkeypatch):
    """Set Up saves `answers.languages`, never the project-fact row (review 350): the function the run calls must read it."""
    from fichero_server.db import db_manager
    from fichero_server.recipes.project import write_project_setup
    from fichero_server.workflows.tools.transcribe import _project_language

    class NoFacts:
        def get(self, *_args):
            return None

    monkeypatch.setattr(db_manager, "get_database", lambda path: NoFacts())
    write_project_setup(tmp_path, {"languages": ["es"], "scripts": ["Latn"]}, None)
    assert _project_language({"library_path": str(tmp_path)}) == "es"
    assert _project_language({"library_path": ""}) is None
