from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_folder_organization.py"
_SPEC = importlib.util.spec_from_file_location("check_folder_organization", _SCRIPT)
assert _SPEC and _SPEC.loader
check_folder_organization = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_folder_organization
_SPEC.loader.exec_module(check_folder_organization)  # type: ignore[attr-defined]


def test_scan_flags_known_mixed_library_directory(monkeypatch, tmp_path) -> None:
    swift_root = tmp_path / "fichero" / "fichero"
    library = swift_root / "Views" / "Library"
    library.mkdir(parents=True)
    (library / "LibraryView.swift").write_text("struct LibraryView {}\n", encoding="utf-8")

    monkeypatch.setattr(check_folder_organization, "SWIFT_ROOT", swift_root)

    found = check_folder_organization.scan()

    assert "Views/Library" in found
    assert any("mixes browser" in reason for reason in found["Views/Library"])


def test_scan_flags_new_directory_over_direct_file_limit(monkeypatch, tmp_path) -> None:
    swift_root = tmp_path / "fichero" / "fichero"
    crowded = swift_root / "Views" / "Crowded"
    crowded.mkdir(parents=True)
    for index in range(check_folder_organization.MAX_DIRECT_SWIFT_FILES + 1):
        (crowded / f"View{index}.swift").write_text("struct View {}\n", encoding="utf-8")

    monkeypatch.setattr(check_folder_organization, "SWIFT_ROOT", swift_root)

    found = check_folder_organization.scan()

    assert found == {
        "Views/Crowded": [
            "19 Swift files directly in one directory (limit: 18)"
        ]
    }
