"""Scoring one reading of a page against another (#5389).

`transcription_accuracy.character_error_rate` (#3905) is the one CER in Fichero, with its definition
and normalisation policies. This route lets any surface reach it: a pass against a pass, a pass
against a run's transcription, either way round. Read-only.

Agreement is not accuracy: with no checked reference, the number says how far two readings differ,
not which is right. So the answer is labelled `agreement` unless the caller names who checked the
reference (`reference_checked_by`), and only then `cer`. A gold text with no attribution is an
anonymous opinion (the same rule `ReferenceTranscription` keeps).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from fichero_server.api.main import get_library_database
from fichero_server.db import Database
from fichero_server.models import Artifact, Document
from fichero_server.workflows.run_comparison import RunComparisonError
from fichero_server.workflows.transcription_accuracy import (
    DEFAULT_POLICY_NAME,
    POLICIES,
    character_error_rate,
)

router = APIRouter(prefix="/documents")


class ReadingRef(BaseModel):
    """One reading of the page: a pass, or a saved result (artifact)."""

    pass_id: Optional[str] = None
    artifact_id: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "ReadingRef":
        if bool(self.pass_id) == bool(self.artifact_id):
            raise ValueError("name exactly one of pass_id or artifact_id")
        return self


class CompareReadingsRequest(BaseModel):
    reference: ReadingRef
    hypothesis: ReadingRef
    policies: list[str] = Field(default_factory=lambda: [DEFAULT_POLICY_NAME],
                                description=f"normalisation policies: {', '.join(sorted(POLICIES))}")
    reference_checked_by: Optional[str] = Field(
        default=None, description="who checked the reference; without it the score is agreement, not CER")


class ReadingScore(BaseModel):
    policy: str
    policy_description: str
    distance: int
    reference_chars: int
    hypothesis_chars: int
    rate: float


class CompareReadingsResponse(BaseModel):
    measure: Literal["agreement", "cer"]
    reference_label: str
    hypothesis_label: str
    definition: str
    scores: list[ReadingScore]


def _reading(db: Database, document_id: str, ref: ReadingRef) -> tuple[str, str]:
    """(text, label) of one reading; 404 when it is not this page's."""
    if ref.pass_id:
        from fichero_server.api.routes.document.segment_readings import document_text
        from fichero_server.models import SegmentPass

        p = db.get(SegmentPass, ref.pass_id)
        if p is None or p.document_id != document_id:
            raise HTTPException(status_code=404, detail=f"pass {ref.pass_id} is not on this page")
        label = " / ".join(x for x in (p.name, p.provider, p.model) if x)
        return document_text(db, document_id, pass_id=p.id).text, f"pass: {label}"
    a = db.get(Artifact, ref.artifact_id)
    if a is None or a.document_id != document_id:
        raise HTTPException(status_code=404, detail=f"result {ref.artifact_id} is not on this page")
    return a.content or "", f"result: {' / '.join(x for x in (a.artifact_type, a.provider, a.model) if x)}"


@router.post("/{document_id}/readings/compare", response_model=CompareReadingsResponse)
async def compare_readings(
    document_id: str,
    request: CompareReadingsRequest,
    db: Database = Depends(get_library_database),
) -> CompareReadingsResponse:
    """How far one reading of this page is from another, by Fichero's CER definition, under each
    normalisation policy asked for. Labelled `agreement` unless `reference_checked_by` names who
    checked the reference. Refuses (422) rather than returning a number it cannot stand behind:
    an empty reference, an unknown policy, a text too long for an exact score."""
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail=f"document {document_id} not found")
    ref_text, ref_label = _reading(db, document_id, request.reference)
    hyp_text, hyp_label = _reading(db, document_id, request.hypothesis)
    try:
        scores = [character_error_rate(ref_text, hyp_text, policy=p) for p in request.policies]
    except RunComparisonError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    checked = bool(request.reference_checked_by and request.reference_checked_by.strip())
    return CompareReadingsResponse(
        measure="cer" if checked else "agreement",
        reference_label=ref_label + (f" (checked by {request.reference_checked_by.strip()})" if checked else ""),
        hypothesis_label=hyp_label,
        definition=scores[0].definition,
        scores=[ReadingScore(policy=s.policy, policy_description=s.policy_description, distance=s.distance,
                             reference_chars=s.reference_chars, hypothesis_chars=s.hypothesis_chars, rate=s.cer)
                for s in scores],
    )


