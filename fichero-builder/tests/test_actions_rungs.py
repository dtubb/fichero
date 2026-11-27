"""Spec: docs/contributor_manual/specs/harness/github-ci.md (ci.builder-reads-actions, ci.actions-or-local). A fake `gh` and a local bare origin."""
import json
import subprocess

import pytest

from fichero_builder import actions, check_tool, journal

SHA_OTHER = "0" * 40


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    r = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "lane-x", str(r)], check=True)
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "c")
    _git(r, "remote", "add", "origin", str(origin))
    monkeypatch.setattr(journal, "path", lambda: tmp_path / "journal.jsonl")
    monkeypatch.setattr(actions, "POLL_S", 0)
    actions.reset()
    return r


def fake_gh(tmp_path, monkeypatch, head, runs, steps=None, fail=False, shards=12, per_shard=None):
    """`runs`: what `gh run list` prints (headSha "HEAD" = the batch head); `steps`: {step name: conclusion} on each of the `shards`
    jobs named as tests.yml names them, `engine (N/12)`, plus a contracts job; `per_shard`: {N: {step: conclusion}} overrides."""
    runs = [{**r, "headSha": head if r.get("headSha") == "HEAD" else r.get("headSha")} for r in runs]
    steps = steps or {}
    jobs = [{"name": f"engine ({n}/12)", "steps": [{"name": k, "conclusion": v} for k, v in {**steps, **(per_shard or {}).get(n, {})}.items()]}
            for n in range(1, shards + 1)]
    jobs.append({"name": "contracts", "steps": [{"name": "Unit tests", "conclusion": "failure"}]})
    script = tmp_path / "gh"
    script.write_text("#!/usr/bin/env python3\nimport sys, json\na = sys.argv[1:]\n"
                      f"if {fail!r}: sys.stderr.write('no network'); sys.exit(4)\n"
                      f"if a[0] == 'run' and a[1] == 'list': print(json.dumps({runs!r}))\n"
                      f"elif a[0] == 'api': print(json.dumps({{'jobs': {jobs!r}}}))\n"
                      "elif a[:2] == ['run', 'view']: print('FAILED tests/unit/test_x.py::test_y\\nE assert 1 == 2')\n")
    script.chmod(0o755)
    monkeypatch.setattr(actions, "GH", str(script))


def cfg(**kw):
    return check_tool.Config(actions=("unit",), always_tests=("tests/smoke.py",), actions_timeout_s=0.2, **kw)


GREEN = {"Unit tests": "success"}
RUN = {"databaseId": 7, "status": "completed", "conclusion": "success", "headSha": "HEAD"}


CLEAN = {"ok": True, "skipped": False, "gitleaks_clean": True, "stdout_tail": "no new finding"}


def _fa(repo, head, c, local, scan=CLEAN):
    """from_actions over the empty range head..head with a security row; the push-gate tests pass their own."""
    pin = repo.parent / "pin0"
    pin.mkdir(exist_ok=True)
    (pin / "harness.toml").write_text("[land]\nbranch = 'main'\n")
    return check_tool.from_actions("unit", repo, head, c, local, pin, head, scan)


def _pin(repo):
    pin = repo.parent / "pin0"
    pin.mkdir(exist_ok=True)
    (pin / "harness.toml").write_text("[land]\nbranch = 'main'\n")
    return pin


def _local(ran):
    return lambda: (ran.append(1), {"ok": True, "stdout_tail": "local"})[1]


def test_a_green_run_of_the_head_supplies_the_unit_rung_and_the_row_names_the_run(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    u = _fa(repo, head, cfg(), _local(ran))
    assert u["ok"] and not ran
    assert "from GitHub run 7" in u["stdout_tail"]
    assert _git(tmp_path / "origin.git", "rev-parse", "refs/heads/lane-x") == head, "the head was pushed to the lane's branch"


def test_a_red_unit_step_is_the_rungs_red_with_the_failing_lines(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], {"Unit tests": "failure"})
    u = _fa(repo, head, cfg(), _local([]))
    assert not u["ok"] and "assert 1 == 2" in u["stderr_tail"]


def test_one_red_shard_is_red_whatever_the_last_shard_says(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN, per_shard={3: {"Unit tests": "failure"}})
    u = _fa(repo, head, cfg(), _local([]))
    assert not u["ok"] and "failure" in u["stdout_tail"]


def test_fewer_than_twelve_shards_is_no_usable_run(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN, shards=11)
    ran = []
    _fa(repo, head, cfg(), _local(ran))
    assert ran == [1]
    assert "11" in (tmp_path / "journal.jsonl").read_text()


def test_the_jobs_tests_yml_really_names_are_read(repo, tmp_path, monkeypatch):
    """The workflow's job name is `engine (N/12)`; a guard on the file keeps the fake and the workflow together."""
    import pathlib
    wf = (pathlib.Path(__file__).resolve().parents[2] / ".github/workflows/tests.yml").read_text()
    assert "name: engine (${{ matrix.shard }}/12)" in wf and actions.SHARDS == 12


def test_the_guards_rung_never_reads_actions(repo, tmp_path, monkeypatch):
    assert "guards" not in actions.STEPS


