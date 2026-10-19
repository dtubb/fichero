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
