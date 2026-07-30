"""Guard: the mind-palace surface stays removed and canvas replaced it.

Route collection deliberately goes through ``app.openapi()`` rather than
``app.routes``. FastAPI 0.141 stopped flattening ``include_router`` calls into
``APIRoute`` entries on the app — included routers now appear as a single
private ``_IncludedRouter`` object whose children live behind private
attributes. Walking ``app.routes`` for ``APIRoute`` instances used to see 356
routes and now sees 2, which would have made the "mind-palace is gone" half of
this guard pass for entirely the wrong reason (#4337).

The OpenAPI document is the public, version-stable view of the same surface —
and it is the artifact the Swift client is generated from, so it is the more
honest thing to assert against anyway. The path set is sanity-checked for size
first, precisely so an empty collection can never make the absence assertions
vacuously true.
"""

from fichero_server.api.main import app

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
    "/api/canvas/folders/{folder_id}/canvas-layout",
    "/api/canvas/folders/{folder_id}/arrange",
    "/api/canvas/folders/{folder_id}/canvas-items",
    "/api/canvas/folders/{folder_id}/canvas-items/{item_id}",
}


def _app_paths() -> set[str]:
    return set(app.openapi()["paths"])


def test_route_collection_sees_the_whole_surface() -> None:
    """An empty/partial path set would make the absence checks meaningless."""
    paths = _app_paths()
    assert len(paths) > 100, (
        f"only collected {len(paths)} paths from the OpenAPI document — route "
        "collection is broken, so any 'route is absent' assertion below would "
        "pass vacuously"
    )


def test_absence_detection_distinguishes_present_from_absent() -> None:
    """Proof the guard can fail: a real path is seen, a made-up one is not.

    Without this, a collection bug that returned some *other* non-empty set
    would still satisfy the size check and silently stop guarding anything.
    """
    paths = _app_paths()
    assert "/api/health" in paths, "a known-present route was not collected"
    assert "/api/mind-palace/rooms" not in paths
    assert "/api/definitely-not-a-real-route" not in paths


def test_mind_palace_surface_is_gone_and_canvas_routes_remain() -> None:
    paths = _app_paths()
    assert len(paths) > 100, "route collection broken; see the guard test above"
    mind_palace_shaped = {
        *_REMOVED_PATHS,
        *{p.replace("/api/canvas", "/api/mind-palace") for p in _CANVAS_PATHS},
    }
    assert not (mind_palace_shaped & paths)
    assert _CANVAS_PATHS <= paths
