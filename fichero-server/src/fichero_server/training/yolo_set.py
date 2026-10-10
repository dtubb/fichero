"""The regions a person corrected, as a YOLO training set (`prep.yolo.fine-tune-from-corrected-regions`, #5525).

A page joins the set when a person's regions are on it: live region (or table) segments whose provenance is a
person's (drawn or adjusted by hand). Each region's class is its own label (`kind_raw`, else `kind`), so a project
that names "marginal note" teaches that class. Held-out pages are the validation set the landed card is scored on
(region overlap, mAP50); with none held out, the training pages stand in and the card says so.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REGION_KINDS = ("region", "table")


class EmptyRegionSet(ValueError):
    """No page in scope has a person's regions to learn from."""


@dataclass
class RegionSet:
    pages: int = 0
    regions: int = 0
    held_out: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    validated_on_training_pages: bool = False

    def summary(self) -> dict[str, Any]:
        return {"pages": self.pages, "regions": self.regions, "held_out": self.held_out, "classes": self.classes,
                "validated_on_training_pages": self.validated_on_training_pages}


def persons_regions(db: Any, document_id: str) -> list[Any]:
    """The live region segments on a page that a person made or corrected, in reading order."""
    from fichero_server.models.segments import ProvenanceKind, Segment

    found = [s for s in db.query(Segment, document_id=document_id)
             if s.kind in REGION_KINDS and s.deleted_at is None and s.provenance_kind == ProvenanceKind.human]
    return sorted(found, key=lambda s: (s.bbox_y, s.bbox_x))  # top to bottom, then left to right: a stable set


def label_of(segment: Any) -> str:
    return (segment.kind_raw or segment.kind or "region").strip()


def yolo_line(class_number: int, segment: Any) -> str:
    """One YOLO label line: class, then the box's centre and size, each 0..1 of the image."""
    x, y, w, h = (min(max(float(v), 0.0), 1.0) for v in (segment.bbox_x, segment.bbox_y, segment.bbox_w, segment.bbox_h))
    return f"{class_number} {x + w / 2:.6f} {y + h / 2:.6f} {w:.6f} {h:.6f}"


def export_region_set(db: Any, *, scope_ids: list[str], held_out_ids: list[str], out_dir: str | Path) -> RegionSet:
    """Write `images/`, `labels/` and `data.yaml` under `out_dir`; refused when nothing is there to learn from."""
    from fichero_server.training.kraken_set import pages_in_scope

    out = Path(out_dir)
    found = [(page, persons_regions(db, page.id)) for page in pages_in_scope(db, scope_ids)]
    found = [(page, regions) for page, regions in found if regions and Path(page.path).is_file()]
    if not found:
        raise EmptyRegionSet("no page in scope has regions a person drew or corrected")
    classes = sorted({label_of(s) for _, regions in found for s in regions})
    number = {name: i for i, name in enumerate(classes)}
    held = set(held_out_ids)
    made = RegionSet(classes=classes)
    for page, regions in found:
        split = "val" if page.id in held else "train"
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        image = out / "images" / split / f"{page.id}{Path(page.path).suffix.lower()}"
        shutil.copy2(page.path, image)
        (out / "labels" / split / f"{page.id}.txt").write_text(
            "\n".join(yolo_line(number[label_of(s)], s) for s in regions) + "\n", encoding="utf-8")
        made.pages += 1
        made.regions += len(regions)
        if split == "val":
            made.held_out.append(page.id)
    val = "images/val" if made.held_out else "images/train"
    made.validated_on_training_pages = not made.held_out
    names = "\n".join(f"  {i}: {name!r}" for i, name in enumerate(classes))
    (out / "data.yaml").write_text(f"path: {out}\ntrain: images/train\nval: {val}\nnames:\n{names}\n",
                                   encoding="utf-8")
    if not (out / "images" / "train").is_dir():
        raise EmptyRegionSet("every page with a person's regions is held out: none is left to train on")
    return made
