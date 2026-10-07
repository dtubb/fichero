"""The bake-off, slice 1: the readers (#4951, `source.try.bakeoff-is-the-same-tool`).

`source/models-chains-and-projects.md` sections 8 and 8a, `compute/distillation.md` "Evaluation against
out-of-the-box models". The bake-off is the evaluation job (`training/evaluation.py`) run on the project's
corrected sample pages: there is ONE comparison code path, so nothing here reads a page or scores one.
This module only decides what goes in and reads what came out:

* **Candidates.** The top three readers for the `read-a-line` step by rule rank (the same hard
  constraints and fixed order setup assembles the recipe with, `recipes/assemble.py`), for the project's
  script and its default material. Tesseract joins for print and typescript when its card has data for
  the project's language; never for handwriting. A cloud reader takes part only where the project
  allows the cloud (the rules already refuse it otherwise), and its whole-volume cost is shown before
  anything runs. A candidate the evaluation cannot score here (not on this Mac, its runtime not in this
  build, a remote model) is named with why, never silently dropped and never substituted.
* **Ground truth.** On each sample page, the newest pass a person made or marked ground truth (imported
  corrected transcriptions, #5513): its lines are the right readings; with none, the lines a person
  corrected inside another pass (#5499). The one choice is the evaluation's (`training.evaluation.
  reference_page`). The bake-off needs at least `MIN_LINES` such lines on at least `MIN_PAGES` pages; below
  that it says how many more are needed, in words, and runs nothing, and names imported transcriptions
  not yet marked ground truth, the usual reason a corpus project counts none.
* **The run.** One `evaluate-models` job in Activity, through the audited `evaluation.run` action: every
  scored candidate reads the same pages, scored by the one CER; the scores and the measured speed land on
  each model's card, keyed by the job.
* **The record.** One comparison record per bake-off, kept in the project folder
  (`recipe/bakeoffs/<id>.yaml`): its selection and its candidates. The table is rebuilt from the record
  and the cards, so it can be read back after the job row is cleared, and run again later.
* **The table.** Ranked by the fixed order: accuracy in bands (within one point of CER of the best are
  tied), then local before remote, cheaper, faster, lower carbon, trainable, smaller, the card id.
* **Read, measured, winner** (#5531). The evaluation's one judgement (`evaluation.judged`): a page a reader
  returned nothing (or far too little) for is not read, with why, never 100% CER; a candidate that read
  under `evaluation.MEASURED_SHARE` of the pages is "not measured: read N of M pages (why)" and has no
  CER; a measured one's CER is over the pages it read, with that count. A winner is named only when at
  least two candidates were measured; otherwise `no_winner_why` says why. Records and card entries kept
  before this are judged the same way when read.
* **Use This.** Sets the step's reader for the project or one folder, as an override on the recipe,
  through the audited `project.save_setup` path (`recipes/project.py` keeps the recipe).
"""
from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from fichero_server.recipes.assemble import Answers, Card, Choice, _chosen, _rank_key, _refusal

#: The recipe step this slice compares: the reader, the step with the most choice.
STEP = "read-a-line"
#: How much ground truth a fair bake-off needs (`source.onboard.bakeoff-minimum`).
MIN_LINES = 100
MIN_PAGES = 2
#: How many readers by rule rank take part (`source.try.bakeoff-is-the-same-tool`: the top three per step).
TOP = 3
#: Candidates within this much CER of the best are tied on accuracy (one point).
BAND = 0.01
#: The materials Tesseract reads; it is never proposed for handwriting.
TESSERACT_MATERIALS = ("print", "typescript")
#: Where the comparison records are kept, in the project's recipe folder.
RECORDS = "bakeoffs"
_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class BakeoffRefused(ValueError):
    """The bake-off cannot run or the choice cannot be used; the message says why, in words."""


# --- the candidates ----------------------------------------------------------------------------------


