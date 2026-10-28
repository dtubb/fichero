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
