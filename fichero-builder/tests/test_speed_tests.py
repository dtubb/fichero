"""speed-tests-1: the unit rung's affected-test selection, the warm DerivedData and its stale-cache retry, the ui rung, and the
Swift tests command. No Mac: a fake runner records what it was asked."""
import hashlib
import json
import subprocess

from fichero_builder import affected, check_tool, journal

GLOBS = ("test_*.py",)
PP = ("pkg/src",)


def _tree(tmp_path, files):
    for name, text in files.items():
        f = tmp_path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    return sorted(files)


def _blobs(root, files):
    return {f: hashlib.sha1((root / f).read_bytes()).hexdigest() for f in files if f.endswith(".py")}


def _select(tmp_path, files, changed, always=()):
    all_py = _tree(tmp_path, files)
    return affected.select(tmp_path, changed, _blobs(tmp_path, all_py), GLOBS, PP, always, tmp_path / "cache")


BASE = {
    "pkg/src/pkg/__init__.py": "",
    "pkg/src/pkg/a.py": "x = 1\n",
    "pkg/src/pkg/b.py": "from pkg import a\n",
    "pkg/src/pkg/c.py": "y = 2\n",
    "pkg/tests/test_a.py": "from pkg.a import x\n",
    "pkg/tests/test_b.py": "import pkg.b\n",
    "pkg/tests/test_c.py": "from pkg import c\n",
    "pkg/tests/test_smoke.py": "def test_x(): pass\n",
}


def test_a_one_file_change_runs_its_importers_direct_and_through_another_module_only(tmp_path):
    sel = _select(tmp_path, BASE, ["pkg/src/pkg/a.py"], always=("pkg/tests/test_smoke.py",))
    assert sel["whole"] == ""
    assert sel["tests"] == ["pkg/tests/test_a.py", "pkg/tests/test_b.py", "pkg/tests/test_smoke.py"]  # b imports a; c and nothing else is left out


def test_a_changed_test_is_in_the_selection_and_a_doc_places_to_no_test(tmp_path):
    sel = _select(tmp_path, BASE, ["pkg/tests/test_c.py", "docs/x.md"])
    assert sel["tests"] == ["pkg/tests/test_c.py"] and sel["changed_tests"] == ["pkg/tests/test_c.py"]


def test_a_deleted_module_still_selects_the_tests_that_import_it(tmp_path):
    files = {k: v for k, v in BASE.items() if k != "pkg/src/pkg/c.py"}
    assert _select(tmp_path, files, ["pkg/src/pkg/c.py"])["tests"] == ["pkg/tests/test_c.py"]


def test_a_conftest_a_fixture_a_config_or_a_data_file_runs_the_whole_suite(tmp_path):
    for changed in ("pkg/tests/conftest.py", "pkg/tests/fixtures/x.json", "pyproject.toml", "pkg/src/pkg/data.json", "pkg/tests/data.csv"):
        assert _select(tmp_path, BASE, [changed])["whole"], changed


def test_a_changed_file_that_does_not_parse_runs_the_whole_suite(tmp_path):
    files = {**BASE, "pkg/src/pkg/a.py": "def (:\n"}
    assert "does not parse" in _select(tmp_path, files, ["pkg/src/pkg/a.py"])["whole"]


def test_only_a_changed_blob_is_parsed_again(tmp_path, monkeypatch):
    files = _tree(tmp_path, BASE)
    cache = tmp_path / "c"
    m1 = affected.cached_map(tmp_path, _blobs(tmp_path, files), cache)
    parsed = []
    real = affected._imports
    monkeypatch.setattr(affected, "_imports", lambda src, path: parsed.append(path) or real(src, path))
    assert affected.cached_map(tmp_path, _blobs(tmp_path, files), cache) == m1 and parsed == [], "same blobs: nothing parsed"
    (tmp_path / "pkg/src/pkg/b.py").write_text("import os\n")
    m2 = affected.cached_map(tmp_path, _blobs(tmp_path, files), cache)
    assert parsed == ["pkg/src/pkg/b.py"] and m2 != m1, "one changed blob: one file parsed"
    gone = {k: v for k, v in _blobs(tmp_path, files).items() if k != "pkg/src/pkg/b.py"}
    affected.cached_map(tmp_path, gone, cache)
    assert "pkg/src/pkg/b.py" not in json.loads((cache / "affected-edges.json").read_text()), "a removed file drops out"


def _git(root, *a):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=a@b", "-c", "user.name=n", *a], check=True, capture_output=True)


