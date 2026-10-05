"""Health names every runtime a recipe step needs when it is missing, with what needs it (#5493).

WHY: a dev engine ran on a venv without kraken, spaCy (+ es_core_news_sm) or iso639. The recipe run
failed ("Kraken is not bundled in this build"), people/places refused to start, setup's language
search could not load, and `health.missing_dependencies` said nothing was missing for any of them.
Health now asks the same checks those steps refuse on, so it cannot say "nothing missing" when a
job will fail for want of one.
"""
from __future__ import annotations

import importlib.util
import threading

import pytest

import fichero_server.api.main as main
from fichero_server.llm import kraken_runtime, local_models

_KRAKEN = "kraken (needed for finding and reading lines (Kraken))"


def _settled_health(client) -> list[str]:
    """Health's list once the off-loop spaCy pipeline check has finished."""
    main._missing_spacy_pipelines()  # starts the check if no health call has yet
    main._spacy_pipelines_check.result(timeout=60)
    return client.get("/api/health").json()["missing_dependencies"]


@pytest.fixture
def probes(monkeypatch):
    """Every probe says present; a test flips the ones it means to be absent."""
    main._reset_dependency_report()
    absent_modules: set[str] = set()
    real = importlib.util.find_spec

    def find_spec(name, *a):
        if name in absent_modules:
            return None
        return object() if name in main._REQUIRED_BY_NAME else real(name, *a)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
    monkeypatch.setattr(local_models, "_spacy_runtime_available", lambda: True)
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: True)
    yield absent_modules
    main._reset_dependency_report()


def test_kraken_spacy_its_pipeline_and_iso639_are_named_when_their_probes_say_absent(client, monkeypatch, probes):
    """The #5493 venv: each is listed, each with the work that needs it."""
    probes.add("iso639")
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)
    monkeypatch.setattr(local_models, "_spacy_runtime_available", lambda: False)
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: name != "es_core_news_sm")

    assert _settled_health(client) == [
        "es_core_news_sm (needed for people and places in 'es' sources)",
        "iso639 (needed for setup's language search)",
        _KRAKEN,
        "spacy (needed for people and places, and the grammar gate (spaCy))",
    ]


def test_nothing_is_listed_when_every_probe_says_present(client, probes):
    """An empty list is a claim that no job will fail for want of a package; it must be earned."""
    assert _settled_health(client) == []


def test_health_does_not_wait_for_the_spacy_pipeline_check(client, monkeypatch, probes):
    """spaCy's installed-model listing imports spaCy (~2 s); health answers on the event loop (#5228)
    and must not block on it. Until that check finishes the cheap probes are still reported, and
    the pipelines join the list once it has."""
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)
    release = threading.Event()
    monkeypatch.setattr(local_models, "spacy_pipeline_available", lambda name: not release.wait(30))
    try:
        first = client.get("/api/health").json()["missing_dependencies"]
    finally:
        release.set()
    assert first == [_KRAKEN]
    assert _settled_health(client) == [
        "en_core_web_sm (needed for people and places in 'en' sources)",
        "es_core_news_sm (needed for people and places in 'es' sources)",
        _KRAKEN,
    ]
