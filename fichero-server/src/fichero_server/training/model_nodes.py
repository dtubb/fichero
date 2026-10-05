"""The models a training node shows (#5439, `source.model.node-in-sidebar`, `source.model.node-inspector`).

Training is the sidebar node; a model shows there only when Fichero trained or fine-tuned it. Every
model here is read from the card it landed with, nothing kept only for display:

* a Kraken reader trained here or on Hugging Face Jobs: its install record's `trained` card
  (`training.landing`), its evaluations on the same record;
* a vision LoRA student: its `fichero-card.json` in the MLX store (`training.mlx_landing`).

A model downloaded or imported (a Kraken reader by DOI, a vision model from the Hub) has no training
card and is not listed: it lives in Settings. Fields a card does not carry are None, never guessed:
a Kraken reader's card names no licence, nor a cluster build.

A model shows only in the project it was trained in (#5483). Cards live on this engine, not in a
library, so the training job writes the project on the card (`project_of`: the library's path,
normalised as the security layer keys it, and its stable library id) and `belongs_to` is the one test
of which project a card belongs to. A card landed before that names no project and shows in none; a
reader among them is still in the Kraken model catalogue (Settings), where downloaded readers live.

Size is the weights' bytes on this Mac's disk, read when listed (the reader's model file, the MLX
build's files), never a figure kept on the card; None when the weights are not here.

Publishing: a model may be published only when its card says `not_for_release: false`. Training asks
for `not_for_release` (default true) and the card keeps it; a card that does not say is not released.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KRAKEN = "kraken-reader"
VISION = "vision-lora"


def project_of(db: Any) -> dict[str, Any]:
    """The project a library's database belongs to, as a trained model's card records it."""
    from fichero_server.security.authz import normalize_library_path

    return {"library_path": normalize_library_path(Path(db.path).parent), "library_id": db.library_uuid()}


def belongs_to(card: dict[str, Any], project: dict[str, Any]) -> bool:
    """Whether the model with this card was trained in `project` (a `project_of`). By library id when
    both carry one (it survives the library moving), else by normalised path. A card naming no
    project belongs to none."""
    mine = card.get("project")
    if not isinstance(mine, dict):
        return False
    if mine.get("library_id") and project.get("library_id"):
        return mine["library_id"] == project["library_id"]
    return bool(mine.get("library_path")) and mine.get("library_path") == project.get("library_path")


def _bytes_here(files: list[Path]) -> int | None:
    """The bytes these weight files hold on this disk, or None when none is here."""
    sizes = [f.stat().st_size for f in files if f.is_file()]
    return sum(sizes) if sizes else None


def _reader_bytes(model_id: str) -> int | None:
    """A trained reader's model file, the one its install record names."""
    from fichero_server.llm.kraken_runtime import _marker_path

    try:
        path = json.loads(_marker_path(model_id).read_text(encoding="utf-8")).get("model_path")
    except (OSError, ValueError):
        return None
    return _bytes_here([Path(path)]) if path else None


def _student_bytes(build_dir: Path) -> int | None:
    """A vision student's MLX build: every file in it but its card."""
    from fichero_server.llm.mlx_model_store import TRAINED_CARD

    if not build_dir.is_dir():
        return None
    return _bytes_here([f for f in build_dir.rglob("*") if f.name != TRAINED_CARD])


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


def _kraken_nodes(project: dict[str, Any], with_card: bool) -> list[dict[str, Any]]:
    from fichero_server.llm import kraken_runtime as kr
    from fichero_server.training.evaluation import model_evaluations

    out = []
    for model_id, card in kr.trained_readers():
        if not belongs_to(card, project):
            continue
        node = _node(model_id, KRAKEN, card, size_bytes=_reader_bytes(model_id),
                     runs_on=[{"build": "kraken", "runs_on": "this Mac", "here": True}],
                     evaluations=(evals := model_evaluations(model_id, "kraken")))
        out.append(node | ({"card": card, "evaluation_history": evals} if with_card else {}))
    return out


def _vision_nodes(project: dict[str, Any], with_card: bool) -> list[dict[str, Any]]:
    from fichero_server.llm.mlx_model_store import get_mlx_model_store
    from fichero_server.training.evaluation import model_evaluations

    store = get_mlx_model_store()
    out = []
    for model_id in store.trained_model_ids():
        card = store.trained_card(model_id) or {}
        if not belongs_to(card, project):
            continue
        builds = card.get("builds") if isinstance(card.get("builds"), dict) else {}
        runs_on = [{"build": name, "runs_on": b.get("runs_on"),
                    "here": bool(b.get("merged_here")) if name == "hf" else Path(str(b.get("path") or "")).is_dir()}
                   for name, b in builds.items() if isinstance(b, dict)]
        node = _node(model_id, VISION, card, size_bytes=_student_bytes(store.trained_dir(model_id)),
                     runs_on=runs_on, evaluations=(evals := model_evaluations(model_id, "vision")))
        out.append(node | ({"card": card, "evaluation_history": evals} if with_card else {}))
    return out


def model_nodes(db: Any) -> list[dict[str, Any]]:
    """Every model Fichero trained or fine-tuned in this library's project, newest first."""
    project = project_of(db)
    nodes = _kraken_nodes(project, False) + _vision_nodes(project, False)
    return sorted(nodes, key=lambda n: str(n.get("trained_at") or ""), reverse=True)


def model_node(db: Any, model_id: str) -> dict[str, Any] | None:
    """One trained model's inspector facts (its whole card and every evaluation), or None when this
    project did not train it."""
    project = project_of(db)
    for node in _kraken_nodes(project, True) + _vision_nodes(project, True):
        if node["id"] == model_id:
            return node
    return None
