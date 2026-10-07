"""The evaluation job: trained against out-of-the-box readers on the held-out checked pages (#5441, `distill.eval.*`).

A trained model is only worth keeping if it beats what can be downloaded. This one job reads a
project's held-out pages with each candidate and scores each against the checked reading of the page:

* **The pages.** Held-out pages are named by the training request and recorded on the trained model's
  card (`held_out`, from the training set's manifest: `training.kraken_set`). With no pages named, the
  evaluation scores on the pages EVERY trained candidate's card says were held out; pages named by the
  caller must be held out of every trained candidate, or the run is refused: a page a candidate trained
  on would make its score meaningless. A trained model whose card holds no held-out page is refused in
  words. Out-of-the-box models trained on none of the project's pages.
* **The reference.** On each page, the newest live pass whose model or name is `checked` (the checked
  pass); with no `checked` named, the newest live pass a person made or marked ground truth (the bake-off's
  ground truth, #5513), else the lines a person corrected inside another pass (#5499). Its lines, empty and `null` readings left out (`kraken_set.line_flag`), are the right readings;
  each page records who checked it (`person` when a person wrote the pass, else `model`,
  `distill.scale.check-trust-levels`).
* **The reading.** Each candidate reads the checked pass's own lines: a Kraken reader on each line's
  baseline and outline (`kraken_runtime.read_given_lines`), a vision model on each line's picture, one
  line a call, with the line reader's prompt. Only this Mac's models: the job is on the local model
  lane. A remote model target is not built yet and is refused.
* **The score.** The ONE CER (`workflows.transcription_accuracy.character_error_rate`) of the page's
  readings (lines joined by newlines) against the checked text, under every named normalisation policy
  (`POLICIES`: diplomatic, layout-insensitive, lenient, accent-blind); per model, total edits over total
  reference characters across the pages read. Every figure names its policy and carries the definition.
* **Read or not read** (#5531). A page a reader returned nothing for, or far too little (fewer characters
  than `READ_SHARE` of the reference's), is recorded as not read, with why (the error it raised, what the
  reader said, else "returned no text"), and never scored as 100% CER: an empty reader once "won" a
  Hebrew bake-off at 100% against two readers that had read something. A candidate is measured only when
  it read at least `MEASURED_SHARE` of the pages; its CER is over the pages it read, shown with that
  count. A best (the bake-off's winner) is named only when at least two candidates were measured.
* **The speed.** The seconds each candidate spent reading, and so its pages an hour on this Mac, measured
  in the run (`source.try.bakeoff-is-the-same-tool`: speed is measured where the model has run).
* **Where it lands.** On each model's card, appended to `evaluations` and never overwriting one: a
  Kraken reader's install record (the marker that carries a trained reader's card), a trained vision
  model's `fichero-card.json`, and for a downloaded vision model with no card yet, a card of its own in
  the MLX store's `cards` folder. `GET /api/evaluation/scores` reads them back for the model's node.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fichero_server.execution import jobs
from fichero_server.execution.throttle import MemoryShortError
from fichero_server.models.compute_requests import EvaluationCandidate, EvaluationRunRequest

KIND = "evaluate-models"
#: Providers that run on this Mac. Anything else is a remote target, not built yet.
LOCAL_PROVIDERS = ("omlx",)
CARDS_DIR = "cards"
#: A page counts as read only when the reader's text has at least this share of the reference's characters
#: (under the default policy). A reader that reads badly still writes about as much as the page holds (a
#: 58%-CER reader wrote whole pages); one that wrote a tenth of it did not read the page, and a CER of
#: ~100% on it would measure the failure, not the reading (Czech: 26-29 characters over 8 pages).
READ_SHARE = 0.10
#: A candidate is measured only when it read at least this share of the pages: a CER over the few pages it
#: happened to read is a score on a different, self-chosen sample, not comparable with the others'.
MEASURED_SHARE = 0.80
#: What a page not read says when the reader gave no reason of its own.
NO_TEXT = "returned no text"


class EvaluationRefused(ValueError):
    """The evaluation cannot give a fair score; the message says why, in words."""


# --- the model's card -------------------------------------------------------------------------------


def card_path(model: str, reader: str) -> Path:
    """Where a model's card lives: the one place its evaluations are kept."""
    if reader == "kraken":
        from fichero_server.llm.kraken_runtime import _marker_path

        return _marker_path(model)
    from fichero_server.llm.mlx_model_store import TRAINED_CARD, TRAINED_ORG, get_mlx_model_store

    store = get_mlx_model_store()
    if model.startswith(f"{TRAINED_ORG}/"):
        return store.trained_dir(model) / TRAINED_CARD
    return store.root / CARDS_DIR / (re.sub(r"[^A-Za-z0-9._-]+", "--", model) + ".json")


