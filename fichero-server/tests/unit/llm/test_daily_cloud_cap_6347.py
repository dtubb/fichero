"""`ai.cloud.daily-cap` (#6347): a daily cap is held through the one hold, from the same ledger, beside the monthly one."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fichero_server.llm import spend


@pytest.fixture(autouse=True)
def _no_app_caps(monkeypatch):
    held: dict = {}
    monkeypatch.setattr(spend, "app_cap_usd", lambda key: held.get(key))
    spend._RESERVED.clear()
    return held


def _project(tmp_path, answers: str = "") -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n" + answers)
    return str(tmp_path / "P.fichero")


def test_no_daily_cap_unless_set(tmp_path):
    assert spend.daily_cap_usd(_project(tmp_path)) is None


def test_a_project_answer_or_the_app_setting_gives_the_daily_cap(tmp_path, _no_app_caps):
    _no_app_caps[spend.APP_DAILY_KEY] = 5.0
    assert spend.daily_cap_usd(_project(tmp_path)) == 5.0
    assert spend.daily_cap_usd(_project(tmp_path / "b", "cloud_daily_cap_usd: 2\n")) == 2.0


def test_the_ledger_keeps_today_and_rolls_over(tmp_path):
    lib = _project(tmp_path)
    day1 = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
    spend._book(lib, 1.5, day1)
    spend._book(lib, 0.5, day1)
    assert spend.daily_booked_usd(lib, day1) == pytest.approx(2.0)
    assert spend.daily_booked_usd(lib, day1 + timedelta(days=1)) == 0.0
    spend._book(lib, 1.0, day1 + timedelta(days=1))
    assert spend.daily_booked_usd(lib, day1 + timedelta(days=1)) == pytest.approx(1.0)
    assert spend.total_booked_usd(lib) == pytest.approx(3.0)  # the month and the total are not reset by a new day


def test_the_daily_cap_refuses_first_when_it_is_lower_and_says_so(tmp_path):
    lib = _project(tmp_path, "cloud_spend_cap_usd: 100\ncloud_daily_cap_usd: 1\n")
    spend._book(lib, 0.9)
    with spend._LOCK:
        why = spend._past_a_cap(lib, 0.0, 0.2)
    assert why and "$1.00 a day" in why and "spent today" in why


def test_the_monthly_cap_still_holds_with_a_daily_cap_beside_it(tmp_path):
    lib = _project(tmp_path, "cloud_spend_cap_usd: 1\ncloud_daily_cap_usd: 50\n")
    spend._book(lib, 0.9)
    with spend._LOCK:
        assert "a month" in spend._past_a_cap(lib, 0.0, 0.2)
        assert spend._past_a_cap(lib, 0.0, 0.05) is None


def test_the_plan_line_names_the_day(tmp_path):
    lib = _project(tmp_path, "cloud_daily_cap_usd: 1\n")
    spend._book(lib, 0.25)
    line = spend.plan_line(lib, estimate_usd=2.0)
    assert line["over_day"] and line["over"] and not line["over_month"]
    assert line["daily_remaining_usd"] == pytest.approx(0.75) and line["needed_daily_cap_usd"] == pytest.approx(2.25)


def test_the_cap_stop_carries_the_daily_figure(tmp_path):
    lib = _project(tmp_path, "cloud_daily_cap_usd: 1\n")
    spend._book(lib, 0.9)
    stop = spend._cap_stop(lib, 0.2, "x")
    assert stop["needed_daily_cap_usd"] == pytest.approx(1.1) and stop["caps"]["day"] == 1.0


def test_a_run_cap_a_daily_cap_and_a_monthly_cap_all_hold_through_the_one_hold(tmp_path):
    lib = _project(tmp_path, "cloud_spend_cap_usd: 100\ncloud_daily_cap_usd: 50\n")
    with spend._LOCK:
        assert spend._past_a_cap(lib, 0.0, 1.0) is None
    spend.set_run_cap(lib, "run-1", 2.0)
    with spend._LOCK:
        assert spend._past_a_cap(lib, 0.0, 1.0) is None
        assert "this run's cloud spend is capped at $2.00" in spend._past_a_cap(lib, 0.0, 3.0)
    spend.clear_run_cap(lib, "run-1")
    spend._book(lib, 49.5)
    with spend._LOCK:
        assert "a day" in spend._past_a_cap(lib, 0.0, 1.0)  # the day refuses first; the month ($100) still has room
