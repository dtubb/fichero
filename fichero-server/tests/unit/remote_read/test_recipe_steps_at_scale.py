"""A recipe's steps at scale (spec: recipe-steps-at-scale, #5642).

`compute.recipe.fuse-same-place-steps`: a batch's consecutive steps at one remote place run as one stage; the
pages go once, each step runs on each page in the recipe's order, and each step's result file comes back. The
readers are faked (Kraken and a vision model run only where the job runs); the package, the runner and the files
are real.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from fichero_server import formats
from fichero_server.remote_read import runner


def _package(tmp: Path, stage: list[str], pages: int = 2) -> Path:
    from fichero_server.media import iiif_fetch

    pkg = tmp / "pkg"
    (pkg / "images").mkdir(parents=True)
    (pkg / "_fichero").mkdir()
    (pkg / "_fichero" / "iiif_fetch.py").write_text(Path(iiif_fetch.__file__).read_text())
    for i in range(pages):
        Image.new("RGB", (200, 100)).save(pkg / "images" / f"{i}.jpg")
    (pkg / "job.json").write_text(json.dumps({
        "step": {"reader": "kraken", "card": "k"}, "stage": stage, "fetch": {"longest": 2000},
        "shards": [list(range(pages))], "sources": [{"id": f"d{i}", "image": f"images/{i}.jpg"} for i in range(pages)]}))
    return pkg


def _found(image):
    w, _h = image.size
    return [{"polygon": [[10, 10], [w - 10, 10], [w - 10, 40], [10, 40]], "baseline": [[10, 35], [w - 10, 35]]}]


def test_lines_then_read_run_as_one_stage_the_read_given_the_lines_found(tmp_path):
    """WHY (`compute.recipe.fuse-same-place-steps`): lines and read placed on one cluster are one stage: each page's
    lines are found once and the read reads THOSE lines (never finding them again), and both steps' files return."""
    pkg = _package(tmp_path, ["lines", "read"])
    found, given = [], []

    def find(image):
        found.append(1)
        return _found(image)

    def read(image, lines):
        given.append(lines)
        return [{**line, "text": "Yten"} for line in lines]

    outcome = runner.run_shard(pkg, 0, tmp_path / "out", reader=read, lines_finder=find)

    assert len(found) == 2 and all(len(lines) == 1 and "text" not in lines[0] for lines in given)
    folder = tmp_path / "out" / "shard-00000"
    for doc in ("d0", "d1"):
        lines_page = formats.read_page("pagexml", (folder / f"{doc}.lines.xml").read_bytes())
        read_page = formats.read_page("pagexml", (folder / f"{doc}.xml").read_bytes())
        assert [s.kind for s in lines_page.segments if s.kind == "line"] == ["line"]
        assert [s for s in read_page.segments if s.kind == "line"][0].readings[0][1] == "Yten"
        steps = outcome["sources"][doc]["steps"]
        assert steps["lines"]["ok"] and steps["read"]["ok"] and steps["read"]["seconds"] >= 0


def test_a_page_whose_read_failed_keeps_its_lines_and_a_rerun_reads_them_without_finding_them_again(tmp_path):
    """WHY (`compute.recipe.fuse-same-place-steps`, `compute.recipe.done-is-landed`): a read that fails on a page
    leaves that page's lines done; the task run again (preempted, re-sent) reads it from the lines it found, and
    does nothing again on the page that was read."""
    pkg = _package(tmp_path, ["lines", "read"])
    found, calls = [], []

    def find(image):
        found.append(1)
        return _found(image)

    def read(image, lines):
        calls.append(1)
        if len(calls) == 2:  # the second page, the first time round
            raise RuntimeError("out of memory")
        return [{**line, "text": "x"} for line in lines]

    first = runner.run_shard(pkg, 0, tmp_path / "out", reader=read, lines_finder=find)
    assert first["sources"]["d1"]["ok"] is False and first["sources"]["d1"]["steps"]["lines"]["ok"]
    assert "out of memory" in first["sources"]["d1"]["why"]

    again = runner.run_shard(pkg, 0, tmp_path / "out", reader=read, lines_finder=find)
    assert len(found) == 2, "the lines found before were read back, not found again"
    assert len(calls) == 3 and again["sources"]["d1"]["ok"], "only the page that failed was read again"