def _read_card(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    card = json.loads(path.read_text(encoding="utf-8"))  # a card that does not parse is never overwritten
    if not isinstance(card, dict):
        raise ValueError(f"the card {path.name} is not a record")
    return card


def model_evaluations(model: str, reader: str) -> list[dict[str, Any]]:
    """Every evaluation written on the model's card, oldest first."""
    try:
        return list(_read_card(card_path(model, reader)).get("evaluations") or [])
    except ValueError:
        return []


def measured_here(db: Any, model: str, reader: str) -> float | None:
    """The reader's CER on THIS project (#5558, the counting rule's measured score): the newest evaluation
    on its card whose pages are this project's documents and which measured it (`judged`, the bake-off's
    own rule), under the default policy. None when it was never measured here: a score is never invented."""
    from fichero_server.models import Document
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    for entry in reversed(model_evaluations(model, reader)):
        pages = [p for p in entry.get("pages") or [] if isinstance(p, str)]
        if not pages or not db.query_in(Document, "id", pages):
            continue
        j = judged(entry.get("per_page") or [], len(pages))
        if j["measured"]:
            return j["scores"][DEFAULT_POLICY_NAME]["cer"]
    return None


def record_on_card(model: str, reader: str, entry: dict[str, Any]) -> None:
    """Append one evaluation to the model's card; earlier ones are kept."""
    path = card_path(model, reader)
    card = _read_card(path)
    card.setdefault("evaluations", []).append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, indent=1), encoding="utf-8")


def trained_card(candidate: EvaluationCandidate) -> dict[str, Any] | None:
    """The training card of a model Fichero trained, or None for an out-of-the-box one."""
    if candidate.reader == "kraken":
        from fichero_server.llm.kraken_runtime import trained_reader_card

        return trained_reader_card(candidate.model)
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    return get_mlx_model_store().trained_card(candidate.model)


def on_this_mac(model: str, reader: str) -> bool:
    if reader == "kraken":
        from fichero_server.llm.kraken_runtime import is_recognition_model_installed

        return is_recognition_model_installed(model)
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    store = get_mlx_model_store()
    try:
        return store.trained_card(model) is not None or store.is_complete(store.spec(model))
    except KeyError:
        return False


# --- the candidates and the pages --------------------------------------------------------------------


def out_of_the_box(candidates: list[EvaluationCandidate]) -> tuple[list[EvaluationCandidate], list[dict[str, str]]]:
    """The registry's out-of-the-box readers for each kind asked, those on this Mac and those not.

    Kraken: a trained reader's base, then the Kraken catalogue. Vision: the vision bases' MLX builds
    (`training.vision_bases`). Default taken 2026-10-05: the registry's readers of the same kind, on this
    Mac only; nothing is downloaded for an evaluation."""
    from fichero_server.llm.kraken_runtime import KRAKEN_RECOGNITION_MODELS
    from fichero_server.training.vision_bases import VISION_BASES

    named = {(c.model, c.reader) for c in candidates}
    offered: list[tuple[str, str]] = []
    kinds = {c.reader for c in candidates}
    if "kraken" in kinds:
        offered += [(str(base), "kraken") for c in candidates if c.reader == "kraken"
                    if (base := (trained_card(c) or {}).get("base"))]
        offered += [(m, "kraken") for m in KRAKEN_RECOGNITION_MODELS]
    if "vision" in kinds:
        offered += [(b.mlx, "vision") for b in VISION_BASES.values() if b.mlx]
    here: list[EvaluationCandidate] = []
    absent: list[dict[str, str]] = []
    for model, reader in dict.fromkeys(offered):
        if (model, reader) in named:
            continue
        if on_this_mac(model, reader):
            here.append(EvaluationCandidate(model=model, reader=reader))
        else:
            absent.append({"model": model, "reader": reader, "why": "not on this Mac: download it to score it"})
    return here, absent


