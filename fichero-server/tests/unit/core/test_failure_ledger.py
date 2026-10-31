"""The failure ledger counts WARNING+ by template and turns a repeat into a plain-language `degraded` entry in
`GET /api/health` (`engine.silent.ledger-*`, `engine.silent.health-lists-degraded`; spec: source/engine-silent-failures.md)."""

from __future__ import annotations

import logging

import pytest

from fichero_server.core import failure_ledger as ledger
from fichero_server.models import Document, HealthResponse


@pytest.fixture(autouse=True)
def _clean():
    ledger.reset()
    yield
    ledger.reset()


def _hit(n: int, *, start: float = 1000.0, step: float = 1.0, area: str = "search", kind: str = "ValueError") -> None:
    for i in range(n):
        ledger.note(area, "embed", kind, sentence="Search is not indexing new pages: the search model cannot be loaded",
                    now=start + i * step)


def test_below_both_thresholds_is_not_degraded():
    _hit(19)
    assert ledger.degraded(now=1020.0) == []


def test_rate_threshold_degrades():
    _hit(20)  # 20 in 19 seconds
    [entry] = ledger.degraded(now=1020.0)
    assert entry.area == "search" and entry.count == 20


def test_slow_repeats_below_the_rate_do_not_degrade_until_the_total():
    _hit(199, step=30.0)  # 2 a minute: never 20 in a minute
    assert ledger.degraded(now=1000.0 + 199 * 30.0) == []
    _hit(1, start=1000.0 + 199 * 30.0)
    assert len(ledger.degraded(now=1000.0 + 199 * 30.0)) == 1


def test_total_threshold_degrades():
    _hit(200, step=10.0)
    assert ledger.degraded(now=3000.0)[0].count == 200


def test_quiet_period_clears():
    _hit(20)
    assert ledger.degraded(now=1020.0 + 299)
    assert ledger.degraded(now=1020.0 + 301) == []


def test_reason_is_plain_and_carries_no_path_or_id():
    _hit(20, kind="OSError")
    reason = ledger.degraded(now=1020.0)[0].reason
    assert reason.startswith("Search is not indexing new pages: the search model cannot be loaded (OSError). 20 failures since ")
    assert "/" not in reason.split("since")[0]


def test_counts_by_template_not_text():
    handler = ledger.LedgerHandler()
    log = logging.getLogger("fichero_server.db")
    for doc_id in ("71470c7dc13a4b93b769366ed70dd488", "4e7e7a018c66422699f9846522329cb0"):
        handler.handle(log.makeRecord(log.name, logging.WARNING, __file__, 1, "Failed to create embedding for %s: %s", (doc_id, "x"), None))
    assert ledger.counts() == {"fichero_server.db|Failed to create embedding for %s: %s": 2}


def test_a_collapsed_summary_adds_its_count():
    handler = ledger.LedgerHandler()
    log = logging.getLogger("fichero_server.db")
    template = "Failed to create embedding for %s: %s"
    handler.handle(log.makeRecord(log.name, logging.WARNING, __file__, 1, template, ("a", "x"), None))
    handler.handle(log.makeRecord(log.name, logging.WARNING, __file__, 1, "%s — repeated %d times in the last minute", (template, 6000), None))
    assert ledger.counts()[f"fichero_server.db|{template}"] == 6001


def test_info_is_not_counted():
    handler = ledger.LedgerHandler()
    log = logging.getLogger("x")
    handler.handle(log.makeRecord(log.name, logging.INFO, __file__, 1, "fine", (), None))
    assert ledger.counts() == {}


def test_note_never_raises_and_is_bounded():
    for i in range(50_000):
        ledger.note("search", "embed", "ValueError", now=1000.0 + i)
    assert ledger.counts()["search|embed|ValueError"] == 50_000
    assert len(ledger._ENTRIES["search|embed|ValueError"].recent) <= ledger.RATE_COUNT
    ledger.note(None, None, None)  # type: ignore[arg-type]


def test_the_ledger_holds_at_most_500_signatures():
    for i in range(ledger.MAX_SIGNATURES + 50):
        ledger.note("search", f"site{i}", "ValueError", now=1000.0)
    assert len(ledger.counts()) == ledger.MAX_SIGNATURES
    ledger.note("search", "site0", "ValueError", now=1001.0)  # a known signature still counts at the cap
    assert ledger.counts()["search|site0|ValueError"] == 2


def test_health_carries_degraded():
    from fichero_server.api import main as api_main

    assert api_main._with_server_proof(HealthResponse(status="healthy"), None).degraded == []
    _hit(20, start=__import__("time").time() - 20)
    health = api_main._with_server_proof(HealthResponse(status="healthy"), None)
    assert health.status == "healthy", "the engine answers; the list is the signal"
    assert [d.area for d in health.degraded] == ["search"]


def test_embedding_failure_degrades_health(tmp_path, monkeypatch):
    """The Air's case: every write's embedding fails, the engine looked healthy."""
    from fichero_server.api import main as api_main
    from fichero_server.db import Database
    from fichero_server.db.embed_process import EmbedderUnavailable

    db = Database(tmp_path / "e.duckdb")
    try:
        monkeypatch.setattr(type(db), "_embedding_text_for_document", lambda *_a, **_k: "some page text")
        monkeypatch.setattr(type(db), "save_passage_embeddings",
                            lambda *_a, **_k: (_ for _ in ()).throw(EmbedderUnavailable("The search model could not be loaded: /Users/bob/x")))
        for i in range(25):
            assert db.embed(Document(name=f"p{i}.txt")).reason == "embedder_unavailable"
        health = api_main._with_server_proof(HealthResponse(status="healthy"), None)
        [entry] = health.degraded
        assert entry.area == "search" and entry.count == 25
        assert "(EmbedderUnavailable)" in entry.reason, entry.reason  # the class the real raise sites give; the spec quotes it
        assert "bob" not in entry.reason and "/Users" not in entry.reason, "health is unauthenticated"
    finally:
        db.close()


def test_a_degraded_id_carries_no_message_text():
    log = logging.getLogger("fichero_server.export_service")
    handler = ledger.LedgerHandler()
    for _ in range(25):
        handler.handle(log.makeRecord(log.name, logging.WARNING, __file__, 1, "Missing original for Some Name at /Some/Fake Path/a.tif", (), None))
    [entry] = ledger.degraded()
    assert len(entry.id) == 12 and "Some" not in entry.id and "/" not in entry.id, entry.id
    assert "Some" not in entry.reason


def test_a_note_made_while_the_lock_is_held_on_the_same_thread_does_not_deadlock():
    import threading

    done = threading.Event()

    def reenter():
        with ledger._LOCK:  # what a finalizer logging a warning mid-count looks like
            ledger.note("search", "embed", "ValueError", now=1000.0)
        done.set()

    threading.Thread(target=reenter, daemon=True).start()
    assert done.wait(5), "deadlocked on its own lock"


def test_degraded_survives_a_note_made_while_it_iterates():
    _hit(25)
    real = ledger._reason

    def reentrant(entry):
        ledger.note("other", "site", "ValueError")  # what a finalizer logging a new signature looks like
        return real(entry)

    ledger._reason = reentrant
    try:
        assert len(ledger.degraded(now=1030.0)) == 1
        assert ledger.counts()
    finally:
        ledger._reason = real


def test_health_still_answers_when_the_ledger_raises(monkeypatch):
    from fichero_server.api import main as api_main

    monkeypatch.setattr(ledger, "degraded", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    health = api_main._with_server_proof(HealthResponse(status="healthy"), None)
    assert health.status == "healthy" and health.degraded == []
