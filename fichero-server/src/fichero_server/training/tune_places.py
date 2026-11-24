"""Where a training step runs, and whether a recipe is proven there (`compute.tune.where-cheapest-first`,
`compute.tune.proven-on-huggingface-first`, #5119, #5398, #4950).

Pure functions of facts passed in: nothing here reads a token, opens a library or reaches a service.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

THIS_MAC = "this-mac"
NOT_PROVEN = "not yet proven on Hugging Face"
PROOF_KEY = "proven_on_huggingface"


@dataclass(frozen=True)
class Mac:
    memory_gb: float
    embedder_gb: float  # what the resident embedder keeps


@dataclass(frozen=True)
class Card:
    name: str
    needs_gb: float  # the card's measured memory (`compute.tune.measured-on-16gb`)


def choose_place(card: Card, mac: Mac, *, bound: dict[str, str], evidence: dict[str, dict[str, Any]] | None = None,
                 prefer: str | None = None) -> dict[str, Any]:
    """This Mac when the card fits beside the embedder; else the bound `gpu-service` target, then the `cluster` one.
    A costlier place than the cheapest that works is taken only with `prefer` AND its A/B evidence (error rate, cost,
    speed, carbon, trainability); evidence for a place not preferred is returned for showing, never acted on."""
    evidence = evidence or {}
    free = mac.memory_gb - mac.embedder_gb
    fits = card.needs_gb <= free
    ladder = [(THIS_MAC, f"{card.name} needs {card.needs_gb:g} GB and this Mac has {free:g} GB free beside the embedder")] if fits else []
    miss = "" if fits else f"{card.name} needs {card.needs_gb:g} GB, which does not fit this Mac's {free:g} GB free beside the embedder"
    for slot, words in (("gpu-service", "the project's Hugging Face target"), ("cluster", "the project's cluster")):
        if slot in bound:
            ladder.append((bound[slot], (miss + "; so " if miss else "") + words))
    if not ladder:
        raise ValueError(f"no place can train {card.name}: it does not fit this Mac and the project binds no gpu-service or cluster target")
    if prefer:
        shown = evidence.get(prefer)
        if prefer not in [p for p, _ in ladder] or not shown:
            raise ValueError(f"{prefer} is chosen over a cheaper place only with its A/B evidence on the project's pages")
        return {"place": prefer, "reason": f"{card.name} on {prefer}: " + ", ".join(f"{k} {v}" for k, v in shown.items()),
                "costlier_evidence": {prefer: shown}}
    place, reason = ladder[0]
    return {"place": place, "reason": reason, "costlier_evidence": {p: e for p, e in evidence.items() if p != place}}


def record_proof(recipe: Path, runs: list[dict[str, Any]], *, band: float) -> dict[str, Any]:
    """Write the proof into the recipe file: two Hugging Face runs whose held-out CER is within `band` of each other.
    Each run names its date, image digest, hardware and CER. Nothing is written when the proof does not hold."""
    if len(runs) < 2:
        raise ValueError("a recipe is proven by two runs on Hugging Face")
    for run in runs:
        for key in ("date", "image_digest", "hardware"):
            if not run.get(key):
                raise ValueError(f"a run's proof needs its {key.replace('_', ' ')}")
    cers = [run["cer"] for run in runs]
    if max(cers) - min(cers) > band:
        raise ValueError(f"the runs' CER ({min(cers)} to {max(cers)}) is not within the band of {band}")
    proof = {"runs": runs, "band": band}
    path = Path(recipe)
    body = json.loads(path.read_text(encoding="utf-8"))
    body[PROOF_KEY] = proof
    path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    return proof


def cluster_offer(recipe: Path) -> dict[str, Any]:
    """A cluster run of this recipe is always offered; an unproven recipe carries the words that say so."""
    proven = bool(json.loads(Path(recipe).read_text(encoding="utf-8")).get(PROOF_KEY))
    return {"offered": True, "note": None if proven else NOT_PROVEN}
