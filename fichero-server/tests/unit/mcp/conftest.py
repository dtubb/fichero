"""Test isolation for MCP tests.

This conftest.py applies the same isolation rules as fichero-mcp/tests/conftest.py
to ensure tests don't leak state (like FICHERO_API_KEY or _CONFIG) between tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
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
def _isolated_mcp_env(monkeypatch, tmp_path_factory):
    """Clear connection env vars, redirect credential files, reset _CONFIG."""
    from fichero_cli import client as client_module
    from fichero_mcp import server as mcp_server

    # Clear connection env vars to prevent tests from using real credentials
    for name in _CONNECTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    # Use its own temp dir for credentials
    token_path = tmp_path_factory.mktemp("mcp-credentials") / ".api-key"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(
        client_module, "_CLI_SESSION_PATH", token_path.with_name("cli-session.json")
    )
    # Also patch _CONTAINER_TOKEN_PATH to avoid reading the real container token file
    monkeypatch.setattr(
        client_module,
        "_CONTAINER_TOKEN_PATH",
        token_path.with_name("container-.api-key"),
    )
    # _CONFIG is module-global and mutated by main(); restore it so test order
    # cannot leak a base URL from one module into another.
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", None)
    monkeypatch.setitem(mcp_server._CONFIG, "library_path", None)
    return token_path
