"""#2869 B1 — the ingest API must be able to request MOVE.

Before the fix the request models only carried `copy_mode: bool`, so a MOVE
import silently degraded to LINK (copy_mode=False ⇒ LINK). The new `mode`
field makes all three IngestModes reachable and fails loudly on a bad value
instead of falling back to LINK.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero.api.routes.ingest import _resolve_ingest_mode
from fichero.ingest import IngestMode


def test_mode_move_is_reachable():
    # The whole point of #2869 B1: MOVE was impossible through copy_mode.
    assert _resolve_ingest_mode("move", False) is IngestMode.MOVE


@pytest.mark.parametrize(
    "value,expected",
    [
        ("link", IngestMode.LINK),
        ("copy", IngestMode.COPY),
        ("move", IngestMode.MOVE),
        ("MOVE", IngestMode.MOVE),  # case-insensitive
        (" copy ", IngestMode.COPY),  # trimmed
    ],
)
def test_mode_string_wins(value, expected):
    # Even with copy_mode=True, an explicit mode overrides the legacy bool.
    assert _resolve_ingest_mode(value, True) is expected


def test_invalid_mode_raises_not_silent_link():
    with pytest.raises(HTTPException) as exc:
        _resolve_ingest_mode("teleport", False)
    assert exc.value.status_code == 400
    assert "teleport" in exc.value.detail


@pytest.mark.parametrize(
    "copy_mode,expected",
    [(True, IngestMode.COPY), (False, IngestMode.LINK)],
)
def test_legacy_copy_mode_fallback(copy_mode, expected):
    # Older callers with no `mode` keep the exact link/copy behaviour.
    assert _resolve_ingest_mode(None, copy_mode) is expected
