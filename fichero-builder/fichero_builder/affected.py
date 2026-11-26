"""The tests a batch can affect (speed-tests-1, part 1): changed source file -> the test files that import it, directly or through
another module, by a static import scan of the tree. Each file's imports are cached by its blob sha, so a batch parses only the files
that changed since the last map.

A change the map cannot place runs the whole suite: a conftest, a pytest/pyproject config, a fixture, a data file under a tests dir or
under a package source dir, or a Python file that does not parse. Everything else outside Python (Swift, docs) places to no test.

ponytail: a test that reaches code only by path (a subprocess running scripts/x.py, a file read) is not seen by the import scan; those
belong in `[check].always_tests` or `[check.whole_tests]`."""
from __future__ import annotations

import ast
import fnmatch
import json
from pathlib import Path

WHOLE_NAMES = ("conftest.py", "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "pyproject.toml", "tox.ini", "setup.cfg")
FIXTURE_DIRS = {"fixtures", "test-fixtures"}
SKIP_DIRS = {".git", "node_modules", ".build", "derived", "venv", ".venv", "__pycache__"}


def _is_test_dir(p: Path) -> bool:
    return bool({"tests", "Tests"} & set(p.parts[:-1]))


def _dotted(parts: tuple[str, ...]) -> str:
    parts = parts[:-1] + ((parts[-1][:-3],) if parts[-1].endswith(".py") else (parts[-1],))
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def module_names(path: str, python_path: tuple[str, ...]) -> set[str]:
    """Every dotted name `path` can be imported as: relative to each python_path root it sits under, relative to the repo root, and, for a
    helper in a tests dir (`from _fake_index import x`), its bare stem."""
    p = Path(path)
    names = {_dotted(p.parts)}
    for root in python_path:
        rp = Path(root)
        if p.parts[:len(rp.parts)] == rp.parts and len(p.parts) > len(rp.parts):
            names.add(_dotted(p.parts[len(rp.parts):]))
    if _is_test_dir(p) and p.suffix == ".py":
        names.add(p.stem)
    names.discard("")
    return names


def _imports(src: str, path: str) -> set[str]:
    """The dotted names a file imports, each with its parent packages; relative imports resolved against the file's package."""
    tree = ast.parse(src)
    pkg = list(Path(path).parts[:-1])
    out: set[str] = set()

    def add(name: str) -> None:
        bits = name.split(".")
        out.update(".".join(bits[:i]) for i in range(1, len(bits) + 1))

    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                add(a.name)
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                up = pkg[:len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                base = ".".join([*up, *([base] if base else [])])
            if base:
                add(base)
                for a in n.names:
                    add(f"{base}.{a.name}")
    return out


def cached_map(root, blobs: dict[str, str], cache_dir: Path | None) -> dict:
    """{"edges": {file: [imported names]}, "bad": [files that do not parse]} for every file of `blobs` ({path: blob sha}). A file's
    imports are kept in the cache dir's affected-edges.json under its path with the blob sha they were read from; only a file whose blob
    differs (or is new) is parsed again, and a file no longer in the tree drops out of the cache."""
    f = cache_dir / "affected-edges.json" if cache_dir else None
    old: dict = {}
    if f is not None and f.is_file():
        try:
            old = json.loads(f.read_text())
        except ValueError:
            old = {}
    kept: dict = {}
    for path, sha in blobs.items():
        hit = old.get(path)
        if hit and hit[0] == sha:
            kept[path] = hit
            continue
        try:
            kept[path] = [sha, sorted(_imports((Path(root) / path).read_text(encoding="utf-8", errors="replace"), path))]
        except (SyntaxError, ValueError, OSError):
            kept[path] = [sha, None]
    if f is not None and kept != old:
        cache_dir.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(kept))
    return {"edges": {p: v[1] for p, v in kept.items() if v[1] is not None}, "bad": [p for p, v in kept.items() if v[1] is None]}


def whole_reason(changed: list[str], python_path: tuple[str, ...]) -> str:
    """Why the whole suite must run, or '' when every changed path can be placed."""
    for c in changed:
        p = Path(c)
        if p.name in WHOLE_NAMES:
            return f"{c} configures every test"
        if FIXTURE_DIRS & set(p.parts[:-1]):
            return f"{c} is a fixture"
        if p.suffix not in (".py", ".md") and (_is_test_dir(p) or any(c.startswith(r.rstrip("/") + "/") for r in python_path)):
            return f"{c} is data the import scan cannot place"
    return ""


def select(root, changed: list[str], blobs: dict[str, str], cfg_test_globs: tuple, python_path: tuple[str, ...], always: tuple,
           cache_dir: Path | None = None) -> dict:
    """{"whole": reason or '', "tests": [files], "changed_tests": [files], "always": [files]}: the tests this change can affect.
    `blobs` is {path: blob sha} for every Python file of the tree; `changed` is every changed path (a deleted one too: it seeds its names by path)."""
    def is_test(f: str) -> bool:
        return any(fnmatch.fnmatch(Path(f).name, g) for g in cfg_test_globs)

    if why := whole_reason(changed, python_path):
        return {"whole": why, "tests": [], "changed_tests": [], "always": list(always)}
    m = cached_map(root, blobs, cache_dir)
    if bad := [c for c in changed if c in m["bad"]]:
        return {"whole": f"{bad[0]} does not parse, so its importers cannot be placed", "tests": [], "changed_tests": [], "always": list(always)}
    importers: dict[str, list[str]] = {}
    for f, names in m["edges"].items():
        for n in names:
            importers.setdefault(n, []).append(f)
    seen_files: set[str] = set()
    todo = [n for c in changed if c.endswith(".py") for n in module_names(c, python_path)]
    seen_names = set(todo)
    while todo:
        for f in importers.get(todo.pop(), ()):
            if f in seen_files:
                continue
            seen_files.add(f)
            for n in module_names(f, python_path) - seen_names:
                seen_names.add(n)
                todo.append(n)
    changed_tests = [c for c in changed if c.endswith(".py") and is_test(c) and c in m["edges"]]
    tests = sorted({*(f for f in seen_files if is_test(f)), *changed_tests, *(a for a in always if a in m["edges"])})
    return {"whole": "", "tests": tests, "changed_tests": changed_tests, "always": list(always)}
