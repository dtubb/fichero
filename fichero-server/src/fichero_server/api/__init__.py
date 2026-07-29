"""
Fichero REST API

FastAPI backend exposing the Fichero data layer.

Usage:
    # CLI
    fichero serve
    fichero serve --port 8080

    # Python
    from fichero_server.api import app
    from fichero_server.security.bind_host import resolve_bind_host
    import uvicorn
    uvicorn.run(app, host=resolve_bind_host(), port=8765)
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from fichero_server.api.main import app as app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    """Resolve ``app`` on first access instead of at package import (#3950).

    This eager import was the root of the fichero_server.db <-> api.main cycle:

        fichero_server.db          (line 67: from fichero_server.db.manager import ...)
        -> fichero_server.db.manager (line 14: from fichero_server.api.change_stream import ...)
        -> fichero_server.api        (this __init__)
        -> fichero_server.api.main   (line 68: from fichero_server.db import Database)
        -> fichero_server.db         ... still half-initialised. ImportError.

    Anything importing a leaf of fichero_server.api (change_stream, auth, routes.*)
    ran this package __init__ first and so dragged in the whole FastAPI app.
    That made `import fichero_server.workflows.tools` impossible standalone, which in
    turn made registry._load_tool_implementations() fail and get swallowed —
    leaving the tool registry silently incomplete (#3951).

    PEP 562 module __getattr__ fires only when the attribute is absent from
    module globals, so `from fichero_server.api import app` still works unchanged;
    it just resolves when someone asks for the app rather than when someone
    asks for an unrelated sibling module.
    """
    if name == "app":
        from fichero_server.api.main import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
