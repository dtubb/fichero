# ruff: noqa: F811
"""sharing.owner-only-asserted-in-the-action (#6325, review 6 item 4): a route the owner alone may call runs an action, and
`POST /api/actions/invoke` (and MCP and chat) reach the same action with library write alone. The gate has to hold at the action,
so every action an owner-only route invokes is declared `owner_only`."""
import inspect
import re

from fastapi.routing import APIRoute

from fichero_server.actions.registry import registry
from tests.route_inventory import served_routes
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

_OWNER_DEPS = {"_require_owner_or_bootstrap", "_require_owner_for_writes", "_owner_only"}
_OWNER_CODE = re.compile(r"\b(owner_check|require_owner|require_app_owner|_require_\w*owner\w*|_checked_root)\(")
_INVOKES = re.compile(r"registry\.invoke\W+\w+,\s*\"([\w.]+)\"")
#: What an action and its route have in common when they share the work: a `*_impl` function.
_SHARED = re.compile(r"\b(\w+_impl)\(")


def _names(dep, out):
    out.add(getattr(dep.call, "__name__", ""))
    for sub in dep.dependencies:
        _names(sub, out)
    return out


def _owner_routes_and_their_actions(app):
    for route in served_routes(app):
        if not isinstance(route, APIRoute):
            continue
        writes = set(route.methods) - {"GET", "HEAD", "OPTIONS"}
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        gated = bool(_names(route.dependant, set()) & _OWNER_DEPS and writes) or bool(_OWNER_CODE.search(source))
        if gated:
            for name in _INVOKES.findall(source):
                yield f"{sorted(route.methods)[0]} {route.path}", name
            shared = set(_SHARED.findall(source))
            for name, reg in registry._actions.items():
                try:
                    theirs = set(_SHARED.findall(inspect.getsource(reg.execute)))
                except (OSError, TypeError):
                    continue
                if shared & theirs:
                    yield f"{sorted(route.methods)[0]} {route.path}", name


#: An action that only undoes an owner-only one (nothing invokes it by name).
INVERSES = {"document.unrelink_originals": "POST /api/documents/relink-originals"}


def test_every_action_an_owner_only_route_invokes_is_owner_only(harness):
    twins = {*_owner_routes_and_their_actions(harness.app), *((route, name) for name, route in INVERSES.items())}
    assert any(n == "document.relink_originals" for _, n in twins), "the guard no longer sees the relink route"
    open_twins = sorted((route, name) for route, name in twins if not registry.get(name).owner_only)
    assert not open_twins, f"owner-only routes whose action twin any editor can invoke: {open_twins}"
