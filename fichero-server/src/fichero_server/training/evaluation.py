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
  pass); with no `checked` named, the newest live pass a person made (the bake-off's ground truth). Its lines, empty and `null` readings left out (`kraken_set.line_flag`), are the right readings;
  each page records who checked it (`person` when a person wrote the pass, else `model`,
  `distill.scale.check-trust-levels`).
* **The reading.** Each candidate reads the checked pass's own lines: a Kraken reader on each line's
  baseline and outline (`kraken_runtime.read_given_lines`), a vision model on each line's picture, one
  line a call, with the line reader's prompt. Only this Mac's models: the job is on the local model
  lane. A remote model target is not built yet and is refused.
* **The score.** The ONE CER (`workflows.transcription_accuracy.character_error_rate`) of the page's
  readings (lines joined by newlines) against the checked text, under every named normalisation policy
  (`POLICIES`: diplomatic, layout-insensitive, lenient, accent-blind); per model, total edits over total
  reference characters across the pages. Every figure names its policy and carries the definition.
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
from fichero_server.models.compute_requests import EvaluationCandidate, EvaluationRunRequest

KIND = "evaluate-models"
#: Providers that run on this Mac. Anything else is a remote target, not built yet.
LOCAL_PROVIDERS = ("omlx",)
CARDS_DIR = "cards"


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


def checked_pass(db: Any, page_id: str, checked: str | None) -> Any | None:
    """The newest live pass on the page whose model or name is `checked`; with None, the newest a person made."""
    from fichero_server.models.segments import SegmentPass

    def is_reference(p: Any) -> bool:
        if checked is None:
            return getattr(p.provenance_kind, "value", p.provenance_kind) == "human"
        return checked in (p.model, p.name)

    passes = [p for p in db.query(SegmentPass, document_id=page_id) if not p.deleted_at and is_reference(p)]
    return max(passes, key=lambda p: p.created_at) if passes else None


def trust_of(chosen: Any) -> str:
    """Who checked the reference: `person` when a person wrote the pass, `model` when a model did."""
    kind = getattr(chosen.provenance_kind, "value", chosen.provenance_kind)
    if kind == "human":
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
    if not lines:
        return None, f"the pass {by_whom(checked)} has no read lines"
    return {"document_id": page_id, "name": doc.name, "photo": doc.path, "pass_id": chosen.id,
            "trust": trust_of(chosen), "lines": lines}, None


# --- reading and scoring -----------------------------------------------------------------------------


def read_with_kraken(photo: str, model: str, lines: list[dict[str, Any]]) -> list[str]:
    from fichero_server.llm import kraken_runtime

    model_path, _catalog = kraken_runtime.resolve_recognition_model(model)
    return kraken_runtime.read_given_lines(photo, model_path, lines)


async def ask_vision(candidate: EvaluationCandidate, image: str, prompt: str) -> str:
    """One line picture to a vision model on this Mac. The seam tests replace."""
    from fichero_server.llm import LLMConfig, vision

    return await vision(images=[image], prompt=prompt,
                        config=LLMConfig(provider=candidate.provider, model=candidate.model))


def read_with_vision(photo: str, candidate: EvaluationCandidate, lines: list[dict[str, Any]],
                     language: str | None) -> list[str]:
    from PIL import Image

    from fichero_server.llm.line_reader import _crop_data_uri, parse_answer, prompt_for

    prompt = prompt_for(1, language)
    with Image.open(photo) as page:
        crops = [_crop_data_uri(page, ln["polygon"]) for ln in lines]

    async def all_lines() -> list[str]:
        out = []
        for crop in crops:  # one line a call, one at a time: the local lane holds one model
            parsed = parse_answer(await ask_vision(candidate, crop, prompt), 1)
            out.append((parsed[0] if parsed else None) or "")
        return out

    return asyncio.run(all_lines())


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


def totals(per_page: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per policy: total edits over total reference characters across the pages scored."""
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


def evaluate(db: Any, job_id: str, request: EvaluationRunRequest, planned: dict[str, Any],
             *, progress: Any = None) -> dict[str, Any]:
    from fichero_server.workflows.transcription_accuracy import CER_DEFINITION, DEFAULT_POLICY_NAME

    candidates = [EvaluationCandidate(**c) for c in planned["candidates"]]
    pages = [p for p in (reference_page(db, pid, request.checked)[0] for pid in planned["pages"]) if p]
    trust = {t: sum(p["trust"] == t for p in pages) for t in sorted({p["trust"] for p in pages})}
    models = []
    for i, c in enumerate(candidates, 1):
        per_page = []
        seconds = 0.0
        for page in pages:
            if _cancelled(db, job_id):
                return {"stopped": True, "models": models}
            if progress:
                progress(f"Reading {page['name']} with {c.model} (model {i} of {len(candidates)})")
            reference = [ln["text"] for ln in page["lines"]]
            began = time.monotonic()
            reads = (read_with_kraken(page["photo"], c.model, page["lines"]) if c.reader == "kraken"
                     else read_with_vision(page["photo"], c, page["lines"], request.language))
            seconds += time.monotonic() - began
            per_page.append({"document_id": page["document_id"], "name": page["name"], "trust": page["trust"],
                             "lines": len(reference), "scores": score_page(reference, reads)})
        models.append({"model": c.model, "reader": c.reader,
                       "role": "trained" if trained_card(c) is not None else "out of the box",
                       "scores": totals(per_page), "per_page": per_page, "speed": speed(seconds, len(pages))})
    measured_at = datetime.now(timezone.utc).isoformat()
    for m in models:
        record_on_card(m["model"], m["reader"], {
            "job_id": job_id, "measured_at": measured_at, "checked": request.checked, "trust": trust,
            "definition": CER_DEFINITION, "pages": [p["document_id"] for p in pages], "role": m["role"],
            "scores": m["scores"], "per_page": m["per_page"], "speed": m["speed"],
            "compared_with": [o["model"] for o in models if o is not m]})
    ranked = sorted((m for m in models if m["scores"][DEFAULT_POLICY_NAME]["cer"] is not None),
                    key=lambda m: m["scores"][DEFAULT_POLICY_NAME]["cer"])
    return {"stopped": False, "measured_at": measured_at, "definition": CER_DEFINITION, "trust": trust,
            "ranked_by": DEFAULT_POLICY_NAME, "best": ranked[0]["model"] if ranked else None, "models": models}


def words(result: dict[str, Any], pages: int) -> str:
    from fichero_server.workflows.transcription_accuracy import DEFAULT_POLICY_NAME

    best = next((m for m in result["models"] if m["model"] == result.get("best")), None)
    said = f"Scored {len(result['models'])} models on {pages} held-out pages"
    if best:
        said += f"; best {best['model']} (CER {best['scores'][DEFAULT_POLICY_NAME]['cer']:.3f}, {DEFAULT_POLICY_NAME})"
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
