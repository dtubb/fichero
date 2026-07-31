"""Performance ratchet: it may not get slower, and it tightens as it gets faster.

The absolute budgets in these tests (4 seconds for an entity list) only catch a
single-step disaster. A run that drifts 0.4s -> 3.9s passes every one of them —
a tenfold slowdown, invisible, because nothing compares a run to any other run
(#4439).

A tripwire at some multiple of "recent" cannot fix that either: if the recent
window keeps absorbing each new slower number, the bar drifts up with the
regression it was meant to catch. Fifty acceptable 5% slowdowns are a 12x
slowdown, and every one of them passes.

So this is a RATCHET, in the direction the project wants to move:

  * `perf_baseline.json` records the best time each measurement has achieved.
  * A run slower than that baseline (plus a jitter allowance) FAILS.
  * A run meaningfully faster REWRITES the baseline — the bar tightens itself,
    permanently, with no one having to remember to lower it.
  * Loosening the bar requires editing the committed baseline by hand, with a
    reason. That is deliberately annoying: a slower Fichero should cost someone
    a sentence explaining why it is worth it.

Getting faster is free and automatic. Getting slower is a decision someone has
to make on purpose and write down.
"""

from __future__ import annotations

import json
import os
import time
import subprocess
from pathlib import Path

_PERF_DIR = Path(__file__).resolve().parent

# The committed ratchet: measurement name -> best milliseconds ever recorded.
BASELINE_PATH = _PERF_DIR / "perf_baseline.json"

# Every run, appended. The baseline says what we hold ourselves to; the log says
# what actually happened, so a regression can be traced to a commit.
HISTORY_PATH = _PERF_DIR / "history.jsonl"

# How much worse than the baseline a run may be before it fails.
#
# This is a JITTER allowance, not a slowdown allowance: a laptop running a build
# in another window genuinely produces slower numbers, and a check that fails on
# that gets switched off, which is worse than no check. It does NOT accumulate —
# the baseline itself never moves up, so this tolerance is measured against the
# best time forever, not against last week's slightly-worse time.
TOLERANCE = 1.35

# A run must beat the baseline by this much to tighten it. Without a margin the
# baseline would chase the luckiest sample on the fastest machine and every
# other machine would fail forever.
TIGHTEN_MARGIN = 0.90

# Below this, scheduling noise dwarfs any change worth acting on.
NOISE_FLOOR_MS = 25.0


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=_PERF_DIR,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _load_baseline() -> dict[str, float]:
    if not BASELINE_PATH.exists():
        return {}
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Fail loudly: a corrupt ratchet silently becomes no ratchet.
        raise AssertionError(
            f"{BASELINE_PATH} is not valid JSON. The performance ratchet cannot "
            f"run without it — restore it from git rather than deleting it, or "
            f"every measurement starts over at whatever today's machine manages."
        ) from None
    return {k: float(v["ms"]) for k, v in data.items() if isinstance(v, dict) and "ms" in v}


def _write_baseline(name: str, ms: float, note: str) -> None:
    """Read-modify-write the ratchet, atomically.

    Two pytest processes can run this suite at once — the gate's perf leg and
    someone running the file directly, which happened while this was being
    built. A plain write_text there interleaves and can leave the ratchet
    truncated or missing another measurement's entry, and a lost ratchet is a
    silently absent guardrail.

    os.replace is atomic on POSIX, so a reader sees the old file or the new one
    and never a half-written one. This still cannot merge two simultaneous
    writers perfectly — last writer wins for the whole file — but it can no
    longer corrupt it, and both writers are recording the same measurements.
    """
    data: dict = {}
    if BASELINE_PATH.exists():
        try:
            data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data[name] = {"ms": round(ms, 1), "commit": _commit(), "note": note}
    tmp = BASELINE_PATH.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, BASELINE_PATH)


