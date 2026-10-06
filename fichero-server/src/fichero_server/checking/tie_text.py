"""Tie a page's reading to its lines (`source.job.tie-text-to-lines`, #5444).

A page read whole by a model (Gemini reading the page) has good text and no lines; Kraken finds the lines
and reads each roughly (a stock reader, `kraken_runtime.read_given_lines`). The page's reading is aligned
to those rough reads in order, character by character (`align`: one edit-distance alignment of the page
text against the rough reads joined, so no line takes text from beyond its neighbours'), and each line is
given the stretch of the page text it matches.

Ruled 2026-10-04 (#5444): the tie is automatic where the match is good. A line whose stretch agrees with
its own rough read by at least `THRESHOLD` (1 minus the accent-blind CER, `line_check.agreement`) is tied.
Below it the line is doubtful: it still gets the stretch, so a person has something to check, and a
`reject` verdict from the reader (`check.verdict`, trust `model`, "doubtful: page text and line disagree"
with the score), so the training set's own rule leaves it out until a person confirms it
(`compute.tune.set-excludes-flagged-lines`), exactly like the line check (`line_check`).

What is written, all through audited, undoable actions under the job's run (so every row is a machine's,
`workflow`, never a person's): a new pass (`segment.pass_create`) naming the page reading as its source
(its provider and model are the page reading's: the model that read the text), a copy of each Kraken line
(and its region) in it (`segment.create`), and each line's reading (`representation.create`, derived
from the page reading's artifact). The Kraken pass is left as it was. A page already tied to that page
reading is not tied again.

The page's reading is its newest model transcription (an artifact of type `transcription`). Not built:
a person's or a checked page reading ranked first (`source.job.tie-text-to-lines`).

One row in Activity (kind `tie-text-to-lines`, the recipe job's own name), on the local model lane.
"""
from __future__ import annotations

import json
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from fichero_server.checking.line_check import agreement, page_lines
from fichero_server.execution import jobs
from fichero_server.models.checking import CheckRunRequest

KIND = "tie-text-to-lines"
#: The match threshold. Default taken 2026-10-05 (design lead): the line check's own-score floor
#: (`line_check.LOW`), awaiting the maintainer's ruling.
THRESHOLD = 0.30
TIED_NAME = "Page reading tied to Kraken's lines"
DOUBTFUL = "doubtful: page text and line disagree"
#: How far, beyond their difference in length, the page text and the lines' reads may drift apart.
BAND = 200
COUNTS = ("tied", "doubtful", "no_text", "pages_tied", "already_tied", "no_page_reading", "no_lines")


def _fold(ch: str) -> str:
    """One character as compared: case- and accent-blind, any space the same."""
    if ch.isspace():
        return " "
    return (unicodedata.normalize("NFD", ch)[:1] or ch).casefold()[:1]


def align(page_text: str, reads: list[str]) -> list[str]:
    """The stretch of `page_text` each line matches, in order (one per read).

    One global edit-distance alignment of the page text against the rough reads joined by a space. A
    line's stretch starts where the alignment enters that line's first character, so the stretches are
    contiguous, in the page's own order, and together are the whole page text: nothing is reordered,
    dropped or given twice."""
    if not reads:
        return []
    joined = " ".join(reads)
    starts, at = [], 0
    for read in reads:
        starts.append(at)
        at += len(read) + 1
    p = [_fold(c) for c in page_text]
    r = [_fold(c) for c in joined]
    n, m = len(p), len(r)
    # moves[i][j]: 0 diagonal, 1 up (page char against nothing), 2 left (read char against nothing).
    # Only a band about the diagonal is worked out (a page's text and its lines' reads run side by side,
    # drifting by at most their difference in length plus `BAND`): cells outside it cannot be on the path.
    width = abs(n - m) + BAND
    far = n + m + 1
    moves = [bytearray(m + 1) for _ in range(n + 1)]
    prev = [j if j <= width else far for j in range(m + 1)]
    for j in range(1, m + 1):
        moves[0][j] = 2
    for i in range(1, n + 1):
        centre = i * m // n
        lo, hi = max(1, centre - width), min(m, centre + width)
        cur = [far] * (m + 1)
        cur[0] = i if centre <= width else far
        row = moves[i]
        row[0] = 1
        pc = p[i - 1]
        for j in range(lo, hi + 1):
            diag = prev[j - 1] + (pc != r[j - 1])
            up = prev[j] + 1
            left = cur[j - 1] + 1
            if diag <= up and diag <= left:
                cur[j] = diag
            elif up <= left:
                cur[j], row[j] = up, 1
            else:
                cur[j], row[j] = left, 2
        prev = cur
    # Walk back: the smallest page index at which the path stands in each read column.
    first_i = [n] * (m + 1)
    i, j = n, m
    first_i[m] = n
    while i > 0 or j > 0:
        move = moves[i][j]
        if move == 0:
            i, j = i - 1, j - 1
        elif move == 1:
            i -= 1
        else:
            j -= 1
        first_i[j] = min(first_i[j], i)
    cuts = [0] + [first_i[s] for s in starts[1:]] + [n]
    for k in range(1, len(cuts) - 1):
        cuts[k] = _snap(page_text, max(cuts[k], cuts[k - 1]), cuts[k - 1], cuts[k + 1])
    return [page_text[cuts[k]:cuts[k + 1]].strip() for k in range(len(reads))]


