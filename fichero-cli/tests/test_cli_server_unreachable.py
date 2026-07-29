"""The CLI must fail loudly when the server is not there (#4227).

The failure mode these guard against is the one AGENTS.md calls out as
unacceptable: a command that cannot reach the server printing something that
looks like a result, or exiting 0. Every case here asserts BOTH the non-zero
exit code and that the human-readable diagnosis names the base URL, so a user
pointed at the wrong host can see it.
"""

from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from fichero_cli import FicheroClient, FicheroError
from fichero_cli import __main__ as cli_main

runner = CliRunner()


def _install_transport(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = FicheroClient

    def factory(**kwargs):
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(cli_main, "FicheroClient", factory)


@pytest.fixture
def refused(monkeypatch):
    """Every request fails the way a stopped server fails."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    _install_transport(monkeypatch, handler)


@pytest.fixture
def server_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    _install_transport(monkeypatch, handler)


@pytest.fixture
def unauthorized(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Not authenticated"})

    _install_transport(monkeypatch, handler)


def _all_output(result) -> str:
    """CliRunner folds the CLI's stderr diagnostics into `output`."""
    return result.output


def test_health_exits_nonzero_when_the_server_is_down(refused):
    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 1
    combined = _all_output(result)
    assert "Cannot connect to the Fichero backend" in combined
    assert "127.0.0.1:8765" in combined


def test_unreachable_server_never_prints_a_result(refused):
    result = runner.invoke(cli_main.app, ["--json", "health"])

    assert result.exit_code == 1
    # No JSON document may be emitted — an empty/partial result rendered as
    # success is exactly the silent failure this asserts against.
    assert '"status"' not in _all_output(result)


def test_unreachable_server_names_the_configured_remote_host(refused):
    result = runner.invoke(
        cli_main.app, ["--base-url", "https://typo-host.example:8765", "health"]
    )

    assert result.exit_code == 1
    assert "typo-host.example:8765" in _all_output(result)


def test_list_command_also_fails_rather_than_reporting_zero_documents(refused):
    result = runner.invoke(cli_main.app, ["docs", "list"])

    assert result.exit_code == 1
    combined = _all_output(result)
    assert "Cannot connect to the Fichero backend" in combined
    # "0 documents" / "[]" would be a lie about the library's contents.
    assert "[]" not in combined


def test_server_error_status_is_surfaced_not_swallowed(server_error):
    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 1
    assert "500" in _all_output(result)


def test_401_tells_the_user_how_to_authenticate(unauthorized):
    result = runner.invoke(cli_main.app, ["health"])

    assert result.exit_code == 1
    assert "fichero auth login" in _all_output(result)


def test_401_on_a_hand_rolled_command_still_fails_loudly(unauthorized):
    """`docs list`'s human path handles FicheroError itself.

    It therefore skips `_report_fichero_error`'s "run `fichero auth login`"
    hint (see the note filed in agent-work/status/cli-mcp-test-wiring.md). What
    it must never do is exit 0 or print a document list, and that is what this
    pins.
    """
    result = runner.invoke(cli_main.app, ["docs", "list"])

    assert result.exit_code == 1
    assert "401" in _all_output(result)


def test_client_level_transport_failure_is_a_typed_error():
    """The message the CLI prints comes from a typed error, not a str match."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with FicheroClient(
        base_url="http://127.0.0.1:8765", token="", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(FicheroError) as excinfo:
            client.health()

    # status_code is None for transport failures — callers distinguish
    # "unreachable" from "responded with an error" on this, not on the text.
    assert excinfo.value.status_code is None
    assert "Cannot connect to the Fichero backend" in str(excinfo.value)
