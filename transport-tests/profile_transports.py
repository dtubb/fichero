#!/usr/bin/env python3
"""Repeatable transport profiling harness for the Fichero engine.

Measures and prints a comparison table, and writes results to JSON so runs are
diffable. Dependency-light: stdlib + httpx (from the dev venv).

Metrics
-------
* Cold import       : wall time to `import fichero_server.api.main` in a FRESH
                      interpreter (baseline for engine launch cost).
* Per-request p50/p95: latency over N requests to /api/health for each transport
                      we can drive from Python:
                        - uds : httpx over a Unix-domain socket
                        - tcp : httpx to a plain-HTTP 127.0.0.1 loopback port
* Streaming TTFB    : time-to-first-byte on a streaming endpoint (if present),
                      UDS vs TCP; else reported as "none available".

Out of scope (noted, not measured): the Swift/PythonKit IN-MEMORY ASGI transport
(AsyncHTTPClientTransport driving the app in-process) — not reachable from a pure
Python harness. The app-side "launch-to-first-authenticated-response p95" layers
on top of these numbers later.

Usage
-----
Run from the repo root, with the shared venv activated (`source .venv/bin/activate`):

    PYTHONPATH=fichero-server/src \
        python transport-tests/profile_transports.py --n 200 --out results.json

`engine_src()` (see `_engine_harness.py`) defaults to `fichero-server/src`
relative to this file's own location, so PYTHONPATH above is belt-and-braces
for the parent process; the subprocess it launches gets it either way.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import engine_src, start_engine  # noqa: E402

HEALTH = "/api/health"
# A candidate streaming endpoint; skipped gracefully if absent / needs a library.
# `/api/changes/stream` (#1863) is the real per-library change-event SSE route
# as of the #4227 rename; the pre-rename harness guessed at a path that never
# existed, which is why this always reported "none available".
STREAM_CANDIDATES = ("/api/changes/stream",)


def measure_cold_import(repeats: int = 1) -> dict:
    """Time `import fichero_server.api.main` in a fresh interpreter (worst-case: cold)."""
    src = engine_src()
    snippet = (
        "import time; t=time.perf_counter(); import fichero_server.api.main; "
        "print(time.perf_counter()-t)"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["FICHERO_MULTIUSER"] = "0"
    samples = []
    for _ in range(repeats):
        out = subprocess.run(
            [sys.executable, "-c", snippet],
            env=env, capture_output=True, text=True,
        )
        if out.returncode != 0:
            raise RuntimeError(f"cold-import failed:\n{out.stderr[-1500:]}")
        samples.append(float(out.stdout.strip().splitlines()[-1]))
    return {"seconds": round(min(samples), 3), "samples": [round(s, 3) for s in samples]}


def measure_latency(ep, n: int, warmup: int = 10) -> dict:
    """p50/p95 latency (ms) over N GET /api/health on a persistent connection."""
    latencies = []
    with httpx.Client(timeout=30, **ep.httpx_kwargs()) as client:
        for _ in range(warmup):
            client.get(HEALTH)
        for _ in range(n):
            t0 = time.perf_counter()
            r = client.get(HEALTH)
            dt = (time.perf_counter() - t0) * 1000.0
            r.raise_for_status()
            latencies.append(dt)
    latencies.sort()
    return {
        "n": n,
        "p50_ms": round(statistics.median(latencies), 3),
        "p95_ms": round(_percentile(latencies, 95), 3),
        "min_ms": round(latencies[0], 3),
        "max_ms": round(latencies[-1], 3),
        "mean_ms": round(statistics.fmean(latencies), 3),
    }


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def measure_stream_ttfb(ep) -> dict | None:
    """TTFB (ms) on the first available streaming endpoint, else None."""
    headers = {"Authorization": f"Bearer {ep.token}"}
    last = "no candidates"
    for path in STREAM_CANDIDATES:
        try:
            with httpx.Client(timeout=8, **ep.httpx_kwargs()) as client:
                t0 = time.perf_counter()
                with client.stream("GET", path, headers=headers) as resp:
                    if resp.status_code >= 400:
                        last = f"{path} -> HTTP {resp.status_code}"
                        continue
                    for _chunk in resp.iter_raw():
                        ttfb = (time.perf_counter() - t0) * 1000.0
                        return {"endpoint": path, "ttfb_ms": round(ttfb, 3)}
                    # stream ended with no bytes
                    return {"endpoint": path, "ttfb_ms": None,
                            "note": "stream produced no bytes before close"}
        except Exception as exc:  # noqa: BLE001
            last = f"{path} -> {exc}"
            continue
    return {"endpoint": None, "note": f"no drivable streaming endpoint (last: {last})"}


def _fmt(v):
    return "n/a" if v is None else f"{v:.3f}"


def print_table(results: dict) -> None:
    ci = results["cold_import"]
    print("\n" + "=" * 66)
    print("Fichero transport profile  —  " + results["timestamp"])
    print("=" * 66)
    print(f"Cold import (import fichero_server.api.main): {ci['seconds']:.3f} s"
          f"  (samples: {ci['samples']})")
    print("-" * 66)
    print(f"{'transport':<10}{'n':>6}{'p50 ms':>12}{'p95 ms':>12}"
          f"{'mean ms':>12}{'max ms':>12}")
    print("-" * 66)
    for name in ("uds", "tcp"):
        lat = results["latency"].get(name)
        if not lat:
            print(f"{name:<10}{'—  (not measured)':>42}")
            continue
        print(f"{name:<10}{lat['n']:>6}{_fmt(lat['p50_ms']):>12}"
              f"{_fmt(lat['p95_ms']):>12}{_fmt(lat['mean_ms']):>12}"
              f"{_fmt(lat['max_ms']):>12}")
    print("-" * 66)
    st = results["stream_ttfb"]
    for name in ("uds", "tcp"):
        entry = st.get(name)
        if not entry:
            continue
        if entry.get("endpoint") and entry.get("ttfb_ms") is not None:
            print(f"stream TTFB [{name}] {entry['endpoint']}: {entry['ttfb_ms']:.3f} ms")
        else:
            print(f"stream TTFB [{name}]: {entry.get('note', 'none available')}")
    # relative summary
    uds = results["latency"].get("uds")
    tcp = results["latency"].get("tcp")
    if uds and tcp and tcp["p50_ms"]:
        delta = (tcp["p50_ms"] - uds["p50_ms"]) / tcp["p50_ms"] * 100.0
        faster = "faster" if delta > 0 else "slower"
        print("-" * 66)
        print(f"UDS p50 is {abs(delta):.1f}% {faster} than TCP loopback p50.")
    print("=" * 66 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=200, help="requests per transport (default 200)")
    ap.add_argument("--out", default="results.json", help="JSON output path")
    ap.add_argument("--import-repeats", type=int, default=1,
                    help="cold-import repeats; reports the min (default 1)")
    ap.add_argument("--skip-tcp", action="store_true", help="profile UDS only")
    args = ap.parse_args()

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine_src": engine_src(),
        "requests_per_transport": args.n,
        "cold_import": {},
        "latency": {},
        "stream_ttfb": {},
    }

    print("[*] measuring cold import ...")
    results["cold_import"] = measure_cold_import(args.import_repeats)

    transports = ["uds"] if args.skip_tcp else ["uds", "tcp"]
    for tname in transports:
        print(f"[*] starting engine on {tname} ...")
        ep = start_engine(transport=tname)
        try:
            print(f"[*] profiling {args.n} requests over {tname} ...")
            results["latency"][tname] = measure_latency(ep, args.n)
            results["stream_ttfb"][tname] = measure_stream_ttfb(ep)
        finally:
            ep.stop()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[*] wrote {args.out}")
    print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
