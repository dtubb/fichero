"""Every /api/hpc route is owner-only: a cluster's host, user and key state are the owner's, not a member's."""
from __future__ import annotations

from fichero_server.api.routes.ai import hpc
from tests.route_inventory import router_routes


def test_every_hpc_route_depends_on_the_owner_check():
    open_routes = []
    for route in router_routes(hpc.router, 10):
        deps = {d.call for d in route.dependant.dependencies}
        if hpc._require_owner_or_bootstrap not in deps:
            open_routes.append(f"{sorted(route.methods)} {route.path}")
    assert not open_routes, f"not owner-only: {open_routes}"
