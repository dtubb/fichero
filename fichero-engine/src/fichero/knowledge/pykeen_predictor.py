"""PyKEEN-backed link prediction (#377, #899 Phase E).

Trains a knowledge-graph embedding model (TransE by default — fast,
small, well-understood) on the SPO triples we already store via
``fichero.kg.triples`` and exposes prediction endpoints that surface
plausible-but-missing links for the human reviewer queue.

Why this matters:
- The reviewer flow (#377) needs candidate facts to triage. PyKEEN
  produces a ranked list of "likely-true triples that aren't in
  the graph yet" — a useful prior for a curation UI.
- The semantic-divergence case from #897 (Davidson alias clusters
  across pages) is partially addressed by Phase B vectors; PyKEEN
  closes the loop by learning that *patterns* of co-mention also
  imply identity, not just name similarity.

Implementation notes:
- Training is a one-shot offline step. The trained model gets
  persisted to ``<library>/pykeen.pt`` and reloaded on demand.
- Default model: TransE (translation in embedding space, ~30s
  training on ~10k triples). RotatE / ComplEx are richer but
  ~10x slower; not the default.
- Lazy-imported (#743 cold-start memory) — PyKEEN pulls torch
  which is heavy.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from fichero.db import Database

logger = logging.getLogger(__name__)


# Default training hyperparams — picked for "useful results on a
# small archive corpus, runs in under a minute." See PyKEEN docs
# for tuning guidance.
DEFAULT_MODEL = "TransE"
DEFAULT_EMBEDDING_DIM = 64
DEFAULT_NUM_EPOCHS = 50
DEFAULT_BATCH_SIZE = 32

# Process-global cache for trained PyKEEN models, keyed by library path.
#
# ``db_manager`` gives each Database instance its own path, but a given library
# should only deserialize its trained model once per process. Cache the loaded
# pipeline per library directory and reuse it across callers.
_MODEL_CACHE: dict[str, object] = {}
_MODEL_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class LinkPrediction:
    """One candidate fact predicted by the trained model."""
    subject_id: str
    predicate: str
    object_id: str
    score: float


def _model_path(db: "Database") -> Path:
    """Where the trained model + metadata live, next to the DuckDB."""
    return Path(db.path).parent / "pykeen"


def _gather_triples(db: "Database") -> list[tuple[str, str, str]]:
    """Pull SPO triples from KnowledgeClaim rows.

    Each claim contributes one triple per (entity_id, slugified_verb,
    canonical_object). Object is kept as raw text in the
    triple — pyKEEN will treat each unique object string as its own
    node. Future improvement: resolve object text to entity URIs
    where possible so the model learns over entities, not literals.
    """
    from fichero.kg._common import extract_svo, slug_verb
    from fichero.models.knowledge import KnowledgeClaim

    triples: list[tuple[str, str, str]] = []
    for claim in db.query(KnowledgeClaim):
        verb, object_text = extract_svo(claim)
        if not object_text:
            continue
        predicate = slug_verb(verb)
        for entity_id in (claim.entity_ids or []):
            triples.append((entity_id, predicate, object_text))
    return triples


def train_model(
    db: "Database",
    *,
    model_name: str = DEFAULT_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    num_epochs: int = DEFAULT_NUM_EPOCHS,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int | str]:
    """Train a KGE model on the library's claims and persist it.

    Returns a stats dict: ``{"triples": N, "entities": M, "relations": K,
    "model": "TransE", "path": "..."}``. Pull the trained model later
    via ``load_model(db)``.

    Training is synchronous and can take 30s+. Callers should run
    this off the request hot path (background task / scheduled job).
    """
    import torch
    from pykeen.pipeline import pipeline
    from pykeen.triples import TriplesFactory

    raw_triples = _gather_triples(db)
    if len(raw_triples) < 10:
        # Not enough data to learn anything meaningful. Surface
        # rather than train a degenerate model.
        return {
            "triples": len(raw_triples),
            "entities": 0,
            "relations": 0,
            "model": model_name,
            "path": "",
            "trained": False,
            "reason": "insufficient triples (need >= 10)",
        }

    import numpy as np
    triples_array = np.array(raw_triples, dtype=str)
    tf = TriplesFactory.from_labeled_triples(triples_array)

    out_dir = _model_path(db)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tiny model, CPU-only — works on a laptop without GPU.
    result = pipeline(
        training=tf,
        testing=tf,  # no held-out set for this lightweight scaffold;
                    # callers that want a proper eval pass their own
                    # train/test split.
        model=model_name,
        model_kwargs=dict(embedding_dim=embedding_dim),
        training_kwargs=dict(num_epochs=num_epochs, batch_size=batch_size),
        random_seed=42,
        device=torch.device("cpu"),
    )
    result.save_to_directory(str(out_dir))
    _invalidate_model_cache(out_dir)

    return {
        "triples": len(raw_triples),
        "entities": tf.num_entities,
        "relations": tf.num_relations,
        "model": model_name,
        "path": str(out_dir),
        "trained": True,
    }


def load_model(db: "Database"):
    """Reload a previously-trained PyKEEN pipeline.

    Returns the PipelineResult or None when no model has been
    trained for this library yet.
    """
    import torch

    out_dir = _model_path(db)
    model_pkl = out_dir / "trained_model.pkl"
    if not model_pkl.exists():
        return None
    cache_key = str(out_dir.resolve())
    model = _MODEL_CACHE.get(cache_key)
    if model is not None:
        return model

    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(cache_key)
        if model is not None:
            return model
        try:
            # PyKEEN serializes the trained model as trained_model.pkl.
            if not model_pkl.exists():
                return None
            model = torch.load(str(model_pkl), weights_only=True)
            _MODEL_CACHE[cache_key] = model
            logger.info("Loaded PyKEEN model (process-global): %s", cache_key)
            return model
        except Exception as exc:
            logger.warning("load_model failed: %s", exc)
            return None


def _invalidate_model_cache(out_dir: Path) -> None:
    """Drop any cached PyKEEN model for ``out_dir`` after retraining."""
    cache_key = str(out_dir.resolve())
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.pop(cache_key, None)


def predict_for_subject(
    db: "Database",
    subject_id: str,
    top_k: int = 10,
) -> list[LinkPrediction]:
    """Return top-k predicted (predicate, object) facts for one entity.

    The model has to have been trained already via ``train_model``;
    returns ``[]`` when no model exists or the subject isn't in the
    trained entity vocabulary.

    For a curation UI: each prediction is a candidate fact to show
    the user — they can accept (creates a KnowledgeClaim), reject
    (logs the negative, used for future model retraining), or skip.
    """
    try:
        from pykeen.predict import predict_target
    except ImportError:  # pragma: no cover
        logger.warning("pykeen.predict missing — try a newer pykeen")
        return []

    model = load_model(db)
    if model is None:
        return []

    out_dir = _model_path(db)
    try:
        from pykeen.triples import TriplesFactory
        # PyKEEN serializes the training factory alongside the model.
        tf_path = out_dir / "training_triples"
        if tf_path.exists():
            tf = TriplesFactory.from_path_binary(tf_path)
        else:
            return []
    except Exception as exc:
        logger.warning("predict_for_subject: triples factory load failed: %s", exc)
        return []

    # The subject id has to be in the entity vocabulary; otherwise
    # the model has no embedding for it.
    if subject_id not in tf.entity_to_id:
        return []

    # Top-k predictions for (subject, ?, ?) — scored across all
    # (predicate, object) combos. PyKEEN's predict_target is the
    # convenience helper for this.
    predictions = []
    for relation in tf.relation_to_id:
        df = predict_target(
            model=model,
            head=subject_id,
            relation=relation,
            triples_factory=tf,
        ).df
        for _, row in df.head(top_k).iterrows():
            predictions.append(LinkPrediction(
                subject_id=subject_id,
                predicate=relation,
                object_id=row["tail_label"],
                score=float(row["score"]),
            ))

    predictions.sort(key=lambda p: -p.score)
    return predictions[:top_k]


__all__ = [name for name in globals() if not name.startswith("__")]
