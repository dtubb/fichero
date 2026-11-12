"""`sharing.tailnet-name-known-without-the-cli` and `sharing.tailnet-serve-command-on-the-sheet` (#6554,
docs/contributor_manual/specs/source/sharing-two-macs.md).

A sandboxed engine runs the Tailscale CLI and reads nothing back, so it could not name this Mac's tailnet address and the
Add Device sheet greyed the Tailscale row. When Tailscale cannot be asked, the engine names the tailnet address it already
knows (the `.ts.net` sharing address, a `.ts.net` name on its certificate, a Remote Access folder named for one) and offers
the one `tailscale serve` command to paste. A Tailscale that answers "stopped" still names nothing.
"""
from __future__ import annotations

import subprocess

from fichero_server.security import tailscale_serve as ts


def _prints(stdout: str):
    return lambda args: subprocess.CompletedProcess(args, 0, stdout, "")


def test_a_cli_that_prints_nothing_offers_the_name_the_engine_knows():
    known = "https://pro.tail1234.ts.net"
    assert ts.detected_tailnet_url("tailscale", run=_prints(""), known=known) == known
    assert ts.detected_tailnet_url("tailscale", run=_prints("not json"), known=known) == known

    def refused(args):
        raise subprocess.CalledProcessError(1, args)

    assert ts.detected_tailnet_url("tailscale", run=refused, known=known) == known


def test_a_stopped_tailscale_names_nothing_whatever_the_engine_knows():
    stopped = '{"BackendState": "Stopped", "Self": {"DNSName": "pro.tail1234.ts.net."}}'
    assert ts.detected_tailnet_url("tailscale", run=_prints(stopped), known="https://pro.tail1234.ts.net") == ""


def test_no_tailscale_installed_names_nothing(monkeypatch):
    monkeypatch.setattr(ts, "tailscale_cli", lambda: None)
    assert ts.detected_tailnet_url(known="https://pro.tail1234.ts.net") == ""


def test_the_ts_net_sharing_address_is_known_without_its_port():
    env = {"FICHERO_PUBLIC_BASE_URL": "https://Pro.tail1234.ts.net:8765"}
    assert ts.known_tailnet_url(env, cert_names=[], storage_dirs=[]) == "https://pro.tail1234.ts.net"


def test_a_ts_net_name_on_the_certificate_is_known():
    env = {"FICHERO_PUBLIC_BASE_URL": "https://pro.local:8765", "FICHERO_TLS_CERTFILE": "/x/pro.local-8765-ab/server.crt"}
    names = ["pro.local", "127.0.0.1", "pro.tail1234.ts.net"]
    assert ts.known_tailnet_url(env, cert_names=names, storage_dirs=[]) == "https://pro.tail1234.ts.net"


def test_a_remote_access_folder_named_for_the_tailnet_is_known():
    env = {"FICHERO_PUBLIC_BASE_URL": "https://10.10.10.2:8765", "FICHERO_TLS_CERTFILE": "/x/10.10.10.2-8765-ab/server.crt"}
    folders = ["10.10.10.2-8765-ab", "pro-m1.local-8765-cd", "pro-m1.tail1234.ts.net-8765-ef"]
    assert ts.known_tailnet_url(env, cert_names=[], storage_dirs=folders) == "https://pro-m1.tail1234.ts.net"


def test_nothing_known_is_nothing():
    env = {"FICHERO_PUBLIC_BASE_URL": "https://pro.local:8765"}
    assert ts.known_tailnet_url(env, cert_names=["pro.local"], storage_dirs=["pro.local-8765-cd", "key.pem"]) == ""


def test_the_serve_command_is_offered_when_the_name_is_known_and_tailscale_cannot_be_asked(monkeypatch):
    from fichero_server.api.routes.auth import pairing

    monkeypatch.setattr(ts, "known_tailnet_url", lambda *a, **k: "https://pro.tail1234.ts.net")
    monkeypatch.setattr(ts, "tailscale_cli", lambda: ts.APP_BUNDLE_CLI)

    def cannot_ask(cli):
        raise ValueError("no JSON")

    monkeypatch.setattr(ts, "serve_status", cannot_ask)
    command = pairing._tailnet_serve_command()
    assert command is not None
    assert "serve --bg --https=8765 https+insecure://127.0.0.1:8765" in command


def test_no_serve_command_when_no_tailnet_name_is_known(monkeypatch):
    from fichero_server.api.routes.auth import pairing

    monkeypatch.setattr(ts, "known_tailnet_url", lambda *a, **k: "")
    assert pairing._tailnet_serve_command() is None
