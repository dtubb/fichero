"""local.github.watch over a faked gh and App Store Connect, from 2026-11-25's real outputs: Tests run 45676804358 (engine shards
red), Security run 45667437823 ("not acquired by Runner"), Xcode Cloud build 3 (Test - macOS failed to launch the test runner)."""
from __future__ import annotations

import json
import subprocess

import pytest

from fichero_builder import gh_watch, journal, queue

TOML = ('[land]\nbranch = "integration"\n[github_watch]\nenabled = true\nrelease_branch = "main"\nxcode_workflow = "759A643E-0866-433E-81D2-33E89E021A1E"\n'
        'asc_key_id = "K"\nasc_issuer_id = "I"\nasc_key_path = "~/k.p8"\n')
TESTS_RUN = {"databaseId": 45676804358, "status": "completed", "conclusion": "success", "headSha": "a40008b70825b0faf7f0b11a5ae4e47e6b512313",
             "createdAt": "2026-11-25T18:36:01Z"}
TESTS_JOBS = [{"databaseId": 139426614850, "name": "Swift build and unit tests", "conclusion": "success"},
              {"databaseId": 139426614975, "name": "engine (1/8)", "conclusion": "failure"},
              {"databaseId": 139426615166, "name": "Builder's own suite", "conclusion": "success"}]
LOG_1_8 = """engine (1/8)\tUNKNOWN STEP\t2026-11-25T19:00:29.3694077Z __________ ERROR at teardown of TestDatabaseBasics.test_default_path ___________
engine (1/8)\tUNKNOWN STEP\t2026-11-25T19:00:29.3826453Z ERROR    fichero_server.workflows.tools.vision_base:vision_base.py:2625 Could not enumerate Vision recognition locales: No module named 'Vision'
engine (1/8)\tUNKNOWN STEP\t2026-11-25T19:00:30.3527157Z FAILED tests/unit/db/test_db.py::TestDatabaseBasics::test_default_path - AssertionError: tests/unit/db/test_db.py::TestDatabaseBasics::test_default_path: makes a directory at /home/runner/Library/Applicati
engine (1/8)\tUNKNOWN STEP\t2026-11-25T19:00:30.3540943Z FAILED tests/unit/recipes/test_page_crop_writes_page_region.py::test_a_page_prepared_from_the_same_file_is_not_found_again_on_the_next_run - assert 0 == 1
"""
SEC_RUN = {"databaseId": 45667437823, "status": "completed", "conclusion": "failure", "headSha": "0c14878050074c4b6eebd71f93dd5a19ef76c3e2",
           "createdAt": "2026-11-25T17:41:40Z"}
SEC_JOBS = [{"databaseId": 139393300540, "name": "scanners", "conclusion": "cancelled"},
            {"databaseId": 139393301166, "name": "codeql (python, ubuntu-latest, none)", "conclusion": "success"}]
SEC_NOTES = [{"annotation_level": "failure", "message": "The job was not acquired by Runner of type hosted even after multiple attempts"},
             {"annotation_level": "notice", "message": "Due to capacity constraints, jobs targeting macOS arm64 runners may experience longer queue times."}]
