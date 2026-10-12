#!/usr/bin/env python3
"""Re-run a scratch project's recipe and check what the MCP operator checked by hand (a dev tool, not shipped).

The operator's walk of 2026-10-11/12 on `~/Fichero Dev Test/MCP Night 1.fichero` (CACIQUES_INDIOS,17,D.5, 92 pages)
checked a run by eye. This does it again, the same way each time:

    scripts/realrun_check.py "~/Fichero Dev Test/MCP Night 1.fichero" --redo read-a-line,find-names-tag-words
    scripts/realrun_check.py "~/Fichero Dev Test/MCP Night 1.fichero" --dry-run     # read the last run only

It speaks only through the fichero CLI (`python -m fichero_cli --json`), on the running dev engine's socket
(FICHERO_UDS; never a URL, so nothing else on the network). It writes nothing beyond Start (`recipes
start-project`), and refuses a project outside ~/Fichero Dev Test. `--dry-run` writes nothing at all.
`--record FILE` saves what it read, so a run can be checked again offline (`--evidence FILE`) or become a fixture.

Exit 0 when no check failed; 1 when one did; 2 when it could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
DEV_TEST = "~/Fichero Dev Test"
SOCKET = "~/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock"
ENDED = ("done", "failed", "cancelled")
NAMES_JOBS = ("find-names-tag-words",)
BLANK_WHYS = ("a blank page: its image holds almost no ink", "a person called it blank")  # recipes/sorting.py
UNCERTAIN = re.compile(r"too uncertain .*\(the reader was \d+% sure, below \d+%\)")
LANGUAGES = {"es": "Spanish", "en": "English", "fr": "French", "pt": "Portuguese", "it": "Italian",
             "de": "German", "la": "Latin", "ca": "Catalan", "nl": "Dutch"}

PASS, FAIL, NA = "PASS", "FAIL", "n/a"


# ── The guard ────────────────────────────────────────────────────────────────────────────────────────────────


def scratch_project(path: str, root: str = DEV_TEST) -> Path:
    """The project's real path, when it is a .fichero package under ~/Fichero Dev Test; ValueError otherwise
    (a symlink out of the folder or a `..` is followed first, so neither gets past)."""
    real = Path(os.path.realpath(os.path.expanduser(path)))
    home = Path(os.path.realpath(os.path.expanduser(root)))
    if real.suffix != ".fichero" or home not in real.parents:
        raise ValueError(f"refused: {real} is not a .fichero project under {home}")
    return real


# ── The CLI ──────────────────────────────────────────────────────────────────────────────────────────────────


def cli_runner(project: Path, socket_path: str) -> Callable[..., Any]:
    """A function that runs one fichero CLI command on the engine's socket and returns its JSON."""
    env = {k: v for k, v in os.environ.items() if k not in ("FICHERO_API_URL", "FICHERO_LIBRARY_PATH")}
    env["FICHERO_UDS"] = os.path.expanduser(socket_path)  # forced: the CLI never dials a URL
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "fichero-cli/src"), str(REPO / "fichero-server/src")])

    def cli(*args: str, missing_ok: bool = False) -> Any:
        done = subprocess.run([sys.executable, "-m", "fichero_cli", "--json", "--library", str(project), *args],
                              env=env, capture_output=True, text=True, timeout=300)
        if done.returncode != 0:
            if missing_ok:
                return None
            raise RuntimeError(f"fichero {' '.join(args)} failed: {(done.stderr or done.stdout).strip()[:400]}")
        return json.loads(done.stdout or "null")

    return cli


def _items(answer: Any) -> list[dict[str, Any]]:
    return answer if isinstance(answer, list) else (answer or {}).get("items") or []


def _find(value: Any, key: str) -> list[Any]:
    """Every value under `key` anywhere in a JSON tree (a workflow's state nests its nodes' outputs)."""
    if isinstance(value, dict):
        return [v for k, v in value.items() if k == key] + [x for v in value.values() for x in _find(v, key)]
    if isinstance(value, list):
        return [x for v in value for x in _find(v, key)]
    return []


def is_names(step: dict[str, Any]) -> bool:
    return step.get("job") in NAMES_JOBS or any(s in NAMES_JOBS for s in step.get("steps") or [])


