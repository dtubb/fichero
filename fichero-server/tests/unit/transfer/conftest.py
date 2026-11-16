"""These tests send pages on a request's own yes; the app's places (`recipes.places`, #5831) allow every place here,
as a person who set them up would. A test of the cap sets them itself."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def every_place_allowed(monkeypatch):
    from fichero_server.recipes import places

    monkeypatch.setattr(places, "get_places", lambda: list(places.PLACES))


@pytest.fixture(autouse=True)
def roomy_disk(monkeypatch):
    """The room for an incoming copy is the fake's, never the disk the test runs on: a full runner disk (the M4, 762 MB
    free, under FREE_FLOOR_BYTES) answered 413 to every copy (#6589 item 14). A test of the floor patches it again."""
    from fichero_server.transfer import remote

    monkeypatch.setattr(remote.shutil, "disk_usage", lambda path: type("U", (), {"free": 10 ** 12})())
