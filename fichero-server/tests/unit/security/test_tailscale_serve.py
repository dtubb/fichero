"""#2603: the engine forwards its tailnet port to its own loopback listener, and only ever
touches the forward it made.

The status shapes are the CLI's own, read on the MBP 2026-10-01 (tailscale 1.102): that Mac
already had an older HTTPS-on-443 proxy of the person's own, which must survive."""

from __future__ import annotations

import json
import subprocess

import pytest

from fichero_server.security import tailscale_serve as ts

PERSON_OWN_443 = {
    "TCP": {"443": {"HTTPS": True}},
    "Web": {"m.tail.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}}},
}


class FakeCli:
    """`tailscale serve` as far as the engine uses it: status, --bg --tcp, --tcp=N off."""

    def __init__(self, status: dict) -> None:
        self.status = json.loads(json.dumps(status))
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args[1:])
        tcp = self.status.setdefault("TCP", {})
        if args[1:] == ["serve", "status", "--json"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(self.status), "")
        if args[1:3] == ["serve", "--bg"]:
            tcp[args[4]] = {"TCPForward": args[5].removeprefix("tcp://")}
        elif args[2].startswith("--tcp=") and args[3] == "off":
            tcp.pop(args[2].removeprefix("--tcp="), None)
        return subprocess.CompletedProcess(args, 0, "", "")


@pytest.fixture
def cli(monkeypatch):
    fake = FakeCli(PERSON_OWN_443)
    monkeypatch.setattr(ts, "_run", fake)
    return fake


def test_creates_the_forward_and_removes_only_it(cli) -> None:
    assert ts.ensure_tcp_forward(8765, "tailscale") is True
    assert cli.status["TCP"]["8765"] == {"TCPForward": "127.0.0.1:8765"}
    ts.remove_tcp_forward(8765, "tailscale")
    assert cli.status == PERSON_OWN_443  # the person's own 443 proxy is untouched


def test_an_existing_forward_to_us_is_reused_and_not_ours_to_remove(cli) -> None:
    cli.status["TCP"]["8765"] = {"TCPForward": "127.0.0.1:8765"}
    assert ts.ensure_tcp_forward(8765, "tailscale") is False
    assert not any(c[:2] == ["serve", "--bg"] for c in cli.calls)


def test_a_port_serving_something_else_is_refused_not_replaced(cli) -> None:
    cli.status["TCP"]["8765"] = {"TCPForward": "127.0.0.1:9999"}
    with pytest.raises(RuntimeError, match="not replacing"):
        ts.ensure_tcp_forward(8765, "tailscale")
    assert cli.status["TCP"]["8765"] == {"TCPForward": "127.0.0.1:9999"}


def test_the_tailnet_url_comes_from_a_ts_net_sharing_address() -> None:
    """The app sets only FICHERO_PUBLIC_BASE_URL; pairing codes never carried the tailnet URL."""
    assert ts.tailnet_url({"FICHERO_PUBLIC_BASE_URL": "https://m.tail.ts.net:8765"}) == (
        "https://m.tail.ts.net:8765"
    )
    assert ts.tailnet_url({"FICHERO_PUBLIC_BASE_URL": "https://m.local:8765"}) == ""
    assert ts.tailnet_url({"FICHERO_TAILNET_URL": "https://x.ts.net"}) == "https://x.ts.net"


def test_the_cli_is_found_in_the_app_bundle_without_the_path_shim(monkeypatch) -> None:
    """The MBP has Tailscale.app but no /usr/local/bin/tailscale: status said not installed."""
    monkeypatch.setattr(ts.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ts.os.path, "exists", lambda p: p == ts.APP_BUNDLE_CLI)
    assert ts.tailscale_cli() == ts.APP_BUNDLE_CLI
