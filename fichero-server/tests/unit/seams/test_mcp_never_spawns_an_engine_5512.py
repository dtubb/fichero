"""`engine.mcp-never-spawns-a-second-engine` (#5512): the MCP server and the client it uses only ATTACH to a running
engine. Two engines on one DuckDB is the harm; no code path here may launch one.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_spec = importlib.util.spec_from_file_location("_scan_files", ROOT / "scripts" / "_scan_files.py")
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)
FORBIDDEN = {"subprocess", "uvicorn", "fichero_cli.engine_manager", "multiprocessing"}
#: ui_control.py runs `osascript` to drive the app's own panes; it launches no engine.
SUBPROCESS_OK = {"ui_control.py"}
SOURCES = [*sorted(scan_files.scan_rglob(ROOT / "fichero-mcp" / "src", "*.py")), ROOT / "fichero-cli" / "src" / "fichero_cli" / "client.py"]


def _imported(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def test_the_scan_sees_the_sources():
    assert len(SOURCES) > 5 and all(p.exists() for p in SOURCES)


def test_no_mcp_or_client_module_can_launch_an_engine():
    def banned(p: Path) -> set[str]:
        return (_imported(p) & FORBIDDEN) - ({"subprocess"} if p.name in SUBPROCESS_OK else set())

    offenders = {p.name: sorted(banned(p)) for p in SOURCES if banned(p)}
    assert not offenders, offenders


def test_the_scan_would_catch_a_spawner(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("from fichero_cli.engine_manager import start\nimport subprocess\n")
    assert _imported(bad) & FORBIDDEN == {"subprocess", "fichero_cli.engine_manager"}
