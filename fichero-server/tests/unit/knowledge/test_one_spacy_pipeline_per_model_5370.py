"""NER and SVO share one loaded spaCy pipeline per model (#5370, `runtime.spacy.one-pipeline-per-language`):
the second module to ask for a model gets the object the first loaded, and it is loaded with its lemmatizer."""
from __future__ import annotations

import spacy

from fichero_server.knowledge import spacy_ner, spacy_svo
from fichero_server.llm import local_models


def test_ner_and_svo_get_the_same_loaded_pipeline_for_one_model(monkeypatch):
    loads: list[tuple] = []

    def fake_load(name, **kwargs):
        loads.append((str(name), tuple(kwargs.get("exclude", ()))))
        return object()

    monkeypatch.setattr(spacy, "load", fake_load)
    monkeypatch.setattr(local_models, "spacy_pipeline_path", lambda name: None)
    local_models.clear_spacy_pipelines()
    spacy_svo._pipeline.cache_clear()

    ner = spacy_ner._open(spacy, "en_core_web_sm")
    svo = spacy_svo._pipeline("en")

    assert ner is svo, "one loaded pipeline serves both"
    assert loads == [("en_core_web_sm", ())], "loaded once, with the lemmatizer"
