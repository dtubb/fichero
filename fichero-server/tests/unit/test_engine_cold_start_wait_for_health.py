"""`wait_for_health` — the polling loop the cold-start perf test (#4441)
stands on — must tell "came up" from "never came up" (BLIND), not report a
timing for a process that crashed on boot.

tests/perf/test_engine_cold_start_perf.py is not collected by the default
unit run (deliberately — it spawns a real uvicorn subprocess), so this
imports it directly by file path and drives its polling function with fake
clock/sleep/get, synthesizing both outcomes rather than requiring a real
engine to be running.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PERF_TEST = REPO_ROOT / "fichero-server" / "tests" / "perf" / "test_engine_cold_start_perf.py"


def _import_perf_test():
    spec = importlib.util.spec_from_file_location("test_engine_cold_start_perf", PERF_TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeClock:
    """A controllable monotonic clock: `sleep` advances it deterministically
    so the loop's real-time behavior is tested without actually waiting."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_a_response_that_comes_up_immediately_is_healthy():
    module = _import_perf_test()
    clock = _FakeClock()
    healthy = module.wait_for_health(
        "http://fake/health", budget_s=5.0, poll_interval_s=0.1,
        get=lambda _url: _Response(200),
        now=clock.now, sleep=clock.sleep,
    )
    assert healthy is True


def test_a_response_that_comes_up_after_a_few_polls_is_healthy():
    module = _import_perf_test()
    clock = _FakeClock()
    calls = {"n": 0}

    def get(_url):
        calls["n"] += 1
        return _Response(200) if calls["n"] >= 3 else _Response(503)

    healthy = module.wait_for_health(
        "http://fake/health", budget_s=5.0, poll_interval_s=0.1,
        get=get, now=clock.now, sleep=clock.sleep,
    )
    assert healthy is True
    assert calls["n"] == 3


def test_a_connection_error_is_retried_not_fatal():
    """A refused connection (nothing listening yet) is the NORMAL early
    state of this loop, not a failure — it must keep polling."""
    module = _import_perf_test()
    clock = _FakeClock()
    calls = {"n": 0}

    def get(_url):
        calls["n"] += 1
        if calls["n"] < 3:
            import httpx
            raise httpx.ConnectError("connection refused", request=None)
        return _Response(200)

    healthy = module.wait_for_health(
        "http://fake/health", budget_s=5.0, poll_interval_s=0.1,
        get=get, now=clock.now, sleep=clock.sleep,
    )
    assert healthy is True
    assert calls["n"] == 3


class TestTheSynthesizedViolation:
    """The failure mode this loop exists to catch: an engine that crashes on
    boot (or never binds the port). Synthesized directly — `get` always
    fails — never borrowed from a real crash log."""

    def test_a_process_that_never_becomes_healthy_reports_unhealthy(self):
        module = _import_perf_test()
        clock = _FakeClock()

        def always_fails(_url):
            import httpx
            raise httpx.ConnectError("connection refused", request=None)

        healthy = module.wait_for_health(
            "http://fake/health", budget_s=1.0, poll_interval_s=0.1,
            get=always_fails, now=clock.now, sleep=clock.sleep,
        )
        assert healthy is False

    def test_it_gives_up_at_the_budget_not_before_and_not_after(self):
        module = _import_perf_test()
        clock = _FakeClock()

        def always_fails(_url):
            import httpx
            raise httpx.ConnectError("connection refused", request=None)

        module.wait_for_health(
            "http://fake/health", budget_s=1.0, poll_interval_s=0.1,
            get=always_fails, now=clock.now, sleep=clock.sleep,
        )
        # The fake clock only advances via `sleep`, called once per failed
        # poll — so the elapsed time is bounded to (budget, budget + one
        # poll interval), never near-instant (a loop that gives up on the
        # FIRST failure would silently turn "the machine hiccuped once"
        # into "the engine is unreachable").
        assert 1.0 <= clock.now() < 1.0 + 0.2

    def test_a_500_is_not_healthy_either(self):
        """Only a real 200 counts — a responding-but-broken process (a 500
        from a half-initialized app) must not be reported as healthy."""
        module = _import_perf_test()
        clock = _FakeClock()
        healthy = module.wait_for_health(
            "http://fake/health", budget_s=0.3, poll_interval_s=0.1,
            get=lambda _url: _Response(500),
            now=clock.now, sleep=clock.sleep,
        )
        assert healthy is False
