"""Training in the recipe (#5660 item 9, `source.recipe.train-offered-per-step`): for each step a model can be
trained for, the Start plan offers "Train a model of your own for this step", offered later, never run at Start
(`source.recipe.train-never-automatic`).

Each offer names the ways to train (fine-tune or distil), and for each the places the engine can run it and the
audited action that starts it: only trainers and places the engine already has. A way with no trainer here is
listed as not available yet, never offered as if it ran. Whether the project has enough corrected material is
the bake-off's one count (`bakeoff.ground_truth`, `bakeoff.readiness`) at the train step's line threshold, so the
offer says how many more lines and pages it needs in the same words.
"""
from __future__ import annotations

from typing import Any

TITLE = "Train a model of your own for this step"

THIS_MAC = {"place": "this-mac", "name": "this Mac"}
HF_JOBS = {"place": "huggingface-jobs", "name": "Hugging Face Jobs"}

#: Per trainable job, its ways to train: (method, how, says, [(place, action that starts it)]); no places: not
#: available yet, with why. Places are the ones the engine trains on today; a cluster (ACENET) or another Mac
#: is not one yet (no training path), so neither is listed.
WAYS: dict[str, list[dict[str, Any]]] = {
    "read-a-line": [
        # The Kraken and MLX trainers learn from a teacher's line readings (`training/kraken_set.py`: no line in
        # the set is a person's), so both are distillations of the reader the project already uses.
        {"method": "kraken", "how": "distil",
         "says": "Train a Kraken reader of your own on the lines your reader read",
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


#: The audited actions that need a teacher (the model whose line readings are the lessons).
_TAUGHT = frozenset({"training.start_here", "training.start", "training.start_vision_lora"})


#: A Mac with at least this much memory trains a Kraken reader itself by default (`source.onboard.auto.train-offer-comes`).
#: Stated, not measured: a measured figure replaces it (QUESTION-TO-MANAGER, #5440).
TRAIN_HERE_MIN_RAM_GB = 16
TRAINING_MODES = ("here", "huggingface", "offered")


def training_setting(answered: str | None, *, mac_memory_gb: float, hf_configured: bool,
                     stays_local: bool = False) -> dict[str, str]:
    """How training happens in this project, from setup's answer (`answers.training`) or, with none, from the machine
    (#5440, ruled 2026-10-17): here when this Mac has the memory, else Hugging Face when a token is set up, else offered
    on the Start plan. A choice that cannot be met falls back to `offered` and says why. A project that keeps its pages on
    this Mac never has Hugging Face (the way that leaves it is refused, `_ways`). Never an alert."""
    enough = mac_memory_gb >= TRAIN_HERE_MIN_RAM_GB
    hf_configured = hf_configured and not stays_local
    off_mac = "this project keeps its pages on this Mac, and Hugging Face would take them off it"
    if answered not in TRAINING_MODES:
        mode = "here" if enough else "huggingface" if hf_configured else "offered"
        return {"mode": mode, "why": {
            "here": "this Mac has the memory to train a reader itself",
            "huggingface": "this Mac is short of memory to train here, and Hugging Face is set up",
            "offered": ("this Mac is short of memory to train here, and " + (off_mac if stays_local else
                                                                              "Hugging Face is not set up"))}[mode]}
    if answered == "here" and not enough:
        return {"mode": "offered", "why": "this Mac has not enough memory to train a reader here"}
    if answered == "huggingface" and stays_local:
        return {"mode": "offered", "why": off_mac}
    if answered == "huggingface" and not hf_configured:
        return {"mode": "offered", "why": "no Hugging Face token is set up (Settings, AI providers, Hugging Face)"}
    return {"mode": answered, "why": "your choice in setup"}


def _does(mode: str) -> str:
    return {"here": "Training runs by itself on this Mac once the corrected lines reach the threshold.",
            "huggingface": "Training runs by itself on Hugging Face Jobs once the corrected lines reach the threshold.",
            "offered": "Training is offered here when the corrected lines reach the threshold; you start it."}[mode]


def _params(action: str, job: str, counts: dict[str, Any]) -> dict[str, Any] | None:
    """What the app posts with `action`, as-is (#5660 item 9): the engine fills it, never the app. None when the
    engine cannot yet (no teacher: no reader has read this project's lines)."""
    scope = counts.get("scope_ids") or []
    if not scope:
        return None
    if action == "training.start_regions_here":
        return {"name": "regions", "scope_ids": scope}
    if action in _TAUGHT:
        teacher = counts.get("teacher")
        if not teacher:
            return None
        params = {"scope_ids": scope, "teacher": teacher}
        if action == "training.start_vision_lora":
            params["name"] = "student"
        # Hugging Face Jobs: `pages_may_leave` stays false; the person's yes is asked when they press start.
        return params
    return None


def _ways(job: str, *, stays_local: bool, counts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    counts = counts or {}
    out = []
    for way in WAYS[job]:
        targets = [{**place, "starts": action, "params": _params(action, job, counts)} for place, action in way["targets"]
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
    return {"pages": pages, "unmarked": unmarked_import_pages(db), "region_pages": len(regions),
            "teacher": _teacher(db), "scope_ids": _roots(db)}


def _teacher(db: Any) -> str | None:
    """The model that read lines on the most pages here: the reader a distillation learns from. None: nothing read."""
    from fichero_server.models import Artifact
    from fichero_server.models.segments import SegmentPass

    # A reader writes a pass of its own, or readings onto the page's lines from its page artifact (#5487), so both
    # name it (as `training.kraken_set.teacher_pass` matches them). A person's ground-truth pass never teaches here.
    pages: dict[str, set[str]] = {}
    for p in db.query(SegmentPass):
        if not p.deleted_at and p.model and not getattr(p, "ground_truth", False) and p.model not in ("human", "manual"):
            pages.setdefault(p.model, set()).add(p.document_id)
    for a in db.query(Artifact, artifact_type="transcription"):
        if a.model and a.model not in ("human", "manual"):
            pages.setdefault(a.model, set()).add(a.document_id)
    return max(pages, key=lambda m: (len(pages[m]), m)) if pages else None


def _roots(db: Any) -> list[str]:
    """The project's top-level live items: what a training run looks through when no folder is chosen."""
    from fichero_server.models import Document

    return sorted(d.id for d in db.query(Document, parent_id=None) if not d.deleted_at)


def train_offers(recipe: dict | None, counts: dict[str, Any], *, stays_local: bool,
                 setting: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """One offer per recipe step a model can be trained for, in the recipe's order."""
    from fichero_server.recipes.assemble import TRAIN_OFFERED_FROM_LINES
    from fichero_server.recipes.bakeoff import readiness

    setting = setting or {"mode": "offered", "why": "no setting given"}
    steps = (recipe or {}).get("steps") or []
    # The recipe's train step sets the line threshold for the step it trains (its `settings.base`).
    at_least = {(s.get("settings") or {}).get("base"): (s.get("offered_when") or {}).get("corrected_lines_at_least")
                for s in steps if s.get("job") == "train-a-model"}
    offers = []
    for step in steps:
        job = step.get("job")
        if job not in WAYS:
            continue
        ways = _ways(job, stays_local=stays_local, counts=counts)
        if not any(w["available"] for w in ways):
            # Nothing here can train it: no count of corrections to ask for (#5659: the names step asked for
            # 2,000 corrected lines, which no spaCy trainer would read).
            ready = {"ready": False, "sentence": None}
        elif job == "find-regions":
            ready = _regions_readiness(counts["region_pages"])
        else:
            ready = readiness(counts["pages"], counts["unmarked"],
                              min_lines=at_least.get(job) or at_least.get(step.get("id")) or TRAIN_OFFERED_FROM_LINES)
        offers.append({"step": step.get("id", job), "job": job, "title": TITLE, "ways": ways, "readiness": ready,
                       "setting": setting, "does": _does(setting["mode"])})
    return offers
