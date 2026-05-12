"""Embedding-based entity vectors in LanceDB.

Phase B of the KG rollup (#899). Encodes the canonical_name +
description of every KnowledgeEntity into a 384-dim dense vector
using ``sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2``
(via fastembed, already a project dep — multilingual so Spanish
archive material works alongside English).

Vectors land in a LanceDB table per library (``kg_entities``). The
existing ``upsert_entity`` calls into this module on the fuzzy-match
fallback path: cosine similarity against same-type entities replaces
the SequenceMatcher heuristic.

Confidence bands (proposed thresholds, tuneable per #899 Phase D):
- ``>=0.92`` → auto-merge. Surface-form variant, accent drift, or
  near-identical title.
- ``0.75 – 0.92`` → flag as predicted match. Don't auto-merge yet;
  emit a log line + (future) push onto a review queue for the
  curation UI.
- ``<0.75`` → distinct entity, create new row + index its vector.

The model is lazy-imported on first use (per the
``feedback_lazy_import`` memory) so the engine cold-start stays
fast for users who don't catalogue.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from fichero.db import Database
    from fichero.knowledge_models import EntityType

logger = logging.getLogger(__name__)


# Embedding model — paraphrase-multilingual-MiniLM-L12-v2.
# 384-dim, ~220MB on disk, ES + EN handled by the same checkpoint.
# Picked over BGE-large or mpnet-base for cold-start time + RAM
# footprint on the on-device deployment.
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIM = 384

# LanceDB table name — one per library, keyed by entity id.
TABLE = "kg_entities"

# Default confidence bands. Stored as module constants so callers
# (and #899 Phase D's calibration work) can override.
AUTO_MERGE_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.75


# Cached embedding model singleton — lazy-loaded.
_model = None


def _get_model():
    """Lazy-load the fastembed model.

    First call downloads the model (~220MB) and incurs a few-second
    init; subsequent calls are free. Loading happens off the FastAPI
    hot path because ``upsert_entity`` runs inside catalogue workflows,
    not request handlers.
    """
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        logger.info("entity_vectors: loading embedding model %s (lazy)", EMBED_MODEL)
        _model = TextEmbedding(model_name=EMBED_MODEL)
    return _model


def encode(text: str) -> np.ndarray:
    """Encode a single string to a 384-dim float32 vector.

    fastembed's API is generator-based for batch; we wrap for the
    one-at-a-time call site in upsert_entity.
    """
    if not text or not text.strip():
        return np.zeros(EMBED_DIM, dtype=np.float32)
    model = _get_model()
    vec = next(iter(model.embed([text])))
    return np.asarray(vec, dtype=np.float32)


def _entity_text(canonical_name: str, description: Optional[str]) -> str:
    """Compose the text we encode for an entity.

    We embed the canonical_name with the description appended — the
    description carries the SVO predicate set by the catalogue
    extractor, which is exactly the discriminating signal between
    "Narrator's Account of Racial Economic Exclusion" and "Sale of
    the Estate." Without it, we'd be matching on bare titles and
    losing the contextual signal.
    """
    name = (canonical_name or "").strip()
    desc = (description or "").strip()
    if desc:
        return f"{name}. {desc}"
    return name


def _ensure_table(db: "Database"):
    """Get or create the kg_entities table in this library's LanceDB.

    Schema: id (str), entity_type (str), canonical_name (str),
    description (str), vector (float32[EMBED_DIM]).
    """
    lance = db.lance
    # list_tables is the modern API; table_names() is deprecated but
    # we still try it for older LanceDB installs.
    if hasattr(lance, "list_tables"):
        raw = lance.list_tables()
    else:  # pragma: no cover
        raw = lance.table_names()
    # Newer LanceDB wraps the list in an object with a .tables attr;
    # older returns a plain list. Normalize. (Mirrors the pattern in
    # fichero/db.py:_lance_tables.)
    if hasattr(raw, "tables"):
        table_names = raw.tables
    elif isinstance(raw, dict):
        table_names = list(raw.keys())
    else:
        table_names = list(raw)
    if TABLE in table_names:
        return lance.open_table(TABLE)

    import pyarrow as pa

    schema = pa.schema([
        pa.field("id", pa.string()),
        pa.field("entity_type", pa.string()),
        pa.field("canonical_name", pa.string()),
        pa.field("description", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
    ])
    return lance.create_table(TABLE, schema=schema)


def index_entity(
    db: "Database",
    entity_id: str,
    entity_type: "EntityType",
    canonical_name: str,
    description: Optional[str] = None,
) -> None:
    """Add or update an entity's vector in LanceDB.

    Idempotent — call again with the same id to refresh (e.g. after
    an alias merge updates the description). Existing rows with the
    same id are deleted first so we don't accumulate stale vectors.
    """
    try:
        table = _ensure_table(db)
        vec = encode(_entity_text(canonical_name, description))
        # L2-normalize so cosine similarity equals 1 - cosine distance
        # when LanceDB does the search side.
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm

        # Delete any prior vector for this id to keep the table 1:1
        # with KnowledgeEntity rows.
        table.delete(f"id = '{entity_id}'")

        table.add([{
            "id": entity_id,
            "entity_type": entity_type.value if hasattr(entity_type, "value") else str(entity_type),
            "canonical_name": canonical_name,
            "description": description or "",
            "vector": vec.tolist(),
        }])
    except Exception as exc:
        # Don't take down the catalogue workflow if vector indexing
        # fails. The DuckDB row is the canonical store; vectors are
        # an accelerator for fuzzy match. Log + carry on.
        logger.warning("entity_vectors.index_entity: %s", exc)


def find_similar(
    db: "Database",
    canonical_name: str,
    entity_type: "EntityType",
    description: Optional[str] = None,
    top_k: int = 5,
) -> list[tuple[str, float, str]]:
    """Cosine-search same-type entities by name+description similarity.

    Returns a list of ``(entity_id, cosine_score, matched_canonical_name)``
    tuples sorted by descending score, up to ``top_k`` hits. Empty
    list if the table is empty or the search fails — callers must
    treat as no-match (fall through to the SequenceMatcher path).

    The score is cosine similarity in ``[-1, 1]``; LanceDB returns
    distance, so we convert via ``score = 1 - distance``.
    """
    try:
        table = _ensure_table(db)
        type_value = entity_type.value if hasattr(entity_type, "value") else str(entity_type)

        # No rows in this library yet → nothing to match.
        try:
            row_count = table.count_rows()
        except Exception:
            row_count = None
        if row_count == 0:
            return []

        vec = encode(_entity_text(canonical_name, description))
        # Explicitly request cosine — LanceDB defaults to L2, which is
        # unbounded and won't map to a 0–1 confidence band. We also
        # L2-normalize the query vector so `1 - distance` is true
        # cosine similarity rather than an approximation.
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        results = (
            table.search(vec.tolist())
            .distance_type("cosine")
            .where(f"entity_type = '{type_value}'")
            .limit(top_k)
            .to_list()
        )

        hits: list[tuple[str, float, str]] = []
        for row in results:
            # _distance is cosine distance in [0, 2]; similarity = 1 - d
            # for L2-normalized vectors lands in [-1, 1] with 1.0 = identical.
            distance = row.get("_distance", 0.0)
            score = 1.0 - distance
            hits.append((row["id"], score, row.get("canonical_name", "")))
        return hits
    except Exception as exc:
        logger.warning("entity_vectors.find_similar: %s", exc)
        return []


def remove(db: "Database", entity_id: str) -> None:
    """Drop an entity's vector — used when an entity is merged away."""
    try:
        table = _ensure_table(db)
        table.delete(f"id = '{entity_id}'")
    except Exception as exc:
        logger.warning("entity_vectors.remove: %s", exc)
