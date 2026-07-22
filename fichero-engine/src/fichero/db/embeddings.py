"""
Embedding helper methods for the Database class.

Mixed into Database via DatabaseEmbeddingMixin to keep db.py focused.
All methods access Database instance state (self._embedder, self.conn, etc.)
and are only valid when mixed into a Database subclass.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import math
import os
import re
import threading
from typing import Any, Callable, Literal

from fichero.errors import ErrorCategory, handle_error

logger = logging.getLogger(__name__)

# Default embedding model (FastEmbed - no scikit-learn dependency).
#
# NOTE: The default stays pinned to multilingual-e5-large until Fichero has an
# explicit re-embed workflow. BAAI/bge-m3 is available as an opt-in embedding
# space via FICHERO_EMBED_MODEL=BAAI/bge-m3; switching spaces deliberately
# changes the stamped model id and existing indexed tables will refuse mixed
# semantic search until re-embedded.
DEFAULT_MODEL = "intfloat/multilingual-e5-large"
BGE_M3_MODEL = "BAAI/bge-m3"
EMBED_MODEL_ENV = "FICHERO_EMBED_MODEL"
EMBEDDINGS_TABLE = "embeddings"
KG_ENTITY_EMBEDDINGS_TABLE = "kg_entity_embeddings"
KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"
LEGACY_KG_ENTITY_EMBEDDINGS_TABLE = "kg_entities"
EMBEDDING_MODEL_ID_FIELD = "embedding_model_id"
EmbeddingRole = Literal["query", "passage"]
PINNED_FASTEMBED_MODEL_ALIAS = "fichero-pinned/multilingual-e5-large-mean-v1"
PINNED_EMBEDDING_POOLING = "mean"
PINNED_EMBEDDING_NORMALIZATION = "l2"
PINNED_EMBEDDING_MODEL_ID = (
    f"{DEFAULT_MODEL}|pooling={PINNED_EMBEDDING_POOLING}|"
    f"normalization={PINNED_EMBEDDING_NORMALIZATION}|format=e5-role-prefix-v1"
)
BGE_M3_FASTEMBED_MODEL = BGE_M3_MODEL
BGE_M3_EMBEDDING_MODEL_ID = (
    f"{BGE_M3_MODEL}|pooling=mean|normalization=l2|format=raw-v1"
)


@dataclass(frozen=True)
class EmbeddingSpaceSpec:
    """Pinned embedding space contract for stored/searchable vectors."""

    source_model_name: str
    fastembed_model_name: str
    pooling: str
    normalization: str
    model_id: str


PINNED_EMBEDDING_SPACE = EmbeddingSpaceSpec(
    source_model_name=DEFAULT_MODEL,
    fastembed_model_name=PINNED_FASTEMBED_MODEL_ALIAS,
    pooling=PINNED_EMBEDDING_POOLING,
    normalization=PINNED_EMBEDDING_NORMALIZATION,
    model_id=PINNED_EMBEDDING_MODEL_ID,
)

BGE_M3_EMBEDDING_SPACE = EmbeddingSpaceSpec(
    source_model_name=BGE_M3_MODEL,
    fastembed_model_name=BGE_M3_FASTEMBED_MODEL,
    pooling="mean",
    normalization="l2",
    model_id=BGE_M3_EMBEDDING_MODEL_ID,
)

SUPPORTED_EMBEDDING_SPACES = {
    PINNED_EMBEDDING_SPACE.source_model_name.lower(): PINNED_EMBEDDING_SPACE,
    PINNED_EMBEDDING_SPACE.fastembed_model_name.lower(): PINNED_EMBEDDING_SPACE,
    BGE_M3_EMBEDDING_SPACE.source_model_name.lower(): BGE_M3_EMBEDDING_SPACE,
}


class EmbeddingSpaceMismatchError(RuntimeError):
    """Raised when a query would mix vectors from incompatible embedding spaces."""

    def __init__(
        self,
        *,
        table_name: str,
        active_model_id: str,
        stored_model_ids: set[str],
    ) -> None:
        self.table_name = table_name
        self.active_model_id = active_model_id
        self.stored_model_ids = frozenset(stored_model_ids)
        stored = ", ".join(sorted(self.stored_model_ids))
        super().__init__(
            "Embedding model mismatch for table "
            f"{table_name}: active pinned model-id {active_model_id!r} does not "
            f"match stored vector model-id(s) {stored}. Refusing mixed-space "
            "semantic search; re-embed deliberately before switching models."
        )


class EmbeddingMigrationConfirmationError(RuntimeError):
    """Raised when a destructive embedding-space migration lacks confirmation."""


@dataclass(frozen=True)
class SourceAnchor:
    """Where an embeddable text unit came from."""

    document_id: str
    page_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass(frozen=True)
class EmbeddableUnit:
    """Generic embedding payload; image regions/annotations can reuse this."""

    id: str
    text: str
    anchor: SourceAnchor
    kind: str = "passage"

# Process-global embedder cache, keyed by model name.
#
# The embedding model is a ~500 MB ONNX model that takes seconds to load. It is
# a *process-global* resource, but the host ``Database`` is instantiated per
# (package_path, thread_id) by ``db_manager`` — so storing the embedder as
# per-instance state (``self._embedder``) reloaded the model on EVERY worker
# thread / page during a run, flooding logs and dominating per-page time. Cache
# the loaded model here so all Database instances and threads share one copy.
# (FastEmbed's TextEmbedding wraps an ONNX Runtime session, which is safe for
# concurrent inference across threads.) Keyed by model name so switching the
# configured model still loads the new one once.
_EMBEDDER_CACHE: dict[str, Any] = {}
_EMBEDDER_CACHE_LOCK = threading.Lock()

# Tables for which the legacy-embedding warning has already been emitted this
# process. Keyed by table name; shared across all Database instances and threads
# so the log line fires at most once per table per process (#2480).
_LEGACY_TABLE_WARNED: set[str] = set()


def _get_shared_embedder(model_name: str, cache_dir: str) -> Any:
    """Return the process-global TextEmbedding for ``model_name``, loading once.

    Double-checked locking so concurrent worker threads don't each load the
    model. The host stores the returned object on ``self._embedder``.
    """
    embedder = _EMBEDDER_CACHE.get(model_name)
    if embedder is not None:
        return embedder
    with _EMBEDDER_CACHE_LOCK:
        embedder = _EMBEDDER_CACHE.get(model_name)
        if embedder is None:
            from fastembed import TextEmbedding

            embedder = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
            _EMBEDDER_CACHE[model_name] = embedder
            logger.info("Loaded embedding model (process-global): %s", model_name)
        return embedder


def _register_e5_fastembed_model() -> None:
    """Register the pinned E5 FastEmbed alias once so pooling stays explicit."""
    from fastembed import TextEmbedding
    from fastembed.common.model_description import PoolingType

    if not hasattr(TextEmbedding, "_list_supported_models"):
        return

    supported = TextEmbedding._list_supported_models()
    if any(
        model.model.lower() == PINNED_EMBEDDING_SPACE.fastembed_model_name.lower()
        for model in supported
    ):
        return

    source = next(
        model
        for model in supported
        if model.model.lower() == PINNED_EMBEDDING_SPACE.source_model_name.lower()
    )
    TextEmbedding.add_custom_model(
        model=PINNED_EMBEDDING_SPACE.fastembed_model_name,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=source.sources,
        dim=source.dim,
        model_file=source.model_file,
        description=source.description,
        license=source.license,
        size_in_gb=source.size_in_GB,
        additional_files=source.additional_files,
    )


def _register_pinned_fastembed_model() -> None:
    """Backward-compatible name for the default pinned E5 registration."""
    _register_e5_fastembed_model()


def _register_bge_m3_fastembed_model() -> None:
    """Register bge-m3 with FastEmbed until upstream ships it in the catalog."""
    from fastembed import TextEmbedding
    from fastembed.common.model_description import ModelSource, PoolingType

    if not hasattr(TextEmbedding, "_list_supported_models"):
        return

    supported = TextEmbedding._list_supported_models()
    if any(model.model.lower() == BGE_M3_MODEL.lower() for model in supported):
        return

    # Metadata mirrors qdrant/fastembed PR #602. Tests assert registration only;
    # first real use may download the ONNX files through FastEmbed's normal path.
    TextEmbedding.add_custom_model(
        model=BGE_M3_FASTEMBED_MODEL,
        pooling=PoolingType.MEAN,
        normalization=True,
        sources=ModelSource(hf=BGE_M3_MODEL),
        dim=1024,
        model_file="onnx/model.onnx",
        description=(
            "Text embeddings, Unimodal (text), Multilingual (100+ languages), "
            "8192 input tokens truncation, versatility in Multi-Functionality, "
            "Multi-Linguality, and Multi-Granularity."
        ),
        license="mit",
        size_in_gb=2.27,
        additional_files=["onnx/model.onnx_data", "onnx/sentencepiece.bpe.model"],
    )


def _register_fastembed_model_for_space(space: EmbeddingSpaceSpec) -> None:
    if space == BGE_M3_EMBEDDING_SPACE:
        _register_bge_m3_fastembed_model()
        return
    _register_e5_fastembed_model()


def _configured_embedding_space() -> EmbeddingSpaceSpec:
    configured = os.getenv(EMBED_MODEL_ENV, "").strip()
    if not configured:
        return PINNED_EMBEDDING_SPACE

    space = SUPPORTED_EMBEDDING_SPACES.get(configured.lower())
    if space is None:
        supported = ", ".join(
            sorted({space.source_model_name for space in SUPPORTED_EMBEDDING_SPACES.values()})
        )
        raise ValueError(
            f"Unsupported {EMBED_MODEL_ENV}={configured!r}; supported embedding "
            f"models: {supported}"
        )
    return space


def format_for_model(model_name: str, text: str, role: EmbeddingRole) -> str:
    """Apply model-specific input formatting.

    E5-family models require query/passage prefixes. bge-m3 and most other
    local FastEmbed models do not.
    """
    if role not in {"query", "passage"}:
        raise ValueError(f"Unknown embedding role: {role!r}")

    normalized = model_name.lower()
    if normalized == PINNED_EMBEDDING_SPACE.fastembed_model_name.lower():
        normalized = PINNED_EMBEDDING_SPACE.source_model_name.lower()
    if normalized.startswith("intfloat/multilingual-e5-"):
        return f"{role}: {text}"
    return text


def _sentence_or_paragraph_boundary(text: str, start: int, end: int) -> int | None:
    """Choose a natural boundary inside ``text[start:end]`` when one exists."""
    window = text[start:end]
    min_offset = max(1, int(len(window) * 0.55))
    boundary = None

    for match in re.finditer(r"\n\s*\n", window):
        if match.end() >= min_offset:
            boundary = start + match.start()

    for match in re.finditer(r"[.!?。！？।]+(?:[\"')\]]+)?(?=\s|$)", window):
        if match.end() >= min_offset:
            boundary = start + match.end()

    return boundary


def split_text_passages(
    text: str,
    *,
    document_id: str,
    page_id: str | None = None,
    max_chars: int = 512,
    overlap_chars: int = 80,
) -> list[EmbeddableUnit]:
    """Split text into anchored passage-sized embeddable units.

    The splitter uses character windows with sentence/paragraph boundary
    preference so offsets stay exact for any UTF-8 script and no tokenizer is
    required. Overlap is stored as real source offsets for downstream roll-up.
    """
    if max_chars < 64:
        raise ValueError("max_chars must be at least 64")
    overlap_chars = max(0, min(overlap_chars, max_chars // 2))

    source = text or ""
    length = len(source)
    passages: list[EmbeddableUnit] = []
    start = 0

    while start < length:
        while start < length and source[start].isspace():
            start += 1
        if start >= length:
            break

        hard_end = min(length, start + max_chars)
        end = hard_end
        if hard_end < length:
            natural_end = _sentence_or_paragraph_boundary(source, start, hard_end)
            if natural_end and natural_end > start:
                end = natural_end

        while end > start and source[end - 1].isspace():
            end -= 1
        if end <= start:
            break

        passage_id = f"{document_id}:passage:{len(passages)}:{start}-{end}"
        passages.append(
            EmbeddableUnit(
                id=passage_id,
                text=source[start:end],
                anchor=SourceAnchor(
                    document_id=document_id,
                    page_id=page_id,
                    char_start=start,
                    char_end=end,
                ),
            )
        )

        if end >= length:
            break
        next_start = max(start + 1, end - overlap_chars)
        start = next_start

    return passages


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalise a vector to unit length.

    Why: LanceDB returns L2 distance from `table.search(query_vector)`. On
    *un-normalised* vectors L2 distance can be hundreds, so the score
    formula `1/(1+d)` collapses every result into the 0.002–0.005 band —
    indistinguishable noise. On *unit-length* vectors L2 distance lives
    in [0, 2] and relates to cosine similarity exactly:

        L2² = 2 - 2·cos_sim   ⇒   cos_sim = 1 - L2²/2

    So normalising once at index time and once at query time gives us
    real, interpretable [0, 1] cosine scores from the same `_distance`
    column without changing the LanceDB API.
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _vector_to_list(vec: Any) -> list[float]:
    """Convert FastEmbed/NumPy vectors or test doubles to a float list."""
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    return [float(x) for x in vec]


def _quantize_int8(vec: list[float]) -> tuple[list[int], float]:
    """Symmetric int8 quantisation with per-vector scale."""
    if not vec:
        return [], 1.0
    max_abs = max(abs(x) for x in vec)
    if max_abs == 0.0:
        return [0 for _ in vec], 1.0
    scale = max_abs / 127.0
    quantized = [max(-127, min(127, int(round(x / scale)))) for x in vec]
    return quantized, scale


def _dequantize_int8(qvec: list[int], scale: float) -> list[float]:
    """Dequantise int8 values back to float vector."""
    if not qvec:
        return []
    if scale <= 0:
        scale = 1.0
    return [float(x) * scale for x in qvec]


def _join_text_parts(parts: list[str | None]) -> str:
    """Join non-empty text fragments into one embedding payload."""
    values = [part.strip() for part in parts if part and part.strip()]
    return " ".join(values)


class DatabaseEmbeddingMixin:
    """Embedding helper methods mixed into Database.

    Provides model loading, text embedding, reindexing, and stats.
    Requires that the host class has: self._embedder, self._lance_path,
    self.all(), self.embed(), self.save_embedding(), self._lance_tables(),
    self.lance.
    """

    def reindex_all(
        self,
        on_progress: Callable[[int, int], None] | None = None,
        *,
        mode: Literal["passage", "page"] = "passage",
        batch_size: int = 32,
    ) -> int:
        """Reindex all documents with page_content.

        Args:
            on_progress: Optional callback(indexed: int, total: int)

        Returns:
            Number of documents indexed
        """
        from fichero.models import Document

        docs = self.all(Document)
        total = len(docs)
        indexed = 0
        batch_size = max(1, batch_size)

        for start in range(0, total, batch_size):
            batch = docs[start : start + batch_size]
            embedded_ids = self._embed_document_batch(batch, mode=mode)
            for doc in batch:
                if doc.id in embedded_ids:
                    indexed += 1

                if on_progress:
                    on_progress(indexed, total)

        logger.info("Reindexed %s/%s documents", indexed, total)
        return indexed

    def embed_many(
        self,
        docs: list[Any],
        *,
        mode: Literal["passage", "page"] = "passage",
    ) -> int:
        """Embed a batch of documents with one forward pass and one append.

        Additive bulk path for the 100k-image problem (#2542): pair it with
        ``Database.save_many`` so a batch of imported docs persists in one
        DuckDB transaction and embeds/appends to LanceDB once, instead of N
        per-doc ``embed`` calls (each its own forward pass + micro-append).

        Reuses the already-tested ``_embed_document_batch`` machinery (single
        ``_embed_texts`` forward pass + one ``save_vectors`` append), so the
        per-page single-doc ``embed`` contract is untouched. A batch-level
        failure falls back to per-doc embedding inside ``_embed_document_batch``
        (logged, never silently dropped). Returns the number of docs embedded.
        """
        docs = [doc for doc in docs if doc is not None]
        if not docs:
            return 0
        return len(self._embed_document_batch(docs, mode=mode))

    def _embed_document_batch(
        self,
        docs: list[Any],
        *,
        mode: Literal["passage", "page"] = "passage",
    ) -> set[str]:
        """Embed a batch of documents with one forward pass per batch."""
        docs_with_text = [
            (doc, text)
            for doc in docs
            if (text := self._embedding_text_for_document(doc))
        ]
        if not docs_with_text:
            return set()

        try:
            if mode == "page":
                texts = [text for _doc, text in docs_with_text]
                vectors = self._embed_texts(texts, role="passage")
                embedded_ids: set[str] = set()
                for (doc, text), vector in zip(docs_with_text, vectors, strict=True):
                    self.save_embedding(doc, vector, text[:500])
                    embedded_ids.add(doc.id)
                return embedded_ids

            units_by_doc_id: dict[str, list[EmbeddableUnit]] = {}
            units: list[EmbeddableUnit] = []
            docs_by_id = {}
            for doc, text in docs_with_text:
                doc_units = self.passage_units_for_document(doc, text=text)
                if not doc_units:
                    continue
                docs_by_id[doc.id] = doc
                units_by_doc_id[doc.id] = doc_units
                units.extend(doc_units)

            if not units:
                return set()

            vectors = self._embed_texts([unit.text for unit in units], role="passage")
            records = []
            for unit, vector in zip(units, vectors, strict=True):
                doc = docs_by_id[unit.anchor.document_id]
                stored_vector = vector
                quantized_vector: list[int] | None = None
                quantized_scale: float | None = None
                if self._use_int8_embeddings():
                    quantized_vector, quantized_scale = _quantize_int8(vector)
                    stored_vector = _dequantize_int8(quantized_vector, quantized_scale)

                records.append(
                    {
                        "id": unit.id,
                        "document_id": unit.anchor.document_id,
                        "text": unit.text,
                        "vector": stored_vector,
                        "embedding_scope": unit.kind,
                        "passage_id": unit.id,
                        "page_id": unit.anchor.page_id,
                        "char_start": unit.anchor.char_start,
                        "char_end": unit.anchor.char_end,
                        "name": getattr(doc, "name", None),
                        "doc_type": getattr(doc, "doc_type", None).value
                        if hasattr(doc, "doc_type") and doc.doc_type
                        else None,
                        "file_type": getattr(doc, "file_type", None).value
                        if hasattr(doc, "file_type") and doc.file_type
                        else None,
                        "vector_int8": quantized_vector,
                        "vector_scale": quantized_scale,
                        **self._vector_model_metadata(),
                    }
                )

            for doc_id in units_by_doc_id:
                self._delete_embedding_rows("document_id", doc_id)
            self.save_vectors(EMBEDDINGS_TABLE, records)
            return set(units_by_doc_id)
        except (RuntimeError, ValueError, OSError, MemoryError) as exc:
            logger.warning("Failed to batch-embed %d document(s): %s", len(docs), exc)
            embedded_ids: set[str] = set()
            for doc, _text in docs_with_text:
                if self.embed(doc, mode=mode):
                    embedded_ids.add(doc.id)
            return embedded_ids

    def embedding_stats(self) -> dict:
        """Get statistics about embeddings.

        Returns:
            Dict with indexed_count, table_exists
        """
        doc_stats = self._vector_table_stats(EMBEDDINGS_TABLE)
        self.ensure_canonical_entity_embedding_table()
        entity_stats = self._vector_table_stats(KG_ENTITY_EMBEDDINGS_TABLE)
        claim_stats = self._vector_table_stats(KG_CLAIM_EMBEDDINGS_TABLE)
        return {
            "indexed_count": doc_stats["indexed_count"],
            "table_exists": doc_stats["table_exists"],
            "entity_indexed_count": entity_stats["indexed_count"],
            "entity_table_exists": entity_stats["table_exists"],
            "claim_indexed_count": claim_stats["indexed_count"],
            "claim_table_exists": claim_stats["table_exists"],
        }

    def ensure_canonical_entity_embedding_table(self) -> str | None:
        """Migrate the legacy entity vector table onto the canonical name."""
        tables = set(self._lance_tables())
        if KG_ENTITY_EMBEDDINGS_TABLE in tables:
            return KG_ENTITY_EMBEDDINGS_TABLE
        if LEGACY_KG_ENTITY_EMBEDDINGS_TABLE not in tables:
            return None

        legacy_rows = (
            self.lance.open_table(LEGACY_KG_ENTITY_EMBEDDINGS_TABLE)
            .search()
            .limit(1_000_000)
            .to_list()
        )
        if legacy_rows:
            self.save_vectors(KG_ENTITY_EMBEDDINGS_TABLE, legacy_rows, replace=True)
        return KG_ENTITY_EMBEDDINGS_TABLE

    def _vector_table_stats(self, table_name: str) -> dict[str, int | bool]:
        """Count rows in one LanceDB vector table if present."""
        try:
            if table_name not in self._lance_tables():
                return {"indexed_count": 0, "table_exists": False}

            table = self.lance.open_table(table_name)
            return {"indexed_count": table.count_rows(), "table_exists": True}
        except Exception:
            return {"indexed_count": 0, "table_exists": False}

    def embedding_table_model_ids(
        self,
        *,
        table_names: tuple[str, ...] = (
            EMBEDDINGS_TABLE,
            KG_ENTITY_EMBEDDINGS_TABLE,
            KG_CLAIM_EMBEDDINGS_TABLE,
        ),
        sample_limit: int = 10_000,
    ) -> dict[str, list[str]]:
        """Return known model ids present in embedding tables.

        Legacy rows without ``embedding_model_id`` are reported as
        ``"<legacy-unstamped>"`` so migration previews can distinguish them
        from empty tables.
        """
        ids_by_table: dict[str, list[str]] = {}
        for table_name in table_names:
            if table_name not in self._lance_tables():
                ids_by_table[table_name] = []
                continue

            table = self.lance.open_table(table_name)
            rows = table.search().limit(sample_limit).to_list()
            ids = {
                str(row.get(EMBEDDING_MODEL_ID_FIELD) or "<legacy-unstamped>")
                for row in rows
            }
            ids_by_table[table_name] = sorted(ids)
        return ids_by_table

    def migrate_embedding_space(
        self,
        *,
        confirm: bool = False,
        include_documents: bool = True,
        include_entities: bool = True,
        include_claims: bool = True,
        mode: Literal["passage", "page"] = "passage",
    ) -> dict[str, Any]:
        """Explicitly rebuild embedding tables for the active embedding space.

        This is intentionally destructive and opt-in: selected LanceDB vector
        tables are dropped before being rebuilt from DuckDB source records. It
        is the safe path for switching from pinned E5 to bge-m3 because stale
        rows for deleted documents/entities cannot survive the migration.
        """
        if not confirm:
            raise EmbeddingMigrationConfirmationError(
                "Embedding-space migration drops and rebuilds vector tables; "
                "pass confirm=True to run it deliberately."
            )

        from fichero.models.knowledge import KnowledgeClaim, KnowledgeEntity

        before = self.embedding_table_model_ids()
        table_names: list[str] = []
        if include_documents:
            table_names.append(EMBEDDINGS_TABLE)
        if include_entities:
            table_names.append(KG_ENTITY_EMBEDDINGS_TABLE)
        if include_claims:
            table_names.append(KG_CLAIM_EMBEDDINGS_TABLE)

        with self._lock:
            for table_name in table_names:
                if table_name in self._lance_tables():
                    self.lance.drop_table(table_name)

        documents_indexed = self.reindex_all(mode=mode) if include_documents else 0
        entities = self.all(KnowledgeEntity) if include_entities else []
        claims = self.all(KnowledgeClaim) if include_claims else []
        entities_indexed = self.embed_entities(entities) if entities else 0
        claims_indexed = self.embed_claims(claims) if claims else 0
        after = self.embedding_table_model_ids()

        return {
            "embedding_model_id": self._get_embedding_model_id(),
            "documents_indexed": documents_indexed,
            "entities_indexed": entities_indexed,
            "claims_indexed": claims_indexed,
            "before": before,
            "after": after,
        }

    def _get_embedding_model_name(self) -> str:
        """Return the configured source model name for the local embedding space."""
        return self._get_embedding_space().source_model_name

    def _get_embedding_space(self) -> EmbeddingSpaceSpec:
        """Return the explicit embedding-space contract."""
        return _configured_embedding_space()

    def _get_embedding_model_id(self) -> str:
        """Return the stamped model-id for newly written vectors."""
        return self._get_embedding_space().model_id

    def _use_int8_embeddings(self) -> bool:
        """Feature flag for int8 embedding storage."""
        raw = os.getenv("FICHERO_EMBEDDINGS_INT8", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    def _ensure_embedder(self) -> None:
        """Lazy-load the embedding model.

        Uses FastEmbed (ONNX-based, no scikit-learn dependency).
        The model + pooling are pinned in code to avoid silent vector drift.
        """
        if self._embedder is None:
            try:
                from fichero.local_models import MODELS_BASE

                space = self._get_embedding_space()
                self._embedding_model_name = space.source_model_name
                self._embedding_model_id = space.model_id
                cache_dir = MODELS_BASE / "embeddings"
                cache_dir.mkdir(parents=True, exist_ok=True)
                _register_fastembed_model_for_space(space)
                # Process-global: loaded once and shared across every Database
                # instance / worker thread (see _get_shared_embedder). Previously
                # this constructed a fresh ~500 MB model per instance/thread.
                self._embedder = _get_shared_embedder(
                    space.fastembed_model_name, str(cache_dir)
                )
            except ImportError as exc:
                # Chain the real cause (#2507): a non-fastembed ImportError
                # (e.g. a bad submodule import) used to be masked as the
                # generic "fastembed not installed", hiding the actual failure.
                raise ImportError(
                    "fastembed not installed. Install with: pip install fastembed"
                ) from exc

    def _embed_text(self, text: str, *, role: EmbeddingRole = "query") -> list[float]:
        """Generate embedding vector for text.

        Uses FastEmbed for local ONNX-based embedding.
        Lazy-loads the model on first use.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector)
        """
        self._ensure_embedder()
        model_name = getattr(self, "_embedding_model_name", None) or self._get_embedding_model_name()
        formatted = format_for_model(model_name, text, role)
        embeddings = list(self._embedder.embed([formatted]))
        return _l2_normalize(_vector_to_list(embeddings[0]))

    def _embed_texts(
        self, texts: list[str], *, role: EmbeddingRole = "passage"
    ) -> list[list[float]]:
        """Batch embed multiple texts.

        More efficient than calling _embed_text() in a loop.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        self._ensure_embedder()
        model_name = getattr(self, "_embedding_model_name", None) or self._get_embedding_model_name()
        formatted = [format_for_model(model_name, text, role) for text in texts]
        embeddings = list(self._embedder.embed(formatted))
        return [_l2_normalize(_vector_to_list(e)) for e in embeddings]

    async def _embed_text_async(
        self, text: str, *, role: EmbeddingRole = "query"
    ) -> list[float]:
        """Async wrapper: offloads synchronous ONNX embed to a thread (#2231).

        Use this in async route handlers to avoid blocking the event loop.
        """
        return await asyncio.to_thread(self._embed_text, text, role=role)

    async def _embed_texts_async(
        self, texts: list[str], *, role: EmbeddingRole = "passage"
    ) -> list[list[float]]:
        """Async wrapper: offloads synchronous batch ONNX embed to a thread (#2231)."""
        return await asyncio.to_thread(self._embed_texts, texts, role=role)

    def _vector_model_metadata(self) -> dict[str, str]:
        """Metadata stamped onto every newly written vector row."""
        return {EMBEDDING_MODEL_ID_FIELD: self._get_embedding_model_id()}

    def _warn_legacy_vector_table(self, table_name: str) -> None:
        if table_name in _LEGACY_TABLE_WARNED:
            return
        _LEGACY_TABLE_WARNED.add(table_name)
        logger.warning(
            "Vector table %s contains legacy/unstamped embeddings; allowing search "
            "for now, but future writes stamp %s.",
            table_name,
            self._get_embedding_model_id(),
        )

    def assert_vector_table_model_compatible(self, table_name: str) -> None:
        """Refuse semantic search when stored vectors use a different known model-id.

        Scans the full embedding_model_id column (no vector data loaded) so a
        partial migration — first N rows stamped with one model, tail rows with
        another — is always detected (#2232).
        """
        if table_name not in self._lance_tables():
            return

        table = self.lance.open_table(table_name)

        # Legacy tables don't have the column at all; detect via schema, not data.
        schema_fields = {field.name for field in table.schema}
        if EMBEDDING_MODEL_ID_FIELD not in schema_fields:
            self._warn_legacy_vector_table(table_name)
            return

        # Scan ALL rows but project only the model-id column (no vector data loaded).
        # count_rows() + select([col]).limit(n) avoids the pylance Rust extension.
        total = table.count_rows()
        if total == 0:
            return
        rows = table.search().select([EMBEDDING_MODEL_ID_FIELD]).limit(total).to_list()
        values = [row.get(EMBEDDING_MODEL_ID_FIELD) for row in rows]
        if not values:
            return

        known_ids = {v for v in values if v is not None}
        if not known_ids:
            self._warn_legacy_vector_table(table_name)
            return

        active_model_id = self._get_embedding_model_id()
        if any(model_id != active_model_id for model_id in known_ids):
            raise EmbeddingSpaceMismatchError(
                table_name=table_name,
                active_model_id=active_model_id,
                stored_model_ids=known_ids,
            )

    def passage_units_for_document(
        self,
        doc,
        *,
        text: str | None = None,
        max_chars: int = 512,
        overlap_chars: int = 80,
    ) -> list[EmbeddableUnit]:
        """Build passage units for a document's page_content."""
        text = text if text is not None else (getattr(doc, "page_content", None) or "")
        page_id = getattr(doc, "id", None)
        return split_text_passages(
            text,
            document_id=getattr(doc, "id"),
            page_id=page_id,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

    def passage_embedding_records(
        self,
        doc,
        *,
        text: str | None = None,
        max_chars: int = 512,
        overlap_chars: int = 80,
    ) -> list[dict[str, Any]]:
        """Embed a document's passages and return LanceDB-ready records."""
        units = self.passage_units_for_document(
            doc, text=text, max_chars=max_chars, overlap_chars=overlap_chars
        )
        if not units:
            return []

        if len(units) == 1:
            vectors = [self._embed_text(units[0].text, role="passage")]
        else:
            vectors = self._embed_texts([unit.text for unit in units], role="passage")
        records = []
        for unit, vector in zip(units, vectors):
            stored_vector = vector
            quantized_vector: list[int] | None = None
            quantized_scale: float | None = None
            if self._use_int8_embeddings():
                quantized_vector, quantized_scale = _quantize_int8(vector)
                stored_vector = _dequantize_int8(quantized_vector, quantized_scale)

            records.append(
                {
                    "id": unit.id,
                    "document_id": unit.anchor.document_id,
                    "text": unit.text,
                    "vector": stored_vector,
                    "embedding_scope": unit.kind,
                    "passage_id": unit.id,
                    "page_id": unit.anchor.page_id,
                    "char_start": unit.anchor.char_start,
                    "char_end": unit.anchor.char_end,
                    "name": getattr(doc, "name", None),
                    "doc_type": getattr(doc, "doc_type", None).value
                    if hasattr(doc, "doc_type") and doc.doc_type
                    else None,
                    "file_type": getattr(doc, "file_type", None).value
                    if hasattr(doc, "file_type") and doc.file_type
                    else None,
                    "vector_int8": quantized_vector,
                    "vector_scale": quantized_scale,
                    **self._vector_model_metadata(),
                }
            )
        return records

    def embed_artifact_content(
        self,
        doc,
        text: str,
        *,
        artifact_id: str,
        embedding_scope: str = "translation",
        max_chars: int = 512,
        overlap_chars: int = 80,
    ) -> int:
        """Embed an artifact's content with a scoped label.

        Translations and other derived representations are stored in the same
        LanceDB embeddings table but with ``embedding_scope`` set to the
        artifact type (e.g. ``"translation"``).  This makes them searchable
        alongside the original document while keeping the passage-scope
        vectors untouched.  Previous artifact-scope vectors for the same
        *artifact_id* are removed before inserting new ones (re-translation
        idempotency).

        Args:
            doc: The source Document the artifact belongs to.
            text: The artifact content to embed (e.g. translated text).
            artifact_id: The Artifact.id — used to scope deletion so
                re-translations replace, not accumulate.
            embedding_scope: Scope label for the vectors (default
                ``"translation"``).
            max_chars: Passage chunk size.
            overlap_chars: Overlap between chunks.

        Returns:
            Number of passage records inserted.
        """
        if not text or len(text.strip()) < 10:
            return 0

        document_id = getattr(doc, "id", None)
        if not document_id:
            return 0

        # Build passage units from the artifact text, keyed to the source
        # document so search finds the document when querying by translation.
        units = split_text_passages(
            text,
            document_id=document_id,
            page_id=document_id,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        # Override the default "passage" kind with the artifact scope.
        units = [
            EmbeddableUnit(
                id=f"{u.id}:{embedding_scope}",
                text=u.text,
                anchor=u.anchor,
                kind=embedding_scope,
            )
            for u in units
        ]
        if not units:
            return 0

        # Embed all passages in one forward pass.
        if len(units) == 1:
            vectors = [self._embed_text(units[0].text, role="passage")]
        else:
            vectors = self._embed_texts([u.text for u in units], role="passage")

        records = []
        for unit, vector in zip(units, vectors):
            stored_vector = vector
            quantized_vector: list[int] | None = None
            quantized_scale: float | None = None
            if self._use_int8_embeddings():
                quantized_vector, quantized_scale = _quantize_int8(vector)
                stored_vector = _dequantize_int8(quantized_vector, quantized_scale)

            records.append(
                {
                    "id": unit.id,
                    "document_id": document_id,
                    "text": unit.text,
                    "vector": stored_vector,
                    "embedding_scope": embedding_scope,
                    "passage_id": unit.id,
                    "page_id": document_id,
                    "char_start": unit.anchor.char_start,
                    "char_end": unit.anchor.char_end,
                    "artifact_id": artifact_id,
                    "name": getattr(doc, "name", None),
                    "doc_type": (
                        getattr(doc, "doc_type", None).value
                        if hasattr(doc, "doc_type") and doc.doc_type
                        else None
                    ),
                    "file_type": (
                        getattr(doc, "file_type", None).value
                        if hasattr(doc, "file_type") and doc.file_type
                        else None
                    ),
                    "vector_int8": quantized_vector,
                    "vector_scale": quantized_scale,
                    **self._vector_model_metadata(),
                }
            )

        # Delete previous vectors for this artifact (re-translation replaces).
        with self._lock:
            self._delete_artifact_embedding_rows(artifact_id, embedding_scope)
            self.save_vectors(EMBEDDINGS_TABLE, records)
        return len(records)

    def _delete_artifact_embedding_rows(
        self, artifact_id: str, embedding_scope: str
    ) -> None:
        """Delete embedding rows scoped to one artifact (re-translation replaces).

        Uses a compound filter on ``embedding_scope`` + ``artifact_id`` so the
        document's own passage vectors are never touched.
        """
        if EMBEDDINGS_TABLE not in self._lance_tables():
            return
        safe_id = artifact_id.replace("'", "''")
        safe_scope = embedding_scope.replace("'", "''")
        table = self.lance.open_table(EMBEDDINGS_TABLE)
        table.delete(f"artifact_id = '{safe_id}' AND embedding_scope = '{safe_scope}'")

    def delete_artifact_embeddings(
        self, artifact_id: str, embedding_scope: str = "translation"
    ) -> bool:
        """Public API: remove all embedding vectors for a given artifact.

        Called when a translation artifact is deleted (undo / cleanup) so
        stale vectors don't linger in search results.  Returns True if the
        table existed (even if no rows matched).
        """
        try:
            if EMBEDDINGS_TABLE not in self._lance_tables():
                return False
            with self._lock:
                self._delete_artifact_embedding_rows(artifact_id, embedding_scope)
            return True
        except Exception as e:
            error = handle_error(
                e,
                default_message=f"Failed to delete artifact embeddings for {artifact_id}",
                category=ErrorCategory.DATABASE,
                context={"artifact_id": artifact_id},
            )
            logger.warning("Artifact embedding deletion failed: %s", error.message)
            return False

    def entity_embedding_text(self, entity) -> str:
        """Compose the canonical text stored/searched for one entity."""
        entity_type = (
            entity.entity_type.value
            if getattr(entity, "entity_type", None) is not None
            else None
        )
        aliases = ", ".join(entity.aliases or [])
        return _join_text_parts(
            [
                entity.canonical_name,
                aliases,
                entity.description,
                entity_type,
            ]
        )

    def claim_embedding_text(self, claim) -> str:
        """Compose the canonical text stored/searched for one claim."""
        subject = claim.subject_canonical or claim.svo_subject
        predicate = (
            claim.predicate_verb or claim.svo_verb or claim.predicate_canonical
        )
        obj = claim.object_phrase or claim.svo_object
        source_text = claim.source_excerpt or claim.text
        return _join_text_parts(
            [
                subject,
                predicate,
                obj,
                source_text,
            ]
        )

    def embed_entities(self, entities, *, batch_size: int = 256) -> int:
        """Write entity embeddings into the canonical LanceDB table.

        Processes entities in batches of ``batch_size`` (#2233) to bound
        peak RAM usage when indexing large corpora.
        """
        entities = [entity for entity in entities if entity is not None]
        if not entities:
            return 0

        total = 0
        for batch_start in range(0, len(entities), batch_size):
            batch = entities[batch_start : batch_start + batch_size]
            texts = [self.entity_embedding_text(entity) for entity in batch]
            vectors = self._embed_texts(texts)
            records = [
                {
                    "id": entity.id,
                    "text": text,
                    "canonical_name": entity.canonical_name,
                    "aliases_text": ", ".join(entity.aliases or []),
                    "description": entity.description or "",
                    "entity_type": entity.entity_type.value if entity.entity_type else None,
                    "vector": vector,
                    **self._vector_model_metadata(),
                }
                for entity, text, vector in zip(batch, texts, vectors)
            ]
            self.save_vectors(KG_ENTITY_EMBEDDINGS_TABLE, records, replace=True)
            total += len(records)
        return total

    def embed_claims(self, claims, *, batch_size: int = 256) -> int:
        """Write claim embeddings into the canonical LanceDB table.

        Processes claims in batches of ``batch_size`` (#2233) to bound
        peak RAM usage when indexing large corpora.
        """
        claims = [claim for claim in claims if claim is not None]
        if not claims:
            return 0

        total = 0
        for batch_start in range(0, len(claims), batch_size):
            batch = claims[batch_start : batch_start + batch_size]
            texts = [self.claim_embedding_text(claim) for claim in batch]
            vectors = self._embed_texts(texts)
            records = [
                {
                    "id": claim.id,
                    "text": text,
                    "source_text": claim.source_excerpt or claim.text,
                    "claim_text": claim.text,
                    "subject": claim.subject_canonical or claim.svo_subject or "",
                    "predicate": (
                        claim.predicate_verb
                        or claim.svo_verb
                        or claim.predicate_canonical
                        or ""
                    ),
                    "object": claim.object_phrase or claim.svo_object or "",
                    "claim_type": claim.claim_type.value if claim.claim_type else "",
                    "curation_state": (
                        claim.curation_state.value if claim.curation_state else ""
                    ),
                    "vector": vector,
                    **self._vector_model_metadata(),
                }
                for claim, text, vector in zip(batch, texts, vectors)
            ]
            self.save_vectors(KG_CLAIM_EMBEDDINGS_TABLE, records, replace=True)
            total += len(records)
        return total

    def schedule_entity_embedding(self, entity) -> None:
        """Best-effort background embed for a just-written entity."""
        self._schedule_embedding_task([entity], label="entity")

    def schedule_claim_embedding(self, claim) -> None:
        """Best-effort background embed for a just-written claim."""
        self.schedule_claim_embeddings([claim])

    def schedule_claim_embeddings(self, claims) -> None:
        """Best-effort background embed for a batch of written claims."""
        self._schedule_embedding_task(list(claims), label="claim")

    def _schedule_embedding_task(self, records, *, label: str) -> None:
        """Run embedding work off-loop when possible; degrade to sync otherwise."""
        def _run() -> None:
            from fichero.db import Database

            worker_db = Database(self.path)
            try:
                if label == "entity":
                    worker_db.embed_entities(records)
                else:
                    worker_db.embed_claims(records)
            finally:
                worker_db.close()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                _run()
            except Exception as exc:
                logger.warning("Failed to auto-embed %s synchronously: %s", label, exc)
            return

        # Lazily initialise a task-tracking set (prevents GC of in-flight tasks)
        # and semaphores to bound concurrent background DB connections per loop.
        if not hasattr(self, "_bg_embedding_tasks"):
            self._bg_embedding_tasks: set = set()
        if not hasattr(self, "_bg_embedding_semaphores"):
            self._bg_embedding_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}

        bg_tasks: set = self._bg_embedding_tasks
        sem = self._bg_embedding_semaphores.get(loop)
        if sem is None:
            sem = asyncio.Semaphore(2)
            self._bg_embedding_semaphores[loop] = sem

        async def _runner() -> None:
            async with sem:
                try:
                    await asyncio.to_thread(_run)
                except Exception as exc:
                    logger.warning("Failed to auto-embed %s in background: %s", label, exc)

        task = loop.create_task(_runner())
        bg_tasks.add(task)
        task.add_done_callback(bg_tasks.discard)
