"""Password hashing + session-token primitives (#2022)."""

from __future__ import annotations

import pytest

from fichero_server.security import accounts
from fichero_server.api.routes.auth_accounts import _dummy_password_hash


def test_hash_is_self_describing_and_salted():
    h = accounts.hash_password("hunter2")
    assert h.startswith("scrypt$")
    # Two hashes of the same password differ (random salt).
    assert accounts.hash_password("hunter2") != h


def test_verify_roundtrip():
    h = accounts.hash_password("correct horse battery staple")
    assert accounts.verify_password("correct horse battery staple", h) is True
    assert accounts.verify_password("wrong", h) is False


def test_dummy_password_hash_is_cached_stable_scrypt_and_verifies_false():
    _dummy_password_hash.cache_clear()

    first = _dummy_password_hash()
    second = _dummy_password_hash()

    assert first is second
    assert first.startswith("scrypt$")
    assert accounts.verify_password("wrong", first) is False


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        accounts.hash_password("")
    # Empty inputs never verify.
    assert accounts.verify_password("", accounts.hash_password("x")) is False


@pytest.mark.parametrize(
    "bad",
    ["", "not-a-hash", "scrypt$bad", "bcrypt$1$2$3$ab$cd", "scrypt$x$y$z$gg$hh"],
)
def test_malformed_encoding_returns_false_not_raise(bad):
    # A corrupt/unknown stored hash must fail closed, never crash login.
    assert accounts.verify_password("anything", bad) is False


def test_unknown_scheme_rejected():
    # Right shape, wrong scheme.
    h = accounts.hash_password("pw")
    forged = "argon2$" + h.split("$", 1)[1]
    assert accounts.verify_password("pw", forged) is False


def test_session_token_unique_and_opaque():
    a = accounts.new_session_token()
    b = accounts.new_session_token()
    assert a != b
    assert len(a) >= 32


def test_token_hash_is_stable_and_one_way():
    tok = accounts.new_session_token()
    assert accounts.hash_token(tok) == accounts.hash_token(tok)
    assert accounts.hash_token(tok) != tok  # store the hash, not the token
    assert len(accounts.hash_token(tok)) == 64  # sha256 hex
