"""dev-workflows.run.watch-tick: caps from the rules file, unknown price refuses, decisions from the session file."""
from __future__ import annotations

import pytest

from fichero_builder import watcher

PRICES = {"sonnet": [3.0, 15.0], "claude-opus-4-1": [15.0, 75.0]}
SPEND = watcher.Spend(window=1000, handoff_at=0.85, session_usd=5.0, day_usd=20.0, silent_s=600, prices=PRICES)
STATE = {"started": True, "idle": False, "context": 0, "tokens": 0, "cost_usd": 0.0, "rate_limited": False, "error": "", "transient": False}


def _toml(tmp_path, text):
    (tmp_path / "harness.toml").write_text(text)
    return tmp_path


def test_a_missing_table_gives_zero_caps_and_zero_caps_refuse(tmp_path):
    s = watcher.load(_toml(tmp_path, "[check]\n"))
    assert s.session_usd == 0 and s.day_usd == 0
    assert any("no cap, no start" in r for r in watcher.refusals(s, "claude", "sonnet"))


def test_the_table_is_read_and_an_unknown_key_or_bad_price_refuses(tmp_path):
    s = watcher.load(_toml(tmp_path, '[spend]\nsession_usd = 4\nday_usd = 30\nwindow = 100000\nprices = { sonnet = [3, 15] }\n'))
    assert (s.session_usd, s.day_usd, s.window, s.prices) == (4.0, 30.0, 100000, {"sonnet": [3, 15]})
    with pytest.raises(ValueError, match="unknown keys"):
        watcher.load(_toml(tmp_path, "[spend]\nsesion_usd = 4\n"))
    with pytest.raises(ValueError, match="two numbers"):
        watcher.load(_toml(tmp_path, '[spend]\nprices = { sonnet = [3] }\n'))


def test_price_is_exact_or_the_longest_contained_key():
    assert watcher.price_for("claude-opus-4-1", SPEND) == [15.0, 75.0]
    assert watcher.price_for("claude-sonnet-4-5-20250929", SPEND) == [3.0, 15.0]
    assert watcher.price_for("qwen/qwen3", SPEND) is None


def test_an_unknown_price_refuses_a_claude_worker_but_not_a_pi_worker():
    assert watcher.refusals(SPEND, "claude", "gpt-9") == ["harness.toml [spend].prices has no price for 'gpt-9': unknown price, no start"]
    assert watcher.refusals(SPEND, "pi", "qwen/qwen3") == []
    assert watcher.refusals(SPEND, "claude", "sonnet") == []


def test_cost_is_the_files_figure_or_the_token_counts_at_the_models_price():
    assert watcher.cost_of({**STATE, "cost_usd": 0.42, "tokens": 10**6}, SPEND, "sonnet") == 0.42
    assert watcher.cost_of({**STATE, "tokens": 10**6}, SPEND, "unknown") == 0.0
    # 1M fresh input at 3, 1M cache reads at 0.3, 1M output at 15 (the remainder once input and cache are taken off)
    s = {**STATE, "tokens": 3 * 10**6, "fresh": 10**6, "cache_read": 10**6, "cache_write": 0}
    assert round(watcher.cost_of(s, SPEND, "sonnet"), 3) == 18.3
    # a one-word reply over a 35k cached prompt costs cents, not a tenth of a dollar (the first live run read 0.11)
    s = {**STATE, "tokens": 35066, "fresh": 4, "cache_read": 31000, "cache_write": 4058}
    assert round(watcher.cost_of(s, SPEND, "sonnet"), 3) == 0.022


def test_spent_today_sums_only_todays_cost_rows():
    rows = [{"event": "cost", "ts": "2026-11-01T09:00:00", "usd": 1.5}, {"event": "cost", "ts": "2026-10-31T23:59:00", "usd": 9},
            {"event": "worker", "ts": "2026-11-01T09:00:00"}, {"event": "cost", "ts": "2026-11-01T10:00:00", "usd": 0.25}]
    assert watcher.spent_today(rows, "2026-11-01") == 1.75


def test_nothing_to_do_for_a_healthy_working_session():
    assert watcher.assess({**STATE, "context": 100}, SPEND, "sonnet", spent_today=0, silent_for_s=10) == []


def test_handoff_at_the_share_of_the_window():
    assert watcher.assess({**STATE, "context": 849}, SPEND, "sonnet", spent_today=0, silent_for_s=0) == []
    assert watcher.assess({**STATE, "context": 850}, SPEND, "sonnet", spent_today=0, silent_for_s=0) == ["handoff: context 850 of 1000"]


