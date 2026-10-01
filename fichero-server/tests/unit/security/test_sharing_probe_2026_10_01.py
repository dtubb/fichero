"""Adversarial probe of library sharing + multi-user at the engine (2026-10-01, overnight).

Every test here drives the REAL routes through the real auth middleware, as the
host app (loopback + bootstrap token), as a paired device on another Mac
(non-loopback client address, https), and as a second person. Two kinds of test:

* PINS — behaviour checked and found correct. A red pin means a sharing guarantee
  the spec relies on (`docs/contributor_manual/specs/transport/library-sharing.md`)
  has regressed.
* DEFECTS — ``xfail(strict=True)``: the test states what SHOULD happen and fails
  today. When the defect is fixed the xfail flips to XPASS and fails the run, which
  is the signal to drop the marker.
"""

from __future__ import annotations

import importlib
from datetime import timedelta
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from fichero_server.api.routes.auth import pairing
from fichero_server.models import ActionAudit
from fichero_server.security import accounts, authz

REMOTE_ADDR = ("198.51.100.20", 5000)
SPKI_PIN = "c3BraS1waW4="


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clear_pairing_state():
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()
    yield
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()


class Harness:
    def __init__(self, api_main, app_db, library, bootstrap):
        self.api_main = api_main
        self.app = api_main.app
        self.app_db = app_db
        self.library = library
        self.bootstrap = bootstrap
        self.lib_header = {"X-Fichero-Library-Path": quote(str(library), safe="/")}

    def client(self, *, base_url="http://testserver", client_addr=("testclient", 5000)):
        # "Authorization": "" pins the client's default so the unit conftest's
        # setdefault() cannot slip the bootstrap token into a request that must carry none.
        return TestClient(
            self.app,
            base_url=base_url,
            client=client_addr,
            headers={**self.lib_header, "Authorization": ""},
        )

    def host(self):
        """The host app: loopback, bootstrap token."""
        c = self.client()
        c.headers["Authorization"] = f"Bearer {self.bootstrap}"
        return c

    def remote(self):
        """Another Mac on the LAN: non-loopback address, https listener."""
        return self.client(base_url="https://paired.example", client_addr=REMOTE_ADDR)

    def pair(self, code_client, *, device_name="MBP", code_headers=None) -> dict:
        code = code_client.post("/api/pair/code", headers=code_headers or {})
        assert code.status_code == 200, code.text
        paired = self.remote().post(
            "/api/pair", json={"code": code.json()["code"], "device_name": device_name}
        )
        assert paired.status_code == 200, paired.text
        return paired.json()

    def audit_rows(self):
        from fichero_server.db import db_manager

        db = db_manager.get_database(self.library)
        return sorted(db.all(ActionAudit), key=lambda a: a.created_at)