def _figure(value: float | None, basis: str, source: str) -> dict[str, Any]:
    from fichero_server.recipes.routes import _figure as figure

    return figure(value, basis, source)


def _reader_of(card: Card) -> tuple[str | None, str | None, str]:
    """(reader kind, model id as the evaluation runs it, provider) for the card's pin."""
    from fichero_server.recipes.cards import kraken_reader_for, mlx_model_for

    pin = card.pin
    if "zenodo" in pin:
        return "kraken", kraken_reader_for(pin), "omlx"
    if mlx_model_for(pin):
        return "vision", mlx_model_for(pin), "omlx"
    if set(pin) == {"cloud", "model"}:
        return "vision", str(pin["model"]), str(pin["cloud"])
    if "tesseract" in pin:
        return "tesseract", f"tesseract:{pin.get('traineddata')}", "tesseract"
    return None, None, ""


def _not_scored_because(card: Card, reader: str | None, model: str | None, provider: str) -> str | None:
    """Why the evaluation cannot score this candidate here, or None when it can."""
    from fichero_server.training.evaluation import LOCAL_PROVIDERS, on_this_mac

    if not card.runs_here:
        return "its runtime is not in this build yet (its card says so): named, not scored"
    if reader not in ("kraken", "vision") or model is None:
        return "the evaluation job cannot read with this kind of model yet"
    if reader == "vision" and provider not in LOCAL_PROVIDERS:
        return "a remote model target is not built in the evaluation job yet: priced, not scored"
    if not on_this_mac(model, reader):
        return "not on this Mac: download it to score it"
    return None


def _cost(card: Card, provider: str, model: str | None, volume: int) -> dict[str, Any]:
    """The whole volume's cost, before anything runs: nothing on this Mac; the price list for a cloud model."""
    if card.local:
        return _figure(0.0, "measured", "runs on this Mac")
    from fichero_server.recipes.routes import _cloud_cost

    return _figure(_cloud_cost(f"{provider}/{model}", volume), "estimate",
                   f"price list x per-page tokens, {volume} pages")


def reader_name(card: Card) -> str:
    """A reader as a person reads it: its card's own name, the `note` setup's recipe rows show for a step's
    model (one source), never its card id (section 7b: "never a raw model id")."""
    return card.note.strip().rstrip(".")


def _name_of(card_id: str) -> str:
    """The card's own name for a card id a record kept; empty for a card no longer shipped."""
    from fichero_server.recipes.discovery import known_cards

    return next((reader_name(c) for c in known_cards(include_not_built=True) if c.id == card_id), "")


def _candidate(card: Card, *, rule_rank: int | None, role: str, volume: int) -> dict[str, Any]:
    reader, model, provider = _reader_of(card)
    return {
        "card": card.id, "name": reader_name(card), "pin": dict(card.pin), "role": role, "rule_rank": rule_rank,
        "reader": reader, "model": model, "provider": provider, "runs_on": card.runs_on, "local": card.local,
        "not_scored": _not_scored_because(card, reader, model, provider),
        "cost_usd": _cost(card, provider, model, volume),
        "carbon_g_per_page": card.carbon_g_per_page, "trainable": card.trainable, "size_gb": card.size_gb,
        "material": sorted(card.material),
    }


def _tesseract_has_the_language(card: Card, a: Answers) -> bool:
    return bool(a.languages) and (card.languages is None or a.languages <= card.languages)


