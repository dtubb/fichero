"""Training in the recipe (#5660 item 9, `source.recipe.train-offered-per-step`): for each step a model can be
trained for, the Start plan offers "Train a model of your own for this step", offered later, never run at Start
(`source.recipe.train-never-automatic`). Under the setting `here`, a ready offer starts by itself on this Mac when a
recipe step finishes (`start_when_ready`, #5440), once.

Each offer names the ways to train (fine-tune or distil), and for each the places the engine can run it and the
audited action that starts it: only trainers and places the engine already has. A way with no trainer here is
listed as not available yet, never offered as if it ran. Whether the project has enough corrected material is
the bake-off's one count (`bakeoff.ground_truth`, `bakeoff.readiness`) at the train step's line threshold, so the
offer says how many more lines and pages it needs in the same words.
"""
from __future__ import annotations

from typing import Any

TITLE = "Train a model of your own for this step"

THIS_MAC = {"place": "this-mac", "name": "this Mac"}
HF_JOBS = {"place": "huggingface-jobs", "name": "Hugging Face Jobs"}

#: The teacher that means the person's own corrected lines (`training.kraken_set.PERSON`, #5700).
PERSON = "person"

#: Per trainable job, its ways to train: (method, how, says, [(place, action that starts it)]); no places: not
#: available yet, with why. Places are the ones the engine trains on today; a cluster (ACENET) or another Mac
#: is not one yet (no training path), so neither is listed.
WAYS: dict[str, list[dict[str, Any]]] = {
    "read-a-line": [
        # The lines a person corrected are the lessons (#5700, teacher `person`): what the readiness counts, so it
        # comes first and is what starts by itself under `here`.
        {"method": "kraken", "how": "fine-tune", "teacher": PERSON,
         "says": "Fine-tune a Kraken reader on the lines you corrected",
         "targets": [(THIS_MAC, "training.start_here"), (HF_JOBS, "training.start")]},
        # The Kraken and MLX trainers can also learn from a teacher's line readings, distilling the reader the
        # project already uses.
        {"method": "kraken", "how": "distil",
         "says": "Train a reader on the lines you have corrected",
         "targets": [(THIS_MAC, "training.start_here"), (HF_JOBS, "training.start")]},
        {"method": "mlx-vision-lora", "how": "distil",
         "says": "Make a small, fast reader from the best model's readings",
         "targets": [(HF_JOBS, "training.start_vision_lora")]},
    ],
    "find-regions": [
        {"method": "yolo", "how": "fine-tune", "says": "Train the region finder on the regions you corrected",
         "targets": [(THIS_MAC, "training.start_regions_here")]},
    ],
    "find-names-tag-words": [
        {"method": "spacy-ner", "how": "fine-tune", "says": "Fine-tune a spaCy names model on your corrected names",
         "targets": [], "why": "not available yet: Fichero has no spaCy trainer"},
    ],
}


def method_for(job: str) -> Any:
    """The job's declared distil method (`recipes.jobs.DISTIL`, `source.distil.each-step-has-a-method`), or None."""
    from fichero_server.recipes.jobs import DISTIL

    return DISTIL.get(job)


#: The audited actions that need a teacher (the model whose line readings are the lessons).
_TAUGHT = frozenset({"training.start_here", "training.start", "training.start_vision_lora"})


#: A Mac with at least this much memory trains a Kraken reader itself by default (`source.onboard.auto.train-offer-comes`).
#: Stated, not measured: a measured figure replaces it (QUESTION-TO-MANAGER, #5440).
TRAIN_HERE_MIN_RAM_GB = 16
TRAINING_MODES = ("here", "huggingface", "offered")


#: What a $0 spend cap says, on the setting and on each Hugging Face place (#5769).
_CAP_HOLDS = "the project's Hugging Face spend cap is $0, so paid training is offered, never started by itself"
#: The attended first run on a cluster (`source.onboard.cluster-offer`): the steps the person takes before a cluster
#: trains unattended. ponytail: steps, not a start action; a cluster training path is not built yet.
CLUSTER_FIRST_RUN = ("Test the connection to the cluster (Settings › Compute, or fichero_hpc_test_cluster)",
                     "Dry-run the submission and read the job script (fichero_hpc_dry_run_submit)",
                     "Watch the first job to its end before leaving the next ones unattended")