def _snap(text: str, cut: int, low: int, high: int) -> int:
    """A cut inside a word moved to the nearest space, never past the cuts either side: a line ends
    between words (a word broken across lines is written so in the page text, and its break is a space)."""
    high = max(high, cut)

    def inside(i: int) -> bool:
        return 0 < i < len(text) and not text[i - 1].isspace() and not text[i].isspace()

    if not inside(cut):
        return cut
    for step in range(1, len(text) + 1):
        for i in (cut - step, cut + step):
            if low <= i <= high and not inside(i):
                return i
        if cut - step < low and cut + step > high:
            break
    return cut


def tie_lines(page_text: str, reads: list[str]) -> list[dict[str, Any]]:
    """Each line's stretch, its score against its own rough read, and whether it is tied."""
    out = []
    for stretch, read in zip(align(page_text, reads), reads):
        score = round(agreement(stretch, read), 3) if stretch else 0.0
        out.append({"text": stretch, "score": score, "tied": bool(stretch) and score >= THRESHOLD,
                    "rough_read": read})
    return out


def start(db: Any, request: CheckRunRequest, *, started_by: str) -> dict[str, str]:
    if request.layer != "readings":
        raise ValueError("tying the page text to its lines writes readings: layer readings")
    if request.provider != "kraken":
        raise ValueError("tying the page text to its lines reads each line with a Kraken reader: provider kraken")
    job_id = jobs.enqueue(db, KIND, f"{KIND}:{uuid.uuid4()}", started_by=started_by, watched=True,
                          detail=json.dumps({"request": request.model_dump()}))
    return {"job_id": job_id}


def page_reading(db: Any, document_id: str) -> Any | None:
    """The page's best reading: its newest model transcription with text that the read checker did
    not flag (#5522: a looping or cut-off read is never the reading tied to the lines)."""
    from fichero_server.llm.read_guard import read_flag_of
    from fichero_server.models import Artifact

    found = [a for a in db.query(Artifact, document_id=document_id, artifact_type="transcription")
             if (a.content or "").strip() and read_flag_of(a) is None]
    return max(found, key=lambda a: (a.created_at, a.id), default=None)


def _lines_pass(db: Any, document_id: str, pass_model: str | None) -> tuple[Any, dict[str, Any]] | None:
    """The newest live pass with lines (Kraken's), never a pass this job made, and its lines by PAGE id."""
    from fichero_server.formats.harness import xml_id
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass

    best = None
    for p in db.query(SegmentPass, document_id=document_id):
        if p.deleted_at or p.name == TIED_NAME or (pass_model is not None and p.model != pass_model):
            continue
        rows = {xml_id(s.id): s for s in db.query(Segment, pass_id=p.id) if s.kind == "line" and not s.deleted_at}
        if rows and (best is None or p.created_at > best[0].created_at):
            best = (p, rows)
    return best


def _already_tied(db: Any, document_id: str, artifact_id: str) -> bool:
    from fichero_server.models.segments import SegmentPass

    return any(p.name == TIED_NAME and p.source_artifact_id == artifact_id and not p.deleted_at
               for p in db.query(SegmentPass, document_id=document_id))


def _copy(db: Any, ctx: Any, registry: Any, pass_id: str, row: Any, parent_id: str | None) -> str:
    made = registry.invoke(db, "segment.create", {
        "document_id": row.document_id, "pass_id": pass_id, "kind": row.kind, "kind_raw": row.kind_raw,
        "anchor": row.anchor.model_dump(mode="json"), "baseline": row.baseline,
        "parent_segment_id": parent_id}, ctx).result
    segment_id = made["segment_ids"][0]
    # The copy keeps the Kraken pass's order: it is placed last at its level, in the order the lines are
    # copied, not where its box sorts on the page (the copy carries no file position of its own).
    from fichero_server.api.routes.document.reading_orders import as_written_order
    from fichero_server.models.reading_orders import ReadingOrderEntry

    order = as_written_order(db, pass_id)
    if order is not None:
        parent_entry = next((e.id for e in db.query(ReadingOrderEntry, order_id=order.id)
                             if parent_id and e.segment_id == parent_id), None)
        registry.invoke(db, "reading_order.place", {"order_id": order.id, "segment_id": segment_id,
                                                    "at_end": True, "parent_entry_id": parent_entry}, ctx)
    return segment_id


