"""`source.onboard.ready-speaks-plainly` (#5801, the owner's Set Up › Ready test of the staged c13efa580): every line
Ready shows names a step by its title and a model by its name, never an id ("steps find-lines, read-a-line",
"kraken-zenodo-21788410", "step find-statements"); a Kraken reader's size comes from its card when the repository
listing has none; a step that waits for another's model says what to do in the sentence.

WHY: the plan's sentences were built from step ids and model ids, the Kraken reader said "size not stated" though
its card states 60 MB, and "Will not run: Find statements" said only that it waited for a step id.
"""

from __future__ import annotations

import pytest

from fichero_server.recipes.start import plan_start
from tests.unit.recipes.test_kraken_reader_offered_before_start import LINES, READ, READER

RAW = ("find-lines", "read-a-line", "find-statements", "find-names-tag-words", READER, "step ")


def _plain(sentence: str) -> None:
    assert not any(raw in sentence for raw in RAW), sentence


def test_a_reader_downloading_is_waited_for_by_the_steps_titles(monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", lambda name: False)
    lines = {**LINES, "id": "find-lines", "title": "Find lines"}
    read = {**READ, "id": "read-a-line", "title": "Read each line"}
    plan = plan_start({"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": [lines, read]},
                      stays_local=True)
    (download,) = plan["downloads"]
    download.update(downloading=True, progress=None)

    said = start._downloading(download)

    assert said.startswith("Find lines and Read each line wait for the Kraken reader PP-OCRv6 (medium)"), said
    _plain(said)


def test_a_kraken_reader_with_no_listed_size_takes_its_cards(monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", lambda name: False)
    monkeypatch.setattr(start, "_repository_record", lambda doi: {})
    (download,) = start.missing_models([{"steps": ["read"], "job": "read-a-line", "card": "workflow",
                                         "provider_override": "kraken", "model_override": READER}])
    assert download["size_mb"] == 60, download
    assert "size not stated" not in start.start_downloads([download])["sentence"]


def test_a_step_that_waits_for_another_says_what_to_do_by_name():
    """"Will not run: Find statements": it waits for Find names, which has no model; the sentence names both and
    says to choose a model for Find names (the step's own fix button would choose one for Find statements)."""
    recipe = {"fichero_recipe": 1, "id": "t", "version": "0.1.0", "title": "t", "steps": [
        {**LINES, "id": "find-lines", "title": "Find lines"},
        {**READ, "id": "read-a-line", "title": "Read each line"},
        {"id": "find-names-tag-words", "job": "find-names-tag-words", "title": "Find names", "model": None,
         "problem": {"sentence": "Fichero has no model for “Find names” yet."}},
        {"id": "find-statements", "job": "find-statements", "title": "Find statements",
         "model": {"spacy": "es_core_news_sm", "version": "bundled"}},
    ]}

    plan = plan_start(recipe, stays_local=True)

    (waits,) = [s for s in plan["skipped"] if s["step"] == "find-statements"]
    assert waits["why"] == ("Find statements waits for Find names, which has no model yet: choose a model for "
                            "Find names, and Find statements runs after it"), waits
    assert waits["fix"] is None
    for skipped in plan["skipped"]:
        _plain(skipped["why"])


def test_a_kraken_reader_not_here_is_named_and_never_told_to_download_first(monkeypatch):
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(kraken_runtime, "recognition_model_path", lambda ref: None)
    with pytest.raises(RuntimeError) as refused:
        kraken_runtime.resolve_recognition_model(READER)
    said = str(refused.value)
    assert "PP-OCRv6 (medium)" in said and "download it first" not in said.lower(), said
    _plain(said)
