"""One cut and one parser for the line reader and the runner (`compute.job.one-runner`, review debt on #5240):
the runner ships a copy of the engine's own functions, never a second implementation that can drift."""
from __future__ import annotations

import pytest
from PIL import Image

from fichero_server.llm import line_cut, line_reader
from fichero_server.remote_read import runner

CASES = ['["uno"]', '["null"]', '["  "]', "[null]", '```json\n["a"]\n```', "not json", '["a","b"]', "[1]"]


@pytest.mark.parametrize("raw", CASES)
def test_the_runner_parses_an_answer_exactly_as_the_line_reader_does(raw):
    """WHY: the mirror had already drifted: the text "null" (#5447) landed as a line's text on a cluster."""
    assert runner.parse_answer(raw, 1) == line_reader.parse_answer(raw, 1)


def test_there_is_one_implementation_and_the_package_ships_it(tmp_path):
    assert runner.crop_line is line_cut.crop_line and line_reader.crop_line is line_cut.crop_line
    assert runner.parse_answer is line_cut.parse_answer and line_reader.parse_answer is line_cut.parse_answer
    from fichero_server.remote_read import package

    assert line_cut.__file__ in {str(p) for p in package.SHIPPED_HELPERS}


def test_the_cut_is_unchanged():
    page = Image.new("RGB", (300, 100), (200, 190, 180))
    crop = line_cut.crop_line(page, [[50, 40], [250, 40], [250, 60], [50, 60]])
    assert crop.size == (200 + 2 * 7, 20 + 2 * 7)  # polygon bounds padded by a third of the 20 px height


def test_a_runner_shipped_alone_loads_the_line_cut_from_the_package(tmp_path):
    """WHY: on Hugging Face the runner has no engine to import; the package's `_fichero/line_cut.py` is the cut."""
    import json
    import subprocess
    import sys

    from fichero_server.remote_read import package as pkg

    helpers = tmp_path / "pkg" / "_fichero"
    helpers.mkdir(parents=True)
    for h in pkg.SHIPPED_HELPERS:
        (helpers / h.name).write_bytes(h.read_bytes())
    (tmp_path / "pkg" / "job.json").write_text(json.dumps({"shards": [[]], "sources": [], "step": {"reader": "x"}, "stage": ["read"],
                                                           "fetch": {"longest": 100}}))
    code = (
        "import sys; sys.modules['fichero_server'] = None; sys.path.insert(0, sys.argv[1])\n"
        "import runner; from pathlib import Path\n"
        "assert runner.crop_line is None\n"
        "runner.run_shard(Path(sys.argv[2]), 0, Path(sys.argv[3]), reader=lambda image: [])\n"
        "assert runner.crop_line is not None and runner.parse_answer('[\"null\"]', 1) == [None]\n")
    done = subprocess.run([sys.executable, "-c", code, str(helpers), str(tmp_path / "pkg"), str(tmp_path / "out")],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-600:]
