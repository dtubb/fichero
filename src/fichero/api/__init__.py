"""
Fichero REST API

FastAPI backend exposing the Fichero data layer.

Usage:
    # CLI
    fichero serve
    fichero serve --port 8080

    # Python
    from fichero.api import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
"""

from fichero.api.main import app

__all__ = ["app"]
