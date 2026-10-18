"""A fake spaCy pipeline loaded by one test must not be served to the next: the pipeline caches are process-wide
(`local_models` keeps the one pipeline per model, `spacy_ner._pipelines`, `spacy_svo._pipeline`), so a test that
fakes `spacy.load` left an `object()` that a later test's parse then called ('object' object is not callable) or
that stopped a later fake loader from running (KeyError 'last')."""
import pytest


@pytest.fixture(autouse=True)
def _no_spacy_pipeline_carried_between_tests():
    def clear():
        from fichero_server.knowledge import spacy_ner, spacy_svo
        from fichero_server.llm import local_models

        local_models.clear_spacy_pipelines()
        spacy_ner._pipelines.clear()
        for cached in (spacy_svo._pipeline, spacy_svo._page_morphology):
            if hasattr(cached, "cache_clear"):  # a test may have replaced it with a plain function
                cached.cache_clear()

    clear()
    yield
    clear()
