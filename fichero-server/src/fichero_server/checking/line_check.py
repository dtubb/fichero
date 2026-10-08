"""The teacher-line check: each line's reading against Kraken's rough read of the page
(`source.lines.reading-checked-against-the-page`, #5446).

A teacher (Gemini reading the lines Kraken found) can give a line the text of the line above or below it.
Kraken's reader reads every line of the pass again, on the line's own baseline and outline (a rough read:
a stock reader, not a good one), and the teacher's reading of each line is scored against that rough read
and against the rough reads of its neighbours. The rule and thresholds are the Sergio project's
`teacher_line_check.py`, which found the shifted lines of the Mosquera teacher set (2026-10-04):

* **closer to a neighbour**: a line up to `NEIGHBOURS` either side, in the same column (their horizontal
  spans overlap), agrees with the reading by at least `SHIFT_FLOOR` and by `SHIFT_MARGIN` more than the
  line's own rough read: the reading is misaligned.
* **below the threshold**: otherwise, the reading agrees with its own rough read by less than `LOW`.

Agreement is 1 minus the character error rate (`character_error_rate`, accent-blind: case, accents,
punctuation and spacing do not count, as in the script), floored at 0. An empty or `null` reading is not
scored here: the training set already leaves it out (`kraken_set.line_flag`).

A flag is a `reject` verdict from the reader (`check.verdict`, trust `model`), with the scores in its
reasons, so the training set's rule leaves the line out with no other change
(`compute.tune.set-excludes-flagged-lines`). A line that passes gets no verdict: a confirm from a rough
reader would outrank an earlier reject by Fable. A line whose reading carries a person's verdict is not
checked again: a person's word stands, so a person's confirm brings a flagged line back for good.

One row in Activity (kind `check-lines`), on the local model lane: Kraken runs on this Mac.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fichero_server.execution import jobs
from fichero_server.models.checking import CheckRunRequest

KIND = "check-lines"
NEIGHBOURS = 2
SHIFT_MARGIN = 0.15
SHIFT_FLOOR = 0.40
LOW = 0.30
POLICY = "accent-blind"
SHIFTED = "closer to a neighbour"
BELOW = "below the threshold"
COUNTS = ("passed", "closer_to_a_neighbour", "below_the_threshold", "not_scored", "checked_by_a_person")
_COUNT_OF = {SHIFTED: "closer_to_a_neighbour", BELOW: "below_the_threshold"}


def agreement(teacher: str, rough: str) -> float:
    """How far the teacher's text agrees with a rough read: 1 - CER, floored at 0 (0 when nothing to score)."""
    from fichero_server.workflows.transcription_accuracy import RunComparisonError, character_error_rate

    try:
        return max(0.0, 1.0 - character_error_rate(teacher, rough or "", policy=POLICY).cer)
    except RunComparisonError:
        return 0.0


def _same_column(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    ax, bx = [p[0] for p in a] or [0.0], [p[0] for p in b] or [0.0]
    return min(max(ax), max(bx)) - max(min(ax), min(bx)) > 0


def flag_lines(lines: list[dict[str, Any]], reads: list[str]) -> list[dict[str, Any]]:
    """Each line's scores and flag (None when it passes). `lines` carry `text` and `polygon`, in reading order."""
    out = []
    for i, line in enumerate(lines):
        text = line["text"]
        own = agreement(text, reads[i])
        near = [(agreement(text, reads[j]), j) for j in range(max(0, i - NEIGHBOURS), min(len(lines), i + NEIGHBOURS + 1))
                if j != i and _same_column(line["polygon"], lines[j]["polygon"])]
        best, best_j = max(near, default=(0.0, None))
        if best >= SHIFT_FLOOR and best >= own + SHIFT_MARGIN:
            flag = SHIFTED
        elif own < LOW:
            flag = BELOW
        else:
            flag = None
        out.append({"own": round(own, 3), "neighbour": round(best, 3),
                    "offset": None if best_j is None else best_j - i, "flag": flag, "rough_read": reads[i]})
    return out


def _points(attr: str | None) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in (p.split(",") for p in (attr or "").split())]


