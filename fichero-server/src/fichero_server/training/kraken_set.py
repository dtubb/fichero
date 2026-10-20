"""A Kraken training set made from a project's pages: PAGE XML beside each photograph (#5398).

`compute.tune.input-is-a-training-set`: the only data a Kraken training job takes. For every page in
scope, the newest pass whose lines were read by the TEACHER (a model id, e.g. Gemini reading the lines
Kraken found: `lines_read_by: model`) is written with Fichero's own PAGE XML writer (`page_export`,
the same file `GET /documents/{id}/export/pagexml` returns), and the page's photograph is copied
beside it under the name the PAGE file gives it, which is how `ketos train -f page` finds it.

Held-out pages are named by the caller and never written: they are the test (the Sergio project's
ten Fable-checked C01 pages). A page with no teacher pass, or one whose pass has no read lines, is
listed as missing with the reason, never silently skipped.

The manifest (`manifest.json`) names pages by file name and document id only: no path from this Mac
crosses (`compute.package.no-paths-cross`), no key or token (`compute.package.no-secrets`). It counts
how many lines a model wrote and how many a person checked (`compute.tune.bootstrapped-data-is-marked`):
a set made by a teacher is never mistaken for one a person checked.

Flagged lines are left out (`compute.tune.set-excludes-flagged-lines`, #5446): a line whose reading is
empty or the word `null` (a model's "no writing" kept as text, #5447), and a line whose newest check
verdict (`check.verdict`, by a person or a checker model such as Fable) rejects it. The manifest counts
what was left out, by flag, names each line, and says whether the check had run on the set's lines at
all. The reading check's own flags (a reading closer to a neighbour's line, one below the set score)
are not built yet; `flags_checked` names the flags this set was checked for.
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from fichero_server.core.naturalsort import in_folder_order
from fichero_server.db.storage import resolve_source

MANIFEST = "manifest.json"
FORMAT = "fichero-kraken-training-set-v1"
#: Why a line is left out of a set, in the order they are tested (`compute.tune.set-excludes-flagged-lines`).
FLAGS = ("empty", "null", "rejected")
#: The one flag a person's set adds (`PERSON`): a line whose counting reading no person made.
PERSON_FLAGS = (*FLAGS, "not_by_a_person")
#: The teacher that means "the person": the lessons are the lines whose counting reading a person made (a correction,
#: `source.reading.correct-a-line`) or chose among machine readings (`reading.choose`,
#: `source.compare.pick-is-a-training-line`), not a model's readings (#5700). Any other value is a model id.
PERSON = "person"


@dataclass
class SetPage:
    document_id: str
    name: str
    xml: str
    image: str
    pass_id: str
    lines: int


@dataclass
class TrainingSet:
    teacher: str
    pages: list[SetPage] = field(default_factory=list)
    held_out: list[dict[str, str]] = field(default_factory=list)
    missing: list[dict[str, str]] = field(default_factory=list)
    #: Each line left out: its page, its segment and its flag.
    left_out_lines: list[dict[str, str]] = field(default_factory=list)
    #: Lines in scope with a check verdict on their reading; 0 means the check had not run on them.
    lines_with_a_verdict: int = 0
    #: The person's set: kept lines a person typed and kept lines a person chose, counted apart.
    lines_typed: int = 0
    lines_chosen: int = 0
    #: `training.line_key` of every kept line of the person's set, so a bake-off's staging can drop the same lines.
    line_keys: set[str] = field(default_factory=set)

    @property
    def lines(self) -> int:
        return sum(p.lines for p in self.pages)

    def left_out(self) -> dict[str, int]:
        counts = Counter(line["flag"] for line in self.left_out_lines)
        return {flag: counts[flag] for flag in self.flags()}

    def flags(self) -> tuple[str, ...]:
        return PERSON_FLAGS if self.teacher == PERSON else FLAGS

    def summary(self) -> dict[str, Any]:
        """The set in numbers, without its page list: what a job's card and a preview carry."""
        return {k: v for k, v in self.manifest().items() if k != "pages"} | {"pages": len(self.pages)}

    def why_empty(self) -> str:
        """Why a set with no page cannot teach, from the preview's own whys (#5699): the start's refusal and the
        job's say what the preview said."""
        whys = Counter(m["why"] for m in self.missing)
        said = "; ".join(f"{n} page{'s' if n != 1 else ''}: {why}" for why, n in whys.most_common())
        held = f"; {len(self.held_out)} held out" if self.held_out else ""
        if not said:
            return f"nothing to train on: no page in scope{held}"
        # The whys first: an opening that named the pass sent a photograph's absence looking like a scope fault
        # (#5710).
        count = len(self.missing)
        return f"nothing to train on: none of the {count} page{'s' if count != 1 else ''} in scope can teach: {said}{held}"

    def manifest(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "teacher": self.teacher,
            "pages": [asdict(p) for p in self.pages],
            "held_out": self.held_out,
            "missing": self.missing,
            "lines": self.lines,
            # A model's teacher set: every line was read by the teacher, none checked by a person. The person's
            # set (`PERSON`): every line is one a person made.
            "lines_read_by_a_model": 0 if self.teacher == PERSON else self.lines,
            "lines_checked_by_a_person": self.lines if self.teacher == PERSON else 0,
            "lines_typed_by_a_person": self.lines_typed,
            "lines_chosen_by_a_person": self.lines_chosen,
            "lines_left_out": len(self.left_out_lines),
            "left_out": self.left_out(),
            "left_out_lines": self.left_out_lines,
            "lines_with_a_verdict": self.lines_with_a_verdict,
            "check_ran": self.lines_with_a_verdict > 0,
            "flags_checked": list(self.flags()),
        }