def left_out(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Every page a stage left out, once per page and reason."""
    seen, out = set(), []
    for entry in [e for s in evidence["status"]["steps"] for e in s.get("left_out") or []] + \
            list(evidence["summary"].get("left_out") or []):
        if (entry["page_id"], entry["why"]) not in seen:
            seen.add((entry["page_id"], entry["why"]))
            out.append(entry)
    return out


def gather(cli: Callable[..., Any], *, redo: list[str], dry_run: bool, every: float, hours: float,
           sleep: Callable[[float], None] = time.sleep, say: Callable[[str], None] = print) -> dict[str, Any]:
    """Start the recipe (not in a dry run), follow it to its end, and read what the checks look at."""
    seen: list[dict[str, Any]] = []
    if dry_run:
        runs = _items(cli("recipes", "runs"))
        if not runs:
            raise RuntimeError("the project has no recipe run to check")
        job_id = runs[0]["job_id"]
    else:
        plan = cli("recipes", "start-project", *[a for r in redo for a in ("--redo", r)])
        job_id = ((plan or {}).get("started") or {}).get("job_id")
        if not job_id:
            raise RuntimeError(f"Start queued no run: {json.dumps(plan)[:400]}")
    deadline = time.monotonic() + hours * 3600
    while True:
        status = cli("recipes", "run-status", job_id)
        seen.append({k: status.get(k) for k in ("state", "reason", "waiting_for", "estimate_seconds_left")})
        say(f"{time.strftime('%H:%M:%S')} {status['state']}: {status.get('reason') or ''}"
            + (f" (waiting for {status['waiting_for']})" if status.get("waiting_for") else ""))
        if dry_run or status["state"] in ENDED or time.monotonic() > deadline:
            break
        sleep(every)
    summary = cli("recipes", "run-summary", job_id)
    languages: dict[str, int] = {}
    for step in status["steps"]:
        if is_names(step) and step.get("child_id"):
            for used in _find(cli("workflow", "threads", "get-thread-status", step["child_id"], missing_ok=True),
                              "languages_used"):
                for name, n in (used or {}).items():
                    languages[name] = languages.get(name, 0) + int(n)
    folders: dict[str, list[str]] = {}
    folder_names: dict[str, str] = {}
    for root in _items(cli("docs", "list-roots")):
        pages = _items(cli("docs", "get-children", root["id"], "--level", "content", "--summary"))
        if pages:
            folders[root["name"]] = [p["name"] for p in pages]
            folder_names[root["id"]] = root["name"]
    proposals = [dict(p, folder=folder_names.get(p.get("folder_id") or "", p.get("folder_id")))
                 for p in _items(cli("find-documents", "list-proposals", "--summary"))]
    evidence = {"job_id": job_id, "dry_run": dry_run, "seen": [] if dry_run else seen, "status": status,
                "summary": summary, "setup": (cli("recipes", "get-project-setup") or {}).get("answers") or {},
                "languages_used": languages, "folders": folders, "proposals": proposals, "texts": {}}
    for entry in left_out(evidence):
        if entry["why"] in BLANK_WHYS:
            text = cli("segments", "get-document-text", entry["page_id"], missing_ok=True)
            evidence["texts"][entry["page_id"]] = (text or {}).get("text") or ""
    return evidence


# ── The checks: each (verdict, detail) from what `gather` read ───────────────────────────────────────────────


def _natural(name: str) -> list[Any]:
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", name)]


def natural_page_order(ev: dict[str, Any]) -> tuple[str, str]:
    if not ev["folders"]:
        return NA, "no folder with pages"
    for folder, names in ev["folders"].items():
        for a, b in zip(names, names[1:]):
            if _natural(a) > _natural(b):
                return FAIL, f"{folder}: {a!r} comes before {b!r}"
    return PASS, f"{sum(map(len, ev['folders'].values()))} pages in {len(ev['folders'])} folder(s)"


def blank_sheets_true_reasons(ev: dict[str, Any]) -> tuple[str, str]:
    entries = left_out(ev)
    if not entries:
        return NA, "nothing left out"
    wrong = [e for e in entries if e["why"] not in BLANK_WHYS and not UNCERTAIN.search(e["why"])]
    if wrong:
        return FAIL, f"{wrong[0]['page']}: {wrong[0]['why']!r}" + (f" (+{len(wrong) - 1})" if len(wrong) > 1 else "")
    for step in ev["status"]["steps"]:
        blank = sum(1 for e in step.get("left_out") or [] if e["why"] in BLANK_WHYS)
        if step.get("blank_versos") not in (None, blank):
            return FAIL, f"{step.get('job')}: blank_versos {step['blank_versos']} but {blank} named blank"
    return PASS, f"{sum(e['why'] in BLANK_WHYS for e in entries)} blank, each with its reason"


def no_written_page_left_out(ev: dict[str, Any]) -> tuple[str, str]:
    # ponytail: "written" = some reading has text for it; a page never read at all is not caught here.
    written = [e["page"] for e in left_out(ev) if (ev["texts"].get(e["page_id"]) or "").strip()]
    if written:
        return FAIL, f"left out as blank but has text: {', '.join(written[:5])}"
    return (PASS, f"{len(ev['texts'])} blank page(s), none with text") if ev["texts"] else (NA, "none left out blank")


def counts_add_up(ev: dict[str, Any]) -> tuple[str, str]:
    for step in ev["status"]["steps"]:
        a = step.get("account")
        if a and a["pages_done"] + a["pages_failed"] + a["pages_left"] != a["pages_total"]:
            return FAIL, (f"{step.get('job')}: {a['pages_done']} done + {a['pages_failed']} failed + "
                          f"{a['pages_left']} left != {a['pages_total']}")
    s = ev["summary"]
    blank = len({e["page_id"] for e in left_out(ev) if e["why"] in BLANK_WHYS})
    if s["pages_read"] + blank > s["pages"]:
        return FAIL, f"{s['pages_read']} read + {blank} blank > {s['pages']} pages"
    failed_reading = sum(f["pages_failed"] for f in s.get("failed") or [] if "read-a-line" in f["steps"])
    if s["finished"] and s["state"] == "done" and s["pages_read"] + blank + failed_reading < s["pages"]:
        return FAIL, (f"{s['pages'] - s['pages_read'] - blank - failed_reading} page(s) unaccounted: "
                      f"{s['pages_read']} read + {blank} blank + {failed_reading} failed of {s['pages']}")
    return PASS, f"{s['pages_read']} read + {blank} blank + {failed_reading} failed of {s['pages']}"


def progress_words(ev: dict[str, Any]) -> tuple[str, str]:
    said = [x["reason"] or "" for x in ev["seen"] if x["state"] == "running"]
    if not said:
        return NA, "not followed while running (dry run, or it ended before the first look)"
    pages = [r for r in said if re.search(r"\d+ of \d+ pages", r)]
    if not pages:
        return FAIL, f"never said its pages: {said[-1]!r}"
    left = [r for r in pages if "left" in r]
    return (PASS, left[-1]) if left else (FAIL, f"pages but never the time left: {pages[-1]!r}")


def never_waits_on_itself(ev: dict[str, Any]) -> tuple[str, str]:
    # ponytail: any "lane" wait while running counts; another recipe run is "Waiting for the recipe run …".
    words = [x.get("waiting_for") or "" for x in ev["seen"] + [ev["status"]] if x.get("state") == "running"]
    words += [x.get("reason") or "" for x in ev["seen"] + [ev["status"]]]
    bad = [w for w in words if "lane" in w or ev["job_id"] in w]
    return (FAIL, bad[0]) if bad else (PASS, f"{len(words)} line(s) read")


def names_did_pages(ev: dict[str, Any]) -> tuple[str, str]:
    names = [s for s in ev["status"]["steps"] if is_names(s)]
    ran = [s for s in names if s.get("account")]
    if not ran:
        return NA, "Names did not run in this run" if not names else f"Names: {names[0].get('why') or names[0]['state']}"
    done = sum(s["account"]["pages_done"] for s in ran)
    return (PASS, f"{done} pages done") if done > 0 else (FAIL, f"0 pages done ({ran[0]['state']})")


def uncertain_left_out_with_warning(ev: dict[str, Any]) -> tuple[str, str]:
    names_out = [e for s in ev["status"]["steps"] if is_names(s) for e in s.get("left_out") or []]
    vague = [e for e in names_out if "uncertain" in e["why"] and not UNCERTAIN.search(e["why"])]
    if vague:
        return FAIL, f"{vague[0]['page']}: no certainty named: {vague[0]['why']!r}"
    uncertain = [e for e in names_out if UNCERTAIN.search(e["why"])]
    return (PASS, f"{len(uncertain)} page(s), e.g. {uncertain[0]['page']}: {uncertain[0]['why']}") if uncertain \
        else (NA, "no page below the bar")


def project_language_used(ev: dict[str, Any]) -> tuple[str, str]:
    tags = ev["setup"].get("languages") or []
    if not tags:
        return NA, "the project names no language"
    used = {k: v for k, v in ev["languages_used"].items() if k.lower() != "unknown"}
    if not used:
        return NA, "Names reported no languages"
    want = LANGUAGES.get(tags[0].split("-")[0].lower(), tags[0])
    most = max(used, key=used.get)
    return (PASS if most == want else FAIL), f"project {tags[0]} ({want}); Names used {used}"


def find_documents_on(folder_match: str) -> Callable[[dict[str, Any]], tuple[str, str]]:
    def check(ev: dict[str, Any]) -> tuple[str, str]:
        if not any(s.get("card") == "find-documents" for s in ev["status"]["steps"]):
            return NA, "the recipe has no Find the Documents"
        mine = [p for p in ev["proposals"] if folder_match in str(p.get("folder") or "")
                and p.get("state", "current") == "current"]
        docs = [d for p in mine for d in p.get("documents") or []]
        dated = [d for d in docs if d.get("date")]
        detail = f"{len(docs)} document(s) proposed on {folder_match}, {len(dated)} dated"
        return (PASS if len(docs) > 1 and dated else FAIL), detail
    return check


def no_read_offer_on_names(ev: dict[str, Any]) -> tuple[str, str]:
    offers = [((s.get("account") or {}).get("offer") or {}).get("label") or "" for s in ev["status"]["steps"]
              if is_names(s)]
    offers += [f.get("offer") or "" for f in ev["summary"].get("failed") or []
               if any(x in NAMES_JOBS for x in f.get("steps") or [])]
    bad = [o for o in offers if o.startswith("Read ")]
    return (FAIL, bad[0]) if bad else (PASS, next((o for o in offers if o), "no offer"))


def checks(folder_match: str) -> list[tuple[str, Callable[[dict[str, Any]], tuple[str, str]]]]:
    return [("natural page order", natural_page_order),
            ("blank sheets caught, with true reasons", blank_sheets_true_reasons),
            ("no written page left out", no_written_page_left_out),
            ("counts add up", counts_add_up),
            ("progress says pages and time left", progress_words),
            ("never waits on its own lane", never_waits_on_itself),
            ("Names: not 0 pages done", names_did_pages),
            ("uncertain pages left out, with the warning (#5694, #5707)", uncertain_left_out_with_warning),
            ("the project's language used (#5708)", project_language_used),
            (f"Find the Documents: >1 document on {folder_match}, dated", find_documents_on(folder_match)),
            ("no \"Read\" offer on a names step", no_read_offer_on_names)]


def table(evidence: dict[str, Any], folder_match: str = "CACIQUES") -> tuple[list[tuple[str, str, str]], bool]:
    """Each check's (name, verdict, detail), and whether none failed. A check that throws on a shape it did not
    expect fails, naming what it could not read."""
    rows = []
    for name, check in checks(folder_match):
        try:
            verdict, detail = check(evidence)
        except (KeyError, TypeError, ValueError) as exc:
            verdict, detail = FAIL, f"could not read the run: {type(exc).__name__}: {exc}"
        rows.append((name, verdict, detail))
    return rows, all(v != FAIL for _, v, _ in rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", nargs="?", help="the scratch project's .fichero package, under ~/Fichero Dev Test")
    ap.add_argument("--redo", default="", help="step ids to run again, comma-separated (read-a-line,…)")
    ap.add_argument("--dry-run", action="store_true", help="start nothing: read and check the last run")
    ap.add_argument("--every", type=float, default=60.0, help="seconds between looks (default 60)")
    ap.add_argument("--hours", type=float, default=4.0, help="give up following after this long (default 4)")
    ap.add_argument("--socket", default=SOCKET, help="the dev engine's socket")
    ap.add_argument("--folder", default="CACIQUES", help="the folder Find the Documents is checked on")
    ap.add_argument("--record", help="save what was read to this JSON file")
    ap.add_argument("--evidence", help="check a recorded JSON file instead of the engine (reads nothing else)")
    args = ap.parse_args(argv)
    try:
        if args.evidence:
            evidence = json.loads(Path(args.evidence).read_text())
        else:
            if not args.project:
                ap.error("a project is needed unless --evidence is given")
            project = scratch_project(args.project)
            evidence = gather(cli_runner(project, args.socket), redo=[r for r in args.redo.split(",") if r],
                              dry_run=args.dry_run, every=args.every, hours=args.hours)
        if args.record:
            Path(args.record).write_text(json.dumps(evidence, indent=1))
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"realrun_check: {exc}", file=sys.stderr)
        return 2
    rows, ok = table(evidence, args.folder)
    width = max(len(n) for n, _, _ in rows)
    print(f"\nrun {evidence['job_id']} ({evidence['status']['state']})")
    for name, verdict, detail in rows:
        print(f"  {verdict:4}  {name:{width}}  {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
