"""The app's launch budgets read from its `LaunchProfile` lines (#7105): first window onAppear within 3 s of process start, and
`connect()` reaching the main actor within 1 s of `applicationWillFinishLaunching`. A launch that logged neither is a red."""
import json
import subprocess
import sys
from pathlib import Path

from fichero_builder import perf_log_readers

ROOT = Path(__file__).resolve().parents[2]


def timeline(first_on_appear: float, will_finish: float, connect: float) -> list[str]:
    """One launch's lines in time order, as the app logs them."""
    at = [
        ("process start", 0.0),
        ("saved libraries materialized (pre-ready)", 310.0),
        ("applicationWillFinishLaunching — engine connect starts", will_finish),
        ("connect() entry — main actor reached", connect),
        ("LibraryWindow first onAppear (2 libraries)", first_on_appear),
    ]
    return [f"⏱ {name} @ {ms}ms" for name, ms in sorted(at, key=lambda row: row[1])]


def test_a_launch_inside_both_budgets_is_ok_and_names_its_figures():
    got = perf_log_readers.launch_budgets(timeline(first_on_appear=2400.0, will_finish=350.0, connect=900.5))
    assert got["ok"] is True
    assert got["figures"] == {"first_on_appear_ms": 2400.0, "connect_after_will_finish_ms": 550.5}
    assert got["over"] == [] and got["missing"] == []


def test_the_launch_of_the_issue_is_over_on_connect():
    got = perf_log_readers.launch_budgets(timeline(first_on_appear=2400.0, will_finish=350.0, connect=110819.0))
    assert got["ok"] is False
    assert got["over"] == ["connect_after_will_finish_ms 110469.0 > 1000"]


def test_a_first_window_after_three_seconds_is_over():
    got = perf_log_readers.launch_budgets(timeline(first_on_appear=3000.1, will_finish=350.0, connect=400.0))
    assert got["ok"] is False and got["over"] == ["first_on_appear_ms 3000.1 > 3000"]


def test_a_log_without_the_milestones_is_a_red_that_names_them():
    got = perf_log_readers.launch_budgets(["⏱ process start @ 0.0ms", "unrelated line"])
    assert got["ok"] is False
    assert got["missing"] == ["applicationWillFinishLaunching — engine connect starts",
                              "connect() entry — main actor reached", "LibraryWindow first onAppear"]


def test_the_json_log_stream_form_is_read_and_only_the_first_launch_counts():
    lines = [json.dumps({"category": "LaunchProfile", "eventMessage": line}) for line in timeline(2000.0, 300.0, 800.0)]
    lines += timeline(9000.0, 300.0, 8000.0)  # a second launch in the same capture
    assert perf_log_readers.launch_budgets(lines)["figures"] == {"first_on_appear_ms": 2000.0, "connect_after_will_finish_ms": 500.0}


def test_the_milestone_names_are_the_ones_the_app_logs():
    app = "".join((ROOT / "fichero/fichero" / name).read_text() for name in (
        "FicheroApp.swift", "App/LibraryWindow.swift", "Services/EngineLifecycleController.swift"))
    for name in perf_log_readers.LAUNCH_MILESTONES.values():
        assert f'milestone("{name}"' in app, name


def test_the_script_exits_1_on_a_launch_over_budget_and_0_inside(tmp_path):
    script = [sys.executable, str(ROOT / "scripts/perf_launch_check.py")]
    slow, quick = tmp_path / "slow.log", tmp_path / "quick.log"
    slow.write_text("\n".join(timeline(2400.0, 350.0, 110819.0)))
    quick.write_text("\n".join(timeline(2400.0, 350.0, 900.0)))
    red = subprocess.run([*script, str(slow)], capture_output=True, text=True)
    green = subprocess.run([*script, str(quick)], capture_output=True, text=True)
    assert red.returncode == 1 and "connect_after_will_finish_ms 110469.0 > 1000" in red.stdout
    assert green.returncode == 0
    assert json.loads(green.stdout.splitlines()[-1].removeprefix("LAUNCH-RESULT "))["figures"]["first_on_appear_ms"] == 2400.0
