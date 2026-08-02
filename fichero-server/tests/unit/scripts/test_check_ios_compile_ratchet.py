"""The iOS compile ratchet must distinguish slow from unmeasured (#4466).

Every branch here runs against a synthesised duration. No Xcode, no build —
which is the point of the script consuming a number rather than producing one:
a measurement harness that runs the thing it measures cannot be tested without
running it.

The branch that matters most is BLIND. This ratchet guards the leg that is
most likely to be skipped (slow, device-less, easy to disable), so "the gate
did not run the iOS build" and "the iOS build was fast" must never print the
same thing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("check_ios_compile_ratchet")


# ---------------------------------------------------------------------------
# BLIND — the branch this exists for
# ---------------------------------------------------------------------------


def test_no_duration_at_all_is_blind(capsys):
    assert guard.main([]) == 2
    assert "BLIND" in capsys.readouterr().err


def test_a_missing_duration_file_is_blind(tmp_path, capsys):
    assert guard.main(["--from-file", str(tmp_path / "absent")]) == 2
    assert "BLIND" in capsys.readouterr().err


def test_an_empty_duration_file_is_blind(tmp_path):
    path = tmp_path / "seconds"
    path.write_text("", encoding="utf-8")

    assert guard.main(["--from-file", str(path)]) == 2


def test_an_unparseable_duration_is_blind(tmp_path):
    path = tmp_path / "seconds"
    path.write_text("not a number", encoding="utf-8")

    assert guard.main(["--from-file", str(path)]) == 2


def test_an_implausibly_fast_compile_is_blind_not_a_new_record(capsys):
    """The dangerous one.

    A zero or near-zero duration is what a skipped or instantly-failed leg
    leaves behind. Recording it would set the bar to ~0ms and fail every honest
    run afterwards — so a broken leg would look like a heroic optimisation
    once, then break the gate forever.
    """
    assert guard.main(["--seconds", "0.0"]) == 2
    assert "BLIND" in capsys.readouterr().err

    assert guard.main(["--seconds", "0.4"]) == 2


def test_a_real_compile_duration_is_not_blind(monkeypatch):
    """The control. If a plausible number were also rejected, the guard would
    be a permanent exit 2 and nobody would notice the difference."""
    recorded: list[tuple[str, float]] = []
    perf = guard._load_recorder()
    monkeypatch.setattr(perf, "record", lambda name, ms: recorded.append((name, ms)))

    assert guard.main(["--seconds", "214.7"]) == 0
    assert recorded == [("ios.compile_ms", 214700.0)]


# ---------------------------------------------------------------------------
# It delegates rather than reimplements
# ---------------------------------------------------------------------------


def test_a_regression_from_the_shared_ratchet_becomes_exit_1(monkeypatch, capsys):
    perf = guard._load_recorder()

    def _raise(name: str, ms: float) -> None:
        raise AssertionError("ios.compile_ms took 900000.0 ms; the best recorded is 200000.0 ms")

    monkeypatch.setattr(perf, "record", _raise)

    assert guard.main(["--seconds", "900.0"]) == 1
    assert "SLOWER than the bar" in capsys.readouterr().err


def test_seconds_are_converted_to_milliseconds(monkeypatch):
    """`perf_ratchet` speaks ms; a unit slip would silently set a bar 1000x
    wrong and then never fire again."""
    seen: list[float] = []
    perf = guard._load_recorder()
    monkeypatch.setattr(perf, "record", lambda name, ms: seen.append(ms))

    guard.main(["--seconds", "1.5"])

    assert seen == [1500.0]


def test_it_uses_the_shared_perf_ratchet_module():
    """Reuse is the requirement, not an implementation detail: a second
    baseline file or a second jitter allowance would be this project's own
    defect class inside the tooling built to prevent it."""
    perf = guard._load_recorder()

    assert hasattr(perf, "record")
    assert hasattr(perf, "TOLERANCE")
    assert perf.BASELINE_PATH.name == "perf_baseline.json"


def test_the_measurement_name_is_a_constant():
    """Renaming a measurement resets its ratchet to whatever the next run
    manages. Pinning it makes that a deliberate edit rather than a typo."""
    assert guard.DEFAULT_MEASUREMENT == "ios.compile_ms"


def test_a_first_run_does_not_fail(monkeypatch):
    """First-recorded-run semantics come from `perf_ratchet`, which writes a
    baseline instead of failing. Asserted here so that behaviour cannot be
    lost by someone adding a "must have a baseline" precondition to this
    script."""
    perf = guard._load_recorder()
    monkeypatch.setattr(perf, "_load_baseline", lambda unit="ms": {})
    monkeypatch.setattr(perf, "_write_baseline", lambda *a, **k: None)
    monkeypatch.setattr(perf, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(perf, "_another_perf_run_is_active", lambda: False)

    assert guard.main(["--seconds", "300.0"]) == 0
