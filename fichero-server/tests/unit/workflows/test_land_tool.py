"""land gate: a READY verdict is keyed by the verbatim patch-id, so a moved line is not the reviewed commit (review 3 B6)."""

from __future__ import annotations

import json
import subprocess

from fichero_server.workflows import land_tool as L


def _repo(tmp_path):
    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\n")
    g("add", "."), g("commit", "-q", "-m", "base")
    return g, g("rev-parse", "HEAD")


def _verdict(tmp_path, root_g, base, head):
    keys = L.commit_keys(tmp_path, base, head)
    s = tmp_path.parent / (tmp_path.name + "-verdicts.json")
    s.write_text(json.dumps({k["patch_id"]: {"verdict": "READY", "message_hash": k["message_hash"]} for k in keys}))
    return s


def test_a_reviewed_commit_lands_and_a_moved_line_does_not(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\n    k()\n")
    g("commit", "-qam", "reviewed")
    good = _verdict(tmp_path, g, base, g("rev-parse", "HEAD"))
    assert L.unreviewed(tmp_path, base, "HEAD", good) == []
    g("reset", "-q", "--hard", base)
    (tmp_path / "m.py").write_text("if x:\n    g()\nh()\nk()\n")  # h() moved out of the if
    g("commit", "-qam", "reviewed")  # same message, different indentation
    assert len(L.unreviewed(tmp_path, base, "HEAD", good)) == 1


def test_a_changed_message_or_a_merge_is_refused(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "a.py").write_text("a = 1\n")
    g("add", "."), g("commit", "-qm", "Part of #1")
    store = _verdict(tmp_path, g, base, g("rev-parse", "HEAD"))
    g("commit", "-q", "--amend", "-m", "Fixes #1")
    assert "no READY verdict" in L.unreviewed(tmp_path, base, "HEAD", store)[0]
    g("checkout", "-q", "-b", "side", base)
    (tmp_path / "b.py").write_text("b = 1\n")
    g("add", "."), g("commit", "-qm", "side")
    g("checkout", "-q", "main")
    g("merge", "--no-ff", "-qm", "merge", "side")
    assert "merge" in L.unreviewed(tmp_path, base, "HEAD", store)[0]


def test_the_boundary_grep_flags_private_text_in_added_lines_and_messages(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\nP = '/Users/someone/secret'\n")
    g("commit", "-qam", "add; token sk-ant-abc123")
    hits = L.boundary(tmp_path, base, "HEAD", [r"/Users/\w+", r"sk-ant-\w+"])
    assert any("m.py" in h and "/Users/" in h for h in hits) and any("message" in h and "sk-ant-" in h for h in hits)
    assert L.boundary(tmp_path, base, "HEAD", []) == []
    g("reset", "-q", "--hard", base)
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\n    k()\n")
    g("commit", "-qam", "clean")
    assert L.boundary(tmp_path, base, "HEAD", [r"/Users/\w+"]) == []  # only ADDED lines count, not the old ones
