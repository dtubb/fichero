"""A try's kept copy and what Start may adopt from it (`wide.try.start-reuses-a-matching-try`, #6127; design approved 2026-11-02).

Slice A: a finished try keeps its scratch copy and a record per page (card, a hash of the step's settings, the page's image signature and the
copy's page id) until it expires, 7 days or the next try of the same stage. The days and the polygon overlap are settings of the project
(`recipe/try-settings.yaml`), not constants. Adoption itself (matching lines, copying readings, Start's first action) builds on this record."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

RECORD = "adoption.json"
DEFAULT_KEEP_DAYS = 7
DEFAULT_MATCH_IOU = 0.9


def settings(library: Path) -> dict[str, float]:
    """`{keep_days, match_iou}` from `recipe/try-settings.yaml`, the approved defaults where it says nothing."""
    import yaml

    path = Path(library) / "recipe" / "try-settings.yaml"
    said = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None
    said = said if isinstance(said, dict) else {}
    days, iou = said.get("keep_days"), said.get("match_iou")
    return {"keep_days": float(days) if isinstance(days, (int, float)) and not isinstance(days, bool) and days >= 0 else DEFAULT_KEEP_DAYS,
            "match_iou": float(iou) if isinstance(iou, (int, float)) and not isinstance(iou, bool) and 0 < iou <= 1 else DEFAULT_MATCH_IOU}


def settings_hash(cards: list[dict[str, Any]]) -> str:
    """The step's settings as one short hash: the cards the try ran, their models and answers, in a fixed order."""
    return hashlib.sha1(json.dumps(cards, sort_keys=True, default=str).encode()).hexdigest()[:16]


def page_record(db: Any, library: Path, page_id: str, copy_page_id: str, *, card_ids: list[str], hash_: str) -> dict[str, Any]:
    """What a try ran on one page: the card ids, the settings hash, the image signature the project's page has now, and the copy's page."""
    from fichero_server.media.current_image import current_page_image
    from fichero_server.models import Document

    doc = db.get(Document, page_id)
    try:
        image = current_page_image(db, doc, library_root=library) if doc is not None else None
        signature = image.signature if image is not None else None
    except Exception:  # noqa: BLE001 -- no signature: the page is never adopted, only run
        signature = None
    return {"page": page_id, "copy_page": copy_page_id, "cards": card_ids, "settings": hash_, "signature": signature}


def keep(scratch: Path, record: dict[str, Any]) -> None:
    """Keep a finished try's scratch copy with its record and the time it was kept."""
    (Path(scratch) / RECORD).write_text(json.dumps({**record, "kept_at": time.time()}), encoding="utf-8")


def kept_copies(samples: Path) -> list[Path]:
    return sorted(p for p in Path(samples).glob("*.fichero") if (p / RECORD).is_file())


