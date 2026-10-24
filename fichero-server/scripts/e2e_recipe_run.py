#!/usr/bin/env python3
"""End-to-end recipe run on a TEMP engine: one Start through every stage to Catalogue, then new material (#6087 e2e).

  python fichero-server/scripts/e2e_recipe_run.py --pages DIR --out DIR [--extra DIR] [--cloud] [--plan-only]
         [--purposes transcribe,translate-normalise,entities,statements,search,catalogue] [--language es --script Latn]

Boots a throwaway engine (`_engine_harness.start_engine`: a fresh FICHERO_BASE_PATH, its own token, a UDS), makes a library in
--out, imports the pages, assembles the recipe for the purposes, prints the Start PLAN (the defaults table: each stage, its
model, where it runs, its estimate, what will not run and why), then, unless --plan-only, presses Start and waits, and writes
each stage's end. With --extra, imports a second folder afterwards and reports what ran again (only the new pages) and which
folders Catalogue redid. Real models, no stubs; --cloud lets a step use a cloud model (the engine reads its key itself: a key is
never read, printed or written here). Writes --out/report.json and --out/report.md.
Run it where the models are: Kraken on the Air, the cloud stages wherever the key is."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine_harness import start_engine  # noqa: E402

IMAGES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def _wait(client, path, done, *, every=3.0, limit=3600.0, say=None):
    start = time.monotonic()
    while True:
        r = client.get(path)
        r.raise_for_status()
        body = r.json()
        if say:
            say(body)
        if done(body):
            return body
        if time.monotonic() - start > limit:
            raise TimeoutError(f"{path} did not finish in {limit}s: {json.dumps(body)[:500]}")
        time.sleep(every)


def _import(client, folder: str, report: dict, label: str):
    r = client.post("/api/ingest/folder", json={"path": folder, "mode": "copy", "recursive": True})
    r.raise_for_status()
    task = r.json()["task_id"]
    status = _wait(client, f"/api/ingest/status/{task}", lambda b: b.get("status") in ("completed", "failed", "error"), every=2)
    report.setdefault("imports", {})[label] = {k: status.get(k) for k in ("status", "imported", "total", "error", "errors") if k in status}
    return status


def _stages(run: dict) -> list[dict]:
    out = []
    for step in run.get("steps") or []:
        out.append({k: step.get(k) for k in ("steps", "job", "state", "why", "model", "provider", "place", "pages", "done", "failed",
                                              "estimate", "catalogue", "entries", "regions_found", "table", "reason") if k in step})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--extra")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cloud", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--language", default="la")
    ap.add_argument("--script", default="Latn")
    ap.add_argument("--purposes", default="transcribe,translate-normalise,entities,statements,search,catalogue")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "cloud": args.cloud}
    import httpx

    ep = start_engine(transport="uds", log_dir=str(out))
    try:
        headers = {"Authorization": f"Bearer {ep.token}"}
        library = str(out / "e2e.fichero")
        headers["X-Fichero-Library-Path"] = library
        with httpx.Client(timeout=120, headers=headers, **ep.httpx_kwargs()) as client:
            client.post("/api/library", json={"path": library}).raise_for_status()
            report["engine_log"] = ep.log_path
            _import(client, args.pages, report, "pages")
            body = {"purposes": args.purposes.split(","), "languages": [args.language], "scripts": [args.script],
                    "materials": ["handwriting"], "cloud_allowed": args.cloud, "pages": 5}
            r = client.post("/api/recipes/assemble", json=body)
            r.raise_for_status()
            assembled = r.json()
            report["assembled_steps"] = [s.get("job") for s in assembled.get("recipe", {}).get("steps", [])]
            r = client.put("/api/recipes/project", json={"answers": {k: body[k] for k in ("purposes", "languages", "scripts", "materials", "cloud_allowed", "pages")},
                                                         "recipe": assembled["recipe"]})
            r.raise_for_status()
            if args.cloud:
                client.post("/api/recipes/project/allow-cloud").raise_for_status()
            plan = client.get("/api/recipes/project/start")
            plan.raise_for_status()
            report["plan"] = plan.json()
            (out / "plan.json").write_text(json.dumps(report["plan"], indent=1, default=str))
            if not args.plan_only:
                started = client.post("/api/recipes/project/start", json={})
                if started.status_code != 200:
                    report["start_refused"] = started.text[:2000]
                else:
                    job = (started.json().get("job_id") or started.json().get("run_id"))
                    report["run_id"] = job
                    run = _wait(client, f"/api/recipes/project/runs/{job}",
                                lambda b: (b.get("state") or b.get("status")) in ("done", "failed", "cancelled", "partial", "completed"),
                                every=5, limit=7200, say=lambda b: print(time.strftime("%H:%M:%S"), b.get("state") or b.get("status"), flush=True))
                    report["run"] = run
                    report["stages"] = _stages(run)
                    summary = client.get(f"/api/recipes/project/runs/{job}/summary")
                    report["summary"] = summary.json() if summary.status_code == 200 else summary.text[:500]
                if args.extra and "run" in report:
                    _import(client, args.extra, report, "extra")
                    time.sleep(10)
                    runs = client.get("/api/recipes/project/runs").json()
                    report["runs_after_extra"] = runs
    finally:
        ep.stop()
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in report if k in ("started", "imports", "assembled_steps", "start_refused", "run_id")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
