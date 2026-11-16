"""These tests send pages on a request's own yes; the app's places (`recipes.places`, #5831) allow every place here,
as a person who set them up would. A test of the cap sets them itself."""
from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def every_place_allowed(monkeypatch, request):
    # a run rooted through a symlink (the M4 gate) mis-scopes a directory conftest's autouse fixture onto every test:
    # scope it by the test file's own path
    if HERE not in Path(str(request.path)).resolve().parents:
        return
    from fichero_server.recipes import places

    monkeypatch.setattr(places, "get_places", lambda: list(places.PLACES))
