"""`sharing.multiuser-switch-needs-no-library` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.4).

The Settings window's client carries no `X-Fichero-Library-Path` (its PairingService has no library; `/api/pair` is not
app-wide in LibraryPathMiddleware). The switch is app-wide (`owner_scope="app"`), so `PUT /api/pair/multiuser` must answer
the designed refusals (409 until the owner chose a password) and then 200, never 400 "Missing X-Fichero-Library-Path header"
(seen seven times in the Air's engine log on 2026-10-31: the switch never stuck).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from fichero_server.security import accounts
from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401  # the probe's fixture

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def _settings_window(harness, headers: dict[str, str]) -> TestClient:
    """A client exactly like the Settings pane's: the owner's key session and NO library header."""
    return TestClient(harness.app, base_url="http://testserver", client=("testclient", 5000),
                      headers={"Authorization": headers["Authorization"]})


def _owner(harness, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    return harness.app_db.create_user(username="owner", display_name="Owner",
                                      password_hash=accounts.hash_password("random-" * 5), is_owner=True)


def test_the_switch_flips_with_no_library_header(harness, monkeypatch):
    owner = _owner(harness, monkeypatch)
    who = signed_in_client(harness, owner)
    window = _settings_window(harness, who.headers)

    first = window.put("/api/pair/multiuser", json={"enabled": True})
    assert first.status_code == 409, f"the password gap, not a library complaint: {first.status_code} {first.text}"
    assert "password" in first.json()["detail"]

    assert window.patch(f"/api/users/{owner.id}", json={"password": "a chosen one"}).status_code == 200
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
