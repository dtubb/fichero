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


def test_only_the_day_cap_parks_and_session_spend_alone_never_ends_a_session():
    """Owner ruling B2 (2026-11-21): no dollar session cap; a session ends on the day cap and the context limit only."""
    assert watcher.assess({**STATE, "cost_usd": 15.0}, SPEND, "sonnet", spent_today=0, silent_for_s=0) == []
    out = watcher.assess({**STATE, "cost_usd": 1.0}, SPEND, "sonnet", spent_today=19.5, silent_for_s=0)
    assert out == ["park: today's spend 20.50 USD reached the cap 20.00"]


def test_a_day_cap_alone_lets_a_worker_start():
    """Owner ruling B2: `session_usd` is no longer required (still accepted, so an older rules file loads)."""
    assert watcher.refusals(watcher.Spend(day_usd=20.0, prices=PRICES), "claude", "sonnet") == []
    assert any("no cap, no start" in r for r in watcher.refusals(watcher.Spend(session_usd=5.0, prices=PRICES), "claude", "sonnet"))


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


def test_the_loop_publishes_the_owners_spend_and_models_for_the_jailed_run(tmp_path, monkeypatch):
    """local.perf.caps-reread-each-tick (#6851): the run's --root is a pinned copy and the owner's own caps are unreadable to the
    worker, so the loop writes `<feed>/rules.json` from the live rules file (with the owner's local override) for it to read."""
    import json
    import stat

    from fichero_builder import queue
    monkeypatch.setattr(watcher, "LOCAL", tmp_path / "none.toml")
    rules_file = tmp_path / "harness.toml"
    rules_file.write_text('[spend]\nday_usd = 30\nprices = { sonnet = [3, 15] }\n[models]\nproviders = ["anthropic"]\n')
    feed = tmp_path / "feed"
    feed.mkdir()
    queue.publish_rules(tmp_path, feed)
    doc = json.loads((feed / "rules.json").read_text())
    assert doc == {"spend": {"day_usd": 30, "prices": {"sonnet": [3, 15]}}, "models": {"providers": ["anthropic"]}}
    assert stat.S_IMODE((feed / "rules.json").stat().st_mode) == 0o644 and watcher.parse(doc["spend"]).day_usd == 30
    rules_file.write_text("[spend]\nday_cap = 1\n")
    with pytest.raises(ValueError, match="unknown keys"):
        queue.publish_rules(tmp_path, feed)
    assert json.loads((feed / "rules.json").read_text()) == doc, "a bad table never replaces the last good copy"


def test_live_spend_sums_other_sessions_fresh_files_of_today_only(tmp_path):
    """local.perf.day-cap-counts-live-sessions (#6871): every other live session's running cost counts, a stale or
    yesterday's file does not, nor the run's own."""
    import json
    import os
    d = tmp_path / "live"
    d.mkdir()
    for name, usd, day in (("a", 1.5, "2026-11-21"), ("b", 2.0, "2026-11-21"), ("me", 9.0, "2026-11-21"),
                           ("old", 7.0, "2026-11-20"), ("dead", 5.0, "2026-11-21")):
        (d / f"{name}.json").write_text(json.dumps({"usd": usd, "day": day}))
    os.utime(d / "dead.json", (1000.0, 1000.0))
    now = (d / "a.json").stat().st_mtime + 10
    assert watcher.live_spend(d, "2026-11-21", "me", now) == 3.5
    assert watcher.live_spend(tmp_path / "none", "2026-11-21", "me", now) == 0


def test_live_spend_skips_a_file_that_is_malformed_or_cannot_be_read(tmp_path):
    """#6871: a run's live file deleted between the listing and the read, or a stray non-JSON file, must not end the watcher."""
    import json
    d = tmp_path / "live"
    d.mkdir()
    (d / "ok.json").write_text(json.dumps({"usd": 1.0, "day": "2026-11-21"}))
    (d / "junk.json").write_text("not json")
    (d / "unreadable.json").mkdir()  # read_text raises OSError, as a vanished file does
    now = (d / "ok.json").stat().st_mtime + 10
    assert watcher.live_spend(d, "2026-11-21", "me", now) == 1.0


# local.spend.metered-provider-needs-a-cap (Step 1.5): no metered provider without a weekly figure; the week's rows park

METERED = '[spend]\nday_usd = 300\nprices = { sonnet = [3, 15] }\nmetered = ["openrouter"]\n[spend.week_usd]\nopenrouter = 25\n'


def test_a_metered_provider_with_no_weekly_figure_refuses_the_rules_file(tmp_path):
    with pytest.raises(ValueError, match="needs a weekly cap"):
        watcher.load(_toml(tmp_path, '[spend]\nday_usd = 300\nmetered = ["openrouter"]\n'))
    s = watcher.load(_toml(tmp_path, METERED))
    assert s.metered == ("openrouter",) and s.week_usd == {"openrouter": 25.0}


def test_openrouter_never_starts_without_a_figure_even_unlisted(tmp_path):
    s = watcher.load(_toml(tmp_path, '[spend]\nday_usd = 300\n'))
    assert any("no weekly cap" in r for r in watcher.refusals(s, "pi", "qwen/qwen3-coder-next", "openrouter"))
    assert not watcher.refusals(watcher.load(_toml(tmp_path, METERED)), "pi", "qwen/qwen3-coder-next", "openrouter")


def test_the_weeks_rows_of_the_provider_reach_the_figure_and_the_session_parks():
    s = watcher.parse({"day_usd": 300, "metered": ["openrouter"], "week_usd": {"openrouter": 25}})
    rows = [{"event": "cost", "provider": "openrouter", "usd": 20, "ts": "2026-11-23T10:00:00"},  # Monday, this week
            {"event": "cost", "provider": "openrouter", "usd": 50, "ts": "2026-11-22T10:00:00"},  # Sunday, last week
            {"event": "cost", "provider": "claude-code", "usd": 99, "ts": "2026-11-24T10:00:00"},  # a subscription: not counted
            {"event": "cost", "usd": 99, "ts": "2026-11-24T10:00:00"}]  # no provider: not counted
    week = watcher.spent_week(rows, "openrouter", "2026-11-25T09:00:00")
    assert week == 20
    assert not watcher.assess({**STATE, "cost_usd": 4.0}, s, "q", spent_today=0, silent_for_s=0, provider="openrouter", spent_week=week)
    d = watcher.assess({**STATE, "cost_usd": 5.0}, s, "q", spent_today=0, silent_for_s=0, provider="openrouter", spent_week=week)
    assert d == ["park: this week's openrouter spend 25.00 USD reached the cap 25.00"]


def test_a_subscription_session_is_not_counted_against_a_week():
    s = watcher.parse({"day_usd": 300, "metered": ["openrouter"], "week_usd": {"openrouter": 25}, "prices": {"sonnet": [3, 15]}})
    assert not watcher.is_metered(s, "claude-code")
    assert not watcher.assess({**STATE, "cost_usd": 50.0}, s, "sonnet", spent_today=0, silent_for_s=0, provider="claude-code", spent_week=999)
