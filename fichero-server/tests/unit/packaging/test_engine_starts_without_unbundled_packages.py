"""The engine must start with ONLY the packages the embedded bundle carries.

2026-09-20: the 2026.09.19 DMG's embedded engine exited 250 on launch ("can't
reach server"). `api/routes/kg/sparql.py` gained a top-level `from rdflib import
Graph` (31e1a2f61) while `rdflib` was commented out of the briefcase `requires`.
Every test passed, because the development environment has rdflib installed.

This test starts the engine's import in a fresh interpreter with every package
that is DELIBERATELY left out of the bundle (the commented-out names in the
briefcase `requires` block) made unimportable. If a module the engine imports at
start needs one of them, this fails here instead of on a user's machine.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = SERVER_ROOT / "pyproject.toml"

# A distribution name is not always its import name.
_IMPORT_NAMES = {"opencv-python-headless": "cv2", "pymupdf": "fitz", "pillow": "PIL"}


def _excluded_import_names() -> list[str]:
    text = PYPROJECT.read_text(encoding="utf-8")
    block = re.search(
        r"^\[tool\.briefcase\.app\.fichero_server\]\n(.*?)^\[", text, re.S | re.M
    )
    assert block, "briefcase app block not found in pyproject.toml"
    requires = re.search(r"^requires = \[\n(.*?)^\]", block.group(1), re.S | re.M)
    assert requires, "briefcase `requires` list not found"
    names = re.findall(r'^\s*#\s*"([A-Za-z0-9_.\-]+)', requires.group(1), re.M)
    return sorted({_IMPORT_NAMES.get(n.lower(), n.replace("-", "_")) for n in names})


def test_the_excluded_list_is_read_from_pyproject() -> None:
    excluded = _excluded_import_names()
    assert "pykeen" in excluded, excluded  # the one deliberate exclusion today
    assert "rdflib" not in excluded, "rdflib must be bundled: the SPARQL route imports it at start"


def test_engine_imports_with_every_unbundled_package_blocked() -> None:
    excluded = _excluded_import_names()
    probe = f"""
import importlib.abc, sys
BLOCKED = {excluded!r}
class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in BLOCKED:
            raise ModuleNotFoundError(f"No module named {{name!r}} (not in the embedded bundle)")
        return None
sys.meta_path.insert(0, _Block())
import fichero_server.api.uds_transport  # what the embedded engine imports at start
print("ENGINE IMPORT OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(SERVER_ROOT),
        env={**__import__("os").environ, "PYTHONPATH": str(SERVER_ROOT / "src")},
        timeout=300,
    )
    assert result.returncode == 0 and "ENGINE IMPORT OK" in result.stdout, (
        "the engine cannot start with only bundled packages:\n" + result.stderr[-2000:]
    )
