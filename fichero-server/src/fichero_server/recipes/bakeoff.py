"""The bake-off, slice 1: the readers (#4951, `source.try.bakeoff-is-the-same-tool`).

`source/models-chains-and-projects.md` sections 8 and 8a, `compute/distillation.md` "Evaluation against
out-of-the-box models". The bake-off is the evaluation job (`training/evaluation.py`) run on the project's
corrected sample pages: there is ONE comparison code path, so nothing here reads a page or scores one.
This module only decides what goes in and reads what came out:

* **Candidates.** At most two readers of each kind (Kraken, Apple Vision, an MLX vision model, a cloud reader;
  `PER_KIND`, ruled 2026-10-11: search wide, the bake-off decides), from everything the finder found, for the
  project's script and its default material; the rules' order only chooses who takes part within a kind. Tesseract joins for print and typescript when its card has data for
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

from fichero_server.recipes.assemble import APPLE_LINES_PIN, Answers, Card, Choice, _chosen, _rank_key, _refusal, in_period
from fichero_server.recipes.cards import seed_cards

#: The recipe step this slice compares: the reader, the step with the most choice.
STEP = "read-a-line"
#: How much ground truth a fair bake-off needs (`source.onboard.bakeoff-minimum`).
MIN_LINES = 100
MIN_PAGES = 2
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
    if pin.get("builtin") == "apple-vision":
        from fichero_server.training.evaluation import APPLE_VISION

        return "vision", APPLE_VISION, "apple"
    if "zenodo" in pin:
        return "kraken", kraken_reader_for(pin), "omlx"
    if mlx_model_for(pin):
        return "vision", mlx_model_for(pin), "omlx"
    if set(pin) == {"cloud", "model"}:
        return "vision", str(pin["model"]), str(pin["cloud"])
    if "tesseract" in pin:
        return "tesseract", f"tesseract:{pin.get('traineddata')}", "tesseract"
    return None, None, ""


def _not_scored_because(card: Card, reader: str | None, model: str | None, provider: str,
                        remote_allowed: bool = False) -> str | None:
    """Why the evaluation cannot score this candidate here, or None when it can."""
    from fichero_server.training.evaluation import LOCAL_PROVIDERS, on_this_mac

    if not card.runs_here:
        return card.cannot_run_because or "its runtime is not in this build yet (its card says so): named, not scored"
    if not card.open_licence:
        # Reading pages with it is using it: a licence not yet accepted is accepted first (#5683).
        return f"its licence ({card.licence or 'not open'}) is not accepted yet: accept it to compare it"
    if reader not in ("kraken", "vision") or model is None:
        return "the evaluation job cannot read with this kind of model yet"
    if reader == "vision" and provider == "apple" and not on_this_mac(model, reader, provider):
        from fichero_server.training.evaluation import apple_vision_warming_up

        if apple_vision_warming_up():
            return "Apple Vision is still starting up on this Mac: ask again in a moment"
        return "Apple Vision's text recognition is not available on this Mac"
    if reader == "vision" and provider not in LOCAL_PROVIDERS:
        return None if remote_allowed else "this project keeps its pages on this Mac: priced, not scored"
    if not on_this_mac(model, reader, provider):
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


def _period_refusal(card: Card, a: Answers) -> str | None:
    """Why a reader made for another period is named but not scored (#5715), or None. The rules only rank it lower
    (`candidates-filtered-then-ranked`); the bake-off does not spend a trial on a hand it says it was not made for."""
    if a.material != "handwriting" or in_period(card, a) is not False:
        return None
    return f"it was made for pages of {card.period[0]}–{card.period[1]}, not the project's period"


def _candidate(card: Card, *, rule_rank: int | None, role: str, volume: int,
               remote_allowed: bool = False, sample_pages: int = 0, a: Answers | None = None) -> dict[str, Any]:
    reader, model, provider = _reader_of(card)
    from fichero_server.training.evaluation import granularities_for

    wrong_period = _period_refusal(card, a) if a is not None else None
    return {
        "card": card.id, "name": reader_name(card), "pin": dict(card.pin), "role": role, "rule_rank": rule_rank,
        "reader": reader, "model": model, "provider": provider, "runs_on": card.runs_on, "local": card.local,
        "not_scored": wrong_period or _not_scored_because(card, reader, model, provider, remote_allowed),
        "cost_usd": _cost(card, provider, model, volume),
        "run_cost_usd": _cost(card, provider, model, sample_pages),
        "carbon_g_per_page": card.carbon_g_per_page, "trainable": card.trainable, "size_gb": card.size_gb,
        "material": sorted(card.material),
        "lines_per_request": card.lines_per_request,
        "granularities": list(granularities_for(reader, provider, card.lines_per_request)),
    }


def _tesseract_has_the_language(card: Card, a: Answers) -> bool:
    return bool(a.languages) and (card.languages is None or a.languages <= card.languages)


#: The kinds of reader a bake-off always tries, at most `PER_KIND` of each (#5660 item 7): Kraken's readers, Apple
#: Vision, an MLX vision model, and a cloud reader where a provider is set up and the project lets pages leave.
FAMILIES = ("kraken", "apple", "mlx", "cloud")


def _family(card: Card) -> str | None:
    from fichero_server.recipes.cards import mlx_model_for

    pin = card.pin
    if "zenodo" in pin:
        return "kraken"
    if pin.get("builtin") == "apple-vision":
        return "apple"
    if mlx_model_for(pin):
        return "mlx"
    if set(pin) == {"cloud", "model"} and not card.local:
        return "cloud"
    return None


def cloud_readers() -> list[Card]:
    """The readers at the person's remote endpoints (`discovery.remote_reader_cards`, one list for the finder and the
    bake-off)."""
    from fichero_server.recipes.discovery import remote_reader_cards

    return remote_reader_cards()


#: At most this many readers of each kind take part, so a run stays affordable (ruled 2026-10-11).
PER_KIND = 2


def candidates(a: Answers, cards: list[Card], *, volume: int, sample_pages: int = 0,
               named: list[str] | None = None) -> list[dict[str, Any]]:
    """The readers that take part (ruled 2026-10-11: no fixed ranking decides; the bake-off does): from everything the
    finder found (the shipped cards, the models here, Kraken's repository, Hugging Face, and the remote endpoints the
    person has set up), at most `PER_KIND` of each kind (`FAMILIES`: Kraken, Apple Vision, an MLX vision model, a
    cloud reader), then the Tesseract baseline where it belongs. Within a kind the rules' order only chooses which
    take part; the winner is the one measured best. A kind with no model that reads here is listed once, with why
    (not available yet, not on this Mac, the pages stay here). A language with no Kraken reader still has its
    Hugging Face and remote readers. `sample_pages`: each candidate's `run_cost_usd` is what it costs to read the
    sample, said before the bake-off starts. `named`: card ids the person asked to have compared: they take part
    in addition to the `PER_KIND` the rules' order chooses, so naming a reader never removes another (#5718)."""
    material = a.material
    remote = bool(a.cloud_allowed)

    def fits(card: Card) -> bool:
        # Its script and language, whatever job its card names: a page reader reads the lines' pictures too.
        refused = _refusal(STEP, replace(card, jobs=frozenset({STEP})), a, material)
        return refused is None or refused[0] in ("cloud-not-allowed", "licence-not-accepted")

    pool = list({c.id: c for c in [*cards, *cloud_readers()]}.values())
    out, placed = [], set()
    wanted = set(named or [])
    for family in FAMILIES:
        # Those that can be scored here first (downloaded, allowed to leave), so the places go to readers that will
        # be measured; then an open licence; then the rules' order, which only chooses who takes part.
        options = sorted((c for c in pool if _family(c) == family and fits(c)),
                         key=lambda c: (not c.runs_here, _not_scored_because(c, *_reader_of(c), remote) is not None,
                                        not c.open_licence, _rank_key(c, material, a)))
        chosen_by_name = [c for c in options if c.id in wanted]
        rest = [c for c in options if c.id not in wanted]
        taking = chosen_by_name + ([c for c in rest if c.runs_here][:PER_KIND] or rest[:1])
        for card in taking:
            out.append(_candidate(card, rule_rank=None, role="contender", volume=volume, remote_allowed=remote,
                                  sample_pages=sample_pages, a=a))
            placed.add(card.id)
    print_like = [m for m in a.materials if m in TESSERACT_MATERIALS]
    if print_like:
        for card in cards:
            if ("tesseract" in card.pin and STEP in card.jobs and card.id not in placed
                    and _tesseract_has_the_language(card, a)
                    and any(_refusal(STEP, card, a, m) is None for m in print_like)):
                out.append(_candidate(card, rule_rank=None, role="baseline for print", volume=volume,
                                      sample_pages=sample_pages))
    return out