def training_setting(answered: str | None, *, mac_memory_gb: float, hf_configured: bool,
                     stays_local: bool = False, spend_cap: float | None = None) -> dict[str, str]:
    """How training happens in this project; with `spend_cap` (`answers.spend_cap`, #5769) at $0, Hugging Face is never
    the setting: it falls back to `offered` and says so."""
    setting = _setting(answered, mac_memory_gb=mac_memory_gb, hf_configured=hf_configured, stays_local=stays_local)
    if setting["mode"] == "huggingface" and spend_cap is not None and spend_cap <= 0:
        return {"mode": "offered", "why": _CAP_HOLDS}
    return setting


def _setting(answered: str | None, *, mac_memory_gb: float, hf_configured: bool,
             stays_local: bool = False) -> dict[str, str]:
    """How training happens in this project, from setup's answer (`answers.training`) or, with none, from the machine
    (#5440, ruled 2026-10-17): here when this Mac has the memory, else Hugging Face when a token is set up, else offered
    on the Start plan. A choice that cannot be met falls back to `offered` and says why. A project that keeps its pages on
    this Mac never has Hugging Face (the way that leaves it is refused, `_ways`). Never an alert."""
    enough = mac_memory_gb >= TRAIN_HERE_MIN_RAM_GB
    hf_configured = hf_configured and not stays_local
    off_mac = "this project keeps its pages on this Mac, and Hugging Face would take them off it"
    if answered not in TRAINING_MODES:
        mode = "here" if enough else "huggingface" if hf_configured else "offered"
        return {"mode": mode, "why": {
            "here": "this Mac has the memory to train a reader itself",
            "huggingface": "this Mac is short of memory to train here, and Hugging Face is set up",
            "offered": ("this Mac is short of memory to train here, and " + (off_mac if stays_local else
                                                                              "Hugging Face is not set up"))}[mode]}
    if answered == "here" and not enough:
        return {"mode": "offered", "why": "this Mac has not enough memory to train a reader here"}
    if answered == "huggingface" and stays_local:
        return {"mode": "offered", "why": off_mac}
    if answered == "huggingface" and not hf_configured:
        return {"mode": "offered", "why": "no Hugging Face token is set up (Settings, AI providers, Hugging Face)"}
    return {"mode": answered, "why": "your choice in setup"}


def _does(mode: str) -> str:
    return {"here": "Training runs by itself on this Mac once the corrected lines reach the threshold.",
            "huggingface": "Training runs by itself on Hugging Face Jobs once the corrected lines reach the threshold.",
            "offered": "Training is offered here when the corrected lines reach the threshold; you start it."}[mode]


def _params(action: str, job: str, counts: dict[str, Any], teacher: str | None = None) -> dict[str, Any] | None:
    """What the app posts with `action`, as-is (#5660 item 9): the engine fills it, never the app. None when the
    engine cannot yet (no teacher: no reader has read this project's lines)."""
    scope = counts.get("scope_ids") or []
    if not scope:
        return None
    if action == "training.start_regions_here":
        return {"name": "regions", "scope_ids": scope}
    if action in _TAUGHT:
        teacher = teacher or counts.get("teacher")
        if not teacher:
            return None
        params = {"scope_ids": scope, "teacher": teacher}
        if action == "training.start_vision_lora":
            params["name"] = "student"
        # Hugging Face Jobs: `pages_may_leave` stays false; the person's yes is asked when they press start.
        return params
    return None


def _ways(job: str, *, stays_local: bool, counts: dict[str, Any] | None = None, spend_cap: float | None = None,
          clusters: list[str] | tuple[str, ...] = ()) -> list[dict[str, Any]]:
    counts = counts or {}
    out = []
    for way in WAYS[job]:
        targets = [{**place, "starts": action, "params": _params(action, job, counts, way.get("teacher")),
                    "held": _CAP_HOLDS if place is HF_JOBS and spend_cap is not None and spend_cap <= 0 else None}
                   for place, action in way["targets"]
                   if not (stays_local and place is not THIS_MAC)]  # pages kept on this Mac never leave it
        if any(t["place"] == HF_JOBS["place"] for t in targets):  # the free alternative beside every paid one
            targets += [{"place": "cluster", "name": name, "starts": None, "params": None, "held": None,
                         "first_run": list(CLUSTER_FIRST_RUN)} for name in clusters]
        why = way.get("why")
        if way["targets"] and not targets:
            why = "this project keeps its pages on this Mac, and this training runs only on Hugging Face Jobs"
        out.append({"method": way["method"], "how": way["how"], "says": way["says"], "targets": targets,
                    "available": bool(targets), "why": why})
    return out