def sweep(samples: Path, *, keep_days: float, stage: str | None = None, now: float | None = None) -> list[str]:
    """Delete kept copies that expired, and (with `stage`) every kept copy of that stage, which its next try replaces. Returns the names removed."""
    now = time.time() if now is None else now
    removed = []
    for path in kept_copies(samples):
        try:
            record = json.loads((path / RECORD).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            record = {}
        same_stage = stage is not None and record.get("stage") == stage
        if same_stage or now - float(record.get("kept_at") or 0) > keep_days * 86400:
            shutil.rmtree(path, ignore_errors=True)
            removed.append(path.name)
    return removed


def _box(row: Any) -> tuple[float, float, float, float]:
    return row.bbox_x, row.bbox_y, row.bbox_w, row.bbox_h


def overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection over union of two (x, y, w, h) boxes: 0 when apart, 1 when the same."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w, h = min(ax + aw, bx + bw) - max(ax, bx), min(ay + ah, by + bh) - max(ay, by)
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / (aw * ah + bw * bh - inter)


def match_lines(copy_lines: list[Any], page_lines: list[Any], min_iou: float) -> dict[str, str]:
    """Each copy line to the project line it overlaps most (at least `min_iou`), each project line used once: `{copy id: page id}`."""
    pairs = sorted(((overlap(_box(c), _box(p)), c.id, p.id) for c in copy_lines for p in page_lines), key=lambda t: (-t[0], t[1], t[2]))
    out: dict[str, str] = {}
    taken: set[str] = set()
    for score, copy_id, page_id in pairs:
        if score >= min_iou and copy_id not in out and page_id not in taken:
            out[copy_id] = page_id
            taken.add(page_id)
    return out


def adopt_page(db: Any, scratch_db: Any, rec: dict[str, Any], before: dict[str, list[str]], *, scratch_name: str, run_id: str,
               min_iou: float, library_path: str | None = None) -> dict[str, int]:
    """Adopt one page's readings from the kept copy onto the project's own lines (`wide.try.start-reuses-a-matching-try`): matched lines only,
    the try's artifacts copied (so the reading says which model made it and the done rule counts it), never over a person's reading, and once
    only (a second call finds the copied artifact and does nothing). Lines the try made that the page lacks are not created here.
    Returns `{readings, unmatched, skipped_person, reading_ids}`."""
    from fichero_server.llm.working_lines import write_readings
    from fichero_server.models import Artifact, ContentRepresentation, Segment
    from fichero_server.models.knowledge import ProvenanceKind

    page_id, copy_page = rec["page"], rec["copy_page"]
    done = {(a.data or {}).get("adopted_from") for a in db.query(Artifact, document_id=page_id)}
    live = lambda rows: [r for r in rows if r.kind == "line" and r.deleted_at is None and not r.is_furniture]  # noqa: E731
    page_lines, copy_lines = live(db.query(Segment, document_id=page_id)), live(scratch_db.query(Segment, document_id=copy_page))
    mapping = match_lines(copy_lines, page_lines, min_iou)
    people = {r.segment_id for r in db.query(ContentRepresentation, document_id=page_id)
              if r.segment_id and r.provenance_kind == ProvenanceKind.human and not r.retracted_at}
    old_art, old_rep = set(before.get("Artifact", ())), set(before.get("ContentRepresentation", ()))
    artifacts = {a.id: a for a in scratch_db.query(Artifact, document_id=copy_page) if a.id not in old_art}
    out: dict[str, Any] = {"readings": 0, "unmatched": 0, "skipped_person": 0, "reading_ids": []}
    new_ids: dict[str, str] = {}
    for row in scratch_db.query(ContentRepresentation, document_id=copy_page):
        if row.id in old_rep or row.retracted_at or not row.segment_id or row.derived_from_artifact_id not in artifacts:
            continue
        target = mapping.get(row.segment_id)
        if target is None:
            out["unmatched"] += 1
            continue
        if target in people:
            out["skipped_person"] += 1
            continue
        source = f"{scratch_name}:{row.derived_from_artifact_id}"
        if source in done:
            continue
        if row.derived_from_artifact_id not in new_ids:
            copied = artifacts[row.derived_from_artifact_id].model_copy(update={
                "id": uuid.uuid4().hex, "document_id": page_id,
                "data": {**(artifacts[row.derived_from_artifact_id].data or {}), "adopted_from": source}})
            db.save(copied)
            new_ids[row.derived_from_artifact_id] = copied.id
        made = write_readings(
            db, document_id=page_id, readings=[(target, row.content, row.machine_confidence)], artifact_id=new_ids[row.derived_from_artifact_id],
            run_id=run_id, level=row.level, library_path=library_path)
        out["readings"] += len(made)
        out["reading_ids"] += made
    return out


def adopt_stage(db: Any, stage_id: str, *, run_id: str) -> dict[str, Any]:
    """Start's first action for one stage: adopt from the stage's kept try every page whose image signature and settings are the ones the try ran
    on, and name the others. `{pages, readings, reading_ids, left_to_run: [{page, why}]}`; nothing adopted is `pages: 0` with the reason."""
    from fichero_server.db.manager import db_manager
    from fichero_server.recipes import samples
    from fichero_server.recipes.project import read_project_setup
    from fichero_server.recipes.stages import get_stage

    library = Path(db.path).parent
    out: dict[str, Any] = {"pages": 0, "readings": 0, "reading_ids": [], "left_to_run": []}
    try:
        record = json.loads(samples._result_path(library, stage_id).read_text(encoding="utf-8")).get("adoption")
    except (OSError, ValueError):
        record = None
    scratch = samples._folder(library) / f"{stage_id}.fichero"
    stage = get_stage(stage_id)
    if not record or stage is None or not (scratch / RECORD).is_file():
        return out
    setup = read_project_setup(library)
    now = settings_hash(samples._stage_plan(db, stage, setup, len(record["pages"]))["runs"])
    scratch_db = db_manager.get_database(scratch)
    try:
        for rec in record["pages"]:
            current = page_record(db, library, rec["page"], rec["copy_page"], card_ids=rec["cards"], hash_=now)
            if now != rec["settings"] or not current["signature"] or current["signature"] != rec["signature"]:
                out["left_to_run"].append({"page": rec["page"], "why": "the page or the step's settings changed since the try"})
                continue
            got = adopt_page(db, scratch_db, rec, record.get("before") or {}, scratch_name=stage_id, run_id=run_id,
                             min_iou=settings(library)["match_iou"], library_path=str(library))
            if got["readings"]:
                out["pages"] += 1
                out["readings"] += got["readings"]
                out["reading_ids"] += got["reading_ids"]
    finally:
        db_manager.close_database(scratch)
    return out


def kept_stages(samples_folder: Path) -> list[str]:
    """The stages that have a kept try, in a fixed order."""
    out = []
    for path in kept_copies(samples_folder):
        try:
            out.append(str(json.loads((path / RECORD).read_text(encoding="utf-8")).get("stage")))
        except (OSError, ValueError):
            continue
    return sorted(set(out))


def tries_on_page(db: Any, page_id: str) -> list[dict[str, Any]]:
    """The kept tries that ran on this page, for the Reader and the Inspector (`wide.try.shown-outside-set-up`): each is labelled as a try's
    (`kind: "try"`, never the project's), with the stage, the day it ran, the model, and its readings on the project's matching lines. Read from
    the kept copy only: nothing is written, and the done rule never sees these."""
    from fichero_server.db.manager import db_manager
    from fichero_server.models import Artifact, ContentRepresentation, Segment
    from fichero_server.recipes import samples

    library = Path(db.path).parent
    out: list[dict[str, Any]] = []
    for scratch in kept_copies(samples._folder(library)):
        try:
            kept = json.loads((scratch / RECORD).read_text(encoding="utf-8"))
            stage = str(kept.get("stage"))
            result = json.loads(samples._result_path(library, stage).read_text(encoding="utf-8")).get("adoption") or {}
        except (OSError, ValueError):
            continue
        rec = next((r for r in result.get("pages", []) if r["page"] == page_id), None)
        if rec is None:
            continue
        before = result.get("before") or {}
        scratch_db = db_manager.get_database(scratch)
        try:
            live = lambda rows: [r for r in rows if r.kind == "line" and r.deleted_at is None and not r.is_furniture]  # noqa: E731
            mapping = match_lines(live(scratch_db.query(Segment, document_id=rec["copy_page"])),
                                  live(db.query(Segment, document_id=page_id)), settings(library)["match_iou"])
            old_art, old_rep = set(before.get("Artifact", ())), set(before.get("ContentRepresentation", ()))
            artifacts = {a.id: a for a in scratch_db.query(Artifact, document_id=rec["copy_page"]) if a.id not in old_art}
            readings = [{"line": mapping[r.segment_id], "text": r.content, "artifact": r.derived_from_artifact_id}
                        for r in scratch_db.query(ContentRepresentation, document_id=rec["copy_page"])
                        if r.id not in old_rep and not r.retracted_at and r.segment_id in mapping and r.derived_from_artifact_id in artifacts]
        finally:
            db_manager.close_database(scratch)
        for art_id in sorted({r["artifact"] for r in readings}):
            art = artifacts[art_id]
            out.append({"kind": "try", "stage": stage, "ran_at": kept.get("kept_at"), "model": art.model,
                        "readings": [{"line": r["line"], "text": r["text"]} for r in readings if r["artifact"] == art_id]})
    return sorted(out, key=lambda t: (t["ran_at"] or 0, t["stage"]), reverse=True)
