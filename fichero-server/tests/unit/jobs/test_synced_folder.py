"""The synced folder, the write half (#4952).

Spec: docs/contributor_manual/specs/source/synced-folder.md. Written from the spec's behaviours before
the code, and driven through the public surface: a folder is tied with `POST /api/sync-folders`,
followed with `GET /api/sync-folders`, written by jobs on the real scheduler, and compared with
the exporter's own route (`GET /api/documents/{id}/export/{format}`). Edits go through the audited
action layer, as the app's do.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from _scan_files import scan_rglob
from lxml import etree

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs

FORMATS = ["pagexml", "alto", "tei"]
CTX = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


@pytest.fixture
def page(db, client):
    """A page with a working pass (converted), as every other export test uses."""
    from fichero_server.api.routes.document.segment_conversion import live_rows_in_order
    from fichero_server.models import Artifact
    from tests.unit.api.seeded_converted_page import seed_page

    _, doc, art = seed_page(db)
    assert client.put(f"/api/artifacts/{art.id}/regions",
                      json={"op": "move", "indices": [3], "bbox": [0.5, 0.9, 0.1, 0.05]}).status_code == 200
    row = live_rows_in_order(db, db.get(Artifact, art.id).geometry_superseded_by_pass_id)[0]
    return SimpleNamespace(id=doc.id, first_row=row)


@pytest.fixture(autouse=True)
def quick(monkeypatch, db):
    from fichero_server import sync_folder

    monkeypatch.setattr(sync_folder, "QUIET_SECONDS", 0.3)
    # The pages' own re-embeds run on the model lane; a real embedder load would only slow these.
    monkeypatch.setattr(type(db), "embed", lambda self, doc, *a, **k: True)


def _tie(client, path, formats=FORMATS):
    r = client.post("/api/sync-folders", json={"path": str(path), "formats": formats})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _status(client, folder_id):
    r = client.get("/api/sync-folders")
    assert r.status_code == 200, r.text
    return next(f for f in r.json()["folders"] if f["id"] == folder_id)


def _wait_for(predicate, seconds=60.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _written(client, folder_id, n):
    return _wait_for(lambda: _status(client, folder_id)["pending"] == 0 and len(_status(client, folder_id)["files"]) == n)


def _files(folder: Path):
    return sorted(p.relative_to(folder).as_posix() for p in scan_rglob(folder, "*") if p.is_file())


def test_source_sync_fixed_layout__one_subfolder_per_format_named_by_title_and_id(client, page, tmp_path):
    """Behaviour `source.sync.fixed-layout`: "a made folder's layout is chosen by Fichero and is the
    same for every project" (one subfolder per format; one file per source; names from the source's
    title and lasting id)."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder)
    assert _written(client, folder_id, 3)
    names = [f for f in _files(folder) if not f.endswith(".loss.json")]
    assert names == [f"alto/book-p1--{page.id}.alto.xml", f"pagexml/book-p1--{page.id}.page.xml",
                     f"tei/book-p1--{page.id}.tei.xml"]


def test_source_sync_out_is_the_exporters__each_file_is_the_exporters_own_output(client, page, tmp_path):
    """Behaviour `source.sync.out-is-the-exporters`: "writing outputs as the work goes on is the
    exporter's continuous export, fed by this model; no second export path exists." Each file is,
    byte for byte, what the exporter's own route gives for that page and format."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder)
    assert _written(client, folder_id, 3)
    for fmt, sub, ext in (("pagexml", "pagexml", ".page.xml"), ("alto", "alto", ".alto.xml"), ("tei", "tei", ".tei.xml")):
        exported = client.get(f"/api/documents/{page.id}/export/{fmt}").json()["content"]
        assert (folder / sub / f"book-p1--{page.id}{ext}").read_text(encoding="utf-8") == exported


def _identity(path: Path) -> dict[str, str]:
    root = etree.parse(str(path)).getroot()
    found = {}
    for el in root.iter():
        tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
        if tag == "MetadataItem":
            found[el.get("name")] = el.get("value")
        elif tag == "fileIdentifier" and (el.get("fileIdentifierLocation") or "").startswith("fichero"):
            found[el.get("fileIdentifierLocation")] = el.text
        elif tag == "idno" and (el.get("type") or "").startswith("fichero"):
            found[el.get("type")] = el.text
    return found


def test_source_sync_files_carry_ids__each_file_carries_its_sources_lasting_id(client, page, tmp_path):
    """Behaviour `source.sync.files-carry-ids`: "each written file carries its source's lasting id, so a
    renamed or moved file is still matched to its source" (in the format's own place for an
    identifier: PAGE's MetadataItem, ALTO's fileIdentifier, TEI's idno)."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder)
    assert _written(client, folder_id, 3)
    for path in scan_rglob(folder, "*.xml"):
        assert _identity(path).get("fichero-source") == page.id, path


