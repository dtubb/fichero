"""Names reads a page in the project's language unless the page is clearly another (#5708), tested to the spec:
`source.lang.project-language-first` (docs/contributor_manual/specs/source/languages-scripts-signs.md).

WHY: the operator's real run (integration 88b81f01e) on a project answered es-Latn with es_core_news_sm: Names
reported `languages_used {'English': 23, 'Spanish': 64}`. Per-page detection on HTR noise ("L isdusnt. crst a it":
a stray "a", an "it") fell back to English and read Spanish pages with the English pipeline.
"""

from __future__ import annotations

import pytest

from fichero_server.llm.language_policy import LanguagePolicy, resolve_language

NOISE = "L isdusnt. crst a it\nnou y^ 8r F 60535 nyi gil ditree delariadad\nmecdes Pllibrause les desvaisrg it a"
ENGLISH = ("The witness said that he had seen the house and that it was in the hands of the priest, and that the "
           "mine of the river was sold to him by the widow of the late owner, who was in the town at the time.")
SPANISH = "Yten dixo el testigo que la casa de la dicha Ana era de su padre y que la vendió en el pueblo de Ystmina."
UNSET = LanguagePolicy(mode="unset", languages=())


@pytest.mark.parametrize("text, want", [(NOISE, "Spanish"), (SPANISH, "Spanish"), (ENGLISH, "English")])
def test_the_projects_language_unless_the_page_is_clearly_another(text, want):
    said = resolve_language(text=text, policy=UNSET, project_language="Spanish")
    assert said.language == want, said
    if want == "Spanish" and text is NOISE:
        assert "project" in said.basis


def test_without_a_project_language_detection_is_as_before():
    assert resolve_language(text=NOISE, policy=UNSET).language == "English"  # the legacy fallback, unchanged


@pytest.mark.asyncio
async def test_names_reads_noisy_pages_of_a_spanish_project_in_spanish(tmp_path, monkeypatch):
    import fichero_server.workflows.tools  # noqa: F401  (registers tools)
    from fichero_server.db import db_manager
    from fichero_server.knowledge import spacy_ner
    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document
    from fichero_server.workflows.runtime import build_initial_state
    from fichero_server.workflows.tools import extract_entities_only as names
    from tests.integration._seedlib import seed

    from fichero_server.models.source_declarations import project_facts
    from fichero_server.recipes.project import write_project_setup

    library = tmp_path / "caciques.fichero"
    seed(library)
    write_project_setup(library, {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"]}, None)
    db = db_manager.get_database(library)
    assert project_facts(db).language == "Spanish"
    db.save(Document(id="p1", name="42_Hoja.JPG", doc_type=DocType.page, page_content=NOISE))
    asked: list[str] = []
    monkeypatch.setattr(spacy_ner, "extract_entities",
                        lambda text, language=None, model=None, **k: asked.append(language) or [])
    state = build_initial_state({"selected_doc_ids": ["p1"]}, library_path=str(library))
    result = await names.extract_entities_only({"documents": [{"id": "p1"}]}, state,
                                               LLMConfig(provider="spacy", model="es_core_news_sm"))
    assert result["summary"]["languages_used"] == {"Spanish": 1}, result["summary"]
