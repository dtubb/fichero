"""Password hashing + session-token primitives for multi-user accounts (#2022).

Security-critical core, kept dependency-free and self-contained: it imports
nothing from the rest of the engine and nothing imports it yet, so it can be
reviewed and tested in isolation before the account storage / routes / middleware
wire it in.

Design decisions (see EPIC #2021 / #2022):
- **Hashing = stdlib ``hashlib.scrypt``** (memory-hard) — NOT argon2/bcrypt — so
  there is no new dependency to bundle into the engine app.
- Passwords are stored as a self-describing string ``scrypt$n$r$p$salt$hash``
  (salt + parameters embedded) so parameters can evolve without a migration.
- Verification is **constant-time** (``hmac.compare_digest``).
- Session tokens: the raw token is a ``secrets.token_urlsafe`` string handed to
  the client ONCE; only its SHA-256 hash is ever stored, so a leaked DB cannot
  be used to impersonate sessions (same principle as the password hash).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# scrypt cost parameters. n must be a power of two. These are a reasonable
# interactive-login cost on a Mac; bump n to raise cost later (the encoded hash
# records the params used, so old hashes keep verifying).
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_DK_LEN = 32
_SCHEME = "scrypt"


def hash_password(password: str) -> str:
    """Hash a plaintext password into a self-describing ``scrypt$...`` string.

    Raises ``ValueError`` on an empty password (callers must enforce a policy,
    but never hash the empty string into a usable credential).
    """
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DK_LEN,
    )
    return "$".join(
        [
            _SCHEME,
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            salt.hex(),
            derived.hex(),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verify ``password`` against a stored ``scrypt$...`` string.

    Returns ``False`` (never raises) on any malformed/unknown encoding so a
    corrupt row can't crash the login path or leak which part failed.
    """
    if not password or not encoded:
        return False
    try:
        scheme, n_s, r_s, p_s, salt_hex, hash_hex = encoded.split("$")
        if scheme != _SCHEME:
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False

    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
    )
    return hmac.compare_digest(candidate, expected)


def new_session_token() -> str:
    """Return a fresh opaque session token to hand to a client exactly once."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hex of a session token. Only this hash is stored server-side;
    incoming bearer tokens are hashed and compared against it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
