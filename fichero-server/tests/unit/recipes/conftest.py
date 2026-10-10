"""Recipe tests run Start with fake engines; a pinned Kraken reader counts as on this Mac unless a test says
otherwise (`source.recipe.missing-model-offered` now refuses Start without it, as it should in the app;
`test_kraken_reader_offered_before_start.py` is where its absence is the subject). Only the Start plan's view
is changed: the bake-off and reader-card tests still see what is really downloaded."""

import pytest


@pytest.fixture(autouse=True)
def kraken_readers_on_this_mac(monkeypatch):
    from fichero_server.recipes import start

    monkeypatch.setattr(start, "_kraken_reader_here", lambda name: True)
