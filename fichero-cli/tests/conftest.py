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


@pytest.fixture(autouse=True)
def isolated_cli_env(monkeypatch, tmp_path):
    """Clear connection env vars and redirect the on-disk credential paths."""
    from fichero_cli import client as client_module

    for name in _CONNECTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    token_path = tmp_path / "credentials" / ".api-key"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(
        client_module, "_CLI_SESSION_PATH", token_path.with_name("cli-session.json")
    )
    assert not os.environ.get("FICHERO_API_URL")
    return token_path