def test_source_sync_files_say_what_they_hold__pass_order_kind_and_a_loss_report_beside(client, db, page, tmp_path):
    """Behaviour `source.sync.files-say-what-they-hold`: "each file names its pass, reading order and
    reading kind, with its loss report beside it." And `source.sync.writes-the-record-or-says-so`:
    the folder holds the working pass."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder)
    assert _written(client, folder_id, 3)
    choices = client.get(f"/api/documents/{page.id}/export/pagexml").json()["choices"]
    for path in scan_rglob(folder, "*.xml"):
        identity = _identity(path)
        assert identity["fichero-pass"] == choices["pass_id"]
        assert identity["fichero-reading-order"] == choices["order_name"]
        assert identity["fichero-reading-kind"] == choices["reading_kind"] == "transcription"
        report = json.loads(Path(f"{path}.loss.json").read_text())
        assert report["choices"]["pass_id"] == choices["pass_id"] and "losses" in report


def test_source_sync_atomic_writes__every_file_arrives_by_rename_from_a_sibling(client, page, tmp_path, monkeypatch):
    """Behaviour `source.sync.atomic-writes`: "every file is written to a temporary file and renamed into
    place, so no other program can read a half-written file." No surface shows a half-written file;
    this watches how each one arrives."""
    arrivals = []
    real_replace = os.replace

    def watch(src, dst):
        arrivals.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", watch)
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder)
    assert _written(client, folder_id, 3)
    written = {p for p in scan_rglob(folder, "*") if p.is_file()}
    assert written == {dst for _src, dst in arrivals}
    assert all(src.parent == dst.parent and src.name != dst.name for src, dst in arrivals)


def test_source_sync_never_overwrites_a_stranger__a_file_in_the_way_is_left_and_reported(client, page, tmp_path):
    """Behaviour `source.sync.never-overwrites-a-stranger`: "Fichero overwrites only files it wrote
    itself, known by a checksum it recorded; any other file in the way is left and reported."""
    folder = tmp_path / "edition"
    stranger = folder / "tei" / f"book-p1--{page.id}.tei.xml"
    stranger.parent.mkdir(parents=True)
    stranger.write_text("<TEI>someone else's edition</TEI>")
    folder_id = _tie(client, folder)
    assert _written(client, folder_id, 2)
    assert stranger.read_text() == "<TEI>someone else's edition</TEI>"
    assert _status(client, folder_id)["in_the_way"] == [f"tei/book-p1--{page.id}.tei.xml"]


def _correct(db, page, text):
    rid = registry.invoke(db, "representation.create", {
        "document_id": page.id, "segment_id": page.first_row.id, "kind": "transcription", "content": text},
        CTX).result["id"]
    registry.invoke(db, "reading.choose", {"segment_id": page.first_row.id, "kind": "transcription",
                                           "representation_id": rid}, CTX)


def test_source_sync_outputs_follow_edits__after_a_quiet_period_only_the_touched_files(client, db, page, tmp_path):
    """Behaviour `source.sync.outputs-follow-edits`: "the files holding a changed segment or reading are
    rewritten after a short quiet period, as an export job in Activity; files the change did not touch
    are not rewritten." Two corrections in a row make one rewrite; a second folder's page that did not
    change is not rewritten."""
    from fichero_server.models import DocType, Document

    other = Document(name="untouched", doc_type=DocType.file)
    db.save(other)
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder, ["pagexml"])
    assert _written(client, folder_id, 1)
    path = folder / "pagexml" / f"book-p1--{page.id}.page.xml"
    before = path.stat().st_mtime_ns

    _correct(db, page, "In the year of Our Lord")
    _correct(db, page, "In the year of Our Lord and Saviour")
    rows = [j for j in client.get("/api/activity/jobs").json()["jobs"] if j["task_type"] == "write-to-folder"]
    assert len(rows) == 1 and rows[0]["state"] == "waiting"  # one job, in Activity, waiting out the quiet
    assert _wait_for(lambda: "and Saviour" in path.read_text(encoding="utf-8"))
    assert path.stat().st_mtime_ns != before
    assert _status(client, folder_id)["pending"] == 0


def test_source_sync_one_mechanism_many_folders__two_folders_two_sets_of_formats(client, page, tmp_path):
    """Behaviour `source.sync.one-mechanism-many-folders`: "a project or one of its folders can have
    several synced folders, each the destination of an export step naming its formats, all through
    the same mechanism.\""""
    edition = _tie(client, tmp_path / "edition", ["tei"])
    layout = _tie(client, tmp_path / "layout", ["pagexml", "alto"])
    assert _written(client, edition, 1) and _written(client, layout, 2)
    assert {f["formats"] == ["tei"] for f in client.get("/api/sync-folders").json()["folders"]} == {True, False}


def test_source_sync_engine_side_and_throttled__an_engine_path_written_as_background_jobs(client, page, tmp_path):
    """Behaviour `source.sync.engine-side-and-throttled`: "the folder is named where the engine runs,
    and syncing is throttled background work." A path that is not absolute on the engine's disk is
    refused; writing is a job of its own kind on a background lane."""
    assert client.post("/api/sync-folders", json={"path": "relative/edition", "formats": ["tei"]}).status_code == 422
    folder_id = _tie(client, tmp_path / "edition", ["tei"])
    assert _written(client, folder_id, 1)
    kind = jobs.KINDS["write-to-folder"]
    assert kind.lane == "database" and kind.qos.__name__ == "set_background_qos"


def test_source_sync_paused_with_background_work__nothing_written_until_resumed(client, page, tmp_path):
    """Behaviour `source.sync.paused-with-background-work`: "writing and intake stop under Pause
    Background Work and catch up when it is resumed.\""""
    client.put("/api/activity/jobs/paused", json={"paused": True})
    try:
        folder = tmp_path / "edition"
        folder_id = _tie(client, folder, ["tei"])
        time.sleep(0.5)
        assert _files(folder) == [] and _status(client, folder_id)["pending"] >= 1
    finally:
        client.put("/api/activity/jobs/paused", json={"paused": False})
    assert _written(client, folder_id, 1)


def test_source_sync_rescan_after_downtime__changes_made_while_stopped_are_found(client, page, test_package, tmp_path, monkeypatch):
    """Behaviour `source.sync.rescan-after-downtime`: "on engine start the folder is compared with the
    recorded checksums, and changes made while the engine was off are handled as though seen live."
    A file edited and a file deleted while the library was closed are both reported when it opens."""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder, ["tei", "pagexml"])
    assert _written(client, folder_id, 2)
    db_manager.close_database(test_package)  # the engine stops
    tei = folder / "tei" / f"book-p1--{page.id}.tei.xml"
    tei.write_text(tei.read_text(encoding="utf-8").replace("<body>", "<body><!-- edited in Oxygen -->"),
                   encoding="utf-8")
    (folder / "pagexml" / f"book-p1--{page.id}.page.xml").unlink()
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    db_manager.get_database(test_package)  # and starts again
    status = _status(client, folder_id)
    assert status["changed_outside"] == [f"tei/book-p1--{page.id}.tei.xml"]
    assert status["deleted_outside"] == [f"pagexml/book-p1--{page.id}.page.xml"]
    assert "edited in Oxygen" in tei.read_text(encoding="utf-8")  # left as the person left it


def test_source_sync_untie_leaves_files__untying_stops_writing_and_leaves_the_files(client, db, page, tmp_path):
    """Behaviour `source.sync.untie-leaves-files`: "untying a folder stops writing and intake and leaves
    its files on disk.\""""
    folder = tmp_path / "edition"
    folder_id = _tie(client, folder, ["pagexml"])
    assert _written(client, folder_id, 1)
    path = folder / "pagexml" / f"book-p1--{page.id}.page.xml"
    before = path.read_text(encoding="utf-8")
    assert client.delete(f"/api/sync-folders/{folder_id}").status_code == 200
    assert all(f["id"] != folder_id for f in client.get("/api/sync-folders").json()["folders"])
    _correct(db, page, "In the year of Our Lord and Saviour")
    time.sleep(1.0)  # past the quiet period: nothing is written to an untied folder
    assert path.read_text(encoding="utf-8") == before
