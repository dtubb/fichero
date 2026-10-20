"""Recipe tests run Start with fake engines; a pinned Kraken reader counts as on this Mac unless a test says
otherwise (`source.recipe.missing-model-offered` now refuses Start without it, as it should in the app;
`test_kraken_reader_offered_before_start.py` is where its absence is the subject). Only the Start plan's view
is changed: the bake-off and reader-card tests still see what is really downloaded."""

import pytest


@pytest.fixture(autouse=True)
def the_model_lane_runs_inline(request, monkeypatch):
    """A unit test has no scheduler thread to run what is handed to the model lane, so a page waiting for its slot waited
    for good (M4, 14f3f1216: `-k regions` hung 300 s in `find_regions`). A recipe test runs the segmenter's call in place;
    a test that asks for `real_model_lane` goes through the real lane and its scheduler."""
    if "real_model_lane" in request.fixturenames:
        return
    from fichero_server.execution import jobs

    monkeypatch.setattr(jobs, "run_on_lane_blocking", lambda library, kind, subject, *, fn, **kw: fn())


@pytest.fixture
def real_model_lane():
    """Ask for this to keep the real model lane (see `the_model_lane_runs_inline`)."""


@pytest.fixture(autouse=True)
def kraken_readers_on_this_mac(monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", lambda name: True)


@pytest.fixture(autouse=True)
def no_remote_compute_account(monkeypatch):
    """The Hub search looks at the person's Hugging Face Jobs account to offer models for remote compute (#5717):
    here there is none, so no test reads this Mac's Keychain or reaches the service. A test of remote compute
    says otherwise (`test_find_remote_models_5717.py`)."""
    from fichero_server.training import hf_jobs

    def no_account(*args, **kwargs):
        raise hf_jobs.NoHuggingFaceToken("No Hugging Face token: add one in Settings (AI providers, Hugging Face).")

    monkeypatch.setattr(hf_jobs, "HfJobsTarget", no_account)


@pytest.fixture(autouse=True)
def cloud_keys_are_there(request, monkeypatch):
    """Every recipe test runs with a key for its cloud pins: a keyless cloud step waits, "Needs a key for <provider>"
    (`source.recipe.missing-key-never-substitutes`, #5364), and tests that pin a cloud checker or reader meant it to run.
    The #5364 tests drive the lookup themselves."""
    if "missing_key_never_substitutes" in request.node.module.__name__:
        return
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "provider_without_key", lambda step: None)
