from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_folder_organization.py"
sys.path.insert(0, str(_SCRIPT.parent))
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


def test_list_output_includes_library_reorg_targets(monkeypatch, tmp_path, capsys) -> None:
    swift_root = tmp_path / "fichero" / "fichero"
    library = swift_root / "Views" / "Library"
    library.mkdir(parents=True)
    (library / "LibraryView.swift").write_text("struct LibraryView {}\n", encoding="utf-8")

    monkeypatch.setattr(check_folder_organization, "SWIFT_ROOT", swift_root)

    check_folder_organization.print_list(check_folder_organization.scan())

    output = capsys.readouterr().out
    assert "suggested subfolders: Artifacts/, PDFReading/, QuickLook/" in output


# spec: code-organization — code-org.folders.swift-test-mirror, code-org.folders.swift-view-local-state


def _app(tmp_path, monkeypatch, files: dict[str, str], tests: dict[str, str] | None = None):
    swift_root = tmp_path / "fichero" / "fichero"
    test_root = tmp_path / "fichero" / "Tests" / "Unit"
    for base, group in ((swift_root, files), (test_root, tests or {})):
        for rel, text in group.items():
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
    test_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(check_folder_organization, "SWIFT_ROOT", swift_root)
    monkeypatch.setattr(check_folder_organization, "TEST_ROOT", test_root)


def test_self_test_runs():
    import subprocess

    done = subprocess.run([sys.executable, str(_SCRIPT), "--self-test"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_the_real_tree_exits_zero_with_its_baselines():
    import subprocess

    done = subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_lone_file_folder_under_views_is_a_finding(monkeypatch, tmp_path) -> None:
    _app(tmp_path, monkeypatch, {"Views/Solo/SoloView.swift": "struct SoloView {}\n"})
    assert any("one Swift file" in r for r in check_folder_organization.scan()["Views/Solo"])


def test_a_layer_named_folder_under_views_is_a_finding(monkeypatch, tmp_path) -> None:
    _app(tmp_path, monkeypatch, {"Views/Feature/Helpers/A.swift": "struct A {}\n", "Views/Feature/Helpers/B.swift": "struct B {}\n"})
    assert any("layer" in r for r in check_folder_organization.scan()["Views/Feature/Helpers"])


def test_a_test_folder_with_no_app_folder_is_a_finding(monkeypatch, tmp_path) -> None:
    _app(tmp_path, monkeypatch, {"Views/Real/A.swift": "struct A {}\n", "Views/Real/B.swift": "struct B {}\n"},
         {"general/Views/Real/ATests.swift": "x\n", "general/Views/Ghost/GTests.swift": "x\n"})
    assert check_folder_organization.scan_test_mirror() == {"general/Views/Ghost": 1}


def test_state_read_by_a_second_feature_is_reported_and_own_feature_state_passes(monkeypatch, tmp_path) -> None:
    _app(tmp_path, monkeypatch, {
        "Views/One/OneState.swift": "@Observable final class OneState {}\n",
        "Views/One/OneView.swift": "struct OneView { let s = OneState() }\n",
        "Views/One/OwnState.swift": "final class OwnState: ObservableObject {}\n",
        "Views/Two/TwoView.swift": "struct TwoView { let s = OneState() }\n",
        "App/Cmd.swift": "struct Cmd { let s = OwnState() }\n",
    })
    found = check_folder_organization.scan_shared_state()
    assert set(found) == {"Views/One/OneState.swift::OneState", "Views/One/OwnState.swift::OwnState"}
    assert found["Views/One/OwnState.swift::OwnState"] == "App/Cmd.swift"


def test_a_folder_above_its_baseline_count_fails(monkeypatch, tmp_path) -> None:
    _app(tmp_path, monkeypatch, {f"Views/Big/V{i}.swift": "struct V {}\n" for i in range(5)})
    monkeypatch.setattr(check_folder_organization, "MIXED_CONCERN_DIRS", {"Views/Big": "mixed"})
    monkeypatch.setattr(check_folder_organization, "KNOWN_VIOLATIONS", {"Views/Big": (4, "baseline")})
    assert check_folder_organization.over_baseline(check_folder_organization.scan()) == {"Views/Big": "5 files, baseline 4"}
    monkeypatch.setattr(check_folder_organization, "KNOWN_VIOLATIONS", {"Views/Big": (5, "baseline")})
    assert check_folder_organization.over_baseline(check_folder_organization.scan()) == {}
