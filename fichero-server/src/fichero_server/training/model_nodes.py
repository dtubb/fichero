"""The models a training node shows (#5439, `source.model.node-in-sidebar`, `source.model.node-inspector`).

Training is the sidebar node; a model shows there only when Fichero trained or fine-tuned it. Every
model here is read from the card it landed with, nothing kept only for display:

* a Kraken reader trained here or on Hugging Face Jobs: its install record's `trained` card
  (`training.landing`), its evaluations on the same record;
* a vision LoRA student: its `fichero-card.json` in the MLX store (`training.mlx_landing`).

A model downloaded or imported (a Kraken reader by DOI, a vision model from the Hub) has no training
card and is not listed: it lives in Settings. Fields a card does not carry are None, never guessed:
a Kraken reader's card names no licence; no card names the project it was trained in (cards live
on this engine, not in a library), nor a cluster build.

Publishing: a model may be published only when its card says `not_for_release: false`. Training asks
for `not_for_release` (default true) and the card keeps it; a card that does not say is not released.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

KRAKEN = "kraken-reader"
VISION = "vision-lora"


def _latest_scores(evaluations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The newest evaluation's CER per normalisation policy, or None when none was run."""
    if not evaluations:
        return None
    last = evaluations[-1]
    return {"measured_at": last.get("measured_at"), "job_id": last.get("job_id"), "checked": last.get("checked"),
            "pages": len(last.get("pages") or []),
            "cer": {policy: (s or {}).get("cer") for policy, s in (last.get("scores") or {}).items()}}


def _set_counts(card: dict[str, Any]) -> dict[str, Any] | None:
    ts = card.get("training_set")
    if not isinstance(ts, dict):
        return None
    keys = ("teacher", "pages", "lines", "lines_read_by_a_model", "lines_checked_by_a_person", "lines_left_out")
    return {k: ts.get(k) for k in keys} | {"held_out_pages": len(card.get("held_out") or [])}


def _node(model_id: str, kind: str, card: dict[str, Any], *, size_bytes: int | None,
          runs_on: list[dict[str, Any]], evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": model_id, "name": str(card.get("display_name") or model_id), "kind": kind,
        "summary": card.get("summary"), "base": card.get("base"), "teacher": card.get("teacher"),
        "job_id": card.get("job_id"), "trained_at": card.get("trained_at"), "trained_where": card.get("target"),
        "training_set": _set_counts(card),
        "scores": _latest_scores(evaluations), "evaluations": len(evaluations),
        "size_bytes": size_bytes, "runs_on": runs_on,
        "licence": card.get("base_licence"), "licence_note": card.get("base_licence_note"),
        "may_publish": card.get("not_for_release") is False, "release_note": card.get("release_note"),
    }


def _kraken_nodes(with_card: bool) -> list[dict[str, Any]]:
    from fichero_server.llm import kraken_runtime as kr
    from fichero_server.training.evaluation import model_evaluations

    out = []
    for model_id, card in kr.trained_readers():
        node = _node(model_id, KRAKEN, card, size_bytes=card.get("size_bytes"),
                     runs_on=[{"build": "kraken", "runs_on": "this Mac", "here": True}],
                     evaluations=(evals := model_evaluations(model_id, "kraken")))
        out.append(node | ({"card": card, "evaluation_history": evals} if with_card else {}))
    return out


def _vision_nodes(with_card: bool) -> list[dict[str, Any]]:
    from fichero_server.llm.mlx_model_store import get_mlx_model_store
    from fichero_server.training.evaluation import model_evaluations

    store = get_mlx_model_store()
    out = []
    for model_id in store.trained_model_ids():
        card = store.trained_card(model_id) or {}
        builds = card.get("builds") if isinstance(card.get("builds"), dict) else {}
        runs_on = [{"build": name, "runs_on": b.get("runs_on"),
                    "here": bool(b.get("merged_here")) if name == "hf" else Path(str(b.get("path") or "")).is_dir()}
                   for name, b in builds.items() if isinstance(b, dict)]
        node = _node(model_id, VISION, card, size_bytes=store._disk_usage_bytes(store.trained_dir(model_id)),
                     runs_on=runs_on, evaluations=(evals := model_evaluations(model_id, "vision")))
        out.append(node | ({"card": card, "evaluation_history": evals} if with_card else {}))
    return out


def model_nodes() -> list[dict[str, Any]]:
    """Every model Fichero trained or fine-tuned on this engine, newest first."""
    nodes = _kraken_nodes(False) + _vision_nodes(False)
    return sorted(nodes, key=lambda n: str(n.get("trained_at") or ""), reverse=True)


def model_node(model_id: str) -> dict[str, Any] | None:
    """One trained model's inspector facts (its whole card and every evaluation), or None."""
    for node in _kraken_nodes(True) + _vision_nodes(True):
        if node["id"] == model_id:
            return node
    return None
