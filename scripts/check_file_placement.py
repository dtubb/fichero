#!/usr/bin/env python3
"""Per-batch file-placement guard (spec harness/code-organization.md, `code-org.enforce.per-batch-placement`).

`--since <base>` judges every file a batch ADDED, and the new path of every file it RENAMED, against the placement
rules below, from `git diff --name-status -M <merge-base> HEAD`. Deleted and modified-in-place files are not judged:
the tree's old debt belongs to the whole-tree guard (a later lane adds that mode to this file).

The rules are rows of RULES: each names the paths it looks at and returns where a misplaced file belongs. A later lane
adds rows (the Swift rules), not code.

Exit codes:
    0  every added or renamed file is in place (the count judged is printed)
    1  at least one file is misplaced, one line each: path, an arrow, the folder it belongs in, the rule
    2  BLIND: git failed, the base is unknown, the diff could not be parsed, or the tree is not this repo
       (with no flag the guard says the whole-tree mode is not built yet, and exits 0 on the real tree)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from _check_floor import require_scan_floor

ROOT = Path(__file__).resolve().parent.parent
BLIND_EXIT_CODE = 2
ARROW = " → "

SERVER_PKG = "fichero-server/src/fichero_server/"
ROUTES = SERVER_PKG + "api/routes/"
SERVER_TESTS = "fichero-server/tests/unit/"
# Where a Python module name is judged: the four source trees.
MODULE_TREES = ("fichero-server/src/", "fichero-cli/src/", "fichero-mcp/src/", "fichero-builder/fichero_builder/")

# spec `code-org.folders.root`, plus the dotfiles git itself needs.
ROOT_ALLOWED = frozenset({
    "AGENTS.md", "CLAUDE.md", "CONSTITUTION.md", "CONTRIBUTING.md", "README.md", "USER.md", "CHANGELOG.md",
    "RELEASE_NOTES.md", "LICENSE", "LICENSING.md", "NOTICE", "CLA.md", "CODE_OF_CONDUCT.md",
    "mkdocs.yml", "features.yaml", "harness.toml", "ruff.toml", ".swiftlint.yml", "coverage-baseline.json",
    "requirements-docs.txt", ".python-version", ".gitignore", ".gitattributes", ".gitmodules",
})
ROOT_ALLOWED_DIRS = (".github/",)

MODULE_NAME = re.compile(r"^[a-z_][a-z0-9_]*\.py$")
BANNED_NAMES = frozenset({"utils.py", "helpers.py", "misc.py", "common.py"})
TEST_NAME = re.compile(r"^test_[a-z][a-z0-9_]*?(_\d{3,5})?\.py$")
TEST_SIDE_FOLDERS = ("scripts", "cli", "mcp", "harness", "seams")
EXEMPT_TEST_NAMES = ("conftest.py", "__init__.py")
ALIAS_MARK = "sys.modules[" + "__name__]"  # split, so this file does not trip its own rule


@dataclass
class Tree:
    """What a rule may ask about the batch's tree: the new file's text and the engine's package folders."""

    repo: Path
    packages: frozenset[str]
    old_test_folders: frozenset[str] = frozenset()  # tests/unit/ folders the merge-base already had: judged by whoever made them

    def text(self, path: str) -> str:
        return _git(self.repo, "show", f"HEAD:{path}")


Judge = Callable[[str, Tree], "str | None"]  # path, tree -> "<destination>: <rule>" when misplaced


def _judge_root(path: str, _tree: Tree) -> str | None:
    if "/" in path or path in ROOT_ALLOWED:
        return None
    return "a folder (docs/, scripts/, or the product it belongs to): the repo root holds only the governance, config and product folders"


def _judge_alias(path: str, tree: Tree) -> str | None:
    if path.endswith(".py") and ALIAS_MARK in tree.text(path):
        return "the real module, imported where it is used: a module that aliases itself into sys.modules is a shim"
    return None


def _judge_package_root(path: str, _tree: Tree) -> str | None:
    rest = path[len(SERVER_PKG):]
    if "/" in rest or not rest.endswith(".py") or rest in ("__init__.py", "__main__.py"):
        return None
    return "fichero_server/<package>/" + rest + ": the package root holds only __init__ and __main__"


def _judge_routes_root(path: str, _tree: Tree) -> str | None:
    rest = path[len(ROUTES):]
    if "/" in rest or not rest.endswith(".py") or rest == "__init__.py":
        return None
    return "api/routes/<resource>/" + rest + ": api/routes/ root holds only its __init__"


def _judge_module_name(path: str, _tree: Tree) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if not name.endswith(".py"):
        return None
    if MODULE_NAME.match(name) and name not in BANNED_NAMES:
        return None
    return "a snake_case module named for what it does: not " + name


