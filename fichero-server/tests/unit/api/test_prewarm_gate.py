"""The embeddings pre-warm gate is opt-OUT (default on), so production always warms
and only a fresh-home engine (UI test) can skip the blocking model download.

Pinning this keeps the test/production divergence explicit: the ONLY way warming is
skipped is the FICHERO_SKIP_EMBEDDINGS_PREWARM=1 opt-out.
"""

from __future__ import annotations

import importlib


def _gate():
    main = importlib.import_module("fichero_server.api.main")
    return main._should_prewarm_embeddings


def test_prewarm_on_by_default(monkeypatch):
    monkeypatch.delenv("FICHERO_SKIP_EMBEDDINGS_PREWARM", raising=False)
    assert _gate()() is True


def test_prewarm_skipped_only_by_explicit_optout(monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_EMBEDDINGS_PREWARM", "1")
    assert _gate()() is False


def test_other_values_still_warm(monkeypatch):
    # Only the exact "1" opts out; anything else (incl. "0") warms.
    for value in ("0", "", "true", "yes"):
        monkeypatch.setenv("FICHERO_SKIP_EMBEDDINGS_PREWARM", value)
        assert _gate()() is True, value
