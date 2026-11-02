"""A try's kept copy and what Start may adopt from it (`wide.try.start-reuses-a-matching-try`, #6127; design approved 2026-11-02).

Slice A: a finished try keeps its scratch copy and a record per page (card, a hash of the step's settings, the page's image signature and the
copy's page id) until it expires, 7 days or the next try of the same stage. The days and the polygon overlap are settings of the project
(`recipe/try-settings.yaml`), not constants. Adoption itself (matching lines, copying readings, Start's first action) builds on this record."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
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
