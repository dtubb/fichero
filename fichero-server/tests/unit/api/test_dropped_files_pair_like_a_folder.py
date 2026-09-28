"""Loose files dropped together pair their layout with their image, as a folder drop does (#5220).

The maintainer dropped the Ajami images WITH their ALTO files selected (not the folder), and
every .xml landed as a raw text document beside its image: the app sent each file to
/api/ingest/file one at a time, so the engine never saw an image and its layout together.
/api/ingest/files takes the set and runs the same pairing: the ALTO becomes a PASS on its image.
If this regresses, a drop of files silently doubles every page into image + stray XML.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from fichero_server.models import Document

ALTO = Path(__file__).resolve().parents[1] / "formats" / "fixtures" / "corpus" / "ajami_fulfulde_elit-wan-00130-001r.alto.xml"


def _drop(tmp_path: Path) -> tuple[Path, Path]:
    """The real Ajami ALTO beside its image -- which it names as `.JPG`, while the file is `.jpg`."""
    image = tmp_path / "ELIT_WAN_00130_001r.jpg"
    Image.new("RGB", (2836, 3862), "white").save(image, quality=40)
    layout = tmp_path / "ELIT_WAN_00130_001r.xml"
    shutil.copy(ALTO, layout)
    return image, layout


def test_an_image_and_its_alto_dropped_together_become_one_page_with_a_pass(client, db, tmp_path):
    image, layout = _drop(tmp_path)
    response = client.post("/api/ingest/files", json={"paths": [str(layout), str(image)]})
    assert response.status_code == 200, response.text
    body = response.json()
    names = [doc["name"] for doc in body["documents"]]
    assert names == [image.name], f"only the image is a document; the ALTO is its pass, got {names}"
    assert body["imported_as_passes"] == [layout.name], body
    assert body["not_imported"] == {} and body["unpaired"] == {}, body
    stored = [d.name for d in db.all(Document) if (d.name or "").endswith(".xml")]
    assert stored == [], f"no .xml document may exist after a paired drop: {stored}"


def test_a_layout_with_no_image_in_the_set_is_named_not_silently_textified(client, tmp_path):
    _, layout = _drop(tmp_path)
    response = client.post("/api/ingest/files", json={"paths": [str(layout)]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert layout.name in body["unpaired"], body


def test_an_empty_drop_is_refused(client):
    assert client.post("/api/ingest/files", json={"paths": []}).status_code == 400