def page_lines(page_xml: str) -> list[dict[str, Any]]:
    """Each TextLine of a PAGE file, in file (reading) order: its id, outline, baseline and text."""
    from fichero_server.formats.pagexml import PAGE_NS_2019
    from fichero_server.security.xml_security import parse_xml_string

    ns = f"{{{PAGE_NS_2019}}}"
    found = []
    for line in parse_xml_string(page_xml).iter(f"{ns}TextLine"):
        coords, base = line.find(f"{ns}Coords"), line.find(f"{ns}Baseline")
        # The line's FIRST own TextEquiv: the export writes the counting reading first and the others
        # after it as alternatives. Joining every Unicode read a corrected line as the correction plus the
        # machine's original (#5499). Only a line with no text of its own reads its words'.
        own = line.find(f"{ns}TextEquiv")
        texts = own.iter(f"{ns}Unicode") if own is not None else line.iter(f"{ns}Unicode")
        found.append({"id": line.get("id") or "",
                      "polygon": _points(coords.get("points") if coords is not None else None),
                      "baseline": _points(base.get("points") if base is not None else None),
                      "text": "".join(u.text or "" for u in texts).strip()})
    return found


def start(db: Any, request: CheckRunRequest, *, started_by: str) -> dict[str, str]:
    if request.layer != "readings":
        raise ValueError("the line-against-page check checks readings")
    if request.provider != "kraken":
        raise ValueError("the line-against-page check reads with a Kraken reader: provider kraken")
    job_id = jobs.enqueue(db, KIND, f"check-lines:{uuid.uuid4()}", started_by=started_by, watched=True,
                          detail=json.dumps({"request": request.model_dump()}))
    return {"job_id": job_id}


def _person_checked(db: Any, segment_id: str, verdicts: dict[str, Any]) -> bool:
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    return any(verdicts[r.id].trust == "person" for r in readings_of_segment(db, segment_id) if r.id in verdicts)


def _newest_by_reading(db: Any) -> dict[str, Any]:
    """Each reading's verdicts by a person, newest last (a person's verdict on any reading of a line counts)."""
    from fichero_server.models.checking import CheckVerdict

    return {v.target_id: v for v in sorted(db.query(CheckVerdict, layer="readings", trust="person"),
                                          key=lambda v: (v.created_at, v.id))}