def _tie(db: Any, job_id: str, request: CheckRunRequest, started_by: str) -> dict[str, Any]:
    import fichero_server.api.routes.check  # noqa: F401  (registers check.verdict)
    import fichero_server.api.routes.document.content_representations  # noqa: F401  (representation.create)
    import fichero_server.api.routes.document.segments  # noqa: F401  (segment.pass_create, segment.create)
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.checking.cards import _descendants
    from fichero_server.llm import kraken_runtime
    from fichero_server.models import Segment
    from fichero_server.page_export import ExportRefused, export_page

    model_path, _catalog = kraken_runtime.resolve_recognition_model(request.model)
    ctx = ActionContext(actor=started_by, run_id=job_id, library_path=str(Path(db.path).parent))
    counts = dict.fromkeys(COUNTS, 0)
    flagged: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    stopped = False
    for doc in _descendants(db, request.scope_ids):
        if getattr(doc.doc_type, "value", doc.doc_type) not in ("file", "page"):
            continue
        if json.loads((jobs.read_job(db, job_id) or {}).get("detail") or "{}").get("cancel"):
            stopped = True
            break
        reading = page_reading(db, doc.id)
        if reading is None:
            counts["no_page_reading"] += 1
            continue
        if _already_tied(db, doc.id, reading.id):
            counts["already_tied"] += 1
            continue
        found = _lines_pass(db, doc.id, request.pass_model)
        if found is None:
            counts["no_lines"] += 1
            continue
        source, segments = found
        photo = Path(doc.path) if doc.path else None
        if photo is None or not photo.is_file():
            missing.append({"document_id": doc.id, "why": "its photograph is not on this Mac"})
            continue
        try:
            lines = [ln for ln in page_lines(export_page(db, doc.id, "pagexml", pass_id=source.id).data.decode("utf-8"))
                     if ln["id"] in segments]
        except ExportRefused as exc:
            missing.append({"document_id": doc.id, "why": str(exc)})
            continue
        reads = kraken_runtime.read_given_lines(photo, model_path, lines)
        tied = tie_lines(reading.content, reads)
        made_pass = registry.invoke(db, "segment.pass_create", {
            "document_id": doc.id, "name": TIED_NAME, "run_id": job_id, "source_artifact_id": reading.id}, ctx).result
        copied: dict[str, str] = {}
        for line, scored in zip(lines, tied):
            row = segments[line["id"]]
            parent_id = None
            if row.parent_segment_id:
                parent_id = copied.get(row.parent_segment_id)
                parent = db.get(Segment, row.parent_segment_id) if parent_id is None else None
                if parent is not None and not parent.deleted_at and parent.kind != "line":
                    parent_id = copied[parent.id] = _copy(db, ctx, registry, made_pass["id"], parent, None)
            segment_id = _copy(db, ctx, registry, made_pass["id"], row, parent_id)
            if not scored["text"]:
                counts["no_text"] += 1
                continue
            made = registry.invoke(db, "representation.create", {
                "document_id": doc.id, "segment_id": segment_id, "kind": request.kind, "content": scored["text"],
                "derived_from_artifact_id": reading.id}, ctx).result
            if scored["tied"]:
                counts["tied"] += 1
                continue
            reasons = (f"{DOUBTFUL}: agrees {scored['score']:.2f} with Kraken's rough read of the line, "
                       f"below {THRESHOLD:.2f} (rough read: {scored['rough_read']!r})")
            registry.invoke(db, "check.verdict", {
                "layer": "readings", "target_id": made["id"], "verdict": "reject", "reasons": reasons,
                "checker_model": request.model, "segment_id": segment_id}, ctx)
            counts["doubtful"] += 1
            flagged.append({"document_id": doc.id, "segment_id": segment_id, "reading_id": made["id"],
                            "flag": DOUBTFUL, "score": scored["score"]})
        counts["pages_tied"] += 1
    return {"counts": counts, "flagged": flagged, "missing": missing, "stopped": stopped,
            "thresholds": {"tie": THRESHOLD, "policy": "accent-blind"}}


def words(counts: dict[str, int]) -> str:
    return (f"{counts['tied']} lines tied, {counts['doubtful']} doubtful, on {counts['pages_tied']} pages; "
            f"{counts['already_tied']} already tied")


def run(db: Any, subject: str) -> dict[str, Any]:
    job_id = jobs.job_id_for(db, KIND, subject)
    row = jobs.read_job(db, job_id)
    detail = json.loads(row["detail"] or "{}")
    request = CheckRunRequest(**detail["request"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason=f"Tying the page text to its lines with {request.model}")
    result = _tie(db, job_id, request, row["started_by"] or "owner")
    detail = json.loads(jobs.read_job(db, job_id)["detail"] or "{}")
    detail["result"] = result
    said = words(result["counts"])
    jobs.save_detail(db, job_id, json.dumps(detail), reason=said)
    if result["stopped"]:
        raise jobs.JobCancelled(f"Stopped by you; {said}")
    return result


def register_job_kinds() -> None:
    if KIND not in jobs.KINDS or jobs.KINDS[KIND].run is None:
        jobs.register_kind(KIND, lambda db, subject: run(db, subject), model=None, name="Tie the page text to its lines")