def _regions_readiness(pages: int) -> dict[str, Any]:
    from fichero_server.recipes.bakeoff import MIN_PAGES, _plural

    more = max(0, MIN_PAGES - pages)
    sentence = None if not more else (
        f"Needs a person's regions on at least {MIN_PAGES} pages; this project has them on "
        f"{_plural(pages, 'page')}. Draw or correct the regions on {_plural(more, 'more page')}.")
    return {"ready": not more, "pages": pages, "min_pages": MIN_PAGES, "more_pages": more, "sentence": sentence}


def counted(db: Any) -> dict[str, Any]:
    """What the offers are counted on: the corrected pages and their lines (the bake-off's one counting rule), the
    imported pages nobody marked ground truth, and how many pages hold a person's regions."""
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.bakeoff import ground_truth, unmarked_import_pages
    from fichero_server.training.yolo_set import REGION_KINDS

    pages, _ = ground_truth(db, None)
    regions = {s.document_id for s in db.query(Segment, provenance_kind="human")
               if s.kind in REGION_KINDS and s.deleted_at is None}
    return {"pages": pages, "unmarked": unmarked_import_pages(db), "region_pages": len(regions),
            "teacher": _teacher(db), "scope_ids": _roots(db)}


def _teacher(db: Any) -> str | None:
    """The model that read lines on the most pages here: the reader a distillation learns from. None: nothing read."""
    from fichero_server.models import Artifact
    from fichero_server.models.segments import SegmentPass

    # A reader writes a pass of its own, or readings onto the page's lines from its page artifact (#5487), so both
    # name it (as `training.kraken_set.teacher_pass` matches them). A person's ground-truth pass never teaches here.
    pages: dict[str, set[str]] = {}
    for p in db.query(SegmentPass):
        if not p.deleted_at and p.model and not getattr(p, "ground_truth", False) and p.model not in ("human", "manual"):
            pages.setdefault(p.model, set()).add(p.document_id)
    for a in db.query(Artifact, artifact_type="transcription"):
        if a.model and a.model not in ("human", "manual"):
            pages.setdefault(a.model, set()).add(a.document_id)
    return max(pages, key=lambda m: (len(pages[m]), m)) if pages else None


def _roots(db: Any) -> list[str]:
    """The project's top-level live items: what a training run looks through when no folder is chosen."""
    from fichero_server.models import Document

    return sorted(d.id for d in db.query(Document, parent_id=None) if not d.deleted_at)


def train_offers(recipe: dict | None, counts: dict[str, Any], *, stays_local: bool,
                 setting: dict[str, str] | None = None, spend_cap: float | None = None,
                 clusters: list[str] | tuple[str, ...] = (), noise_band: dict[str, Any] | None = None
                 ) -> list[dict[str, Any]]:
    """One offer per recipe step a model can be trained for, in the recipe's order."""
    from fichero_server.recipes.assemble import TRAIN_OFFERED_FROM_LINES
    from fichero_server.recipes.bakeoff import readiness

    setting = setting or {"mode": "offered", "why": "no setting given"}
    steps = (recipe or {}).get("steps") or []
    # The recipe's train step sets the line threshold for the step it trains (its `settings.base`).
    at_least = {(s.get("settings") or {}).get("base"): (s.get("offered_when") or {}).get("corrected_lines_at_least")
                for s in steps if s.get("job") == "train-a-model"}
    offers = []
    for step in steps:
        job = step.get("job")
        if job not in WAYS:
            continue
        ways = _ways(job, stays_local=stays_local, counts=counts, spend_cap=spend_cap, clusters=clusters)
        if not any(w["available"] for w in ways):
            # Nothing here can train it: no count of corrections to ask for (#5659: the names step asked for
            # 2,000 corrected lines, which no spaCy trainer would read).
            ready = {"ready": False, "sentence": None}
        elif job == "find-regions":
            ready = _regions_readiness(counts["region_pages"])
        else:
            ready = readiness(counts["pages"], counts["unmarked"],
                              min_lines=at_least.get(job) or at_least.get(step.get("id")) or TRAIN_OFFERED_FROM_LINES)
        offers.append({"step": step.get("id", job), "job": job, "title": TITLE, "ways": ways, "readiness": ready,
                       "setting": setting, "does": _does(setting["mode"]), "noise_band": noise_band})
    return offers


