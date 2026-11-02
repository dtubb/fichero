"""`sharing.address-choice`, engine half (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.3).

`GET /api/pair/addresses` is the engine's list of every address this Mac can be reached at, in the order to try, each with a
label and, where it cannot work, the one line why. The app only draws it. No row is loopback.
"""
from __future__ import annotations

from tests.unit.transport.test_sharing_state_and_multiuser_switch_to_spec import _owner
from tests.unit.transport.test_two_macs_end_to_end_to_spec import two_macs  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def _rows(two_macs, monkeypatch, *, tailnet="", forward="none", public="", lan="192.0.2.10", conflict=None):
    from fichero_server.security import bind_host, sharing_report, tailscale_serve

    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_LAN_HOST", lan)
    if public:
        monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", public)
    else:
        monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: tailnet)
    monkeypatch.setattr(tailscale_serve, "forward_state", lambda port: forward)
    monkeypatch.setattr(tailscale_serve, "forward_conflict", lambda port: conflict)
    monkeypatch.setattr(bind_host, "primary_lan_ip", lambda: lan)
    sharing_report._cache.clear()
    return two_macs["a"].get("/api/pair/addresses", headers=_owner(two_macs["a"])).json()["items"]


def test_with_a_tailnet_name_whose_forward_is_ours_the_first_row_is_the_tailnet(two_macs, monkeypatch):
    rows = _rows(two_macs, monkeypatch, tailnet="https://m.tail.ts.net", forward="ours", public="https://m.local:8765")
    assert [r["kind"] for r in rows] == ["tailnet", "local-name", "lan"]
    assert rows[0]["reason"] is None and rows[0]["label"].startswith("Tailscale")


def test_with_no_tailnet_the_first_row_is_the_local_name(two_macs, monkeypatch):
    rows = _rows(two_macs, monkeypatch, public="https://m.local:8765")
    assert [r["kind"] for r in rows] == ["local-name", "lan"]


def test_a_tailnet_row_whose_forward_is_not_ours_says_why_and_goes_last(two_macs, monkeypatch):
    conflict = {"holds": "tcp://localhost:8000", "free_with": "tailscale serve --tcp=8765 off"}
    rows = _rows(two_macs, monkeypatch, tailnet="https://m.tail.ts.net", forward="foreign", public="https://m.local:8765", conflict=conflict)
    assert rows[-1]["kind"] == "tailnet" and rows[-1]["listening"] is False
    assert "tcp://localhost:8000" in rows[-1]["reason"] and "tailscale serve --tcp=8765 off" in rows[-1]["reason"]


def test_a_tailnet_row_with_no_forward_yet_says_to_turn_sharing_off_and_on(two_macs, monkeypatch):
    rows = _rows(two_macs, monkeypatch, tailnet="https://m.tail.ts.net", forward="none")
    assert rows[-1]["kind"] == "tailnet" and "off and on" in rows[-1]["reason"]


def test_a_tailnet_that_could_not_be_asked_is_not_called_down(two_macs, monkeypatch):
    rows = _rows(two_macs, monkeypatch, tailnet="https://m.tail.ts.net", forward="unknown")
    assert "could not ask Tailscale" in [r for r in rows if r["kind"] == "tailnet"][0]["reason"]


def test_no_row_is_loopback_and_the_lan_row_names_the_port(two_macs, monkeypatch):
    rows = _rows(two_macs, monkeypatch, public="https://m.local:8765")
    assert not any("127.0.0.1" in r["url"] or "localhost" in r["url"] for r in rows)
    assert [r["url"] for r in rows if r["kind"] == "lan"] == ["https://192.0.2.10:8765"]


def test_the_list_is_the_owners_alone(two_macs, monkeypatch):
    _rows(two_macs, monkeypatch)
    assert two_macs["b"].get("/api/pair/addresses").status_code in (401, 403)