@pytest.fixture
def harness(test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", SPKI_PIN)
    monkeypatch.delenv("FICHERO_TAILNET_URL", raising=False)
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")

    import fichero_server.api.main as api_main
    from fichero_server.api.auth import initialize_token

    api_main = importlib.reload(api_main)
    from fichero_server.api.routes.ai.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    try:
        yield Harness(api_main, app_db, test_package, initialize_token())
    finally:
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        importlib.reload(api_main)


def _multiuser_on(harness, monkeypatch):
    """Multi-user ON with an owner (owner of the test library), alice (editor), bob (viewer)."""
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    db = harness.app_db
    users = {}
    for name, is_owner in (("owner", True), ("alice", False), ("bob", False)):
        users[name] = db.create_user(
            username=name,
            display_name=name.title(),
            password_hash=accounts.hash_password("pw-" + name),
            is_owner=is_owner,
        )
    lib = authz.normalize_library_path(harness.library)
    db.set_library_role(user_id=users["owner"].id, library_path=lib, role=authz.ROLE_OWNER)
    db.set_library_role(user_id=users["alice"].id, library_path=lib, role=authz.ROLE_EDITOR)
    db.set_library_role(user_id=users["bob"].id, library_path=lib, role=authz.ROLE_VIEWER)
    return users


def _login(harness, username) -> str:
    r = harness.client().post(
        "/api/auth/login", json={"username": username, "password": "pw-" + username}
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _pair_as(harness, username, device_name) -> dict:
    token = _login(harness, username)
    return harness.pair(harness.client(), device_name=device_name, code_headers=_bearer(token))


# =============================================================================
# 1. Pairing
# =============================================================================


def test_pin_a_pairing_code_is_one_time(harness):
    """A replayed code must not mint a second device token (a QR photographed twice)."""
    code = harness.host().post("/api/pair/code").json()["code"]
    remote = harness.remote()
    first = remote.post("/api/pair", json={"code": code, "device_name": "MBP"})
    second = remote.post("/api/pair", json={"code": code, "device_name": "Thief"})
    assert first.status_code == 200
    assert second.status_code == 401
    assert [d.name for d in harness.app_db.list_devices()] == ["MBP"]


def test_pin_an_expired_pairing_code_is_refused(harness):
    code = harness.host().post("/api/pair/code").json()["code"]
    record = pairing._PAIRING_CODES[code]
    record.expires_at = record.expires_at - pairing.PAIRING_CODE_TTL - timedelta(seconds=1)
    r = harness.remote().post("/api/pair", json={"code": code, "device_name": "MBP"})
    assert r.status_code == 401
    assert harness.app_db.list_devices() == []


def test_pin_a_wrong_code_is_refused_and_rate_limited(harness):
    harness.host().post("/api/pair/code")
    remote = harness.remote()
    statuses = [
        remote.post("/api/pair", json={"code": "AAAA-AAAA", "device_name": "x"}).status_code
        for _ in range(pairing.PAIRING_RATE_LIMIT + 1)
    ]
    assert statuses[:-1] == [401] * pairing.PAIRING_RATE_LIMIT
    assert statuses[-1] == 429


@pytest.mark.xfail(
    strict=True,
    reason="#5350: /api/pair rate limit keyed on a client-supplied Tailscale-User-Login header",
)
def test_defect_pairing_rate_limit_cannot_be_dodged_with_a_forged_tailscale_header(harness):
    """An unauthenticated caller rotates `Tailscale-User-Login` and is never rate limited.

    `_rate_limit_scope_from_request` (api/auth.py) buckets an unauthenticated request by
    the `tailscale-user-login` header when present. That header is only trustworthy when
    a Tailscale proxy set it, and Fichero's `tailscale serve --tcp` is a raw TCP forward
    that never sets it -- so on the LAN or the tailnet any caller can write it, and a
    fresh value per attempt gives a fresh bucket. The pairing guess limit (5/min) is then
    no limit. Fix: never key an unauthenticated limiter on a client header; use the
    peer address (and for the tailnet, a global bucket).
    """
    harness.host().post("/api/pair/code")
    remote = harness.remote()
    statuses = [
        remote.post(
            "/api/pair",
            json={"code": "AAAA-AAAA", "device_name": "x"},
            headers={"Tailscale-User-Login": f"attacker{i}@example.com"},
        ).status_code
        for i in range(pairing.PAIRING_RATE_LIMIT + 3)
    ]
    assert 429 in statuses, statuses


def test_pin_a_remote_caller_cannot_mint_a_pairing_code_without_a_token(harness):
    r = harness.remote().post("/api/pair/code")
    assert r.status_code in (401, 403)
    assert pairing._PAIRING_CODES == {}


def test_pin_a_remote_caller_with_the_bootstrap_token_is_refused(harness, monkeypatch):
    """The bootstrap secret is loopback-only in BOTH modes: a leaked .api-key is not a remote key."""
    for mode in ("0", "1"):
        monkeypatch.setenv("FICHERO_MULTIUSER", mode)
        r = harness.remote().post("/api/pair/code", headers=_bearer(harness.bootstrap))
        assert r.status_code in (401, 403), (mode, r.text)
        r = harness.remote().get("/api/documents", headers=_bearer(harness.bootstrap))
        assert r.status_code in (401, 403), (mode, r.text)


def test_pin_pairing_over_plain_http_from_the_network_is_refused(harness):
    code = harness.host().post("/api/pair/code").json()["code"]
    r = harness.client(base_url="http://paired.example", client_addr=REMOTE_ADDR).post(
        "/api/pair", json={"code": code, "device_name": "MBP"}
    )
    assert r.status_code == 400
    assert harness.app_db.list_devices() == []


def test_pin_a_paired_device_cannot_mint_pairing_codes_single_user(harness):
    """Multi-user off: only the host's bootstrap owner shows a pairing card; a device cannot chain."""
    token = harness.pair(harness.host())["device_token"]
    r = harness.remote().post("/api/pair/code", headers=_bearer(token))
    assert r.status_code == 403


def test_pin_a_paired_device_cannot_list_or_revoke_devices_over_rest_single_user(harness):
    a = harness.pair(harness.host(), device_name="MBP")
    b = harness.pair(harness.host(), device_name="iPad")
    remote = harness.remote()
    assert remote.get("/api/pair/devices", headers=_bearer(a["device_token"])).status_code == 403
    r = remote.post(f"/api/pair/devices/{b['device_id']}/revoke", headers=_bearer(a["device_token"]))
    assert r.status_code == 403
    assert harness.app_db.get_device(b["device_id"]).revoked is False


# =============================================================================
# 2. Revocation reaches every route family
# =============================================================================


def _every_authenticated_route(app):
    from fichero_server.api.auth import _UNAUTHENTICATED_PATHS, _UNAUTHENTICATED_PREFIXES

    for route in app.routes:
        if not isinstance(route, Route):
            continue
        path = route.path
        if path in _UNAUTHENTICATED_PATHS or path.startswith(_UNAUTHENTICATED_PREFIXES):
            continue
        concrete = path
        for name in route.param_convertors:
            concrete = concrete.replace("{" + name + ":path}", "x").replace("{" + name + "}", "x")
        for method in sorted(route.methods or ()):
            if method in ("HEAD", "OPTIONS"):
                continue
            yield method, concrete


def _sweep(harness, client, token):
    leaks = []
    for method, path in _every_authenticated_route(harness.app):
        r = client.request(method, path, headers=_bearer(token) if token else {})
        if r.status_code not in (401, 403):
            leaks.append((method, path, r.status_code))
    return leaks


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_a_revoked_device_is_refused_on_every_route(harness, monkeypatch, mode):
    """Every HTTP route the app serves -- reads, writes, /api/changes/stream, storage
    thumbnails and source files, IIIF, exports, undo -- refuses a revoked token. There
    are no websocket routes or mounts; the one middleware is the gate."""
    if mode == "1":
        _multiuser_on(harness, monkeypatch)
        device = _pair_as(harness, "owner", "MBP")
        revoker = harness.client()
        revoker.headers["Authorization"] = f"Bearer {_login(harness, 'owner')}"
    else:
        device = harness.pair(harness.host())
        revoker = harness.host()
    # Control: live, the token reads -- so the 401s below are the revocation, not a broken harness.
    assert harness.remote().get("/api/notes", headers=_bearer(device["device_token"])).status_code == 200
    revoke = revoker.post(f"/api/pair/devices/{device['device_id']}/revoke")
    assert revoke.status_code == 200, revoke.text
    assert harness.remote().get("/api/notes", headers=_bearer(device["device_token"])).status_code == 401
    routes = list(_every_authenticated_route(harness.app))
    assert len(routes) > 300
    assert _sweep(harness, harness.remote(), device["device_token"]) == []


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_an_expired_device_is_refused_on_every_route(harness, monkeypatch, mode):
    if mode == "1":
        users = _multiuser_on(harness, monkeypatch)
        owner_id = users["owner"].id
    else:
        from fichero_server.api.auth import ensure_owner_account

        owner_id = ensure_owner_account(harness.app_db).id
    raw = accounts.new_session_token()
    harness.app_db.create_device(
        name="Old", user_id=owner_id, token_hash=accounts.hash_token(raw), ttl=timedelta(seconds=-1)
    )
    assert _sweep(harness, harness.remote(), raw) == []


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_no_token_and_garbage_tokens_are_refused_on_every_route_from_the_network(
    harness, monkeypatch, mode
):
    monkeypatch.setenv("FICHERO_MULTIUSER", mode)
    remote = harness.remote()
    assert _sweep(harness, remote, None) == []
    assert _sweep(harness, remote, "not-a-token") == []


# =============================================================================
# 3. Multi-user off vs on
# =============================================================================


def test_pin_multiuser_on_a_viewers_device_cannot_write(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    bob = _pair_as(harness, "bob", "Bob's Mac")
    remote = harness.remote()
    r = remote.post("/api/notes", json={"body": "viewer write"}, headers=_bearer(bob["device_token"]))
    assert r.status_code == 403, r.text
    r = remote.get("/api/notes", headers=_bearer(bob["device_token"]))
    assert r.status_code == 200, r.text


def test_pin_multiuser_on_a_non_owner_device_cannot_revoke_anothers_device_over_rest(
    harness, monkeypatch
):
    _multiuser_on(harness, monkeypatch)
    owner_dev = _pair_as(harness, "owner", "Owner's iPad")
    alice_dev = _pair_as(harness, "alice", "Alice's Mac")
    r = harness.remote().post(
        f"/api/pair/devices/{owner_dev['device_id']}/revoke", headers=_bearer(alice_dev["device_token"])
    )
    assert r.status_code == 403
    assert harness.app_db.get_device(owner_dev["device_id"]).revoked is False


def test_an_editor_cannot_revoke_the_owners_device_through_actions_invoke(harness, monkeypatch):
    """Multi-user on: Alice (editor of ONE library) revokes the owner's iPad.

    `POST /api/pair/devices/{id}/revoke` checks `_can_manage_device` (owner, or the
    device's own person). The SAME change is registered as the action `device.revoke`
    (`api/routes/auth/pairing.py::_device_revoke_action`), and the generic
    `POST /api/actions/invoke` only asks `authz.assert_can_write(actor, library,
    device_id)` -- library write access, which an editor has. App-wide device
    management therefore hangs off ANY library role. `device.list` likewise hands an
    editor every person's device names and ids. Fix: the two actions must check what
    the route checks (owner or own device) -- or not be invokable from /invoke.
    """
    _multiuser_on(harness, monkeypatch)
    owner_dev = _pair_as(harness, "owner", "Owner's iPad")
    alice_dev = _pair_as(harness, "alice", "Alice's Mac")
    r = harness.remote().post(
        "/api/actions/invoke",
        json={"name": "device.revoke", "params": {"device_id": owner_dev["device_id"]}},
        headers=_bearer(alice_dev["device_token"]),
    )
    assert r.status_code == 403, r.text
    assert harness.app_db.get_device(owner_dev["device_id"]).revoked is False


def test_multiuser_off_does_not_promote_a_viewers_device_to_owner(harness, monkeypatch):
    """Bob is a VIEWER and paired his Mac while Multi-user was on. The owner switches
    Multi-user off. Bob's device token now authenticates as the owner: it writes to the
    library, the audit names "owner", and it can reach every other library on the host.

    `_authenticate_device_token` (api/auth.py) with multi-user off returns
    `_resolve_single_user_owner()` for ANY live device row, never looking at
    `device.user_id`. The ruling (`sharing.private-by-default`) makes a single-user
    device the owner because the OWNER paired it -- not a device another person paired.
    Fix: with multi-user off, accept a device only when its `user_id` is an active
    owner and refuse the rest (or revoke non-owner devices when Multi-user goes off).
    """
    _multiuser_on(harness, monkeypatch)
    bob = _pair_as(harness, "bob", "Bob's Mac")
    remote = harness.remote()
    # Multi-user on: a viewer cannot write, as it should be.
    assert remote.post("/api/notes", json={"body": "x"}, headers=_bearer(bob["device_token"])).status_code == 403

    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    r = remote.post(
        "/api/notes", json={"body": "written by a viewer"}, headers=_bearer(bob["device_token"])
    )
    assert r.status_code in (401, 403), (r.status_code, harness.audit_rows()[-1].actor)



def test_pin_disabling_a_person_cuts_off_their_paired_device(harness, monkeypatch):
    """The owner disables Alice; her paired Mac is refused at once (`PATCH /api/users/{id}`
    revokes her sessions and devices before `set_active`)."""
    users = _multiuser_on(harness, monkeypatch)
    alice = _pair_as(harness, "alice", "Alice's Mac")
    remote = harness.remote()
    assert remote.get("/api/notes", headers=_bearer(alice["device_token"])).status_code == 200
    owner_session = _login(harness, "owner")
    r = harness.client().patch(
        f"/api/users/{users['alice'].id}", json={"active": False}, headers=_bearer(owner_session)
    )
    assert r.status_code == 200, r.text
    assert harness.app_db.get_user(users["alice"].id).active is False
    assert remote.get("/api/notes", headers=_bearer(alice["device_token"])).status_code == 401


@pytest.mark.parametrize(
    "change",
    [{"display_name": "Alice B."}, {"password": "new-password-1"}, "reactivate"],
    ids=["rename", "password", "reactivate"],
)
def test_pin_editing_a_person_who_paired_a_device(harness, monkeypatch, change):
    users = _multiuser_on(harness, monkeypatch)
    _pair_as(harness, "alice", "Alice's Mac")
    owner_session = _login(harness, "owner")
    client = harness.client()
    url = f"/api/users/{users['alice'].id}"
    if change == "reactivate":
        assert client.patch(url, json={"active": False}, headers=_bearer(owner_session)).status_code == 200
        change = {"active": True}
    assert client.patch(url, json=change, headers=_bearer(owner_session)).status_code == 200


@pytest.mark.parametrize("paired", [False, True], ids=["signed-in", "paired"])
def test_promoting_a_person_who_has_signed_in_to_owner_works(harness, monkeypatch, paired):
    """`PATCH /api/users/{id} {"is_owner": true}` raises DuckDB's "Violates foreign key
    constraint ... still referenced by a foreign key in a different table" (a 500 to
    the app) whenever the person has a `sessions` row -- i.e. has ever signed in, which
    pairing a device requires.

    `AppDatabase.set_is_owner` -> `_update_user_fk_safe` (db/app.py). `is_owner` is in
    the index `idx_users_owner (is_owner, active)`, and DuckDB executes an UPDATE of an
    indexed column as delete+insert, which its FK check refuses while another table
    references the row. `_update_user_fk_safe` lifts only `library_roles` and
    `library_acl_overrides` out of the way, not `sessions`/`devices`/
    `enrollment_secrets`. (Disabling works only because the route revokes first.)
    Fix: lift every table that references `users(id)` -- or drop those FKs, as the
    library DB does -- and pin each `set_*` with a person holding a session AND a device.
    """
    users = _multiuser_on(harness, monkeypatch)
    if paired:
        _pair_as(harness, "alice", "Alice's Mac")
    else:
        _login(harness, "alice")
    owner_session = _login(harness, "owner")
    try:
        status = harness.client().patch(
            f"/api/users/{users['alice'].id}", json={"is_owner": True}, headers=_bearer(owner_session)
        ).status_code
    except Exception as exc:  # TestClient re-raises the server's ConstraintException
        status = repr(exc)
    assert status == 200, status
    assert harness.app_db.get_user(users["alice"].id).is_owner is True


def test_pin_multiuser_on_a_device_cannot_reach_a_library_it_was_not_shared(
    harness, monkeypatch, tmp_path
):
    """Alice's device names ANOTHER library on the host (only the owner's): every
    family refuses -- reads, the audit log, writes, undo."""
    from fichero_server.db import db_manager

    _multiuser_on(harness, monkeypatch)
    private = tmp_path / "private.fichero"
    private.mkdir()
    for sub in ("lance", "storage", "files"):
        (private / sub).mkdir()
    db_manager.get_database(private)
    harness.app_db.set_library_role(
        user_id=harness.app_db.get_user_by_username("owner").id,
        library_path=authz.normalize_library_path(private),
        role=authz.ROLE_OWNER,
    )
    alice = _pair_as(harness, "alice", "Alice's Mac")
    headers = {
        **_bearer(alice["device_token"]),
        "X-Fichero-Library-Path": quote(str(private), safe="/"),
    }
    remote = harness.remote()
    for method, path, body in (
        ("GET", "/api/documents", None),
        ("GET", "/api/notes", None),
        ("GET", "/api/actions/audit", None),
        ("POST", "/api/notes", {"body": "x"}),
        ("POST", "/api/actions/invoke", {"name": "note.create", "params": {"body": "x"}}),
        ("POST", "/api/actions/audit/nonexistent/undo", None),
    ):
        r = remote.request(method, path, headers=headers, json=body)
        assert r.status_code == 403, (method, path, r.status_code, r.text[:200])



def test_multiuser_on_the_host_app_can_list_and_revoke_a_device(harness, monkeypatch):
    """The host app talks to its engine with the loopback bootstrap token, which the
    ruling makes the owner. With Multi-user on, `_pairing_user` (pairing.py) demands a
    session user and 401s the bootstrap, so the Sharing pane cannot list paired devices
    or revoke a lost one -- `sharing.revoke` breaks the moment Multi-user is on.
    (`_owner_for_pairing` already has the one-active-owner bootstrap fallback;
    `_pairing_user` and `_can_manage_device` do not use it.) The spec notes this for
    minting a code; it holds for list and revoke too.
    """
    _multiuser_on(harness, monkeypatch)
    dev = _pair_as(harness, "owner", "Lost iPad")
    host = harness.host()
    assert host.get("/api/pair/devices").status_code == 200
    assert host.post(f"/api/pair/devices/{dev['device_id']}/revoke").status_code == 200
    assert harness.app_db.get_device(dev["device_id"]).revoked is True


# =============================================================================
# 4. Who did it
# =============================================================================


def _note_round_trip(harness, client, headers):
    """Create, edit, delete a note, then undo the delete. Returns the audit rows written."""
    before = {a.id for a in harness.audit_rows()}
    created = client.post("/api/notes", json={"body": "one"}, headers=headers)
    assert created.status_code == 200, created.text
    note_id = created.json()["id"]
    assert client.patch(f"/api/notes/{note_id}", json={"body": "two"}, headers=headers).status_code == 200
    assert client.delete(f"/api/notes/{note_id}", headers=headers).status_code == 204
    delete_row = [a for a in harness.audit_rows() if a.action_name == "note.delete"][-1]
    undo = client.post(f"/api/actions/audit/{delete_row.id}/undo", headers=headers)
    assert undo.status_code == 200, undo.text
    return [a for a in harness.audit_rows() if a.id not in before]


def test_pin_who_did_it_single_user_device_rows_name_owner_and_device(harness):
    dev = harness.pair(harness.host(), device_name="MBP")
    rows = _note_round_trip(harness, harness.remote(), _bearer(dev["device_token"]))
    assert len(rows) == 4
    for row in rows:
        assert row.actor == "owner", (row.action_name, row.actor)
        assert row.device == {"id": dev["device_id"], "name": "MBP"}, (row.action_name, row.device)


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_who_did_it_host_rows_name_owner_and_no_device(harness, monkeypatch, mode):
    if mode == "1":
        _multiuser_on(harness, monkeypatch)
    rows = _note_round_trip(harness, harness.host(), {})
    assert len(rows) == 4
    for row in rows:
        assert row.actor == "owner", (mode, row.action_name, row.actor)
        assert row.device is None


def test_pin_who_did_it_multiuser_device_rows_name_the_person_and_device(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    dev = _pair_as(harness, "alice", "Alice's Mac")
    rows = _note_round_trip(harness, harness.remote(), _bearer(dev["device_token"]))
    assert len(rows) == 4
    for row in rows:
        assert row.actor == "alice", (row.action_name, row.actor)
        assert row.device == {"id": dev["device_id"], "name": "Alice's Mac"}


def test_pin_who_did_it_cannot_be_claimed_by_a_header_or_body(harness):
    dev = harness.pair(harness.host(), device_name="MBP")
    remote = harness.remote()
    r = remote.post(
        "/api/actions/invoke",
        json={"name": "note.create", "params": {"body": "x"}, "actor": "owner"},
        headers=_bearer(dev["device_token"]),
    )
    assert r.status_code == 422
    r = remote.post(
        "/api/notes",
        json={"body": "x"},
        headers={**_bearer(dev["device_token"]), "X-Fichero-Client": "fichero-app-host"},
    )
    assert r.status_code == 200
    row = harness.audit_rows()[-1]
    assert row.device == {"id": dev["device_id"], "name": "MBP"}


# =============================================================================
# 5. Concurrency: two Macs edit the same thing
# =============================================================================


def test_two_macs_editing_one_note_the_second_stale_edit_is_refused(harness):
    """The host and the paired Mac both open a note at body "draft". The host saves
    "host words"; the Mac, which never saw that, saves "mac words". Both get 200 and the
    host's words are gone with nothing telling either person.

    Readings have a compare-and-set (`expected_counting_id`, 409 stale, pinned by
    `tests/unit/api/test_stale_keeps_your_words.py`); notes (`PATCH /api/notes/{id}`,
    `NotePatchRequest`) and document updates (`PUT /api/documents/{id}`) have none.
    With two Macs on one library (`sharing.edits-both-ways`) a lost update is now an
    everyday case. Fix: an optional `expected_updated_at`/version on the patch, refused
    with 409 naming the current text, as readings do.
    """
    host = harness.host()
    dev = harness.pair(host)
    remote = harness.remote()
    note_id = host.post("/api/notes", json={"body": "draft"}).json()["id"]
    seen_by_mac = remote.get(f"/api/notes/{note_id}", headers=_bearer(dev["device_token"])).json()

    assert host.patch(f"/api/notes/{note_id}", json={"body": "host words"}).status_code == 200
    stale = remote.patch(
        f"/api/notes/{note_id}",
        json={"body": "mac words", "expected_updated_at": seen_by_mac["updated_at"]},
        headers=_bearer(dev["device_token"]),
    )
    assert stale.status_code == 409, (stale.status_code, stale.text)


# =============================================================================
# 6. Transport
# =============================================================================


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_a_loopback_spoofing_header_never_makes_a_network_caller_loopback(harness, monkeypatch, mode):
    monkeypatch.setenv("FICHERO_MULTIUSER", mode)
    remote = harness.remote()
    for header in ("X-Forwarded-For", "X-Real-IP", "Forwarded"):
        value = "for=127.0.0.1" if header == "Forwarded" else "127.0.0.1"
        r = remote.get("/api/documents", headers={header: value})
        assert r.status_code in (401, 403), (header, r.status_code)
        r = remote.get("/api/documents", headers={header: value, **_bearer(harness.bootstrap)})
        assert r.status_code in (401, 403), (header, r.status_code)


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_a_forwarded_header_strips_loopback_owner_even_from_genuine_loopback(
    harness, monkeypatch, mode
):
    """A proxied request reaching the loopback listener is not owner (a proxy in front of it)."""
    monkeypatch.setenv("FICHERO_MULTIUSER", mode)
    r = harness.host().get("/api/documents", headers={"X-Forwarded-For": "203.0.113.9"})
    assert r.status_code in (401, 403)


@pytest.mark.parametrize("mode", ["0", "1"])
def test_pin_malformed_bearers_are_refused_from_the_network(harness, monkeypatch, mode):
    monkeypatch.setenv("FICHERO_MULTIUSER", mode)
    remote = harness.remote()
    for value in (
        "Bearer",
        "Bearer ",
        "bearer " + harness.bootstrap,
        "Basic " + harness.bootstrap,
        harness.bootstrap,
        "Bearer " + harness.bootstrap + " extra",
        "Bearer \t",
    ):
        r = remote.get("/api/documents", headers={"Authorization": value})
        assert r.status_code in (401, 403), (value, r.status_code)


def test_pin_loopback_with_the_bootstrap_token_is_owner(harness, monkeypatch):
    for mode in ("0", "1"):
        monkeypatch.setenv("FICHERO_MULTIUSER", mode)
        r = harness.host().get("/api/auth/identity")
        assert r.status_code == 200, (mode, r.text)
        assert r.json()["auth_kind"] == "bootstrap"


def test_unauthenticated_health_does_not_tell_the_network_about_an_open_library(harness):
    """`/api/health` is unauthenticated (the app polls it before it has a token). Given
    an X-Fichero-Library-Path it calls `assert_library_read_authorized`, which with
    multi-user OFF allows everyone (`authz._allowed` returns True before looking at the
    caller), so a caller on the LAN with no token gets the library's document count and
    `database` -- its absolute path on the host's disk (`no-local-paths-server-may-be-remote`).
    `engine_owner` is already withheld from non-loopback callers for exactly this reason.
    Fix: answer library-specific health only to an authenticated caller (or drop
    `database`/`document_count` for a caller without a token).
    """
    # The host opens the library, as the app does.
    assert harness.host().get("/api/documents").status_code == 200
    r = harness.remote().get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("database") is None and body.get("document_count") is None, body


def test_pin_a_paired_device_still_gets_its_librarys_health(harness, monkeypatch):
    """#5349's fix withholds library details only from ANONYMOUS network callers: a paired Mac
    polling health with its token must still see the library it opened, or its readiness check
    would never see the library as open."""
    owner_dev = harness.pair(harness.host(), device_name="Owner's iPad")  # Multi-user off
    assert harness.host().get("/api/documents").status_code == 200
    r = harness.remote().get("/api/health", headers=_bearer(owner_dev["device_token"]))
    assert r.status_code == 200
    assert r.json().get("document_count") is not None, r.json()


def test_pin_an_edit_against_the_current_version_is_saved(harness):
    """#5348's refusal is only for a STALE edit: saving against the version you last saw works."""
    host = harness.host()
    note_id = host.post("/api/notes", json={"body": "draft"}).json()["id"]
    seen = host.get(f"/api/notes/{note_id}").json()
    r = host.patch(f"/api/notes/{note_id}", json={"body": "mine", "expected_updated_at": seen["updated_at"]})
    assert r.status_code == 200 and r.json()["body"] == "mine", r.text
