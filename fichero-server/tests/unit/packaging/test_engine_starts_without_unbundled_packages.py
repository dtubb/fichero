"""The engine must start with ONLY the packages the embedded bundle carries.

2026-09-20: the 2026.09.19 DMG's embedded engine exited 250 on launch ("can't
reach server"). `api/routes/kg/sparql.py` gained a top-level `from rdflib import
Graph` (31e1a2f61) while `rdflib` was not in the briefcase `requires`. Every test
passed, because the development environment has rdflib installed.

The bundle holds exactly the briefcase `requires` list and whatever those
packages themselves require. So this test works that set out from pyproject.toml
and the installed metadata, then starts the engine's import in a fresh
interpreter where EVERY OTHER third-party module is unimportable. A module the
engine imports at start that the bundle would not carry fails here, by name,
instead of on a user's machine. (A first version blocked only the names
commented out of the list; it would have missed `networkx`, which was simply
never listed.)
"""

from __future__ import annotations

import importlib.metadata as md
import os
import re
import subprocess
import sys
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

SERVER_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = SERVER_ROOT / "pyproject.toml"

# Importable without being a bundled distribution: interpreter and test plumbing.
_ALWAYS_ALLOWED = {"fichero_server", "_distutils_hack", "pkg_resources", "setuptools", "sitecustomize", "usercustomize"}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _briefcase_requires() -> list[str]:
    text = PYPROJECT.read_text(encoding="utf-8")
    # The app block AND its macOS sub-block (the PyObjC frameworks live there).
    found: list[str] = []
    for header in (r"\[tool\.briefcase\.app\.fichero_server\]", r"\[tool\.briefcase\.app\.fichero_server\.macOS\]"):
        block = re.search(rf"^{header}\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
        assert block, f"briefcase block {header} not found in pyproject.toml"
        requires = re.search(r"^requires = \[\n(.*?)^\]", block.group(1), re.S | re.M)
        assert requires, f"`requires` list not found in {header}"
        found += re.findall(r'^\s*"([^"]+)"', requires.group(1), re.M)
    return found


def _bundled_distributions() -> set[str]:
    """The `requires` list plus everything those distributions require, as installed here."""
    env = default_environment()
    seen: set[str] = set()
    todo = [Requirement(r) for r in _briefcase_requires()]
    while todo:
        req = todo.pop()
        name = _norm(req.name)
        if name in seen or (req.marker is not None and not req.marker.evaluate({**env, "extra": ""})):
            continue
        seen.add(name)
        try:
            deps = md.requires(req.name) or []
        except md.PackageNotFoundError:
            continue  # not installed here (a macOS-only or bundle-only package): nothing to walk
        for dep in deps:
            r = Requirement(dep)
            if r.marker is None or r.marker.evaluate({**env, "extra": ""}):
                todo.append(r)
    return seen


def _bundled_import_names() -> set[str]:
    bundled = _bundled_distributions()
    names: set[str] = set()
    for module, dists in md.packages_distributions().items():
        if any(_norm(d) in bundled for d in dists):
            names.add(module)
    return names


def test_the_bundle_list_is_read_from_pyproject() -> None:
    dists = _bundled_distributions()
    assert {"rdflib", "pykeen", "fastapi", "duckdb"} <= dists, sorted(dists)[:40]
    assert "torch" in dists, "pykeen's own dependencies must be walked"


def test_engine_imports_with_every_unbundled_package_blocked() -> None:
    allowed = sorted(_bundled_import_names() | _ALWAYS_ALLOWED)
    probe = f"""
import importlib.abc, importlib.machinery, sys
ALLOWED = set({allowed!r})
STDLIB = set(sys.stdlib_module_names)
class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        top = name.split('.')[0]
        if top in STDLIB or top in ALLOWED or top.startswith('_'):
            return None
        raise ModuleNotFoundError(f"No module named {{name!r}}: not in the embedded bundle (add its package to the briefcase requires, or import it lazily behind a guard)")
sys.meta_path.insert(0, _Block())
import fichero_server.api.uds_transport  # what the embedded engine imports at start
print("ENGINE IMPORT OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(SERVER_ROOT),
        env={**os.environ, "PYTHONPATH": str(SERVER_ROOT / "src")},
        timeout=600,
    )
    assert result.returncode == 0 and "ENGINE IMPORT OK" in result.stdout, (
        "the engine cannot start with only bundled packages:\n" + result.stderr[-2500:]
    )


def test_every_unguarded_third_party_import_is_bundled() -> None:
    """Start-up is not the only way to crash: a LAZY import inside a function that
    is not wrapped in try/except fails the first time that feature runs. Every
    third-party import in the engine's source must either be a bundled package or
    sit inside a `try` (a deliberate, optional dependency that degrades)."""
    import ast

    bundled = {m.lower() for m in _bundled_import_names() | _ALWAYS_ALLOWED}
    stdlib = set(sys.stdlib_module_names)
    first_party = {"fichero_server", "fichero_cli", "fichero_mcp", "__future__"}
    offenders: list[str] = []
    src = SERVER_ROOT / "src" / "fichero_server"
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            guarded, p = False, node
            while p in parents:
                p = parents[p]
                if isinstance(p, ast.Try):
                    guarded = True
                    break
            for name in names:
                top = name.split(".")[0]
                if top in stdlib or top in first_party or top.lower() in bundled or guarded:
                    continue
                offenders.append(f"{path.relative_to(SERVER_ROOT)}:{node.lineno} imports {top!r}")
    assert not offenders, (
        "unguarded imports of packages the embedded bundle does not carry "
        "(add the package to the briefcase requires, or guard the import):\n  " + "\n  ".join(offenders)
    )
