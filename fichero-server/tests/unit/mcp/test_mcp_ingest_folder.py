"""An agent can bring a folder in over MCP, linked in place, through the real engine route (#5400).

`fichero_import` takes one file and uploads a copy; over MCP there was no way to bring a folder in
as a folder, or to leave files where they are. In the Sergio notebooks project that meant
importing 221 photos with the CLI instead. These tests drive the MCP tools through the real
`/api/ingest/folder` route and its background import (no mocked importer), because a test that
only checks the request would pass while the library stayed empty.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_cli import FicheroClient
from fichero_mcp import server as mcp_server
from fichero_server.models import Document


@pytest.fixture
def mcp_on_the_real_app(client, test_package, monkeypatch):
    """The MCP server's client, its requests answered by the in-process app (as test_places_over_time)."""
    def forward(request: httpx.Request) -> httpx.Response:
        answered = client.request(request.method, request.url.path, params=dict(request.url.params),
                                  content=request.content or None,
                                  headers={"content-type": request.headers.get("content-type", "application/json")})
        return httpx.Response(answered.status_code, content=answered.content,
                              headers={"content-type": answered.headers.get("content-type", "application/json")})

    def build() -> FicheroClient:
        return FicheroClient(base_url="http://test", library_path=str(test_package), token="t",
                             transport=httpx.MockTransport(forward))

    monkeypatch.setattr(mcp_server, "_client", build)
    monkeypatch.setattr(mcp_server, "_mutating_client", build)
    return build


def _notebook(root: Path) -> Path:
    folder = root / "SM_NPQ_C09"
    folder.mkdir()
    for i in (1, 2):
        Image.new("RGB", (60, 40), (200, 200, 190)).save(folder / f"SM_NPQ_C09_{i:03d}.jpg")
    return folder


def test_a_folder_comes_in_as_a_folder_with_its_files_linked_in_place(mcp_on_the_real_app, db, tmp_path, test_package):
    """WHY: a project's photos (816 MB for three notebooks) must not be copied into the library to be
    read; linked, they stay in their archive folder and the library records where. The folder must
    arrive as a folder holding its photos, and the agent must be able to see the import finish."""
    folder = _notebook(tmp_path)
    task = mcp_server.fichero_ingest_folder(str(folder))
    status = mcp_server.fichero_ingest_status(task.task_id)

    assert status.status == "completed", status
    assert status.failed == 0 and len(status.document_ids) >= 2
    (parent,) = [d for d in db.query(Document) if d.name == "SM_NPQ_C09"]
    photos = sorted(db.query(Document, parent_id=parent.id), key=lambda d: d.name)
    assert [p.name for p in photos] == ["SM_NPQ_C09_001.jpg", "SM_NPQ_C09_002.jpg"]
    assert all(Path(p.path).parent == folder for p in photos), "linked where they are, not copied"
    assert not list(Path(test_package).rglob("SM_NPQ_C09_001.jpg")), "no copy inside the library"


def test_an_unknown_mode_is_refused_before_anything_is_imported(mcp_on_the_real_app, db, tmp_path):
    """WHY: a typo in the mode must not fall back to some default way of importing (rule 0: never
    substitute silently); nothing is written."""
    folder = _notebook(tmp_path)
    with pytest.raises(ValueError):
        mcp_server.fichero_ingest_folder(str(folder), mode="symlink")
    assert not [d for d in db.query(Document) if d.name == "SM_NPQ_C09"]
