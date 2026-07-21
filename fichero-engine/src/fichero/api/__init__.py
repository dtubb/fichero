"""
Fichero REST API

FastAPI backend exposing the Fichero data layer.

Usage:
    # CLI
    fichero serve
    fichero serve --port 8080

    # Python
    from fichero.api import app
    from fichero.security.bind_host import resolve_bind_host
    import uvicorn
    uvicorn.run(app, host=resolve_bind_host(), port=8765)
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from fichero.api.main import app as app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    """Resolve ``app`` on first access instead of at package import (#3950).

    This eager import was the root of the fichero.db <-> api.main cycle:

        fichero.db          (line 67: from fichero.db_manager import ...)
        -> fichero.db_manager (line 14: from fichero.api.change_stream import ...)
        -> fichero.api        (this __init__)
        -> fichero.api.main   (line 68: from fichero.db import Database)
        -> fichero.db         ... still half-initialised. ImportError.

    Anything importing a leaf of fichero.api (change_stream, auth, routes.*)
    ran this package __init__ first and so dragged in the whole FastAPI app.
    That made `import fichero.workflows.tools` impossible standalone, which in
    turn made registry._load_tool_implementations() fail and get swallowed —
    leaving the tool registry silently incomplete (#3951).

    PEP 562 module __getattr__ fires only when the attribute is absent from
    module globals, so `from fichero.api import app` still works unchanged;
    it just resolves when someone asks for the app rather than when someone
    asks for an unrelated sibling module.
    """
    if name == "app":
        from fichero.api.main import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
