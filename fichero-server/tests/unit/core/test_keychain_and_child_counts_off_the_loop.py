"""The loop stays free of the keychain and of child counts (`activity.engine.keychain-cached`,
`activity.engine.child-counts-off-the-loop`; owner's Dev Embedded 5d323cf97: "Compare on These Pages" spun while
`keychain.lookup_api_key -> _run_security` (a `security` subprocess) and `get_children -> child_counts` held the event
loop 2.5 s)."""
from __future__ import annotations

import asyncio
import threading

import pytest

from fichero_server.security import keychain


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(keychain, "_is_macos", lambda: True)
    keychain.forget_cached_lookups()
    yield
    keychain.forget_cached_lookups()


def _security(monkeypatch, answers):
    calls: list[tuple] = []

    def run(*args, input_data=None):
        calls.append(args)
        return answers.pop(0) if len(answers) > 1 else answers[0]

    monkeypatch.setattr(keychain, "_run_security", run)
    return calls


def test_a_found_key_is_read_from_the_keychain_once(monkeypatch):
    calls = _security(monkeypatch, [(0, "sk-abc\n", "")])
    assert keychain.lookup_api_key("openai").key == "sk-abc"
    assert keychain.lookup_api_key("openai").key == "sk-abc"
    assert len(calls) == 1  # the second lookup spawned no `security` subprocess


def test_an_absent_key_is_cached_too_but_an_unreadable_one_is_asked_again(monkeypatch):
    calls = _security(monkeypatch, [(44, "", "not found")])
    assert keychain.lookup_api_key("a").state is keychain.ProviderKeyState.ABSENT
    keychain.lookup_api_key("a")
    assert len(calls) == 1
    calls2 = _security(monkeypatch, [(51, "", "refused")])
    assert keychain.lookup_api_key("b").state is keychain.ProviderKeyState.UNREADABLE
    keychain.lookup_api_key("b")
    assert len(calls2) == 2  # a refusal may be fixed by the person: not remembered


def test_saving_or_deleting_a_key_drops_the_cached_answer(monkeypatch):
    calls = _security(monkeypatch, [(0, "old\n", "")])
    keychain.lookup_api_key("openai")
    keychain.delete_api_key("openai")
    keychain.lookup_api_key("openai")
    assert len(calls) == 3  # the read, the delete, and a fresh read after it


def test_get_children_counts_children_off_the_loop(monkeypatch):
    from fichero_server.api.routes.document import documents

    seen: list[bool] = []
    main = threading.get_ident()

    def counts(db, items):
        seen.append(threading.get_ident() != main)
        return items

    monkeypatch.setattr(documents, "_with_child_counts", counts)
    asyncio.run(documents._child_counts_off_the_loop(None, []))
    assert seen == [True]


def test_a_stale_answer_is_returned_at_once_and_refreshed_on_a_thread(monkeypatch):
    """Review 306: the first lookup every 5 minutes ran `security` on the loop."""
    calls = _security(monkeypatch, [(0, "sk-1\n", "")])
    keychain.lookup_api_key("openai")
    monkeypatch.setattr(keychain, "_LOOKUP_SECONDS", -1.0)  # everything kept is now stale
    main = threading.get_ident()
    seen: list[bool] = []
    done = threading.Event()
    real = keychain._read_api_key

    def read(provider):
        seen.append(threading.get_ident() != main)
        try:
            return real(provider)
        finally:
            done.set()

    monkeypatch.setattr(keychain, "_read_api_key", read)
    assert keychain.lookup_api_key("openai").key == "sk-1"  # the stale answer, no wait
    assert done.wait(10) and seen == [True]  # re-read on a thread of its own


def test_warming_reads_each_provider_once(monkeypatch):
    calls = _security(monkeypatch, [(44, "", "none")])
    keychain.warm_api_keys(["a", "b"])
    keychain.lookup_api_key("a")
    assert len(calls) == 2


def test_a_read_begun_before_a_save_never_stores_its_old_answer(monkeypatch):
    """Review 309 LOW: a refresh in flight when a key is saved or deleted must not put the old answer back."""
    started, release = threading.Event(), threading.Event()

    def slow_security(*args, input_data=None):
        started.set()
        release.wait(10)
        return (0, "old-key\n", "")

    monkeypatch.setattr(keychain, "_run_security", slow_security)
    out = []
    reader = threading.Thread(target=lambda: out.append(keychain.lookup_api_key("openai")))
    reader.start()
    assert started.wait(10)
    keychain.forget_cached_lookups("openai")  # the key was saved while the read ran
    release.set()
    reader.join(10)
    assert out[0].key == "old-key"  # that caller still gets what it read...
    assert "openai" not in keychain._LOOKUPS  # ...but it was not kept for the next one


def test_startup_warms_only_the_providers_the_person_has_set_up(monkeypatch):
    """Review 309: never probe every provider type (a Keychain dialog per unread legacy item)."""
    from types import SimpleNamespace as NS

    from fichero_server.api import main
    from fichero_server.db import app as app_module

    warmed: list[list[str]] = []
    monkeypatch.setattr(keychain, "warm_api_keys", lambda names: warmed.append(list(names)))
    rows = [NS(provider_type=NS(value="openai"), enabled=True), NS(provider_type=NS(value="anthropic"), enabled=False),
            NS(provider_type=NS(value="mlx"), enabled=True)]
    monkeypatch.setattr(app_module, "get_app_db", lambda: NS(list_providers=lambda: rows))
    from fichero_server.llm import providers

    monkeypatch.setattr(providers, "get_provider_info", lambda t: NS(is_local=(t == "mlx")))
    main._warm_configured_provider_keys()
    assert warmed == [["openai"]]  # enabled and not on-device; the disabled and the local ones are not asked
