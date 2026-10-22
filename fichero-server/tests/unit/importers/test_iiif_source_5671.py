"""A folder bound to a IIIF source, imported by reference as a job, refreshed, and read at a step's size (#5671).

WHY: an archive's collection runs to tens of thousands of canvases. Importing them must make small rows, fast, with
no image fetched; importing the same source again must make nothing twice (the folder follows its source); and a step
on this Mac must fetch only the image it reads, at the size it reads it, politely, into a bounded cache. A fake IIIF
server answers and counts every request, so the tests say exactly what crossed the network.
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from fichero_server.importers import iiif_source
from fichero_server.media.iiif_fetch import PoliteFetcher
from fichero_server.models import Document
from tests.unit.importers.test_iiif_by_reference import HOST, FakeIIIFServer, _manifest3


def _fetcher(server):
    return PoliteFetcher(get=server.get, sleep=lambda s: None)


def test_thirty_thousand_canvases_import_quickly_as_references_and_again_make_nothing(db, monkeypatch):
    """`iiif.scale.million-pages`, at 30,000 canvases, built here, never fetched from the network."""
    manifest = _manifest3("big", 30_000)
    server = FakeIIIFServer({manifest["id"]: manifest})
    said = []

    writes: list[int] = []
    real_save_many = db.save_many

    def counted(rows, *a, **k):
        writes.append(len(rows))
        return real_save_many(rows, *a, **k)

    monkeypatch.setattr(db, "save_many", counted)
    done = iiif_source.import_source(db, manifest["id"], fetcher=_fetcher(server), say=said.append)

    assert done["added"] == 30_000 and done["canvases"] == 30_000
    assert server.requests == [manifest["id"]]  # the manifest only: no image fetched
    # "quickly" is a count, not a clock (a loaded Mac takes any number of seconds): one insert per 1,000 rows, never one per row
    assert sum(writes) >= 30_000 and max(writes) <= iiif_source.BATCH and len(writes) <= 31, writes[:5]
    pages = db.query(Document, parent_id=done["folder_id"])
    assert len(pages) == 30_000 and all(not p.path for p in pages[:50])
    page = next(p for p in pages if p.metadata["iiif_id"] == f"{HOST}/big/canvas/12345")
    assert page.metadata["iiif_service"] == f"{HOST}/img/big/12345" and page.metadata["by_reference"] is True
    assert (page.metadata["width"], page.metadata["height"]) == (4000, 6000) and page.sequence == 12345
    assert said[-1] == "Importing from IIIF: 30,000 of 30,000 new canvases"
    folder = db.get(Document, done["folder_id"])
    assert folder.metadata["iiif_source"] == manifest["id"] and folder.metadata["iiif_canvases"] == 30_000

    again = iiif_source.import_source(db, manifest["id"], fetcher=_fetcher(server))
    assert again["added"] == 0 and again["already_here"] == 30_000 and again["folder_id"] == done["folder_id"]
    assert len(db.query(Document, parent_id=done["folder_id"])) == 30_000


def test_the_bulk_insert_of_new_rows_never_overwrites_one_already_there(db):
    """`save_many(new=True)` is a plain INSERT: an id already in the table fails the batch, all of it, unchanged."""
    kept = Document(name="kept")
    db.save(kept)
    with pytest.raises(Exception):
        db.save_many([Document(name="fresh"), kept.model_copy(update={"name": "overwritten"})], new=True)
    assert db.get(Document, kept.id).name == "kept"
    assert not [d for d in db.query(Document) if d.name == "fresh"]


def test_a_refresh_adds_what_the_source_added_and_counts_what_it_withdrew(db):
    url = f"{HOST}/vol/manifest"
    first = _manifest3("vol", 5)
    server = FakeIIIFServer({url: first})
    done = iiif_source.import_source(db, url, fetcher=_fetcher(server))
    assert done["added"] == 5

    later = _manifest3("vol", 7)
    later["items"] = later["items"][1:]  # canvas 1 withdrawn, 6 and 7 added
    server.documents[url] = later
    again = iiif_source.import_source(db, url, fetcher=_fetcher(server))

    assert (again["added"], again["already_here"], again["withdrawn"]) == (2, 4, 1)
    pages = db.query(Document, parent_id=done["folder_id"])
    assert len(pages) == 7  # the withdrawn canvas is kept: a person's work may hang on it
    assert iiif_source.bound_folder(db, url).id == done["folder_id"]


def test_presentation_2_imports_into_a_bound_folder_too(db):
    v2 = {"@id": f"{HOST}/v2/manifest", "@type": "sc:Manifest", "label": "Old volume", "sequences": [{"canvases": [{
        "@id": f"{HOST}/v2/canvas/{i}", "@type": "sc:Canvas", "label": str(i), "width": 3000, "height": 4000,
        "images": [{"resource": {"@id": f"{HOST}/v2/img/{i}/full/full/0/default.jpg", "service": {
            "@id": f"{HOST}/v2/img/{i}", "profile": "http://iiif.io/api/image/2/level1.json"}}}]} for i in (1, 2)]}]}
    server = FakeIIIFServer({v2["@id"]: v2})
    done = iiif_source.import_source(db, v2["@id"], fetcher=_fetcher(server))
    services = {p.metadata["iiif_service"] for p in db.query(Document, parent_id=done["folder_id"])}
    assert services == {f"{HOST}/v2/img/1", f"{HOST}/v2/img/2"}


def test_the_import_is_a_job_and_a_bound_folder_refreshes(client, db, monkeypatch, jobs_run_by_the_test):
    from fichero_server.execution import jobs
    from fichero_server.media import iiif_fetch

    manifest = _manifest3("job", 3)
    server = FakeIIIFServer({manifest["id"]: manifest})
    monkeypatch.setattr(iiif_fetch, "urllib_get", server.get)

    started = client.post("/api/iiif/import", json={"url": manifest["id"]})
    assert started.status_code == 200, started.text
    job = jobs.read_job(db, started.json()["job_id"])
    assert job["kind"] == iiif_source.IMPORT_KIND
    iiif_source.register_job_kinds()
    jobs.KINDS[iiif_source.IMPORT_KIND].run(db, job["subject"])
    folder = iiif_source.bound_folder(db, manifest["id"])
    assert len(db.query(Document, parent_id=folder.id)) == 3
    assert "Imported 3 new canvases" in jobs.read_job(db, job["id"])["reason"]

    server.documents[manifest["id"]] = _manifest3("job", 4)
    refreshed = client.post(f"/api/iiif/folders/{folder.id}/refresh")
    assert refreshed.status_code == 200, refreshed.text
    again = jobs.read_job(db, refreshed.json()["job_id"])
    jobs.KINDS[iiif_source.IMPORT_KIND].run(db, again["subject"])
    assert len(db.query(Document, parent_id=folder.id)) == 4

    assert client.post("/api/iiif/import", json={"url": "http://plain.example/m"}).status_code == 422
    assert client.post("/api/iiif/folders/nope/refresh").status_code == 404


def test_a_step_fetches_a_remote_page_at_its_size_once_into_a_bounded_cache(db, tmp_path, monkeypatch):
    from PIL import Image

    from fichero_server.workflows.tools.sources import _resolve_abs_path

    buf = BytesIO()
    Image.new("RGB", (240, 360), (230, 225, 210)).save(buf, format="JPEG")
    asked = []
    fetcher = PoliteFetcher(get=lambda url, t: asked.append(url) or (200, {}, buf.getvalue()))
    monkeypatch.setattr(iiif_source, "_FETCHER", fetcher)
    doc = Document(name="f. 1", metadata={"iiif_service": f"{HOST}/img/vol/1", "iiif_type": "Canvas"})
    package = tmp_path / "Lib.fichero"

    first = _resolve_abs_path(doc, str(package))
    second = _resolve_abs_path(doc, str(package))

    longest = iiif_source.STEP_LONGEST
    assert first == second and first.endswith(f"{doc.id}.jpg")
    assert asked == [f"{HOST}/img/vol/1/full/!{longest},{longest}/0/default.jpg"]  # once, at the step's size

    root = package / "storage" / "iiif-steps"
    old = root / "x" / "old.jpg"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x" * 100)
    import os

    os.utime(old, (1, 1))
    iiif_source._evict(root, budget=len(buf.getvalue()) + 10)
    assert not old.exists() and json.dumps(first)  # the least recently used went; the step's image stayed
    assert os.path.exists(first)


@pytest.fixture(autouse=True)
def _fresh_fetcher(monkeypatch):
    monkeypatch.setattr(iiif_source, "_FETCHER", None)
