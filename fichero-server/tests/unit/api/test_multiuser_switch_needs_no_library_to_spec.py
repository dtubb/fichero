"""`sharing.multiuser-switch-needs-no-library` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.4).

The Settings window's client carries no `X-Fichero-Library-Path` (its PairingService has no library; `/api/pair` is not
app-wide in LibraryPathMiddleware). The switch is app-wide (`owner_scope="app"`), so `PUT /api/pair/multiuser` must answer
the designed refusals (409 until the owner chose a password) and then 200, never 400 "Missing X-Fichero-Library-Path header"
(seen seven times in the Air's engine log on 2026-10-31: the switch never stuck).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from fichero_server.security import accounts
from tests.signed_in import mac_app_client, signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401  # the probe's fixture and helpers
    _bearer,
    _login,
    _multiuser_on,
    harness,
)

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def _settings_window(harness, headers: dict[str, str] | None = None) -> TestClient:
    """A client exactly like the Settings pane's: the Mac's own app over its Unix socket, the start-up credential, NO library header."""
    window = mac_app_client(harness)
    window.headers.pop("X-Fichero-Library-Path", None)
    return window


def _owner(harness, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    return harness.app_db.create_user(username="owner", display_name="Owner",
                                      password_hash=accounts.hash_password("random-" * 5), is_owner=True)


def test_the_switch_flips_with_no_library_header(harness, monkeypatch):
    _owner(harness, monkeypatch)
    window = _settings_window(harness)

    first = window.put("/api/pair/multiuser", json={"enabled": True})
    assert first.status_code == 409, f"the password gap, not a library complaint: {first.status_code} {first.text}"
    assert "password" in first.json()["detail"]

    assert window.post("/api/auth/owner-password", json={"password": "a chosen one"}).status_code == 200
    on = window.put("/api/pair/multiuser", json={"enabled": True})
    assert on.status_code == 200, on.text
    assert on.json()["multiuser_enabled"] is True and on.json()["audit_id"]
    assert harness.app_db.get_setting("multiuser.enabled") == "true"

    off = window.put("/api/pair/multiuser", json={"enabled": False})
    assert off.status_code == 200, off.text
    assert harness.app_db.get_setting("multiuser.enabled") == "false"


# The start-up key is still refused while Multi-user is off: pinned by
# tests/unit/security/test_owner_session_sets_the_switch_5908.py::test_the_start_up_key_is_refused_for_both_steps (named there
# for the ambient-owner ratchet), so it is not repeated here.


def test_the_switchs_audit_row_is_undone_from_a_library_window(harness, monkeypatch):
    """Review 2026-10-31 (M): the switch's row lives in the global package; the undo routes look in the window's library.
    Undo of an app-wide step must still work from a library window, the CLI or MCP (`sharing.set_multiuser` is undoable)."""
    owner = _owner(harness, monkeypatch)
    who = signed_in_client(harness, owner)
    window = _settings_window(harness)
    assert window.post("/api/auth/owner-password", json={"password": "a chosen one"}).status_code == 200
    on = window.put("/api/pair/multiuser", json={"enabled": True})
    assert on.status_code == 200, on.text
    assert harness.app_db.get_setting("multiuser.enabled") == "true"

    library_window = harness.client()  # a project window: the library header, the owner's session
    undone = library_window.post(f"/api/actions/audit/{on.json()['audit_id']}/undo", headers=who.headers)
    assert undone.status_code == 200, undone.text
    assert harness.app_db.get_setting("multiuser.enabled") == "false", "the undo took the switch back"


def test_a_paired_device_without_a_header_is_refused(harness, monkeypatch):
    """A header-less non-owner (a paired device's token) → 403: dropping the library dependency dropped no rule."""
    _multiuser_on(harness, monkeypatch)  # the owner mints the code signed in, not as the ambient host (the ratchet)
    minter = harness.client()
    minter.headers.update(_bearer(_login(harness, "owner")))
    device = harness.pair(minter)
    monkeypatch.delenv("FICHERO_MULTIUSER")  # the env pins the switch; the device must meet the route's own refusal
    bare = TestClient(harness.app, base_url="http://testserver", client=("testclient", 5000),
                      headers={"Authorization": f"Bearer {device['device_token']}"})
    switch = bare.put("/api/pair/multiuser", json={"enabled": True})
    assert switch.status_code == 403, switch.text
    assert harness.app_db.get_setting("multiuser.enabled") != "true"