def _judge_test(path: str, tree: Tree) -> str | None:
    if not path.endswith(".py"):
        return None
    parts = path[len(SERVER_TESTS):].split("/")
    name = parts[-1]
    if name in EXEMPT_TEST_NAMES or name.startswith("_"):
        return None
    if not TEST_NAME.match(name):
        return "test_<what_it_proves>[_<issue>].py: the issue number is a suffix, never right after test_"
    folder = parts[0] if len(parts) > 1 else ""
    if folder in tree.packages or folder in TEST_SIDE_FOLDERS or folder in tree.old_test_folders:
        return None
    return "tests/unit/<package>/" + name + ": a new test sits in the folder mirroring its fichero_server package (or a tests/unit folder that already exists)"


@dataclass(frozen=True)
class Rule:
    name: str
    applies: Callable[[str], bool]
    judge: Judge


RULES: tuple[Rule, ...] = (
    Rule("repo root", lambda p: "/" not in p, _judge_root),
    Rule("no alias module", lambda p: p.endswith(".py"), _judge_alias),
    Rule("engine package root", lambda p: p.startswith(SERVER_PKG), _judge_package_root),
    Rule("api/routes root", lambda p: p.startswith(ROUTES), _judge_routes_root),
    Rule("module names", lambda p: p.startswith(MODULE_TREES), _judge_module_name),
    Rule("tests", lambda p: p.startswith(SERVER_TESTS), _judge_test),
)


class Blind(Exception):
    """Raised when the range cannot be read at all."""


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True, text=True, check=True, timeout=120,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise Blind(f"git {args[0]} failed: {getattr(exc, 'stderr', '') or exc}") from None


def parse_added(raw: str) -> list[str]:
    """New paths from `git diff --name-status -M -z`: every A, and the NEW name of every R."""
    fields = raw.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    paths, i = [], 0
    while i < len(fields):
        status = fields[i]
        if status[:1] == "R" or status[:1] == "C":
            if i + 2 >= len(fields):
                raise Blind(f"unparseable diff row at field {i}: {fields[i:i + 3]}")
            if status[:1] == "R":
                paths.append(fields[i + 2])
            i += 3
        elif status and status[0] in "AMDTU":
            if i + 1 >= len(fields):
                raise Blind(f"unparseable diff row at field {i}: {fields[i:]}")
            if status[:1] == "A":
                paths.append(fields[i + 1])
            i += 2
        else:
            raise Blind(f"unparseable diff status {status!r}")
    return paths


def judge(paths: list[str], tree: Tree) -> list[tuple[str, str]]:
    """[(path, "<destination>: <rule>")] for each misplaced path, first failing rule per path."""
    out = []
    for path in paths:
        for rule in RULES:
            if rule.applies(path) and (why := rule.judge(path, tree)):
                out.append((path, why))
                break
    return out


def _folders(repo: Path, rev: str, path: str) -> frozenset[str]:
    return frozenset(p.rsplit("/", 1)[-1] for p in _git(repo, "ls-tree", "-d", "--name-only", rev, path).split("\n") if p)


def run_since(base: str, repo: Path = ROOT, packages_floor: int = 10) -> int:
    merge_base = _git(repo, "merge-base", "HEAD", base).strip()
    raw = _git(repo, "diff", "--name-status", "-M", "-z", merge_base, "HEAD")
    paths = parse_added(raw)
    packages = _folders(repo, "HEAD", SERVER_PKG)
    require_scan_floor(len(packages), packages_floor, "fichero_server packages")
    bad = judge(paths, Tree(repo, packages, _folders(repo, merge_base, SERVER_TESTS)))
    for path, why in bad:
        print(f"{path}{ARROW}{why}")
    if bad:
        print(f"check_file_placement --since {base}: {len(bad)} of {len(paths)} added or renamed files misplaced")
        return 1
    print(f"check_file_placement --since {base}: {len(paths)} added or renamed files judged, all in place")
    return 0


# --- self-test: a scratch repo with one right and one wrong file per rule ---------------------------------------------

