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


#: The served surface is about 940 routes; a walk that sees fewer than this saw a router it did not unwrap.
ROUTE_FLOOR = 500


def served_routes(app: Any, floor: int = ROUTE_FLOOR) -> list[Any]:
    """`api_routes(app)`, failing when it holds fewer than `floor` routes, so a guard that walks nothing (FastAPI 0.141
    keeps included routers whole) fails instead of passing blind."""
    routes = api_routes(app)
    assert len(routes) >= floor, f"the walk saw {len(routes)} routes, fewer than {floor}: routers were not unwrapped"
    return routes


def router_routes(router: Any, floor: int) -> list[Any]:
    """One module's `router.routes`, failing when it holds fewer than `floor` routes or any that is not a plain
    `APIRoute` (an included sub-router FastAPI 0.141 keeps whole, which a walk would skip)."""
    routes = list(router.routes)
    assert len(routes) >= floor, f"the walk saw {len(routes)} routes, fewer than {floor}"
    nested = [r for r in routes if not isinstance(r, APIRoute)]
    assert not nested, f"routes a walk would skip (an included router kept whole): {nested[:3]}"
    return routes
