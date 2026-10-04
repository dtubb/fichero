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
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST = "manifest.json"
FORMAT = "fichero-kraken-training-set-v1"


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

    @property
    def lines(self) -> int:
        return sum(p.lines for p in self.pages)

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


def export_training_set(db: Any, *, scope_ids: list[str], teacher: str, held_out_ids: list[str],
                        out_dir: str | Path) -> TrainingSet:
    """Write the set under `out_dir` (PAGE XML and photographs side by side, and the manifest)."""
    from fichero_server.page_export import ExportRefused, export_page

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    held = set(held_out_ids)
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
        content = exported.data.decode("utf-8")
        lines = read_lines(content)
        source = Path(page.path)
        if lines == 0 or not source.is_file():
            why = "its teacher pass has no read lines" if lines == 0 else "its photograph is not on this Mac"
            result.missing.append({"document_id": page.id, "name": page.name, "why": why})
            continue
        image_name = PurePosixPath(page.path).name
        stem = Path(image_name).stem
        (out / f"{stem}.xml").write_text(content, encoding="utf-8")
        shutil.copy2(source, out / image_name)
        result.pages.append(SetPage(document_id=page.id, name=page.name, xml=f"{stem}.xml",
                                    image=image_name, pass_id=chosen.id, lines=lines))
    (out / MANIFEST).write_text(json.dumps(result.manifest(), indent=1), encoding="utf-8")
    if not result.pages:
        raise EmptyTrainingSet(
            f"no page in scope has a pass read by {teacher} with read lines "
            f"({len(result.missing)} missing, {len(result.held_out)} held out)")
    return result
