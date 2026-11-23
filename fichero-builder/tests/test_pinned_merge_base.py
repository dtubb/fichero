"""#6853: the pinned-checks rung judges what the lane changed (merge-base...head), so a landing that moved a pinned file
on the base, which the lane did not touch, is no violation."""

import subprocess

from fichero_builder import check_tool as ct


def _g(d, *a):
    return subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()


def test_a_base_that_moved_a_pinned_file_is_no_violation_for_a_lane_that_did_not(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    _g(w, "init", "-q", "-b", "main")
    (w / "harness.toml").write_text('[check]\ncheck_paths = ["harness.toml"]\n')
    (w / "a.py").write_text("1\n")
    _g(w, "add", "."), _g(w, "commit", "-q", "-m", "base")
    old = _g(w, "rev-parse", "HEAD")
    _g(w, "checkout", "-q", "-b", "lane")
    (w / "a.py").write_text("2\n")
    _g(w, "commit", "-qam", "lane")
    lane = _g(w, "rev-parse", "HEAD")
    _g(w, "checkout", "-q", "main")
    (w / "harness.toml").write_text('[check]\ncheck_paths = ["harness.toml"]\n# moved by a landing\n')
    _g(w, "commit", "-qam", "landing moves the pinned file")
    moved = _g(w, "rev-parse", "HEAD")
    pinned = tmp_path / "pinned"
    subprocess.run(["git", "clone", "-q", str(w), str(pinned)], check=True, capture_output=True)
    cfg = ct.load(pinned)
    assert ct.pinned_violations(w, moved, lane, cfg, pinned) == []
    assert ct.pinned_violations(w, old, lane, cfg, pinned) == []
    _g(w, "checkout", "-q", "lane")
    (w / "harness.toml").write_text("# the lane edits it\n")
    _g(w, "commit", "-qam", "lane edits")
    assert ct.pinned_violations(w, moved, _g(w, "rev-parse", "HEAD"), cfg, pinned) != []


def test_the_lane_diff_leaves_out_a_pinned_file_only_the_base_moved(tmp_path):
    from fichero_builder import work

    w = tmp_path / "w"
    w.mkdir()
    _g(w, "init", "-q", "-b", "main")
    (w / "harness.toml").write_text("a\n")
    (w / "a.py").write_text("1\n")
    _g(w, "add", "."), _g(w, "commit", "-q", "-m", "base")
    _g(w, "checkout", "-q", "-b", "lane")
    (w / "a.py").write_text("2\n")
    _g(w, "commit", "-qam", "lane")
    lane = _g(w, "rev-parse", "HEAD")
    _g(w, "checkout", "-q", "main")
    (w / "harness.toml").write_text("moved\n")
    _g(w, "commit", "-qam", "landing")
    assert work.lane_diff(w, "main", lane, "--name-only").split() == ["a.py"]
    assert work.lane_diff(w, "main", lane, paths=("harness.toml",)) == ""
