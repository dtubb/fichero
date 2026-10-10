"""A recording in a project of pages is not sent to the steps that read page images (2026-10-10, overnight check).

In the Dev Embedded app a project held two photographs and a speech recording. Start sent the recording to the
image steps; the reader said "cannot identify image file ... speech.m4a" and the whole step failed for the one
file it could never read. The steps that take a page image (or what is found on one: lines, regions, signs, line
readings) leave recordings out and say how many; steps that take text still take a recording once it has some.
"""

from __future__ import annotations

from fichero_server.models import DocType, Document, FileType
from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _start,
    engine,
    pages,
)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def test_a_recording_is_left_out_of_the_image_steps_and_said(client, db, pages, tmp_path, engine):
    speech = tmp_path / "speech.m4a"
    speech.write_bytes(b"\x00\x00\x00\x20ftypM4A ")
    db.save(Document(name="speech.m4a", doc_type=DocType.file, file_type=FileType.audio, path=str(speech)))
    r = client.put("/api/recipes/project", json={"answers": {"purpose": "transcribe"},
                                                 "recipe": _recipe(tmp_path, LINES, READ)})
    assert r.status_code == 200, r.text

    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert sorted(engine.read) == ["p0.png", "p1.png"]
    assert run["steps"][0]["recordings_left_out"] == 1, run["steps"][0]