#: How many of the best vision candidates are asked at every granularity (`source.try.asking-granularity-is-measured`).
TRIAL_BEST = 2


def _trial_cost(scored: list[dict[str, Any]], named: list[str]) -> float:
    """What asking the best candidates at their other granularities can cost at most, before anything runs: the
    `TRIAL_BEST` dearest cloud candidates (who is best is not known yet) and any named, each run at its other
    granularities. Unknown prices count as nothing here; `cost_known` already says the total is a lower bound."""
    extra = {c["card"]: (c["run_cost_usd"]["value"] or 0.0) * (len(c.get("granularities") or ()) - 1)
             for c in scored if not c["local"] and c.get("granularities")}
    dearest = sorted(extra.values(), reverse=True)[:TRIAL_BEST]
    return sum(dearest) + sum(v for card, v in extra.items() if card in named and v not in dearest)


def next_run(db: Any, a: Answers, cards: list[Card], *, volume: int, named: list[str] | None = None) -> dict[str, Any]:
    """Who would take part in a bake-off started now, and what it would cost, before anything is pressed (ruled
    2026-10-11): each candidate with its cost on the sample pages, the total of those that would be scored, and the
    sentence that says it."""
    pages, _ = ground_truth(db, None)
    chosen = candidates(a, cards, volume=volume, sample_pages=len(pages), named=named)
    scored = [c for c in chosen if c["not_scored"] is None]
    paid = [c for c in scored if not c["local"]]
    total = sum(c["run_cost_usd"]["value"] or 0.0 for c in paid)
    trial = _trial_cost(scored, named or [])
    asked_again = [c for c in scored if c.get("granularities")]
    unknown = any(c["run_cost_usd"]["value"] is None for c in paid)
    if not paid:
        sentence = f"Every reader compared runs on this Mac: the comparison costs nothing ({len(scored)} readers)."
    else:
        sentence = (f"The comparison costs {'at least ' if unknown else 'about '}${total:.2f}: {len(paid)} cloud "
                    f"reader{'s' if len(paid) != 1 else ''} on {len(pages)} page{'s' if len(pages) != 1 else ''}; "
                    f"the other {len(scored) - len(paid)} run on this Mac, free.")
    if asked_again:
        sentence += (" The two best readers that take a picture of each line, and any you name, are then asked again "
                     "a line, a region and a page at a time" + (f": up to ${trial:.2f} more." if trial else ", free."))
    return {"candidates": chosen, "pages": len(pages), "run_cost_usd": round(total, 4),
            "granularity_run_cost_usd": round(trial, 4), "cost_known": not unknown, "sentence": sentence}


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
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def readiness(pages: list[dict[str, Any]], unmarked_pages: int = 0, *, min_lines: int = MIN_LINES) -> dict[str, Any]:
    """Whether the sample pages hold enough ground truth for a fair bake-off: the corrected lines and pages
    counted, how many more of each are needed, and, when short, the sentence that says so. The one count
    behind both the list's readiness (shown before anything is pressed) and Start's refusal.

    `unmarked_pages` (`unmarked_import_pages`): pages of imported transcriptions not marked ground truth.
    When short and there are some, the sentence says so and how to mark them, since that is the usual
    reason a project of corrected files counts none (#5513). `min_lines`: training's threshold is counted and said
    the same way (`recipes.train_offers`, #5660 item 9)."""
    lines = sum(p["lines"] for p in pages)
    more_lines, more_pages = max(0, min_lines - lines), max(0, MIN_PAGES - len(pages))
    sentence = None
    if more_lines or more_pages:
        needs = (f"Needs {min_lines:,} corrected lines on at least {MIN_PAGES} pages; this project has {lines} on "
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
    return {"ready": sentence is None, "lines": lines, "pages": len(pages), "min_lines": min_lines,
            "min_pages": MIN_PAGES, "more_lines": more_lines, "more_pages": more_pages,
            "unmarked_import_pages": unmarked_pages, "sentence": sentence}


# --- starting --------------------------------------------------------------------------------------------


def start(db: Any, library: Path, a: Answers, cards: list[Card], *, page_ids: list[str] | None, volume: int,
          run_evaluation: Callable[[dict[str, Any]], str], now: str, named: list[str] | None = None) -> dict[str, Any]:
    """Check the ground truth, pick the candidates, start the one evaluation job and keep the record.

    `run_evaluation` takes an `EvaluationRunRequest` as a dict and returns the job id (the audited
    `evaluation.run` action). Refused in words, with nothing run, below the threshold or when no
    candidate can be scored here. `named`: card ids the person named, asked at every granularity whatever
    their score."""
    pages, left_out = ground_truth(db, page_ids)
    ready = readiness(pages, unmarked_import_pages(db))
    if not ready["ready"]:
        raise BakeoffRefused(ready["sentence"])
    chosen = candidates(a, cards, volume=volume, sample_pages=len(pages), named=named)
    scored = [c for c in chosen if c["not_scored"] is None]
    if not scored:
        # Each reader by its card's name, never its id (section 7b).
        why = " ".join(f"{c['name'] or 'A reader'}: {c['not_scored']}." for c in chosen)
        raise BakeoffRefused(f"No reader can be compared on this Mac yet. {why or 'No reader fits this project.'}")
    job_id = run_evaluation({
        "checked": None, "add_out_of_the_box": False, "held_out_ids": [p["document_id"] for p in pages],
        "language": sorted(a.languages)[0] if a.languages else None, "remote_allowed": bool(a.cloud_allowed),
        "candidates": [{"model": c["model"], "reader": c["reader"], "provider": c["provider"],
                        "lines_per_request": c.get("lines_per_request")} for c in scored],
        "granularities_for_best": TRIAL_BEST, "named": [c["model"] for c in scored if c["card"] in (named or [])],
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
    from fichero_server.training.evaluation import judged, wer_over
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
            "why": j["why"], "pages_per_hour": speed.get("pages_per_hour"), "seconds": speed.get("seconds"),
            "wer": wer_over(j["per_page"]) if j["measured"] else None}


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
    if record.get("step") == LINES_STEP:
        return lines_result(db, record)
    job = jobs.read_job(db, record["job_id"])
    state = job["state"] if job else "cleared"
    rows, waiting = [], False
    for c in record["candidates"]:
        row = {k: c[k] for k in ("card", "pin", "role", "rule_rank", "reader", "model", "runs_on", "local",
                                 "cost_usd", "carbon_g_per_page", "trainable", "size_gb", "material")}
        # A record kept before rows carried a name reads it from the card now (one source: the card).
        row["name"] = c.get("name") or _name_of(c["card"])
        row.update(cer=None, policy=None, scores={}, per_page=[], pages_per_hour=None, seconds=None,
                   measured=False, pages_read=None, pages_total=None, why=c["not_scored"], wer=None,
                   granularity=None, lines_per_request=c.get("lines_per_request"))
        if c["not_scored"] is not None:
            rows.append(row)
            continue
        # One row for each way the job asked it (#5722): a model asked at several granularities has several.
        entries = [e for e in model_evaluations(c["model"], c["reader"]) if e.get("job_id") == record["job_id"]]
        if not entries:
            waiting = state in ("waiting", "running")
            row["why"] = ("waiting for the evaluation job to score it" if waiting
                          else f"the evaluation job ended ({state}) without scoring it")
            rows.append(row)
        for entry in entries:
            rows.append({**row, **_scored_row(entry), "granularity": entry.get("granularity")})
    ranked = _rank(rows, record["material"], int(record.get("volume") or 0))
    # A winner only among the measured, and only when at least two were (#5531); none while still scoring.
    # Two rows of one reader asked two ways are one reader.
    compared = [r for r in ranked if r["measured"] and r["cer"] is not None]
    no_winner = None if waiting else no_winner_why(list({r["card"]: r["name"] or "a reader" for r in compared}.values()))
    winning = compared[0] if not waiting and no_winner is None else None
    return {**{k: record[k] for k in ("id", "job_id", "step", "started_at", "pages", "left_out", "lines")},
            "state": state, "reason": job["reason"] if job else None, "rows": ranked,
            "winner": winning["card"] if winning else None,
            "winner_granularity": winning["granularity"] if winning else None, "no_winner_why": no_winner}


# --- Use This --------------------------------------------------------------------------------------------


def use_this(recipe: dict[str, Any] | None, table: dict[str, Any], card: Card, *, scope: str,
             folder_id: str | None, now: str, granularity: str | None = None) -> dict[str, Any]:
    """The recipe with this bake-off's candidate as the step's reader for the scope, kept as an override.

    For the project, the step's own model is set from the candidate's card too, so Start reads with it;
    for a folder, only the override records it. A later Use This for the same step and scope replaces
    the earlier override. A reader measured at several granularities is used at the one named (`granularity`),
    else at its best-ranked row's; the step and the override record it (#5722)."""
    import copy

    if not recipe:
        raise BakeoffRefused("this project has no recipe yet: run setup first")
    name = reader_name(card) or "That reader"
    row = next((r for r in table["rows"] if r["card"] == card.id
                and (granularity is None or r.get("granularity") == granularity)), None)
    if row is None and granularity is not None:
        raise BakeoffRefused(f"{name} was not measured at that granularity ({granularity}) in this bake-off")
    if row is None:
        raise BakeoffRefused(f"{name} is not one of this bake-off's candidates")
    lines = table["step"] == LINES_STEP
    if not row.get("measured") or (row["cer"] is None and not lines):
        raise BakeoffRefused(f"{name} was not measured in this bake-off ({row['why']}), so it cannot be chosen "
                             "from it")
    if lines and "kraken" not in card.pin and card.pin != APPLE_LINES_PIN:
        raise BakeoffRefused(f"{name} was compared, but the line step runs Kraken's line finder and Apple Vision's "
                             "lines only so far: it cannot be chosen for the step yet")
    if scope == "folder" and not folder_id:
        raise BakeoffRefused("name the folder to use it for")
    out = copy.deepcopy(recipe)
    step = next((s for s in out.get("steps") or [] if s.get("job") == table["step"]), None)
    if step is None:
        raise BakeoffRefused(f"this project's recipe has no {table['step']} step to set a reader for")
    because = (f"chosen in the comparison on your pages: found {row['lines_found']} of {row['lines_checked']} "
               f"checked lines; rank {row['rank']}" if lines else
               f"chosen in the bake-off on your pages: CER {row['cer'] * 100:.1f}% ({row['policy']}) on the "
               f"{row['pages_read']} of {_plural(row['pages_total'], 'page')} it read, {table['lines']} lines; "
               f"rank {row['rank']}" + (f", asked by {row['granularity']}" if row.get("granularity") else ""))
    override = {"step": step["id"], "scope": scope, "folder_id": folder_id if scope == "folder" else None,
                "model": dict(card.pin), "card": card.id, "runs_on": card.runs_on, "from_bakeoff": table["id"],
                "cer": row["cer"], "policy": row["policy"], "because": because, "at": now,
                "granularity": row.get("granularity")}
    out["overrides"] = [o for o in out.get("overrides") or []
                        if (o.get("step"), o.get("scope"), o.get("folder_id"))
                        != (override["step"], override["scope"], override["folder_id"])] + [override]
    return apply_project_overrides(out, [card])


def apply_project_overrides(recipe: dict[str, Any], cards: list[Card]) -> dict[str, Any]:
    """Set each step a project-scope override names to that override's reader, as the step's own choice, so
    the recipe Start reads and the one setup proposes again both read with the reader the person chose
    (`source.try.use-this-scope`). The one code path for Use This and for assembling a project's recipe
    again. A folder override stays an override only: the step's own model is the project's. An override
    whose card Fichero no longer has (a Hugging Face reader no longer kept, a card no longer shipped) still sets
    its step to the model it names: the person chose it, and the rules never take a choice back (#5660 item 8:
    the default came back once the finder stopped listing the chosen reader). Changes `recipe` in place."""
    by_id = {c.id: c for c in cards}
    steps = {s.get("id"): s for s in recipe.get("steps") or []}
    for override in recipe.get("overrides") or []:
        step, card = steps.get(override.get("step")), by_id.get(override.get("card"))
        if override.get("scope") != "project" or step is None:
            continue
        if card is None:
            if not isinstance(override.get("model"), dict) or not override["model"]:
                continue
            card = Card(id=str(override.get("card") or ""), pin=dict(override["model"]), jobs=frozenset({step["job"]}),
                        scripts=None, languages=None, material=frozenset(),
                        runs_on=str(override.get("runs_on") or "this-mac"),
                        note=str(override["model"].get("hf", "")).rsplit("/", 1)[-1] or str(override.get("card") or ""),
                        offered_because="chosen by you")
        for stale in ("gap", "problem"):
            step.pop(stale, None)
        measured = replace(card, cer_measured_here=override.get("cer"))
        step.update(_chosen(Choice(step["job"], measured, reasons=[override.get("because") or "chosen by you"])))
        step["uses_cloud"] = str(step.get("runs_on") or "").startswith("cloud")
        if override.get("granularity"):
            step["granularity"] = override["granularity"]  # how the model is asked, as measured (#5722)
        else:
            step.pop("granularity", None)
    return recipe


# --- the line finders (#5660 item 7) ---------------------------------------------------------------------------
#
# The same bake-off for the step that finds the lines: each line finder the engine has runs on the sample pages,
# and is scored by how many of the lines a person checked it finds. A checked line is found when one of the
# finder's lines covers at least `LINE_COVER` of its box, and is no more than `LINE_TALL` times its height (a box
# round a whole paragraph does not find its lines). Kraken's segmenter (the step's own) and Apple Vision's text
# lines run here; a YOLO layout model finds regions, not lines, and is named as not a line finder.

LINES_STEP = "find-lines"
LINE_KIND = "compare-line-finders"
LINE_COVER = 0.5
LINE_TALL = 2.5

#: The line finders, by the name a person reads: what each is, and the card a choice of it would set.
LINE_FINDERS: tuple[dict[str, Any], ...] = (
    {"finder": "kraken-blla", "name": "Kraken's line finder", "card": "kraken:builtin/blla@bundled",
     "pin": {"kraken": "blla", "kraken_version": "bundled"}},
    {"finder": "apple-vision", "name": "Apple Vision's text lines", "card": "apple:vision/find-lines@os",
     "pin": APPLE_LINES_PIN},
    {"finder": "yolo", "name": "The YOLO layout model", "card": "yolo:hf/hantian/yolo-doclaynet@main",
     "pin": {"yolo": "yolo-doclaynet-11n"}, "not_available": "not available yet: it finds regions, not lines"},
)


def line_finders() -> list[dict[str, Any]]:
    """The candidate line finders (`source.recipe.line-finders-are-a-candidate-list`, #5451): the engine's own, and a
    finder for every other card that names the Find lines job, so adding a card adds a candidate. One with no way to
    run as a line finder yet is listed as not scored, saying so, never run as another."""
    known = {f["card"] for f in LINE_FINDERS}
    more = [{"finder": c.id, "name": reader_name(c), "card": c.id, "pin": c.pin,
             "not_available": "not available yet: no workflow runs it as a line finder"}
            for c in seed_cards() if "find-lines" in c.jobs and c.id not in known]
    return [*LINE_FINDERS, *more]


def _finder_unavailable(finder: dict[str, Any]) -> str | None:
    if finder.get("not_available"):
        return finder["not_available"]
    if finder["finder"] == "apple-vision":
        from fichero_server.training.evaluation import apple_vision_here

        return None if apple_vision_here() else "Apple Vision's text recognition is not available on this Mac"
    if finder["finder"] == "kraken-blla":
        from fichero_server.llm.kraken_runtime import is_installed

        return None if is_installed() else "Kraken is not in this build"
    return None


def find_lines_with(finder: str, photo: str) -> list[list[float]]:
    """The lines a finder finds on a page, each a normalised [x, y, w, h] box. The seam tests replace."""
    if finder == "kraken-blla":
        from fichero_server.llm import kraken_runtime
        from fichero_server.media.ocr_geometry import OCRGeometryLevel

        result = kraken_runtime.segment_to_geometry(photo)
        return [list(b.bbox) for b in result.boxes if b.level == OCRGeometryLevel.LINE]
    if finder == "apple-vision":
        from fichero_server.workflows.tools.vision_base import apple_vision_ocr_with_geometry

        return [list(b.bbox) for b in apple_vision_ocr_with_geometry(photo).line_boxes]
    raise ValueError(f"no line finder {finder!r}")


def _checked_boxes(page: dict[str, Any]) -> list[list[float]]:
    """The checked lines' boxes, normalised to the photograph (their outlines are in its pixels)."""
    from PIL import Image

    with Image.open(page["photo"]) as image:
        width, height = image.size
    boxes = []
    for line in page["lines"]:
        points = line.get("polygon") or line.get("baseline") or []
        if not points or not width or not height:
            continue
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        boxes.append([min(xs) / width, min(ys) / height, (max(xs) - min(xs)) / width, (max(ys) - min(ys)) / height])
    return boxes


def _covers(found: list[float], checked: list[float]) -> bool:
    fx, fy, fw, fh = found
    cx, cy, cw, ch = checked
    across = max(0.0, min(fx + fw, cx + cw) - max(fx, cx))
    down = max(0.0, min(fy + fh, cy + ch) - max(fy, cy))
    area = cw * ch
    return area > 0 and across * down / area >= LINE_COVER and fh <= LINE_TALL * max(ch, 1e-9)


def score_lines(found: list[list[float]], checked: list[list[float]]) -> dict[str, int]:
    """How many checked lines the finder found, of how many, and how many of its lines match none."""
    hit = sum(1 for c in checked if any(_covers(f, c) for f in found))
    extra = sum(1 for f in found if not any(_covers(f, c) for c in checked))
    return {"found": hit, "checked": len(checked), "extra": extra}


def start_lines(db: Any, library: Path, *, page_ids: list[str] | None, now: str, started_by: str) -> dict[str, Any]:
    """Compare the line finders on the sample pages: the same readiness as the readers' bake-off, one
    `compare-line-finders` job in Activity, one record. Refused in words when no finder can run here."""
    import uuid

    from fichero_server.execution import jobs

    pages, left_out = ground_truth(db, page_ids)
    ready = readiness(pages, unmarked_import_pages(db))
    if not ready["ready"]:
        raise BakeoffRefused(ready["sentence"])
    finders = [{**f, "not_scored": _finder_unavailable(f)} for f in line_finders()]
    if not any(f["not_scored"] is None for f in finders):
        why = " ".join(f"{f['name']}: {f['not_scored']}." for f in finders)
        raise BakeoffRefused(f"No line finder can be compared on this Mac yet. {why}")
    register_job_kinds()
    record_id = uuid.uuid4().hex
    job_id = jobs.enqueue(db, LINE_KIND, record_id, started_by=started_by, watched=True)
    record = {"id": record_id, "job_id": job_id, "step": LINES_STEP, "started_at": now, "material": "",
              "volume": 0, "pages": pages, "left_out": left_out, "lines": sum(p["lines"] for p in pages),
              "candidates": [{k: f.get(k) for k in ("finder", "name", "card", "pin", "not_scored")} for f in finders]}
    write_record(library, record)
    return record


def _run_lines(db: Any, record_id: str) -> dict[str, Any]:
    """The job's work: each finder on each sample page, scored, kept on the job's row as it goes."""
    import json
    import time

    from fichero_server.execution import jobs
    from fichero_server.training.evaluation import reference_page

    job_id = jobs.current_job_id()
    record = read_record(Path(db.path).parent, record_id)
    out: dict[str, Any] = {}
    for finder in record["candidates"]:
        if finder["not_scored"] is not None:
            continue
        per_page, began = [], time.monotonic()
        for p in record["pages"]:
            page, _why = reference_page(db, p["document_id"], None)
            if page is None:
                continue
            if job_id:
                jobs.save_detail(db, job_id, json.dumps({"finders": out}),
                                 reason=f"Finding lines on {page['name']} with {finder['name']}")
            try:
                found, why = find_lines_with(finder["finder"], page["photo"]), None
            except Exception as exc:  # noqa: BLE001 -- the page says why it was not scored
                found, why = [], f"failed: {exc}"
            per_page.append({"document_id": p["document_id"], "name": page["name"], "why": why,
                             **score_lines(found, _checked_boxes(page))})
        out[finder["finder"]] = {"per_page": per_page, "seconds": round(time.monotonic() - began, 2)}
        if job_id:
            jobs.save_detail(db, job_id, json.dumps({"finders": out}))
    return {"finders": out}


def register_job_kinds() -> None:
    from fichero_server.execution import jobs

    if LINE_KIND not in jobs.KINDS or jobs.KINDS[LINE_KIND].run is None:
        jobs.register_kind(LINE_KIND, _run_lines, model=None, lane="local-ml", name="Compare the line finders")


def lines_result(db: Any, record: dict[str, Any]) -> dict[str, Any]:
    """The line finders' table: by the share of checked lines each found, then fewer extra lines, then faster."""
    import json

    from fichero_server.execution import jobs

    job = jobs.read_job(db, record["job_id"])
    state = job["state"] if job else "cleared"
    try:
        done = (json.loads(job["detail"] or "{}") if job else {}).get("finders") or {}
    except ValueError:
        done = {}
    rows = []
    for f in record["candidates"]:
        row = {"card": f["card"], "name": f["name"], "pin": f["pin"], "role": "contender", "rule_rank": None,
               "reader": None, "model": f["finder"], "runs_on": "this-mac", "local": True,
               "cost_usd": _figure(0.0, "measured", "runs on this Mac"), "carbon_g_per_page": None,
               "trainable": False, "size_gb": 0.0, "cer": None, "policy": None, "scores": {}, "per_page": [],
               "measured": False, "pages_read": None, "pages_total": len(record["pages"]), "pages_per_hour": None,
               "seconds": None, "wer": None, "lines_found": None, "lines_checked": None, "extra_lines": None,
               "why": f["not_scored"]}
        kept = done.get(f["finder"])
        if f["not_scored"] is None and kept:
            pages = [p for p in kept["per_page"] if p["why"] is None]
            row.update(lines_found=sum(p["found"] for p in pages), lines_checked=sum(p["checked"] for p in pages),
                       extra_lines=sum(p["extra"] for p in pages), pages_read=len(pages), seconds=kept["seconds"],
                       measured=bool(pages), why=None if pages else "it could not find lines on any of the pages")
        elif f["not_scored"] is None:
            row["why"] = ("waiting for the comparison job" if state in ("waiting", "running")
                          else f"the comparison job ended ({state}) without scoring it")
        rows.append(row)

    def key(r: dict[str, Any]) -> tuple:
        share = r["lines_found"] / r["lines_checked"] if r["measured"] and r["lines_checked"] else -1.0
        return (-share, r["extra_lines"] if r["extra_lines"] is not None else math.inf, r["seconds"] or math.inf,
                r["card"])

    ranked = sorted(rows, key=key)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    measured = [r for r in ranked if r["measured"]]
    # Still scoring while a finder that can run has no result yet (the table is read from what the job kept).
    waiting = any(f["not_scored"] is None and f["finder"] not in done for f in record["candidates"]) \
        and state in ("waiting", "running")
    no_winner = None
    if not waiting and len(measured) < 2:
        no_winner = ("no line finder found lines on these pages" if not measured
                     else f"only {measured[0]['name']} could be compared")
    winner = measured[0]["card"] if not waiting and no_winner is None else None
    return {**{k: record[k] for k in ("id", "job_id", "step", "started_at", "pages", "left_out", "lines")},
            "state": state, "reason": job["reason"] if job else None, "rows": ranked, "winner": winner,
            "no_winner_why": no_winner}
