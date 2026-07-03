from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_canonical_renderers.py"
_SPEC = importlib.util.spec_from_file_location("check_canonical_renderers", _SCRIPT)
assert _SPEC and _SPEC.loader
check_canonical_renderers = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_canonical_renderers
_SPEC.loader.exec_module(check_canonical_renderers)  # type: ignore[attr-defined]


def test_builder_named_entity_item_is_not_treated_as_swiftui_renderer():
    findings = check_canonical_renderers.scan()
    symbols = {(finding["file"], finding["symbol"]) for finding in findings}

    assert ("Spatial/SpatialScene3D.swift", "makeItemEntity") not in symbols
