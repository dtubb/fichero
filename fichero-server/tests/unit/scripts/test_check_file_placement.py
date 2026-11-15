"""spec: code-organization — `code-org.enforce.per-batch-placement`: `check_file_placement --since <base>` judges each file
a batch adds or renames, and proves it can see a misplaced one. `code-org.folders.root`, `code-org.folders.python-packages`,
`code-org.folders.python-no-shim-modules`, `code-org.folders.python-test-mirror`, `code-org.naming.python-tests`: the whole-tree
mode (no flag) holds today's debt to a baseline that only shrinks."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[4]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "scripts" / "check_file_placement.py"), *args], cwd=REPO,
                          capture_output=True, text=True, timeout=120)


def test_the_guard_proves_it_sees_one_wrong_file_per_rule():
    done = _run("--self-test")
    assert done.returncode == 0 and "self-test ok" in done.stdout, done.stdout + done.stderr


def test_an_unknown_base_is_blind_not_clean():
    done = _run("--since", "no-such-ref-for-the-test")
    assert done.returncode == 2, done.stdout + done.stderr


def _has_base() -> bool:
    return (REPO / ".git").exists() and subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "origin/integration"], cwd=REPO, capture_output=True).returncode == 0


@pytest.mark.skipif(not _has_base(), reason="no repo or no origin/integration to diff against (a gate copy, a bare clone): the guard goes blind there, by design")
def test_this_branch_places_every_file_it_adds():
    done = _run("--since", "origin/integration")
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="the whole-tree mode lists tracked files with git: a gate copy has none")
def test_the_whole_tree_has_no_misplaced_file_beyond_the_baseline():
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


# --- the Swift rules (spec: code-organization — code-org.enforce.per-batch-placement) -----------------------------------

import importlib.util  # noqa: E402

sys.path.insert(0, str(REPO / "scripts"))
_spec = importlib.util.spec_from_file_location("check_file_placement", REPO / "scripts" / "check_file_placement.py")
assert _spec and _spec.loader
placement = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = placement
_spec.loader.exec_module(placement)  # type: ignore[attr-defined]

_APP = "fichero/fichero/"
_TESTS = "fichero/Tests/Unit/"


class _FakeTree(placement.Tree):
    def __init__(self, files: dict, dirs: set, old_dirs: set):
        super().__init__(REPO, frozenset(), frozenset(), merge_base="base")
        self._files, self._dirs, self._old = files, {d.rstrip("/") for d in dirs}, {d.rstrip("/") for d in old_dirs}

    def text(self, path: str) -> str:
        return self._files[path]

    def has_dir(self, path: str, rev: str = "HEAD") -> bool:
        return path.rstrip("/") in (self._dirs if rev == "HEAD" else self._old)


def _judge(path: str, text: str = "x\n", dirs=(), old=()):
    return dict(placement.judge([path], _FakeTree({path: text}, set(dirs), set(old)))).get(path)


@pytest.mark.parametrize("right, right_text, wrong, wrong_text, fragment", [
    (_APP + "Models/Library/Thing.swift", "struct Thing {}\n", _APP + "Thing.swift", "struct Thing {}\n", "never at the app root"),
    (_APP + "Views/Library/ThingRow.swift", "struct ThingRow: View {}\n", _APP + "Models/Library/ThingRow.swift", "struct ThingRow: View {}\n", "Views/<Feature>/"),
    (_APP + "Models/Library/Thing.swift", "struct Thing {}\n", _APP + "Models/Library/Other.swift", "struct Elsewhere {}\n", "named for its type"),
    (_APP + "Views/Library/ThingRow.swift", "struct ThingRow: View {}\n", _APP + "Views/Library/Thing.swift", "struct Thing: View {}\n", "shape word"),
    (_APP + "Models/Library/PaneIOS.swift", "struct PaneIOS {}\n", _APP + "Models/Library/PaneiOS.swift", "struct PaneiOS {}\n", "IOS / MacOS"),
])
def test_each_swift_app_rule_has_a_right_and_a_wrong_file(right, right_text, wrong, wrong_text, fragment):
    assert _judge(right, right_text) is None
    why = _judge(wrong, wrong_text)
    assert why and fragment in why, why


def test_a_new_swift_test_sits_in_the_mirror_of_an_existing_app_folder_and_ends_tests():
    app = {_APP + "Views/Library"}
    assert _judge(_TESTS + "general/Views/Library/ThingTests.swift", dirs=app) is None
    assert "no app folder" in _judge(_TESTS + "general/Views/Nowhere/ThingTests.swift", dirs=app)
    assert "Tests.swift" in _judge(_TESTS + "general/Views/Library/ThingCheck.swift", dirs=app)
    assert _judge(_TESTS + "general/Views/Nowhere/ThingTests.swift", dirs=app, old={_TESTS + "general/Views/Nowhere"}) is None
    assert _judge(_TESTS + "general/TestFixtures.swift") is None


def test_an_app_scene_or_window_may_sit_in_app_and_other_app_views_may_not():
    assert _judge(_APP + "App/MainScene.swift", "struct MainScene: View {}\n") is None
    assert _judge(_APP + "App/Menus/FileCommands.swift", "struct FileCommands: View {}\n") is None
    assert "Views/<Feature>/" in _judge(_APP + "App/SettingsRow.swift", "struct SettingsRow: View {}\n")
