"""Other Fichero engines this one has paired with (#5657, the slice of `compute.target.add-fichero-mac` a copy
between machines needs).

Pairing is the existing device pairing, run by this engine as the device: the person reads a code off the
other Mac's Fichero, this engine exchanges it at that Mac's `POST /api/pair` for a device token, and from then
on every call there carries that token. The far engine stamps what lands with its paired person
(`compute.land.server-sets-the-maker`). Only a tailnet address is accepted (`https://<name>.ts.net`, through
`tailscale serve`): never a hand-written URL, never `funnel`.

Each machine is kept whole (its name, address and token) as one Keychain item, so the token is never in a
database or a file. A machine with no Keychain (a Linux server) cannot pair out; it can still be paired TO.
"""

from __future__ import annotations

import json
import socket
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from fichero_server.core.timeutil import utc_now

_PREFIX = "fichero-machine:"


@dataclass
class Machine:
    id: str
    name: str
    url: str
    token: str
    paired_at: str

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "url": self.url, "paired_at": self.paired_at}


# --- the store: a seam, so tests never touch this Mac's Keychain ---------------------------------------


def _put(account: str, secret: str) -> bool:
    from fichero_server.security.keychain import set_api_key

    return set_api_key(account, secret)


def _get(account: str) -> str | None:
    from fichero_server.security.keychain import get_api_key

    return get_api_key(account)


def _delete(account: str) -> bool:
    from fichero_server.security.keychain import delete_api_key

    return delete_api_key(account)


def _accounts() -> list[str]:
    from fichero_server.security.keychain import list_providers

    return [a for a in list_providers() if a.startswith(_PREFIX)]


def this_machine() -> str:
    return socket.gethostname().split(".")[0] or "this Mac"


def machines() -> list[Machine]:
    out = []
    for account in _accounts():
        raw = _get(account)
        if raw:
            out.append(Machine(**json.loads(raw)))
    return sorted(out, key=lambda m: m.name)


def machine(machine_id: str) -> Machine:
    raw = _get(_PREFIX + machine_id)
    if not raw:
        raise LookupError(f"No paired machine {machine_id}: pair it first (its Fichero shows a pairing code).")
    return Machine(**json.loads(raw))


def forget(machine_id: str) -> None:
    """Drop the saved token for a paired machine. The far Mac still lists the device until it revokes it there."""
    machine(machine_id)  # LookupError if not paired
    if not _delete(_PREFIX + machine_id):
        raise RuntimeError("The Keychain would not remove the saved pairing.")


def address_url(address: str) -> str:
    """`name.tailnet.ts.net` or `https://name.tailnet.ts.net` -> the https URL; anything else refused."""
    from fichero_server.security.remote_access_tls import validate_tailnet_url

    address = address.strip()
    return validate_tailnet_url(address if "://" in address else f"https://{address}")


def client(url: str, token: str | None = None):
    """The HTTP client to another engine. A seam: a test returns the far engine's TestClient."""
    from fichero_server.core.egress import check_egress  # noqa: PLC0415
    check_egress("another-mac", what="the copy", to="your other Mac")
    import httpx

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=url, headers=headers, timeout=httpx.Timeout(60.0, connect=10.0))


def pair(address: str, code: str) -> Machine:
    """Exchange a pairing code shown on the other Mac for a device token, and keep the machine."""
    url = address_url(address)
    far = client(url)
    try:
        answer = far.post("/api/pair", json={"code": code, "device_name": f"{this_machine()} (Fichero)"})
    finally:
        far.close()
    if answer.status_code != 200:
        detail = answer.json().get("detail") if answer.headers.get("content-type", "").startswith("application/json") else None
        raise PermissionError(f"{url} refused the pairing code: {detail or answer.status_code}")
    token = answer.json()["device_token"]
    found = Machine(id=uuid.uuid4().hex, name=url.removeprefix("https://").split(".")[0], url=url, token=token,
                    paired_at=utc_now().isoformat())
    if not _put(_PREFIX + found.id, json.dumps(asdict(found))):
        raise RuntimeError("This machine has no Keychain to keep the pairing in, so it cannot copy to another one.")
    return found
