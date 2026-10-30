"""`engine.repeated-log-line-collapses` (owner 2026-10-30): 380,611 copies of one warning filled engine.log.
If this regresses, one failing loop can write a log line without bound again."""

from __future__ import annotations

import logging

from fichero_server.core.log_throttle import RepeatCollapser, log_collapsed


def test_after_the_limit_repeats_are_held_back_then_summarised_once():
    collapser = RepeatCollapser(limit=3, window_s=60)
    outcomes = [collapser.admit("tmpl", now=float(n)) for n in range(10)]
    assert [o.write for o in outcomes] == [True] * 3 + [False] * 7
    assert all(o.summary is None for o in outcomes)
    after = collapser.admit("tmpl", now=61.0)
    assert after.write is True and after.summary == 7          # ONE summary, riding on the next occurrence
    assert collapser.admit("tmpl", now=62.0).summary is None


def test_different_templates_do_not_share_a_budget():
    collapser = RepeatCollapser(limit=1, window_s=60)
    assert collapser.admit("a", now=0).write and collapser.admit("b", now=0).write
    assert not collapser.admit("a", now=1).write


def test_a_quiet_minute_resets_without_a_summary():
    collapser = RepeatCollapser(limit=2, window_s=60)
    collapser.admit("t", now=0)
    collapser.admit("t", now=1)
    later = collapser.admit("t", now=100)
    assert later.write and later.summary is None


def test_log_collapsed_writes_the_arguments_and_the_summary(caplog):
    collapser = RepeatCollapser(limit=2, window_s=60)
    logger = logging.getLogger("throttle-test")
    with caplog.at_level(logging.WARNING, logger="throttle-test"):
        for n in range(6):
            log_collapsed(logger, logging.WARNING, "Failed for %s: %s", f"doc{n}", "boom", collapser=collapser, now=float(n))
        log_collapsed(logger, logging.WARNING, "Failed for %s: %s", "doc9", "boom", collapser=collapser, now=70.0)
    messages = [r.getMessage() for r in caplog.records]
    assert messages[:2] == ["Failed for doc0: boom", "Failed for doc1: boom"]
    assert messages[2] == "Failed for %s: %s — repeated 4 times in the last minute"
    assert messages[3] == "Failed for doc9: boom"
    assert len(messages) == 4
