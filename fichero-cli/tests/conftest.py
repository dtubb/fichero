"""Test seam for the fichero-cli product tree (#4227).

`pytest fichero-cli/tests` has to work with no PYTHONPATH exported, so this
conftest puts this product's `src/` **and** the server's on `sys.path` — the
CLI imports the server's Pydantic response models directly. It mirrors the
sibling seam in `fichero-server/tests/conftest.py`.

The autouse `isolated_cli_env` fixture is load-bearing, not tidiness: every
connection/auth assertion here reads real process state (`FICHERO_*` env vars,
`~/Library/Application Support/Fichero/.api-key`, `cli-session.json`). Without
the isolation a developer with a running engine gets different results from one
without, which is a test that asserts the machine rather than the code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _src in ("fichero-cli/src", "fichero-server/src"):
    _path = str(_REPO_ROOT / _src)
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Env vars that change which server the CLI dials or which credential it sends.
_CONNECTION_ENV_VARS = (
    "FICHERO_API_URL",
    "FICHERO_API_KEY",
    "FICHERO_SESSION_TOKEN",
    "FICHERO_LIBRARY_PATH",
    "FICHERO_UDS_PATH",
    "FICHERO_BIND_HOST",
    "FICHERO_TLS_CERTFILE",
    "FICHERO_TLS_KEYFILE",
)


def _forbid_the_default_engine(monkeypatch) -> None:
    """No test may open a socket to an engine that could be live (the owner's included): the default address, 127.0.0.1:8765
    under any loopback name, and the address a developer's own FICHERO_API_URL names (read BEFORE the env is cleared). A test
    that needs a server stubs the transport or starts its own on a port of its own. The CLI and MCP twins carry the same guard."""
    import socket
    from urllib.parse import urlparse

    named = {("127.0.0.1", 8765), ("localhost", 8765), ("::1", 8765)}
    live = urlparse(os.environ.get("FICHERO_API_URL") or "")
    if live.hostname:
        named.add((live.hostname, live.port or (443 if live.scheme == "https" else 80)))

    def forbid(real):
        def guarded(self, address, *args, **kwargs):
            if isinstance(address, tuple) and len(address) >= 2 and (address[0], address[1]) in named:
                raise AssertionError(
                    f"a test dialled {address[0]}:{address[1]}, an address a live engine may answer on: stub the transport "
                    "(httpx.MockTransport) or start a server of its own on a free port")
            return real(self, address, *args, **kwargs)
        return guarded

    monkeypatch.setattr(socket.socket, "connect", forbid(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", forbid(socket.socket.connect_ex))


@pytest.fixture(autouse=True)
def isolated_cli_env(monkeypatch, tmp_path_factory):
    """Clear connection env vars and redirect the on-disk credential paths.

    The credentials live in their own temp dir, never in the test's tmp_path: in the full run this autouse
    fixture also reached server tests, and a `credentials` folder in their tmp_path broke every test that
    lists it (53k phantom folders at the P4 gate)."""
    from fichero_cli import client as client_module

    _forbid_the_default_engine(monkeypatch)
    for name in _CONNECTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    token_path = tmp_path_factory.mktemp("cli-credentials") / ".api-key"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(
        client_module, "_CLI_SESSION_PATH", token_path.with_name("cli-session.json")
    )
    assert not os.environ.get("FICHERO_API_URL")
    return token_path
