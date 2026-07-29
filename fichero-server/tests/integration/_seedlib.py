"""Import the scripts-only seeder as a module so tests share one fixture builder.

`seed_test_library.py` lives in `fichero-server/scripts/` (not on PYTHONPATH),
so we load it by path. Both the contract walker and the CLI contract test import
`seed` from here, guaranteeing all three clients (engine, CLI, Swift) validate
against the identical ground-truth library.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SEEDER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed_test_library.py"

_spec = importlib.util.spec_from_file_location("seed_test_library", _SEEDER_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - import wiring
    raise ImportError(f"could not load seeder at {_SEEDER_PATH}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

seed = _module.seed  # (path: Path) -> dict with {path, expected, keys, ids}

__all__ = ["seed"]
