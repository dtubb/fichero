"""multiuser.person-bound-invite (#2403 slice 10, release bar #5910 item 6): a pairing code minted FOR a named person
binds the device that redeems it to that person, with no password and no way to become anyone else."""

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.auth import pairing
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _login,
    _multiuser_on,
    harness,
)


class _FakeRequest:
    """The ambient start-up key: bootstrap auth, no signed-in person. Called directly, not over HTTP, so no test line
    acts as the ambient owner (the ratchet)."""

    class state:
        bootstrap_auth = True


def _as(harness, username, library=True):
    """A signed-in client; `library` sends the open library's header, as the app does for every request."""
    client = harness.client()
    client.headers.update(_bearer(_login(harness, username)))
    if library:
        client.headers["X-Fichero-Library-Path"] = str(harness.library)
    return client


def _invite(harness, username, client=None, **options):
    """Minted by the owner SIGNED IN, never the ambient host (the ambient-owner ratchet must not grow)."""
    return (client or _as(harness, "owner")).post("/api/pair/code", json={"username": username, **options})


def _redeem(harness, code, bare=False, **extra):
    """The person's side. An existing person proves who they are with their password (`pw-<name>` in these tests);
    `bare=True` sends none."""
    record = pairing._PAIRING_CODES.get(code)
    if not bare and record is not None and record.person and not record.new_person:
        extra.setdefault("password", "pw-" + record.person)
    return harness.remote().post("/api/pair", json={"code": code, "device_name": "Ann's Mac", **extra})


def test_a_code_for_a_named_person_binds_the_device_to_that_person(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "alice")
    assert minted.status_code == 200, minted.text
    assert minted.json()["person"] == "alice"

    paired = _redeem(harness, minted.json()["code"])
    assert paired.status_code == 200, paired.text
    assert harness.app_db.get_device(paired.json()["device_id"]).user_id == users["alice"].id


