#!/usr/bin/env python3
"""Per-batch file-placement guard (spec harness/code-organization.md, `code-org.enforce.per-batch-placement`).

`--since <base>` judges every file a batch ADDED, and the new path of every file it RENAMED, against the placement
rules below, from `git diff --name-status -M <merge-base> HEAD`. Deleted and modified-in-place files are not judged:
the tree's old debt belongs to the whole-tree mode (no flag), which judges every tracked file against KNOWN_VIOLATIONS.

The rules are rows of RULES: each names the paths it looks at and returns where a misplaced file belongs. A later lane
adds rows (the Swift rules), not code.

Exit codes:
    0  every added or renamed file is in place (the count judged is printed)
    1  at least one file is misplaced, one line each: path, an arrow, the folder it belongs in, the rule
    2  BLIND: git failed, the base is unknown, the diff could not be parsed, or the tree is not this repo
       (no flag: the whole-tree mode; 0 when nothing exceeds KNOWN_VIOLATIONS, 1 when a count rises or an entry is stale)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from _check_floor import require_scan_floor
from check_swift_one_type_per_file import analyze, file_findings

ROOT = Path(__file__).resolve().parent.parent
BLIND_EXIT_CODE = 2
ARROW = " → "

SERVER_PKG = "fichero-server/src/fichero_server/"
ROUTES = SERVER_PKG + "api/routes/"
SERVER_TESTS = "fichero-server/tests/unit/"
APP = "fichero/fichero/"
SWIFT_TESTS = "fichero/Tests/Unit/"
APP_LAYERS = ("App", "Models", "Services", "Intents", "Views", "Resources")
MIRROR_LAYERS = ("Views", "Models", "Services", "App", "Intents")
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
    on_disk: bool = False  # whole-tree mode reads the working tree; --since reads HEAD
    merge_base: str = "HEAD"
    _facts: dict = field(default_factory=dict, repr=False)

    def text(self, path: str) -> str:
        if self.on_disk:
            return (self.repo / path).read_text(encoding="utf-8", errors="replace")
        return _git(self.repo, "show", f"HEAD:{path}")

    def facts(self, path: str):
        """The parsed Swift file, read once per path (two rules ask)."""
        if path not in self._facts:
            self._facts[path] = analyze(self.text(path))
        return self._facts[path]

    def has_dir(self, path: str, rev: str = "HEAD") -> bool:
        if self.on_disk:
            return (self.repo / path).is_dir()
        return bool(_git(self.repo, "ls-tree", "-d", "--name-only", rev, path.rstrip("/")).strip())


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


def _judge_swift_layer(path: str, _tree: Tree) -> str | None:
    if path[len(APP):].split("/")[0] in APP_LAYERS and "/" in path[len(APP):]:
        return None
    return "fichero/fichero/<Layer>/<Feature>/: a Swift file sits under App, Models, Services, Intents, Views or Resources, never at the app root"


def _judge_swift_view_place(path: str, tree: Tree) -> str | None:
    rest = path[len(APP):]
    views = [t for t in tree.facts(path).types if t.is_view]
    if not views:
        return None
    parts = rest.split("/")
    app_root = parts[0] == "App" and all(t.name.endswith(("Scene", "Window")) for t in views)  # the app's own window roots
    if (parts[0] == "Views" and len(parts) > 2) or rest.startswith("App/Menus/") or app_root:
        return None
    return "Views/<Feature>/ (menu commands: App/Menus/): a View type lives under a feature folder of Views/"


def _judge_swift_name(path: str, tree: Tree) -> str | None:
    for finding in file_findings(path[len(APP):], tree.facts(path)):
        kind, _, what = finding.partition(": ")
        if kind == "file-name":
            return "a file named for its type: " + what
        if kind == "view-shape":
            return "a View type ending in a shape word: " + what
        if kind == "platform":
            return "IOS / MacOS spelling: " + what
    return None


def _judge_swift_test(path: str, tree: Tree) -> str | None:
    parts = path[len(SWIFT_TESTS):].split("/")
    name = parts[-1]
    if len(parts) == 2 and parts[0] == "general" and not name.endswith("Tests.swift"):
        return None  # shared helpers (TestFixtures, AppSource, EngineHarness) sit at Tests/Unit/general/
    if not name.endswith("Tests.swift"):
        return "<Name>Tests.swift: a new test file ends Tests.swift"
    if len(parts) < 3:
        return None  # a platform's own canary tests
    folder = "/".join(parts[:-1])
    if parts[1] in MIRROR_LAYERS:
        if tree.has_dir(APP + "/".join(parts[1:-1])) or tree.has_dir(SWIFT_TESTS + folder, tree.merge_base):
            return None
        return f"{APP}{'/'.join(parts[1:-1])}/ has no app folder: the test folder mirrors an existing fichero/fichero/<Layer>/<Feature>/"
    if tree.has_dir(SWIFT_TESTS + folder, tree.merge_base):
        return None
    return "fichero/Tests/Unit/<platform>/<Layer>/<Feature>/: a new test sits in the folder mirroring its app folder (or a test folder that already exists)"


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
    Rule("swift layer", lambda p: p.startswith(APP) and p.endswith(".swift"), _judge_swift_layer),
    Rule("swift view place", lambda p: p.startswith(APP) and p.endswith(".swift"), _judge_swift_view_place),
    Rule("swift names", lambda p: p.startswith(APP) and p.endswith(".swift"), _judge_swift_name),
    Rule("swift tests", lambda p: p.startswith(SWIFT_TESTS) and p.endswith(".swift"), _judge_swift_test),
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
    bad = judge(paths, Tree(repo, packages, _folders(repo, merge_base, SERVER_TESTS), merge_base=merge_base))
    for path, why in bad:
        print(f"{path}{ARROW}{why}")
    if bad:
        print(f"check_file_placement --since {base}: {len(bad)} of {len(paths)} added or renamed files misplaced")
        return 1
    print(f"check_file_placement --since {base}: {len(paths)} added or renamed files judged, all in place")
    return 0


# --- whole-tree mode: the same rules over every tracked file, against a baseline of today's debt ------------------------

# Misplaced files today, counted per (folder, rule): "<folder>  [<rule>]" -> how many. A count that rises fails; an entry whose
# folder is gone or that no longer finds a file fails (delete it); a count that fell is a note (lower it). The list only shrinks.
KNOWN_VIOLATIONS: dict[str, int] = {
    ".  [repo root]": 1,
    "fichero-server/src/fichero_server  [engine package root]": 18,
    "fichero-server/src/fichero_server/api/routes  [api/routes root]": 7,
    "fichero-server/src/fichero_server/workflows  [no alias module]": 6,
    "fichero-server/tests/unit  [tests]": 22,
    "fichero-server/tests/unit/activity  [tests]": 2,
    "fichero-server/tests/unit/api  [tests]": 2,
    "fichero-server/tests/unit/check  [tests]": 11,
    "fichero-server/tests/unit/export  [tests]": 11,
    "fichero-server/tests/unit/finddocs  [tests]": 1,
    "fichero-server/tests/unit/jobs  [tests]": 128,
    "fichero-server/tests/unit/kg  [tests]": 25,
    "fichero-server/tests/unit/packaging  [tests]": 1,
    "fichero-server/tests/unit/transport  [tests]": 28,
    "scripts  [no alias module]": 1,
}
TRACKED_FLOOR = 4000  # tracked files on 2026-11-15: 8064


def tracked_files(repo: Path) -> list[str]:
    return [p for p in _git(repo, "ls-files", "-z").split("\0") if p]


def judge_rule_named(paths: list[str], tree: Tree) -> list[tuple[str, str, str]]:
    """[(path, rule name, why)] for each misplaced path, first failing rule per path."""
    out = []
    for path in paths:
        for rule in RULES:
            if rule.applies(path) and (why := rule.judge(path, tree)):
                out.append((path, rule.name, why))
                break
    return out


def _is_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:  # a path this user may not stat: tracked, but not ours to judge
        return False


def whole_tree_counts(repo: Path, floor: int = TRACKED_FLOOR) -> tuple[dict[str, int], dict[str, list[str]], int]:
    paths = tracked_files(repo)
    require_scan_floor(len(paths), floor, "tracked files")
    packages = _folders(repo, "HEAD", SERVER_PKG)
    require_scan_floor(len(packages), 10, "fichero_server packages")
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    tree = Tree(repo, packages, on_disk=True)
    # the Swift rules judge a batch's new files only: the whole tree's Swift debt is baselined by check_swift_one_type_per_file
    # and check_folder_organization, so counting it here too would hold it in two baselines
    for path, rule, _why in judge_rule_named([p for p in paths if _is_file(repo / p) and not p.endswith(".swift")], tree):
        key = f"{path.rsplit('/', 1)[0] if '/' in path else '.'}  [{rule}]"
        counts[key] = counts.get(key, 0) + 1
        examples.setdefault(key, []).append(path)
    return counts, examples, len(paths)


def run_whole_tree(repo: Path = ROOT, known: dict[str, int] | None = None, floor: int = TRACKED_FLOOR) -> int:
    known = KNOWN_VIOLATIONS if known is None else known
    counts, examples, scanned = whole_tree_counts(repo, floor)
    rose = {k: (known.get(k, 0), n) for k, n in counts.items() if n > known.get(k, 0)}
    gone = sorted(k for k in known if k not in counts)
    fell = {k: (known[k], counts[k]) for k in known if k in counts and counts[k] < known[k]}
    for key, (was, now) in sorted(rose.items()):
        print(f"{key}: {now} misplaced (baseline {was}): " + ", ".join(sorted(examples[key])[:5]))
    for key in gone:
        print(f"{key}: baseline entry is clean or its folder is gone: delete it from KNOWN_VIOLATIONS")
    for key, (was, now) in sorted(fell.items()):
        print(f"note: {key}: {now} now (baseline {was}): lower the baseline")
    if rose or gone:
        print(f"check_file_placement: {len(rose)} folder(s) over baseline, {len(gone)} stale baseline entr(ies)")
        return 1
    print(f"check_file_placement: {scanned} tracked files judged, {sum(counts.values())} known misplaced in {len(counts)} folder(s), none new")
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
_A = "fichero/fichero/"
_T = "fichero/Tests/Unit/"
_RIGHT_ADDS.update({
    _A + "Views/Library/NewThingView.swift": "import SwiftUI\nstruct NewThingView: View {}\n",
    _A + "App/Menus/NewCommands.swift": "struct NewCommands: View {}\n",
    _A + "Models/Library/NewThing.swift": "struct NewThing {}\n",
    _T + "general/Views/Library/NewThingViewTests.swift": "x\n",
    _T + "general/Engine/NewEngineTests.swift": "x\n",  # a test folder the base already had
    _T + "general/TestMoreFixtures.swift": "x\n",
})
_WRONG_ADDS.update({
    _A + "Loose.swift": "struct Loose {}\n",
    _A + "Models/Library/WrongName.swift": "struct SomethingElse {}\n",
    _A + "Models/Library/Stray.swift": "struct StrayView: View {}\n",
    _A + "Views/Library/Odd.swift": "struct Odd: View {}\n",
    _A + "Views/Library/PaneiOS.swift": "struct PaneiOS {}\n",
    _T + "general/Views/Nowhere/ThingTests.swift": "x\n",
    _T + "general/Views/Library/ThingCheck.swift": "x\n",
})
_BASE_FILES = {
    _A + "Views/Library/Old.swift": "struct Old {}\n",
    _A + "Models/Library/Old.swift": "struct Old {}\n",
    _T + "general/Engine/OldTests.swift": "x\n",
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
        tree = Tree(repo, _folders(repo, "HEAD", _PKG), _folders(repo, "main", SERVER_TESTS), merge_base="main")
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
            _A + "Loose.swift": "never at the app root",
            _A + "Models/Library/WrongName.swift": "named for its type",
            _A + "Models/Library/Stray.swift": "Views/<Feature>/",
            _A + "Views/Library/Odd.swift": "shape word",
            _A + "Views/Library/PaneiOS.swift": "IOS / MacOS",
            _T + "general/Views/Nowhere/ThingTests.swift": "no app folder",
            _T + "general/Views/Library/ThingCheck.swift": "Tests.swift",
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
        if _self_test_whole_tree(repo) != 0:
            return 1
    print("self-test ok")
    return 0


def _self_test_whole_tree(repo: Path) -> int:
    """The whole-tree mode on the scratch repo: a planted loose module fails, none passes, a stale baseline fails."""
    _git(repo, "checkout", "-q", "main")
    clean = {_PKG + "stray_module.py"}  # absent on main
    if run_whole_tree(repo, {}, floor=1) != 1:
        print("self-test FAILED: a zero baseline over a tree with known debt did not fail", file=sys.stderr)
        return 1
    counts, _, _ = whole_tree_counts(repo, floor=1)
    if counts != {".  [repo root]": 2, "fichero-builder  [no alias module]": 1, SERVER_TESTS + "legacy  [tests]": 1}:
        print(f"self-test FAILED: main's debt read as {counts}", file=sys.stderr)
        return 1
    if run_whole_tree(repo, dict(counts), floor=1) != 0:
        print("self-test FAILED: the tree equal to its baseline did not pass", file=sys.stderr)
        return 1
    if run_whole_tree(repo, {**counts, "gone/folder  [repo root]": 1}, floor=1) != 1:
        print("self-test FAILED: a baseline entry with no file did not fail", file=sys.stderr)
        return 1
    _write(repo, {p: "x = 1\n" for p in clean})
    _git(repo, "add", "-A")
    if run_whole_tree(repo, dict(counts), floor=1) != 1:
        print("self-test FAILED: a planted loose engine module did not fail", file=sys.stderr)
        return 1
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
        try:
            return run_whole_tree()
        except Blind as exc:
            print(f"check_file_placement: BLIND: {exc}", file=sys.stderr)
            return BLIND_EXIT_CODE
    try:
        return run_since(args.since)
    except Blind as exc:
        print(f"check_file_placement: BLIND: {exc}", file=sys.stderr)
        return BLIND_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
