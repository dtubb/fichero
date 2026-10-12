"""`scripts/realrun_check.py` reads a recorded run and fails each check the operator made by hand when, and only
when, the run shows the defect; it refuses a project outside ~/Fichero Dev Test, and a dry run writes nothing.

No engine: the run is a recorded JSON fixture, and the CLI is a stand-in that answers from it.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fichero-server/tests/fixtures/realrun/caciques_run.json"


def _script():
    spec = importlib.util.spec_from_file_location("realrun_check", ROOT / "scripts/realrun_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rc = _script()


def _run() -> dict:
    return json.loads(FIXTURE.read_text())


def _verdicts(evidence: dict) -> dict[str, str]:
    rows, _ = rc.table(evidence)
    return {name: verdict for name, verdict, _ in rows}


def _verdict(evidence: dict, starts: str) -> str:
    return next(v for name, v in _verdicts(evidence).items() if name.startswith(starts))


def test_the_recorded_good_run_passes_every_check():
    rows, ok = rc.table(_run())
    assert ok, rows
    assert [v for _, v, _ in rows].count(rc.FAIL) == 0
    assert len(rows) == 11


def _names(ev: dict) -> dict:
    return next(s for s in ev["status"]["steps"] if s["job"] == "find-names-tag-words")


@pytest.mark.parametrize("starts, break_it", [
    ("natural page order", lambda ev: ev["folders"]["CACIQUES_INDIOS,17,D.5"].insert(
        0, "CACIQUES_INDIOS,17,D.5_0010.jpg")),
    ("blank sheets", lambda ev: ev["status"]["steps"][0]["left_out"][0].update(why="left out")),
    ("blank sheets", lambda ev: ev["status"]["steps"][0].update(blank_versos=3)),
    ("no written page", lambda ev: ev["texts"].update(p6="En la ciudad de los Reyes")),
    ("counts add up", lambda ev: ev["status"]["steps"][0]["account"].update(pages_done=2)),
    ("counts add up", lambda ev: ev["summary"].update(pages=9)),
    ("progress says", lambda ev: ev["seen"][1].update(reason="Running step find-lines, read-a-line: 0 of 1 folder")),
    ("progress says", lambda ev: ev["seen"][1].update(reason="Reading the lines with Kraken: 3 of 5 pages")),
    ("never waits", lambda ev: ev["seen"][1].update(
        waiting_for="Waiting for the model lane: Transcribe (Kraken) is reading")),
    ("Names: not 0", lambda ev: _names(ev)["account"].update(pages_done=0, pages_left=3)),
    ("uncertain pages", lambda ev: _names(ev)["left_out"][0].update(why="its reading is too uncertain")),
    ("the project's language", lambda ev: ev.update(languages_used={"English": 23, "Spanish": 4})),
    ("Find the Documents", lambda ev: ev["proposals"][0].update(documents=ev["proposals"][0]["documents"][:1])),
    ("Find the Documents", lambda ev: [d.update(date=None) for d in ev["proposals"][0]["documents"]]),
    ("no \"Read\" offer", lambda ev: _names(ev)["account"].update(
        offer={"action": "read-again", "pages": 92, "label": "Read the 92 pages not done"})),
])
def test_each_defect_the_operator_saw_fails_its_check(starts, break_it):
    ev = _run()
    break_it(ev)
    failed = [n for n, v in _verdicts(ev).items() if v == rc.FAIL]
    assert any(n.startswith(starts) for n in failed), failed
    _, ok = rc.table(ev)
    assert not ok


def test_what_a_dry_run_cannot_see_is_not_applicable_not_a_pass():
    ev = _run()
    ev["seen"] = []
    assert _verdict(ev, "progress says") == rc.NA
    _names(ev).update(account=None, why="already done on every page")
    assert _verdict(ev, "Names: not 0") == rc.NA


def test_a_shape_it_does_not_know_fails_the_check_naming_why():
    ev = _run()
    del ev["summary"]["pages_read"]
    rows, ok = rc.table(ev)
    assert not ok
    assert any("could not read the run" in d for _, v, d in rows if v == rc.FAIL)


def test_only_a_project_under_fichero_dev_test_is_accepted(tmp_path):
    home = tmp_path / "Fichero Dev Test"
    (home / "MCP Night 1.fichero").mkdir(parents=True)
    real = tmp_path / "Projects" / "Marshall.fichero"
    real.mkdir(parents=True)
    (home / "link.fichero").symlink_to(real)
    assert rc.scratch_project(str(home / "MCP Night 1.fichero"), str(home)) == (home / "MCP Night 1.fichero").resolve()
    for refused in (real, home / "link.fichero", home / ".." / "Projects" / "Marshall.fichero", home):
        with pytest.raises(ValueError, match="refused"):
            rc.scratch_project(str(refused), str(home))


class _CLI:
    """The fichero CLI as the script calls it, answered from the recording; it notes every command."""

    def __init__(self, ev: dict):
        self.ev, self.calls = ev, []

    def __call__(self, *args: str, missing_ok: bool = False):
        self.calls.append(args)
        ev, head = self.ev, args[:2]
        answers = {
            ("recipes", "runs"): {"items": [ev["status"]]},
            ("recipes", "start-project"): {"started": {"job_id": ev["job_id"], "pages": 6, "workflows": [],
                                                       "started_at": "now"}},
            ("recipes", "run-status"): ev["status"],
            ("recipes", "run-summary"): ev["summary"],
            ("recipes", "get-project-setup"): {"answers": ev["setup"], "recipe": None},
            ("workflow", "threads"): {"state": {"node_outputs": {"names": {
                "languages_used": ev["languages_used"]}}}},
            ("docs", "list-roots"): {"items": [{"id": "f1", "name": "CACIQUES_INDIOS,17,D.5"}]},
            ("docs", "get-children"): {"items": [{"name": n} for n in ev["folders"]["CACIQUES_INDIOS,17,D.5"]]},
            ("find-documents", "list-proposals"): {"items": [{k: v for k, v in p.items() if k != "folder"}
                                                             for p in ev["proposals"]]},
            ("segments", "get-document-text"): {"text": ev["texts"].get(args[-1], "")},
        }
        return copy.deepcopy(answers[head])


def test_a_dry_run_reads_the_last_run_and_writes_nothing():
    cli = _CLI(_run())
    ev = rc.gather(cli, redo=["read-a-line"], dry_run=True, every=0, hours=1, sleep=lambda s: None, say=lambda s: None)
    assert ("recipes", "start-project") not in [c[:2] for c in cli.calls]
    assert ev["job_id"] == "afaeecb4" and ev["seen"] == []
    assert ev["languages_used"] == {"Spanish": 3}
    assert ev["proposals"][0]["folder"] == "CACIQUES_INDIOS,17,D.5"
    rows, ok = rc.table(ev)
    assert ok, rows


def test_a_run_starts_once_with_its_redo_and_is_followed_to_its_end():
    run = _run()
    cli = _CLI(run)
    states = iter(["running", "running", "done"])
    real_status = cli.__call__

    def stepping(*args, **kw):
        answer = real_status(*args, **kw)
        if args[:2] == ("recipes", "run-status"):
            answer["state"] = next(states)
        return answer

    slept = []
    ev = rc.gather(stepping, redo=["read-a-line", "find-names-tag-words"], dry_run=False, every=60, hours=1,
                   sleep=slept.append, say=lambda s: None)
    starts = [c for c in cli.calls if c[:2] == ("recipes", "start-project")]
    assert starts == [("recipes", "start-project", "--redo", "read-a-line", "--redo", "find-names-tag-words")]
    assert slept == [60, 60]
    assert [s["state"] for s in ev["seen"]] == ["running", "running", "done"]
    assert {c[:2] for c in cli.calls} <= {("recipes", "start-project"), *READS}


#: Every command the script sends besides Start: each one a read (GET).
READS = {("recipes", "runs"), ("recipes", "run-status"), ("recipes", "run-summary"), ("recipes", "get-project-setup"),
         ("workflow", "threads"), ("docs", "list-roots"), ("docs", "get-children"),
         ("find-documents", "list-proposals"), ("segments", "get-document-text")}


def test_every_command_it_sends_is_a_read_the_cli_has():
    """The CLI's own commands, read offline: each one the script sends exists, and is a GET (`docs`, not
    `documents`, and `workflow threads`, not `workflow-execution`, are the CLI's spellings)."""
    import inspect
    import sys

    sys.path.insert(0, str(ROOT / "fichero-cli/src"))
    try:
        from typer.main import get_command

        from fichero_cli.__main__ import app
    finally:
        sys.path.pop(0)
    root = get_command(app)
    source = (ROOT / "scripts/realrun_check.py").read_text()
    sent = {tuple(a.strip('"') for a in m.split(", ")) for m in
            __import__("re").findall(r'cli\(("[a-z][a-z-]*"(?:, "[a-z][a-z-]*"){1,2})', source)}
    assert sent, "no CLI calls found in the script"
    for words in sent:
        command = root
        for word in words:
            command = command.commands[word]
        doc = inspect.getdoc(command.callback) or ""
        assert "(GET " in doc or words == ("recipes", "start-project"), (words, doc)


def test_main_checks_a_recording_and_exits_by_its_verdict(tmp_path, capsys):
    good = tmp_path / "good.json"
    good.write_text(FIXTURE.read_text())
    assert rc.main(["--evidence", str(good)]) == 0
    bad = _run()
    bad["languages_used"] = {"English": 10}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    assert rc.main(["--evidence", str(path)]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert rc.main([str(tmp_path / "elsewhere.fichero")]) == 2
