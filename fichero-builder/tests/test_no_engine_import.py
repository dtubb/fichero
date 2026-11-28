"""dev-workflows.core.shared: the Builder imports nothing from the engine, so it runs on any Python with the standard library."""
from __future__ import annotations

import ast
import importlib
import pkgutil
import sys
from pathlib import Path

import fichero_builder

PKG = Path(fichero_builder.__file__).parent


def _imports(path: Path) -> set[str]:
    out = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module.split(".")[0])
    return out


# The one optional dependency (manager 2026-11-28, the owner's DuckDB ruling of 2026-11-16): the console's history index. It is
# imported inside a function only, so the module (and everything else) still imports with the standard library alone.
OPTIONAL = {"history.py": {"duckdb"}}


def _top_level_imports(path: Path) -> set[str]:
    out = set()
    for n in ast.parse(path.read_text()).body:
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            out.add(n.module.split(".")[0])
    return out


def test_no_module_imports_the_engine_or_anything_outside_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    for path in sorted(PKG.glob("*.py")):
        bad = {m for m in _imports(path) if m not in stdlib and m != "fichero_builder"} - OPTIONAL.get(path.name, set())
        assert not bad, f"{path.name} imports {sorted(bad)}"
        assert not (_top_level_imports(path) & OPTIONAL.get(path.name, set())), f"{path.name}: an optional dependency only inside a function"


def test_every_module_imports_without_the_engine_on_the_path():
    assert not any(p.startswith("fichero_server") for p in sys.modules), "the engine is already loaded; this test runs alone"
    for info in pkgutil.iter_modules([str(PKG)]):
        importlib.import_module(f"fichero_builder.{info.name}")
    assert not any(p.startswith("fichero_server") for p in sys.modules)


def test_the_start_path_points_at_hook_scripts_that_exist():
    """The first live run was refused every edit: the hook path had the wrong number of parents after the move."""
    from fichero_builder import start_tool
    assert start_tool._HOOK.is_file() and start_tool._HANDOFF.is_file(), (start_tool._HOOK, start_tool._HANDOFF)
