"""Schema-hidden library header dependencies.

The Swift client injects ``X-Fichero-Library-Path`` as a transport header.
Routes should not declare it as an OpenAPI operation parameter.
"""

from urllib.parse import unquote

from fastapi import HTTPException, Request

from fichero.db.library_paths import nfc_path

LIBRARY_PATH_HEADER = "X-Fichero-Library-Path"


def optional_library_path(request: Request) -> str | None:
    """Read the library path transport header without exposing it in OpenAPI."""
    library_path = request.headers.get(LIBRARY_PATH_HEADER)
    return nfc_path(unquote(library_path)) if library_path is not None else None


def require_library_path(request: Request) -> str:
    """Read the required library path transport header without OpenAPI exposure."""
    library_path = optional_library_path(request)
    if not library_path:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Fichero-Library-Path header. Please open a library document first.",
        )
    return library_path
