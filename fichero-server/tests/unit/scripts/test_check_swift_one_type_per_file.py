"""spec: code-organization — `code-org.naming.swift-file-is-type`, `code-org.naming.swift-views-end-view`,
`code-org.naming.swift-platform-suffix`: `check_swift_one_type_per_file` holds a baseline that may only fall and proves it
sees each kind of finding."""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
_SCRIPT = REPO / "scripts" / "check_swift_one_type_per_file.py"
sys.path.insert(0, str(REPO / "scripts"))
_SPEC = importlib.util.spec_from_file_location("check_swift_one_type_per_file", _SCRIPT)
assert _SPEC and _SPEC.loader
guard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = guard
_SPEC.loader.exec_module(guard)  # type: ignore[attr-defined]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], cwd=REPO, capture_output=True, text=True, timeout=120)


def _findings(rel: str, src: str) -> list[str]:
    return guard.file_findings(rel, guard.analyze(src))


def test_self_test_plants_every_kind_of_finding():
    done = _run("--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_the_real_tree_is_at_or_under_its_baseline():
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


def test_two_public_types_in_one_file_are_a_finding_and_a_private_helper_is_not():
    assert any(f.startswith("one-type") for f in _findings("Models/Pair.swift", "struct Pair {}\nstruct Other {}\n"))
    assert _findings("Models/Pair.swift", "struct Pair {}\nprivate struct Helper {}\n#Preview { Pair() }\n") == []


def test_a_wire_bundle_under_services_is_the_one_allowed_exception():
    src = "struct A {}\nstruct B {}\n"
    assert _findings("Services/Thing/ThingTypes.swift", src) == []
    assert any(f.startswith("one-type") for f in _findings("Models/ThingTypes.swift", src))


def test_a_file_is_named_for_its_type_and_a_topic_file_extends_it():
    assert any(f.startswith("file-name") for f in _findings("Models/Wrong.swift", "struct Other {}\n"))
    assert _findings("Models/Right.swift", "struct Right {}\n") == []
    assert any(f.startswith("file-name") for f in _findings("Models/Thing+Topic.swift", "extension Elsewhere {}\n"))
    assert _findings("Models/Thing+Topic.swift", "extension Thing {}\nprivate struct Extra {}\n") == []


def test_a_view_ends_in_a_shape_word_and_sits_under_views():
    assert any(f.startswith("view-shape") for f in _findings("Views/A/Odd.swift", "struct Odd: View {}\n"))
    assert _findings("Views/A/OddRow.swift", "struct OddRow: View {}\n") == []
    assert any(f.startswith("view-place") for f in _findings("Models/Stray.swift", "struct StrayView: View {}\n"))
    assert _findings("App/Menus/FileCommands.swift", "struct FileCommands: View {}\n") == []
    assert _findings("App/MainScene.swift", "struct MainScene: View {}\n") == []


def test_a_generic_constraint_is_not_a_view_conformance():
    assert _findings("Models/Box.swift", "struct Box<T: View> {}\n") == []


def test_ios_and_macos_suffixes_are_findings_and_the_ruled_spelling_is_not():
    assert any(f.startswith("platform") for f in _findings("Views/A/PaneiOS.swift", "struct PaneiOS {}\n"))
    assert any(f.startswith("platform") for f in _findings("Views/A/Pane.swift", "struct Pane {}\nprivate struct X {}\nstruct PanemacOS {}\n"))
    assert not any(f.startswith("platform") for f in _findings("Views/A/PaneIOS.swift", "struct PaneIOS {}\n"))


def test_comments_and_strings_do_not_declare_types():
    src = '// struct Fake {}\n/* struct Fake2 {} */\nstruct Real {\n let s = "struct Fake3 {} \\(1 + 2) \\"q\\""\n}\n'
    assert _findings("Models/Real.swift", src) == []
    assert guard.analyze('let x = """\nstruct Fake {}\n"""\nstruct Real {}\n').types[0].name == "Real"


def test_a_count_above_the_baseline_fails_and_a_lower_one_does_not():
    found = {"Models/A.swift": ["x", "y"]}
    assert guard.compare(found, {"Models/A.swift": 1})[0] == found
    assert guard.compare(found, {"Models/A.swift": 2})[0] == {}
    assert guard.compare(found, {"Models/A.swift": 3})[1] == ["Models/A.swift"]
    assert guard.compare({"Models/B.swift": ["x"]}, {})[0] == {"Models/B.swift": ["x"]}


def test_a_scratch_tree_with_too_few_files_goes_blind(tmp_path):
    (tmp_path / "A.swift").write_text("struct A {}\n", encoding="utf-8")
    code = ("import sys; sys.path.insert(0, 'scripts'); import check_swift_one_type_per_file as g; "
            f"g.SWIFT_ROOT = g.Path({str(tmp_path)!r}); sys.exit(g.main([]))")
    done = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=60)
    assert done.returncode == 2, done.stdout + done.stderr
