"""`sharing.cli-mints-a-link` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.5): `fichero devices invite`
mints a pairing code on the HOST and prints (or files) the pairing link, so two machines link with no GUI:
`devices invite --link-file L` here, `devices pair --link-file L` there.

The engine already lets the host's owner mint over its socket; the CLI only has to NAME the address, which it reads
from `GET /api/pair/sharing` (`sharing.state-names-every-address`). The link is the app's own shape
(`fichero://pair?payload=<base64 JSON>`, `RemoteClientPairing.inviteLinkString`), so the Mac, the phone and the CLI
all redeem it. The raw code is never printed on its own.
"""
from __future__ import annotations

import json
import stat

import pytest
from typer.testing import CliRunner

from fichero_cli import __main__ as cli_main
from fichero_cli import pairing

runner = CliRunner()
LOCAL = "https://host-a.local:8765"
TAILNET = "https://host-a.tail1234.ts.net"  # as GET /api/pair/sharing returns it: the origin, NO port (review H3)
TAILNET_LINK = "https://host-a.tail1234.ts.net:8765"  # what the link must carry: the forward is --https=8765
PIN = "c3BraS1waW4="
MINT = {"code": "ABCD-1234", "expires_at": "2026-10-31T16:00:00Z", "spki_pin": PIN, "tailnet_url": TAILNET}


class _Host:
    """The host engine as the CLI sees it: one mint, one sharing-state read, both recorded."""

    state: dict = {}
    calls: list[str] = []

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def sharing_state(self):
        _Host.calls.append("sharing")
        return dict(_Host.state)

    def create_pairing_code(self):
        _Host.calls.append("mint")
        return dict(MINT)


@pytest.fixture
def host(monkeypatch):
    _Host.calls = []
    _Host.state = {"public_base_url": LOCAL, "tailnet_url": TAILNET, "tailnet_forward": "ours", "multiuser_enabled": False}
    monkeypatch.setattr(cli_main, "FicheroClient", _Host)
    return _Host


# -- the pure part: the link ---------------------------------------------------------------------------------------
def test_the_link_for_a_local_address_carries_the_pin_and_decodes_like_the_apps():
    text = pairing.invite_link(api_url=LOCAL, code="ABCD-1234", spki=PIN, expires_at=MINT["expires_at"], library_path="/x")
    link = pairing.parse_link(text)  # the same parser `devices pair` runs
    assert (link.api_url, link.code, link.spki) == (LOCAL, "ABCD-1234", PIN)
    assert text.startswith("fichero://pair?payload=")
    payload = json.loads(pairing._payload_of(text))
    assert payload == {"v": 1, "api_url": LOCAL, "pair_code": "ABCD-1234", "expires_at": MINT["expires_at"], "spki": PIN,
                       "library_path": "/x"}
    assert list(payload) == sorted(payload), "sorted keys: the same link reads the same from every machine"


def test_the_link_for_a_tailnet_address_carries_no_pin():
    text = pairing.invite_link(api_url=TAILNET_LINK, code="ABCD-1234", spki=PIN, expires_at=None, library_path=None)
    link = pairing.parse_link(text)
    assert (link.api_url, link.spki) == (TAILNET_LINK, None)
    payload = json.loads(pairing._payload_of(text))
    assert "spki" not in payload and "library_path" not in payload and "expires_at" not in payload


# -- the command ---------------------------------------------------------------------------------------------------
def test_invite_defaults_to_tailscale_when_the_host_has_a_forward_of_its_own(host):
    result = runner.invoke(cli_main.app, ["devices", "invite"])
    assert result.exit_code == 0, result.output
    assert host.calls == ["sharing", "mint"]
    link = pairing.parse_link(result.output.strip().splitlines()[-1])
    assert link.api_url == TAILNET_LINK and link.spki is None and link.code == "ABCD-1234", "the sharing port rides on the tailnet name"
    assert "Tailscale" in result.output and "16:00" in result.output


def test_invite_falls_back_to_this_network_without_a_tailnet_forward(host):
    host.state["tailnet_forward"] = "foreign"
    result = runner.invoke(cli_main.app, ["devices", "invite"])
    assert result.exit_code == 0, result.output
    link = pairing.parse_link(result.output.strip().splitlines()[-1])
    assert link.api_url == LOCAL and link.spki == PIN


def test_invite_takes_the_address_the_person_asks_for(host):
    this = runner.invoke(cli_main.app, ["devices", "invite", "--address", "this-network"])
    assert pairing.parse_link(this.output.strip().splitlines()[-1]).api_url == LOCAL
    tail = runner.invoke(cli_main.app, ["devices", "invite", "--address", "tailscale"])
    assert pairing.parse_link(tail.output.strip().splitlines()[-1]).api_url == TAILNET_LINK


def test_invite_refuses_an_address_the_host_does_not_have(host):
    host.state["tailnet_url"] = None
    host.state["tailnet_forward"] = "none"
    result = runner.invoke(cli_main.app, ["devices", "invite", "--address", "tailscale"])
    assert result.exit_code == 1
    assert "Tailscale" in result.output and "fichero://" not in result.output
    assert host.calls == ["sharing"], "nothing is minted for an address nothing listens on"