#: The jobs a start on this Mac makes; one that is waiting, running, paused or done means training has started.
_HERE_KINDS = ("train-on-this-mac", "train-regions-on-this-mac")


def due_starts(offers: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """(action, params) for each offer that starts by itself now: its setting is `here`, it is ready, and this Mac
    can start it with what the engine filled (a teacher, a scope). Hugging Face never starts by itself: its pages
    leave only on the person's yes."""
    due = []
    for offer in offers:
        if offer["setting"]["mode"] != "here" or not offer["readiness"].get("ready"):
            continue
        start = next((t for w in offer["ways"] for t in w["targets"]
                      if t["place"] == THIS_MAC["place"] and t.get("params")), None)
        if start:
            due.append((start["starts"], start["params"]))
    return due


def this_mac_memory_gb() -> float:
    import os

    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError):
        return 8.0


def _offers_now(db: Any, *, mac_memory_gb: float | None = None) -> list[dict[str, Any]]:
    """The project's train offers as the Start plan counts them, with its setting."""
    from pathlib import Path

    from fichero_server.llm import get_api_key
    from fichero_server.recipes.project import read_project_setup

    from fichero_server.recipes.answers import spend_cap

    setup = read_project_setup(Path(db.path).parent)
    answers = setup["answers"] or {}
    stays_local = not answers.get("cloud_allowed", False)
    setting = training_setting(answers.get("training"), mac_memory_gb=mac_memory_gb or this_mac_memory_gb(),
                               hf_configured=bool(get_api_key("huggingface")), stays_local=stays_local,
                               spend_cap=spend_cap(answers))
    from fichero_server.recipes.project import read_noise_band

    return train_offers(setup["recipe"], counted(db), stays_local=stays_local, setting=setting,
                        spend_cap=spend_cap(answers), noise_band=read_noise_band(Path(db.path).parent))


def _start(db: Any, action: str, params: dict[str, Any]) -> str:
    """Start `action` as the recipe; its job's id."""
    from pathlib import Path

    import fichero_server.api.routes.training  # noqa: F401  (registers the training actions)
    from fichero_server.actions.registry import ActionContext, registry

    ctx = ActionContext(actor="recipe", library_path=str(Path(db.path).parent), is_bootstrap=True)
    return registry.invoke(db, action, params, ctx).result["job_id"]


def _corrected_lines(db: Any) -> int:
    """The corrected lines the offers count (the bake-off's one rule)."""
    from fichero_server.recipes.bakeoff import ground_truth

    pages, _ = ground_truth(db, None)
    return sum(p["lines"] for p in pages)


def _newest_here_job(db: Any) -> dict[str, Any] | None:
    from fichero_server.execution import jobs

    jobs._ensure(db)
    job_id = jobs.newest_job_id_of_kinds(db, _HERE_KINDS)
    return jobs.read_job(db, job_id) if job_id else None


def held_after_failure(db: Any) -> str | None:
    """Why training does not start again by itself, or None: the newest training on this Mac failed or was stopped,
    and there are no more corrected lines than it was started on. It starts again on more corrections, or when the
    person starts it."""
    import json

    job = _newest_here_job(db)
    if job is None or job["state"] not in ("failed", "cancelled"):
        return None
    then = json.loads(job.get("detail") or "{}").get("started_at_lines")
    now = _corrected_lines(db)
    if then is not None and now > then:
        return None
    ended = "failed" if job["state"] == "failed" else "was stopped"
    return (f"Training on this Mac {ended} ({job.get('reason') or 'no reason given'}) on {then or now:,} corrected "
            "lines; it starts again by itself when there are more, or when you start it.")


