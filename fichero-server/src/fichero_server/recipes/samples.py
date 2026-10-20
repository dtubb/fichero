"""Sample pages, and trying a stage on them before Start (section 7c, #5668).

`source.onboard.stages.samples-proposed`: Fichero proposes 3 to 5 sample pages spread across the material (first,
last, the largest and smallest images, then evenly spaced); the person can choose others, kept beside
`recipe/setup.yaml` and holding for every stage.

`source.onboard.stages.sample-run-reuses` and `samples-are-not-the-work`: one run, try this stage on these pages.
Read and Find Lines reuse the bake-off and its evaluation job (section 8a). Every other stage runs its own steps of
the project's recipe, through the Start plan's cards and the recipe runner's own `_run_workflow` (one code path), on
a COPY of the sample pages in a scratch project beside the setup (`transfer.plan.build_plan` +
`transfer.copy.copy_into_target`); what the run made there is read back as the stage's result
(`recipe/samples/<stage>.json`) and the scratch project removed. Nothing is ever written as the project's passes,
readings, names, dates or statements, so Start does not count a try as done. A try is replaced by the next one and
cleared when its stage is unticked. A stage whose steps would use the cloud says its cost first and runs only with
that yes.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SAMPLES_FILE = "samples.json"
TRY_KIND = "try-a-stage"
MAX_SAMPLES, MIN_SAMPLES = 5, 3
#: Organise's sample is one run of neighbouring pages, at most this long (`organise-tried-on-a-run`).
RUN_LENGTH = 12
#: The stages tried on that run; every other stage gets the spread samples (#5686).
RUN_STAGES = frozenset({"organise"})


def _folder(library: Path) -> Path:
    return library / "recipe" / "samples"


def _pages(db: Any) -> list[Any]:
    """The project's material as Items shows it (#5686): each folder's pages in its own order (sort order, then the
    name read naturally), the folders in the same order, never the order an import happened to create them."""
    from fichero_server.core.naturalsort import in_folder_order
    from fichero_server.models import Document

    pages = [d for d in (db.get(Document, i) for i in db.unit_of_work_ids()) if d is not None]
    folders = {p.parent_id: db.get(Document, p.parent_id) for p in pages if p.parent_id}

    def key(doc: Any) -> tuple:
        folder = folders.get(doc.parent_id)
        # The folders in their order, then each folder's pages in theirs: the one shared order (#5693).
        return (folder is None, in_folder_order(folder) if folder else (), doc.parent_id or "", in_folder_order(doc))

    return sorted(pages, key=key)


def _size(library: Path, doc: Any) -> int:
    raw = getattr(doc, "path", None)
    if not raw:
        return 0
    path = Path(raw) if Path(raw).is_absolute() else library / raw
    try:
        return path.stat().st_size
    except OSError:
        return 0


def propose(db: Any) -> list[dict[str, str]]:
    """3 to 5 pages spread across the material, each with why it was picked; every page when there are fewer."""
    library = Path(db.path).parent
    pages = _pages(db)
    if len(pages) <= MAX_SAMPLES:
        return [{"id": p.id, "name": p.name, "why": "one of your pages"} for p in pages]
    sized = sorted(pages, key=lambda p: _size(library, p))
    picks: dict[str, str] = {}
    for doc, why in ((pages[0], "your first page"), (pages[-1], "your last page"),
                     (sized[-1], "the largest image"), (sized[0], "the smallest image")):
        picks.setdefault(doc.id, why)
    step = len(pages) / (MAX_SAMPLES + 1)
    for i in range(1, MAX_SAMPLES + 1):
        if len(picks) >= MAX_SAMPLES:
            break
        picks.setdefault(pages[min(len(pages) - 1, int(i * step))].id, "spread across the rest")
    by_id = {p.id: p for p in pages}
    order = {p.id: i for i, p in enumerate(pages)}
    return [{"id": i, "name": by_id[i].name, "why": why} for i, why in sorted(picks.items(), key=lambda kv: order[kv[0]])]


def propose_run(db: Any) -> list[dict[str, str]]:
    """Organise's sample (`source.onboard.stages.organise-tried-on-a-run`): one run of up to `RUN_LENGTH` consecutive
    pages in their folder's own order, from the folder with the most pages, from its first page; each says why. Where
    a document ends is only seen on neighbouring pages, which pages spread across the material are not."""
    from fichero_server.finddocs.job import scopes
    from fichero_server.models import Document

    pages = _pages(db)
    if not pages:
        return []
    folder_id, run = max(scopes(db, [p.id for p in pages]).items(), key=lambda kv: len(kv[1]))
    folder = db.get(Document, folder_id) if folder_id else None
    where = f"“{folder.name}”" if folder is not None else "your pages"
    run = run[:RUN_LENGTH]
    return [{"id": p.id, "name": p.name,
             "why": f"page {i} of {len(run)} in a row from {where}: Organise looks for where one document ends "
                    "and the next begins"} for i, p in enumerate(run, 1)]


def chosen(db: Any, stage: str | None = None) -> dict[str, Any]:
    """The samples (`_chosen`), each marked as the person's own page (`yours`: a page of this project, never the shipped
    example image) with whether its thumbnail is made yet, so the stage page can draw them (#5808 b)."""
    from fichero_server.db.storage import has_thumbnail

    found = _chosen(db, stage)
    package = Path(db.path).parent
    return {**found, "pages": [{**p, "yours": True, "thumbnail": bool(has_thumbnail(p["id"], package))}
                               for p in found["pages"]]}


def _chosen(db: Any, stage: str | None = None) -> dict[str, Any]:
    """The samples: the person's choice when there is one, else Fichero's proposal. For Organise, the run of
    consecutive pages it is tried on (`propose_run`): pages chosen across the material cannot show a document's
    end."""
    from fichero_server.models import Document
    if stage in RUN_STAGES:
        return {"chosen_by": "fichero", "pages": propose_run(db)}
    library = Path(db.path).parent
    try:
        kept = json.loads((_folder(library) / SAMPLES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = None
    if kept and kept.get("ids"):
        docs = [db.get(Document, i) for i in kept["ids"]]
        live = [d for d in docs if d is not None and d.deleted_at is None]
        if live:
            return {"chosen_by": "you", "pages": [{"id": d.id, "name": d.name, "why": "chosen by you"} for d in live]}
    return {"chosen_by": "fichero", "pages": propose(db)}


def choose(db: Any, ids: list[str]) -> dict[str, Any]:
    """Keep the person's samples (empty: back to Fichero's proposal). ValueError for a page not in the project."""
    from fichero_server.models import Document

    library = Path(db.path).parent
    for doc_id in ids:
        doc = db.get(Document, doc_id)
        if doc is None or doc.deleted_at is not None:
            raise ValueError(f"There is no page {doc_id} in this project.")
    folder = _folder(library)
    folder.mkdir(parents=True, exist_ok=True)
    if ids:
        (folder / SAMPLES_FILE).write_text(json.dumps({"ids": list(dict.fromkeys(ids))}), encoding="utf-8")
    else:
        (folder / SAMPLES_FILE).unlink(missing_ok=True)
    return chosen(db)


# --- trying a stage ---------------------------------------------------------------------------------------------


def _result_path(library: Path, stage: str) -> Path:
    return _folder(library) / f"{stage}.json"


def stored_results(library: Path, recipe: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Each chosen stage's kept sample result, as its last try left it (for what a kinds question may suggest)."""
    from fichero_server.recipes.stages import STAGES

    on = {str(s.get("job")) for s in (recipe or {}).get("steps") or []}
    out: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        if not on & set(stage.jobs):
            continue
        try:
            out[stage.id] = json.loads(_result_path(Path(library), stage.id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # not tried yet, or the record is unreadable: nothing is suggested
    return out


def read_result(db: Any, stage: str, recipe: dict[str, Any] | None) -> dict[str, Any] | None:
    """The stage's sample result; None (and the record cleared) when the stage is not on in the recipe."""
    from fichero_server.recipes.stages import get_stage

    library = Path(db.path).parent
    path = _result_path(library, stage)
    known = get_stage(stage)
    on = known is not None and bool({str(s.get("job")) for s in (recipe or {}).get("steps") or []} & set(known.jobs))
    if not on:
        path.unlink(missing_ok=True)  # cleared when unticked
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if result.get("bakeoff"):
        from fichero_server.recipes import bakeoff

        result["comparison"] = bakeoff.result(db, library, result["bakeoff"])
    return _following_its_job(db, result)


def _following_its_job(db: Any, result: dict[str, Any]) -> dict[str, Any]:
    """A result still "waiting" reads as its job is: done, or failed with the job's sentence (or that it is gone), so
    the app's spinner stops and Compare is not held off for ever by a try that ended (#5806)."""
    from fichero_server.execution import jobs

    job_id = result.get("job_id")
    if result.get("state") not in ("waiting", "running") or not job_id:
        return result
    row = jobs.read_job(db, job_id)
    state = row["state"] if row else "cleared"
    if state == "done":
        return {**result, "state": "done"}
    if state == "cancelled":  # Stop reads "stopped", not "failed" (review 337)
        return {**result, "state": "stopped", "error": result.get("error") or "Stopped",
                "candidates": _ended(result, "Stopped", final="stopped")}
    if state in ("failed", "cleared"):
        why = _sentence(row.get("reason")) if row else None
        error = result.get("error") or why or "The try did not finish: try it again"
        return {**result, "state": "failed", "error": error, "candidates": _ended(result, error)}
    followed = {**result, "state": state if state == "running" else result["state"]}
    said_now = jobs.state_and_reason(db, job_id)
    if said_now and said_now[1]:
        # What the try is doing or waiting for, in words, always beside its spinner (`recipes.try.says-what-it-waits-for`):
        # "Copying the sample pages", "Waiting for the model lane: …", "Trying Read: …". Never a spinner with no words.
        followed["waiting_for"] = said_now[1]
    if state in ("waiting", "running") and "comparison" not in followed:
        # A try waiting its turn, or running while its page waits for the lane ("Waiting: ..." on its row), says what
        # for beside the app's spinner (#5837): the same field a bake-off's wait uses.
        said = jobs.state_and_reason(db, job_id)
        if said and said[1] and (state == "waiting" or said[1].startswith("Waiting")):
            followed["comparison"] = {"state": "waiting", "reason": said[1]}
    return followed


#: One lock per kept result file: the try's thread and its progress watcher both write it (review 323).
_FILE_LOCKS: dict[str, threading.RLock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _file_lock(path: Path) -> threading.RLock:
    with _FILE_LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(str(path), threading.RLock())


def _ended(result: dict[str, Any], error: str, final: str = "failed") -> list[dict[str, Any]]:
    """The compared columns of a try whose job ended before it wrote its end (the engine stopped under it): each
    still-running column is failed with the try's sentence and a final progress, counting the pages it had finished,
    never left "running" at 0 of N with no why (`source.onboard.stages.try-progress-in-place`)."""
    total = len(result.get("pages") or [])
    columns = []
    for column in result.get("candidates") or []:
        if column.get("state") in ("waiting", "running"):
            made = column.get("per_page") or []
            column = {**column, "state": final, "why": column.get("why") or error,
                      "progress": finished_progress(final, made, total, str(result.get("stage")))}
        columns.append(column)
    return columns


def _write(library: Path, stage: str, result: dict[str, Any]) -> None:
    path = _result_path(library, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(path):
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")  # unique: no two writers share a temp file
        tmp.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
        tmp.replace(path)


def _stage_plan(db: Any, stage: Any, setup: dict[str, Any], page_count: int) -> dict[str, Any]:
    """The Start plan's cards for this stage's own steps, and what they would cost on the samples."""
    from fichero_server.recipes.start import estimate, plan_start

    from fichero_server.recipes import places

    recipe = setup["recipe"] or {}
    answers = setup["answers"] or {}
    steps = {s.get("id") for s in recipe.get("steps") or [] if s.get("job") in stage.jobs}
    plan = plan_start(recipe, stays_local=not places.may_leave_to(answers, "cloud"), only=steps,
                      job_answers=answers.get("job_answers"), db=db)
    plan["estimate"] = estimate(plan["workflows"], page_count)
    return plan


def start_try(db: Any, stage_id: str, setup: dict[str, Any], *, page_ids: list[str] | None, cost_ok: bool,
              started_by: str, run_evaluation=None, candidates: list[str] | None = None) -> dict[str, Any]:
    """Try a stage on the samples, comparing its main step's candidates side by side
    (`source.onboard.stages.compares-candidates`): `candidates` (card ids), else the step's own model and the per-step
    finder's next ones, up to three, each on its own copy of the samples in one `try-a-stage` job. Read and Find Lines
    start the bake-off instead when no candidates are named and the samples hold its ground truth. ValueError, in
    words, for a stage that is off, cannot be tried, or names a model Fichero does not know; PermissionError for a
    cloud candidate without the yes (`cost_ok`)."""
    from fichero_server.core.timeutil import utc_now_iso
    from fichero_server.execution import jobs
    from fichero_server.recipes import bakeoff
    from fichero_server.recipes.stages import TRIED_BY_THE_BAKEOFF, get_stage, sampleable

    library = Path(db.path).parent
    stage = get_stage(stage_id)
    if stage is None:
        raise LookupError(f"Set Up has no stage {stage_id!r}")
    recipe = setup["recipe"] or {}
    if not {str(s.get("job")) for s in recipe.get("steps") or []} & set(stage.jobs):
        raise ValueError(f"{stage.title} is not chosen for this project: choose it first")
    if not sampleable(stage):
        raise ValueError(f"{stage.title} cannot be tried on sample pages yet")
    ids = page_ids or [p["id"] for p in chosen(db, stage_id)["pages"]]
    if not ids:
        raise ValueError("This project has no pages to try it on yet")
    now = utc_now_iso(timespec="seconds")
    result: dict[str, Any] = {"stage": stage_id, "pages": ids, "tried_at": now, "state": "waiting"}
    if stage_id in TRIED_BY_THE_BAKEOFF and not candidates and _bakeoff_ready(db, ids):
        from fichero_server.recipes.discovery import known_cards
        from fichero_server.recipes.start import count_pages
        from fichero_server.api.routes.system.recipes import _answers

        if stage_id == "find-lines":
            record = bakeoff.start_lines(db, library, page_ids=ids, now=now, started_by=started_by)
        else:
            a = _answers(setup["answers"] or {})
            record = bakeoff.start(db, library, a, known_cards(a, include_not_built=True), page_ids=ids,
                                   volume=a.pages or count_pages(db), now=now, run_evaluation=run_evaluation)
        result.update(bakeoff=record["id"], job_id=record["job_id"], how="the comparison of candidates on these pages")
        _write(library, stage_id, result)
        return result
    if "read" in stage.needs and not _any_reading(db, ids):
        raise ValueError(f"These pages have no reading yet: {stage.title} needs Read. Try Read on them, or Start, "
                         "first.")
    step = _main_step(recipe, stage)
    cards = _cards_for(setup, step, candidates) if step is not None else []
    if candidates and len(cards) < len(set(candidates)):
        known = {c.id for c in cards}
        raise ValueError("Fichero does not know the model " + ", ".join(c for c in candidates if c not in known))
    tried = [(card, _stage_plan(db, stage, _with_card(setup, step, card), len(ids))) for card in cards] \
        or [(None, _stage_plan(db, stage, setup, len(ids)))]
    runnable = [(card, plan) for card, plan in tried if not plan["refusals"]]
    if not runnable:
        raise ValueError(f"{stage.title} cannot run yet: " + "; ".join(tried[0][1]["refusals"]))
    clouded = [plan for _, plan in runnable if not _local(plan)]
    if clouded and not cost_ok:
        costs = [plan["estimate"]["total_cost_usd"] for plan in clouded]
        said = (f"about ${sum(costs):.2f}" if all(isinstance(c, (int, float)) for c in costs)
                else "a cost that is not known")
        raise PermissionError(f"Trying {stage.title} on {len(ids)} pages uses the cloud and costs {said}: "
                              "try it again with your yes to the cost")
    from fichero_server.recipes.start import queue_downloads

    for _card, plan in runnable:  # what a candidate needs is fetched as Start fetches it; its run waits (#5687)
        queue_downloads(db, plan, started_by=started_by)
    own_plan = runnable[0][1]
    columns = [_column(card, plan) for card, plan in tried if card is not None]
    register_job_kinds()
    # The result file is there before the job is queued: a job picked up at once reads it (#5806, the 07:51 failure).
    result.update(how="its own steps on a copy of these pages",
                  models=[{"steps": w["steps"], "model": w["model_override"], "where": w["runs_on"]}
                          for w in own_plan["workflows"]], cost=own_plan["estimate"], candidates=columns)
    _write(library, stage_id, result)
    job_id = jobs.enqueue(db, TRY_KIND, f"{stage_id}:{uuid.uuid4().hex[:8]}", started_by=started_by, watched=True,
                          detail=json.dumps({"stage": stage_id, "pages": ids}))
    result = {**json.loads(_result_path(library, stage_id).read_text(encoding="utf-8")), "job_id": job_id}
    _write(library, stage_id, result)
    return result


# --- comparing candidates (`source.onboard.stages.compares-candidates`) -------------------------------------------

#: At most this many candidates are compared on a stage's samples.
COMPARED = 3
TEXT_STAGES = frozenset({"read", "normalise", "translate"})
SHAPE_STAGES = frozenset({"find-regions", "find-lines"})
ITEM_STAGES = frozenset({"names", "statements", "dates"})


def _any_reading(db: Any, page_ids: list[str]) -> bool:
    """Whether any of these pages has text to work from: a reading, or its own text (a page imported as text)."""
    from fichero_server.models import Document
    from fichero_server.recipes.run_view import _has_reading

    return any(((doc := db.get(Document, page_id)) is not None and (doc.page_content or "").strip())
               or _has_reading(db, page_id) for page_id in page_ids)


def _sentence(text: str | None) -> str | None:
    """A failure as a person reads it: never an exception's class name in front (#5687)."""
    if not text:
        return text
    import re

    return re.sub(r"^(?:[A-Za-z_][\w.]*(?:Error|Exception|Unavailable|Missing)): ", "", text.strip())


def _await_downloads(db: Any, plan: dict[str, Any], *, every: float = 2.0) -> str | None:
    """Wait for the models this candidate's plan needs to land; why not, in words, when one cannot."""
    from fichero_server.execution import jobs

    try_id, last = jobs.current_job_id(), None

    for download in plan.get("downloads") or []:
        name = download.get("name") or download.get("model")
        if not download.get("job_id"):
            return f"it needs {name} downloaded first, and its download did not start"
        while True:
            row = jobs.read_job(db, download["job_id"]) or {}
            if row.get("state") == "done":
                break
            if row.get("state") in ("failed", "cancelled", None):
                return f"{name} could not be downloaded: {_sentence(row.get('reason')) or 'the download stopped'}"
            if try_id and row.get("reason") != last:  # say what it waits for, with the download's own progress
                last = row.get("reason")
                jobs.save_detail(db, try_id, jobs.read_job(db, try_id).get("detail") or "{}",
                                 reason=f"Waiting for {name} to download" + (f" ({last})" if last else ""))
            time.sleep(every)
    return None


def _bakeoff_ready(db: Any, page_ids: list[str]) -> bool:
    """Whether the samples hold the bake-off's ground truth (its corrected lines)."""
    from fichero_server.recipes import bakeoff

    return bool(bakeoff.readiness(bakeoff.ground_truth(db, page_ids)[0])["ready"])


def _main_step(recipe: dict[str, Any], stage: Any) -> dict[str, Any] | None:
    """The stage's step whose model is compared: the recipe's first step of the stage's jobs that names a model."""
    steps = [s for s in recipe.get("steps") or [] if s.get("job") in stage.jobs]
    return next((s for s in steps if s.get("model")), steps[0] if steps else None)


#: What can do a step, said where a wrong choice is refused (#5838).
_WHO_DOES = {"find-lines": "the line finders are Kraken and Apple Vision (print); cloud vision models cannot find lines yet"}


def _cards_for(setup: dict[str, Any], step: dict[str, Any], wanted: list[str] | None) -> list[Any]:
    """The cards compared for the step: `wanted` in its order, else the step's own and the per-step finder's next
    ones runnable here (`source.find.candidates-fit-the-step`), up to `COMPARED`."""
    from fichero_server.api.routes.system.recipes import _answers
    from fichero_server.recipes.assemble import _rank_key, _refusal
    from fichero_server.recipes.discovery import discover, known_cards, step_candidates

    job = str(step.get("job"))
    a = _answers(setup["answers"] or {})
    found, _ = discover(a, online=False, job=job)
    own_card = (step.get("card") or {}).get("id") if isinstance(step.get("card"), dict) else None
    found = step_candidates(found, job, frozenset({own_card} if own_card else ()),
                            step.get("model") if isinstance(step.get("model"), dict) else None)  # Find a Reader's list: page readers, cloud and remote ones included (#5808)
    by_id = {c.id: c for c in [*known_cards(a, include_not_built=True), *found]}
    if wanted:
        named = [by_id[i] for i in dict.fromkeys(wanted) if i in by_id]
        wrong = [c for c in named if job not in c.jobs]
        if wrong:  # a model that cannot do the step is never compared on it (#5838)
            raise ValueError(", ".join(c.note.strip().rstrip(".") or c.id for c in wrong)
                             + f" cannot do the step {step.get('id') or job} ({job}); " + _WHO_DOES.get(job, "pick another model"))
        return named
    own = (step.get("card") or {}).get("id") if isinstance(step.get("card"), dict) else None
    if own is None:
        own = next((c.id for c in found if dict(c.pin) == step.get("model")), None)
    fits = sorted((c for c in found if job in c.jobs and c.runs_here and not c.offered_only
                   and _refusal(job, c, a, a.material) is None), key=lambda c: _rank_key(c, a.material, a))
    out = [by_id[own]] if own in by_id else []
    out += [c for c in fits if c.id != own]
    return out[:COMPARED]


def _with_card(setup: dict[str, Any], step: dict[str, Any] | None, card: Any) -> dict[str, Any]:
    """The setup with the step's model swapped for the card's (a copy: the project's setup is never changed)."""
    import copy

    if step is None or card is None:
        return setup
    changed = copy.deepcopy(setup)
    for s in (changed["recipe"] or {}).get("steps") or []:
        if s.get("id") == step.get("id"):
            s.update(model=dict(card.pin), runs_on=card.runs_on, card={"id": card.id, "note": card.note})
            s.pop("problem", None)
            s.pop("gap", None)
    return changed


def _local(plan: dict[str, Any]) -> bool:
    return not any(str(r.get("runs_on")).startswith("cloud") for r in [*plan["workflows"], *plan["runs"]])


def _column(card: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """A candidate's column, before it runs: the bake-off row's fields (`bakeoff._candidate`'s shape)."""
    from fichero_server.recipes.bakeoff import _figure, reader_name
    from fichero_server.recipes.discovery import model_link

    local = _local(plan)
    cost = plan["estimate"].get("total_cost_usd")
    return {"card": card.id, "name": reader_name(card), "link": model_link(card), "pin": dict(card.pin),
            "runs_on": card.runs_on,
            "local": bool(card.local and local),
            "cost_usd": (_figure(0.0, "measured", "runs on this Mac") if local else
                         _figure(cost if isinstance(cost, (int, float)) else None, "estimate",
                                 "the price list, on these pages")),
            "seconds": None, "cer": None, "agreement": None, "measures": None,
            "why": "; ".join(plan["refusals"]) or None, "state": "waiting" if not plan["refusals"] else "not run"}


def _similar(a: str, b: str, why: list[str]) -> float | None:
    """1 less the character distance between two readings (each way, averaged); None when neither way can be
    measured, with the reason added to `why` (the candidate's measures say it)."""
    from fichero_server.workflows.run_comparison import RunComparisonError
    from fichero_server.workflows.transcription_accuracy import character_error_rate

    scores = []
    for ref, hyp in ((a, b), (b, a)):
        try:
            scores.append(max(0.0, 1.0 - character_error_rate(ref, hyp).cer))
        except RunComparisonError as exc:  # an empty side, or one too long to compare: said in the measures
            why.append(str(exc))
    return sum(scores) / len(scores) if scores else None


def _iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    h = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = w * h
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _measure(db: Any, stage_id: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How each candidate's run compares with the others' on the same pages: agreement (and CER on lines a person
    corrected) for text, mean best overlap for shapes, counts and what only it found for items."""
    out = []
    for i, run in enumerate(runs):
        others = [r for j, r in enumerate(runs) if j != i]
        if stage_id in TEXT_STAGES:
            why: list[str] = []
            agree = [x for o in others for p, text in run["texts"].items()
                     if (x := _similar(text, o["texts"].get(p, ""), why)) is not None]
            measured = {"kind": "text", "agreement": _mean(agree), "cer": _cer_on_checked(db, run["texts"], why)}
            if why:
                measured["not_measured"] = "couldn't measure: " + "; ".join(dict.fromkeys(why))
            out.append(measured)
        elif stage_id in SHAPE_STAGES:
            from collections import Counter

            # Only against candidates that found shapes: one that found none (it failed, or the page has none for it) is
            # nothing to overlap with, and counting it scored every box 0% (owner, 2026-10-19).
            found = [o for o in others if any(o["boxes"].values())]
            best = [max((_iou(box, other) for other in o["boxes"].get(p, [])), default=0.0)
                    for o in found for p, boxes in run["boxes"].items() for box in boxes]
            measured = {"kind": "shapes", "agreement": _mean(best), "cer": None, "found": len(run["items"]),
                        "kinds": dict(Counter(run["items"]))}
            if others and not found:
                measured["not_measured"] = "nothing to compare with: the other candidates found no lines"
            out.append(measured)
        elif stage_id in ITEM_STAGES:
            mine = set(run["items"])
            theirs = set().union(*(set(o["items"]) for o in others)) if others else set()
            jaccard = [len(mine & set(o["items"])) / len(mine | set(o["items"])) for o in others
                       if mine | set(o["items"])]
            out.append({"kind": "items", "agreement": _mean(jaccard), "cer": None, "found": len(mine),
                        "only_this_found": sorted(mine - theirs)[:20]})
        else:
            out.append({"kind": None, "agreement": None, "cer": None})
    return out


def _cer_on_checked(db: Any, texts: dict[str, str], why: list[str]) -> float | None:
    """The character error rate of these pages' readings on the lines a person corrected on them; None when none,
    with the reason a page could not be scored added to `why`."""
    from fichero_server.training.evaluation import reference_page
    from fichero_server.workflows.run_comparison import RunComparisonError
    from fichero_server.workflows.transcription_accuracy import character_error_rate

    distance = chars = 0
    for page_id, text in texts.items():
        page, _why = reference_page(db, page_id, None)
        if page is None:
            continue
        reference = "\n".join(line["text"] for line in page["lines"])
        try:
            score = character_error_rate(reference, text)
        except RunComparisonError as exc:  # an empty reference, or a page too long to compare: said in the measures
            why.append(str(exc))
            continue
        distance += score.distance
        chars += score.reference_chars
    return round(distance / chars, 4) if chars else None


def register_job_kinds() -> None:
    from fichero_server.execution import jobs

    if TRY_KIND not in jobs.KINDS or jobs.KINDS[TRY_KIND].run is None:
        # Its own lane (#5806): like a recipe run it only waits on its steps' own jobs and never holds the model lane
        # they need, but a try waiting on a download must not hold up another stage's try.
        jobs.register_kind(TRY_KIND, _run_try, model=None, lane="tries", name="Try a stage on the sample pages")


#: The kinds of row a stage's run makes, read back from the scratch copy as its result.
_RESULT_MODELS = ("ContentRepresentation", "Segment", "KnowledgeEntity", "KnowledgeClaim", "Artifact")


def _snapshot(db: Any) -> dict[str, set[str]]:
    models = {m.__name__: m for m in db._all_schema_models()}
    return {name: {r.id for r in db.all(models[name])} for name in _RESULT_MODELS if name in models}


def _readable(row: Any) -> str:
    for attr in ("text", "content", "canonical_name", "name"):
        value = getattr(row, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()[:400]
    return ""


def _run_try(db: Any, subject: str) -> dict[str, Any]:
    """The try job, with a person watching: its model-lane rows go ahead of a bulk run's (#5839)."""
    from fichero_server.execution import jobs

    with jobs.person_is_waiting(db, jobs.current_job_id() or jobs.job_id_for(db, TRY_KIND, subject)):
        return _run_try_watched(db, subject)


def _run_try_watched(db: Any, subject: str) -> dict[str, Any]:
    """The job: each candidate's run of the stage's cards on its own copy of the samples (one run when nothing is
    compared), the step's own as the try's result, and the columns with how each compared."""
    from fichero_server.execution import jobs
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.stages import get_stage

    stage_id = subject.split(":", 1)[0]
    library = Path(db.path).parent
    job_id = jobs.current_job_id() or jobs.job_id_for(db, TRY_KIND, subject)
    result = json.loads(_result_path(library, stage_id).read_text(encoding="utf-8"))
    stage = get_stage(stage_id)
    setup = read_project_setup(library)
    columns = result.get("candidates") or []
    step = _main_step(setup["recipe"] or {}, stage)
    wanted = [c["card"] for c in columns if c.get("state") != "not run"]
    cards = _cards_for(setup, step, wanted) if wanted and step is not None else []
    runs = []
    total = len(result["pages"])
    for i, card in enumerate(cards or [None]):
        started = time.monotonic()
        def publish(made, state="running", page=None, _card=card.id if card is not None else None, _first=i == 0):  # noqa: E306
            progress = progress_of(made, total, stage_id, state, page)
            publish_progress(library, stage_id, _card, progress, made)
            if _first:  # the row Activity shows counts the first run's pages
                _count_on_the_row(db, job_id, stage_id, progress)

        publish([], "running")  # it says it is running, with 0 of N, before its first page is made
        one = _run_one(db, stage, _with_card(setup, step, card), result["pages"], job_id,
                       stage_id if i == 0 else f"{stage_id}-{i}",
                       name=card.note if card is not None else stage.title, publish=publish)
        one["seconds"] = round(time.monotonic() - started, 1)
        runs.append(one)
    own = runs[0]
    result.update(state=own["state"], ran=own["ran"], **own["made"])
    if own.get("error"):
        result["error"] = own["error"]
    by_card = {card.id: run for card, run in zip(cards, runs)}
    for column, measures in zip([c for c in columns if c["card"] in by_card], _measure(db, stage_id, runs)):
        run = by_card[column["card"]]
        column.update(progress=finished_progress(run["state"], run["made"]["per_page"], total, stage_id),
                      state=run["state"], seconds=run["seconds"], per_page=run["made"]["per_page"],
                      names=run["made"]["names"], measures=measures, agreement=measures["agreement"],
                      cer=measures["cer"], why=run.get("error"))
    result["candidates"] = columns
    result["progress"] = finished_progress(own["state"], own["made"]["per_page"], total, stage_id)
    _write(library, stage_id, result)
    return result


def _count_on_the_row(db: Any, job_id: str, stage_id: str, progress: dict[str, Any]) -> None:
    """The try's own row carries the pages done and tried (`activity.details.progress-counts`): its pages live in a
    scratch copy that is deleted when the try ends, so the row's tree could only say 0 of 1."""
    from fichero_server.execution import jobs

    try:
        jobs.save_detail(db, job_id, json.dumps({"stage": stage_id, "done": progress["done"], "total": progress["total"]}))
    except Exception:  # noqa: BLE001 -- a count is a courtesy; the try's result stands
        logger.debug("a try's count could not be kept on its row", exc_info=True)


#: How often a running candidate's finished pages are read back from its copy and published (seconds).
PROGRESS_EVERY = 2.0


def _watch(copy: Any, before: dict[str, set[str]], back: dict[str, str], publish: Any, stop: threading.Event) -> None:
    """Publish a candidate's finished pages while its steps run, until `stop`: a read of the copy that fails is
    skipped, never a failed try (the final result is read once the run ends)."""
    while not stop.wait(PROGRESS_EVERY):
        try:
            publish(_collect(copy, before, back)["per_page"])
        except Exception:  # noqa: BLE001 -- progress is a courtesy; the run's own result stands
            logger.debug("a try's progress could not be read", exc_info=True)


def _run_one(db: Any, stage: Any, setup: dict[str, Any], page_ids: list[str], job_id: str, scratch_name: str, *,
             name: str, publish: Any = None) -> dict[str, Any]:
    """One run of the stage's own steps on a fresh copy of the pages: what it made, in the project's page ids, and
    for comparing, each page's whole reading, its shapes and the items it found."""
    from fichero_server.db.manager import db_manager
    from fichero_server.execution import jobs
    from fichero_server.models import DocType, Document
    from fichero_server.models.transfer import TransferMode
    from fichero_server.recipes import runner
    from fichero_server.transfer.copy import copy_into_target
    from fichero_server.transfer.plan import build_plan

    library = Path(db.path).parent
    stage_id = stage.id
    out: dict[str, Any] = {"state": "failed", "ran": [], "made": {"per_page": [], "names": []}, "texts": {},
                           "boxes": {}, "items": []}
    # A linked page whose original is not on this Mac fails every card with a bare errno, page after page (#5811, 28
    # times in a minute). Say it once, in words, with the fix.
    from fichero_server.importers import relink

    said = relink.missing_originals(db, set(page_ids))
    if said:
        out["error"] = said["sentence"]
        return out
    jobs.save_detail(db, job_id, json.dumps({"stage": stage_id}), reason=f"Copying the sample pages for {stage.title}")
    scratch = _folder(library) / f"{scratch_name}.fichero"
    shutil.rmtree(scratch, ignore_errors=True)
    for sub in ("lance", "storage", "files"):
        (scratch / sub).mkdir(parents=True, exist_ok=True)
    try:
        copy = db_manager.get_database(scratch)
        folder = Document(name="Samples", doc_type=DocType.folder)
        copy.save(folder)
        plan = build_plan(db, copy, items=page_ids, target_parent_id=folder.id, transfer_id=uuid.uuid4().hex,
                          audit_id=uuid.uuid4().hex, actor="try")
        copy_into_target(db, copy, plan, mode=TransferMode.copy, actor="try", finish=False)
        back = {new: old for old, new in plan.id_map.items()}
        pages = [plan.id_map[i] for i in page_ids if i in plan.id_map]
        stage_plan = _stage_plan(db, stage, setup, len(pages))
        missing = _await_downloads(db, stage_plan)
        if missing:
            out.update(state="failed", error=missing)
            return out
        cards = stage_plan["runs"]
        before = _snapshot(copy)
        ran, extra = [], {}
        stop = threading.Event()
        watcher = None
        if publish is not None:
            watcher = threading.Thread(target=_watch, args=(copy, before, back, publish, stop), name="try-progress",
                                       daemon=True)
            watcher.start()
        for card in cards:
            if card.get("card") in ("find-documents", "entries"):
                jobs.save_detail(db, job_id, json.dumps({"stage": stage_id}), reason=f"Trying {stage.title}: {name}")
                made_here, state, why = _organise(copy, card, pages, back)
                extra.update(made_here)
                ran.append({"steps": card["steps"], "state": state, "why": why})
                continue
            if card.get("card") == "regions":
                from fichero_server.recipes.regions import find_regions

                jobs.save_detail(db, job_id, json.dumps({"stage": stage_id}), reason=f"Trying {stage.title}: {name}")
                find_regions(copy, pages, job_id, str(card.get("model")), provider=card.get("provider") or "yolo")
                ran.append({"steps": card["steps"], "state": "done", "why": None})
                continue
            if card.get("card") != "workflow":
                ran.append({"steps": card.get("steps"), "state": "skipped", "why": "not tried on samples yet"})
                continue
            jobs.save_detail(db, job_id, json.dumps({"stage": stage_id}), reason=f"Trying {stage.title}: {name}")
            run_on, uncertain = pages, []
            if card.get("job") in runner._NAMES_JOBS:  # not on a reading too uncertain to name anyone (#5694)
                uncertain = runner.too_uncertain_for_names(copy, pages)
                run_on = [p for p in pages if p not in {e["page_id"] for e in uncertain}]
            _thread, state, why = runner._run_workflow(copy, card, run_on, job_id) if run_on else (None, "done", None)
            if uncertain:
                why = "; ".join(filter(None, [why, *(f"{e['page']}: {e['why']}" for e in uncertain)]))
            ran.append({"steps": card["steps"], "workflow": card["workflow"], "state": state, "why": why})
        stop.set()
        if watcher is not None:
            watcher.join()  # no late publish may land after the final result is written (review 323)
        made = _collect(copy, before, back)
        texts, boxes, items = _for_comparing(copy, before, back, stage_id)
        out.update(state="done" if all(r["state"] != "failed" for r in ran) else "failed", ran=ran,
                   made={**made, **extra}, texts=texts, boxes=boxes, items=items)
        failed = [_sentence(r["why"]) or "the run stopped before it finished" for r in ran if r["state"] == "failed"]
        if failed:
            out["error"] = "; ".join(failed)  # a failure always says why in words, never a blank
    except Exception as exc:  # noqa: BLE001 -- the try says why, in words; the project is untouched either way
        out.update(state="failed", error=_sentence(str(exc)) or "the run stopped")
    finally:
        if "stop" in locals():
            stop.set()
            if watcher is not None:
                watcher.join()
        db_manager.close_database(scratch)
        shutil.rmtree(scratch, ignore_errors=True)
    return out


def _organise(copy: Any, card: dict[str, Any], pages: list[str],
              back: dict[str, str]) -> tuple[dict[str, Any], str, str | None]:
    """Organise's steps on the copy (`organise-tried-on-a-run`): Find the Documents proposes, accepting nothing by
    itself; Split into entries splits the pages with text with the step's model. What they made, in the project's
    own page ids."""
    import asyncio

    from fichero_server.models import Document

    if card["card"] == "find-documents":
        from fichero_server.finddocs.job import find_documents

        documents = [{"page_ids": [back.get(i, i) for i in d.page_ids], "name": d.name, "kind": d.kind,
                      "confidence": d.confidence, "reasons": list(d.reasons)}
                     for proposal in find_documents(copy, pages) for d in proposal.documents]
        return {"documents": documents}, "done", None
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.diary_entries import split_pages_into_entries

    with_text = [d for d in (copy.get(Document, i) for i in pages) if d is not None and (d.page_content or "").strip()]
    if not with_text:
        return {"entries": []}, "done", "no page has text to split yet: Read comes first"
    made, _totals, errors, _lines = asyncio.run(split_pages_into_entries(
        copy, with_text, LLMConfig(provider=card["provider"], model=card["model"])))
    entries = [{"page_id": back.get(e.parent_id or "", e.parent_id), "name": e.name,
                "opening": (e.page_content or "").strip()[:200]} for e in made]
    return {"entries": entries}, ("failed" if errors and not made else "done"), "; ".join(errors) or None


def _for_comparing(copy: Any, before: dict[str, set[str]], back: dict[str, str],
                   stage_id: str) -> tuple[dict[str, str], dict[str, list[list[float]]], list[str]]:
    """What a run made, whole, for comparing it with another's: each original page's reading, its shapes (the
    stage's own kind: regions, or lines), and the items (names, statements, dates) it found."""
    from fichero_server.models import Document

    models = {m.__name__: m for m in copy._all_schema_models()}
    new = {name: [r for r in copy.all(models[name]) if r.id not in ids] for name, ids in before.items()}
    texts: dict[str, str] = {}
    for r in new.get("ContentRepresentation", []):
        page = back.get(r.document_id or "")
        if page is not None and (r.content or "").strip():
            texts[page] = (texts.get(page, "") + "\n" + r.content.strip()).strip()
    shape = "region" if stage_id == "find-regions" else "line"
    boxes: dict[str, list[list[float]]] = {}
    labels: list[str] = []
    for seg in new.get("Segment", []):
        page = back.get(seg.document_id or "")
        if page is not None and seg.kind == shape:
            boxes.setdefault(page, []).append([seg.bbox_x, seg.bbox_y, seg.bbox_w, seg.bbox_h])
            labels.append(seg.kind_raw or shape)
    if stage_id in SHAPE_STAGES:
        items = labels
    elif stage_id == "statements":
        items = [_readable(c) for c in new.get("KnowledgeClaim", [])]
    elif stage_id == "dates":
        items = [f"{back[d.id]}:{d.date_jdn}" for d in copy.all(Document) if d.id in back and d.date_jdn is not None]
    else:
        items = [e.canonical_name for e in new.get("KnowledgeEntity", [])]
    return texts, boxes, [i for i in items if i]


def _collect(copy: Any, before: dict[str, set[str]], back: dict[str, str]) -> dict[str, Any]:
    """What the run made on the copy, per original page: readings, lines and regions, statements; and the names."""
    models = {m.__name__: m for m in copy._all_schema_models()}
    per_page: dict[str, dict[str, Any]] = {}

    def page(doc_id: str | None) -> dict[str, Any] | None:
        original = back.get(doc_id or "")
        if original is None:
            return None
        return per_page.setdefault(original, {"id": original, "readings": [], "segments": {}, "statements": []})

    new = {name: [r for r in copy.all(models[name]) if r.id not in ids] for name, ids in before.items()}
    for r in new.get("ContentRepresentation", []):
        if (entry := page(r.document_id)) is not None:
            entry["readings"].append({"kind": r.kind, "level": r.level, "text": _readable(r)})
    for s in new.get("Segment", []):
        if (entry := page(s.document_id)) is not None:
            entry["segments"][s.kind] = entry["segments"].get(s.kind, 0) + 1
            entry.setdefault("shapes", []).append(s)
    for c in new.get("KnowledgeClaim", []):
        if (entry := page(getattr(c, "source_document_id", None))) is not None:
            entry["statements"].append(_readable(c))
    names = [{"name": e.canonical_name, "type": str(getattr(e.entity_type, "value", e.entity_type))}
             for e in new.get("KnowledgeEntity", [])]
    for entry in per_page.values():
        entry["shapes"] = shapes_of(entry.get("shapes", []))
    return {"per_page": list(per_page.values()), "names": names}


#: At most this many drawn shapes go with a page in a try's result (`source.onboard.stages.compare-results-per-model`).
MAX_SHAPES = 600


def shape_of(segment: Any) -> dict[str, Any]:
    """A segment as the compare window draws it: its kind, its box and baseline, normalised to the page."""
    return {"kind": segment.kind, "bbox": [segment.bbox_x, segment.bbox_y, segment.bbox_w, segment.bbox_h],
            "baseline": segment.baseline}


def shapes_of(segments: list[Any]) -> list[dict[str, Any]]:
    return [shape_of(s) for s in segments[:MAX_SHAPES]]


#: What a stage is doing, in the words of the progress line ("Kraken: page 2 of 5, finding lines").
STEP_WORDS = {"find-lines": "finding lines", "find-regions": "finding regions", "read": "reading",
              "normalise": "writing it as one level", "translate": "translating", "names": "finding names",
              "statements": "finding statements", "dates": "working out dates", "organise": "organising"}


def progress_of(made: list[dict[str, Any]], total: int, stage_id: str, state: str, page: str | None = None,
                waiting_for: str | None = None) -> dict[str, Any]:
    """One model's progress on a try, shown in place (`source.onboard.stages.try-progress-in-place`): the pages it has
    made something on so far, of the pages tried, and what it is doing in words."""
    done = sum(1 for p in made if p.get("readings") or p.get("segments") or p.get("statements"))
    return {"state": state, "done": done, "total": total, "page": page, "step": STEP_WORDS.get(stage_id, "working"),
            "waiting_for": waiting_for}


def publish_progress(library: Path, stage_id: str, card_id: str | None, progress: dict[str, Any],
                     made: list[dict[str, Any]]) -> None:
    """Write one candidate's progress and the pages it has finished into the kept result, so the app sees each page
    as it finishes; a stage try with no compared candidates (`card_id` None) publishes on the result itself. Read,
    changed and written under the file's lock. Nothing when the try's record is gone (replaced or cleared)."""
    path = _result_path(library, stage_id)
    with _file_lock(path):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if card_id is None:
            result.update(progress=progress, per_page=made)
        for column in result.get("candidates") or []:
            if column.get("card") == card_id:
                column.update(progress=progress, per_page=made, state=progress["state"])
        _write(library, stage_id, result)


def finished_progress(state: str, made: list[dict[str, Any]], total: int, stage_id: str) -> dict[str, Any]:
    """A run's last progress: how it ended and how many pages have a result."""
    return progress_of(made, total, stage_id, state)