def test_invite_refuses_when_sharing_is_off(host):
    host.state["public_base_url"] = None
    host.state["tailnet_url"] = None
    result = runner.invoke(cli_main.app, ["devices", "invite"])
    assert result.exit_code == 1 and "Sharing" in result.output and host.calls == ["sharing"]


def test_link_file_is_owner_only_and_stdout_holds_no_link(host, tmp_path):
    target = tmp_path / "link.txt"
    result = runner.invoke(cli_main.app, ["devices", "invite", "--link-file", str(target)])
    assert result.exit_code == 0, result.output
    assert "fichero://" not in result.output and "ABCD" not in result.output
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert pairing.parse_link(target.read_text()).code == "ABCD-1234"


# -- review 2026-10-31 (M): the link file is made owner-only at creation, never through someone else's file ---------------
def test_link_file_refuses_a_symlink_and_a_directory(host, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    link = tmp_path / "link-is-a-symlink"
    link.symlink_to(victim)
    result = runner.invoke(cli_main.app, ["devices", "invite", "--link-file", str(link)])
    assert result.exit_code == 1 and "symlink" in result.output.lower(), result.output
    assert victim.read_text() == "keep me", "the symlink's target was written through"
    assert "fichero://" not in result.output

    folder = tmp_path / "a-folder"
    folder.mkdir()
    result = runner.invoke(cli_main.app, ["devices", "invite", "--link-file", str(folder)])
    assert result.exit_code == 1 and "fichero://" not in result.output


def test_link_file_replaces_the_owners_own_loose_file_with_an_owner_only_one(host, tmp_path):
    """A pre-existing 0666 file of the caller's own never holds the link while readable: the link is written to a fresh
    0600 file beside it and moved into place."""
    target = tmp_path / "loose.txt"
    target.write_text("old")
    target.chmod(0o666)
    result = runner.invoke(cli_main.app, ["devices", "invite", "--link-file", str(target)])
    assert result.exit_code == 0, result.output
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert pairing.parse_link(target.read_text()).code == "ABCD-1234"
    assert not list(tmp_path.glob("*.tmp*")), "no temp file left behind"


def test_write_owner_only_creates_with_excl_and_nofollow(tmp_path, monkeypatch):
    """The temp file is created O_CREAT|O_EXCL|O_NOFOLLOW at mode 0600; the mode is never fixed up after a write."""
    seen = []
    real_open = pairing.os.open

    def spy(path, flags, mode=0o777, *a, **k):
        seen.append((flags, mode))
        return real_open(path, flags, mode, *a, **k)

    monkeypatch.setattr(pairing.os, "open", spy)
    pairing.write_owner_only(tmp_path / "x", "text\n")
    flags, mode = seen[-1]
    assert flags & pairing.os.O_EXCL and flags & pairing.os.O_NOFOLLOW and mode == 0o600


# -- review 2026-10-31: H3 the port, L4 the encoding, L5 the words ---------------------------------------------------------
def test_the_tailnet_link_carries_the_sharing_port():
    assert pairing.tailnet_link_url("https://host-a.tail1234.ts.net", "https://host-a.local:8765") == "https://host-a.tail1234.ts.net:8765"
    assert pairing.tailnet_link_url("https://host-a.tail1234.ts.net:9443", "https://host-a.local:8765") == "https://host-a.tail1234.ts.net:9443"
    assert pairing.tailnet_link_url("https://host-a.tail1234.ts.net", None) == "https://host-a.tail1234.ts.net:8765"


def test_the_link_survives_a_library_path_that_base64_encodes_to_a_plus_sign():
    """L4: an unquoted `+` in the query reads back as a space and the link is 'damaged'. Every payload must round-trip."""
    for path in ("/Users/x/Proj~1>.fichero", "/a>>", "/~~~~", "/Users/d/Marshall.fichero", "/" + "~>" * 40):
        text = pairing.invite_link(api_url=LOCAL, code="ABCD-1234", spki=PIN, expires_at=None, library_path=path)
        assert json.loads(pairing._payload_of(text))["library_path"] == path
        assert pairing.parse_link(text).code == "ABCD-1234"


def test_invite_words_name_what_exists(host):
    """L5: a tailnet address whose forward is not Fichero's own says so; no address at all says Sharing is off; a refused
    this-network never points at a Tailscale that cannot work."""
    host.state["tailnet_forward"] = "none"
    result = runner.invoke(cli_main.app, ["devices", "invite", "--address", "tailscale"])
    assert result.exit_code == 1 and "published" in result.output and "another service" not in result.output, result.output
    host.state["public_base_url"] = None
    result = runner.invoke(cli_main.app, ["devices", "invite", "--address", "this-network"])
    assert result.exit_code == 1 and "tailscale" not in result.output.lower(), result.output
