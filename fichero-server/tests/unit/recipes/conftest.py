"""Recipe tests run Start with fake engines; a pinned Kraken reader counts as on this Mac unless a test says
otherwise (`source.recipe.missing-model-offered` now refuses Start without it, as it should in the app;
`test_kraken_reader_offered_before_start.py` is where its absence is the subject). Only the Start plan's view
is changed: the bake-off and reader-card tests still see what is really downloaded."""

import pytest


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