def candidates(a: Answers, cards: list[Card], *, volume: int) -> list[dict[str, Any]]:
    """The readers that take part, in rule rank, then the Tesseract baseline where it belongs."""
    material = a.material
    kept = [c for c in cards if c.runs_here and _refusal(STEP, c, a, material) is None]
    ranked = sorted(kept, key=lambda c: _rank_key(c, material))[:TOP]
    out = [_candidate(c, rule_rank=i, role="rule rank", volume=volume) for i, c in enumerate(ranked, 1)]
    print_like = [m for m in a.materials if m in TESSERACT_MATERIALS]
    if print_like:
        named = {c.id for c in ranked}
        for card in cards:
            if ("tesseract" in card.pin and STEP in card.jobs and card.id not in named
                    and _tesseract_has_the_language(card, a)
                    and any(_refusal(STEP, card, a, m) is None for m in print_like)):
                out.append(_candidate(card, rule_rank=None, role="baseline for print", volume=volume))
    return out


# --- the ground truth ----------------------------------------------------------------------------------


#: Imported formats that carry transcriptions (a YOLO or GCP file carries none, so it is never ground truth).
TRANSCRIPTION_FORMATS = ("pagexml", "alto", "tei", "hocr", "plain-text")


def person_made_pages(db: Any) -> list[str]:
    """Every page with a live pass a person made or marked ground truth (`made_by_a_person`, #5513), oldest
    pass first; then every page with a reading a person made on any pass (#5499)."""
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import SegmentPass, made_by_a_person

    passes = [p for p in db.query(SegmentPass) if not p.deleted_at and made_by_a_person(p)]
    pages = [p.document_id for p in sorted(passes, key=lambda p: p.created_at)]
    corrected = sorted((r for r in db.query(ContentRepresentation, provenance_kind="human") if r.segment_id),
                       key=lambda r: r.created_at)
    return list(dict.fromkeys(pages + [r.document_id for r in corrected]))


def unmarked_import_pages(db: Any) -> int:
    """How many pages hold imported transcriptions nobody has marked ground truth and no person-made pass:
    what the readiness sentence names, since on a corpus project it is why nothing counts (#5513)."""
    from fichero_server.models.segments import SegmentPass, made_by_a_person

    live = [p for p in db.query(SegmentPass) if not p.deleted_at]
    counted = {p.document_id for p in live if made_by_a_person(p)}
    return len({p.document_id for p in live
                if p.import_format in TRANSCRIPTION_FORMATS and not made_by_a_person(p)} - counted)