XC = {
    "/v1/ciWorkflows/759A643E-0866-433E-81D2-33E89E021A1E/buildRuns?limit=1&sort=-number&fields[ciBuildRuns]=number,executionProgress,completionStatus":
        {"data": [{"id": "cbff3b1d-e011-4d4c-8ea0-acef82453ab7", "attributes": {"number": 3, "executionProgress": "COMPLETE", "completionStatus": "FAILED"}}]},
    "/v1/ciBuildRuns/cbff3b1d-e011-4d4c-8ea0-acef82453ab7/actions?fields[ciBuildActions]=name,completionStatus":
        {"data": [{"id": "2994a1d2-2b5d-499a-9021-d4fd01b47c04", "attributes": {"name": "Test - macOS", "completionStatus": "FAILED"}},
                  {"id": "0de3e664-7205-49c2-9484-1bf8c134dbc6", "attributes": {"name": "Build - iOS", "completionStatus": "SUCCEEDED"}}]},
    "/v1/ciBuildActions/2994a1d2-2b5d-499a-9021-d4fd01b47c04/issues?limit=20":
        {"data": [{"attributes": {"issueType": "ERROR", "message": "Fichero encountered an error (Failed to install or launch the test runner. "
                                  "(Underlying Error: Could not launch “FicheroTests”. Runningboard has returned error 5."}},
                  {"attributes": {"issueType": "WARNING", "message": "Conditional cast from 'any Error' to 'NSError' always succeeds"}},
                  {"attributes": {"issueType": "ERROR", "message": "Could not launch “Fichero”"}}]},
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    (tmp_path / "s").mkdir()
    (tmp_path / "harness.toml").write_text(TOML)
    return tmp_path


def world(root, tests_run=TESTS_RUN, tests_jobs=TESTS_JOBS, xc=XC, texts=None, extra_runs=()):
    def run(argv, **k):
        a = argv[1:]
        out = None
        if a[:2] == ["run", "list"] and "--workflow" in a:
            out = [*extra_runs, tests_run] if a[a.index("--workflow") + 1] == "Tests" else [SEC_RUN]
        elif a[:2] == ["run", "list"]:
            out = [{"databaseId": 1, "workflowName": "Tests"}, {"databaseId": 2, "workflowName": "Security"}]
        elif a[:2] == ["run", "view"] and "--log-failed" in a:
            return subprocess.CompletedProcess(argv, 0, LOG_1_8, "")
        elif a[:2] == ["run", "view"]:
            out = {"jobs": tests_jobs if a[2] == str(tests_run["databaseId"]) else SEC_JOBS}
        elif a[0] == "api":
            out = SEC_NOTES
        return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")
    return gh_watch.World(root, gh_watch.load(root), run=run, asc=xc.__getitem__, text=(texts.append if texts is not None else None))


def alerts():
    answered = {r["id"] for r in journal.read() if r["event"] == "alert-answer"}
    return [r["what"] for r in journal.read() if r["event"] == "alert" and r["id"] not in answered]


def test_one_pass_raises_one_alert_per_failed_job_with_its_tests_capacity_and_xcode_issues(root):
    texts = []
    assert gh_watch.main_run(root, world=world(root, texts=texts), out=lambda s: None) == 0
    got = alerts()
    assert len(got) == 3
    tests = next(a for a in got if a.startswith("Tests job 'engine (1/8)'"))
    assert "at a40008b70: 2 test(s): test_default_path, test_a_page_prepared_from_the_same_file_is_not_found_again_on_the_next_run" in tests
    sec = next(a for a in got if a.startswith("Security job 'scanners'"))
    assert "GitHub capacity, not our code" in sec
    xc = next(a for a in got if a.startswith("Xcode Cloud build 3 'Test - macOS' failed"))
    assert "Failed to install or launch the test runner" in xc and "Conditional cast" not in xc, "a warning is not why it failed"
    assert texts == [], "no alert named a release or TestFlight build: no owner text"
    info = [r for r in journal.read() if r["event"] == "gh-watch" and r.get("state") == "info"]
    assert len(info) == 1 and "2 red run(s) on main, expected until the next release" in info[0]["detail"]


def test_a_second_pass_on_the_same_heads_says_nothing_and_a_later_green_run_clears_the_alert(root):
    gh_watch.main_run(root, world=world(root), out=lambda s: None)
    gh_watch.main_run(root, world=world(root), out=lambda s: None)
    assert len(alerts()) == 3, "deduped per (workflow, job, head)"
    assert len([r for r in journal.read() if r["event"] == "gh-watch" and r.get("state") == "info"]) == 1, "the release branch: once a day"
    green = {**TESTS_RUN, "databaseId": 45690000000, "headSha": "b" * 40}
    gh_watch.main_run(root, world=world(root, tests_run=green, tests_jobs=[{**j, "conclusion": "success"} for j in TESTS_JOBS]), out=lambda s: None)
    assert not [a for a in alerts() if a.startswith("Tests job")] and len(alerts()) == 2


def test_a_cancelled_newest_run_is_skipped_and_a_run_going_past_the_limit_is_stuck(root):
    cancelled = {**TESTS_RUN, "databaseId": 9, "conclusion": "cancelled"}
    stuck = {"databaseId": 8, "status": "in_progress", "conclusion": "", "headSha": "c" * 40, "createdAt": "2026-11-25T10:00:00Z"}
    gh_watch.main_run(root, world=world(root, extra_runs=(stuck, cancelled)), out=lambda s: None)
    assert any(a.startswith("Tests job 'engine (1/8)' failed at a40008b70") for a in alerts()), "the cancelled run is skipped"
    assert any(a.startswith("Tests run 8 on integration has run") and "stuck" in a for a in alerts())


def test_a_failed_jobs_log_that_github_drops_still_alerts_and_the_other_parts_run(root):
    """Live pass 2026-11-25: `gh run view --log-failed` got "connection reset" and the rest of the Tests part was lost."""
    w = world(root)
    real = w._run

    def dropped(argv, **k):
        if "--log-failed" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "failed to get job: read: connection reset by peer")
        return real(argv, **k)
    w._run = dropped
    gh_watch.main_run(root, world=w, out=lambda s: None)
    assert any(a.startswith("Tests job 'engine (1/8)' failed at a40008b70 (no pytest FAILED/ERROR line") for a in alerts())
    assert len(alerts()) == 3


def test_an_alert_naming_a_testflight_build_texts_the_owner(root):
    texts = []
    xc = {**XC}
    key = "/v1/ciBuildRuns/cbff3b1d-e011-4d4c-8ea0-acef82453ab7/actions?fields[ciBuildActions]=name,completionStatus"
    xc[key] = {"data": [{"id": "2994a1d2-2b5d-499a-9021-d4fd01b47c04", "attributes": {"name": "Archive - TestFlight", "completionStatus": "FAILED"}}]}
    gh_watch.main_run(root, world=world(root, xc=xc, texts=texts), out=lambda s: None)
    assert len(texts) == 1 and texts[0].startswith("Xcode Cloud build 3 'Archive - TestFlight' failed")


def test_the_loop_job_is_off_without_github_watch_and_runs_every_n_seconds_when_on(root, monkeypatch):
    assert queue.gh_watch_job(root.parent / "none")[0] is None
    ran = []
    procs = queue.Procs(start=None, alive=None, send=None, rebase=None, row=None, chain=None, landed=None, end_of=None, stop=None,
                        gh_watch=lambda: ran.append(1) or 0, gh_watch_s=600)
    clock = [1000.0]
    monkeypatch.setattr(queue.time, "time", lambda: clock[0])
    for t in (1000.0, 1300.0, 1601.0):
        clock[0] = t
        queue.gh_watch_when_due(procs, None)
    assert ran == [1, 1]


def test_an_es256_der_signature_becomes_the_64_byte_jwt_form():
    der = bytes([0x30, 0x45, 0x02, 0x21, 0x00]) + b"\x81" * 32 + bytes([0x02, 0x20]) + b"\x02" * 32
    assert gh_watch._der_to_raw(der) == b"\x81" * 32 + b"\x02" * 32