def _append_history(name: str, ms: float, verdict: str) -> None:
    row = {"name": name, "ms": round(ms, 2), "commit": _commit(), "verdict": verdict}
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def _another_perf_run_is_active() -> bool:
    """Is a second perf suite running right now?

    `gate` serialises its legs under a global lock, so the gate's own perf run
    has the machine. A run started OUTSIDE that lock does not — and one was,
    while this was being built: two pytest processes on tests/perf at ~140% CPU
    each, both writing the same baseline.

    Numbers measured under that contention are wrong in the sticky direction. A
    ratchet keeps the best time forever, so one bad baseline is a bar nobody can
    meet and one lucky baseline is a bar that hides real regressions.
    """
    try:
        out = subprocess.run(
            ["pgrep", "-f", "pytest.*tests/perf"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False  # cannot tell -> do not block the suite
    pids = {p for p in out.stdout.split() if p.strip() and p.strip() != str(os.getpid())}
    return len(pids) > 1


def record(name: str, ms: float) -> None:
    """Hold `name` to its best-ever time, and tighten when it beats it.

    `name` is the stable identity of a measurement. Rename it and its ratchet
    resets to whatever the next run happens to manage — so don't.
    """
    if _another_perf_run_is_active():
        # Measure, report, record NOTHING. A contended number must not become
        # the bar in either direction.
        print(
            f"\n[perf] {name}: {ms:.1f} ms — NOT recorded: another perf run is "
            f"active, so this machine was shared and the number is unreliable. "
            f"Run `gate perf` (which takes the gate lock) to record."
        )
        return

    if os.environ.get("FICHERO_PERF_NO_HISTORY") == "1":
        # For a machine already known to be thrashing. Records nothing: a bad
        # number must never become the baseline, and a lucky one must not
        # either.
        print(f"\n[perf] {name}: {ms:.1f} ms (ratchet disabled)")
        return

    baseline = _load_baseline().get(name)

    if baseline is None:
        _write_baseline(name, ms, "first recorded run")
        _append_history(name, ms, "baseline")
        print(f"\n[perf] {name}: {ms:.1f} ms — baseline set")
        return

    ceiling = baseline * TOLERANCE

    if ms > ceiling and ms > NOISE_FLOOR_MS:
        _append_history(name, ms, "REGRESSION")
        raise AssertionError(
            f"{name} took {ms:.1f} ms; the best recorded is {baseline:.1f} ms "
            f"(ceiling {ceiling:.1f} ms with jitter allowance).\n"
            f"\n"
            f"This is a RATCHET, not a budget — it does not care that the number "
            f"is under some absolute limit. Fichero is meant to get faster over "
            f"time, so a slower run has to be a decision someone makes on purpose.\n"
            f"\n"
            f"If the machine was busy, re-run on a quiet one.\n"
            f"If this is a REAL and accepted slowdown, raise the entry for "
            f"'{name}' in {BASELINE_PATH.name} and say in the note what bought "
            f"the time."
        )

    if ms < baseline * TIGHTEN_MARGIN:
        _write_baseline(name, ms, f"tightened from {baseline:.1f} ms")
        _append_history(name, ms, "tightened")
        print(
            f"\n[perf] {name}: {ms:.1f} ms — FASTER than {baseline:.1f} ms. "
            f"Ratchet tightened; this is the bar now."
        )
        return

    _append_history(name, ms, "ok")
    print(f"\n[perf] {name}: {ms:.1f} ms (best {baseline:.1f} ms)")


class _Measurement:
    """One timed block. `ms` is readable afterwards for an extra assertion."""

    __slots__ = ("name", "ms", "_start")

    def __init__(self, name: str) -> None:
        self.name = name
        self.ms = 0.0
        self._start = 0.0

    def __enter__(self) -> "_Measurement":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.ms = (time.perf_counter() - self._start) * 1000
        # A failing test's timing is meaningless — it may not have done the
        # work. Record nothing and let the real failure through.
        if exc_type is None:
            record(self.name, self.ms)
        return False


def measure(name: str) -> _Measurement:
    """Time a block and hold it to its best-ever result.

    Perf is a property of a piece of behaviour, not a separate suite. Any test
    anywhere can put its own slow part under the ratchet:

        def test_listing_entities(perf, client):
            with perf("entities.list.full"):
                r = client.get("/api/entities?limit=500")
            assert r.status_code == 200

    The name is the measurement's identity across runs and must be stable —
    rename it and its ratchet silently starts over at whatever today's machine
    manages. Prefer `area.thing` so related measurements sort together.
    """
    return _Measurement(name)


# ---------------------------------------------------------------------------
# Every test, automatically
# ---------------------------------------------------------------------------
#
# `measure()` above is for a named slice inside a test. This is the blunt
# version Daniel asked for: EVERY test is timed and held to its best, so a
# slowdown shows up in whatever suite you happen to be running rather than
# waiting for the perf leg.
#
# Two things make that affordable:
#
#   * Only tests above the noise floor are kept. Most of ~7,500 tests run in
#     single-digit milliseconds where scheduling noise dwarfs any real change,
#     and recording them would be thousands of meaningless bars.
#   * Everything is collected in memory and written ONCE at session end. The
#     per-measurement path shells out to git and rewrites a JSON file; doing
#     that per test would cost more than the tests.

_session: dict[str, float] = {}


def note_test_duration(nodeid: str, seconds: float) -> None:
    """Remember one test's duration. Cheap: a dict write."""
    ms = seconds * 1000
    if ms < NOISE_FLOOR_MS:
        return
    # Keep the FASTEST observation within a session: a parametrised test or a
    # retry should be judged on its best, same as across sessions.
    key = f"test::{nodeid}"
    if ms < _session.get(key, float("inf")):
        _session[key] = ms


def flush_session() -> list[str]:
    """Compare everything collected, tighten what improved, write once.

    Returns human-readable regression lines — empty when all is well. The
    caller decides whether that fails the run, because "is a slow test a
    failure?" is a policy question and this module only measures.
    """
    entries = dict(_session)
    _session.clear()
    if not entries or os.environ.get("FICHERO_PERF_NO_HISTORY") == "1":
        return []
    if _another_perf_run_is_active():
        return []

    baseline = _load_baseline()
    commit = _commit()
    regressions: list[str] = []
    data: dict = {}
    if BASELINE_PATH.exists():
        try:
            data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

    changed = False
    for name, ms in sorted(entries.items()):
        best = baseline.get(name)
        if best is None:
            data[name] = {"ms": round(ms, 1), "commit": commit, "note": "first recorded run"}
            changed = True
        elif ms > best * TOLERANCE:
            regressions.append(
                f"{name}: {ms:.0f} ms vs best {best:.0f} ms ({ms / best:.1f}x)"
            )
        elif ms < best * TIGHTEN_MARGIN:
            data[name] = {
                "ms": round(ms, 1), "commit": commit,
                "note": f"tightened from {best:.1f} ms",
            }
            changed = True

    if changed:
        tmp = BASELINE_PATH.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, BASELINE_PATH)

    return regressions