# =============================================================================
# Where the readers disagree (#5665): the same comparison, from two readings to N, line by line, word by word.
# `source.disagree.route`, `.normalised-first`, `.medoid-aligned`, `.agreement-not-accuracy` in
# docs/contributor_manual/specs/source/readings-and-apparatus.md.
# =============================================================================

#: The convention readers are compared at (`source.disagree.normalised-first`).
DISAGREEMENT_POLICY = "catmus-as-written"
#: A reading made from a line's own words, not a reader's reading of the line.
_DERIVED_TOOLS = frozenset({"line-from-its-words"})
#: The levels a reading as written may carry: unset (a reader that says nothing reads as written) or as written.
_AS_WRITTEN_LEVELS = frozenset({None, "", "as_written", "as-written"})


class DisagreementReader(BaseModel):
    id: str = Field(description="stable for the page: the reader and its run")
    label: str = Field(description="in words: the model, and which run when one model was sampled several times")


class DisagreementVariant(BaseModel):
    text: str = Field(description="an aligned word, normalised; \"\" where a reader gave nothing there")
    readers: list[str] = Field(description="the ids of the readers that gave it")


class DisagreementWord(BaseModel):
    text: str
    char_start: int = Field(description="index into the line's `text`")
    char_end: int
    bbox: Optional[list[float]] = Field(default=None, description=(
        "[x, y, width, height] in the page image's pixels when the reference reading places the word; else null"))
    agreement: float = Field(description="the share of the line's readers whose aligned word is exactly this (0-1)")
    variants: list[DisagreementVariant] = Field(description="every distinct aligned word, most readers first")


class DisagreementLine(BaseModel):
    segment_id: str
    reference_reader: str = Field(description="the medoid reading's reader id")
    text: str = Field(description="the reference reading, normalised")
    agreement: float = Field(description="the mean of its words' agreement")
    words: list[DisagreementWord]


class DisagreementResponse(BaseModel):
    """Where a page's readers disagree: agreement between readers, never accuracy (no reading is checked)."""

    page_id: str
    readers: list[DisagreementReader]
    page_agreement: Optional[float] = Field(description="the mean over the page's words; null with no words")
    normalised_as: str = Field(description="the convention the readings were compared at")
    image_width: Optional[int] = Field(default=None, description="pixel width of the image the bboxes are in")
    image_height: Optional[int] = Field(default=None, description="pixel height of the image the bboxes are in")
    lines: list[DisagreementLine]