_PKG = "fichero-server/src/fichero_server/"
_RIGHT_ADDS = {
    "README.md": "x\n",
    ".github/workflows/x.yml": "x\n",
    _PKG + "core/new_thing.py": "x = 1\n",
    _PKG + "api/routes/library/new_route.py": "x = 1\n",
    "fichero-cli/src/fichero_cli/new_cmd.py": "x = 1\n",
    "fichero-mcp/src/fichero_mcp/new_tool.py": "x = 1\n",
    "fichero-builder/fichero_builder/new_step.py": "x = 1\n",
    SERVER_TESTS + "core/test_new_thing.py": "x = 1\n",
    SERVER_TESTS + "core/test_new_thing_6001.py": "x = 1\n",
    SERVER_TESTS + "scripts/test_a_guard.py": "x = 1\n",
    SERVER_TESTS + "core/conftest.py": "x = 1\n",
    SERVER_TESTS + "legacy/test_in_old_folder.py": "x = 1\n",
    "docs/anything.py": "x = 1\n",
}
_WRONG_ADDS = {
    "notes.txt": "x\n",
    _PKG + "stray_module.py": "x = 1\n",
    _PKG + "api/routes/stray_route.py": "x = 1\n",
    _PKG + "core/aliased.py": f"import sys\n{ALIAS_MARK} = 1\n",
    _PKG + "core/utils.py": "x = 1\n",
    _PKG + "core/BadName.py": "x = 1\n",
    "fichero-cli/src/fichero_cli/helpers.py": "x = 1\n",
    "fichero-mcp/src/fichero_mcp/Misc.py": "x = 1\n",
    "fichero-builder/fichero_builder/common.py": "x = 1\n",
    SERVER_TESTS + "test_loose.py": "x = 1\n",
    SERVER_TESTS + "nopackage/test_thing.py": "x = 1\n",
    SERVER_TESTS + "core/test_6001_thing.py": "x = 1\n",
    SERVER_TESTS + "core/thing_test.py": "x = 1\n",
}
_BASE_FILES = {
    **{_PKG + f"pkg{i}/__init__.py": "" for i in range(12)},
    _PKG + "core/__init__.py": "",
    _PKG + "__init__.py": "",
    "README.md.base": "x\n",
    SERVER_TESTS + "legacy/test_old.py": "x = 1\n",  # a test folder that is no package, already in the base
    "old_loose.py": "x = 1\n",  # base debt: never judged
    "fichero-builder/old_place.py": "x = 1\n",
    "fichero-builder/old_alias.py": f"{ALIAS_MARK} = 1\n",
    "fichero-builder/old_fine.py": "x = 1\n",
}
# renames: old (in base) -> new; the second is right, the others wrong
_RENAMES_WRONG = {
    "fichero-builder/old_place.py": _PKG + "moved_to_root.py",
    "fichero-builder/old_alias.py": _PKG + "core/moved_alias.py",
}
_RENAMES_RIGHT = {"fichero-builder/old_fine.py": _PKG + "core/moved_fine.py"}


def _write(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@example.invalid"), ("config", "user.name", "t"),
                     ("config", "commit.gpgsign", "false")):
            _git(repo, *args)
        _write(repo, _BASE_FILES)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "checkout", "-q", "-b", "work")
        _write(repo, _RIGHT_ADDS)
        _write(repo, _WRONG_ADDS)
        for old, new in {**_RENAMES_WRONG, **_RENAMES_RIGHT}.items():
            (repo / new).parent.mkdir(parents=True, exist_ok=True)
            _git(repo, "mv", old, new)
        (repo / "old_loose.py").write_text("x = 2\n", encoding="utf-8")  # modified in place: not judged
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "batch")

        paths = parse_added(_git(repo, "diff", "--name-status", "-M", "-z", "main", "HEAD"))
        if not paths:
            print("self-test FAILED: the guard saw no added or renamed file in a range that has many", file=sys.stderr)
            return 1
        tree = Tree(repo, _folders(repo, "HEAD", _PKG), _folders(repo, "main", SERVER_TESTS))
        got = dict(judge(paths, tree))
        expected = set(_WRONG_ADDS) | set(_RENAMES_WRONG.values())
        if set(got) != expected:
            print("self-test FAILED: reported", sorted(got), "expected", sorted(expected), file=sys.stderr)
            return 1
        wants = {
            "notes.txt": "repo root",
            _PKG + "stray_module.py": "fichero_server/<package>/stray_module.py",
            _PKG + "api/routes/stray_route.py": "api/routes/<resource>/stray_route.py",
            SERVER_TESTS + "test_loose.py": "tests/unit/<package>/test_loose.py",
            SERVER_TESTS + "nopackage/test_thing.py": "tests/unit/<package>/test_thing.py",
            SERVER_TESTS + "core/test_6001_thing.py": "suffix",
            _PKG + "moved_to_root.py": "fichero_server/<package>/moved_to_root.py",
            _PKG + "core/moved_alias.py": "sys.modules",
        }
        for path, fragment in wants.items():
            if fragment not in got[path]:
                print(f"self-test FAILED: {path} reported as {got[path]!r}, expected it to name {fragment!r}", file=sys.stderr)
                return 1
        if run_since("main", repo) != 1:
            print("self-test FAILED: the range with misplaced files did not exit 1", file=sys.stderr)
            return 1
        try:
            run_since("no-such-base", repo)
        except Blind:
            pass
        else:
            print("self-test FAILED: an unknown base did not go blind", file=sys.stderr)
            return 1
    print("self-test ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", metavar="BASE", default=None, help="judge the files this item added or renamed since its merge-base with BASE")
    parser.add_argument("--self-test", action="store_true", help="run the guard over a scratch repo with one right and one wrong file per rule")
    args = parser.parse_args(argv)
    if args.self_test:
        try:
            return _self_test()
        except Blind as exc:
            print(f"check_file_placement: self-test BLIND: {exc}", file=sys.stderr)
            return BLIND_EXIT_CODE
    if args.since is None:
        if not (ROOT / SERVER_PKG).is_dir():
            print(f"check_file_placement: BLIND: {SERVER_PKG} is missing (the tree moved)", file=sys.stderr)
            return BLIND_EXIT_CODE
        print("check_file_placement: the whole-tree mode is not built yet (a later lane); the per-batch run is --since <base>")
        return 0
    try:
        return run_since(args.since)
    except Blind as exc:
        print(f"check_file_placement: BLIND: {exc}", file=sys.stderr)
        return BLIND_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
