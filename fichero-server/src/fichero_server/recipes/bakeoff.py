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
* **Ground truth.** On each sample page, the newest pass a person made: its lines are the right readings.
  The bake-off needs at least `MIN_LINES` such lines on at least `MIN_PAGES` pages; below that it says
  how many more are needed, in words, and runs nothing.
* **The run.** One `evaluate-models` job in Activity, through the audited `evaluation.run` action: every
  scored candidate reads the same pages, scored by the one CER; the scores and the measured speed land on
  each model's card, keyed by the job.
* **The record.** One comparison record per bake-off, kept in the project folder
  (`recipe/bakeoffs/<id>.yaml`): its selection and its candidates. The table is rebuilt from the record
  and the cards, so it can be read back after the job row is cleared, and run again later.
* **The table.** Ranked by the fixed order: accuracy in bands (within one point of CER of the best are
  tied), then local before remote, cheaper, faster, lower carbon, trainable, smaller, the card id.
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
    from fichero_server.recipes.cards import kraken_reader_for

    pin = card.pin
    if "zenodo" in pin:
        return "kraken", kraken_reader_for(pin), "omlx"
    if set(pin) == {"hf", "revision"} and str(pin["hf"]).startswith("mlx-community/"):
        return "vision", str(pin["hf"]), "omlx"
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


def _candidate(card: Card, *, rule_rank: int | None, role: str, volume: int) -> dict[str, Any]:
    reader, model, provider = _reader_of(card)
    return {
        "card": card.id, "pin": dict(card.pin), "role": role, "rule_rank": rule_rank,
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


def person_made_pages(db: Any) -> list[str]:
    """Every page with a live pass a person made, oldest pass first."""
    from fichero_server.models.segments import SegmentPass

    passes = [p for p in db.query(SegmentPass, provenance_kind="human") if not p.deleted_at]
    return list(dict.fromkeys(p.document_id for p in sorted(passes, key=lambda p: p.created_at)))


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


def shortfall(pages: list[dict[str, Any]]) -> str | None:
    """How much more ground truth the bake-off needs, in words; None when there is enough."""
    lines = sum(p["lines"] for p in pages)
    if lines >= MIN_LINES and len(pages) >= MIN_PAGES:
        return None
    more = []
    if lines < MIN_LINES:
        n = MIN_LINES - lines
        more.append(f"{n} more corrected line{'s' if n != 1 else ''}")
    if len(pages) < MIN_PAGES:
        n = MIN_PAGES - len(pages)
        more.append(f"corrected lines on {n} more page{'s' if n != 1 else ''}")
    return (f"The bake-off needs at least {MIN_LINES} corrected lines on at least {MIN_PAGES} pages; there "
            f"{'is' if lines == 1 else 'are'} {lines} on {len(pages)} page{'s' if len(pages) != 1 else ''}. "
            f"Correct {' and '.join(more)}, and it will be offered again.")


# --- starting --------------------------------------------------------------------------------------------


def start(db: Any, library: Path, a: Answers, cards: list[Card], *, page_ids: list[str] | None, volume: int,
          run_evaluation: Callable[[dict[str, Any]], str], now: str) -> dict[str, Any]:
    """Check the ground truth, pick the candidates, start the one evaluation job and keep the record.

    `run_evaluation` takes an `EvaluationRunRequest` as a dict and returns the job id (the audited
    `evaluation.run` action). Refused in words, with nothing run, below the threshold or when no
    candidate can be scored here."""
    pages, left_out = ground_truth(db, page_ids)
    short = shortfall(pages)
    if short is not None:
        raise BakeoffRefused(short)
    chosen = candidates(a, cards, volume=volume)
    scored = [c for c in chosen if c["not_scored"] is None]
    if not scored:
        why = "; ".join(f"{c['card']}: {c['not_scored']}" for c in chosen) or "no reader fits this project's answers"
        raise BakeoffRefused(f"no candidate reader can be scored on this Mac ({why})")
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
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    speed = entry.get("speed") or {}
    return {"cer": entry["scores"][DEFAULT_POLICY_NAME]["cer"], "policy": DEFAULT_POLICY_NAME,
            "scores": {name: s.get("cer") for name, s in entry["scores"].items()},
            "per_page": [{"document_id": p["document_id"], "name": p["name"], "lines": p["lines"],
                          "cer": p["scores"][DEFAULT_POLICY_NAME].get("cer")} for p in entry.get("per_page") or []],
            "pages_per_hour": speed.get("pages_per_hour"), "seconds": speed.get("seconds")}


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
    from fichero_server.training.evaluation import model_evaluations

    record = read_record(library, bakeoff_id)
    job = jobs.read_job(db, record["job_id"])
    state = job["state"] if job else "cleared"
    rows = []
    for c in record["candidates"]:
        row = {k: c[k] for k in ("card", "pin", "role", "rule_rank", "reader", "model", "runs_on", "local",
                                 "cost_usd", "carbon_g_per_page", "trainable", "size_gb", "material")}
        row.update(cer=None, policy=None, scores={}, per_page=[], pages_per_hour=None, seconds=None,
                   why=c["not_scored"])
        if c["not_scored"] is None:
            entry = next((e for e in model_evaluations(c["model"], c["reader"])
                          if e.get("job_id") == record["job_id"]), None)
            if entry is not None:
                row.update(_scored_row(entry))
            else:
                row["why"] = ("waiting for the evaluation job to score it" if state in ("waiting", "running")
                              else f"the evaluation job ended ({state}) without scoring it")
        rows.append(row)
    ranked = _rank(rows, record["material"], int(record.get("volume") or 0))
    winner = next((r["card"] for r in ranked if r["cer"] is not None), None)
    return {**{k: record[k] for k in ("id", "job_id", "step", "started_at", "pages", "left_out", "lines")},
            "state": state, "reason": job["reason"] if job else None, "rows": ranked, "winner": winner}


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
    row = next((r for r in table["rows"] if r["card"] == card.id), None)
    if row is None:
        raise BakeoffRefused(f"{card.id} is not one of this bake-off's candidates")
    if row["cer"] is None:
        raise BakeoffRefused(f"{card.id} was not scored in this bake-off ({row['why']}), so it cannot be chosen from it")
    if scope == "folder" and not folder_id:
        raise BakeoffRefused("name the folder to use it for")
    out = copy.deepcopy(recipe)
    step = next((s for s in out.get("steps") or [] if s.get("job") == table["step"]), None)
    if step is None:
        raise BakeoffRefused(f"this project's recipe has no {table['step']} step to set a reader for")
    pages = len(row["per_page"])
    because = (f"chosen in the bake-off on your pages: CER {row['cer'] * 100:.1f}% ({row['policy']}) on "
               f"{pages} page{'s' if pages != 1 else ''}, {table['lines']} lines; rank {row['rank']}")
    override = {"step": step["id"], "scope": scope, "folder_id": folder_id if scope == "folder" else None,
                "model": dict(card.pin), "card": card.id, "runs_on": card.runs_on, "from_bakeoff": table["id"],
                "cer": row["cer"], "policy": row["policy"], "because": because, "at": now}
    out["overrides"] = [o for o in out.get("overrides") or []
                        if (o.get("step"), o.get("scope"), o.get("folder_id"))
                        != (override["step"], override["scope"], override["folder_id"])] + [override]
    if scope == "project":
        for stale in ("gap", "problem"):
            step.pop(stale, None)
        step.update(_chosen(Choice(step["job"], replace(card, cer_measured_here=row["cer"]), reasons=[because])))
        step["uses_cloud"] = str(step.get("runs_on") or "").startswith("cloud")
    return out
