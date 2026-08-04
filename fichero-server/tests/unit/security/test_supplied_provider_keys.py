"""App-supplied provider keys, held in memory only (#4534).

Daniel's decision: the app owns the keychain item and the engine never reads a
keychain. The app is code-signed and stable across reboots and engine rebuilds;
the engine's executable path moves between Dev and Release and on every rebuild,
and an ACL can only be as stable as the identity it names.

The fourth state is the point of these tests. `absent` means the keychain has
nothing; `not_supplied` means no app has handed the engine a key. Reporting the
second as the first would tell a user with a perfectly good key in the app that
they have no key — the same collapse `test_keychain_read_states.py` exists to
prevent, one layer up.
"""

from __future__ import annotations

import logging

import pytest

from fichero_server.security import provider_keys
from fichero_server.security.keychain import ProviderKeyState


@pytest.fixture(autouse=True)
def _clear_supplied():
    """The store is process-global by design (one engine, one set of keys), so
    each test must start and end clean or they leak into each other."""
    for name in list(provider_keys.supplied_providers()):
        provider_keys.forget_api_key(name)
    yield
    for name in list(provider_keys.supplied_providers()):
        provider_keys.forget_api_key(name)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


def test_supplied_key_is_readable_back():
    provider_keys.supply_api_key("openrouter", "sk-or-v1-test")

    assert provider_keys.supplied_api_key("openrouter") == "sk-or-v1-test"
    assert provider_keys.has_supplied_api_key("openrouter") is True


def test_provider_name_is_normalized():
    """The app and the engine must agree on the key regardless of casing or
    stray whitespace — a mismatch here would present as "supplied it, still
    says not supplied", which is the worst possible symptom for this feature."""
    provider_keys.supply_api_key("  OpenRouter  ", "sk-test")

    assert provider_keys.supplied_api_key("openrouter") == "sk-test"
    assert provider_keys.supplied_api_key("OPENROUTER") == "sk-test"


def test_resupply_replaces_rather_than_erroring():
    """Re-supply on reconnect is the NORMAL path (the app pushes on every
    connect), not an error and not a duplicate."""
    provider_keys.supply_api_key("openrouter", "old")
    provider_keys.supply_api_key("openrouter", "new")

    assert provider_keys.supplied_api_key("openrouter") == "new"
    assert sorted(provider_keys.supplied_providers()) == ["openrouter"]


def test_empty_key_or_provider_is_ignored():
    """Edge case: an empty supply must not create a phantom entry that then
    reports FOUND with nothing behind it."""
    provider_keys.supply_api_key("openrouter", "")
    provider_keys.supply_api_key("", "sk-test")

    assert provider_keys.supplied_providers() == frozenset()


def test_forget_reports_whether_it_held_one():
    provider_keys.supply_api_key("openrouter", "sk-test")

    assert provider_keys.forget_api_key("openrouter") is True
    assert provider_keys.forget_api_key("openrouter") is False
    assert provider_keys.has_supplied_api_key("openrouter") is False


def test_supplied_providers_snapshot_cannot_mutate_the_store():
    provider_keys.supply_api_key("openrouter", "sk-test")

    snapshot = provider_keys.supplied_providers()
    assert isinstance(snapshot, frozenset)

    provider_keys.forget_api_key("openrouter")
    # The snapshot is stale, which is fine — what matters is that holding it
    # did not keep the secret alive in the store.
    assert provider_keys.has_supplied_api_key("openrouter") is False


def test_the_key_is_never_logged(caplog):
    """A credential in the log is a credential on disk. The provider name and
    the fact of supply are the useful diagnostics; the secret is not."""
    secret = "sk-or-v1-DO-NOT-LOG-ME"

    with caplog.at_level(logging.DEBUG, logger=provider_keys.__name__):
        provider_keys.supply_api_key("openrouter", secret)

    assert caplog.records, "supplying a key must leave a diagnostic line"
    for record in caplog.records:
        assert secret not in record.getMessage()
    assert any("openrouter" in r.getMessage() for r in caplog.records)


def test_nothing_is_persisted(tmp_path, monkeypatch):
    """The whole point: no file anywhere. A second persisted copy would be a
    second lifetime and a second thing to go stale."""
    monkeypatch.chdir(tmp_path)
    provider_keys.supply_api_key("openrouter", "sk-test")

    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# The fourth state
# ---------------------------------------------------------------------------


def test_not_supplied_is_a_distinct_state_from_absent():
    assert ProviderKeyState.NOT_SUPPLIED is not ProviderKeyState.ABSENT
    assert ProviderKeyState.NOT_SUPPLIED.value == "not_supplied"


def test_the_remedy_names_an_action_not_just_a_state():
    """A CLI or MCP user has no way to guess that the answer is "open the app
    once", so the answer travels with the state (manager condition 2)."""
    remedy = provider_keys.NO_APP_REMEDY

    assert "Open Fichero" in remedy
    assert "retry" in remedy.lower()
    # And it must not strand a headless caller who has no app at all.
    assert "environment variable" in remedy.lower()


# ---------------------------------------------------------------------------
# Resolution order
# ---------------------------------------------------------------------------


def test_supplied_key_wins_over_the_keychain(monkeypatch):
    """A running app's push is fresher than anything on disk, and the engine is
    meant to stop reading keychains at all."""
    from fichero_server import llm

    llm.clear_api_key_cache()
    monkeypatch.setattr(
        "fichero_server.security.keychain.get_api_key", lambda p: "from-keychain"
    )
    provider_keys.supply_api_key("openai", "from-app")

    assert llm.get_api_key("openai") == "from-app"
    llm.clear_api_key_cache()


def test_falls_through_to_the_keychain_when_nothing_supplied(monkeypatch):
    """The cutover is the app STARTING to supply, not a flag day — an engine no
    app has pushed to must keep working."""
    from fichero_server import llm

    llm.clear_api_key_cache()
    monkeypatch.setattr(
        "fichero_server.security.keychain.get_api_key", lambda p: "from-keychain"
    )

    assert llm.get_api_key("openai") == "from-keychain"
    llm.clear_api_key_cache()


def test_supplying_a_key_busts_the_resolution_cache(monkeypatch):
    """Side effect that must happen: llm.py caches resolved keys process-wide
    (#2545). Without the bust, a key supplied after the first resolution would
    not take effect until a restart — which is exactly the window this design
    is supposed to close."""
    from fichero_server import llm

    llm.clear_api_key_cache()
    monkeypatch.setattr("fichero_server.security.keychain.get_api_key", lambda p: None)
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")

    assert llm.get_api_key("openai") == "from-env"

    provider_keys.supply_api_key("openai", "from-app")
    assert llm.get_api_key("openai") == "from-app", (
        "a supplied key must take effect immediately, not after a restart"
    )

    provider_keys.forget_api_key("openai")
    assert llm.get_api_key("openai") == "from-env", (
        "forgetting must also bust the cache, or a deleted key keeps working"
    )
    llm.clear_api_key_cache()
