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
`workflow`, never a person's): each line's stretch as a reading ON THE PAGE'S OWN LINES
(`representation.create`, derived from the page reading's artifact, whose provider and model say who read
the text). One line pass per page, read many times (#5487, ruled 2026-10-05, #5467): the lines are those
of the page's working pass (`llm.working_lines`); a page with none has them found by Kraken first, its
regions kept as the lines' parents, through the same save and conversion as Find Lines. No second pass is
made. A page already tied to that page reading is not tied again; a line given no stretch is left untied
and counted. Which reading of a line counts is the counting rule's (`resolve_counting`): the tied stretch
is the line's newest machine reading, so an older machine reading of it stays as history.

The page's reading is ranked (`page_reading`): a person's, then a checked model reading, then the newest
model transcription; never a flagged read, and never a reading that is the lines' own text (a reader's
words already on the lines, or Kraken's own read), which would make a rough read its own reference.

One row in Activity (kind `tie-text-to-lines`, the recipe job's own name), on the local model lane.
"""
from __future__ import annotations

import json
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from fichero_server.checking.line_check import agreement
from fichero_server.execution import jobs
from fichero_server.models.checking import CheckRunRequest

KIND = "tie-text-to-lines"
#: The match threshold. Default taken 2026-10-05 (design lead): the line check's own-score floor
#: (`line_check.LOW`), awaiting the maintainer's ruling.
THRESHOLD = 0.30
DOUBTFUL = "doubtful: page text and line disagree"
#: How far, beyond their difference in length, the page text and the lines' reads may drift apart.
BAND = 200
COUNTS = ("tied", "doubtful", "untied", "pages_tied", "already_tied", "no_page_reading", "no_lines", "lines_found")


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


#: Who queues the tie when a page reading lands (#5558): nobody pressed anything.
AUTOMATIC = "automatic"


def rough_reader(db: Any) -> str | None:
    """The Kraken reader an automatic tie reads the lines with: the project recipe's own (its tie step's
    reader, else its line reader's, when that is a Kraken reader on this Mac), else the first reader of
    Kraken's catalogue on this Mac; None when this Mac has none (the tie cannot read the lines)."""
    from fichero_server.llm.kraken_runtime import KRAKEN_RECOGNITION_MODELS, is_recognition_model_installed
    from fichero_server.recipes.cards import kraken_reader_for
    from fichero_server.recipes.project import read_project_setup

    try:
        recipe = read_project_setup(Path(db.path).parent).get("recipe") or {}
    except (OSError, ValueError):
        recipe = {}
    steps = sorted((s for s in recipe.get("steps") or [] if s.get("job") in (KIND, "read-a-line")),
                   key=lambda s: s.get("job") != KIND)
    named = [kraken_reader_for(s.get("model") or {}) for s in steps]
    for reader in [*named, *KRAKEN_RECOGNITION_MODELS]:
        if reader and is_recognition_model_installed(reader):
            return reader
    return None


def after_page_reading(db: Any, artifact: Any) -> str | None:
    """Queue the tie for a page reading just saved (#5558, source-model.md "Every output comes into the
    page"): no recipe step needs to name it. Only for a reading of the whole page (a transcription with no
    lines of its own, not flagged, not the lines' own text) on a page that HAS lines: a page without lines
    gets them from its reading step, and a result with boxes becomes its own pass. Background work: one
    waiting job per page on the local model lane (many readings of a page make one tie), never run inline.
    Returns the job id, or None when nothing is queued."""
    from fichero_server.llm.read_guard import read_flag_of
    from fichero_server.llm.working_lines import working_lines

    if artifact.artifact_type != "transcription" or not (artifact.content or "").strip():
        return None
    if artifact.ocr_geometry is not None and artifact.ocr_geometry.boxes:  # raw-geometry-ok: has it lines?
        return None
    if read_flag_of(artifact) is not None or _read_from_lines(artifact):
        return None
    if working_lines(db, artifact.document_id) is None:
        return None
    reader = rough_reader(db)
    if reader is None:
        return None
    register_job_kinds()
    request = CheckRunRequest(layer="readings", scope_ids=[artifact.document_id], provider="kraken", model=reader,
                              check=KIND)
    return jobs.enqueue(db, KIND, f"{KIND}:after-reading:{artifact.document_id}", started_by=AUTOMATIC,
                        detail=json.dumps({"request": request.model_dump()}))


def _read_from_lines(artifact: Any) -> bool:
    """True for a reading that is its lines' own text joined: a reader's words already written onto the
    page's lines (`working_lines.READ_ONTO_PASS`, #5487), or Kraken's own read of the lines it found. Tied
    back to the lines, a rough read would be made the reference for itself (#5444, 2026-10-06)."""
    from fichero_server.llm.working_lines import READ_ONTO_PASS

    if (artifact.data or {}).get(READ_ONTO_PASS):
        return True
    geometry = artifact.ocr_geometry  # raw-geometry-ok: which reader made the result, not its boxes
    return geometry is not None and str(geometry.source or "").startswith("kraken")


def page_reading(db: Any, document_id: str) -> Any | None:
    """The page's best reading (`source.job.tie-text-to-lines`): a person's reading first, then a checked
    model reading (marked reviewed, or confirmed by a person's verdict), then the newest model reading;
    newest first within each. Never a reading the read checker flagged (#5522: a looping or cut-off read is
    never the reading tied to the lines), and never one read from the lines themselves (`_read_from_lines`)."""
    from fichero_server.llm.read_guard import read_flag_of
    from fichero_server.models import Artifact
    from fichero_server.models.checking import CheckVerdict

    found = [a for a in db.query(Artifact, document_id=document_id, artifact_type="transcription")
             if (a.content or "").strip() and read_flag_of(a) is None and not _read_from_lines(a)]

    def checked(a: Any) -> bool:
        return bool(a.reviewed) or any(v.verdict == "confirm" for v in
                                       db.query(CheckVerdict, target_id=a.id, trust="person"))

    return max(found, key=lambda a: (a.provider == "human", checked(a), a.created_at, a.id), default=None)


def _already_tied(db: Any, lines: list[Any], artifact_id: str) -> bool:
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    return any(r.derived_from_artifact_id == artifact_id for row in lines for r in readings_of_segment(db, row.id))


def _find_lines(db: Any, doc: Any, photo: Path, job_id: str) -> None:
    """The page has no lines: Kraken finds them (its regions kept as the lines' parents) and they become the
    page's pass at once, through the same save and conversion as a Find Lines run (#5487)."""
    from fichero_server.llm import kraken_runtime
    from fichero_server.maintenance.project_conversion import convert_new_results
    from fichero_server.models import Artifact

    geometry = kraken_runtime.segment_to_geometry(photo)
    if not geometry.boxes:
        return
    db.save(Artifact(document_id=doc.id, source_document_id=doc.id, artifact_type="regions", content="",
                     ocr_geometry=geometry, provider=geometry.provider, model=geometry.model, run_id=job_id))
    convert_new_results(db, doc.id, run_id=job_id)


def _tie(db: Any, job_id: str, request: CheckRunRequest, started_by: str) -> dict[str, Any]:
    import fichero_server.api.routes.check  # noqa: F401  (registers check.verdict)
    import fichero_server.api.routes.document.content_representations  # noqa: F401  (representation.create)
    from PIL import Image

    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.checking.cards import _descendants
    from fichero_server.llm import kraken_runtime
    from fichero_server.llm.working_lines import in_pixels, working_lines

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
        photo = Path(doc.path) if doc.path else None
        found = working_lines(db, doc.id, model=request.pass_model)
        if found is not None and _already_tied(db, found.lines, reading.id):
            counts["already_tied"] += 1
            continue
        if photo is None or not photo.is_file():
            missing.append({"document_id": doc.id, "why": "its photograph is not on this Mac"})
            continue
        if found is None and request.pass_model is None:
            _find_lines(db, doc, photo, job_id)
            found = working_lines(db, doc.id)
            counts["lines_found"] += found is not None
        if found is None:
            counts["no_lines"] += 1
            continue
        with Image.open(photo) as image:
            width, height = float(image.width), float(image.height)
        lines = [in_pixels(row, width, height) for row in found.lines]
        reads = kraken_runtime.read_given_lines(photo, model_path, lines)
        for row, scored in zip(found.lines, tie_lines(reading.content, reads)):
            if not scored["text"]:
                counts["untied"] += 1
                continue
            made = registry.invoke(db, "representation.create", {
                "document_id": doc.id, "segment_id": row.id, "kind": request.kind, "content": scored["text"],
                "derived_from_artifact_id": reading.id}, ctx).result
            if scored["tied"]:
                counts["tied"] += 1
                continue
            reasons = (f"{DOUBTFUL}: agrees {scored['score']:.2f} with Kraken's rough read of the line, "
                       f"below {THRESHOLD:.2f} (rough read: {scored['rough_read']!r})")
            registry.invoke(db, "check.verdict", {
                "layer": "readings", "target_id": made["id"], "verdict": "reject", "reasons": reasons,
                "checker_model": request.model, "segment_id": row.id}, ctx)
            counts["doubtful"] += 1
            flagged.append({"document_id": doc.id, "segment_id": row.id, "reading_id": made["id"],
                            "flag": DOUBTFUL, "score": scored["score"]})
        counts["pages_tied"] += 1
    return {"counts": counts, "flagged": flagged, "missing": missing, "stopped": stopped,
            "thresholds": {"tie": THRESHOLD, "policy": "accent-blind"}}


def words(counts: dict[str, int]) -> str:
    return (f"{counts['tied']} lines tied, {counts['doubtful']} doubtful, {counts['untied']} untied, on "
            f"{counts['pages_tied']} pages; {counts['already_tied']} already tied")


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
