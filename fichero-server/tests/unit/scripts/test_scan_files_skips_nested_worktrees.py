"""Guards must not scan a nested agent worktree as if it were this repository.

Worktree isolation puts a FULL repo copy at `<cwd>/.claude/worktrees/<id>/`. git ignores
it; `Path.rglob` does not. On 2026-09-27 one under `docs/contributor_manual/specs/source/`
gave `check_spec_behaviors_are_tagged` 128 bogus findings, and 70-odd guards walked trees
the same way. They now go through `scan_rglob`, which prunes hidden directories below the
scan root. These tests pin both halves: the copy is skipped, the real file beside it is not.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scan_files = _load("_scan_files")


def _tree(root: Path) -> None:
    for rel in (
        "Views/Real.swift",
        "Views/Sub/Deep.swift",
        ".claude/worktrees/agent-x/Views/Real.swift",
        "Views/.build/Generated.swift",
        "Views/.swiftlint.swift",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("struct X {}\n")


def test_a_nested_worktree_copy_is_not_scanned(tmp_path):
    """If this fails, every guard reports the copy's files as this repo's — double
    findings, doubled scan floors, and violations nobody here can fix."""
    _tree(tmp_path)
    found = {p.relative_to(tmp_path).as_posix() for p in scan_files.scan_rglob(tmp_path, "*.swift")}
    assert not any(".claude" in f for f in found)
    assert "Views/.build/Generated.swift" not in found


def test_the_real_files_beside_it_are_still_scanned(tmp_path):
    """Over-fire check: pruning must not blind the guard to the files it exists for,
    including a hidden FILE at a real level (Path.rglob yields those too)."""
    _tree(tmp_path)
    found = {p.relative_to(tmp_path).as_posix() for p in scan_files.scan_rglob(tmp_path, "*.swift")}
    assert found == {"Views/Real.swift", "Views/Sub/Deep.swift", "Views/.swiftlint.swift"}


def test_a_root_that_itself_sits_inside_a_hidden_directory_is_scanned(tmp_path):
    """Only parts BELOW the root are judged: this lane's own checkout lives under
    `.claude/worktrees/`, and a guard run there must still see its tree."""
    root = tmp_path / ".claude" / "worktrees" / "me"
    _tree(root)
    found = {p.relative_to(root).as_posix() for p in scan_files.scan_rglob(root, "*.swift")}
    assert "Views/Real.swift" in found


def test_star_yields_directories_like_rglob(tmp_path):
    """`check_folder_organization` filters `rglob("*")` with `is_dir()`; the helper must
    keep yielding directories or that guard silently checks no folders."""
    _tree(tmp_path)
    dirs = {p.relative_to(tmp_path).as_posix() for p in scan_files.scan_rglob(tmp_path) if p.is_dir()}
    assert dirs == {"Views", "Views/Sub"}


def test_a_missing_root_raises_instead_of_scanning_nothing(tmp_path):
    """`Path.rglob` over a path that does not exist returns nothing, and an absence
    assertion over nothing passes: a test with `parents[4]` for `parents[3]` did exactly
    that on 2026-09-27. A walk that cannot happen must not read as a clean walk."""
    with pytest.raises(FileNotFoundError):
        list(scan_files.scan_rglob(tmp_path / "nope", "*.swift"))


def test_an_optional_root_may_be_absent(tmp_path):
    """Over-fire check: a root a checkout may legitimately lack opts out explicitly."""
    assert list(scan_files.scan_rglob(tmp_path / "nope", "*.swift", optional=True)) == []


def test_a_real_guard_ignores_the_copy(tmp_path, monkeypatch):
    """End to end through one routed guard: an orphan view that exists ONLY in a nested
    copy is not reported; the same orphan in the real tree is."""
    dead = _load("check_dead_files")
    orphan = "struct OrphanSheet: View { var body: some View { Text(\"x\") } }\n"
    copy = tmp_path / ".claude" / "worktrees" / "agent-x" / "Views" / "OrphanSheet.swift"
    copy.parent.mkdir(parents=True)
    copy.write_text(orphan)
    monkeypatch.setattr(dead, "SWIFT_ROOT", tmp_path)
    assert dead.scan() == {}
    (tmp_path / "Views").mkdir(exist_ok=True)
    (tmp_path / "Views" / "OrphanSheet.swift").write_text(orphan)
    assert "Views/OrphanSheet.swift" in dead.scan()


#: Walkers deliberately left on bare `rglob`, each with the reason.
BARE_RGLOB_ALLOWED = {
    # Walks a BUILT .app bundle, not a source tree; no worktree can be nested in it.
    "check_release_size_ratchet.py",
}


def test_no_guard_walks_a_tree_with_bare_rglob():
    """The class, not the instance: 70-odd guards had the same defect because each was
    written with the primitive that silently walks into hidden copies. A new guard written
    the old way would reintroduce it one file at a time."""
    offenders = sorted(
        path.name
        for path in SCRIPTS.glob("check_*.py")
        if path.name not in BARE_RGLOB_ALLOWED
        and re.search(r"\.rglob\(|os\.walk\(", path.read_text(encoding="utf-8"))
    )
    assert offenders == [], f"use _scan_files.scan_rglob instead: {offenders}"


#: Test files that walk a tree with bare `rglob`, each with why that is right. All of them
#: walk a RUNTIME directory the test itself created (a tmp dir, a library, a basetemp), where
#: an empty result can be the point and no source tree or nested worktree can appear.
TESTS_BARE_RGLOB_ALLOWED = {
    "conftest.py": "sizes leaked pytest basetemps under the system temp dir",
    "test_tmp_reclaim_bound.py": "walks the basetemp it is measuring",
    "test_auth_lazy_token.py": "looks for app.duckdb under a tmp base path",
    "test_library_sync_io.py": "asserts no .synctmp file is left in tmp_path",
    "test_unicode_library_merge_action.py": "hashes the files of a tmp library",
}


def test_no_test_walks_a_source_tree_with_bare_rglob():
    """The other half of the class. A test asserting ABSENCE over `rglob` of a computed
    root passes when the root does not exist — `parents[4]` for `parents[3]` did exactly
    that on 2026-09-27 — and walks any nested worktree copy as if it were this repo. Source
    scans in tests go through `scan_rglob`, which raises on a missing root."""
    repo = SCRIPTS.parent
    offenders = sorted(
        str(path.relative_to(repo))
        for base in ("fichero-server/tests", "fichero-cli/tests", "fichero-mcp/tests")
        if (repo / base).is_dir()
        for path in scan_files.scan_rglob(repo / base, "*.py")
        if path.name not in TESTS_BARE_RGLOB_ALLOWED
        and path.name != Path(__file__).name
        and re.search(r"\.rglob\(|os\.walk\(", path.read_text(encoding="utf-8"))
    )
    assert offenders == [], f"use _scan_files.scan_rglob for source scans: {offenders}"
