"""A read package and Fichero's runner (#5398 slice 2: reading at scale off the Mac).

The package carries what a reading job needs and nothing else; the runner reads one shard of it where
the job runs. The reader is faked here (Kraken and a vision model run only where the job runs); the
package, the fetching, the PAGE XML and the outcome record are real.
"""
from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from fichero_server import formats
from fichero_server.llm import line_reader
from fichero_server.models import DocType, Document, FileType
from fichero_server.remote_read import runner
from fichero_server.remote_read.package import NotSendable, ReadStep, build_read_package

HOST = "https://iiif.archive.example"


@pytest.fixture
def archive(db, tmp_path):
    """Three photos here, two canvases on a IIIF server, one page with nothing to read from."""
    folder = Document(name="EAP000", doc_type=DocType.folder)
    db.save(folder)
    photos = tmp_path / "photos"
    photos.mkdir()
    for i in range(1, 4):
        Image.new("RGB", (300, 400), (200 + i, 200, 190)).save(photos / f"p{i}.jpg")
        db.save(Document(name=f"p{i}.jpg", doc_type=DocType.file, file_type=FileType.image,
                         path=str(photos / f"p{i}.jpg"), parent_id=folder.id, sequence=i))
    for i in (4, 5):
        db.save(Document(name=f"f. {i}", doc_type=DocType.page, parent_id=folder.id, sequence=i,
                         metadata={"iiif_service": f"{HOST}/img/{i}", "width": 4000, "height": 6000}))
    db.save(Document(name="lost", doc_type=DocType.file, file_type=FileType.image, path=str(tmp_path / "gone.jpg"),
                     parent_id=folder.id, sequence=6))
    model = tmp_path / "student.safetensors"
    model.write_bytes(b"weights")
    return folder, ReadStep(reader="kraken", card="kraken-trained-abc", model_file=str(model))


def test_the_package_holds_sources_by_id_and_files_by_hash_and_no_mac_path(db, tmp_path, archive):
    """WHY (`compute.package.no-paths-cross`, `.least-needed`): a person's folder names never leave the
    Mac; a source is a document id, a file is its sha256; IIIF pages carry only their service."""
    folder, step = archive
    made = build_read_package(db, job_id="job-1", scope_ids=[folder.id], step=step, out_dir=tmp_path / "pkg",
                              shard_size=2)
    texts = [p.read_text(encoding="utf-8") for p in (tmp_path / "pkg").glob("*.json")]
    assert all(str(tmp_path) not in text for text in texts)
    job = json.loads((tmp_path / "pkg" / "job.json").read_text())
    assert [len(s) for s in job["shards"]] == [2, 2, 1] and len(job["sources"]) == 5
    assert job["sources"][3] == {"id": job["sources"][3]["id"], "iiif_service": f"{HOST}/img/4", "canvas": [4000, 6000]}
    assert all(s["image"].startswith("images/") for s in job["sources"][:3])
    assert made.skipped and made.skipped[0]["why"] == "its image is not on this Mac"
    rels = {o["rel"] for o in json.loads((tmp_path / "pkg" / "manifest.json").read_text())["objects"]}
    assert rels == {s["image"] for s in job["sources"][:3]} | {"models/student.safetensors"}


def test_the_same_request_makes_the_same_package(db, tmp_path, archive):
    """WHY (`compute.package.is-a-projection`): a package is never the record; made twice it is the
    same bytes, so it can be deleted and remade, and a re-send finds nothing new."""
    folder, step = archive
    for name in ("a", "b"):
        build_read_package(db, job_id="job-1", scope_ids=[folder.id], step=step, out_dir=tmp_path / name)
    for part in ("job.json", "manifest.json"):
        assert (tmp_path / "a" / part).read_bytes() == (tmp_path / "b" / part).read_bytes()


def test_a_step_that_cannot_be_sent_is_refused(db, tmp_path, archive):
    folder, _ = archive
    with pytest.raises(NotSendable, match="weights"):
        build_read_package(db, job_id="j", scope_ids=[folder.id], step=ReadStep(reader="vlm", card="x"),
                           out_dir=tmp_path / "p")
    with pytest.raises(NotSendable, match="not on this Mac"):
        build_read_package(db, job_id="j", scope_ids=[folder.id],
                           step=ReadStep(reader="kraken", card="k", model_file=str(tmp_path / "missing")), out_dir=tmp_path / "p")


