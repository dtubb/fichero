"""The route inventory the security guards walk sees the whole served surface, by full path (#5674 follow-up).

WHY (2026-10-11): FastAPI 0.141 keeps included routers whole, so ``app.routes`` held two ``APIRoute`` entries and the
page-deny, id-parameter and revocation guards walked nothing. The page-deny guard failed only because it counts; the
others passed blind. The inventory is checked against the contract's own paths, so it cannot shrink unseen again.
"""
from __future__ import annotations

import re

from fastapi.routing import APIRoute

from fichero_server.api.main import app
from tests.route_inventory import api_routes


def test_the_inventory_holds_every_served_route_by_its_full_path():
    # The contract writes a `{name:path}` parameter as `{name}`.
    served = {(m, re.sub(r":path}", "}", r.path)) for r in api_routes(app) if isinstance(r, APIRoute)
              for m in r.methods}
    documented = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops}
    assert len(documented) > 300, "the documented surface itself is far too small to check against"
    missing = documented - served
    assert not missing, sorted(missing)[:10]
    assert ("GET", "/api/tasks") in served, "an included router's root route keeps its prefix"
