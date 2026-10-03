"""Image tools write scratch files into a per-run folder that goes when the run ends (#5386).

WHY: split, prepare, rotate and six other image tools wrote to fixed folders under the system temp
directory that nothing cleaned; on the Sergio notebooks (374 photos, a nearly full disk) that was
gigabytes of copies left behind, and the next run reused stale files beside new ones. A run's
scratch folder is now its own and is removed with the run, unless the run is paused.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from fichero_server.workflows.tools.run_scratch import remove_run_scratch, run_scratch_dir
from fichero_server.workflows.tools.split_images import split_image_file


def test_split_writes_into_its_runs_folder_and_the_run_end_removes_it(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    folder = run_scratch_dir({"task_id": "run-1"}, "split-images")
    assert Path(folder).is_relative_to(tmp_path / "fichero-runs" / "run-1")
    src = tmp_path / "spread.jpg"
    Image.new("RGB", (60, 40), "white").save(src)
    out = split_image_file(src, folder)
    assert out["outputs"] and all(Path(p).is_file() for p in out["outputs"])

    remove_run_scratch("run-1")
    assert not (tmp_path / "fichero-runs" / "run-1").exists()


def test_two_runs_do_not_share_a_scratch_folder():
    assert run_scratch_dir({"task_id": "a"}, "split-images") != run_scratch_dir({"task_id": "b"}, "split-images")
