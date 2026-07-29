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


@pytest.fixture(autouse=True)
def isolated_mcp_env(monkeypatch, tmp_path):
    """Clear connection env vars, redirect credential files, reset _CONFIG."""
    from fichero_cli import client as client_module
    from fichero_mcp import full as mcp_full
    from fichero_mcp import server as mcp_server
    from fichero_mcp import simple as mcp_simple

    for name in _CONNECTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    token_path = tmp_path / "credentials" / ".api-key"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(
        client_module, "_CLI_SESSION_PATH", token_path.with_name("cli-session.json")
    )
    # _CONFIG is module-global and mutated by each surface's main(); restore it
    # so test order cannot leak a base URL from one module into another.
    for module in (mcp_server, mcp_simple, mcp_full):
        monkeypatch.setitem(module._CONFIG, "base_url", None)
        monkeypatch.setitem(module._CONFIG, "library_path", None)
    return token_path
