"""dev-workflows.tool.work: `builder work` chains run -> patches -> fetch -> check -> review -> land in ONE process, journals
every step, stops with `QUESTION: <why>` (exit 2) and never pushes. The steps are faked; the order, stops and rows are real."""
from __future__ import annotations

import pytest

from fichero_builder import __main__ as cli
from fichero_builder import journal, work

RULES = '[land]\nbranch = "integration"\n[check]\nengine_repo = "/engine"\n[models]\nproviders = ["claude-code"]\n' \
        'builder = { provider = "claude-code", model = "sonnet" }\nreviewer = { provider = "claude-code", model = "opus" }\n'
HEAD = "c" * 40
PUSH = f"READY TO LAND: git {'pu' + 'sh'} origin {HEAD}:refs/heads/integration"  # the land script's own line


@pytest.fixture
def chain(tmp_path, monkeypatch):
    (tmp_path / "harness.toml").write_text(RULES)
    monkeypatch.setattr(journal, "STATE", tmp_path / "s")
    calls = []
    fakes = {
        "do_run": lambda a, model: (calls.append(("run", model)), "done")[1],
        "do_export": lambda a, branch: (calls.append(("export", branch)), 2)[1],
        "do_fetch": lambda a, repo: (calls.append(("fetch", repo)), HEAD)[1],
        "do_check": lambda a, repo, since, head, ladder: (calls.append(("check", since, head)), {"ok": True, "failed": ""})[1],
        "do_review": lambda a, repo, head, ladder, verdicts, model: (calls.append(("review", model, ladder.endswith(".json"))), (True, "READY"))[1],
        "do_land": lambda a, repo, head, verdicts, log: (calls.append(("land", head)), (True, PUSH))[1],
    }
    for k, v in fakes.items():
        monkeypatch.setattr(work, k, v)

    def go(*extra):
        return cli.main(["work", "--brief", "b.txt", "--worktree", str(tmp_path / "wt"), "--name", "n1", "--issues", "7", "8",
                         "--pinned", str(tmp_path), "--state", str(tmp_path / "s"), *extra])
    go.calls, go.tmp = calls, tmp_path
    return go


def rows():
    return [r for r in journal.read() if r["event"] == "work"]


def test_the_chain_runs_in_order_with_the_roles_models_prints_the_push_and_never_pushes(chain, capsys):
    assert chain() == 0
    assert [c[0] for c in chain.calls] == ["run", "export", "fetch", "check", "review", "land"]
    assert chain.calls[0][1] == "sonnet" and chain.calls[4][1] == "opus", "[models].builder and [models].reviewer"
    assert chain.calls[3][1] == "integration" and chain.calls[3][2] == HEAD
    assert PUSH in capsys.readouterr().out
    assert [(r["step"], r["ok"]) for r in rows()] == [(s, True) for s in ("run", "patches", "fetch", "check", "review", "land")]
    assert all(r["name"] == "n1" and r["issues"] == [7, 8] and "detail" in r for r in rows())


@pytest.mark.parametrize("end", ["parked", "gone"])
def test_a_worker_that_did_not_finish_is_a_question(chain, monkeypatch, capsys, end):
    monkeypatch.setattr(work, "do_run", lambda a, model: end)
    assert chain() == 2
    out = capsys.readouterr().out
    assert out.startswith("QUESTION: ") and end in out
    assert chain.calls == [] and [(r["step"], r["ok"]) for r in rows()] == [("run", False)]


def test_a_red_check_stops_before_review(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_check", lambda a, repo, since, head, ladder: {"ok": False, "failed": "pytest"})
    assert chain() == 2
    out = capsys.readouterr().out
    assert out.startswith("QUESTION: ") and "pytest" in out
    assert [c[0] for c in chain.calls] == ["run", "export", "fetch"]
    assert rows()[-1]["step"] == "check" and rows()[-1]["ok"] is False


def test_a_not_ready_review_stops_before_land(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_review", lambda *a: (False, "NOT READY: a test is missing"))
    assert chain() == 2
    assert "NOT READY: a test is missing" in capsys.readouterr().out
    assert "land" not in [c[0] for c in chain.calls]
    assert rows()[-1]["step"] == "review" and rows()[-1]["ok"] is False


def test_a_refused_land_is_a_question_and_prints_no_push_line(chain, monkeypatch, capsys):
    monkeypatch.setattr(work, "do_land", lambda *a: (False, "REFUSED: boundary"))
    assert chain() == 2
    out = capsys.readouterr().out
    assert "QUESTION: " in out and "REFUSED: boundary" in out and "READY TO LAND" not in out
    assert rows()[-1]["step"] == "land" and rows()[-1]["ok"] is False


def test_no_patches_is_a_question(chain, monkeypatch):
    monkeypatch.setattr(work, "do_export", lambda a, branch: 0)
    assert chain() == 2 and rows()[-1]["step"] == "patches"


def test_a_role_with_no_model_is_a_question_before_anything_starts(chain, capsys):
    (chain.tmp / "harness.toml").write_text(RULES.replace('reviewer = { provider = "claude-code", model = "opus" }', ""))
    assert chain() == 2
    assert chain.calls == [] and "reviewer" in capsys.readouterr().out