def held_out_pages(request: EvaluationRunRequest, candidates: list[EvaluationCandidate]) -> list[str]:
    """The pages every candidate can be scored on fairly: none of them trained on any."""
    trained: dict[str, list[str]] = {}
    for c in candidates:
        card = trained_card(c)
        if card is None:
            continue
        held = [str(h["document_id"]) for h in card.get("held_out") or [] if h.get("document_id")]
        if not held:
            raise EvaluationRefused(
                f"{c.model} has no held-out pages: it was trained with none kept back, so every checked page "
                "may have taught it and none can score it fairly. Train it again with pages held out.")
        trained[c.model] = held
    if request.held_out_ids:
        for model, held in trained.items():
            taught = [p for p in request.held_out_ids if p not in held]
            if taught:
                raise EvaluationRefused(
                    f"{len(taught)} of the pages named are not held out from {model} (its card does not list "
                    f"them), so it may have trained on them: {', '.join(taught[:5])}")
        return list(dict.fromkeys(request.held_out_ids))
    if not trained:
        raise EvaluationRefused("name the held-out checked pages: no candidate is a trained model whose card names "
                                "the pages held out of its training")
    first, *rest = trained.values()
    pages = [p for p in first if all(p in other for other in rest)]
    if not pages:
        raise EvaluationRefused("the trained candidates share no held-out page: no page is fair to all of them")
    return pages


def by_whom(checked: str | None) -> str:
    """The reference named in words: the checked pass's model or name, or a person."""
    return f"checked by {checked}" if checked is not None else "made by a person"


def person_read_lines(db: Any, page_id: str, kind: str = "transcription") -> dict[str, set[str]]:
    """The segments of a page whose COUNTING reading a person made, by pass (#5499): a person's corrections
    inside a model's pass. Worked out by the one counting rule (`counting_by_kind`), so a correction a
    person withdrew, or one a later machine reading does not outrank, is counted exactly as the page reads."""
    from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment

    by_pass: dict[str, set[str]] = {}
    corrected = {r.segment_id for r in db.query(ContentRepresentation, document_id=page_id, provenance_kind="human")
                 if r.segment_id and r.kind == kind}
    for segment_id in sorted(corrected):
        row = db.get(Segment, segment_id)
        if row is None or row.deleted_at is not None:
            continue
        counted = counting_by_kind(db, segment_id, readings_of_segment(db, segment_id)).get(kind)
        if counted is not None and counted.representation_id and not counted.labelled_machine:
            by_pass.setdefault(row.pass_id, set()).add(segment_id)
    return by_pass


def checked_pass(db: Any, page_id: str, checked: str | None) -> Any | None:
    """The newest live pass on the page whose model or name is `checked`. With None, the newest a person
    made or marked ground truth (`made_by_a_person`, #5513); with none such, the newest holding lines a
    person corrected (#5499), whose corrected lines alone are the reference (`reference_page`)."""
    from fichero_server.models.segments import SegmentPass, made_by_a_person

    live = [p for p in db.query(SegmentPass, document_id=page_id) if not p.deleted_at]
    if checked is not None:
        passes = [p for p in live if checked in (p.model, p.name)]
    else:
        passes = [p for p in live if made_by_a_person(p)]
        if not passes:
            corrected = person_read_lines(db, page_id)
            passes = [p for p in live if p.id in corrected]
    return max(passes, key=lambda p: p.created_at) if passes else None


def trust_of(chosen: Any) -> str:
    """Who checked the reference: `person` when a person wrote the pass or marked it ground truth,
    `model` when a model did."""
    from fichero_server.models.segments import made_by_a_person

    if made_by_a_person(chosen):
        return "person"
    return "model" if chosen.model else "not recorded"


