"""Moved to `fichero-builder/fichero_builder/policy_hook.py` (dev-workflows Step 1.1). This name stays for the engine's dev-tier
route and the older tests; it is the same module object."""
import importlib
import sys
from pathlib import Path

_BUILDER = str(Path(__file__).resolve().parents[4] / "fichero-builder")
if _BUILDER not in sys.path:
    sys.path.insert(0, _BUILDER)
sys.modules[__name__] = importlib.import_module("fichero_builder.policy_hook")
