from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


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
        "fichero/fichero/B.swift": [
            "not in Fichero target (no Sources entry, not under a synchronized root)"
        ]
    }


# ---------------------------------------------------------------------------
# #4512 — the check went BLIND on the real project. NOT the objectVersion-100
# format: the parser reads short numeric ids fine. The #4487 BLIND guard was
# indented INSIDE the target-search loop, so the FIRST PBXNativeTarget whose
# name was not "Fichero" raised SystemExit(2) — which happened the moment
# FicheroIOSTests became the first target in the file. The fixture above could
# never see it (its only target IS Fichero), which is exactly the
# guardrails-must-match-granularity failure: a green test over a blind gate.
# ---------------------------------------------------------------------------

# objectVersion-100-shaped project: short NUMERIC ids (500/510/900) mixed with
# classic hex ids, tab-indented like the real file, and — the regression shape —
# a decoy test target FIRST.
_PBXPROJ_V100 = """\
// !$*UTF8*$!
{
\tarchiveVersion = 1;
\tclasses = {
\t};
\tobjectVersion = 100;
\tobjects = {
\t\t208ADA983022008100B83F96 /* DecoyTests */ = {
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildPhases = (
\t\t\t);
\t\t\tname = DecoyTests;
\t\t\tproductName = DecoyTests;
\t\t};
\t\t500 /* Fichero */ = {
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildPhases = (
\t\t\t\t510 /* Sources */,
\t\t\t);
\t\t\tfileSystemSynchronizedGroups = (
\t\t\t\t900 /* fichero */,
\t\t\t);
\t\t\tname = Fichero;
\t\t\tproductName = Fichero;
\t\t};
\t\t510 /* Sources */ = {
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tfiles = (
\t\t\t);
\t\t};
\t\t900 /* fichero */ = {isa = PBXFileSystemSynchronizedRootGroup; path = fichero; sourceTree = "<group>"; };
\t};
\trootObject = 700;
}
"""

# Same project WITHOUT the synchronized root — nothing registers the sources,
# so any Swift file on disk is an orphan the check must flag.
_PBXPROJ_V100_UNREGISTERED = _PBXPROJ_V100.replace(
    "\t\t\tfileSystemSynchronizedGroups = (\n\t\t\t\t900 /* fichero */,\n\t\t\t);\n",
    "",
)

# No Fichero target anywhere — the genuine #4487 BLIND case must stay exit 2.
_PBXPROJ_V100_NO_TARGET = _PBXPROJ_V100.replace("name = Fichero;", "name = SomethingElse;")


def _v100_project(tmp_path: Path, pbxproj: str, swift_files: list[str]) -> tuple[Path, Path, Path]:
    """Lay out ROOT/fichero/fichero/<files> + ROOT/fichero/fichero.xcodeproj."""
    swift_root = tmp_path / "fichero" / "fichero"
    swift_root.mkdir(parents=True)
    for rel in swift_files:
        target = swift_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// swift\n", encoding="utf-8")
    project_file = tmp_path / "fichero" / "fichero.xcodeproj" / "project.pbxproj"
    project_file.parent.mkdir(parents=True)
    project_file.write_text(pbxproj, encoding="utf-8")
    return project_file, swift_root, tmp_path


def test_v100_passes_when_the_synchronized_root_covers_every_file(tmp_path):
    project_file, swift_root, root = _v100_project(
        tmp_path, _PBXPROJ_V100, ["App.swift", "Views/Deep/Nested.swift"]
    )
    assert check_xcode_registration.scan(project_file, swift_root, root) == {}


def test_v100_flags_an_unregistered_file(tmp_path):
    """The negative fixture: the check must be able to SEE a violation."""
    project_file, swift_root, root = _v100_project(
        tmp_path, _PBXPROJ_V100_UNREGISTERED, ["Orphan.swift"]
    )
    found = check_xcode_registration.scan(project_file, swift_root, root)
    assert list(found) == ["fichero/fichero/Orphan.swift"]


def test_target_after_a_decoy_is_found_not_blind(tmp_path):
    """#4512's exact regression — fails against the pre-fix source."""
    project_file, _, _ = _v100_project(tmp_path, _PBXPROJ_V100, [])
    objects = check_xcode_registration.parse_pbxproj(project_file)
    assert check_xcode_registration.target_sources_phase_ids(objects) == ["510"]


def test_missing_target_is_blind_exit_2(tmp_path):
    """The fail-closed half survives the fix: no Fichero target → exit 2."""
    project_file, _, _ = _v100_project(tmp_path, _PBXPROJ_V100_NO_TARGET, [])
    objects = check_xcode_registration.parse_pbxproj(project_file)
    with pytest.raises(SystemExit) as excinfo:
        check_xcode_registration.target_sources_phase_ids(objects)
    assert excinfo.value.code == 2


def test_numeric_and_hex_ids_both_parse(tmp_path):
    """objectVersion 100 mixes short numeric ids with classic hex ids."""
    project_file, _, _ = _v100_project(tmp_path, _PBXPROJ_V100, [])
    objects = check_xcode_registration.parse_pbxproj(project_file)
    assert objects["500"].isa == "PBXNativeTarget"  # numeric id, block form
    assert objects["208ADA983022008100B83F96"].isa == "PBXNativeTarget"  # hex id
    assert objects["900"].isa == "PBXFileSystemSynchronizedRootGroup"  # inline form