def reference_page(db: Any, page_id: str, checked: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """(the page's checked lines, photograph and trust; or None with why)."""
    from fichero_server.checking.line_check import page_lines
    from fichero_server.models import Document
    from fichero_server.page_export import ExportRefused, export_page
    from fichero_server.training.kraken_set import line_flag

    doc = db.get(Document, page_id)
    if doc is None:
        return None, "no such page"
    chosen = checked_pass(db, page_id, checked)
    if chosen is None:
        return None, f"no pass {by_whom(checked)}"
    if not doc.path or not Path(doc.path).is_file():
        return None, "its photograph is not on this Mac"
    try:
        xml = export_page(db, page_id, "pagexml", pass_id=chosen.id).data.decode("utf-8")
    except ExportRefused as exc:
        return None, str(exc)
    lines = [ln for ln in page_lines(xml) if line_flag(ln["text"], False) is None]
    trust = trust_of(chosen)
    if checked is None and trust != "person":
        # A model's pass with a person's corrections in it (#5499): only the lines a person corrected are
        # right readings; the rest are the model's, and scoring against them would score the model.
        from fichero_server.formats.harness import xml_id

        corrected = {xml_id(sid) for sid in person_read_lines(db, page_id).get(chosen.id, set())}
        lines, trust = [ln for ln in lines if ln["id"] in corrected], "person"
    if not lines:
        return None, f"the pass {by_whom(checked)} has no read lines"
    return {"document_id": page_id, "name": doc.name, "photo": doc.path, "pass_id": chosen.id,
            "trust": trust, "lines": lines}, None


# --- reading and scoring -----------------------------------------------------------------------------


def read_with_kraken(photo: str, model: str, lines: list[dict[str, Any]]) -> tuple[list[str], str | None]:
    """(the lines' readings, why Kraken read nothing when that is known). Kraken reads a line on its own
    baseline and outline; a page whose lines carry neither (some imported transcriptions) reads as nothing."""
    from fichero_server.llm import kraken_runtime

    model_path, _catalog = kraken_runtime.resolve_recognition_model(model)
    reads = kraken_runtime.read_given_lines(photo, model_path, lines)
    if not kraken_runtime._usable(lines):
        return reads, "its lines carry no baseline and outline for Kraken to read on"
    return reads, None


async def ask_vision(candidate: EvaluationCandidate, image: str, prompt: str) -> str:
    """One line picture to a vision model on this Mac. The seam tests replace."""
    from fichero_server.llm import LLMConfig, vision

    return await vision(images=[image], prompt=prompt,
                        config=LLMConfig(provider=candidate.provider, model=candidate.model))


def read_with_vision(photo: str, candidate: EvaluationCandidate, lines: list[dict[str, Any]],
                     language: str | None) -> tuple[list[str], str | None]:
    """(the lines' readings, why the model gave nothing when it answered nothing or nothing readable)."""
    from PIL import Image

    from fichero_server.llm.line_reader import _crop_data_uri, parse_answer, prompt_for

    prompt = prompt_for(1, language)
    with Image.open(photo) as page:
        crops = [_crop_data_uri(page, ln["polygon"]) for ln in lines]

    answers: list[str] = []

    async def all_lines() -> list[str]:
        out = []
        for crop in crops:  # one line a call, one at a time: the local lane holds one model
            raw = await ask_vision(candidate, crop, prompt)
            answers.append(raw or "")
            parsed = parse_answer(raw, 1)
            out.append((parsed[0] if parsed else None) or "")
        return out

    reads = asyncio.run(all_lines())
    if answers and not any(a.strip() for a in answers):
        return reads, "the model gave an empty answer for every line"
    if answers and all(parse_answer(a, 1) is None for a in answers):
        return reads, "the model's answers were not the readings it was asked for"
    return reads, None


def score_page(reference: list[str], reads: list[str]) -> dict[str, dict[str, Any]]:
    """The page's CER under every named policy, by the one CER function."""
    from fichero_server.workflows.run_comparison import RunComparisonError
    from fichero_server.workflows.transcription_accuracy import POLICIES, character_error_rate

    ref, hyp = "\n".join(reference), "\n".join(reads)
    scores: dict[str, dict[str, Any]] = {}
    for name in POLICIES:
        try:
            s = character_error_rate(ref, hyp, policy=name)
        except RunComparisonError as exc:
            scores[name] = {"cer": None, "why": str(exc)}
            continue
        scores[name] = {"cer": s.cer, "distance": s.distance, "reference_chars": s.reference_chars,
                        "hypothesis_chars": s.hypothesis_chars}
    return scores


def judge_page(page: dict[str, Any], why: str | None = None) -> dict[str, Any]:
    """The page as read, or not read with why (#5531): the one judgement for a page just read and for one an
    older evaluation kept without it (judged from the characters its scores recorded). `why` is the reader's
    own reason (an error it raised, what it said); a page it read anyway is read. A page not read keeps no
    CER: its scores say why instead, so nothing sums it as 100%."""
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    if "read" in page:
        return page
    s = page["scores"].get(DEFAULT_POLICY_NAME) or {}
    ref, hyp = s.get("reference_chars"), s.get("hypothesis_chars")
    if ref is None or hyp is None:  # the reference itself could not be scored: not the reader's failure
        return {**page, "read": True, "why": None}
    if hyp >= READ_SHARE * ref:
        return {**page, "read": True, "why": None, "reference_chars": ref, "hypothesis_chars": hyp}
    why = why or (NO_TEXT if hyp == 0 else f"returned {hyp} characters against {ref} in the reference")
    return {**page, "read": False, "why": why, "reference_chars": ref, "hypothesis_chars": hyp,
            "scores": {name: {"cer": None, "why": f"not read: {why}"} for name in page["scores"]}}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def measured(per_page: list[dict[str, Any]], pages: int) -> dict[str, Any]:
    """Whether the candidate read enough of the `pages` to be measured (`MEASURED_SHARE`), the pages it read,
    and, when not, why in words: "not measured: read 2 of 8 pages (returned no text on 6 pages)"."""
    from collections import Counter

    kept = [judge_page(p) for p in per_page]
    read = sum(bool(p["read"]) for p in kept)
    if pages and read >= MEASURED_SHARE * pages:
        return {"measured": True, "pages_read": read, "pages_total": pages, "why": None}
    reasons = Counter(p["why"] for p in kept if not p["read"])
    because = "; ".join(f"{why} on {_plural(n, 'page')}" for why, n in reasons.most_common(2))
    return {"measured": False, "pages_read": read, "pages_total": pages,
            "why": f"not measured: read {read} of {_plural(pages, 'page')}" + (f" ({because})" if because else "")}


def no_winner_why(measured_names: list[str]) -> str | None:
    """Why no best is named, in words, or None when there is one: a best needs at least two measured."""
    if len(measured_names) >= 2:
        return None
    if measured_names:
        return f"No winner: only one reader could be compared ({measured_names[0]})."
    return "No winner: no reader read these pages."


def judged(per_page: list[dict[str, Any]], pages: int) -> dict[str, Any]:
    """A candidate's pages judged read or not, its scores over the pages it read, and whether it was
    measured: the one reading of a candidate's pages, live and for an evaluation kept before #5531."""
    kept = [judge_page(p) for p in per_page]
    return {"per_page": kept, "scores": totals(kept), **measured(kept, pages)}


def totals(per_page: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per policy: total edits over total reference characters across the pages scored (a page not read
    carries no CER, so it is never summed)."""
    from fichero_server.workflows.transcription_accuracy import POLICIES

    out = {}
    for name in POLICIES:
        scored = [p["scores"][name] for p in per_page if p["scores"][name].get("cer") is not None]
        distance = sum(s["distance"] for s in scored)
        chars = sum(s["reference_chars"] for s in scored)
        out[name] = {"cer": distance / chars if chars else None, "distance": distance, "reference_chars": chars,
                     "pages": len(scored)}
    return out


def speed(seconds: float, pages: int) -> dict[str, Any]:
    """The reading time measured in this run, and the pages an hour it gives on this Mac."""
    return {"seconds": round(seconds, 3), "pages": pages,
            "pages_per_hour": round(pages * 3600 / seconds, 1) if seconds > 0 and pages else None,
            "basis": "measured on this Mac"}


# --- the job -------------------------------------------------------------------------------------------


def plan(db: Any, request: EvaluationRunRequest) -> dict[str, Any]:
    """The candidates, the pages and what was left out, or refused in words. Nothing is read yet."""
    for c in request.candidates:
        if c.reader == "vision" and c.provider not in LOCAL_PROVIDERS:
            raise EvaluationRefused(f"{c.model} on {c.provider}: only this Mac's models can be evaluated so far "
                                    f"({', '.join(LOCAL_PROVIDERS)}); a remote model target is not built yet")
        if not on_this_mac(c.model, c.reader):
            raise EvaluationRefused(f"{c.model} is not on this Mac: download it (or land its training) first")
    candidates = list(request.candidates)
    absent: list[dict[str, str]] = []
    if request.add_out_of_the_box:
        extra, absent = out_of_the_box(candidates)
        candidates += extra
    pages, missing = [], []
    for page_id in held_out_pages(request, candidates):
        page, why = reference_page(db, page_id, request.checked)
        if page is None:
            missing.append({"document_id": page_id, "why": why})
        else:
            pages.append(page_id)
    if not pages:
        raise EvaluationRefused(f"none of the {len(missing)} held-out pages has a reading "
                                f"{by_whom(request.checked)} to score against")
    return {"candidates": [c.model_dump() for c in candidates], "pages": pages, "missing": missing,
            "not_on_this_mac": absent}


def start(db: Any, request: EvaluationRunRequest, *, started_by: str,
          check_pages: Callable[[list[str]], None] | None = None) -> dict[str, str]:
    """`check_pages` sees the planned pages before anything is queued, and refuses by raising."""
    planned = plan(db, request)
    if check_pages is not None:
        check_pages(planned["pages"])
    job_id = jobs.enqueue(db, KIND, f"evaluate:{uuid.uuid4()}", started_by=started_by, watched=True,
                          detail=json.dumps({"request": request.model_dump(), "plan": planned}))
    return {"job_id": job_id}


def _cancelled(db: Any, job_id: str) -> bool:
    return bool(json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}").get("cancel"))


def _measured_so_far(db: Any, job_id: str) -> dict[str, Any]:
    """The pages each candidate has already been scored on in this job, by `model|reader`."""
    return json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}").get("measured_so_far") or {}


def _keep_measured(db: Any, job_id: str, key: str, per_page: list[dict[str, Any]], seconds: float) -> None:
    """Keep a candidate's scored pages on the job as they are measured (#5524): a job that stops for
    memory goes back to waiting and, run again, carries on from here instead of reading them again
    (a Syriac bake-off that stopped after 6 of 12 pages kept nothing)."""
    detail = json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}")
    detail.setdefault("measured_so_far", {})[key] = {"per_page": per_page, "seconds": seconds}
    jobs.save_detail(db, job_id, json.dumps(detail))


def evaluate(db: Any, job_id: str, request: EvaluationRunRequest, planned: dict[str, Any],
             *, progress: Any = None) -> dict[str, Any]:
    from fichero_server.workflows.transcription_accuracy import CER_DEFINITION, DEFAULT_POLICY_NAME

    candidates = [EvaluationCandidate(**c) for c in planned["candidates"]]
    pages = [p for p in (reference_page(db, pid, request.checked)[0] for pid in planned["pages"]) if p]
    trust = {t: sum(p["trust"] == t for p in pages) for t in sorted({p["trust"] for p in pages})}
    models = []
    so_far = _measured_so_far(db, job_id)
    for i, c in enumerate(candidates, 1):
        key = f"{c.model}|{c.reader}"
        per_page = list((so_far.get(key) or {}).get("per_page") or [])
        seconds = float((so_far.get(key) or {}).get("seconds") or 0.0)
        done = {p["document_id"] for p in per_page}
        for page in pages:
            if page["document_id"] in done:
                continue
            if _cancelled(db, job_id):
                return {"stopped": True, "models": models}
            if progress:
                progress(f"Reading {page['name']} with {c.model} (model {i} of {len(candidates)})")
            reference = [ln["text"] for ln in page["lines"]]
            began = time.monotonic()
            try:
                reads, why = (read_with_kraken(page["photo"], c.model, page["lines"]) if c.reader == "kraken"
                              else read_with_vision(page["photo"], c, page["lines"], request.language))
            except MemoryShortError:
                raise  # not the reader's failure: the job waits for memory and carries on (#5524)
            except Exception as exc:  # recorded on the page as why it was not read (#5531), never 100% CER
                reads, why = [], f"failed: {exc}"
            seconds += time.monotonic() - began
            per_page.append(judge_page({"document_id": page["document_id"], "name": page["name"],
                                        "trust": page["trust"], "lines": len(reference),
                                        "scores": score_page(reference, reads)}, why))
            _keep_measured(db, job_id, key, per_page, seconds)
        models.append({"model": c.model, "reader": c.reader,
                       "role": "trained" if trained_card(c) is not None else "out of the box",
                       **judged(per_page, len(pages)), "speed": speed(seconds, len(pages))})
    measured_at = datetime.now(timezone.utc).isoformat()
    for m in models:
        record_on_card(m["model"], m["reader"], {
            "job_id": job_id, "measured_at": measured_at, "checked": request.checked, "trust": trust,
            "definition": CER_DEFINITION, "pages": [p["document_id"] for p in pages], "role": m["role"],
            "scores": m["scores"], "per_page": m["per_page"], "speed": m["speed"], "measured": m["measured"],
            "pages_read": m["pages_read"], "pages_total": m["pages_total"], "why": m["why"],
            "compared_with": [o["model"] for o in models if o is not m]})
    ranked = sorted((m for m in models if m["measured"] and m["scores"][DEFAULT_POLICY_NAME]["cer"] is not None),
                    key=lambda m: m["scores"][DEFAULT_POLICY_NAME]["cer"])
    no_best = no_winner_why([m["model"] for m in ranked])
    return {"stopped": False, "measured_at": measured_at, "definition": CER_DEFINITION, "trust": trust,
            "ranked_by": DEFAULT_POLICY_NAME, "best": None if no_best else ranked[0]["model"],
            "no_best_why": no_best, "models": models}


def words(result: dict[str, Any], pages: int) -> str:
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    best = next((m for m in result["models"] if m["model"] == result.get("best")), None)
    said = f"Scored {len(result['models'])} models on {pages} held-out pages"
    if best:
        said += f"; best {best['model']} (CER {best['scores'][DEFAULT_POLICY_NAME]['cer']:.3f}, {DEFAULT_POLICY_NAME})"
    elif result.get("no_best_why"):
        said += f". {result['no_best_why']}"
    return said


def run(db: Any, subject: str) -> dict[str, Any]:
    job_id = jobs.job_id_for(db, KIND, subject)
    detail = json.loads(jobs.read_job(db, job_id)["detail"] or "{}")
    request = EvaluationRunRequest(**detail["request"])
    planned = detail["plan"]
    jobs.save_detail(db, job_id, json.dumps(detail), reason="Reading the held-out pages with each model")
    # The reason only: the detail is read back as stored, so a stop asked for meanwhile is kept.
    result = evaluate(db, job_id, request, planned,
                      progress=lambda said: jobs.save_detail(db, job_id, jobs.read_job(db, job_id)["detail"], reason=said))
    detail = json.loads(jobs.read_job(db, job_id)["detail"] or "{}")
    detail["result"] = result
    if result["stopped"]:
        jobs.save_detail(db, job_id, json.dumps(detail), reason="Stopped by you; nothing written on the cards")
        raise jobs.JobCancelled("Stopped by you; nothing written on the cards")
    jobs.save_detail(db, job_id, json.dumps(detail), reason=words(result, len(planned["pages"])))
    return result


def status(db: Any, job_id: str) -> dict[str, Any]:
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != KIND:
        raise LookupError(f"no evaluation {job_id}")
    detail = json.loads(row["detail"] or "{}")
    return {"job_id": job_id, "state": row["state"], "reason": row["reason"], "request": detail.get("request"),
            "plan": detail.get("plan"), "result": detail.get("result")}


def request_cancel(db: Any, job_id: str) -> str:
    row = jobs.read_job(db, job_id)
    if row is None or row["kind"] != KIND:
        raise LookupError(f"no evaluation {job_id}")
    if row["state"] == "waiting":
        jobs.cancel_waiting(db, job_id)
        return "cancelled"
    if row["state"] == "running":
        detail = json.loads(row["detail"] or "{}")
        detail["cancel"] = True
        jobs.save_detail(db, job_id, json.dumps(detail))
    return row["state"]


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None,
                           name="Evaluate models on held-out pages", cancel=request_cancel)