def _check(db: Any, job_id: str, request: CheckRunRequest, started_by: str) -> dict[str, Any]:
    import fichero_server.api.routes.check  # noqa: F401  (registers check.verdict)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
    from fichero_server.checking.cards import _descendants
    from fichero_server.formats.harness import xml_id
    from fichero_server.llm import kraken_runtime
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass
    from fichero_server.page_export import ExportRefused, export_page

    model_path, _catalog = kraken_runtime.resolve_recognition_model(request.model)
    ctx = ActionContext(actor=started_by, run_id=job_id, library_path=str(Path(db.path).parent))
    person = _newest_by_reading(db)
    # What an earlier attempt of this job already checked (#5524): a check that stopped for memory goes
    # back to waiting and, run again, carries on after the last page it finished, so no line gets a
    # second verdict and the counts are the whole run's.
    so_far = json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}").get("checked_so_far") or {}
    counts = {**dict.fromkeys(COUNTS, 0), **(so_far.get("counts") or {})}
    flagged: list[dict[str, Any]] = list(so_far.get("flagged") or [])
    missing: list[dict[str, str]] = list(so_far.get("missing") or [])
    done: list[str] = list(so_far.get("docs") or [])
    stopped = False

    def check_page(doc: Any) -> None:
        passes = [p for p in db.query(SegmentPass, document_id=doc.id) if not p.deleted_at
                  and (request.pass_model is None or p.model == request.pass_model)]
        segments_by_pass = {p.id: {xml_id(s.id): s for s in db.query(Segment, pass_id=p.id)
                                   if s.kind == "line" and not s.deleted_at} for p in passes}
        passes = [p for p in passes if segments_by_pass[p.id]]
        if not passes:
            return
        chosen = max(passes, key=lambda p: p.created_at)
        segments = segments_by_pass[chosen.id]
        photo = Path(doc.path) if doc.path else None
        if photo is None or not photo.is_file():
            missing.append({"document_id": doc.id, "why": "its photograph is not on this Mac"})
            return
        try:
            lines = [ln for ln in page_lines(export_page(db, doc.id, "pagexml", pass_id=chosen.id).data.decode("utf-8"))
                     if ln["id"] in segments]
        except ExportRefused as exc:
            missing.append({"document_id": doc.id, "why": str(exc)})
            return
        reads = kraken_runtime.read_given_lines(photo, model_path, lines)
        for line, scored in zip(lines, flag_lines(lines, reads)):
            segment = segments[line["id"]]
            if not line["text"] or line["text"].casefold() == "null":
                counts["not_scored"] += 1
                continue
            if _person_checked(db, segment.id, person):
                counts["checked_by_a_person"] += 1
                continue
            if scored["flag"] is None:
                counts["passed"] += 1
                continue
            items = readings_of_segment(db, segment.id)
            counted = counting_by_kind(db, segment.id, items).get(request.kind)
            reading = next((i for i in items if counted and i.id == counted.representation_id), None) or (
                items[0] if items else None)
            if reading is None:
                counts["not_scored"] += 1
                continue
            where = "" if scored["offset"] is None else (
                f", {scored['neighbour']:.2f} with the line {abs(scored['offset'])} "
                f"{'below' if scored['offset'] > 0 else 'above'}")
            reasons = (f"{scored['flag']}: agrees {scored['own']:.2f} with Kraken's rough read of its own line"
                       f"{where} (rough read: {scored['rough_read']!r})")
            registry.invoke(db, "check.verdict", {
                "layer": "readings", "target_id": reading.id, "verdict": "reject", "reasons": reasons,
                "checker_model": request.model, "segment_id": segment.id}, ctx)
            counts[_COUNT_OF[scored["flag"]]] += 1
            flagged.append({"document_id": doc.id, "segment_id": segment.id, "reading_id": reading.id,
                            "flag": scored["flag"], "own": scored["own"], "neighbour": scored["neighbour"],
                            "offset": scored["offset"]})

    for doc in _descendants(db, request.scope_ids):
        if getattr(doc.doc_type, "value", doc.doc_type) not in ("file", "page") or doc.id in done:
            continue
        if json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}").get("cancel"):
            stopped = True
            break
        check_page(doc)  # a memory stop raises out of here before the page counts as checked
        done.append(doc.id)
        detail = json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}")
        detail["checked_so_far"] = {"docs": done, "counts": counts, "flagged": flagged, "missing": missing}
        # The reason says how far it has got, so Activity shows progress while it runs (#5524).
        jobs.save_detail(db, job_id, json.dumps(detail),
                         reason=f"Checking lines against the page with {request.model}: {words(counts)} so far")
    return {"counts": counts, "flagged": flagged, "missing": missing, "stopped": stopped,
            "thresholds": {"neighbours": NEIGHBOURS, "shift_margin": SHIFT_MARGIN, "shift_floor": SHIFT_FLOOR,
                           "low": LOW, "policy": POLICY}}


def words(counts: dict[str, int]) -> str:
    return (f"{counts['passed']} passed, {counts['closer_to_a_neighbour']} closer to a neighbour, "
            f"{counts['below_the_threshold']} below the threshold")


def run(db: Any, subject: str) -> dict[str, Any]:
    job_id = jobs.job_id_for(db, KIND, subject)
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    request = CheckRunRequest(**detail["request"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Checking lines against the page with {request.model}")
    result = _check(db, job_id, request, row["started_by"] or "owner")
    detail = json.loads(jobs.read_job(db, job_id)["detail"] or "{}")
    detail["result"] = result
    said = words(result["counts"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason=said)
    if result["stopped"]:
        raise jobs.JobCancelled(f"Stopped by you; {said}")
    return result


def _request_cancel(db: Any, job_id: str) -> str:
    from fichero_server.checking.job import request_cancel

    return request_cancel(db, job_id)


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, name="Check lines against the page",
                           cancel=_request_cancel)  # Stop on its row reaches a running one (#5356)