def test_a_read_alone_still_finds_its_own_lines(tmp_path):
    """WHY: a stage of the read alone (no lines step at that place) is today's read: the reader finds the lines."""
    pkg = _package(tmp_path, ["read"], pages=1)
    outcome = runner.run_shard(pkg, 0, tmp_path / "out", reader=lambda image: [{**_found(image)[0], "text": "y"}])
    assert outcome["sources"]["d0"]["ok"] and set(outcome["sources"]["d0"]["steps"]) == {"read"}
    assert not (tmp_path / "out" / "shard-00000" / "d0.lines.xml").exists()


# --- the stage through the job: sent once, each step's files landed ----------------------------------------------

from fichero_server.models import DocType, Document, FileType, Segment, SegmentPass  # noqa: E402
from fichero_server.remote_read import job as read_job  # noqa: E402
from fichero_server.remote_read.job import ReadAtScaleRequest  # noqa: E402

from .test_read_at_scale_job import FakeHub  # noqa: E402


class StageHub(FakeHub):
    """Runs the real runner's stage on each shard; the read fails on the page named `unread`."""

    def __init__(self, unread):
        super().__init__()
        self.unread, self.stages = unread, []

    def fetch_part(self, job_key, part, local_dir):
        self.stages.append(json.loads((self.package / "job.json").read_text())["stage"])

        def read(image, lines):
            if image.size == self.unread:
                raise RuntimeError("CUDA out of memory")
            return [{**line, "text": "En la ciudad"} for line in lines]

        runner.run_shard(self.package, int(part.split("-")[1]), local_dir.parent, reader=read, lines_finder=_found)
        return local_dir


def test_a_stage_of_lines_and_read_lands_the_read_and_a_failed_reads_lines(db, tmp_path, monkeypatch, project_says_yes):
    """WHY (`compute.recipe.fuse-same-place-steps`, `compute.recipe.done-is-landed`): the job sends the pages once for
    both steps; a page read lands its read (lines and text, one pass); a page whose read failed lands the lines it got,
    so its lines step is done and only the read is left to do."""
    monkeypatch.setattr(read_job, "_work_dir", lambda job_id: tmp_path / "work" / job_id)
    monkeypatch.setattr(read_job.jobs._scheduler, "wake", lambda key: None)
    monkeypatch.setattr(read_job, "resolve_step", lambda request, bucket: {
        "reader": "vlm", "card": request.card, "model": "/work/models/student", "prompt": "Read the line.",
        "lines_per_call": 1, "language": "es"})
    folder = Document(name="EAP000", doc_type=DocType.folder)
    db.save(folder)
    (tmp_path / "photos").mkdir()
    pages = []
    for i, size in enumerate([(300, 400), (320, 400)]):
        path = tmp_path / "photos" / f"p{i}.jpg"
        Image.new("RGB", size, (200, 200, 190)).save(path)
        pages.append(Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path),
                              parent_id=folder.id, sequence=i))
        db.save(pages[-1])
    started = read_job.start(db, ReadAtScaleRequest(scope_ids=[folder.id], reader="vlm", card="c", pages_may_leave=True),
                             started_by="owner", target_factory=FakeHub, stage=("lines", "read"))
    subject = db.execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [started["job_id"]])[0]
    hub = StageHub(unread=(320, 400))
    read_job.run(db, subject, target=hub, sleep=lambda s: None)

    assert hub.stages == [["lines", "read"]]
    (read_pass,) = db.query(SegmentPass, document_id=pages[0].id)
    (lines_pass,) = db.query(SegmentPass, document_id=pages[1].id)
    read_lines = [s for s in db.query(Segment, pass_id=read_pass.id) if s.kind == "line"]
    unread_lines = [s for s in db.query(Segment, pass_id=lines_pass.id) if s.kind == "line"]
    assert len(read_lines) == 1 and len(unread_lines) == 1
    assert read_job.status(db, started["job_id"])["landing"] == {"landed": 1, "already": 0, "unread": 1, "set_aside": 0,
                                                                  "lines_only": 1}