def _jpeg(size):
    buf = io.BytesIO()
    Image.new("RGB", size, (220, 215, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _fake_reader(image):
    w, h = image.size
    return [{"polygon": [[10, 10], [w - 10, 10], [w - 10, 40], [10, 40]], "baseline": [[10, 35], [w - 10, 35]],
             "text": "Yten una negra & < >"}]


def test_a_shard_is_read_into_page_xml_fichero_reads_and_a_failure_does_not_stop_it(db, tmp_path, archive):
    """WHY: the results come home as PAGE XML through Fichero's own import, so the runner's files must be
    what Fichero's reader reads, in the pixels of the image actually read; and one archive image that
    will not come must be recorded with its reason while the rest of the shard is read."""
    folder, step = archive
    build_read_package(db, job_id="job-1", scope_ids=[folder.id], step=step, out_dir=tmp_path / "pkg", shard_size=5)
    asked = []

    def get(url, timeout):
        asked.append(url)
        return (200, {}, _jpeg((1333, 2000))) if "/img/4/" in url else (404, {}, b"")

    outcome = runner.run_shard(tmp_path / "pkg", 0, tmp_path / "out", reader=_fake_reader, get=get)

    job = json.loads((tmp_path / "pkg" / "job.json").read_text())
    ok = [s for s, o in outcome["sources"].items() if o["ok"]]
    failed = {s: o["why"] for s, o in outcome["sources"].items() if not o["ok"]}
    assert len(ok) == 4 and list(failed) == [job["sources"][4]["id"]] and "404" in failed[job["sources"][4]["id"]]
    assert asked[0] == f"{HOST}/img/4/full/!2000,2000/0/default.jpg", "fetched at the size the reader needs"
    data = (tmp_path / "out" / "shard-00000" / f"{job['sources'][3]['id']}.xml").read_bytes()
    assert formats.validate(formats.format_named("pagexml"), data) == []
    page = formats.read_page("pagexml", data)
    assert page.image_size == (1333, 2000)
    (line,) = [s for s in page.segments if s.kind == "line"]
    assert line.readings[0][1] == "Yten una negra & < >"


def test_a_shard_run_again_skips_what_it_already_read():
    """WHY: a preempted Slurm task or a re-sent Job starts the shard again; pages already read must not be
    read (and paid for) twice."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "pkg"
        (pkg / "images").mkdir(parents=True)
        (pkg / "_fichero").mkdir()
        from fichero_server.media import iiif_fetch
        (pkg / "_fichero" / "iiif_fetch.py").write_text(Path(iiif_fetch.__file__).read_text())
        Image.new("RGB", (100, 100)).save(pkg / "images" / "a.jpg")
        (pkg / "job.json").write_text(json.dumps({"step": {"reader": "kraken", "card": "k"}, "fetch": {"longest": 2000},
                                                  "shards": [[0]], "sources": [{"id": "d1", "image": "images/a.jpg"}]}))
        calls = []

        def reader(image):
            calls.append(1)
            return _fake_reader(image)

        runner.run_shard(pkg, 0, Path(tmp) / "out", reader=reader)
        runner.run_shard(pkg, 0, Path(tmp) / "out", reader=reader)
        assert len(calls) == 1


def test_the_runner_cuts_and_parses_as_the_line_reader_does():
    """WHY: a student trained on the line reader's pictures and answers must be shown and parsed the
    same way where it reads at scale; the runner cannot import Fichero there, so these pin the copy."""
    page = Image.new("RGB", (2000, 1200))
    polygon = [[100, 300], [900, 310], [900, 360], [100, 350]]  # under 1,600 px: no resize on either side
    assert page.crop(runner.crop_box(polygon, page.width, page.height)).size == line_reader.crop_line(page, polygon).size
    for raw in ('["Yten"]', '```json\n["a", null]\n```', "not json", '["a","b"]'):
        assert runner.parse_answer(raw, 1) == line_reader.parse_answer(raw, 1)
