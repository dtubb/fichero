"""multiuser.turning-on-needs-an-owner-password (#5908): turning Multi-user on leaves an account someone can sign in to.

Spec: docs/contributor_manual/specs/transport/multiuser-always-on.md. First launch makes a key-only owner with a random
password nobody knows; the switch refuses until a person chose the owner's password, which can be set while it is off.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.security import accounts, multiuser


def _owner(app_db, active=True):
    # the first-run owner: a random password, never recorded as chosen
    return app_db.create_user(username="owner", display_name="Daniel", password_hash=accounts.hash_password("random-" * 5),
                              is_owner=True, active=active)


def test_no_owner_and_a_key_only_owner_both_refuse(app_db):
    assert multiuser.owner_password_gap(app_db)
    _owner(app_db)
    assert multiuser.owner_password_gap(app_db), "the random first-run password is not a chosen one"


def test_a_chosen_owner_password_clears_the_gap_and_an_inactive_owner_does_not(app_db):
    owner = _owner(app_db, active=False)
    multiuser.note_owner_password_set(app_db)
    assert multiuser.owner_password_gap(app_db), "an inactive owner cannot sign in"
    app_db.set_active(owner.id, True)
    assert multiuser.owner_password_gap(app_db) is None


def test_the_switch_refuses_in_words_until_the_password_is_chosen(test_package, app_db, monkeypatch):
    from fichero_server.actions import ActionContext, registry
    from fichero_server.actions.registry import ActionRefused
    from fichero_server.db import db_manager

    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)
    _owner(app_db)
    library_db = db_manager.get_database(test_package)
    ctx = ActionContext(actor="owner", library_path=str(test_package), is_bootstrap=True)
    with pytest.raises(ActionRefused, match="owner's account to have a password"):
        registry.invoke(library_db, "sharing.set_multiuser", {"enabled": True}, ctx)
    assert app_db.get_setting("multiuser.enabled") != "true"
    multiuser.note_owner_password_set(app_db)
    registry.invoke(library_db, "sharing.set_multiuser", {"enabled": True}, ctx)
    assert app_db.get_setting("multiuser.enabled") == "true"
    registry.invoke(library_db, "sharing.set_multiuser", {"enabled": False}, ctx)  # turning off needs nothing


def _update(app_db, monkeypatch, user_id, **fields):
    from fichero_server.api.routes.auth import accounts as routes

    monkeypatch.setattr(routes, "_use_multiuser_auth", lambda: False)
    bootstrap = fields.pop("bootstrap", True)
    request = SimpleNamespace(state=SimpleNamespace(bootstrap_auth=bootstrap))
    return routes.update_user(request, user_id, routes.UpdateUserRequest(**fields), app_db)


def test_the_owner_password_can_be_set_while_multiuser_is_off_and_is_recorded(app_db, monkeypatch):
    owner = _owner(app_db)
    _update(app_db, monkeypatch, owner.id, password="a chosen one")
    assert accounts.verify_password("a chosen one", app_db.get_user(owner.id).password_hash)
    assert multiuser.owner_password_gap(app_db) is None


def test_while_off_nothing_else_is_allowed_and_not_for_a_paired_device(app_db, monkeypatch):
    owner = _owner(app_db)
    member = app_db.create_user(username="ann", display_name="Ann", password_hash=accounts.hash_password("x"), is_owner=False)
    for kwargs in ({"user_id": member.id, "password": "p"},            # not the owner
                   {"user_id": owner.id, "display_name": "Other"},      # not the password
                   {"user_id": owner.id, "password": "p", "active": False},
                   {"user_id": owner.id, "password": "p", "bootstrap": False}):  # not the app's own credential
        with pytest.raises(HTTPException) as refused:
            _update(app_db, monkeypatch, **kwargs)
        assert refused.value.status_code == 404
    assert multiuser.owner_password_gap(app_db), "nothing was recorded"
