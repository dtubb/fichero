"""These tests send pages on a request's own yes; the app's places (`recipes.places`, #5831) allow every place here,
as a person who set them up would. A test of the cap sets them itself."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def every_place_allowed(monkeypatch):
    from fichero_server.recipes import places

    monkeypatch.setattr(places, "get_places", lambda: list(places.PLACES))