class EmptyTrainingSet(ValueError):
    """Nothing in scope had a teacher pass with read lines: there is nothing to train on."""


def pages_in_scope(db: Any, scope_ids: list[str]) -> list[Any]:
    """The pages under the named documents and folders, depth first, in their stored order: every
    document that is a file with a path (a folder contributes its descendants, not itself)."""
    from fichero_server.models import Document

    seen: set[str] = set()
    pages: list[Any] = []

    def visit(doc: Any) -> None:
        if doc is None or doc.id in seen or getattr(doc, "deleted_at", None):
            return
        seen.add(doc.id)
        children = sorted(db.query(Document, parent_id=doc.id),
                          key=in_folder_order)  # the one shared order (#5693)
        if getattr(doc, "path", None) and getattr(doc.doc_type, "value", doc.doc_type) in ("file", "page"):
            pages.append(doc)
        for child in children:
            visit(child)

    for doc_id in scope_ids:
        visit(db.get(Document, doc_id))
    return pages


def teacher_pass(db: Any, document_id: str, teacher: str) -> Any | None:
    """The newest live pass on the page whose readings the teacher made, or None: a pass the teacher made,
    or the page's own lines carrying the teacher's readings (one line pass per page, read many times, #5487:
    a reader, or the page text tied to the lines, #5444, writes readings onto the lines the page has, derived
    from the reader's page artifact, instead of a pass of its own)."""
    from fichero_server.models import Artifact, ContentRepresentation, Segment
    from fichero_server.models.segments import SegmentPass

    passes = {p.id: p for p in db.query(SegmentPass, document_id=document_id) if not p.deleted_at}
    chosen = {pid for pid, p in passes.items() if p.model == teacher}
    by_teacher = {a.id for a in db.query(Artifact, document_id=document_id) if a.model == teacher}
    if by_teacher:
        for reading in db.query(ContentRepresentation, document_id=document_id):
            if reading.segment_id and reading.retracted_at is None and reading.derived_from_artifact_id in by_teacher:
                segment = db.get(Segment, reading.segment_id)
                if segment is not None and segment.pass_id in passes:
                    chosen.add(segment.pass_id)
    return max((passes[pid] for pid in chosen), key=lambda p: p.created_at, default=None)


def line_makers(db: Any, pass_row: Any) -> dict[str, str | None]:
    """For each line of the pass, by its PAGE id, who made the reading that counts: "typed" (a person made it, a
    correction), "chosen" (a person chose it among machine readings, `reading.choose`), or None (no person: a model's
    reading nobody picked). A pass a person made or vouched for (`made_by_a_person`) is all typed. One batched lookup
    for the whole pass, not a query per line."""
    from fichero_server.api.routes.document.segment_readings import counting_readings
    from fichero_server.formats.harness import xml_id
    from fichero_server.models import Segment
    from fichero_server.models.readings import ReadingChoice
    from fichero_server.models.segments import made_by_a_person

    lines = [s for s in db.query(Segment, pass_id=pass_row.id) if s.kind == "line" and not s.deleted_at]
    if made_by_a_person(pass_row):
        return {xml_id(line.id): "typed" for line in lines}
    counted = counting_readings(db, lines)
    chosen = {c.representation_id for c in db.query_in(ReadingChoice, "segment_id", [line.id for line in lines])
              if c.superseded_at is None} if lines else set()
    makers: dict[str, str | None] = {}
    for line in lines:
        reading = counted.get(line.id)
        if reading is None:
            makers[xml_id(line.id)] = None
        elif reading.provenance_kind.value == "human":
            makers[xml_id(line.id)] = "typed"
        else:
            makers[xml_id(line.id)] = "chosen" if reading.id in chosen else None
    return makers