def start_when_ready(db: Any, *, mac_memory_gb: float | None = None) -> list[str]:
    """Start each training due under `here` (#5440), unless training has already started on this Mac (a job
    waiting, running, paused or done) or the last one failed and nothing new has come since (`held_after_failure`).
    Each start records the corrected lines it began on. Returns the actions started. A refusal (nothing to train
    on) is logged, never fails the step that asked.
    ponytail: once per project; training again on later corrections waits for the evaluation that adopts (#5441)."""
    import json
    import logging

    from fichero_server.execution import jobs

    log = logging.getLogger(__name__)
    newest = _newest_here_job(db)
    if newest is not None and newest["state"] not in ("failed", "cancelled"):
        return []
    held = held_after_failure(db)
    if held:
        log.info("training not started by itself: %s", held)
        return []
    started = []
    for action, params in due_starts(_offers_now(db, mac_memory_gb=mac_memory_gb)):
        try:
            job_id = _start(db, action, params)
        except Exception as exc:  # noqa: BLE001 -- training not starting never fails the recipe step
            log.warning("training did not start by itself (%s): %s", action, exc)
            continue
        job = jobs.read_job(db, job_id) or {}
        detail = {**json.loads(job.get("detail") or "{}"), "started_at_lines": _corrected_lines(db)}
        jobs.save_detail(db, job_id, json.dumps(detail))
        started.append(action)
    return started


#: The Job kinds that run on Hugging Face and are paid for there: training and reading at scale.
HF_PAID_KINDS = ("train-a-model", "read-at-scale")


def _hours(limit: str | None) -> float | None:
    """A Job's time limit (`4h`, `90m`, `1h30m`, `3600s`, `1d`) in hours, or None when it says none."""
    import re

    parts = re.findall(r"(\d+(?:\.\d+)?)\s*([smhd])", str(limit or ""))
    per = {"s": 1 / 3600, "m": 1 / 60, "h": 1.0, "d": 24.0}
    return sum(float(n) * per[u] for n, u in parts) if parts else None


def spend_this_month(db: Any, *, cap: float, now: Any = None) -> dict[str, Any]:
    """This month's Hugging Face spend against the project's cap (`source.onboard.spend-cap`, #5769): each Job sent this
    calendar month at its most, its hardware's price an hour (as listed when it was sent) times its time limit, where
    the service ends it. A Job not yet sent costs nothing yet; one with no listed price is counted as unknown, never $0.
    ponytail: an upper bound; the time a Job actually ran, when the service reports it."""
    from datetime import datetime, timezone

    from fichero_server.core.timeutil import ensure_utc
    from fichero_server.execution import jobs

    month = ensure_utc(now or datetime.now(timezone.utc)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent, counted_jobs, unpriced = 0.0, 0, 0
    for at, detail in jobs.details_of_kinds(db, HF_PAID_KINDS):
        if at < month:  # both in UTC: the month turns at midnight UTC
            continue
        request = detail.get("request") or {}
        if request.get("target", "huggingface-jobs") != "huggingface-jobs":
            continue  # a read on a cluster: an allocation, not bought by the hour
        # a reading run is one row of many Jobs, a Job for each shard sent (each try); a training run is one Job
        sent = (sum(s.get("tries", 0) for s in detail["shards"].values()) if detail.get("shards")
                else int(bool(detail.get("far_id"))))
        if not sent:
            continue
        counted_jobs += sent
        price, hours = detail.get("price_per_hour_usd"), _hours(request.get("timeout"))
        if price is None or hours is None:
            unpriced += sent
            continue
        spent += float(price) * hours * sent
    spent = round(spent, 2)
    sentence = (f"Hugging Face this month: at most ${spent:.2f} of ${cap:.2f}, "
                f"{counted_jobs} {'Job' if counted_jobs == 1 else 'Jobs'}"
                + (f", {unpriced} with no listed price" if unpriced else ""))
    return {"cap_usd": cap, "spent_at_most_usd": spent, "jobs": counted_jobs, "unpriced": unpriced,
            "month": month.strftime("%Y-%m"), "sentence": sentence + "."}
