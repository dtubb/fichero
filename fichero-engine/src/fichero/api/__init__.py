"""
Fichero REST API

FastAPI backend exposing the Fichero data layer.

Usage:
    # CLI
    fichero serve
    fichero serve --port 8080

    # Python
    from fichero.api import app
    from fichero.bind_host import resolve_bind_host
    import uvicorn
    uvicorn.run(app, host=resolve_bind_host(), port=8765)
"""

from fichero.api.main import app

__all__ = ["app"]