def lines_not_by_a_person(db: Any, pass_row: Any) -> set[str]:
    """The PAGE ids of the pass's lines whose counting transcription no person made or chose."""
    return {line_id for line_id, who in line_makers(db, pass_row).items() if who is None}


def person_pass(db: Any, document_id: str) -> tuple[Any, set[str]] | None:
    """The newest live line pass on the page with at least one line a person made, and the PAGE ids of its lines a
    person did not make; None when no pass has one. Each pass is looked at once."""
    from fichero_server.models import Segment
    from fichero_server.models.segments import SegmentPass

    for candidate in sorted((p for p in db.query(SegmentPass, document_id=document_id) if not p.deleted_at),
                            key=lambda p: p.created_at, reverse=True):
        total = sum(1 for s in db.query(Segment, pass_id=candidate.id) if s.kind == "line" and not s.deleted_at)
        others = lines_not_by_a_person(db, candidate)
        if total and len(others) < total:
            return candidate, others
    return None


def read_lines(page_xml: str) -> int:
    """TextLines with a baseline and some text: what `ketos train -f page` can learn from."""
    # Imported here: the training route imports this module at app start, and the format modules and
    # the XML parser load on first use (#3950, `test_lazy_engine_imports`).
    from fichero_server.formats.pagexml import PAGE_NS_2019
    from fichero_server.security.xml_security import parse_xml_string

    _PAGE_NS = f"{{{PAGE_NS_2019}}}"
    root = parse_xml_string(page_xml)
    count = 0
    for line in root.iter(f"{_PAGE_NS}TextLine"):
        text = "".join(u.text or "" for u in line.iter(f"{_PAGE_NS}Unicode"))
        if line.find(f"{_PAGE_NS}Baseline") is not None and text.strip():
            count += 1
    return count


def line_flag(text: str, rejected: bool, not_by_a_person: bool = False) -> str | None:
    """Why this line stays out of a training set, or None when it may teach."""
    words = text.strip()
    if not words:
        return "empty"
    if words.casefold() == "null":
        return "null"
    if rejected:
        return "rejected"
    return "not_by_a_person" if not_by_a_person else None


def newest_reading_verdicts(db: Any) -> dict[str, Any]:
    """The newest check verdict on each reading, by the reading's id."""
    from fichero_server.models.checking import CheckVerdict

    newest: dict[str, Any] = {}
    for verdict in sorted(db.query(CheckVerdict, layer="readings"), key=lambda v: (v.created_at, v.id)):
        newest[verdict.target_id] = verdict
    return newest


def lines_of_pass(db: Any, pass_id: str, verdicts: dict[str, Any]) -> tuple[dict[str, str], set[str], int]:
    """The pass's lines by their PAGE id (to their segment id), the PAGE ids of those whose newest
    verdict, over all the line's readings, is a reject, and how many lines carry a verdict at all."""
    from fichero_server.api.routes.document.segment_readings import readings_of_segment
    from fichero_server.formats.harness import xml_id
    from fichero_server.models import Segment

    segments = {xml_id(s.id): s.id for s in db.query(Segment, pass_id=pass_id) if s.kind == "line" and not s.deleted_at}
    rejected: set[str] = set()
    with_verdict = 0
    if not verdicts:
        return segments, rejected, 0
    for page_id, segment_id in segments.items():
        on_line = [verdicts[r.id] for r in readings_of_segment(db, segment_id) if r.id in verdicts]
        if not on_line:
            continue
        with_verdict += 1
        if max(on_line, key=lambda v: (v.created_at, v.id)).verdict == "reject":
            rejected.add(page_id)
    return segments, rejected, with_verdict


def drop_flagged_lines(page_xml: str, rejected: set[str], not_by_a_person: set[str] = frozenset()) -> tuple[str, list[tuple[str, str]]]:
    """The PAGE file without its flagged TextLines, and (PAGE id, flag) for each line taken out. A file
    with nothing flagged comes back exactly as it was.

    And with every text AS WRITTEN (#5651, `source.reading.abbreviation-markup-parsed`): a corpus's
    abbreviation markup (`dha$.dicha`, `$ant:`, `$-`) is not ink, so a reader trained on it would learn
    `$` as a letter of the hand. The abbreviation stays as the scribe wrote it (`dha`)."""
    from fichero_server.formats.abbreviation_markup import as_written, has_markup
    from fichero_server.formats.pagexml import PAGE_NS_2019
    from fichero_server.formats.validation import parse

    ns = f"{{{PAGE_NS_2019}}}"
    root = parse(page_xml.encode("utf-8"))
    rewritten = False
    for unicode in root.iter(f"{ns}Unicode"):
        if unicode.text and has_markup(unicode.text):
            unicode.text = as_written(unicode.text)
            rewritten = True
    dropped: list[tuple[str, str]] = []
    for line in list(root.iter(f"{ns}TextLine")):
        line_id = line.get("id") or ""
        text = "".join(u.text or "" for u in line.iter(f"{ns}Unicode"))
        flag = line_flag(text, line_id in rejected, line_id in not_by_a_person)
        if flag:
            line.getparent().remove(line)
            dropped.append((line_id, flag))
    if not dropped and not rewritten:
        return page_xml, dropped
    from lxml import etree

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8"), dropped