def test_the_session_cap_then_the_day_cap_park():
    """Since 2026-11-02 (dev-workflows.run.loop-session-cap-hands-off) the session cap hands off; only the day cap parks."""
    out = watcher.assess({**STATE, "cost_usd": 5.0}, SPEND, "sonnet", spent_today=0, silent_for_s=0)
    assert out == ["handoff: session spend 5.00 USD reached the cap 5.00"]
    out = watcher.assess({**STATE, "cost_usd": 1.0}, SPEND, "sonnet", spent_today=19.5, silent_for_s=0)
    assert out == ["park: today's spend 20.50 USD reached the cap 20.00"]


def test_a_quota_refusal_or_a_lasting_error_parks_but_a_transient_one_does_not():
    assert watcher.assess({**STATE, "rate_limited": True}, SPEND, "sonnet", spent_today=0, silent_for_s=0)[0].startswith("park: the provider refused")
    assert watcher.assess({**STATE, "error": "400 bad request"}, SPEND, "sonnet", spent_today=0, silent_for_s=0) == ["park: provider error: 400 bad request"]
    assert watcher.assess({**STATE, "error": "503 overloaded", "transient": True}, SPEND, "sonnet", spent_today=0, silent_for_s=0) == []


def test_a_silent_working_session_alerts_and_an_idle_one_does_not():
    assert watcher.assess(STATE, SPEND, "sonnet", spent_today=0, silent_for_s=600) == ["alert: no change in the session file for 600 s"]
    assert watcher.assess({**STATE, "idle": True}, SPEND, "sonnet", spent_today=0, silent_for_s=6000) == []
    assert watcher.assess({**STATE, "started": False}, SPEND, "sonnet", spent_today=0, silent_for_s=6000) == [], "not yet started is not silent"


def test_the_handoff_threshold_is_an_absolute_token_count_when_set():
    """dev-workflows.run.loop-handoff-tokens: ie-lane2 used 17M tokens for three steps on a 1M window; 150000 tokens, not 85% of it."""
    big = watcher.Spend(window=1_000_000, handoff_at=0.85, handoff_tokens=150_000, session_usd=5.0, day_usd=20.0, silent_s=600, prices=PRICES)
    assert watcher.assess({**STATE, "context": 149_999}, big, "sonnet", spent_today=0, silent_for_s=0) == []
    assert watcher.assess({**STATE, "context": 150_001}, big, "sonnet", spent_today=0, silent_for_s=0) == ["handoff: context 150001 of 150000"]
    assert watcher.threshold(big) == 150_000 and watcher.threshold(SPEND) == 850


def test_a_machines_own_spend_caps_win_only_from_the_owners_private_file(tmp_path, monkeypatch):
    """Manager 2026-11-02: per-machine caps live in an untracked `harness.local.toml` under the owner's home; its [spend] keys win,
    the rest of [spend] stays, an unknown key still refuses. Review 2026-11-02: a file a worker could write must never count: one
    owned by someone other than the checkout's owner, or writable by group or world, is ignored."""
    import os
    local = tmp_path / "home" / "harness.local.toml"
    local.parent.mkdir()
    monkeypatch.setattr(watcher, "LOCAL", local)
    (tmp_path / "harness.toml").write_text("[spend]\nwindow = 200000\nsession_usd = 8\nday_usd = 60\n")
    assert watcher.load(tmp_path).day_usd == 60
    local.write_text("[spend]\nday_usd = 100\n")
    local.chmod(0o600)
    sp = watcher.load(tmp_path)
    assert sp.day_usd == 100 and sp.session_usd == 8 and sp.window == 200000
    local.chmod(0o666)
    assert watcher.load(tmp_path).day_usd == 60, "a file others can write is ignored"
    local.chmod(0o600)
    monkeypatch.setattr(os, "stat", lambda p, *a, **k: type("S", (), {"st_uid": 0, "st_mode": 0o100600})() if str(p) == str(tmp_path) else os.lstat(p))
    assert watcher.local_file(tmp_path) is None, "owned by someone other than the checkout's owner"
    monkeypatch.undo()
    monkeypatch.setattr(watcher, "LOCAL", local)
    local.write_text("[spend]\nday_cap = 1\n")
    with pytest.raises(ValueError, match="unknown keys"):
        watcher.load(tmp_path)