def ground_truth(db: Any, page_ids: list[str] | None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """(the sample pages with their corrected lines counted, the pages left out and why)."""
    from fichero_server.training.evaluation import reference_page

    pages, left_out = [], []
    for page_id in dict.fromkeys(page_ids or person_made_pages(db)):
        page, why = reference_page(db, page_id, None)
        if page is None:
            left_out.append({"document_id": page_id, "why": str(why)})
        else:
            pages.append({"document_id": page_id, "name": page["name"], "lines": len(page["lines"])})
    return pages, left_out


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def readiness(pages: list[dict[str, Any]], unmarked_pages: int = 0) -> dict[str, Any]:
    """Whether the sample pages hold enough ground truth for a fair bake-off: the corrected lines and pages
    counted, how many more of each are needed, and, when short, the sentence that says so. The one count
    behind both the list's readiness (shown before anything is pressed) and Start's refusal.

    `unmarked_pages` (`unmarked_import_pages`): pages of imported transcriptions not marked ground truth.
    When short and there are some, the sentence says so and how to mark them, since that is the usual
    reason a project of corrected files counts none (#5513)."""
    lines = sum(p["lines"] for p in pages)
    more_lines, more_pages = max(0, MIN_LINES - lines), max(0, MIN_PAGES - len(pages))
    sentence = None
    if more_lines or more_pages:
        needs = (f"Needs {MIN_LINES} corrected lines on at least {MIN_PAGES} pages; this project has {lines} on "
                 f"{_plural(len(pages), 'page')}.")
        if unmarked_pages:
            what = (f"{_plural(unmarked_pages, 'page')} {'has' if unmarked_pages == 1 else 'have'} imported "
                    "transcriptions not marked as ground truth: mark the corrected ones as ground truth "
                    "(Mark as Ground Truth on the pass), or correct more lines.")
        elif more_lines and more_pages:
            what = f"Correct {_plural(more_lines, 'more line')}, on at least {_plural(more_pages, 'more page')}."
        elif more_lines:
            what = f"Correct {_plural(more_lines, 'more line')}."
        else:
            what = f"Correct lines on {_plural(more_pages, 'more page')}."
        sentence = f"{needs} {what}"
    return {"ready": sentence is None, "lines": lines, "pages": len(pages), "min_lines": MIN_LINES,
            "min_pages": MIN_PAGES, "more_lines": more_lines, "more_pages": more_pages,
            "unmarked_import_pages": unmarked_pages, "sentence": sentence}


# --- starting --------------------------------------------------------------------------------------------


def start(db: Any, library: Path, a: Answers, cards: list[Card], *, page_ids: list[str] | None, volume: int,
          run_evaluation: Callable[[dict[str, Any]], str], now: str) -> dict[str, Any]:
    """Check the ground truth, pick the candidates, start the one evaluation job and keep the record.

    `run_evaluation` takes an `EvaluationRunRequest` as a dict and returns the job id (the audited
    `evaluation.run` action). Refused in words, with nothing run, below the threshold or when no
    candidate can be scored here."""
    pages, left_out = ground_truth(db, page_ids)
    ready = readiness(pages, unmarked_import_pages(db))
    if not ready["ready"]:
        raise BakeoffRefused(ready["sentence"])
    chosen = candidates(a, cards, volume=volume)
    scored = [c for c in chosen if c["not_scored"] is None]
    if not scored:
        # Each reader by its card's name, never its id (section 7b).
        why = " ".join(f"{c['name'] or 'A reader'}: {c['not_scored']}." for c in chosen)
        raise BakeoffRefused(f"No reader can be compared on this Mac yet. {why or 'No reader fits this project.'}")
    job_id = run_evaluation({
        "checked": None, "add_out_of_the_box": False, "held_out_ids": [p["document_id"] for p in pages],
        "language": sorted(a.languages)[0] if a.languages else None,
        "candidates": [{"model": c["model"], "reader": c["reader"], "provider": c["provider"]} for c in scored],
    })
    record = {"id": job_id, "job_id": job_id, "step": STEP, "started_at": now, "material": a.material,
              "volume": volume, "pages": pages, "left_out": left_out,
              "lines": sum(p["lines"] for p in pages), "candidates": chosen}
    write_record(library, record)
    return record


# --- the record ------------------------------------------------------------------------------------------


def _record_path(library: Path, bakeoff_id: str) -> Path:
    from fichero_server.recipes.project import FOLDER

    if not _ID.match(bakeoff_id):
        raise LookupError(f"no bake-off {bakeoff_id!r}")
    return Path(library) / FOLDER / RECORDS / f"{bakeoff_id}.yaml"


def write_record(library: Path, record: dict[str, Any]) -> None:
    from fichero_server.recipes.project import _write_yaml

    _write_yaml(_record_path(library, record["id"]), record)


def read_record(library: Path, bakeoff_id: str) -> dict[str, Any]:
    import yaml

    path = _record_path(library, bakeoff_id)
    if not path.is_file():
        raise LookupError(f"no bake-off {bakeoff_id}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_records(library: Path) -> list[dict[str, Any]]:
    """Every bake-off kept in the project, newest first."""
    import yaml

    from fichero_server.recipes.project import FOLDER

    folder = Path(library) / FOLDER / RECORDS
    records = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in folder.glob("*.yaml")] if folder.is_dir() else []
    return sorted(records, key=lambda r: str(r.get("started_at")), reverse=True)


# --- the table -------------------------------------------------------------------------------------------


def _scored_row(entry: dict[str, Any]) -> dict[str, Any]:
    """A candidate's row from its card's entry for this job, judged by the evaluation's one rule (an entry
    kept before #5531 has no read/measured fields: it is judged from the characters its pages recorded)."""
    from fichero_server.training.evaluation import judged
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    speed = entry.get("speed") or {}
    pages = entry.get("per_page") or []
    j = judged(pages, len(entry.get("pages") or pages))
    cer = j["scores"][DEFAULT_POLICY_NAME]["cer"] if j["measured"] else None
    return {"cer": cer, "policy": DEFAULT_POLICY_NAME if cer is not None else None,
            "scores": {name: s.get("cer") for name, s in j["scores"].items()} if j["measured"] else {},
            "per_page": [{"document_id": p["document_id"], "name": p["name"], "lines": p["lines"],
                          "cer": p["scores"][DEFAULT_POLICY_NAME].get("cer"), "read": p["read"], "why": p["why"]}
                         for p in j["per_page"]],
            "measured": j["measured"], "pages_read": j["pages_read"], "pages_total": j["pages_total"],
            "why": j["why"], "pages_per_hour": speed.get("pages_per_hour"), "seconds": speed.get("seconds")}


def _rank(rows: list[dict[str, Any]], material: str, volume: int) -> list[dict[str, Any]]:
    """The fixed order (section 8): accuracy in one-point bands from the best, then the rules' own order
    (`assemble._rank_key`: local, cheaper, faster, lower carbon, trainable, smaller, card id)."""
    measured = [r["cer"] for r in rows if r["cer"] is not None]
    best = min(measured) if measured else None

    def band(cer: float | None) -> float:
        if cer is None or best is None:
            return math.inf
        gap = cer - best
        return 0 if gap <= BAND + 1e-12 else math.ceil(gap / BAND - 1e-12)

    def key(r: dict[str, Any]) -> tuple:
        cost = r["cost_usd"]["value"]
        like = Card(id=r["card"], pin=r["pin"], jobs=frozenset(), scripts=None, languages=None,
                    material=frozenset(r["material"]), runs_on=r["runs_on"],
                    cost_per_page=(cost / volume) if cost is not None and volume else math.inf,
                    pages_per_hour=r["pages_per_hour"] or 0.0, carbon_g_per_page=r["carbon_g_per_page"],
                    trainable=r["trainable"], size_gb=r["size_gb"])
        return (band(r["cer"]), *_rank_key(like, material)[1:])

    ranked = sorted(rows, key=key)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


def result(db: Any, library: Path, bakeoff_id: str) -> dict[str, Any]:
    """The comparison: the record, the job's state and the ranked table, read from the cards."""
    from fichero_server.execution import jobs
    from fichero_server.training.evaluation import model_evaluations, no_winner_why

    record = read_record(library, bakeoff_id)
    job = jobs.read_job(db, record["job_id"])
    state = job["state"] if job else "cleared"
    rows, waiting = [], False
    for c in record["candidates"]:
        row = {k: c[k] for k in ("card", "pin", "role", "rule_rank", "reader", "model", "runs_on", "local",
                                 "cost_usd", "carbon_g_per_page", "trainable", "size_gb", "material")}
        # A record kept before rows carried a name reads it from the card now (one source: the card).
        row["name"] = c.get("name") or _name_of(c["card"])
        row.update(cer=None, policy=None, scores={}, per_page=[], pages_per_hour=None, seconds=None,
                   measured=False, pages_read=None, pages_total=None, why=c["not_scored"])
        if c["not_scored"] is None:
            entry = next((e for e in model_evaluations(c["model"], c["reader"])
                          if e.get("job_id") == record["job_id"]), None)
            if entry is not None:
                row.update(_scored_row(entry))
            else:
                waiting = state in ("waiting", "running")
                row["why"] = ("waiting for the evaluation job to score it" if waiting
                              else f"the evaluation job ended ({state}) without scoring it")
        rows.append(row)
    ranked = _rank(rows, record["material"], int(record.get("volume") or 0))
    # A winner only among the measured, and only when at least two were (#5531); none while still scoring.
    compared = [r for r in ranked if r["measured"] and r["cer"] is not None]
    no_winner = None if waiting else no_winner_why([r["name"] or "a reader" for r in compared])
    winner = compared[0]["card"] if not waiting and no_winner is None else None
    return {**{k: record[k] for k in ("id", "job_id", "step", "started_at", "pages", "left_out", "lines")},
            "state": state, "reason": job["reason"] if job else None, "rows": ranked, "winner": winner,
            "no_winner_why": no_winner}


# --- Use This --------------------------------------------------------------------------------------------


def use_this(recipe: dict[str, Any] | None, table: dict[str, Any], card: Card, *, scope: str,
             folder_id: str | None, now: str) -> dict[str, Any]:
    """The recipe with this bake-off's candidate as the step's reader for the scope, kept as an override.

    For the project, the step's own model is set from the candidate's card too, so Start reads with it;
    for a folder, only the override records it. A later Use This for the same step and scope replaces
    the earlier override."""
    import copy

    if not recipe:
        raise BakeoffRefused("this project has no recipe yet: run setup first")
    name = reader_name(card) or "That reader"
    row = next((r for r in table["rows"] if r["card"] == card.id), None)
    if row is None:
        raise BakeoffRefused(f"{name} is not one of this bake-off's candidates")
    if row["cer"] is None or not row.get("measured"):
        raise BakeoffRefused(f"{name} was not measured in this bake-off ({row['why']}), so it cannot be chosen "
                             "from it")
    if scope == "folder" and not folder_id:
        raise BakeoffRefused("name the folder to use it for")
    out = copy.deepcopy(recipe)
    step = next((s for s in out.get("steps") or [] if s.get("job") == table["step"]), None)
    if step is None:
        raise BakeoffRefused(f"this project's recipe has no {table['step']} step to set a reader for")
    because = (f"chosen in the bake-off on your pages: CER {row['cer'] * 100:.1f}% ({row['policy']}) on the "
               f"{row['pages_read']} of {_plural(row['pages_total'], 'page')} it read, {table['lines']} lines; "
               f"rank {row['rank']}")
    override = {"step": step["id"], "scope": scope, "folder_id": folder_id if scope == "folder" else None,
                "model": dict(card.pin), "card": card.id, "runs_on": card.runs_on, "from_bakeoff": table["id"],
                "cer": row["cer"], "policy": row["policy"], "because": because, "at": now}
    out["overrides"] = [o for o in out.get("overrides") or []
                        if (o.get("step"), o.get("scope"), o.get("folder_id"))
                        != (override["step"], override["scope"], override["folder_id"])] + [override]
    return apply_project_overrides(out, [card])


def apply_project_overrides(recipe: dict[str, Any], cards: list[Card]) -> dict[str, Any]:
    """Set each step a project-scope override names to that override's reader, as the step's own choice, so
    the recipe Start reads and the one setup proposes again both read with the reader the person chose
    (`source.try.use-this-scope`). The one code path for Use This and for assembling a project's recipe
    again. A folder override stays an override only: the step's own model is the project's. An override
    whose card is no longer shipped is kept and leaves the step to the rules. Changes `recipe` in place."""
    by_id = {c.id: c for c in cards}
    steps = {s.get("id"): s for s in recipe.get("steps") or []}
    for override in recipe.get("overrides") or []:
        step, card = steps.get(override.get("step")), by_id.get(override.get("card"))
        if override.get("scope") != "project" or step is None or card is None:
            continue
        for stale in ("gap", "problem"):
            step.pop(stale, None)
        measured = replace(card, cer_measured_here=override.get("cer"))
        step.update(_chosen(Choice(step["job"], measured, reasons=[override.get("because") or "chosen by you"])))
        step["uses_cloud"] = str(step.get("runs_on") or "").startswith("cloud")
    return recipe
