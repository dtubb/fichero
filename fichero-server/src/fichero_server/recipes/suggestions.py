"""The one list of suggestions for a project's answers (`wide.suggest.*`, #6052): what the defaults table chose and what the sample showed,
each in words with the answer that fired it and where to change it. Pure: the route reads the project, this decides, the app draws."""
from __future__ import annotations

from typing import Any

from fichero_server.recipes import defaults

DAMAGE = ("torn", "water-damage", "stains")
#: ponytail: the price of the compare/review rows is the plan's estimate, not computed here; the route fills it when it has one.


def _row(id_: str, what: str, why: str, source: str, applied: bool, change: str, price: str | None = None) -> dict[str, Any]:
    return {"id": id_, "what": what, "why": why, "from": source, "applied": applied, "change": change, "price": price}


def build(answers: dict[str, Any] | None, pages: int, sample: dict[str, Any] | None, readers: dict[str, dict[str, list[str]]] | None) -> list[dict[str, Any]]:
    """The rows: conditions (ticked or seen in the sample), the model kind the How answers chose, each script's readers, a try for damage, and Review for a large reader."""
    answers, sample, readers = answers or {}, sample or {}, readers or {}
    chosen = list(answers.get("condition") or [])
    got = defaults.resolve(answers, pages)
    rows: list[dict[str, Any]] = []
    for cid, add in defaults.table()["adds"].items():
        seen = sample.get(f"condition.{cid}")
        if cid not in chosen and not seen:
            continue
        what = ("Prepare Images: " + ", ".join(add["prepare"])) if add.get("prepare") else (
            "Leave out the damaged areas and turn Review on" if "leave-out" in add.get("steps", []) else "Nothing run for it yet")
        rows.append(_row(f"condition.{cid}", what, add["why"] + (f" ({seen['why']})" if seen else ""),
                         f"condition: {cid.replace('-', ' ')}", cid in chosen, "about-the-material.condition"))
    how = answers.get("how") or {}
    if how.get("places") or how.get("matters"):
        rows.append(_row("defaults.model-kind", got["model_kind"], defaults.says_why(got, "model_kind"),
                         "your answers on How", True, "how.model-kind"))
    for script in answers.get("scripts") or []:
        found = readers.get(script)
        if found is None:
            continue
        if found["found"] and not found["installed"]:
            rows.append(_row(f"reader.script.{script}", f"Readers found for {script}: {', '.join(found['found'])}; none is installed",
                             "A reader for this script is not on this Mac. Your corrections could train one.", f"script: {script}", False,
                             "stage.read-a-line"))
        elif not found["found"]:
            near = ", ".join(found.get("nearest") or []) or "none close"
            rows.append(_row(f"reader.script.{script}", f"No reader found for {script}; nearest: {near}",
                             "Fichero has no reader for this script. Corrections could train one.", f"script: {script}", False,
                             "stage.read-a-line"))
    if "handwriting" in (answers.get("materials") or []) and set(chosen) & set(DAMAGE):
        rows.append(_row("try.compare-with-review", "Compare the reader alone with the reader and a review pass on your samples",
                         "Damaged handwriting may need a second look; the compare shows whether it pays. You choose in the compare view.",
                         "condition: " + ", ".join(c.replace("-", " ") for c in chosen if c in DAMAGE), False, "stage.read-a-line"))
    if how.get("model_kind") == "large" or "large" in str(got["model_kind"]):
        rows.append(_row("review.on-for-large-cloud-reader", "Turn Review on", "A large reader may invent or regularise text; a review checks it.",
                         "model kind: large", got["review"] == "on", "stage.review"))
    return rows
