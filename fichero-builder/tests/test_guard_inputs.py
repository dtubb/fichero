"""The repo's [check.guard_inputs] (speed 5) names real guards and real paths: a stale prefix makes rev-parse fail, so that
guard silently never caches; a renamed guard keeps a dead entry (2026-11-08, #6116)."""
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_declared_guard_exists_and_every_input_is_in_the_tree():
    inputs = tomllib.loads((ROOT / "harness.toml").read_text())["check"]["guard_inputs"]
    assert len(inputs) > 50
    for stem, prefixes in inputs.items():
        assert (ROOT / "scripts" / f"{stem}.py").is_file(), stem
        assert "scripts" in prefixes, stem  # the guard itself, its helpers and baselines
        for p in prefixes:
            if not (ROOT / ".git").exists():  # a gate copy (the M4 run dir) has no repo: the tree itself is the check
                assert (ROOT / p).exists(), f"{stem}: {p} is not in the tree"
                continue
            r = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"HEAD:{p}"], capture_output=True)
            assert r.returncode == 0, f"{stem}: {p} is not in HEAD"


def test_a_since_guard_takes_one_prefix_or_a_list_of_them(tmp_path):
    from fichero_builder import check_tool

    cfg = check_tool.Config(since_guards={"scripts/check_a.py": "fichero/", "scripts/check_b.py": ["fichero/", "fichero-server/"]})
    ran = []
    original = check_tool._run
    check_tool._run = lambda name, *a, **k: ran.append(name) or {"ok": True}
    try:
        check_tool.since_guards(tmp_path, "base", ["fichero-server/x.py"], cfg)
        assert ran == ["check_b"]
        ran.clear()
        check_tool.since_guards(tmp_path, "base", ["fichero/y.swift"], cfg)
        assert ran == ["check_a", "check_b"]
    finally:
        check_tool._run = original
