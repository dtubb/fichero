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
import shutil
import uuid
from pathlib import Path
from typing import Any

SAMPLES_FILE = "samples.json"
TRY_KIND = "try-a-stage"
MAX_SAMPLES, MIN_SAMPLES = 5, 3


def _folder(library: Path) -> Path:
    return library / "recipe" / "samples"


def _pages(db: Any) -> list[Any]:
    """The project's material in creation order, as a started recipe runs over it."""
    from fichero_server.models import Document

    return [d for d in (db.get(Document, i) for i in db.unit_of_work_ids()) if d is not None]


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


def chosen(db: Any) -> dict[str, Any]:
    """The samples: the person's choice when there is one, else Fichero's proposal."""
    from fichero_server.models import Document

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
    return result


def _write(library: Path, stage: str, result: dict[str, Any]) -> None:
    path = _result_path(library, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _stage_plan(db: Any, stage: Any, setup: dict[str, Any], page_count: int) -> dict[str, Any]:
    """The Start plan's cards for this stage's own steps, and what they would cost on the samples."""
    from fichero_server.recipes.start import estimate, plan_start

    recipe = setup["recipe"] or {}
    answers = setup["answers"] or {}
    steps = {s.get("id") for s in recipe.get("steps") or [] if s.get("job") in stage.jobs}
    plan = plan_start(recipe, stays_local=not answers.get("cloud_allowed", False), only=steps,
                      job_answers=answers.get("job_answers"), db=db)
    plan["estimate"] = estimate(plan["workflows"], page_count)
    return plan


def start_try(db: Any, stage_id: str, setup: dict[str, Any], *, page_ids: list[str] | None, cost_ok: bool,
              started_by: str, run_evaluation=None) -> dict[str, Any]:
    """Try a stage on the samples. Read and Find Lines start the bake-off on them; any other stage queues one
    `try-a-stage` job. ValueError, in words, for a stage that is off, cannot be tried, or would cost money without
    the yes (`cost_ok`)."""
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
    ids = page_ids or [p["id"] for p in chosen(db)["pages"]]
    if not ids:
        raise ValueError("This project has no pages to try it on yet")
    now = utc_now_iso(timespec="seconds")
    result: dict[str, Any] = {"stage": stage_id, "pages": ids, "tried_at": now, "state": "waiting"}
    if stage_id in TRIED_BY_THE_BAKEOFF:
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
    plan = _stage_plan(db, stage, setup, len(ids))
    if plan["refusals"]:
        raise ValueError(f"{stage.title} cannot run yet: " + "; ".join(plan["refusals"]))
    cost = plan["estimate"]["total_cost_usd"]
    clouded = [w for w in plan["workflows"] if str(w["runs_on"]).startswith("cloud")]
    if clouded and not cost_ok:
        said = f"about ${cost:.2f}" if isinstance(cost, (int, float)) else "a cost that is not known"
        raise PermissionError(f"Trying {stage.title} on {len(ids)} pages uses the cloud and costs {said}: "
                              "try it again with your yes to the cost")
    register_job_kinds()
    job_id = jobs.enqueue(db, TRY_KIND, f"{stage_id}:{uuid.uuid4().hex[:8]}", started_by=started_by, watched=True,
                          detail=json.dumps({"stage": stage_id, "pages": ids}))
    result.update(job_id=job_id, how="its own steps on a copy of these pages",
                  models=[{"steps": w["steps"], "model": w["model_override"], "where": w["runs_on"]}
                          for w in plan["workflows"]], cost=plan["estimate"])
    _write(library, stage_id, result)
    return result


def register_job_kinds() -> None:
    from fichero_server.execution import jobs

    if TRY_KIND not in jobs.KINDS or jobs.KINDS[TRY_KIND].run is None:
        # The recipes lane, as a recipe run: it only waits on its steps' own jobs, never holds the model lane they need.
        jobs.register_kind(TRY_KIND, _run_try, model=None, lane="recipes", name="Try a stage on the sample pages")


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
    """The job: copy the samples into a scratch project, run the stage's cards there, keep what they made."""
    from fichero_server.db.manager import db_manager
    from fichero_server.execution import jobs
    from fichero_server.models import DocType, Document
    from fichero_server.models.transfer import TransferMode
    from fichero_server.recipes import runner
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.stages import get_stage
    from fichero_server.transfer.copy import copy_into_target
    from fichero_server.transfer.plan import build_plan

    stage_id = subject.split(":", 1)[0]
    library = Path(db.path).parent
    job_id = jobs.current_job_id() or jobs.job_id_for(db, TRY_KIND, subject)
    result = json.loads(_result_path(library, stage_id).read_text(encoding="utf-8"))
    stage = get_stage(stage_id)
    setup = read_project_setup(library)
    scratch = _folder(library) / f"{stage_id}.fichero"
    shutil.rmtree(scratch, ignore_errors=True)
    for sub in ("lance", "storage", "files"):
        (scratch / sub).mkdir(parents=True, exist_ok=True)
    try:
        copy = db_manager.get_database(scratch)
        folder = Document(name="Samples", doc_type=DocType.folder)
        copy.save(folder)
        plan = build_plan(db, copy, items=result["pages"], target_parent_id=folder.id, transfer_id=uuid.uuid4().hex,
                          audit_id=uuid.uuid4().hex, actor="try")
        copy_into_target(db, copy, plan, mode=TransferMode.copy, actor="try", finish=False)
        back = {new: old for old, new in plan.id_map.items()}
        pages = [plan.id_map[i] for i in result["pages"] if i in plan.id_map]
        cards = _stage_plan(db, stage, setup, len(pages))["runs"]
        before = _snapshot(copy)
        ran = []
        for card in cards:
            if card.get("card") != "workflow":
                ran.append({"steps": card.get("steps"), "state": "skipped", "why": "not tried on samples yet"})
                continue
            jobs.save_detail(db, job_id, json.dumps({"stage": stage_id}), reason=f"Trying {stage.title}: {card['workflow']}")
            _thread, state, why = runner._run_workflow(copy, card, pages, job_id)
            ran.append({"steps": card["steps"], "workflow": card["workflow"], "state": state, "why": why})
        made = _collect(copy, before, back)
        result.update(state="done" if all(r["state"] != "failed" for r in ran) else "failed", ran=ran, **made)
    except Exception as exc:  # noqa: BLE001 -- the try says why; the project is untouched either way
        result.update(state="failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        db_manager.close_database(scratch)
        shutil.rmtree(scratch, ignore_errors=True)
    _write(library, stage_id, result)
    return result


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
    for c in new.get("KnowledgeClaim", []):
        if (entry := page(getattr(c, "source_document_id", None))) is not None:
            entry["statements"].append(_readable(c))
    names = [{"name": e.canonical_name, "type": str(getattr(e.entity_type, "value", e.entity_type))}
             for e in new.get("KnowledgeEntity", [])]
    return {"per_page": list(per_page.values()), "names": names}
