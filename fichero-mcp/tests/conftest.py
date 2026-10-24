"""Test seam for the fichero-mcp product tree (#4227).

`pytest fichero-mcp/tests` has to work with no PYTHONPATH exported. This
package imports `FicheroClient` from the CLI product and response models from
the server, so all three `src/` dirs go on `sys.path` — the same seam
`fichero-server/tests/conftest.py` installs for the sibling products.

`isolated_mcp_env` is autouse and load-bearing: the MCP tools resolve their
server URL and credential from the live environment and from
`~/Library/Application Support/Fichero/`. Without the isolation, the
fail-closed auth assertions would pass or fail depending on whether the
developer happens to have an engine running.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _src in ("fichero-mcp/src", "fichero-cli/src", "fichero-server/src"):
    _path = str(_REPO_ROOT / _src)
    if _path not in sys.path:
        sys.path.insert(0, _path)

_CONNECTION_ENV_VARS = (
    "FICHERO_API_URL",
    "FICHERO_API_KEY",
    "FICHERO_SESSION_TOKEN",
    "FICHERO_LIBRARY_PATH",
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
def isolated_mcp_env(monkeypatch, tmp_path_factory):
    """Clear connection env vars, redirect credential files, reset _CONFIG."""
    from fichero_cli import client as client_module
    from fichero_mcp import server as mcp_server

    _forbid_the_default_engine(monkeypatch)
    for name in _CONNECTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Its own temp dir, never the test's tmp_path: in a combined run this autouse fixture also reaches server tests,
    # and a `credentials` folder in their tmp_path breaks every test that lists it (the CLI's twin, 3202dcfa8).
    token_path = tmp_path_factory.mktemp("mcp-credentials") / ".api-key"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(
        client_module, "_CLI_SESSION_PATH", token_path.with_name("cli-session.json")
    )
    # `_read_token` also checks `_CONTAINER_TOKEN_PATH` — the SANDBOXED app's
    # own container copy of the same file, a real path under
    # ~/Library/Containers/app.fichero.fichero/... this fixture's docstring
    # promised isolation from but did not patch. On a machine that has ever
    # run the real sandboxed app (every dev machine, including this one,
    # verified: a real `.api-key` sits there right now), a test asserting
    # "no credential" silently picked up that REAL local secret instead —
    # a mocked transport meant no actual leak occurred, but the test's
    # pass/fail depended on host state it never should have touched.
    monkeypatch.setattr(
        client_module, "_CONTAINER_TOKEN_PATH", token_path.with_name("container-.api-key")
    )
    # _CONFIG is module-global and mutated by each surface's main(); restore it
    # so test order cannot leak a base URL from one module into another.
    for module in (mcp_server,):
        monkeypatch.setitem(module._CONFIG, "base_url", None)
        monkeypatch.setitem(module._CONFIG, "library_path", None)
    return token_path
