"""A folder import's task status tells the truth about what went in (#5140).

WHY: the app and the CLI learn what a folder drop did ONLY from
``GET /api/ingest/status/{id}``. The acceptance run (2026-09-27) dropped the
Reichsanzeiger pages: both 9632x6648 scans were refused as over the pixel cap,
their PAGE files became no pass, and the task still said ``completed`` -- and
the pairing report (which layout files became passes, which did not and why)
was written only to the engine log. If this regresses, a person is told a
folder imported when nothing did, and never learns which PAGE/ALTO file was
left out.

Real files through the real route: a Transkribus PAGE file paired with its
image, and eScriptorium's sample, which names an image that is not there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
from fichero_server.loaders import image_loader

FORMATS = Path(__file__).resolve().parents[1] / "formats" / "fixtures"


def _image(path: Path, size=(40, 60)) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)


@pytest.fixture
def export_folder(tmp_path) -> Path:
    folder = tmp_path / "export"
    _image(folder / "M_Otterskirchen_012_0002.jpg")
    (folder / "M_Otterskirchen_012_0002.xml").write_bytes(
        (FORMATS / "transkribus_regions_only_0002.page.xml").read_bytes()
    )
    (folder / "orphan.page.xml").write_bytes(
        (FORMATS / "escriptorium_export.page.xml").read_bytes()
    )
    return folder


def _drop(client, folder: Path) -> dict:
    started = client.post(
        "/api/ingest/folder",
        json={"path": str(folder), "mode": "copy", "recursive": True,
              "extract_text": False, "auto_embed": False},
    )
    assert started.status_code == 200, started.text
    # TestClient runs the background task before returning the response.
    status = client.get(f"/api/ingest/status/{started.json()['task_id']}")
    assert status.status_code == 200, status.text
    return status.json()


def test_status_carries_the_pairing_report(client, export_folder):
    """The paired file is named as a pass; the orphan is named with its reason."""
    status = _drop(client, export_folder)

    assert status["status"] == "completed", status
    assert status["imported_as_passes"] == ["M_Otterskirchen_012_0002.xml"]
    assert list(status["unpaired"]) == ["orphan.page.xml"]
    assert "default.png" in status["unpaired"]["orphan.page.xml"]


def test_a_folder_whose_every_image_is_refused_is_not_completed(
    client, export_folder, monkeypatch
):
    """Every scan over the pixel cap: the task fails and names each refusal."""
    # A 40x60 test image stands in for a 64 MP newspaper scan. The orphan
    # goes: it would still land as an ordinary file, and then something DID
    # go in (a partly refused folder stays `completed`, its refusals listed).
    monkeypatch.setattr(image_loader, "_MAX_IMAGE_PIXELS", 100)
    (export_folder / "orphan.page.xml").unlink()

    status = _drop(client, export_folder)

    assert status["status"] == "failed", status
    assert status["failed"] == 1
    assert "Image too large" in status["error"]
    assert "M_Otterskirchen_012_0002.jpg" in status["error"]
    # Its layout file became no pass, and the status says so by name.
    assert status["imported_as_passes"] == []
    assert "M_Otterskirchen_012_0002.xml" in status["not_imported"]
