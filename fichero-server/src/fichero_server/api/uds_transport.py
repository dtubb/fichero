"""ASGI wrapper that marks requests arriving over the Unix-domain socket.

Only the UDS server is wrapped with this. It stamps a positive transport
marker onto the ASGI ``scope`` so that ``_is_loopback_request`` can trust a UDS
connection as loopback-owner WITHOUT ever keying off ``request.client is None``
(a misconfigured proxy / stripping middleware / ASGI test transport can forge a
``None`` client on the TCP path, which must never be granted bootstrap-owner).

The shared TCP+TLS app is never wrapped, so a TCP request never carries the
marker and the existing non-loopback -> 401/403 behaviour is unchanged.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from fichero_server.api.main import app as _app

# Keep this literal in sync with ``_is_loopback_request`` in ``fichero_server.api.auth``.
UDS_TRANSPORT_SCOPE_KEY = "fichero.transport"
UDS_TRANSPORT_VALUE = "uds"

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class UDSTransportApp:
    """ASGI middleware stamping the UDS transport marker on http/websocket scopes."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") in ("http", "websocket"):
            scope[UDS_TRANSPORT_SCOPE_KEY] = UDS_TRANSPORT_VALUE
        await self._app(scope, receive, send)


# Module-level ASGI callable for the string-import launch path
# (`uvicorn fichero_server.api.uds_transport:app --uds <path>`).
app = UDSTransportApp(_app)

# The per-launch secret that authorises first-run arrives with the process (stdin pipe, or the Debug dev file).
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402

from fichero_server.security import launch_secret as _launch_secret  # noqa: E402

_launch_secret.load_at_startup(_os.environ, _sys.stdin)