def test_no_run_in_time_runs_the_rung_locally_with_one_journal_row(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [])
    ran = []
    r = _fa(repo, head, cfg(), _local(ran))
    assert r["stdout_tail"] == "local" and len(ran) == 1
    rows = [json.loads(x) for x in (tmp_path / "journal.jsonl").read_text().splitlines()]
    why = [x for x in rows if x.get("state") == "actions-local" and x["rung"] == "unit"]
    assert len(why) == 1 and "no finished Actions run" in why[0]["reason"]


def test_a_run_for_another_sha_is_refused(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [{**RUN, "headSha": SHA_OTHER}], GREEN)
    ran = []
    _fa(repo, head, cfg(), _local(ran))
    assert ran == [1]


def test_a_run_still_in_progress_is_not_a_pass(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [{**RUN, "status": "in_progress", "conclusion": None}], GREEN)
    ran = []
    _fa(repo, head, cfg(), _local(ran))
    assert ran == [1]


def test_a_gh_that_fails_runs_locally_with_the_reason(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [], fail=True)
    ran = []
    _fa(repo, head, cfg(), _local(ran))
    assert ran == [1]
    assert "no network" in (tmp_path / "journal.jsonl").read_text()


def test_a_rung_not_listed_in_actions_runs_locally_and_pushes_nothing(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    _fa(repo, head, check_tool.Config(actions=()), _local(ran))
    assert ran == [1]
    assert subprocess.run(["git", "-C", str(tmp_path / "origin.git"), "rev-parse", "-q", "--verify", "refs/heads/lane-x"], capture_output=True).returncode


def test_a_batch_not_on_a_lane_branch_runs_locally(repo, tmp_path, monkeypatch):
    _git(repo, "checkout", "-q", "-b", "other")
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    _fa(repo, head, cfg(), _local(ran))
    assert ran == [1]



def _origin_has(tmp_path, head):
    r = subprocess.run(["git", "-C", str(tmp_path / "origin.git"), "cat-file", "-e", head], capture_output=True)
    return r.returncode == 0


@pytest.mark.parametrize("scan", [
    {"ok": True, "gitleaks_clean": False, "stdout_tail": "gitleaks generic-api-key x"},   # report-only, gitleaks red
    {"ok": True, "skipped": True, "stdout_tail": "not required: no changed path is under a scanned directory"},
    {"ok": True, "not_run": True, "stdout_tail": "not-run: runner down"},
    {"ok": True, "stdout_tail": "ran but says nothing about gitleaks"},
    None,
], ids=["gitleaks-red-report-only", "skipped-not-required", "not-run", "no-gitleaks-verdict", "no-row"])
def test_the_head_is_not_pushed_without_a_clean_gitleaks_scan_whatever_enforce_says(repo, tmp_path, monkeypatch, scan):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    _fa(repo, head, cfg(), _local(ran), scan)
    assert ran == [1], "the rung ran locally"
    assert not _origin_has(tmp_path, head), "the bare origin never got the head"
    assert "not pushed" in (tmp_path / "journal.jsonl").read_text()


def test_a_boundary_hit_in_the_batch_is_not_pushed(repo, tmp_path, monkeypatch):
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "f.txt").write_text("token = ghp_" + "a" * 24 + "\n")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add")
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    check_tool.from_actions("unit", repo, head, cfg(), _local(ran), _pin(repo), base, CLEAN)
    assert ran == [1] and not _origin_has(tmp_path, head)
    assert "boundary" in (tmp_path / "journal.jsonl").read_text()


def test_a_lanes_edited_harness_toml_cannot_loosen_the_boundary_patterns(repo, tmp_path, monkeypatch):
    """The patterns come from the pinned copy: the lane's own harness.toml with an emptied-out pattern list changes nothing."""
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "harness.toml").write_text('[land]\nboundary = ["never-matches-anything-xyz"]\n')
    (repo / "f.txt").write_text("token = ghp_" + "a" * 24 + "\n")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add")
    head = _git(repo, "rev-parse", "HEAD")
    pinned = tmp_path / "pinned"
    pinned.mkdir()
    (pinned / "harness.toml").write_text("[land]\nbranch = 'main'\n")  # no boundary key: the default patterns
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    check_tool.from_actions("unit", repo, head, cfg(), _local(ran), pinned, base, CLEAN)
    assert ran == [1] and not _origin_has(tmp_path, head)
    assert "boundary" in (tmp_path / "journal.jsonl").read_text()


def test_an_unreadable_pinned_harness_toml_blocks_the_push(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    check_tool.from_actions("unit", repo, head, cfg(), _local(ran), tmp_path / "nowhere", head, CLEAN)
    assert ran == [1] and not _origin_has(tmp_path, head)


def test_a_unit_rung_the_local_run_skips_is_not_turned_on_by_actions(repo, tmp_path, monkeypatch):
    head = _git(repo, "rev-parse", "HEAD")
    fake_gh(tmp_path, monkeypatch, head, [RUN], GREEN)
    ran = []
    c = check_tool.Config(actions=("unit",), actions_timeout_s=0.2)
    check_tool.from_actions("unit", repo, head, c, _local(ran), _pin(repo), head, CLEAN)
    assert ran == [1] and not _origin_has(tmp_path, head), "no always_tests: local() answers and nothing is pushed"
