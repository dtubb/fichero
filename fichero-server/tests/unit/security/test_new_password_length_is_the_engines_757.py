"""`sharing.settings.accounts-add-sheet` (## 757): the 8-character rule for a NEW account's password is the engine's, not
only the app's hint. Both routes that set one for a new account refuse a short password with a 422 that says why."""

import pytest

from tests.unit.security.test_invite_registers_public_key_to_spec import (  # noqa: F401
    _fresh_redeem_rate_limit,
    _invite,
    _redeem,
)
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _login,
    _multiuser_on,
    harness,
)


def _create(harness, password):
    token = _login(harness, "owner")
    return harness.client().post(
        "/api/users", headers=_bearer(token), json={"username": "cy", "display_name": "Cy", "password": password})


@pytest.mark.parametrize("password", ["p", "1234567"])
def test_creating_an_account_with_a_short_password_is_refused_in_words(harness, monkeypatch, password):
    _multiuser_on(harness, monkeypatch)
    refused = _create(harness, password)
    assert refused.status_code == 422 and "at least 8 characters" in refused.json()["detail"], refused.text


def test_creating_an_account_with_eight_characters_works(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    assert _create(harness, "12345678").status_code == 200


@pytest.mark.parametrize("password", ["p", "1234567"])
def test_redeeming_an_invite_with_a_short_password_is_refused_in_words(harness, monkeypatch, password):
    _multiuser_on(harness, monkeypatch)
    refused = _redeem(harness, _invite(harness), new_password=password)
    assert refused.status_code == 422 and "at least 8 characters" in refused.json()["detail"], refused.text


def test_a_key_redemption_has_no_password_and_is_not_held_to_the_rule(harness, monkeypatch):
    from tests.signed_in import new_key

    _multiuser_on(harness, monkeypatch)
    _key, pem = new_key()
    assert _redeem(harness, _invite(harness), public_key_pem=pem, client={"kind": "app", "name": "m"}).status_code == 200
