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


def test_an_absent_key_is_cached_too_and_an_unreadable_one_is_kept_5_seconds_then_asked_again_off_the_thread(monkeypatch):
    """`activity.engine.keychain-cached` (435, reviewed 440): a refusal is kept `_UNREADABLE_SECONDS` (so a locked keychain
    does not run `security` on the caller each time), and after that it is re-read on a thread of its own, the caller
    getting the old answer at once."""
    import time

    calls = _security(monkeypatch, [(44, "", "not found")])
    assert keychain.lookup_api_key("a").state is keychain.ProviderKeyState.ABSENT
    keychain.lookup_api_key("a")
    assert len(calls) == 1
    calls2 = _security(monkeypatch, [(51, "", "refused")])
    assert keychain.lookup_api_key("b").state is keychain.ProviderKeyState.UNREADABLE
    keychain.lookup_api_key("b")
    assert len(calls2) == 1  # within the 5 s: kept, no second `security`
    monkeypatch.setattr(keychain, "_UNREADABLE_SECONDS", 0.0)  # the 5 s are over
    assert keychain.lookup_api_key("b").state is keychain.ProviderKeyState.UNREADABLE  # the old answer, at once
    deadline = time.monotonic() + 5
    while len(calls2) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(calls2) == 2  # asked again, on the refresh thread


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


def test_an_unreadable_keychain_replaces_the_old_found_answer_and_a_repeat_runs_no_subprocess_on_the_caller(monkeypatch):
    """#4534 + 435: the keychain locks after a key was read; the refresh says UNREADABLE, the old FOUND is not served on,
    and while it stays locked a repeat lookup is a cache hit (a refusal is kept ~5 s), never `security` on the caller."""
    from fichero_server.security.keychain import ProviderKeyState

    threads: list[int] = []
    answers = [(0, "sk-1\n", ""), (36, "", "User interaction is not allowed.")]

    def run(*args, input_data=None):
        threads.append(threading.get_ident())
        return answers.pop(0) if len(answers) > 1 else answers[0]

    monkeypatch.setattr(keychain, "_run_security", run)
    assert keychain.lookup_api_key("openai").state is ProviderKeyState.FOUND
    monkeypatch.setattr(keychain, "_LOOKUP_SECONDS", -1.0)  # the kept answer is stale
    assert keychain.lookup_api_key("openai").state is ProviderKeyState.FOUND  # served once; re-read on a thread
    for _ in range(200):
        kept = keychain._LOOKUPS.get("openai")
        if kept is not None and kept[1].state is ProviderKeyState.UNREADABLE:
            break
        threading.Event().wait(0.02)
    before = len(threads)
    for _ in range(3):  # locked: every repeat is answered from the cache
        assert keychain.lookup_api_key("openai").state is ProviderKeyState.UNREADABLE
    assert len(threads) == before, "a repeat lookup ran `security` again"
    assert all(t != threading.get_ident() for t in threads[1:]), "the refresh ran off the calling thread"


def test_a_found_answer_is_kept_for_a_short_while_only():
    assert keychain._LOOKUP_SECONDS <= 30.0


def test_the_children_route_counts_through_the_off_the_loop_helper(client, db, monkeypatch):
    """The route itself, not only the helper: `GET /api/documents/{id}/children` hands its rows to
    `_child_counts_off_the_loop` (documents.py), so a count behind a write never holds the event loop."""
    from fichero_server.api.routes.document import documents
    from fichero_server.models import DocType, Document

    parent = Document(name="folder", doc_type=DocType.folder)
    db.save(parent)
    db.save(Document(name="page", doc_type=DocType.file, parent_id=parent.id))
    asked: list[int] = []
    real = documents._child_counts_off_the_loop

    async def spy(db_, items):
        asked.append(len(items))
        return await real(db_, items)

    monkeypatch.setattr(documents, "_child_counts_off_the_loop", spy)
    response = client.get(f"/api/documents/{parent.id}/children")
    assert response.status_code == 200, response.text
    assert asked == [1]
