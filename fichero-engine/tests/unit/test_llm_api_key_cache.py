"""Unit tests for the process-level resolved-API-key cache (#2545, M1).

The resolved API key is part of the LangChain model-cache key, so it is
resolved BEFORE every model-cache lookup. Without a cache that means a
synchronous Keychain round-trip on every LLM call — hundreds of thousands of
them across a 100k-image run. These tests pin the cache behaviour:

* a second resolution for the same provider does NOT re-hit the Keychain,
* ``clear_api_key_cache()`` forces a fresh read,
* different providers are cached separately (no collision),
* a missing key (None) is cached too (not re-read every call).
"""

import pytest

import fichero.llm as llm


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test starts and ends with an empty key cache."""
    llm.clear_api_key_cache()
    yield
    llm.clear_api_key_cache()


def test_same_provider_hits_keychain_once(monkeypatch):
    calls = {"n": 0}

    def fake_keychain_get(provider):
        calls["n"] += 1
        return f"key-for-{provider}"

    monkeypatch.setattr("fichero.security.keychain.get_api_key", fake_keychain_get)

    first = llm.get_api_key("openai")
    second = llm.get_api_key("openai")

    assert first == "key-for-openai"
    assert second == "key-for-openai"
    # Second resolution served from cache — Keychain read exactly once.
    assert calls["n"] == 1


def test_clear_forces_fresh_read(monkeypatch):
    calls = {"n": 0}

    def fake_keychain_get(provider):
        calls["n"] += 1
        # Simulate a rotated credential between reads.
        return f"key-{calls['n']}"

    monkeypatch.setattr("fichero.security.keychain.get_api_key", fake_keychain_get)

    assert llm.get_api_key("openai") == "key-1"
    assert llm.get_api_key("openai") == "key-1"  # cached
    assert calls["n"] == 1

    llm.clear_api_key_cache("openai")

    assert llm.get_api_key("openai") == "key-2"  # re-read after invalidation
    assert calls["n"] == 2


def test_clear_all_forces_fresh_read(monkeypatch):
    calls = {"n": 0}

    def fake_keychain_get(provider):
        calls["n"] += 1
        return f"key-{provider}-{calls['n']}"

    monkeypatch.setattr("fichero.security.keychain.get_api_key", fake_keychain_get)

    llm.get_api_key("openai")
    llm.get_api_key("anthropic")
    assert calls["n"] == 2

    llm.clear_api_key_cache()  # clear everything

    llm.get_api_key("openai")
    llm.get_api_key("anthropic")
    assert calls["n"] == 4


def test_different_providers_do_not_collide(monkeypatch):
    def fake_keychain_get(provider):
        return f"key-for-{provider}"

    monkeypatch.setattr("fichero.security.keychain.get_api_key", fake_keychain_get)

    openai_key = llm.get_api_key("openai")
    anthropic_key = llm.get_api_key("anthropic")

    assert openai_key == "key-for-openai"
    assert anthropic_key == "key-for-anthropic"
    assert openai_key != anthropic_key


def test_missing_key_is_cached(monkeypatch):
    calls = {"n": 0}

    def fake_keychain_get(provider):
        calls["n"] += 1
        return None

    monkeypatch.setattr("fichero.security.keychain.get_api_key", fake_keychain_get)
    # Make sure the env fallback also yields nothing for a deterministic None.
    monkeypatch.setattr(
        "fichero.providers.get_provider_info", lambda provider: None
    )

    assert llm.get_api_key("openai") is None
    assert llm.get_api_key("openai") is None
    # None is cached — the underlying Keychain read happens only once.
    assert calls["n"] == 1


class TestKeychainWriteInvalidatesCache:
    """A Keychain set/delete busts the llm cache so a rotated key takes effect
    immediately, no process restart (#2545 follow-up — wired in keychain.py)."""

    def test_set_api_key_invalidates_cache(self, monkeypatch):
        import fichero.security.keychain as keychain

        reads = {"n": 0}

        def fake_read(provider):
            reads["n"] += 1
            return f"key-{reads['n']}"

        monkeypatch.setattr(llm, "_read_api_key_uncached", fake_read)
        assert llm.get_api_key("openai") == "key-1"
        assert llm.get_api_key("openai") == "key-1"  # cached
        assert reads["n"] == 1

        # Simulate a successful keychain write (mock the macOS plumbing).
        monkeypatch.setattr(keychain, "_is_macos", lambda: True)
        monkeypatch.setattr(keychain, "_run_security", lambda *a: (0, "", ""))
        assert keychain.set_api_key("openai", "rotated") is True

        # Cache was busted → next resolve reads fresh.
        assert llm.get_api_key("openai") == "key-2"
        assert reads["n"] == 2

    def test_delete_api_key_invalidates_cache(self, monkeypatch):
        import fichero.security.keychain as keychain

        reads = {"n": 0}
        monkeypatch.setattr(
            llm, "_read_api_key_uncached", lambda p: f"key-{reads.__setitem__('n', reads['n'] + 1) or reads['n']}"
        )
        assert llm.get_api_key("anthropic") == "key-1"
        assert reads["n"] == 1

        monkeypatch.setattr(keychain, "_is_macos", lambda: True)
        monkeypatch.setattr(keychain, "_run_security", lambda *a: (0, "", ""))
        assert keychain.delete_api_key("anthropic") is True

        assert llm.get_api_key("anthropic") == "key-2"
        assert reads["n"] == 2
