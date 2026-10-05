"""Health names every runtime a recipe step needs when it is missing, with what needs it (#5493).

WHY: a dev engine ran on a venv without kraken, spaCy (+ es_core_news_sm) or iso639. The recipe run
failed ("Kraken is not bundled in this build"), people/places refused to start, setup's language
search could not load, and `health.missing_dependencies` said nothing was missing for any of them.
Health now asks the same checks those steps refuse on, so it cannot say "nothing missing" when a
job will fail for want of one -- without importing spaCy, which it must not load in every engine.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

import fichero_server.api.main as main
from fichero_server.knowledge.spacy_svo import MODELS
from fichero_server.llm import kraken_runtime, local_models

_KRAKEN = "kraken (needed for finding and reading lines (Kraken))"


def _health(client) -> list[str]:
    return client.get("/api/health").json()["missing_dependencies"]


@pytest.fixture
def probes(monkeypatch):
    """Every probe says present; a test adds the module names it means to be absent."""
    main._reset_dependency_report()
    absent: set[str] = set()
    real = importlib.util.find_spec
    faked = set(main._REQUIRED_BY_NAME) | set(MODELS.values())

    def find_spec(name, *a):
        if name in absent:
            return None
        return object() if name in faked else real(name, *a)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    monkeypatch.setattr(local_models, "spacy_pipeline_path", lambda name: None)  # nothing in the store
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: True)
    monkeypatch.setattr(local_models, "_spacy_runtime_available", lambda: True)
    yield absent
    main._reset_dependency_report()


def test_kraken_spacy_its_pipeline_and_iso639_are_named_when_their_probes_say_absent(client, monkeypatch, probes):
    """The #5493 venv: each is listed, each with the work that needs it."""
    probes.update({"iso639", "es_core_news_sm"})
    monkeypatch.setattr(kraken_runtime, "is_installed", lambda: False)
    monkeypatch.setattr(local_models, "_spacy_runtime_available", lambda: False)

    assert _health(client) == [
        "es_core_news_sm (needed for people and places in 'es' sources)",
        "iso639 (needed for setup's language search)",
        _KRAKEN,
        "spacy (needed for people and places, and the grammar gate (spaCy))",
    ]


def test_nothing_is_listed_when_every_probe_says_present(client, probes):
    """An empty list is a claim that no job will fail for want of a package; it must be earned."""
    assert _health(client) == []


def test_a_pipeline_in_the_model_store_is_not_missing(client, monkeypatch, probes):
    """Steps load a downloaded pipeline from the store first (`runtime.spacy.store-first`)."""
    probes.update(MODELS.values())
    monkeypatch.setattr(local_models, "spacy_pipeline_path", lambda name: Path("/store") / name)
    assert _health(client) == []


def test_health_does_not_import_spacy():
    """spaCy's own model listing imports spaCy (~2 s); health answers on the event loop (#5228) and
    must not load it in every engine, the shipped one included."""
    code = (
        "import sys\n"
        "import fichero_server.api.main as m\n"
        "assert 'spacy' not in sys.modules, 'imported before health'\n"
        "m._missing_required_modules()\n"
        "print('spacy' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == "False"
