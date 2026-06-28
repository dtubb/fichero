from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_xcode_registration.py"
_SPEC = importlib.util.spec_from_file_location("check_xcode_registration", _SCRIPT)
assert _SPEC and _SPEC.loader
check_xcode_registration = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_xcode_registration
_SPEC.loader.exec_module(check_xcode_registration)  # type: ignore[attr-defined]


def _write_fake_project(root: Path) -> None:
    project = root / "fichero" / "fichero.xcodeproj" / "project.pbxproj"
    project.parent.mkdir(parents=True)
    project.write_text(
        """
// !$*UTF8*$!
{
	objects = {
		BUILD_A /* A.swift in Sources */ = {isa = PBXBuildFile; fileRef = REF_A /* A.swift */; };
		REF_A /* A.swift */ = {isa = PBXFileReference; path = fichero/A.swift; sourceTree = SOURCE_ROOT; };
		REF_B /* B.swift */ = {isa = PBXFileReference; path = fichero/B.swift; sourceTree = SOURCE_ROOT; };
		PHASE /* Sources */ = {
			isa = PBXSourcesBuildPhase;
			files = (
				BUILD_A /* A.swift in Sources */,
			);
		};
		TARGET /* Fichero */ = {
			isa = PBXNativeTarget;
			name = Fichero;
			buildPhases = (
				PHASE /* Sources */,
			);
		};
	};
}
""",
        encoding="utf-8",
    )


def test_scan_flags_only_unregistered_swift_files(monkeypatch, tmp_path):
    swift_root = tmp_path / "fichero" / "fichero"
    swift_root.mkdir(parents=True)
    (swift_root / "A.swift").write_text("struct A {}\n", encoding="utf-8")
    (swift_root / "B.swift").write_text("struct B {}\n", encoding="utf-8")
    _write_fake_project(tmp_path)

    monkeypatch.setattr(check_xcode_registration, "ROOT", tmp_path)
    monkeypatch.setattr(check_xcode_registration, "SWIFT_ROOT", swift_root)
    monkeypatch.setattr(
        check_xcode_registration,
        "PROJECT_FILE",
        tmp_path / "fichero" / "fichero.xcodeproj" / "project.pbxproj",
    )

    assert check_xcode_registration.scan() == {
        "fichero/fichero/B.swift": ["not in Fichero PBXSourcesBuildPhase"]
    }
