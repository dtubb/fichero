"""ASGI wrapper that withholds local-only routes from the TCP listener.

The sibling of ``fichero.api.uds_transport``. Read them together: they are the
two entry points into ONE FastAPI application, with two different postures.

    uds_transport  — stamps the loopback-owner marker, serves everything
    tcp_transport  — serves everything EXCEPT the local control surface

Why a wrapper and not a route guard: both listeners serve the SAME
``fichero.api.main:app`` object (``uds_transport`` is middleware, not a second
application), so a route added to that app is reachable on BOTH transports.
The sharing control surface must be reachable ONLY over the local socket —
otherwise a remote device could ask the engine to open a port for it. Blocking
at the TCP entry point makes that structural: the request never reaches the
handler, rather than reaching it and being refused.

The route itself stays a normal FastAPI route on the shared app, so it keeps
its OpenAPI schema and its generated Swift client. That is the trade this shape
buys over deleting the route from the app entirely (#4222/#4224).

The weakness of this approach is that the guarantee lives at the ENTRY POINT,
so it holds only while every TCP launcher uses this wrapper. A launcher that
reaches for the bare ``fichero.api.main:app`` silently loses it — no error, no
failing test, an open door. ``scripts/check_tcp_transport_wrapper.py`` is what
converts that from "everyone must remember" into a failing gate.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from fichero.api.main import app as _app

#: Path prefixes served on the local socket only. A remote caller gets 404 —
#: the same answer as a route that does not exist, which is what it is from
#: the TCP surface's point of view.
LOCAL_ONLY_PREFIXES: tuple[str, ...] = ("/api/sharing",)

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


def is_local_only_path(path: str) -> bool:
    """True when ``path`` belongs to the local-socket-only control surface."""
    return any(
        path == prefix or path.startswith(prefix + "/") for prefix in LOCAL_ONLY_PREFIXES
    )


class TCPTransportApp:
    """Serve the shared app, minus the local-only control surface."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") in ("http", "websocket") and is_local_only_path(
            scope.get("path", "")
        ):
            await self._reject(scope, send)
            return
        await self._app(scope, receive, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        if scope.get("type") == "websocket":
            await send({"type": "websocket.close", "code": 4404})
            return
        body = json.dumps({"detail": "Not Found"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


# Module-level ASGI callable for the string-import launch path
# (`uvicorn fichero.api.tcp_transport:app --host ... --port ...`).
app = TCPTransportApp(_app)
