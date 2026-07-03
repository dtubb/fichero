from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_service_consistency.py"
_SPEC = importlib.util.spec_from_file_location("check_service_consistency", _SCRIPT)
assert _SPEC and _SPEC.loader
check_service_consistency = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_service_consistency
_SPEC.loader.exec_module(check_service_consistency)  # type: ignore[attr-defined]


def test_activity_stream_service_is_sanctioned_sse_transport():
    found = check_service_consistency.scan()

    assert "ActivityStreamService.swift" in found
    assert "ActivityStreamService.swift" in check_service_consistency.SANCTIONED_RAW_TRANSPORT


def test_stale_service_allowlist_entries_are_gone():
    found = check_service_consistency.scan()

    assert "AppleScriptSupport.swift" not in found
    assert "StorageServiceGenerated.swift" not in found