def test_the_unit_rung_runs_the_selected_files_and_journals_why(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "state")
    repo = tmp_path / "r"
    _tree(repo, BASE)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "x")
    ran = []
    monkeypatch.setattr(check_tool, "green_runs", lambda tree, files, whole, cfg, t: (ran.append((list(files), whole)),
                        {"ok": True, "stdout_tail": "", "runs": [{"stdout_tail": "3 passed in 1s"}]})[1])
    cfg = check_tool.Config(always_tests=("pkg/tests/test_smoke.py",), python_path=PP, test_globs=GLOBS)
    r = check_tool.unit(repo, ["pkg/src/pkg/a.py"], cfg)
    assert ran == [(["pkg/tests/test_a.py", "pkg/tests/test_b.py", "pkg/tests/test_smoke.py"], ())]
    assert "ran 3 test files, 3 tests passed" in r["stdout_tail"]
    row = [x for x in journal.read() if x.get("state") == "unit-selection"][-1]
    assert row["files"] == 3 and "affected test files" in row["why"]
    ran.clear()
    check_tool.unit(repo, ["pkg/tests/conftest.py"], cfg)
    assert ran[0][0] == ["pkg/tests"] and "whole suite" in [x for x in journal.read() if x.get("state") == "unit-selection"][-1]["why"]


def test_the_unit_rung_is_off_without_always_tests(tmp_path):
    assert check_tool.unit(tmp_path, ["a.py"], check_tool.Config())["skipped"]


# ---- the runner

REAL = "/g"
BUILD = ("xcodebuild", "-scheme", "S", "-derivedDataPath", "x", "build")


class Fake:
    """A fake ssh and run_command. `script` maps a call's number to (exit_code, stdout) for build runs; the default is green."""

    def __init__(self, monkeypatch, tmp_path, outcomes=None, gui=0):
        self.ssh_scripts, self.runs, self.outcomes, self.gui = [], [], list(outcomes or []), gui
        monkeypatch.setattr(journal, "STATE", tmp_path / "state")
        monkeypatch.setattr(check_tool, "_stable_build_tree", lambda root, cfg: str(root))
        monkeypatch.setattr(check_tool, "_ssh", self.ssh)
        monkeypatch.setattr(check_tool, "run_command", self.run)

    def ssh(self, host, script, *a, **k):
        self.ssh_scripts.append(script)
        rc = self.gui if "launchctl" in script else 0
        return type("P", (), {"returncode": rc, "stdout": REAL.encode() if "pwd" in script else b"", "stderr": b""})()

    def run(self, name, argv, *a, **k):
        if name == "build-sync":
            return {"ok": True}
        self.runs.append((name, argv[-1]))
        code, out = self.outcomes.pop(0) if self.outcomes else (0, "")
        return {"ok": code == 0, "exit_code": code, "timed_out": False, "seconds": 1, "stdout_tail": out, "stderr_tail": "", "errors": out if code else ""}


def _cfg(**kw):
    return check_tool.Config(build=BUILD, build_remote="m4:/g", **kw)


def test_a_second_build_reuses_the_same_derived_dir_and_never_a_fresh_one(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path)
    for _ in range(2):
        assert check_tool._remote_build(tmp_path, _cfg(), reuse=False)["ok"]
    assert len(fake.runs) == 2 and all("/g/derived" in s and "derived-" not in s for _n, s in fake.runs)
    assert not any("rm -rf /g/derived" in s for s in fake.ssh_scripts)  # nothing cleared on a green build


def test_a_stale_cache_signature_clears_the_derived_dir_and_retries_once_saying_so(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, [(65, "/x/A.swift:3:8: error: No such module 'Foo'"), (0, "BUILD SUCCEEDED")])
    r = check_tool._remote_build(tmp_path, _cfg(), reuse=False)
    assert r["ok"] and len(fake.runs) == 2
    assert any(s.startswith("rm -rf /g/derived/*") for s in fake.ssh_scripts)
    assert r["results"][0]["retried"] == "clean" and "retried once with /g/derived cleared" in r["results"][0]["stdout_tail"]
    assert any(x.get("state") == "retry" and "stale-cache" in x["detail"] for x in journal.read())


def test_a_stale_cache_that_fails_again_is_red_after_one_retry_only(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, [(65, "PCM mismatch"), (65, "/x/A.swift:3:8: error: PCM mismatch")])
    assert not check_tool._remote_build(tmp_path, _cfg(), reuse=False)["ok"]
    assert len(fake.runs) == 2


def test_the_daily_builds_clear_and_retry_the_same_way(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, [(65, "module 'Foo' not found"), (0, "")])
    r = check_tool._remote_build(tmp_path, _cfg(), BUILD, "ios-sim", reuse=False)
    assert r["ok"] and any(s.startswith("rm -rf /g/derived-ios-sim/*") for s in fake.ssh_scripts)


# ---- the ui rung

def test_the_ui_rung_is_required_only_for_the_segment_editor_swift():
    assert check_tool.ui_required(["fichero/fichero/Views/Preview/X.swift"])
    assert check_tool.ui_required(["fichero/fichero/Models/SegmentStore.swift"])
    assert not check_tool.ui_required(["fichero/fichero/Views/Library/X.swift", "fichero/fichero/Views/Preview/notes.md"])


