"""Regression #4359: loopback + multi-user OFF must never require sign-in.

Daniel launched Dev Local (loopback bootstrap token, multi-user off) and got a
full-window "Sign In — Sign in to open your libraries" wall. 'Loopback is
always owner' is a hard invariant: with multi-user disabled, the auth probes
the app consults on launch must answer exactly the shapes that resolve the
Swift session gate to `.disabled` (no auth surface at all):

- ``GET /api/auth/me``       -> 404 (multi-user disabled; never 401)
- ``GET /api/auth/identity`` -> 200 with ``multiuser_enabled: false`` AND
  ``is_owner_access: true`` under ``auth_kind == "bootstrap"``

Any drift here — a 401 where 404 was contractual, a missing owner identity, a
5xx from a broken row mapper — reintroduces the sign-in wall on the Mac that
owns the engine.
"""

from __future__ import annotations


def test_auth_me_is_404_not_401_when_multiuser_off(client):
    # 404 is the contract the Swift gate maps to `.disabled` (no gate at all).
    # A 401 here sends the app down the identity/accounts probes; a 5xx makes
    # the gate "fail closed" into a login wall for the loopback owner.
    response = client.get("/api/auth/me")
    assert response.status_code == 404, response.text


def test_identity_reports_bootstrap_owner_when_multiuser_off(client):
    response = client.get("/api/auth/identity")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["multiuser_enabled"] is False
    assert payload["is_owner_access"] is True
    assert payload["auth_kind"] == "bootstrap"


def test_no_probe_the_gate_consults_errors_out(client):
    # The full launch-probe set the session gate consults must never 5xx —
    # a server error on any of them is indistinguishable from "signed out"
    # to a fail-closed client (#4348 class).
    for path in ("/api/auth/me", "/api/auth/identity", "/api/users"):
        response = client.get(path)
        assert response.status_code < 500, f"{path}: {response.status_code} {response.text}"


def test_login_wall_inputs_never_materialize_on_loopback(client):
    # Combined shape assertion: with multi-user off the ONLY resolutions the
    # Swift `SessionStore.resolvePhase` can reach from these answers are
    # `.disabled` (me==404, or identity says multiuser off / owner access).
    me = client.get("/api/auth/me")
    identity = client.get("/api/auth/identity")
    assert me.status_code == 404 or (
        identity.status_code == 200
        and (
            identity.json()["multiuser_enabled"] is False
            or identity.json()["is_owner_access"] is True
        )
    ), f"gate inputs drifted: me={me.status_code}, identity={identity.status_code} {identity.text}"
