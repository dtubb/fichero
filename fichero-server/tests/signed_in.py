"""Sign in as a person through a client, the way every real client does (multiuser-always-on, slice 3).

Tests that need "a signed-in someone" use `signed_in_client` instead of the ambient owner (loopback plus the bootstrap
token), which slice 10 removes. It runs the real challenge/sign-in routes, so what it returns is a real session.
"""

from __future__ import annotations

import base64
from typing import NamedTuple

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def new_key():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return key, pem


def signature_for(
    key, client_id: str, issued: dict, *, engine_id=None, expires_at=None, purpose="fichero-sign-in-v1"
) -> str:
    """Base64 DER signature over the domain-separated message (see multiuser-always-on.md)."""
    parts = [purpose, engine_id or issued["engine_id"], client_id, issued["nonce"], str(expires_at or issued["expires_at"])]
    return base64.b64encode(key.sign("\x00".join(parts).encode(), ec.ECDSA(hashes.SHA256()))).decode()


class SignedIn(NamedTuple):
    token: str
    headers: dict
    key: object
    client: object


def signed_in_client(harness, user, *, kind="device", name="Test client", host="test-host") -> SignedIn:
    """Register a client for `user`, sign in through the real routes, return the session."""
    key, pem = new_key()
    client = harness.app_db.create_client(user_id=user.id, kind=kind, name=name, host=host, public_key_pem=pem)
    http = harness.client()
    issued = http.post("/api/auth/challenge", json={"client_id": client.id}).json()
    signed = http.post(
        "/api/auth/sign-in",
        json={"client_id": client.id, "nonce": issued["nonce"], "signature": signature_for(key, client.id, issued)},
    )
    assert signed.status_code == 200, signed.text
    token = signed.json()["session_token"]
    return SignedIn(token, {"Authorization": f"Bearer {token}"}, key, client)


def uds_client(harness, peer=None):
    """A client whose requests arrive as if over the engine's Unix socket (the server stamps `fichero.transport`).

    `peer` stands for the socket's verified peer credentials (`fichero.peer`: uid, pid, exe, signer)."""
    from fastapi.testclient import TestClient

    async def over_the_socket(scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope["fichero.transport"] = "uds"
            if peer is not None:
                scope["fichero.peer"] = peer
        await harness.app(scope, receive, send)

    return TestClient(over_the_socket, base_url="http://testserver", headers={**harness.lib_header, "Authorization": ""})