def test_a_runner_with_no_gui_session_is_not_run_with_its_reason_never_red(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, gui=113)
    r = check_tool.ui(tmp_path, ["fichero/fichero/Views/Preview/X.swift"], _cfg(ui_tests=("FicheroUITests/SegmentEditorUITests",), ui={"enforce": True}))
    assert r["ok"] and r["not_run"] and "no logged-in GUI session" in r["stdout_tail"] and not fake.runs


def test_the_ui_rung_runs_the_filtered_tests_report_only_and_counts_greens(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, [(0, ""), (0, ""), (65, "Test Case 'SegmentEditorUITests.testSplit' failed")])
    cfg = _cfg(ui_tests=("FicheroUITests/SegmentEditorUITests",))
    ch = ["fichero/fichero/Views/Preview/X.swift"]
    assert "(1/3 green" in check_tool.ui(tmp_path, ch, cfg)["stdout_tail"]
    assert "(2/3 green" in check_tool.ui(tmp_path, ch, cfg)["stdout_tail"]
    assert "-only-testing:FicheroUITests/SegmentEditorUITests" in fake.runs[0][1] and " test'" in fake.runs[0][1] + "'"
    red = check_tool.ui(tmp_path, ch, cfg)
    assert red["ok"] and "RED SegmentEditorUITests.testSplit" in red["stdout_tail"]  # report-only: green row, alert journalled
    assert check_tool._ui_greens() == 0  # a red resets the count
    assert check_tool.ui(tmp_path, ["docs/a.md"], cfg)["skipped"]


def test_an_enforcing_ui_rung_is_red_on_a_failed_test(tmp_path, monkeypatch):
    Fake(monkeypatch, tmp_path, [(65, "Test Case 'X.y' failed")])
    assert not check_tool.ui(tmp_path, ["fichero/fichero/Views/Preview/X.swift"], _cfg(ui_tests=("T",), ui={"enforce": True}))["ok"]


# ---- the Swift unit tests command

SWIFT = ("xcodebuild", "-project", "p", "-scheme", "S", "-testPlan", "fichero")


def test_the_swift_tests_build_for_testing_then_test_without_building_in_the_kept_derived_dir(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, [(0, ""), (0, "Executed 42 tests, with 0 failures (0 unexpected) in 3.0")])
    r = check_tool.swift_tests(tmp_path, _cfg(swift_tests=SWIFT))
    assert r["ok"] and "42 tests, 0 failed" in r["stdout_tail"]
    assert all("/g/derived" in s and "derived-" not in s for _n, s in fake.runs)
    assert "build-for-testing" in fake.runs[0][1] and "test-without-building" in fake.runs[1][1] and "-testPlan fichero" in fake.runs[1][1]
    assert any(x.get("state") == "swift-tests" and x["tests"] == 42 for x in journal.read())


def test_a_test_target_that_does_not_compile_is_red_with_the_compiler_errors(tmp_path, monkeypatch):
    fake = Fake(monkeypatch, tmp_path, [(65, "/t/AppTests.swift:9:5: error: missing argument for parameter 'x'")])
    r = check_tool.swift_tests(tmp_path, _cfg(swift_tests=SWIFT))
    assert not r["ok"] and not r.get("not_run") and "does not compile" in r["stdout_tail"] and "AppTests.swift:9:5" in r["stdout_tail"]
    assert len(fake.runs) == 1  # the tests never ran


def test_failing_swift_tests_are_red_naming_them(tmp_path, monkeypatch):
    Fake(monkeypatch, tmp_path, [(0, ""), (65, "Test Case '-[AppTests testA]' failed (0.1 seconds).\nExecuted 5 tests, with 1 failure (0 unexpected)\n** TEST FAILED **")])
    r = check_tool.swift_tests(tmp_path, _cfg(swift_tests=SWIFT))
    assert not r["ok"] and not r.get("not_run") and "-[AppTests testA]" in r["stdout_tail"] and "5 tests, 1 failed" in r["stdout_tail"]


def test_the_swift_tests_never_run_without_a_build_remote(tmp_path, monkeypatch):
    Fake(monkeypatch, tmp_path)
    r = check_tool.swift_tests(tmp_path, check_tool.Config(swift_tests=SWIFT))
    assert r["not_run"] and not r["ok"]


def test_the_config_reads_the_new_keys(tmp_path):
    (tmp_path / "harness.toml").write_text('[check]\nalways_tests = ["a.py"]\nui_tests = ["T"]\nui_runner = "m:/g"\nswift_tests = ["xcodebuild"]\n[check.ui]\nenforce = false\n')
    c = check_tool.load(tmp_path)
    assert (c.always_tests, c.ui_tests, c.ui_runner, c.swift_tests, c.ui) == (("a.py",), ("T",), "m:/g", ("xcodebuild",), {"enforce": False})
