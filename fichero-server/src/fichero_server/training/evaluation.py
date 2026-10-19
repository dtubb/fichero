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
#: Readers on this Mac: its MLX models, and Apple Vision's on-device recognition (#5660 item 7).
LOCAL_PROVIDERS = ("omlx", "apple")
#: Apple Vision as the evaluation names it: `vision` reader, provider `apple`, this model.
APPLE_VISION = "apple-vision"
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


def apple_vision_here() -> bool:
    """Whether this Mac's Vision framework recognises text (the locales it offers; none off macOS)."""
    try:
        from fichero_server.workflows.tools.vision_base import _supported_vision_locales, supported_locales_are_known

        if not supported_locales_are_known():
            import asyncio

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass  # a worker thread: loading the bundle here holds only this thread
            else:
                return False  # the event loop must not load PyObjC's Vision (#5843); the startup warm-up answers soon
        return bool(_supported_vision_locales())
    except Exception:  # noqa: BLE001 -- no Vision framework here: not available, said by the caller
        return False


def on_this_mac(model: str, reader: str, provider: str = "omlx") -> bool:
    if reader == "vision" and provider == "apple":
        return model == APPLE_VISION and apple_vision_here()
    if reader == "vision" and provider not in LOCAL_PROVIDERS:
        return True  # a cloud provider: nothing to download; whether pages may leave is the request's
    if reader == "kraken":
        from fichero_server.llm.kraken_runtime import is_recognition_model_installed

        return is_recognition_model_installed(model)
    from fichero_server.llm.mlx_model_store import get_mlx_model_store

    store = get_mlx_model_store()
    # By the store's own id for any name it knows: a catalogue id, its Hub repository (a recipe's pin and
    # the vision bases name the repository), a trained model, or a model found in the store (#5519).
    model_id = store.canonical_id(model)
    if model_id is None:
        return False
    return store.trained_card(model_id) is not None or store.is_complete(store.spec(model_id))


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
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    # The page's image as every step finds it: a copied page's stored path is inside the package
    # (`source.pages.image-found-wherever-kept`, #5668).
    photo = _resolve_abs_path(doc, str(Path(db.path).parent))
    if not photo or not Path(photo).is_file():
        return None, "its photograph is not on this Mac"
    try:
        xml = export_page(db, page_id, "pagexml", pass_id=chosen.id, reading_level="as_written").data.decode("utf-8")
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
    return {"document_id": page_id, "name": doc.name, "photo": photo, "pass_id": chosen.id,
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


async def ask_vision(candidate: EvaluationCandidate, images: list[str], prompt: str) -> str:
    """One request to a vision model: the pictures of the lines it is asked about. The seam tests replace."""
    from fichero_server.llm import LLMConfig, vision

    return await vision(images=images, prompt=prompt,
                        config=LLMConfig(provider=candidate.provider, model=candidate.model))


def requests_for(lines: list[dict[str, Any]], granularity: str, lines_per_request: int | None = None
                 ) -> list[list[dict[str, Any]]]:
    """The requests a page's lines are asked in (#5722): one line each, one region each (consecutive lines of the
    same `region`; a page without regions is one region) or all in one. A request never holds more than
    `lines_per_request` lines: a longer one is split on line boundaries, in order."""
    if granularity == "lines":
        groups = [[ln] for ln in lines]
    elif granularity == "region":
        groups = []
        for ln in lines:
            if groups and groups[-1][0].get("region", "") == ln.get("region", ""):
                groups[-1].append(ln)
            else:
                groups.append([ln])
    elif granularity == "page":
        groups = [list(lines)]
    else:
        raise ValueError(f"no granularity {granularity!r}: one of lines, region, page")
    cap = lines_per_request or max(len(lines), 1)
    return [g[i:i + cap] for g in groups for i in range(0, len(g), cap)]


def granularities_for(reader: str | None, provider: str, lines_per_request: int | None) -> tuple[str, ...]:
    """The granularities worth measuring for a reader. Kraken and Apple Vision read a line at a time by nature:
    none. A card that states `lines_per_request` says the model cannot take a page, so `page` would only be
    `region` again: not tried."""
    if reader != "vision" or provider == "apple":
        return ()
    return ("lines", "region") if lines_per_request else ("lines", "region", "page")


def granularities_to_try(candidate: EvaluationCandidate) -> tuple[str, ...]:
    return granularities_for(candidate.reader, candidate.provider, candidate.lines_per_request)


def read_with_vision(photo: str, candidate: EvaluationCandidate, lines: list[dict[str, Any]],
                     language: str | None) -> tuple[list[str], str | None]:
    """(the lines' readings, why the model gave nothing when it answered nothing or nothing readable).

    The lines are asked in the candidate's requests (`requests_for`). An answer that does not match its request
    (not one reading per line) reads as nothing for those lines: it is not re-asked another way, because how the
    model answers asked this way is the measure."""
    from PIL import Image

    from fichero_server.llm.line_reader import _crop_data_uri, parse_answer, prompt_for

    apple = candidate.provider == "apple"
    groups = ([[ln] for ln in lines] if apple else
              requests_for(lines, candidate.granularity, candidate.lines_per_request))
    with Image.open(photo) as page:
        crops = [[_crop_data_uri(page, ln["polygon"]) for ln in group] for group in groups]

    answers: list[str] = []
    parsed_all: list[list[str | None] | None] = []

    async def all_requests() -> list[str]:
        out: list[str] = []
        for group, pictures in zip(groups, crops):  # one request at a time: the local lane holds one model
            raw = await ask_vision(candidate, pictures, prompt_for(len(group), language))
            answers.append(raw or "")
            if apple:
                # Apple Vision recognises the text in each line's picture: its answer IS the reading, not a JSON array.
                out.append(" ".join((raw or "").split()))
                continue
            parsed = parse_answer(raw, len(group))
            parsed_all.append(parsed)
            out.extend((parsed[i] if parsed else None) or "" for i in range(len(group)))
        return out

    reads = asyncio.run(all_requests())
    if apple:
        if answers and not any(a.strip() for a in answers):
            return reads, "Apple Vision recognised no text in any line"
        return reads, None
    if answers and not any(a.strip() for a in answers):
        return reads, "the model gave an empty answer for every line"
    if parsed_all and all(p is None for p in parsed_all):
        return reads, "the model's answers were not the readings it was asked for"
    return reads, None


def word_errors(reference: list[str], reads: list[str]) -> dict[str, int]:
    """The page's word errors (#5660 item 7, WER beside CER): the word-level edit distance between the reference
    lines and the reads, and the reference's word count. Words are split on whitespace, as written; a page in a
    script that does not divide its words by spaces has none to count (0, so `wer_over` leaves it out): it is
    scored by character alone (`source.recipe.nothing-assumes-spaces-direction-or-an-alphabet`)."""
    from fichero_server.llm.language_policy import text_separates_words

    if not text_separates_words("\n".join(reference)):
        return {"distance": 0, "reference_words": 0}
    ref = " ".join(reference).split()
    hyp = " ".join(reads).split()
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return {"distance": previous[-1], "reference_words": len(ref)}


def wer_over(per_page: list[dict[str, Any]]) -> float | None:
    """The word error rate over the pages read, from each page's `words` (none kept before #5660: None)."""
    read = [p for p in per_page if p.get("read", True) and isinstance(p.get("words"), dict)]
    total = sum(p["words"]["reference_words"] for p in read)
    return sum(p["words"]["distance"] for p in read) / total if read and total else None


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


#: How many held-out splits the noise band is measured over (ruled Q6 2026-10-17, #5692).
NOISE_SPLITS = 3
#: The fewest read pages a band is measured from (review 70: three pages, one a split, measure nothing). Five a split.
#: ponytail: a stated floor; a per-split line count if pages vary too much in length.
NOISE_MIN_PAGES = 15


def noise_band(per_page: list[dict[str, Any]], splits: int = NOISE_SPLITS) -> float | None:
    """The CER spread over `splits` held-out splits of the pages a reader read (page i in split i % splits): the
    difference between the worst and the best split's CER. None with fewer than `NOISE_MIN_PAGES` read pages."""
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    scored = [p["scores"][DEFAULT_POLICY_NAME] for p in per_page
              if p.get("read", True) and (p["scores"].get(DEFAULT_POLICY_NAME) or {}).get("cer") is not None]
    if len(scored) < max(splits, NOISE_MIN_PAGES):
        return None
    cers = []
    for k in range(splits):
        part = scored[k::splits]
        chars = sum(s["reference_chars"] for s in part)
        if not chars:
            return None
        cers.append(sum(s["distance"] for s in part) / chars)
    return max(cers) - min(cers)


def speed(seconds: float, pages: int) -> dict[str, Any]:
    """The reading time measured in this run, and the pages an hour it gives on this Mac."""
    return {"seconds": round(seconds, 3), "pages": pages,
            "pages_per_hour": round(pages * 3600 / seconds, 1) if seconds > 0 and pages else None,
            "basis": "measured on this Mac"}


# --- the job -------------------------------------------------------------------------------------------


def plan(db: Any, request: EvaluationRunRequest) -> dict[str, Any]:
    """The candidates, the pages and what was left out, or refused in words. Nothing is read yet."""
    for c in request.candidates:
        if c.reader == "vision" and c.provider not in LOCAL_PROVIDERS and not request.remote_allowed:
            raise EvaluationRefused(f"{c.model} on {c.provider} would send the sample's lines off this Mac, and "
                                    "this evaluation keeps them here")
        if not on_this_mac(c.model, c.reader, c.provider):
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


def _trial_candidates(models: list[dict[str, Any]], tried: list[EvaluationCandidate],
                      request: EvaluationRunRequest) -> list[EvaluationCandidate]:
    """The candidates asked again at their other granularities (#5722): the `granularities_for_best` best vision
    models by their score at their own granularity, and every one the person named. The rest ran once."""
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    by_key = {(c.model, c.reader): c for c in tried}
    measured = sorted((m for m in models if m["measured"] and m["scores"][DEFAULT_POLICY_NAME]["cer"] is not None
                       and granularities_to_try(by_key[(m["model"], m["reader"])])),
                      key=lambda m: m["scores"][DEFAULT_POLICY_NAME]["cer"])
    best = list(dict.fromkeys(m["model"] for m in measured))[:request.granularities_for_best]
    take = {*best, *request.named}
    return [c.model_copy(update={"granularity": g}) for c in tried if c.model in take
            for g in granularities_to_try(c) if g != c.granularity]


def evaluate(db: Any, job_id: str, request: EvaluationRunRequest, planned: dict[str, Any],
             *, progress: Any = None) -> dict[str, Any]:
    from fichero_server.workflows.transcription_accuracy import CER_DEFINITION, DEFAULT_POLICY_NAME

    candidates = [EvaluationCandidate(**c) for c in planned["candidates"]]
    pages = [p for p in (reference_page(db, pid, request.checked)[0] for pid in planned["pages"]) if p]
    trust = {t: sum(p["trust"] == t for p in pages) for t in sorted({p["trust"] for p in pages})}
    models = []
    so_far = _measured_so_far(db, job_id)
    queue, i, trial_done = list(candidates), 0, False
    while i < len(queue):
        c = queue[i]
        i += 1
        asked = c.granularity if granularities_to_try(c) else None
        key = f"{c.model}|{c.reader}" + (f"|{asked}" if asked else "")
        per_page = list((so_far.get(key) or {}).get("per_page") or [])
        seconds = float((so_far.get(key) or {}).get("seconds") or 0.0)
        done = {p["document_id"] for p in per_page}
        for page in pages:
            if page["document_id"] in done:
                continue
            if _cancelled(db, job_id):
                return {"stopped": True, "models": models}
            if progress:
                progress(f"Reading {page['name']} with {c.model} (model {i} of {len(queue)})"
                         + (f", asked by {asked}" if asked else ""))
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
                                        "scores": score_page(reference, reads),
                                        "words": word_errors(reference, reads)}, why))
            _keep_measured(db, job_id, key, per_page, seconds)
        models.append({"model": c.model, "reader": c.reader, "granularity": asked,
                       "lines_per_request": c.lines_per_request,
                       "role": "trained" if trained_card(c) is not None else "out of the box",
                       **judged(per_page, len(pages)), "speed": speed(seconds, len(pages))})
        if i == len(queue) and not trial_done:
            trial_done = True
            queue += _trial_candidates(models, queue, request)
    measured_at = datetime.now(timezone.utc).isoformat()
    for m in models:
        record_on_card(m["model"], m["reader"], {
            "job_id": job_id, "measured_at": measured_at, "checked": request.checked, "trust": trust,
            "definition": CER_DEFINITION, "pages": [p["document_id"] for p in pages], "role": m["role"],
            "scores": m["scores"], "per_page": m["per_page"], "speed": m["speed"], "measured": m["measured"],
            "pages_read": m["pages_read"], "pages_total": m["pages_total"], "why": m["why"],
            "granularity": m["granularity"], "lines_per_request": m["lines_per_request"],
            "compared_with": list(dict.fromkeys(o["model"] for o in models if o["model"] != m["model"]))})
    ranked = sorted((m for m in models if m["measured"] and m["scores"][DEFAULT_POLICY_NAME]["cer"] is not None),
                    key=lambda m: m["scores"][DEFAULT_POLICY_NAME]["cer"])
    # One model asked three ways is still one candidate: a winner needs two models.
    no_best = no_winner_why(list(dict.fromkeys(m["model"] for m in ranked)))
    band = noise_band(ranked[0]["per_page"]) if ranked else None
    if band is not None:  # the project's noise band, from the best reader's own pages (#5692)
        from fichero_server.recipes.project import write_noise_band

        write_noise_band(Path(db.path).parent, band, pages=ranked[0]["pages_read"], model=ranked[0]["model"])
    return {"stopped": False, "measured_at": measured_at, "definition": CER_DEFINITION, "trust": trust,
            "noise_band": band,
            "ranked_by": DEFAULT_POLICY_NAME, "best": None if no_best else ranked[0]["model"],
            "best_granularity": None if no_best else ranked[0]["granularity"],
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


#: What an override the evaluation set says made it: a reader the rules chose, which a better one may replace.
ADOPTED_BY = "evaluation"


def adopt_trained(db: Any, result: dict[str, Any]) -> dict[str, Any] | None:
    """Set the best trained Kraken reader measured as the project's read-a-line reader, only when its CER beats
    the best downloadable reader's by more than the project's noise band (#5700, #5441,
    `source.train.adopt-only-past-the-noise-band`); kept through `project.save_setup` (audited, undoable), as a
    person's Use This is. A reader the person chose is never replaced (review 77): the trained one is measured
    against theirs and, past the band, offered (`offered`), not switched to. None when the evaluation measured no trained reader, else what was decided and why.
    ponytail: Kraken readers only; a trained vision model is measured and carded but not set on the step yet."""
    from fichero_server.recipes.project import read_noise_band, read_project_setup

    policy = result["ranked_by"]

    def best(role: str) -> dict[str, Any] | None:
        rows = [m for m in result["models"] if m["role"] == role and m["reader"] == "kraken" and m["measured"]
                and m["scores"][policy]["cer"] is not None]
        return min(rows, key=lambda m: m["scores"][policy]["cer"], default=None)

    trained, base = best("trained"), best("out of the box")
    if trained is None:
        return None
    library = Path(db.path).parent
    band = read_noise_band(library)["value"]
    recipe = read_project_setup(library).get("recipe")
    step = next((s for s in (recipe or {}).get("steps") or [] if s.get("job") == "read-a-line"), None)
    chosen = next((o for o in (recipe or {}).get("overrides") or [] if step is not None
                   and (o.get("step"), o.get("scope"), o.get("folder_id")) == (step["id"], "project", None)
                   and o.get("by") != ADOPTED_BY), None)
    if step is not None:  # review 77: the step's current reader is the one to beat, when it was measured
        from fichero_server.recipes.cards import kraken_reader_for

        pin = (chosen or {}).get("model") or step.get("model") or {}
        current = kraken_reader_for(pin) or pin.get("model") or pin.get("hf")
        base = next((m for m in result["models"] if m["model"] == current and m["measured"]
                     and m["scores"][policy]["cer"] is not None), base)
    if trained["pages_read"] < NOISE_MIN_PAGES:
        return {"adopted": None, "why": f"{trained['model']} was measured on {trained['pages_read']} held-out pages; "
                                        f"a reader is adopted from {NOISE_MIN_PAGES} up, as the noise band is"}
    cer = trained["scores"][policy]["cer"]
    if base is None:
        return {"adopted": None, "why": f"{trained['model']} was not compared with a downloadable reader, so the "
                                        "project keeps its reader"}
    gain = base["scores"][policy]["cer"] - cer
    said = (f"{trained['model']} CER {cer:.3f} against {base['model']} {base['scores'][policy]['cer']:.3f} "
            f"({policy}, {trained['pages_read']} held-out pages)")
    if gain <= band:
        return {"adopted": None, "gain": round(gain, 6), "noise_band": band,
                "why": (f"{said}: not adopted, the gain {gain:+.4f} is within the project's noise band ({band})"
                        if gain > 0 else f"{said}: not adopted, {base['model']} reads these pages as well or better")}
    if step is None:
        return {"adopted": None, "gain": round(gain, 6), "noise_band": band,
                "why": f"{said}: beyond the noise band, but this project's recipe has no read-a-line step"}
    if chosen is not None:
        return {"adopted": None, "offered": trained["model"], "step": step["id"], "gain": round(gain, 6),
                "noise_band": band,
                "why": (f"{said}: beyond the project's noise band ({band}), offered; the reader you chose stays "
                        "until you choose this one")}
    from fichero_server.actions.registry import ActionContext, registry

    because = f"trained on your corrections: {said}, beyond the project's noise band ({band})"
    recipe["overrides"] = [o for o in recipe.get("overrides") or []
                           if (o.get("step"), o.get("scope"), o.get("folder_id")) != (step["id"], "project", None)]
    recipe["overrides"].append({"step": step["id"], "scope": "project", "folder_id": None,
                                "model": {"trained": trained["model"]}, "card": trained["model"],
                                "runs_on": "this-mac", "cer": cer, "policy": policy, "because": because,
                                "by": ADOPTED_BY,
                                "at": datetime.now(timezone.utc).isoformat()})
    step["model"] = {"trained": trained["model"]}
    ctx = ActionContext(actor="evaluation", library_path=str(library), is_bootstrap=True)
    registry.invoke(db, "project.save_setup", {"recipe": recipe}, ctx)
    return {"adopted": trained["model"], "step": step["id"], "gain": round(gain, 6), "noise_band": band,
            "why": because}


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
    result["adoption"] = adopt_trained(db, result)
    detail["result"] = result
    said = words(result, len(planned["pages"])) + (f". {result['adoption']['why']}" if result["adoption"] else "")
    jobs.save_detail(db, job_id, json.dumps(detail), reason=said)
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
