"""#2538: the launcher must loudly flag a plain-HTTP engine on the app's
pinned port, instead of leaving the app with a silently dead Activity stream.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest

_LAUNCHER = (
    Path(__file__).resolve().parents[2] / "scripts" / "start_backend.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("start_backend", _LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_warns_on_plain_http_on_app_port(caplog):
    mod = _load()
    with caplog.at_level(logging.WARNING):
        mod._warn_if_app_unreachable("http", mod.APP_LOOPBACK_PORT)
    assert any(
        "silently fail" in r.message and "#2538" in r.message
        for r in caplog.records
    ), "plain HTTP on the pinned app port must warn loudly"


@pytest.mark.parametrize(
    "scheme,port",
    [
        ("https", 8765),  # correct: TLS on the app port
        ("http", 9000),  # plain HTTP on some other (non-app) port is fine
    ],
)
def test_no_warning_when_scheme_matches_or_other_port(scheme, port, caplog):
    mod = _load()
    with caplog.at_level(logging.WARNING):
        mod._warn_if_app_unreachable(scheme, port)
    assert not caplog.records, f"unexpected warning for {scheme}:{port}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
