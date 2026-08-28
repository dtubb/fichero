"""Which client surfaces have talked to this engine, and when.

The app, the `fichero` CLI, and the MCP server all send an
``X-Fichero-Client`` header (attribution metadata, #4469). This module
keeps an in-memory last-seen table per client name so the Sharing UI can
answer "is anything actually connected?" (Daniel, 2026-08-27: "shouldn't
we see in Sharing that you're connected?").

In-memory on purpose: presence is a property of THIS engine process; a
restart genuinely resets it.
"""

from __future__ import annotations

import threading

from pydantic import BaseModel

from fichero_server.core.timeutil import utc_now


class ClientPresenceEntry(BaseModel):
    client: str
    first_seen: str
    last_seen: str
    requests: int
    transport: str


class ConnectedClientsResponse(BaseModel):
    clients: list[ClientPresenceEntry]

_LOCK = threading.Lock()
_SEEN: dict[str, dict] = {}

# The app itself doesn't send the header on every store; count the UDS/
# loopback app traffic under this name when the header is absent but the
# transport marker says it is the app's own socket.
APP_CLIENT_NAME = "fichero-app"


def record(client_name: str | None, *, transport: str | None) -> None:
    name = (client_name or "").strip()
    if not name and transport == "uds":
        name = APP_CLIENT_NAME
    if not name:
        return
    now = utc_now().isoformat()
    with _LOCK:
        entry = _SEEN.setdefault(name, {"first_seen": now, "requests": 0})
        entry["last_seen"] = now
        entry["requests"] += 1
        entry["transport"] = transport or "tcp"


def snapshot() -> list[dict]:
    with _LOCK:
        return [
            {"client": name, **info}
            for name, info in sorted(_SEEN.items())
        ]
