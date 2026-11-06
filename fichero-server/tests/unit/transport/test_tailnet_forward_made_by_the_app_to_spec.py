"""sharing.tailnet-forward-made-by-the-app (t55, owner 2026-11-06): links must point to Tailscale. The sandboxed engine
cannot run the Tailscale CLI, so the app makes the forward and tells the engine (`FICHERO_TAILNET_URL`,
`FICHERO_TAILNET_FORWARD=app`): the engine then reports the forward as Fichero's, names the tailnet address FIRST in
the link, and never removes a forward it did not make.
"""

import logging
import subprocess

from fichero_server.security import sharing_report, tailscale_serve

TAILNET = "https://pro.tail1234.ts.net"


def _app_made_it(monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_TAILNET_URL", TAILNET)
    monkeypatch.setenv("FICHERO_TAILNET_FORWARD", "app")
    monkeypatch.setattr(tailscale_serve, "tailscale_cli", lambda: "/Applications/Tailscale.app/Contents/MacOS/Tailscale")

    def sandboxed(_args):
        raise subprocess.CalledProcessError(1, "tailscale")

    monkeypatch.setattr(tailscale_serve, "_run", sandboxed)


def test_a_forward_the_app_made_is_fichero_s_even_when_the_engine_cannot_ask(monkeypatch):
    _app_made_it(monkeypatch)
    assert tailscale_serve.forward_state(8765) == "ours"


def test_without_the_app_s_word_a_sandboxed_engine_still_says_unknown(monkeypatch):
    _app_made_it(monkeypatch)
    monkeypatch.delenv("FICHERO_TAILNET_FORWARD")
    assert tailscale_serve.forward_state(8765) == "unknown"


def test_the_link_names_the_tailnet_address_first(monkeypatch):
    _app_made_it(monkeypatch)
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://pro.local:8765")
    monkeypatch.setattr(sharing_report, "_kept", lambda _name, fn: fn())
    monkeypatch.setattr("fichero_server.security.bind_host.primary_lan_ip", lambda: "10.0.0.5")
    rows = sharing_report.address_rows()
    assert rows[0].kind == "tailnet" and rows[0].url == TAILNET and rows[0].listening


def test_the_engine_leaves_the_app_s_forward_alone(monkeypatch):
    _app_made_it(monkeypatch)
    monkeypatch.setenv("FICHERO_TLS_CERTFILE", "/tmp/cert.pem")
    assert tailscale_serve.start_for_engine(log=logging.getLogger("t")) is None


def test_no_forward_is_said_in_the_log(monkeypatch, caplog):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_TLS_CERTFILE", "/tmp/cert.pem")
    for name in ("FICHERO_TAILNET_URL", "FICHERO_TAILNET_FORWARD", "FICHERO_PUBLIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tailscale_serve, "tailscale_cli", lambda: None)
    with caplog.at_level(logging.INFO):
        assert tailscale_serve.start_for_engine(log=logging.getLogger("t")) is None
    assert "no forward: Tailscale is not installed" in caplog.text
