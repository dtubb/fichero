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

MANIFEST = "manifest.json"
FORMAT = "fichero-kraken-training-set-v1"
#: Why a line is left out of a set, in the order they are tested (`compute.tune.set-excludes-flagged-lines`).
FLAGS = ("empty", "null", "rejected")


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

    @property
    def lines(self) -> int:
        return sum(p.lines for p in self.pages)

    def left_out(self) -> dict[str, int]:
        counts = Counter(line["flag"] for line in self.left_out_lines)
        return {flag: counts[flag] for flag in FLAGS}

    def summary(self) -> dict[str, Any]:
        """The set in numbers, without its page list: what a job's card and a preview carry."""
        return {k: v for k, v in self.manifest().items() if k != "pages"} | {"pages": len(self.pages)}

    def manifest(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "teacher": self.teacher,
            "pages": [asdict(p) for p in self.pages],
            "held_out": self.held_out,
            "missing": self.missing,
            "lines": self.lines,
            # Every line here was read by the teacher, none checked by a person.
            "lines_read_by_a_model": self.lines,
            "lines_checked_by_a_person": 0,
            "lines_left_out": len(self.left_out_lines),
            "left_out": self.left_out(),
            "left_out_lines": self.left_out_lines,
            "lines_with_a_verdict": self.lines_with_a_verdict,
            "check_ran": self.lines_with_a_verdict > 0,
            "flags_checked": list(FLAGS),
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
                          key=lambda d: (d.sequence if d.sequence is not None else 1 << 30, d.name or ""))
        if getattr(doc, "path", None) and getattr(doc.doc_type, "value", doc.doc_type) in ("file", "page"):
            pages.append(doc)
        for child in children:
            visit(child)

    for doc_id in scope_ids:
        visit(db.get(Document, doc_id))
    return pages


def teacher_pass(db: Any, document_id: str, teacher: str) -> Any | None:
    """The newest live pass on the page whose readings the teacher made, or None."""
    from fichero_server.models.segments import SegmentPass

    passes = [p for p in db.query(SegmentPass, document_id=document_id)
              if p.model == teacher and not p.deleted_at]
    return max(passes, key=lambda p: p.created_at) if passes else None


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


def line_flag(text: str, rejected: bool) -> str | None:
    """Why this line stays out of a training set, or None when it may teach."""
    words = text.strip()
    if not words:
        return "empty"
    if words.casefold() == "null":
        return "null"
    return "rejected" if rejected else None


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


def drop_flagged_lines(page_xml: str, rejected: set[str]) -> tuple[str, list[tuple[str, str]]]:
    """The PAGE file without its flagged TextLines, and (PAGE id, flag) for each line taken out. A file
    with nothing flagged comes back exactly as it was."""
    from fichero_server.formats.pagexml import PAGE_NS_2019
    from fichero_server.formats.validation import parse

    ns = f"{{{PAGE_NS_2019}}}"
    root = parse(page_xml.encode("utf-8"))
    dropped: list[tuple[str, str]] = []
    for line in list(root.iter(f"{ns}TextLine")):
        line_id = line.get("id") or ""
        text = "".join(u.text or "" for u in line.iter(f"{ns}Unicode"))
        flag = line_flag(text, line_id in rejected)
        if flag:
            line.getparent().remove(line)
            dropped.append((line_id, flag))
    if not dropped:
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
        chosen = teacher_pass(db, page.id, teacher)
        if chosen is None:
            result.missing.append({"document_id": page.id, "name": page.name,
                                   "why": f"no pass read by {teacher}"})
            continue
        try:
            exported = export_page(db, page.id, "pagexml", pass_id=chosen.id)
        except ExportRefused as exc:
            result.missing.append({"document_id": page.id, "name": page.name, "why": str(exc)})
            continue
        segments, rejected, with_verdict = lines_of_pass(db, chosen.id, verdicts)
        result.lines_with_a_verdict += with_verdict
        content, dropped = drop_flagged_lines(exported.data.decode("utf-8"), rejected)
        result.left_out_lines.extend({"document_id": page.id, "segment_id": segments.get(line_id, line_id),
                                      "flag": flag} for line_id, flag in dropped)
        lines = read_lines(content)
        source = Path(page.path)
        if lines == 0 or not source.is_file():
            if lines:
                why = "its photograph is not on this Mac"
            elif dropped:
                why = "every line of its teacher pass was flagged"
            else:
                why = "its teacher pass has no read lines"
            result.missing.append({"document_id": page.id, "name": page.name, "why": why})
            continue
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


def export_training_set(db: Any, *, scope_ids: list[str], teacher: str, held_out_ids: list[str],
                        out_dir: str | Path) -> TrainingSet:
    """Write the set under `out_dir`; refused when no page has a line to teach."""
    result = build_training_set(db, scope_ids=scope_ids, teacher=teacher, held_out_ids=held_out_ids, out_dir=out_dir)
    if not result.pages:
        raise EmptyTrainingSet(
            f"no page in scope has a pass read by {teacher} with read lines "
            f"({len(result.missing)} missing, {len(result.held_out)} held out)")
    return result