def _align(ref: str, hyp: str) -> list[tuple[Optional[int], Optional[int]]]:
    """One least-cost character alignment of `hyp` to `ref` (Levenshtein, unit costs): each step is
    (ref index, hyp index), None for an insertion or a deletion. Lines are short: an exact table."""
    n, m = len(ref), len(hyp)
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        row, above = cost[i], cost[i - 1]
        for j in range(1, m + 1):
            row[j] = min(above[j - 1] + (ref[i - 1] != hyp[j - 1]), above[j] + 1, row[j - 1] + 1)
    steps: list[tuple[Optional[int], Optional[int]]] = []
    i, j = n, m
    while i or j:
        if i and j and cost[i][j] == cost[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            steps.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and cost[i][j] == cost[i - 1][j] + 1:
            steps.append((i - 1, None))
            i -= 1
        else:
            steps.append((None, j - 1))
            j -= 1
    steps.reverse()
    return steps


def _words(text: str) -> list[tuple[int, int]]:
    import re

    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def aligned_words(ref: str, hyp: str, spans: list[tuple[int, int]]) -> list[str]:
    """The hypothesis's word against each reference word (`spans`), read off the character alignment: the
    hypothesis characters aligned to the word's characters, and those inserted inside it. "" where nothing
    aligned (the reader left the word out)."""
    word_of: list[Optional[int]] = [None] * len(ref)
    for index, (start, end) in enumerate(spans):
        for k in range(start, end):
            word_of[k] = index
    buckets: list[list[str]] = [[] for _ in spans]
    steps = _align(ref, hyp)
    last_ref: Optional[int] = None
    for position, (r, h) in enumerate(steps):
        if r is not None:
            last_ref = r
            if h is not None and word_of[r] is not None:
                buckets[word_of[r]].append(hyp[h])
            continue
        ch = hyp[h]
        before = word_of[last_ref] if last_ref is not None else None
        after = next((word_of[r2] for r2, _h in steps[position + 1:] if r2 is not None), None)
        if before is not None and before == after:
            buckets[before].append(ch)  # inside a word: a space here splits it, and it then differs
        elif not ch.isspace() and before is not None:
            buckets[before].append(ch)
        elif not ch.isspace() and after is not None:
            buckets[after].append(ch)
    return ["".join(b).strip() for b in buckets]


def medoid(texts: list[str]) -> int:
    """The index of the reading with the least summed edit distance to the others (the first, on a tie)."""
    from fichero_server.llm.multilingual import levenshtein_distance

    sums = [sum(levenshtein_distance(a, b) for b in texts) for a in texts]
    return sums.index(min(sums))


def line_disagreement(readings: list[tuple[str, str]]) -> Optional[dict]:
    """One line's disagreement from its readings, each (reader id, normalised text), in reader order: the medoid
    the reference, each word's agreement and variants. None for fewer than two readings or no words."""
    if len(readings) < 2:
        return None
    texts = [t for _r, t in readings]
    ref_index = medoid(texts)
    ref_reader, ref = readings[ref_index]
    spans = _words(ref)
    if not spans:
        return None
    per_reader = {reader: (aligned_words(ref, text, spans) if i != ref_index else [ref[s:e] for s, e in spans])
                  for i, (reader, text) in enumerate(readings)}
    words = []
    for k, (start, end) in enumerate(spans):
        word = ref[start:end]
        variants: dict[str, list[str]] = {}
        for reader, _text in readings:
            variants.setdefault(per_reader[reader][k], []).append(reader)
        ordered = sorted(variants.items(), key=lambda kv: -len(kv[1]))  # stable: the first given first on a tie
        words.append({"text": word, "char_start": start, "char_end": end,
                      "agreement": len(variants.get(word, [])) / len(readings),
                      "variants": [{"text": t, "readers": r} for t, r in ordered]})
    return {"reference_reader": ref_reader, "text": ref, "words": words,
            "agreement": sum(w["agreement"] for w in words) / len(words)}


def _reader_of(row, artifacts: dict) -> tuple[str, str]:
    """(model, run) a reading was made by: its page artifact's model, else what the row says; the run it was made
    under, else its artifact (one reading set per artifact)."""
    artifact = artifacts.get(row.derived_from_artifact_id) if row.derived_from_artifact_id else None
    model = (getattr(artifact, "model", None) or row.producer_model or getattr(artifact, "provider", None)
             or row.producer_tool or "a reader")
    run = row.producer_run_id or row.derived_from_artifact_id or row.id
    return str(model), str(run)


def _model_label(model: str) -> str:
    try:
        from fichero_server.llm.mlx_model_store import get_mlx_model_store

        store = get_mlx_model_store()
        model_id = store.canonical_id(model.removeprefix("omlx/"))
        if model_id is not None:
            return store.spec(model_id).display_name
    except Exception:  # noqa: BLE001 -- a name is never worth failing the comparison for
        pass
    return model


def _image_size(db: Database, document: Document) -> tuple[Optional[int], Optional[int]]:
    """The page image's pixel size: as the page records it, else read from its image file; (None, None) unknown."""
    metadata = document.metadata or {}
    w, h = metadata.get("width"), metadata.get("height")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
        return int(w), int(h)
    if not document.path:
        return None, None
    from pathlib import Path

    path = Path(document.path)
    if not path.is_absolute():
        path = Path(db.path).parent / path
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:  # noqa: BLE001 -- not an image, or not here: the size is unknown, never guessed
        return None, None


def _placed_words(by_segment: dict, words: list, count: int, width: Optional[int],
                  height: Optional[int]) -> Optional[list[list[float]]]:
    """Each reference word's box in pixels, where the reference reader read the line's word segments one for one
    (as many words read as the reference has); else None: a word the reading does not place has no box."""
    if not width or not height or not count:
        return None
    read = sorted((w for w in words if w.id in by_segment), key=lambda w: (w.bbox_y, w.bbox_x))
    if len(read) != count:
        return None
    return [[w.bbox_x * width, w.bbox_y * height, w.bbox_w * width, w.bbox_h * height] for w in read]


def page_disagreement(db: Database, page_id: str) -> DisagreementResponse:
    """`GET /api/documents/{page_id}/disagreement`'s answer (`source.disagree.route`). LookupError: no such page."""
    from fichero_server.api.routes.document.segment_readings import is_unconverted_pass, ordered_lines, working_pass
    from fichero_server.models import ContentRepresentation
    from fichero_server.models.segments import Segment
    from fichero_server.workflows.transcription_accuracy import normalize

    document = db.get(Document, page_id)
    if document is None:
        raise LookupError(f"document {page_id} not found")
    policy = POLICIES[DISAGREEMENT_POLICY]
    width, height = _image_size(db, document)
    empty = DisagreementResponse(page_id=page_id, readers=[], page_agreement=None, normalised_as=policy.name,
                                 image_width=width, image_height=height, lines=[])
    answer = working_pass(db, page_id)
    if answer.pass_id is None or is_unconverted_pass(answer.pass_id):
        return empty
    lines = ordered_lines(db, answer.pass_id)
    line_ids = {line.id for line in lines}
    words_of: dict[str, list[Segment]] = {}
    for row in db.query(Segment, pass_id=answer.pass_id):
        if row.kind == "word" and row.deleted_at is None and row.parent_segment_id in line_ids:
            words_of.setdefault(row.parent_segment_id, []).append(row)
    # A person's reading is a correction, not a reader: it is not compared (it settles the disagreement).
    rows = [r for r in db.query(ContentRepresentation, document_id=page_id)
            if r.kind == "transcription" and r.level in _AS_WRITTEN_LEVELS and r.segment_id
            and r.producer_tool not in _DERIVED_TOOLS
            and getattr(r.provenance_kind, "value", r.provenance_kind) != "human"]
    artifact_ids = sorted({r.derived_from_artifact_id for r in rows if r.derived_from_artifact_id})
    artifacts = {a.id: a for a in db.query_in(Artifact, "id", artifact_ids)} if artifact_ids else {}
    # Each reader (a model and its run) in the order first met, with its newest reading of each segment.
    readers: dict[tuple[str, str], str] = {}
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: (r.created_at, r.id)):
        key = _reader_of(row, artifacts)
        readers.setdefault(key, f"{key[0]}#{key[1]}")
        newest.setdefault(key, {})[row.segment_id] = row
    on_lines = [key for key in readers if line_ids & set(newest[key])]
    runs_of: dict[str, list[str]] = {}
    for model, run in on_lines:
        runs_of.setdefault(model, []).append(run)
    labels = {key: _model_label(key[0]) + (f", run {runs_of[key[0]].index(key[1]) + 1}"
                                           if len(runs_of[key[0]]) > 1 else "") for key in on_lines}
    listed = [DisagreementReader(id=readers[k], label=labels[k]) for k in on_lines]
    if len(on_lines) < 2:
        return empty.model_copy(update={"readers": listed})
    out_lines: list[DisagreementLine] = []
    every_word: list[float] = []
    for line in lines:
        given = [(readers[key], normalize(newest[key][line.id].content, policy))
                 for key in on_lines if line.id in newest[key]]
        found = line_disagreement(given)
        if found is None:
            continue
        ref_key = next(k for k in on_lines if readers[k] == found["reference_reader"])
        placed = _placed_words(newest[ref_key], words_of.get(line.id) or [], len(found["words"]), width, height)
        words = [DisagreementWord(**w, bbox=placed[i] if placed else None) for i, w in enumerate(found["words"])]
        every_word += [w.agreement for w in words]
        out_lines.append(DisagreementLine(segment_id=line.id, reference_reader=found["reference_reader"],
                                          text=found["text"], agreement=found["agreement"], words=words))
    return DisagreementResponse(
        page_id=page_id, readers=listed, normalised_as=policy.name, image_width=width, image_height=height,
        page_agreement=(sum(every_word) / len(every_word)) if every_word else None, lines=out_lines)


@router.get("/{page_id}/disagreement", response_model=DisagreementResponse)
async def get_page_disagreement(page_id: str, db: Database = Depends(get_library_database)) -> DisagreementResponse:
    """Where this page's readers disagree, line by line and word by word (`source.disagree.route`, #5665). Every
    reading of a line (each reader, or each sampled run of one) is brought to the line as written (CATMuS); per
    line the medoid reading is the reference, each other reading is aligned to it character by character, and
    each word scores the share of readers that gave exactly it. Agreement, never accuracy. With fewer than two
    readings, 200 with `lines` empty and `page_agreement` null; an unknown page is 404. Read-only."""
    try:
        return page_disagreement(db, page_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
