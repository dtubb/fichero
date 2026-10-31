"""The studio trial's running log: one row per item and role, from the journal and Pi's session files."""
from __future__ import annotations

import shutil

from pipeline import journal, runlog
from pipeline.tests.conftest import ISSUES

FIXTURE = runlog.ROOT / "pipeline" / "tests" / "fixtures" / "pi-session-redacted.jsonl"


def test_the_log_has_a_row_per_item_and_role_with_tokens_cost_and_verdict(scratch, tmp_path):
    cfg = scratch["cfg"]
    cfg["workers"]["context_tokens_by"] = {"anthropic": 200000}
    for role in ("coder", "reviewer"):
        (tmp_path / role).mkdir()
        shutil.copy(FIXTURE, tmp_path / role / "s.jsonl")
    journal.append("item", issue=1001, task="t", title="x", window="w", worktree="/nowhere", ids=[], key="1001")
    for role in ("coder", "reviewer"):
        journal.append("worker", window=role, task="t", role=role, model="anthropic/claude-haiku-5-5", session_dir=str(tmp_path / role))
    journal.append("issue_done", issue=1001, key="1001", task="t", sha="a" * 40, turns=8, tokens=1, usd=0.5)
    journal.append("check", issue=1001, key="1001", ok=False, sha="a" * 40, results=[{"name": "diff-bound", "ok": False, "text": "wide"}])
    journal.append("verdict", issue=1001, key="1001", sha="a" * 40, verdict="NOT_READY", by="reviewer", findings="")
    rs = runlog.rows(cfg, diff=lambda *a: "42")
    coder_row, review_row = rs
    assert (coder_row["role"], coder_row["provider"], coder_row["model"], coder_row["ctx_cap"]) == ("coder", "anthropic", "claude-haiku-5-5", 200000)
    assert coder_row["tool_errors"] == 2 and coder_row["diff_lines"] == "42" and coder_row["ladder"] == "red:diff-bound"
    assert coder_row["false_done"] == 1 and coder_row["prompt_tokens"] > 30000 and coder_row["output_tokens"] > 100
    assert coder_row["cost_usd"] > 0 and coder_row["pi_cost_usd"] > 0
    assert review_row["role"] == "reviewer" and review_row["binding_verdict"] == "NOT_READY"
    out = runlog.write(tmp_path / "log.tsv")
    lines = (tmp_path / "log.tsv").read_text().splitlines()
    assert out["rows"] == 2 and lines[0].split("\t") == runlog.COLUMNS and len(lines[1].split("\t")) == len(runlog.COLUMNS)


def coder_row(item, prompt, cached, usd):
    return {"role": "coder", "item": item, "prompt_tokens": prompt, "cached_tokens": cached, "output_tokens": 10, "cost_usd": usd}


def test_cluster_rows_compare_the_per_issue_cost_of_a_lane_with_the_single_issue_tasks():
    rows = [coder_row("1", 1000, 0, 0.10), coder_row("2", 3000, 0, 0.30),   # two single-issue tasks: 2000 tokens, US$0.20 each on average
            coder_row("3@lane", 1000, 600, 0.05), coder_row("4@lane", 1400, 1000, 0.07), {"role": "reviewer", "item": "3@lane"}]
    got = runlog.cluster_rows(rows, lambda key: "lane" if key.endswith("@lane") else key)
    lane = next(r for r in got if r["task"] == "lane")
    assert (lane["issues"], lane["prompt_per_issue"], lane["cache_hit"], lane["cost_per_issue"]) == (2, 1200, 0.667, 0.06)
    assert (lane["solo_prompt_per_issue"], lane["ratio_prompt"], lane["ratio_cost"]) == (2000, 0.6, 0.3)
    assert len(got) == 3
