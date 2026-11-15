"""The issue/spec reconcile's pure decision logic (parse, classify, TSV round trip) is self-checking."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "issue_spec_reconcile.py"


def _load():
    spec = importlib.util.spec_from_file_location("issue_spec_reconcile", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_self_test_passes():
    assert _load().self_test() == 0
