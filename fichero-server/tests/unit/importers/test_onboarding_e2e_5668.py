"""What the end-to-end onboarding run on real pages found wrong in the engine (#5668, the week plan's top goal:
"onboarding does everything automatically: read, then organise"), each pinned where it was found.

The run (2026-10-11): a scratch engine driven only through the fichero CLI; a project; the 92 pages of
CACIQUES_INDIOS,17,D.5 added with Copy; Set Up's answers and stages; Start; the result read back.
"""

from __future__ import annotations

from PIL import Image


def test_a_copy_import_of_a_folder_warns_of_no_page_in_icloud(client, tmp_path):
    """`source.onboard.icloud-pages-warned`: "a folder is never 'a page in iCloud' … pages copied into the
    project are never counted." The run's Copy import of a local folder said "1 page is in iCloud and not on this
    Mac", naming the folder: a directory reports a size with no blocks of its own."""
    box = tmp_path / "CACIQUES_INDIOS,17,D.5"
    box.mkdir()
    for i in range(3):
        Image.new("RGB", (40, 60), (230, 225, 210)).save(box / f"{i + 1}_Hoja_{530 + i}_Recto.JPG")

    started = client.post("/api/ingest/folder", json={"path": str(box), "mode": "copy"})
    assert started.status_code == 200, started.text
    status = client.get(f"/api/ingest/status/{started.json()['task_id']}").json()

    assert status["status"] == "completed", status
    assert status["in_icloud"] is None, status["in_icloud"]
