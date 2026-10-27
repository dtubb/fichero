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
import os
import signal
import sys
import tempfile
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


def _provider_rows(base: str, models: str) -> None:
    """Settings > AI rows for the temp engine, written to ITS app database before it boots (never the owner's: the base path is
    a fresh temp dir). The rules pick among the models of the person's provider rows; the key itself is sent over the transport."""
    os.environ["FICHERO_BASE_PATH"] = base
    from fichero_server.db.app import get_app_db
    from fichero_server.models import Model, Provider, ProviderType

    db, rows = get_app_db(), {}
    for spec in models.split(","):
        provider, model = spec.split(":", 1)
        if provider not in rows:
            rows[provider] = db.save_provider(Provider(name=provider, provider_type=ProviderType(provider)))
        db.save_model(Model(provider_id=rows[provider].id, name=model, model_id=model, capabilities=["text", "vision"]))
    db.close()
    os.environ.pop("FICHERO_BASE_PATH", None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages")
    ap.add_argument("--extra")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cloud", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    ap.add_argument("--library", help="an existing .fichero package to open (a copy of an earlier run's): the pages are not imported again")
    ap.add_argument("--no-start", action="store_true", help="import and set up, do not press Start (then --extra can still run)")
    ap.add_argument("--models", default="google:gemini-2.5-flash,anthropic:claude-haiku-4-5", help="provider:model rows to add (--cloud)")
    ap.add_argument("--only", default="", help="keep only these step ids in the stored recipe (comma list)")
    ap.add_argument("--keys", default="anthropic,google", help="providers whose key is read here and given to the temp engine (--cloud)")
    ap.add_argument("--language", default="la")
    ap.add_argument("--script", default="Latn")
    ap.add_argument("--purposes", default="transcribe,translate-normalise,entities,statements,search,catalogue")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "cloud": args.cloud}
    import httpx

    os.environ["FICHERO_FEATURE_TIER"] = "beta"  # the keys route is beta-tier; the temp engine inherits it
    base = tempfile.mkdtemp(prefix="fich_base_")
    if args.cloud:
        _provider_rows(base, args.models)
    for sig in (signal.SIGTERM, signal.SIGHUP):  # a killed script still runs `finally`, which stops its temp engine
        signal.signal(sig, lambda signum, _frame: sys.exit(128 + signum))
    ep = start_engine(transport="uds", log_dir=str(out), base_path=base)
    try:
        headers = {"Authorization": f"Bearer {ep.token}"}
        library = args.library or str(Path(tempfile.mkdtemp(prefix="e2e_", dir="/tmp")) / "e2e.fichero")  # /tmp is an allowed library root
        report["library"] = library
        headers["X-Fichero-Library-Path"] = library
        with httpx.Client(timeout=120, headers=headers, **ep.httpx_kwargs()) as client:
            if args.cloud:
                # The app owns the keychain and pushes a key to its engine over the authenticated transport, held in memory
                # (#4534). This stands in for the app: the key is read here and sent to the throwaway engine, never printed or kept.
                from fichero_server.llm import get_api_key

                supplied = []
                for provider in args.keys.split(","):
                    key = get_api_key(provider)
                    if key:
                        r = client.post(f"/api/providers/{provider}/api-key", json={"api_key": key})
                        if r.status_code != 200:
                            report.setdefault("key_errors", {})[provider] = f"{r.status_code} {r.text[:200]}"
                        else:
                            supplied.append(provider)
                    del key
                report["keys_supplied_for"] = supplied
            client.post("/api/library", json={"path": library}).raise_for_status()
            report["engine_log"] = ep.log_path
            if not args.library:
                _import(client, args.pages, report, "pages")
            body = {"purposes": args.purposes.split(","), "languages": [args.language], "scripts": [args.script],
                    "materials": ["handwriting"], "cloud_allowed": args.cloud, "pages": 5}
            r = client.post("/api/recipes/assemble", json=body)
            r.raise_for_status()
            assembled = r.json()
            report["assembled_steps"] = [s.get("job") for s in assembled.get("steps", [])]
            report["assembled_notes"] = {k: assembled.get(k) for k in ("gaps", "by_hand", "left_off", "removed")}
            if args.only:  # run just these steps (the rest of the carried library is already done)
                assembled["steps"] = [x for x in assembled["steps"] if x.get("job") in args.only.split(",")]
            answers = {k: body[k] for k in ("purposes", "languages", "scripts", "materials", "cloud_allowed", "pages")}
            answers["cloud_spend_cap_usd"] = 0.5  # the manager's cap for the e2e
            if args.library:
                # A library carried over from another machine holds that machine's recipe: assemble again here, with the keys here.
                r = client.put("/api/recipes/project", json={"answers": answers, "recipe": assembled})
            else:
                # Answers alone: the engine assembles and stores the recipe itself (#5747), as Set Up's Continue does.
                r = client.put("/api/recipes/project", json={"answers": answers})
            r.raise_for_status()
            if args.cloud:
                client.post("/api/recipes/project/allow-cloud").raise_for_status()
            plan = client.get("/api/recipes/project/start")
            plan.raise_for_status()
            report["plan"] = plan.json()
            (out / "plan.json").write_text(json.dumps(report["plan"], indent=1, default=str))
            if not (args.plan_only or args.no_start):
                started = client.post("/api/recipes/project/start", json={})
                if started.status_code != 200:
                    report["start_refused"] = started.text[:2000]
                else:
                    job = (started.json().get("started") or {}).get("job_id")
                    report["run_id"] = job
                    run = _wait(client, f"/api/recipes/project/runs/{job}",
                                lambda b: (b.get("state") or "") not in ("", "queued", "running", "waiting", "paused", "pending"),
                                every=5, limit=7200, say=lambda b: print(time.strftime("%H:%M:%S"), b.get("state") or b.get("status"), flush=True))
                    report["run"] = run
                    report["stages"] = _stages(run)
                    summary = client.get(f"/api/recipes/project/runs/{job}/summary")
                    report["summary"] = summary.json() if summary.status_code == 200 else summary.text[:500]
            if report.get("run_id"):
                # What the project's spend record says after the run, to set beside the plan's projection (`cloud_cap` of the plan).
                again = client.get("/api/recipes/project/start")
                report["cloud_cap_before"] = (report["plan"] or {}).get("cloud_cap")
                report["cloud_cap_after"] = again.json().get("cloud_cap") if again.status_code == 200 else again.text[:300]
            if args.extra and not args.plan_only:
                before = {r["job_id"] for r in client.get("/api/recipes/project/runs").json()["items"]}
                _import(client, args.extra, report, "extra")
                # The import's own run (material arrives: the plan runs on the new pages alone): wait for it.
                deadline = time.monotonic() + 3600
                new = None
                while time.monotonic() < deadline:
                    runs = client.get("/api/recipes/project/runs").json()["items"]
                    new = next((r for r in runs if r["job_id"] not in before), None)
                    if new and (new.get("state") or "") not in ("queued", "running", "waiting", "paused", "pending"):
                        break
                    print(time.strftime("%H:%M:%S"), "new-material run:", (new or {}).get("state"), ((new or {}).get("reason") or "")[:80], flush=True)
                    time.sleep(10)
                report["new_material_run"] = new
                report["new_material_stages"] = _stages(new or {})
    finally:
        ep.stop()
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: report[k] for k in report if k in ("started", "imports", "assembled_steps", "start_refused", "run_id")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
