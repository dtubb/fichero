"""A unit test never reads the model-registry cache from the person's real Application Support folder (#6108): that file is
refreshed from upstream, so prices and retired models would change between runs and machines."""
from __future__ import annotations

import pytest

from fichero_server.db.paths import default_server_state_dir
from fichero_server.llm import model_types


def test_a_price_lookup_aimed_at_the_real_application_support_folder_fails_naming_the_cause(monkeypatch):
    monkeypatch.setenv("FICHERO_BASE_PATH", str(default_server_state_dir()))
    monkeypatch.setattr(model_types, "_PRICE_TABLE", None)
    with pytest.raises(AssertionError, match="vendored"):
        model_types._price_table()


def test_a_price_lookup_in_the_tests_own_folder_reads_the_vendored_snapshot(monkeypatch):
    monkeypatch.setattr(model_types, "_PRICE_TABLE", None)
    assert not model_types._cached_registry_path().exists()  # the test's folder holds no refreshed cache
    assert model_types._price_table().get("gpt-4o") is not None  # the vendored snapshot answers