def build_training_set(db: Any, *, scope_ids: list[str], teacher: str, held_out_ids: list[str],
                       out_dir: str | Path | None) -> TrainingSet:
    """The set, with its flagged lines left out; written under `out_dir` (PAGE XML and photographs side
    by side, and the manifest), or only counted when `out_dir` is None. One code path for both, so a
    preview counts exactly what a training job sends."""
    from fichero_server.page_export import ExportRefused, export_page

    out = Path(out_dir) if out_dir is not None else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    held = set(held_out_ids)
    verdicts = newest_reading_verdicts(db)
    result = TrainingSet(teacher=teacher)
    for page in pages_in_scope(db, scope_ids):
        if page.id in held:
            result.held_out.append({"document_id": page.id, "name": page.name})
            continue
        not_person: set[str] = set()
        if teacher == PERSON:
            found = person_pass(db, page.id)
            chosen, not_person = found if found else (None, set())
        else:
            chosen = teacher_pass(db, page.id, teacher)
        if chosen is None:
            result.missing.append({"document_id": page.id, "name": page.name,
                                   "why": "no line corrected by a person" if teacher == PERSON
                                   else f"no pass read by {teacher}"})
            continue
        try:
            exported = export_page(db, page.id, "pagexml", pass_id=chosen.id, reading_level="as_written")
        except ExportRefused as exc:
            result.missing.append({"document_id": page.id, "name": page.name, "why": str(exc)})
            continue
        segments, rejected, with_verdict = lines_of_pass(db, chosen.id, verdicts)
        result.lines_with_a_verdict += with_verdict
        content, dropped = drop_flagged_lines(exported.data.decode("utf-8"), rejected, not_person)
        result.left_out_lines.extend({"document_id": page.id, "segment_id": segments.get(line_id, line_id),
                                      "flag": flag} for line_id, flag in dropped)
        lines = read_lines(content)
        # The photograph where it is: a copied page's stored path is inside the package (#5699).
        source = resolve_source(page, library_root=Path(db.path).parent)
        if lines == 0 or source is None or not source.is_file():
            if lines:
                why = "its photograph is not on this Mac"
            elif dropped:
                why = "every line of its teacher pass was flagged"
            else:
                why = "its teacher pass has no read lines"
            result.missing.append({"document_id": page.id, "name": page.name, "why": why})
            continue
        if teacher == PERSON:
            from fichero_server.training.line_key import image_digest, line_key
            from fichero_server.training.line_pairs import lines_with_ids

            makers = line_makers(db, chosen)
            digest = image_digest(source)
            for line_id, polygon, _text in lines_with_ids(content):
                if makers.get(line_id) == "chosen":
                    result.lines_chosen += 1
                else:
                    result.lines_typed += 1
                result.line_keys.add(line_key(digest, polygon))
        image_name = PurePosixPath(page.path).name
        stem = Path(image_name).stem
        if out is not None:
            (out / f"{stem}.xml").write_text(content, encoding="utf-8")
            shutil.copy2(source, out / image_name)
        result.pages.append(SetPage(document_id=page.id, name=page.name, xml=f"{stem}.xml",
                                    image=image_name, pass_id=chosen.id, lines=lines))
    if out is not None:
        (out / MANIFEST).write_text(json.dumps(result.manifest(), indent=1), encoding="utf-8")
    return result


def refuse_an_empty_set(db: Any, request: Any) -> None:
    """Refuse a start whose set would be empty, before it is queued and with the preview's reason (#5699): it was
    queued, then failed a second later with another reason. Counted as the preview counts it, nothing written;
    after a start's cheaper refusals (the yes, the token, the base reader)."""
    made = build_training_set(db, scope_ids=request.scope_ids, teacher=request.teacher,
                              held_out_ids=request.held_out_ids, out_dir=None)
    if not made.pages:
        raise EmptyTrainingSet(made.why_empty())


def export_training_set(db: Any, *, scope_ids: list[str], teacher: str, held_out_ids: list[str],
                        out_dir: str | Path) -> TrainingSet:
    """Write the set under `out_dir`; refused when no page has a line to teach."""
    result = build_training_set(db, scope_ids=scope_ids, teacher=teacher, held_out_ids=held_out_ids, out_dir=out_dir)
    if not result.pages:
        raise EmptyTrainingSet(result.why_empty())
    return result
