"""#5745: PyObjC resolves Quartz names lazily and not thread-safely, so the first page read on
parallel threads died with a bare KeyError('CGImageGetWidth'). Importing the engine's Quartz
users resolves every name they use up front, on the importing thread."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("Quartz")

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_SCAN = Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py"
_spec = importlib.util.spec_from_file_location("_scan_files", _SCAN)
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)

CODE = """
import sys; sys.path[:0] = {paths!r}
import Quartz
import fichero_server.media.quartz_warm as w
missing = [n for n in w.NAMES if n not in vars(Quartz) and hasattr(Quartz, n)]  # a name this macOS lacks is not ours to resolve
print("MISSING", missing)
"""


def test_every_quartz_name_is_resolved_on_import():
    out = subprocess.run([sys.executable, "-I", "-c", CODE.format(paths=sys.path)], capture_output=True, text=True,
                         check=True).stdout
    assert "MISSING []" in out, out


def test_names_cover_every_quartz_name_the_code_uses():
    import ast
    import pathlib

    import fichero_server
    from fichero_server.media import quartz_warm

    used = set()
    for path in scan_files.scan_rglob(pathlib.Path(fichero_server.__file__).parent, "*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module == "Quartz":
                used |= {a.name for a in node.names}
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "Quartz":
                used.add(node.attr)
    assert used - set(quartz_warm.NAMES) == set()