def test_two_people_two_codes_each_device_is_its_own_person(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    ids = {}
    for name in ("alice", "bob"):
        ids[name] = _redeem(harness, _invite(harness, name).json()["code"]).json()["device_id"]
    assert harness.app_db.get_device(ids["alice"]).user_id == users["alice"].id
    assert harness.app_db.get_device(ids["bob"]).user_id == users["bob"].id


def test_redeeming_as_someone_else_is_refused_and_spends_nothing(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "alice").json()["code"]
    refused = _redeem(harness, code, username="bob", password="pw-bob", bare=True)
    assert refused.status_code == 403
    assert "for another person" in refused.json()["detail"]
    assert harness.app_db.list_devices() == []
    assert _redeem(harness, code).status_code == 200, "the invitation is still good for the person it names"


def test_a_code_is_good_once(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "alice").json()["code"]
    assert _redeem(harness, code).status_code == 200
    assert _redeem(harness, code).status_code == 401


def test_only_a_signed_in_owner_may_name_a_person(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    assert _invite(harness, "bob", client=_as(harness, "alice")).status_code == 403
    ambient = _FakeRequest()  # the start-up key (loopback + bootstrap), no person signed in
    with pytest.raises(HTTPException) as refused:
        pairing._invited_person(ambient, harness.app_db, "bob")
    assert refused.value.status_code == 403 and "signed-in owner" in refused.value.detail
    assert _invite(harness, "bob", client=_as(harness, "owner")).status_code == 200


def test_a_disabled_person_gets_no_code(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    harness.app_db.set_active(users["bob"].id, False)
    assert _invite(harness, "bob").status_code == 403


def test_naming_a_person_needs_multi_user_on(harness):
    """The mint is authenticated, so it may say why; the redeem never does (see the next test)."""
    with pytest.raises(HTTPException) as refused:
        pairing._invited_person(_FakeRequest(), harness.app_db, "alice")
    assert refused.value.status_code == 409


def test_a_code_that_names_no_person_is_as_before(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _as(harness, "owner").post("/api/pair/code")
    assert minted.json()["person"] is None
    assert _redeem(harness, minted.json()["code"]).status_code == 401, "person required, as sharing.device-chooses-person"
    assert minted.json()["invite_id"] is None and minted.json()["role"] is None


def test_the_redeem_is_audited_with_the_person_the_minter_and_the_device(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    paired = _redeem(harness, _invite(harness, "alice").json()["code"]).json()
    rows = [r for r in harness.app_db.list_action_audits() if r.action_name == "device.pair_for_person"]
    assert len(rows) == 1
    assert rows[0].target_ids == [paired["device_id"]]
    assert rows[0].params["person"] == "alice" and rows[0].params["minted_by"] == "owner"
    assert rows[0].actor == "invite:owner"


def test_the_bound_device_has_that_persons_role_never_the_owners(harness, monkeypatch):
    """bob is a viewer (reads, cannot write); alice is an editor (writes). Neither is the owner."""
    users = _multiuser_on(harness, monkeypatch)
    for name, may_write in (("bob", False), ("alice", True)):
        paired = _redeem(harness, _invite(harness, name).json()["code"]).json()
        device = harness.app_db.get_device(paired["device_id"])
        assert device.user_id == users[name].id
        assert harness.app_db.get_user(device.user_id).is_owner is False
        wrote = harness.remote().post("/api/notes", json={"body": f"{name} writes"},
                                      headers=_bearer(paired["device_token"]))
        assert (wrote.status_code < 300) is may_write, f"{name}: {wrote.status_code} {wrote.text}"


def test_a_redeem_after_multi_user_was_turned_off_is_refused_like_a_bad_code_and_spends_nothing(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "alice").json()["code"]
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    refused = _redeem(harness, code)
    assert refused.status_code == 401 and refused.json()["detail"] == "invalid or expired pairing code"
    assert harness.app_db.list_devices() == []
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    assert _redeem(harness, code).status_code == 200, "nothing was spent"


# -- owner's rulings 2026-10-20: viewer by default, 7 days by default (up to never), revocable, a password the person sets ---
from datetime import timedelta  # noqa: E402

from fichero_server.security import authz  # noqa: E402


def _lib(harness):
    return authz.normalize_library_path(harness.library)


def test_an_invitation_defaults_to_a_viewer_and_seven_days(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    before = pairing.utc_now()
    minted = _invite(harness, "carol").json()
    record = pairing._PAIRING_CODES[minted["code"]]
    assert minted["role"] == "viewer" and record.role == "viewer"
    assert timedelta(days=7) - timedelta(minutes=1) <= record.expires_at - before <= timedelta(days=7, minutes=1)
    assert minted["never_expires"] is False and minted["expires_at"] is not None


def test_the_owner_may_pick_editor_and_a_lifetime_per_invitation(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "carol", role="editor", expires_in_days=30).json()
    record = pairing._PAIRING_CODES[minted["code"]]
    assert record.role == "editor"
    assert timedelta(days=29, hours=23) <= record.expires_at - pairing.utc_now() <= timedelta(days=30, minutes=1)
    assert _invite(harness, "carol", role="admin").status_code == 422, "only viewer or editor"
    assert _invite(harness, "carol", expires_in_days=0).status_code == 422
    assert _invite(harness, "carol", expires_in_days=3651).status_code == 422


def test_an_invitation_that_never_expires_is_allowed_and_stays_good(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "carol", never_expires=True).json()
    assert minted["never_expires"] is True and minted["expires_at"] is None
    assert pairing._PAIRING_CODES[minted["code"]].expires_at == pairing.NEVER_EXPIRES
    pairing._prune_pairing_codes(pairing.utc_now() + timedelta(days=3650))
    assert minted["code"] in pairing._PAIRING_CODES, "never means never: not pruned"


def test_a_lifetime_belongs_to_an_invitation_to_a_named_person(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    refused = _as(harness, "owner").post("/api/pair/code", json={"never_expires": True})
    assert refused.status_code == 400


def test_an_invitation_code_is_longer_than_the_ten_minute_code(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    short = _as(harness, "owner").post("/api/pair/code").json()["code"]
    long = _invite(harness, "carol").json()["code"]
    assert len(short.replace("-", "")) == 8 and len(long.replace("-", "")) == 16, "80 bits for a code that lives days"


def test_a_new_person_sets_their_own_password_and_gets_the_role_on_the_library(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "carol", display_name="Carol", library=str(harness.library)).json()
    assert harness.app_db.get_user_by_username("carol") is None, "no account until the person accepts"

    no_password = _redeem(harness, minted["code"])
    assert no_password.status_code == 422 and "password" in no_password.json()["detail"]
    assert _redeem(harness, minted["code"], new_password="short").status_code == 422
    assert harness.app_db.get_user_by_username("carol") is None and harness.app_db.list_devices() == []

    paired = _redeem(harness, minted["code"], new_password="a long secret")
    assert paired.status_code == 200, paired.text
    carol = harness.app_db.get_user_by_username("carol")
    assert carol is not None and carol.is_owner is False and carol.display_name == "Carol"
    assert harness.app_db.get_device(paired.json()["device_id"]).user_id == carol.id
    assert harness.app_db.get_library_role(carol.id, _lib(harness)).role == "viewer"
    signed_in = harness.client().post("/api/auth/login", json={"username": "carol", "password": "a long secret"})
    assert signed_in.status_code == 200, "the password the person chose is the one that signs in"


def test_the_owner_never_sets_a_new_persons_password(harness, monkeypatch):
    """The mint takes no password, and a redeem is what makes the account: an owner session cannot do it for them."""
    _multiuser_on(harness, monkeypatch)
    assert "password" not in pairing.PairCodeRequest.model_fields and "new_password" not in pairing.PairCodeRequest.model_fields
    minted = _invite(harness, "carol", password="owner-chosen")
    assert minted.status_code == 200
    assert harness.client().post("/api/auth/login", json={"username": "carol", "password": "owner-chosen"}).status_code in (401, 404)


def test_an_existing_person_proves_themselves_with_their_password_and_keeps_their_role(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "bob", role="editor", library=str(harness.library)).json()["code"]
    assert _redeem(harness, code, bare=True).status_code == 401
    assert _redeem(harness, code, password="wrong").status_code == 401
    assert pairing._PAIRING_CODES.get(code) is not None, "a wrong password spends nothing"
    assert _redeem(harness, code).status_code == 200
    assert harness.app_db.get_library_role(users["bob"].id, _lib(harness)).role == "viewer", "an invitation never changes a role they have"


def test_a_used_invitation_cannot_make_a_second_account_or_device(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "carol").json()["code"]
    assert _redeem(harness, code, new_password="a long secret").status_code == 200
    assert _redeem(harness, code, new_password="another one!").status_code == 401
    assert len(harness.app_db.list_devices()) == 1


def test_an_expired_invitation_is_refused_and_a_taken_name_is_said(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "carol").json()["code"]
    pairing._PAIRING_CODES[code].expires_at = pairing.utc_now() - timedelta(seconds=1)
    assert _redeem(harness, code, new_password="a long secret").status_code == 401
    other = _invite(harness, "dave").json()["code"]
    harness.app_db.create_user(username="dave", display_name="Dave", password_hash="x", is_owner=False)
    assert _redeem(harness, other, new_password="a long secret").status_code == 409


def test_the_owner_lists_unused_invitations_without_the_codes_and_revokes_any_of_them(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    owner = _as(harness, "owner")
    plain = _invite(harness, "carol", client=owner).json()
    forever = _invite(harness, "dave", client=owner, never_expires=True, role="editor").json()
    listed = owner.get("/api/pair/invites").json()
    assert {i["person"] for i in listed} == {"carol", "dave"}
    assert plain["code"] not in str(listed) and forever["code"] not in str(listed)
    by_person = {i["person"]: i for i in listed}
    assert by_person["dave"]["never_expires"] is True and by_person["dave"]["expires_at"] is None
    assert by_person["carol"]["minted_by"] == "owner" and by_person["carol"]["role"] == "viewer"

    assert owner.delete(f"/api/pair/invites/{by_person['dave']['id']}").status_code == 200
    assert _redeem(harness, forever["code"], new_password="a long secret").status_code == 401, "revoked, though it never expired"
    assert owner.delete(f"/api/pair/invites/{by_person['dave']['id']}").status_code == 404
    assert [i["person"] for i in owner.get("/api/pair/invites").json()] == ["carol"]
    audited = [r for r in harness.app_db.list_action_audits() if r.action_name == "invite.revoke"]
    assert len(audited) == 1 and audited[0].params["person"] == "dave"


def test_only_an_owner_lists_or_revokes_invitations(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    invite_id = _invite(harness, "carol").json()["invite_id"]
    member = _as(harness, "alice")
    assert member.get("/api/pair/invites").status_code == 403
    assert member.delete(f"/api/pair/invites/{invite_id}").status_code == 403


def test_a_role_on_a_library_needs_the_owner_of_that_library(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    refused = _invite(harness, "carol", library="/somewhere/else.fichero")
    assert refused.status_code == 403


def test_the_audit_row_of_a_new_persons_redeem_names_the_minting_owner_the_role_and_the_account(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "carol", role="editor", library=str(harness.library), never_expires=True).json()["code"]
    paired = _redeem(harness, code, new_password="a long secret").json()
    row = next(r for r in harness.app_db.list_action_audits() if r.action_name == "device.pair_for_person")
    assert row.target_ids == [paired["device_id"]] and row.actor == "invite:owner"
    assert row.params["new_person"] is True and row.params["role"] == "editor" and row.params["never_expires"] is True


# -- review 635 -------------------------------------------------------------------------------------------------------
import threading  # noqa: E402


def test_an_invitation_defaults_to_the_library_open_when_it_is_minted_and_the_person_can_read_it_but_not_write(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "carol").json()  # no `library` in the request: the header names the open one
    assert pairing._PAIRING_CODES[minted["code"]].library == _lib(harness)
    paired = _redeem(harness, minted["code"], new_password="a long secret").json()
    carol = harness.app_db.get_user_by_username("carol")
    assert harness.app_db.get_library_role(carol.id, _lib(harness)).role == "viewer" == minted["role"]
    token = _bearer(paired["device_token"])
    read = harness.remote().get("/api/notes", headers=token)
    assert read.status_code == 200, read.text
    wrote = harness.remote().post("/api/notes", json={"body": "carol writes"}, headers=token)
    assert wrote.status_code == 403, wrote.text


def test_a_new_person_with_no_library_at_all_is_refused_at_the_mint_in_words(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    refused = _invite(harness, "carol", client=_as(harness, "owner", library=False))
    assert refused.status_code == 409 and "library" in refused.json()["detail"]
    assert pairing._PAIRING_CODES == {}, "nothing was minted"


def test_the_answer_the_list_and_the_audit_say_the_role_really_granted(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    owner = _as(harness, "owner")
    new = _invite(harness, "carol", client=owner, role="editor").json()
    existing = _invite(harness, "bob", client=owner, role="editor").json()  # bob is a viewer and stays one
    assert new["role"] == "editor" and existing["role"] == "viewer"
    listed = {i["person"]: i["role"] for i in owner.get("/api/pair/invites").json()}
    assert listed == {"carol": "editor", "bob": "viewer"}
    minted = {r.params["person"]: r.params["role"] for r in harness.app_db.list_action_audits() if r.action_name == "invite.mint"}
    assert minted == {"carol": "editor", "bob": "viewer"}


def test_every_mint_is_audited_with_the_owner_the_role_the_library_and_the_expiry_never_the_code(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "carol", never_expires=True).json()
    rows = [r for r in harness.app_db.list_action_audits() if r.action_name == "invite.mint"]
    assert len(rows) == 1 and rows[0].actor == "owner" and rows[0].target_ids == [minted["invite_id"]]
    assert rows[0].params["never_expires"] is True and rows[0].params["library"] == _lib(harness)
    assert minted["code"] not in str(rows[0].params) and minted["code"] not in str(rows[0].target_ids)


def test_the_list_and_revoke_admit_a_signed_in_owner_only_not_the_start_up_key(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    with pytest.raises(HTTPException) as refused:
        pairing._signed_in_owner(_FakeRequest())
    assert refused.value.status_code == 403
    assert _as(harness, "alice").get("/api/pair/invites").status_code == 403
    assert _as(harness, "owner").get("/api/pair/invites").status_code == 200


def test_two_redeems_of_one_code_at_once_make_one_device_and_the_other_is_told(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "carol").json()["code"]
    gate, answers = threading.Barrier(2), []

    def go():
        remote = harness.remote()
        gate.wait()
        answers.append(remote.post("/api/pair", json={"code": code, "device_name": "Mac", "new_password": "a long secret"}).status_code)

    workers = [threading.Thread(target=go) for _ in range(2)]
    [w.start() for w in workers]
    [w.join() for w in workers]
    assert sorted(answers).count(200) == 1 and set(answers) <= {200, 401, 409}, answers
    assert len(harness.app_db.list_devices()) == 1 and harness.app_db.get_user_by_username("carol") is not None


def test_a_code_being_redeemed_refuses_a_second_redeem_in_words_and_a_refusal_releases_it(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "carol").json()["code"]
    pairing._PAIRING_CODES[code].claimed = True  # another redeem is under way
    busy = _redeem(harness, code, new_password="a long secret")
    assert busy.status_code == 409 and "being used right now" in busy.json()["detail"]
    assert pairing._PAIRING_CODES[code].claimed is True, "the loser never releases the winner's claim"
    pairing._PAIRING_CODES[code].claimed = False
    assert _redeem(harness, code).status_code == 422 and pairing._PAIRING_CODES[code].claimed is False, "a refusal releases it"
    assert _redeem(harness, code, new_password="a long secret").status_code == 200


def test_a_refused_redeem_hints_the_next_step_in_a_typed_header_not_in_prose(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    new = _redeem(harness, _invite(harness, "carol").json()["code"])
    assert new.status_code == 422 and new.headers["X-Fichero-Pair-Next"] == "choose-password"
    existing = _redeem(harness, _invite(harness, "alice").json()["code"], bare=True)
    assert existing.status_code == 401 and existing.headers["X-Fichero-Pair-Next"] == "person-required"


def test_a_new_name_differing_only_in_case_is_refused_as_taken_at_create_mint_and_redeem(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    owner = _as(harness, "owner")
    clash = owner.post("/api/users", json={"username": "ALICE", "display_name": "Other", "password": "pw-other-1"})
    assert clash.status_code == 409 and "exists" in clash.json()["detail"]
    minted = _invite(harness, "Alice", client=owner)
    assert minted.status_code == 409 and "differs only in case" in minted.json()["detail"], "not a new person, not alice"
    assert pairing._PAIRING_CODES == {}
    code = _invite(harness, "dave", client=owner).json()["code"]
    harness.app_db.create_user(username="DAVE", display_name="Dave", password_hash="x", is_owner=False)
    assert _redeem(harness, code, new_password="a long secret").status_code == 409, "taken by 'DAVE' meanwhile"


def test_lookups_stay_exact_so_an_existing_carol_and_carol_pair_each_sign_in_as_themselves(harness, monkeypatch):
    """The older pair (made before names were checked case-folded) must not lock the newer account out."""
    _multiuser_on(harness, monkeypatch)
    from fichero_server.security import accounts

    older = harness.app_db.create_user(username="carol", display_name="carol", password_hash=accounts.hash_password("pw-lower"))
    newer = harness.app_db.create_user(username="Carol", display_name="Carol", password_hash=accounts.hash_password("pw-Upper"))
    assert harness.app_db.get_user_by_username("carol").id == older.id
    assert harness.app_db.get_user_by_username("Carol").id == newer.id
    lower = harness.client().post("/api/auth/login", json={"username": "carol", "password": "pw-lower"})
    upper = harness.client().post("/api/auth/login", json={"username": "Carol", "password": "pw-Upper"})
    assert lower.status_code == 200 and upper.status_code == 200
    assert harness.client().post("/api/auth/login", json={"username": "carol", "password": "pw-Upper"}).status_code == 401
    assert harness.app_db.username_taken("CAROL") is True
    assert _as(harness, "owner").post("/api/users", json={"username": "CAROL", "display_name": "x", "password": "pw-new-123"}).status_code == 409
