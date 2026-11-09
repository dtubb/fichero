"""dev-workflows.run.verify-all: one verdict row from every guard, the full engine suite and the app build; the DMG only after green."""
from __future__ import annotations

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import build, check_tool, journal, verify


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    root = tmp_path / "r"
    for d in ("fichero-server/tests", "fichero-cli/tests", "fichero-builder/tests"):
        (root / d).mkdir(parents=True)
    (root / "harness.toml").write_text('[check]\nwhole_tests = { "fichero-builder/fichero_builder/" = "fichero-builder/tests" }\nbuild_paths = ["fichero/"]\n')
    seen = []
    ok = {"guards": True, "suite": True, "build": True}
    monkeypatch.setattr(check_tool, "_git", lambda r, *a: {"stdout_tail": "a" * 40 + "\n", "ok": True})
    monkeypatch.setattr(check_tool, "_scratch_tree", lambda r, sha, p, cfg, overlay=True: str(root))
    monkeypatch.setattr(check_tool, "guards", lambda tree, cfg: (seen.append("guards"), {"ok": ok["guards"], "reason": "a guard red"})[1])
    monkeypatch.setattr(check_tool, "green_runs", lambda tree, files, whole, cfg, t: (seen.append(("suite", files, whole)), {"ok": ok["suite"]})[1])
    monkeypatch.setattr(check_tool, "build", lambda tree, names, cfg: (seen.append(("build", names)), {"ok": ok["build"], "skipped": False})[1])
    monkeypatch.setattr(build, "main", lambda a: (seen.append("dmg"), 0)[1])
    monkeypatch.setattr(verify.jail, "load", lambda r: None)
    return root, seen, ok


def run(root, *extra):
    return cli.main(["verify-all", "--root", str(root), "--state", str(journal.STATE), *extra])


def test_green_runs_every_part_writes_one_row_and_builds_the_dmg_only_with_build(world, monkeypatch):
    root, seen, _ok = world
    monkeypatch.setattr(check_tool, "load", lambda r: check_tool.Config(whole_tests={"fichero-builder/fichero_builder/": "fichero-builder/tests"},
                                                                       build_paths=("fichero/",)))
    assert verify.verify(root, jail_required=False)["ok"]
    assert "guards" in seen and ("suite", ["fichero-cli/tests", "fichero-server/tests"], ("fichero-builder/tests",)) in seen
    assert ("build", ["fichero/"]) in seen and "dmg" not in seen
    (row,) = [r for r in journal.read() if r["event"] == "verify"]
    assert row["ok"] and set(row["parts"]) == {"guards", "suite", "build"} and row["sha"] == "a" * 40


def test_a_red_part_is_not_verified_and_no_dmg_is_built(world, monkeypatch):
    root, seen, ok = world
    monkeypatch.setattr(check_tool, "load", lambda r: check_tool.Config(build_paths=("fichero/",)))
    ok["suite"] = False
    r = verify.verify(root, jail_required=False)
    assert not r["ok"] and r["parts"]["guards"]["ok"] and not r["parts"]["suite"]["ok"] and r["parts"]["build"]["ok"], "the others still ran"
    assert next(x for x in journal.read() if x["event"] == "verify")["ok"] is False
    monkeypatch.setattr(verify, "verify", lambda root_, **k: r)
    assert run(root, "--build") == 1 and "dmg" not in seen


def test_build_flag_makes_the_dmg_after_a_green_verdict(world, monkeypatch):
    root, seen, _ok = world
    monkeypatch.setattr(verify, "verify", lambda root_, **k: {"ok": True, "sha": "b" * 40, "parts": {"guards": {"ok": True, "seconds": 1, "detail": "green"}}})
    assert run(root) == 0 and "dmg" not in seen
    assert run(root, "--build") == 0 and "dmg" in seen


def test_two_overlapping_ladders_keep_the_jail_until_the_last_one_ends():
    """Speed 3 defect found 2026-11-02: the first ladder to end set the jail to None and the other's rungs ran as the owner."""
    j = object()
    check_tool._jail_enter(j), check_tool._jail_enter(j)
    check_tool._jail_exit()
    assert check_tool._JAIL is j
    check_tool._jail_exit()
    assert check_tool._JAIL is None


def test_a_red_part_names_what_failed_and_never_says_green(world, monkeypatch):
    root, _seen, _ok = world
    monkeypatch.setattr(check_tool, "load", lambda r: check_tool.Config(whole_tests={}, build_paths=("fichero/",)))
    monkeypatch.setattr(check_tool, "guards", lambda tree, cfg: {"ok": False, "reason": "", "results": [{"name": "check_a", "ok": True}, {"name": "check_b", "ok": False}]})
    assert not verify.verify(root, jail_required=False)["ok"]
    (row,) = [r for r in journal.read() if r["event"] == "verify"]
    assert row["parts"]["guards"]["detail"].startswith("failed: check_b")
