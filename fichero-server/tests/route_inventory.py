"""Every route the engine serves, as guards read them (#5674 follow-up, 2026-10-11).

FastAPI 0.141 includes a router without copying its routes: ``app.routes`` holds one private ``_IncludedRouter`` per
included router, and a guard that walks it for ``APIRoute`` sees almost nothing. Its "every GET route on a denied
page refuses" then checked zero routes and failed only because it counts them; a guard without that count would have
passed blind. Here: each ``APIRoute`` the app serves, with its FULL path (the include prefix joined), read from the
router's own effective routes, so a guard walks the real surface. On a FastAPI that still copies routes, the app's
own ``APIRoute`` entries are returned as they are.
"""
from __future__ import annotations

import copy
from typing import Any

from fastapi.routing import APIRoute


def api_routes(app: Any) -> list[Any]:
    """Every route of ``app``: each ``APIRoute`` (a copy whose ``path`` is the full served path) and every other
    route (a ``Mount``, a plain ``Route``) as it is."""
    out: list[Any] = []
    for route in app.router.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is None:
            out.append(route)
            continue
        for context in contexts():
            original = context.original_route
            if isinstance(original, APIRoute):
                served = copy.copy(original)
                served.path = context.path
                served.param_convertors = original.param_convertors
                out.append(served)
            elif original is not None:
                out.append(original)
    return out
