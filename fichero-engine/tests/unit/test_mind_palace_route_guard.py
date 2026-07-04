from fastapi.routing import APIRoute

from fichero.api.main import app

_REMOVED_PATHS = {
    "/api/mind-palace/rooms",
    "/api/mind-palace/rooms/{room_id}",
    "/api/mind-palace/rooms/{room_id}/scene",
    "/api/mind-palace/rooms/{room_id}/viewport/{user_id}",
    "/api/mind-palace/rooms/{room_id}/focus",
    "/api/mind-palace/rooms/{room_id}/suggest-arrangement",
    "/api/mind-palace/rooms/{room_id}/capture",
    "/api/mind-palace/nodes",
    "/api/mind-palace/nodes/{node_id}",
    "/api/mind-palace/connections",
    "/api/mind-palace/connections/{connection_id}",
    "/api/mind-palace/stacks",
    "/api/mind-palace/stacks/{stack_id}",
    "/api/mind-palace/stacks/{stack_id}/nodes/{node_id}",
    "/api/mind-palace/notes",
    "/api/mind-palace/notes/{note_id}",
    "/api/mind-palace/export/tinderbox",
    "/api/mind-palace/import/tinderbox",
    "/api/mindpalace/render",
}

_CANVAS_PATHS = {
    "/api/canvas/folders/{scope_id}/layout",
    "/api/canvas/folders/{scope_id}/arrange",
    "/api/canvas/folders/{scope_id}/items",
    "/api/canvas/folders/{scope_id}/items/{item_id}",
}


def _app_paths() -> set[str]:
    return {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    }


def test_mind_palace_surface_is_gone_and_canvas_routes_remain() -> None:
    paths = _app_paths()
    assert not ({*_REMOVED_PATHS, *{p.replace("/api/canvas", "/api/mind-palace") for p in _CANVAS_PATHS}} & paths)
    assert _CANVAS_PATHS <= paths
