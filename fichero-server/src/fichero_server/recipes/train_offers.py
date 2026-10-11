"""Training in the recipe (#5660 item 9, `source.recipe.train-offered-per-step`): for each step a model can be
trained for, the Start plan offers "Train a model on your corrected pages", offered later, never run at Start
(`source.recipe.train-never-automatic`).

Each offer names the ways to train (fine-tune or distil), and for each the places the engine can run it and the
audited action that starts it: only trainers and places the engine already has. A way with no trainer here is
listed as not available yet, never offered as if it ran. Whether the project has enough corrected material is
the bake-off's one count (`bakeoff.ground_truth`, `bakeoff.readiness`) at the train step's line threshold, so the
offer says how many more lines and pages it needs in the same words.
"""
from __future__ import annotations

from typing import Any

TITLE = "Train a model on your corrected pages"

THIS_MAC = {"place": "this-mac", "name": "this Mac"}
HF_JOBS = {"place": "huggingface-jobs", "name": "Hugging Face Jobs"}

#: Per trainable job, its ways to train: (method, how, says, [(place, action that starts it)]); no places: not
#: available yet, with why. Places are the ones the engine trains on today; a cluster (ACENET) or another Mac
#: is not one yet (no training path), so neither is listed.
WAYS: dict[str, list[dict[str, Any]]] = {
    "read-a-line": [
        {"method": "kraken", "how": "fine-tune", "says": "Fine-tune a Kraken reader on your corrected lines",
         "targets": [(THIS_MAC, "training.start_here"), (HF_JOBS, "training.start")]},
        {"method": "mlx-vision-lora", "how": "distil",
         "says": "Distil a vision model's readings into a small MLX model (LoRA)",
         "targets": [(HF_JOBS, "training.start_vision_lora")]},
    ],
    "find-regions": [
        {"method": "yolo", "how": "fine-tune", "says": "Fine-tune a YOLO layout model on your corrected regions",
         "targets": [(THIS_MAC, "training.start_regions_here")]},
    ],
    "find-names-tag-words": [
        {"method": "spacy-ner", "how": "fine-tune", "says": "Fine-tune a spaCy names model on your corrected names",
         "targets": [], "why": "not available yet: Fichero has no spaCy trainer"},
    ],
}


def _ways(job: str, *, stays_local: bool) -> list[dict[str, Any]]:
    out = []
    for way in WAYS[job]:
        targets = [{**place, "starts": action} for place, action in way["targets"]
                   if not (stays_local and place is not THIS_MAC)]  # pages kept on this Mac never leave it
        why = way.get("why")
        if way["targets"] and not targets:
            why = "this project keeps its pages on this Mac, and this training runs only on Hugging Face Jobs"
        out.append({"method": way["method"], "how": way["how"], "says": way["says"], "targets": targets,
                    "available": bool(targets), "why": why})
    return out


def _regions_readiness(pages: int) -> dict[str, Any]:
    from fichero_server.recipes.bakeoff import MIN_PAGES, _plural

    more = max(0, MIN_PAGES - pages)
    sentence = None if not more else (
        f"Needs a person's regions on at least {MIN_PAGES} pages; this project has them on "
        f"{_plural(pages, 'page')}. Draw or correct the regions on {_plural(more, 'more page')}.")
    return {"ready": not more, "pages": pages, "min_pages": MIN_PAGES, "more_pages": more, "sentence": sentence}


def counted(db: Any) -> dict[str, Any]:
    """What the offers are counted on: the corrected pages and their lines (the bake-off's one counting rule), the
    imported pages nobody marked ground truth, and how many pages hold a person's regions."""
    from fichero_server.models.segments import Segment
    from fichero_server.recipes.bakeoff import ground_truth, unmarked_import_pages
    from fichero_server.training.yolo_set import REGION_KINDS

    pages, _ = ground_truth(db, None)
    regions = {s.document_id for s in db.query(Segment, provenance_kind="human")
               if s.kind in REGION_KINDS and s.deleted_at is None}
    return {"pages": pages, "unmarked": unmarked_import_pages(db), "region_pages": len(regions)}


def train_offers(recipe: dict | None, counts: dict[str, Any], *, stays_local: bool) -> list[dict[str, Any]]:
    """One offer per recipe step a model can be trained for, in the recipe's order."""
    from fichero_server.recipes.assemble import TRAIN_OFFERED_FROM_LINES
    from fichero_server.recipes.bakeoff import readiness

    steps = (recipe or {}).get("steps") or []
    # The recipe's train step sets the line threshold for the step it trains (its `settings.base`).
    at_least = {(s.get("settings") or {}).get("base"): (s.get("offered_when") or {}).get("corrected_lines_at_least")
                for s in steps if s.get("job") == "train-a-model"}
    offers = []
    for step in steps:
        job = step.get("job")
        if job not in WAYS:
            continue
        if job == "find-regions":
            ready = _regions_readiness(counts["region_pages"])
        else:
            ready = readiness(counts["pages"], counts["unmarked"],
                              min_lines=at_least.get(job) or at_least.get(step.get("id")) or TRAIN_OFFERED_FROM_LINES)
        offers.append({"step": step.get("id", job), "job": job, "title": TITLE,
                       "ways": _ways(job, stays_local=stays_local), "readiness": ready})
    return offers
