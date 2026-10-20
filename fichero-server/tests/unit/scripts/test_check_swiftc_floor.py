"""scripts/check_swiftc_floor.py (#5730, platform.27-only-api-gated): a helper compiled by a bare `swiftc` is built for
the host's OS, where a 27-only API compiles unflagged and then fails on a 26 Mac."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_swiftc_floor.py"
_SPEC = importlib.util.spec_from_file_location("check_swiftc_floor", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]


def _tree(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / "fichero-server" / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return tmp_path


def test_the_real_tree_passes() -> None:
    assert _mod.scan() == []


def test_a_bare_swiftc_on_the_bridge_is_caught(tmp_path: Path) -> None:
    root = _tree(tmp_path, "build.sh", "swiftc -O -parse-as-library -o fm-bridge FmBridge.swift\n")
    assert len(_mod.scan(root)) == 1


def test_a_continued_swiftc_without_the_target_is_caught(tmp_path: Path) -> None:
    root = _tree(tmp_path, "build.sh", "swiftc -O -parse-as-library \\\n  -o out/fm-bridge \\\n  FmBridge.swift\n")
    assert len(_mod.scan(root)) == 1


def test_a_swiftc_that_names_the_floor_passes_even_across_lines(tmp_path: Path) -> None:
    root = _tree(tmp_path, "build.sh",
                 "swiftc -O -parse-as-library -target arm64-apple-macos26.0 \\\n  -o out/fm-bridge FmBridge.swift\n")
    assert _mod.scan(root) == []


def test_looking_for_swiftc_is_not_building_with_it(tmp_path: Path) -> None:
    root = _tree(tmp_path, "build.sh", 'if ! command -v swiftc >/dev/null 2>&1; then echo "no fm-bridge"; fi\n# swiftc fm-bridge\n')
    assert _mod.scan(root) == []
