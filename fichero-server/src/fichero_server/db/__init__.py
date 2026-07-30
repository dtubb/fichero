"""
Fichero Database Layer

Simple Pythonic wrapper for DuckDB + LanceDB.
- DuckDB: Documents, artifacts, workflows, runs
- LanceDB: Vector search (embeddings)

One process owns a library read-write. DuckDB's file lock is the enforcement
boundary; opening the same library read-write from another Fichero engine
process must fail clearly instead of surfacing a raw DuckDB lock stack.

Usage:
    from fichero_server.db import db
    from fichero_server.models import Document, Artifact, Workflow, Run

    # Save
    doc = Document(name="image.jpg", path="/path/image.jpg")
    db.save(doc)

    # Get by ID
    doc = db.get(Document, "abc123")

    # Query
    pages = db.query(Document, parent_id=doc.id, doc_type="page")

    # Semantic search
    results = db.search("handwritten letters from 1920s")

    # Create embedding for a document
    db.embed(doc)

    # Artifacts
    artifact = Artifact(document_id=doc.id, artifact_type="transcription", content="...")
    db.save(artifact)

    # Delete
    db.delete(doc)
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import UnionType
from typing import TYPE_CHECKING, TypeVar, Type, get_origin, get_args, Union, Any, Sequence, cast, Callable, Literal

if TYPE_CHECKING:
    from fichero_server.models import Artifact, Workflow
from dataclasses import dataclass, field
from datetime import datetime
import difflib
import math
import json
import logging
import os
import re
import threading
import time
import unicodedata
import duckdb
from pydantic import BaseModel
from pydantic_core import PydanticUndefinedType
from fichero_server.db.embeddings import (
    EMBEDDINGS_TABLE,
    DatabaseEmbeddingMixin,
    EmbeddingSpaceMismatchError,
    _dequantize_int8,
    _quantize_int8,
)
from fichero_server.db.manager import DatabaseManager, db_manager  # noqa: F401
from fichero_server.errors import ErrorCategory, handle_error
from fichero_server.security.path_security import resolve_under_allowed_roots

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Minimum content length to create embedding
MIN_CONTENT_LENGTH = 10

# Default embedding model (FastEmbed). Keep in sync with
# db_embeddings.DEFAULT_MODEL, the source of truth for the real embedder.
# (multilingual-e5-large until fastembed ships bge-m3 — see db_embeddings note + #2117.)
DEFAULT_MODEL = "intfloat/multilingual-e5-large"

# Valid identifier pattern for SQL column/table names
_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_DUCKDB_WRITE_CONFLICT_RETRIES = 3
_DUCKDB_WRITE_CONFLICT_BACKOFF_SECONDS = 0.01


def _vector_compaction_interval() -> int:
    """How many LanceDB appends to a table before an automatic compaction.

    At 100k images the save path does one tiny LanceDB append per document,
    leaving 100k micro-fragments that rot read performance and pile up
    compaction debt (#2542). We bound that by running ``table.optimize()``
    (compaction + prune) every N appends, NOT on every write — compacting on
    every append would be strictly worse than the problem it solves.

    0 (or a negative value) disables the automatic trigger; callers can still
    invoke ``Database.compact_vectors()`` explicitly.
    """
    raw = os.getenv("FICHERO_VECTOR_COMPACTION_INTERVAL", "200").strip()
    try:
        return int(raw)
    except ValueError:
        return 200


def _collect_folder_descendants_helper(conn: duckdb.DuckDBPyConnection, folder_id: str) -> set[str]:
    """BFS over parent_id to gather every doc under the given folder.

    Pulled out as a free function so Database.search can call it without
    growing the class API. Includes the folder itself in the returned
    set, so a search scoped to a folder also returns that folder's own
    document row when applicable.
    """
    seen: set[str] = {folder_id}
    frontier: list[str] = [folder_id]
    while frontier:
        batch = frontier
        frontier = []
        # IN-clause batch lookup; cap batches so we don't blow past
        # DuckDB's parameter limits on enormous trees.
        for chunk_start in range(0, len(batch), 500):
            chunk = batch[chunk_start: chunk_start + 500]
            placeholders = ",".join(f"$p{i}" for i in range(len(chunk)))
            params = {f"p{i}": parent_id for i, parent_id in enumerate(chunk)}
            try:
                rows = conn.execute(
                    f"SELECT id FROM documents WHERE parent_id IN ({placeholders})",
                    params,
                ).fetchall()
            except Exception:
                rows = []
            for (child_id,) in rows:
                if child_id not in seen:
                    seen.add(child_id)
                    frontier.append(child_id)
    return seen


def _validated_identifier(identifier: str, *, kind: str) -> str:
    if not _VALID_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"Invalid {kind}: {identifier!r}")
    return identifier


# Markers transcribe writes when a page is blank or unreadable. When
# page_content is just a marker, embedding it makes every marker-only
# doc share an identical vector and cluster at the top of every
# semantic query (#481 follow-up). _is_content_marker_only catches
# this so db.embed() can fall back to the doc's name.
_MARKER_PATTERNS = (
    "[sin texto]",
    "[ilegible]",
    "[illegible]",
    "[uncertain]",
    "[no text]",
    "[blank]",
    "[empty]",
    "[unreadable]",
)

_SAVED_SEARCH_NODE_KIND = "saved_search"
_SAVED_SEARCH_PROTOTYPE_KEY = "saved_search"
_SAVED_SEARCH_QUERY_ITEM_ID = "saved-search-query"
_RESEARCH_WORKSPACE_NODE_KIND = "workspace"
_RESEARCH_WORKSPACE_PROTOTYPE_KEY = "research_workspace"
_RESEARCH_PLAN_NODE_KIND = "plan"
_RESEARCH_PLAN_PROTOTYPE_KEY = "research_plan"
_RESEARCH_TASK_NODE_KIND = "task"
_RESEARCH_TASK_PROTOTYPE_KEY = "research_task"
_RESEARCH_STEP_NODE_KIND = "step"
_RESEARCH_STEP_PROTOTYPE_KEY = "research_step"
_NOTE_NODE_KIND = "note"
_NOTE_PROTOTYPE_KEY = "note"
_MILESTONE_NODE_KIND = "milestone"
_MILESTONE_PROTOTYPE_KEY = "milestone"
_ENTITY_NODE_KIND = "entity"
_ROOM_NODE_KIND = "room"
_FOLDER_PROTOTYPE_KEY = "folder"
_ROOM_PROTOTYPE_KEY = "room"
_WORKFLOW_NODE_KIND = "workflow"
_WORKFLOW_PROTOTYPE_KEY = "workflow"
# Distinct from _WORKFLOW_NODE_KIND so `query(Document, node_kind=...)` can
# tell the one locked container apart from the workflow mirrors it holds.
_WORKFLOW_CONTAINER_NODE_KIND = "workflow_container"
# Deterministic id (not a `_new_id()` uuid) so every library reopen finds the
# same locked container row instead of minting duplicates (#11 Phase 1).
_DEFAULT_WORKFLOWS_CONTAINER_ID = "system-default-workflows"

_BUILTIN_DOCUMENT_PROTOTYPE_SEEDS: tuple[dict[str, Any], ...] = (
    {
        "key": "book",
        "label": "Book",
        "color": "#0A84FF",
        "attributes": {},
    },
    {
        "key": _FOLDER_PROTOTYPE_KEY,
        "label": "Folder",
        "color": "#8E8E93",
        "attributes": {
            "container_kind": "folder",
            "supports_children": True,
        },
    },
    {
        "key": "letter",
        "label": "Letter",
        "color": "#30D158",
        "attributes": {},
    },
    {
        "key": "interview",
        "label": "Interview",
        "color": "#FF9500",
        "attributes": {},
    },
    {
        "key": "primary_source",
        "label": "Primary Source",
        "color": "#5856D6",
        "attributes": {},
    },
    {
        "key": _RESEARCH_WORKSPACE_PROTOTYPE_KEY,
        "label": "Research Workspace",
        "color": "#0A84FF",
        "parent_key": _FOLDER_PROTOTYPE_KEY,
        "attributes": {
            "status": "active",
            "created_by": "human",
            "chat_scope": "container",
            "carries_tasks": True,
            "workspace_kind": "research",
        },
    },
    {
        "key": _ROOM_PROTOTYPE_KEY,
        "label": "Room",
        "color": "#BF5AF2",
        "parent_key": _FOLDER_PROTOTYPE_KEY,
        "attributes": {
            "spatial_layout": True,
            "workspace_kind": "room",
        },
    },
    {
        "key": "secondary_source",
        "label": "Secondary Source",
        "color": "#AF52DE",
        "attributes": {},
    },
    {
        "key": "map",
        "label": "Map",
        "color": "#64D2FF",
        "attributes": {},
    },
    {
        "key": _MILESTONE_PROTOTYPE_KEY,
        "label": "Milestone",
        "color": "#FF375F",
        "attributes": {},
    },
    {
        "key": _NOTE_PROTOTYPE_KEY,
        "label": "Note",
        "color": "#FF9500",
        "attributes": {},
    },
    {
        "key": _WORKFLOW_PROTOTYPE_KEY,
        "label": "Workflow",
        "color": "#32ADE6",
        "attributes": {},
    },
    {
        "key": "translation",
        "label": "Translation",
        "color": "#FFD60A",
        "attributes": {},
    },
)

_BUILTIN_NODE_CLASS_SEEDS: tuple[dict[str, str], ...] = (
    {"key": "chapter", "label": "Chapter", "color": "#0A84FF"},
    {"key": "container", "label": "Container", "color": "#5856D6"},
    {"key": "note", "label": "Note", "color": "#FF9500"},
)


def _is_content_marker_only(text: str) -> bool:
    """True when `text` is a transcribe marker (or a few of them) and
    nothing else of substance. Case-insensitive, accent-tolerant.
    """
    folded = _fold_for_search(text)
    if not folded:
        return True
    # Strip all known markers and see if anything is left.
    residual = folded
    for marker in _MARKER_PATTERNS:
        residual = residual.replace(_fold_for_search(marker), "")
    # Whitespace + punctuation only = marker-only.
    residual = "".join(c for c in residual if c.isalnum())
    return len(residual) < 3  # 'a' / 'el' / single-token noise allowed through.


def _fold_for_search(text: str) -> str:
    """Normalise text for accent-insensitive substring search.

    Decomposes via Unicode NFD, drops combining marks (category Mn), and
    lowercases. Result: 'Quibdó' → 'quibdo', 'CAFÉ' → 'cafe', 'español'
    → 'espanol'. Critical for the Spanish + Latin manuscript corpus where
    queries are typed ASCII but the page_content is full diacritic.

    Stable + fast (no compilation, no regex). Pure-string in/out so it
    composes with pandas `str.contains` and any other str path.
    """
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).lower()


class SearchExecutionError(RuntimeError):
    """A search query failed to execute (index error, bad filter, backend fault).

    Raised instead of returning an empty result set (#4109): a FAILED search
    must never be indistinguishable from a search with no hits. Routes map
    this to HTTP 500 with the message as detail.
    """


@dataclass
class SearchAnchor:
    """Stable character-position anchor within the indexed transcript text."""

    document_id: str
    char_start: int
    char_end: int


@dataclass
class SearchExcerpt:
    """Transcript excerpt generated from the search layer's indexed text."""

    text: str
    char_start: int
    char_end: int
    match_start: int | None
    match_end: int | None
    anchor: SearchAnchor


@dataclass
class SearchResult:
    """Search result with score and document reference."""

    document_id: str
    score: float
    content_preview: str
    metadata: dict[str, Any]
    highlights: list[str] | None = None  # Highlighted text snippets
    transcript_excerpts: list[SearchExcerpt] = field(default_factory=list)
    kg_claim_ids: list[str] = field(default_factory=list)
    kg_entity_ids: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        preview = (
            self.content_preview[:50] + "..."
            if len(self.content_preview) > 50
            else self.content_preview
        )
        return f"SearchResult(id={self.document_id}, score={self.score:.3f}, preview='{preview}')"


def _fold_with_index(text: str) -> tuple[str, list[int]]:
    """Fold text for accent-insensitive matching while keeping original offsets."""
    folded_chars: list[str] = []
    index_map: list[int] = []
    for original_index, char in enumerate(text):
        for folded_char in unicodedata.normalize("NFD", char):
            if unicodedata.category(folded_char) == "Mn":
                continue
            folded_chars.append(folded_char.lower())
            index_map.append(original_index)
    return "".join(folded_chars), index_map


def _search_match_terms(query: str) -> list[str]:
    """Return ordered excerpt terms, preferring the full phrase over tokens."""
    folded = _fold_for_search(query.strip())
    if not folded:
        return []
    terms = [folded]
    terms.extend(t for t in re.findall(r"\w+", folded) if len(t) > 1)
    seen: set[str] = set()
    return [t for t in terms if not (t in seen or seen.add(t))]


def _contains_any_term(text_series, terms: list[str]):
    """Return a boolean mask matching any folded term as a substring."""
    if not terms:
        return text_series.str.contains("", regex=False, na=False) & False
    mask = text_series.str.contains(terms[0], case=False, regex=False, na=False)
    for term in terms[1:]:
        mask |= text_series.str.contains(term, case=False, regex=False, na=False)
    return mask


def _fuzzy_contains_any_term(text_series, terms: list[str], cutoff: float = 0.6):
    """Fuzzy-match each query term against words in the corpus.

    For each term, split every document's text into words and check whether
    any word is a close match using difflib's SequenceMatcher ratio. This
    catches typos like 'Aspriya' → 'Asprilla', 'Quibdo' → 'Quibdó', etc.
    The ratio threshold (``cutoff``) controls how permissive the match is:
    0.6 is a good default — strict enough to avoid false positives, loose
    enough to catch 1-2 character transpositions or deletions.

    Returns a boolean mask (same length as text_series).
    """
    if not terms:
        return text_series.str.contains("", regex=False, na=False) & False

    # Build a word→index map from the entire corpus so each term scans once.
    # Each cell is True if ANY of its words matches ANY term above cutoff.

    def _row_matches(text: str) -> bool:
        if not isinstance(text, str) or not text:
            return False
        words = text.split()
        for term in terms:
            for word in words:
                if difflib.SequenceMatcher(None, word, term).ratio() >= cutoff:
                    return True
        # Also check exact substring as a fallback (handles multi-word terms)
        for term in terms:
            if term in text:
                return True
        return False

    return text_series.apply(_row_matches)


def _bm25_scores(corpus: list[str], query_terms: list[str]) -> list[float]:
    """Compute BM25 scores for a folded corpus against folded query terms."""
    if not corpus or not query_terms:
        return [0.0 for _ in corpus]

    tokenized = [re.findall(r"\w+", doc) for doc in corpus]
    lengths = [len(tokens) for tokens in tokenized]
    avgdl = sum(lengths) / max(len(lengths), 1)
    if avgdl <= 0:
        return [0.0 for _ in corpus]

    query_tokens = [t for t in query_terms if len(t) > 1]
    if not query_tokens:
        return [0.0 for _ in corpus]

    doc_freq: dict[str, int] = {}
    for term in query_tokens:
        doc_freq[term] = sum(1 for tokens in tokenized if term in tokens)

    k1 = 1.5
    b = 0.75
    n_docs = len(tokenized)
    scores: list[float] = []
    for tokens, dl in zip(tokenized, lengths):
        tf: dict[str, int] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        score = 0.0
        for term in query_tokens:
            f = tf.get(term, 0)
            if f == 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denom = f + k1 * (1 - b + b * (dl / avgdl))
            score += idf * ((f * (k1 + 1)) / max(denom, 1e-9))
        scores.append(score)
    return scores


def _build_transcript_excerpts(
    document_id: str,
    content: str,
    query: str,
    *,
    context_chars: int = 80,
    max_excerpts: int = 3,
) -> list[SearchExcerpt]:
    """Build anchored snippets from the already-indexed search text.

    This deliberately consumes the content returned by the search layer
    (LanceDB rows / merged result content), not a fresh document lookup.
    """
    if not content:
        return []

    folded_content, index_map = _fold_with_index(content)
    spans: list[tuple[int, int]] = []
    for term in _search_match_terms(query):
        start_at = 0
        while len(spans) < max_excerpts:
            folded_start = folded_content.find(term, start_at)
            if folded_start < 0:
                break
            folded_end = folded_start + len(term)
            match_start = index_map[folded_start]
            match_end = index_map[folded_end - 1] + 1
            if not any(match_start < end and match_end > start for start, end in spans):
                spans.append((match_start, match_end))
            start_at = folded_end
        if len(spans) >= max_excerpts:
            break

    if not spans:
        preview_end = min(len(content), context_chars * 2)
        return [
            SearchExcerpt(
                text=content[:preview_end],
                char_start=0,
                char_end=preview_end,
                match_start=None,
                match_end=None,
                anchor=SearchAnchor(
                    document_id=document_id,
                    char_start=0,
                    char_end=preview_end,
                ),
            )
        ]

    excerpts: list[SearchExcerpt] = []
    for match_start, match_end in spans[:max_excerpts]:
        excerpt_start = max(0, match_start - context_chars)
        excerpt_end = min(len(content), match_end + context_chars)
        excerpts.append(
            SearchExcerpt(
                text=content[excerpt_start:excerpt_end],
                char_start=excerpt_start,
                char_end=excerpt_end,
                match_start=match_start,
                match_end=match_end,
                anchor=SearchAnchor(
                    document_id=document_id,
                    char_start=match_start,
                    char_end=match_end,
                ),
            )
        )
    return excerpts


def _search_result_preview(
    content: str,
    excerpts: list[SearchExcerpt],
    *,
    max_chars: int = 200,
) -> str:
    """Prefer the first actual match excerpt over the raw leading content preview."""
    for excerpt in excerpts:
        if excerpt.match_start is not None and excerpt.match_end is not None:
            return excerpt.text
    return content[:max_chars] + "..." if len(content) > max_chars else content


class Database(DatabaseEmbeddingMixin):
    """Simple Pythonic wrapper for DuckDB + LanceDB."""

    def __init__(self, path: str | Path | None = None):
        """
        Initialize database connection.

        Args:
            path: Path to database file. Defaults to ~/Library/Application Support/com.fichero.fichero/library.duckdb
        """
        if path is None:
            from fichero_server.db.storage import settings

            path = settings.db_path
        else:
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = self._connect()
        self.duck = self.conn  # Alias used by ActionStore and other direct SQL callers
        self._lance_path = path.parent / "vectors"
        self._lance_db = None  # Lazy init
        self._embedder = None  # Lazy init
        self._embedding_model_name = None
        self._tables_created: set[str] = set()
        self._lock = threading.RLock()
        self._transaction_gate = threading.RLock()
        self._tx_state = threading.local()
        # Per-table count of LanceDB appends since the last compaction. Drives
        # the bounded auto-compaction trigger in save_vectors (#2542).
        self._vector_append_counts: dict[str, int] = {}

        # Migrate tables if needed
        from fichero_server.db.migrations.schema import (
            migrate_canvas_layout_table,
            migrate_document_table,
            migrate_workflow_table,
            migrate_saved_search_table,
            migrate_provider_refs_table,
            migrate_known_libraries_table,
            migrate_library_entity_types_table,
            migrate_spatial_node_layout_fields,
            migrate_references_table,
            migrate_reference_provenance_table,
        )
        migrate_document_table(self.conn)
        migrate_workflow_table(self.conn)
        migrate_saved_search_table(self.conn)
        migrate_provider_refs_table(self.conn)
        migrate_known_libraries_table(self.conn)
        migrate_library_entity_types_table(self.conn)
        migrate_canvas_layout_table(self.conn)
        migrate_spatial_node_layout_fields(self.conn)
        migrate_references_table(self.conn)
        migrate_reference_provenance_table(self.conn)
        self._materialize_schema()
        self._seed_builtin_document_prototypes()
        self._seed_builtin_node_classes()
        self._backfill_claim_links_to_library_links()
        self._backfill_filed_entity_documents()
        self._backfill_note_documents()
        self._backfill_milestone_documents()
        self._backfill_saved_search_documents()
        self._backfill_spatial_room_documents()
        self._backfill_research_workspace_documents()
        self._backfill_research_plan_task_step_documents()
        # NOTE: no unconditional `_seed_default_workflows_container()` call
        # here — unlike the backfills above, the container has no underlying
        # row of its own to backfill from. It's created lazily, the first
        # time an `is_system=True` Workflow is saved (see
        # `_save_workflow_document`), so a library with zero default
        # workflows doesn't grow a permanent empty "Default Workflows" node
        # (and so raw `documents` row counts in tests/tooling stay
        # predictable for libraries that never touch workflows).
        self._backfill_workflow_documents()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        """Open a DuckDB connection for this library path."""
        try:
            return duckdb.connect(str(self.path))
        except duckdb.Error as exc:
            if self._is_lock_error(exc):
                raise RuntimeError(
                    "Library already open by another Fichero engine process. "
                    "Only one engine may hold a library read-write. "
                    f"Close the other process before opening {self.path}."
                ) from exc
            raise

    @staticmethod
    def _is_invalidated_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "database has been invalidated" in message
            or "connection already closed" in message
        )

    @staticmethod
    def _is_write_conflict_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "transactioncontext error: conflict" in message
            or "conflict on update" in message
            or "transaction conflict" in message
            or "could not serialize" in message
        )

    @staticmethod
    def _is_lock_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "could not set lock on file" in message
            or "database is locked" in message
            or ("lock" in message and "duckdb" in message)
        )

    def _reconnect_after_invalidated(self) -> None:
        """Replace a DuckDB connection poisoned by a prior FatalException."""
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = self._connect()
        self.duck = self.conn
        # Table/index setup may not have run on the fresh connection in this
        # process. Force the next _ensure_table call to reconcile schema and
        # drop unsafe indexes again.
        self._tables_created.clear()
        try:
            from fichero_server.db.migrations.schema import migrate_knowledge_indices

            migrate_knowledge_indices(self.conn)
        except Exception as exc:
            logger.warning(
                "Knowledge index reconciliation after reconnect failed: %s",
                exc,
            )
        self._materialize_schema()

    def _all_schema_models(self) -> tuple[type[BaseModel], ...]:
        from fichero_server.models.hermeneutics import (
            HermeneuticCircleState,
            Interpretation,
            InterpretiveFramework,
            PatternInstance,
        )
        from fichero_server.models.knowledge import (
            Annotation,
            BookStructureNode,
            ClaimMergeAudit,
            ClaimSuppressionRule,
            ClassificationValue,
            DocumentCitation,
            EntityMatchCandidate,
            EntityResolutionRule,
            KnowledgeClaim,
            KnowledgeClaimLink,
            KnowledgeEntity,
            KnowledgePredictionRun,
            LibraryEntityType,
            LibraryItemLink,
            Milestone,
            MutationLog,
            Note as KnowledgeNote,
            Project,
            ProjectInclusion,
            Reference,
            ReferenceProvenance,
        )
        from fichero_server.models import (
            ActionAudit,
            AgentNote,
            Artifact,
            Conversation,
            Document,
            DocumentNote,
            ImageEditChain,
            KnownLibrary,
            Note as LegacyNote,
            ProviderRef,
            Run,
            SavedSearch,
            Trace,
            Workflow,
        )
        from fichero_server.models.research import (
            ResearchChecklist,
            ResearchNote,
            ResearchPlan,
            ResearchProject,
            ResearchStep,
            ResearchTask,
            SearchSource,
        )
        from fichero_server.models.canvas import (
            CanvasLayout,
            CanvasItem,
            SpatialConnection,
            SpatialNode,
            SpatialRoom,
            SpatialViewport,
        )

        return (
            ActionAudit,
            AgentNote,
            Annotation,
            Artifact,
            BookStructureNode,
            CanvasLayout,
            CanvasItem,
            ClaimMergeAudit,
            ClaimSuppressionRule,
            ClassificationValue,
            Conversation,
            Document,
            DocumentCitation,
            DocumentNote,
            EntityMatchCandidate,
            EntityResolutionRule,
            HermeneuticCircleState,
            ImageEditChain,
            Interpretation,
            InterpretiveFramework,
            KnownLibrary,
            KnowledgeClaim,
            KnowledgeClaimLink,
            KnowledgeEntity,
            KnowledgeNote,
            KnowledgePredictionRun,
            LegacyNote,
            LibraryEntityType,
            LibraryItemLink,
            Milestone,
            MutationLog,
            PatternInstance,
            Project,
            ProjectInclusion,
            ProviderRef,
            Reference,
            ReferenceProvenance,
            ResearchChecklist,
            ResearchNote,
            ResearchPlan,
            ResearchProject,
            ResearchStep,
            ResearchTask,
            Run,
            SavedSearch,
            SearchSource,
            SpatialConnection,
            SpatialNode,
            SpatialRoom,
            SpatialViewport,
            Trace,
            Workflow,
        )

    def _materialize_schema(self) -> None:
        """Create and reconcile all persisted tables/columns eagerly."""
        for model in self._all_schema_models():
            self._tables_created.discard(self._table_name(model))
            self._ensure_table(model)

    def _execute(self, sql: str, params: Any | None = None, fetch: str | None = None):
        """Execute SQL, retrying bounded DuckDB transient write conflicts.

        When ``fetch`` is ``"all"`` or ``"one"`` the fetch happens INSIDE the
        lock, so a SELECT's rows are materialized before another thread can use
        the one shared connection (#2508). ``fetch=None`` returns the raw cursor
        (legacy in-method callers that fetch immediately under their own lock).
        """
        self._ensure_transaction_started()
        with self._transaction_gate:
            with self._lock:
                for attempt in range(_DUCKDB_WRITE_CONFLICT_RETRIES + 1):
                    try:
                        cur = (
                            self.conn.execute(sql)
                            if params is None
                            else self.conn.execute(sql, params)
                        )
                        if fetch == "all":
                            return cur.fetchall()
                        if fetch == "one":
                            return cur.fetchone()
                        return cur
                    except duckdb.Error as exc:
                        if self._is_invalidated_error(exc):
                            logger.warning(
                                "DuckDB connection for %s was invalidated; reopening and retrying",
                                self.path,
                            )
                            self._reconnect_after_invalidated()
                            continue
                        if not self._is_write_conflict_error(exc):
                            raise
                        if attempt >= _DUCKDB_WRITE_CONFLICT_RETRIES:
                            raise RuntimeError(
                                "DuckDB write conflict did not resolve after "
                                f"{_DUCKDB_WRITE_CONFLICT_RETRIES} retries for {self.path}. "
                                "The library is receiving concurrent writes; retry the operation."
                            ) from exc
                        delay = _DUCKDB_WRITE_CONFLICT_BACKOFF_SECONDS * (attempt + 1)
                        logger.warning(
                            "DuckDB write conflict for %s; retrying in %.3fs (%s/%s)",
                            self.path,
                            delay,
                            attempt + 1,
                            _DUCKDB_WRITE_CONFLICT_RETRIES,
                        )
                        time.sleep(delay)
                raise RuntimeError("DuckDB execution retry loop exited unexpectedly")

    # =========================================================================
    # Direct-SQL seam for the store modules (#2508)
    # -------------------------------------------------------------------------
    # The action/cache/checkpoint/activity/scheduler/task stores run raw SQL.
    # Under the single shared connection (#2508) every such statement MUST be
    # serialized on this Database's lock. These helpers are the only sanctioned
    # way for those stores to touch SQL — they replace ``db.duck.execute(...)``
    # (which ran outside the lock). The fetch happens INSIDE the lock so a
    # SELECT's rows are materialized before another thread can use the
    # connection. No new SQL — same statements, now serialized.
    # =========================================================================

    def execute(self, sql: str, params: Any | None = None):
        """Run a statement for its side effect (DDL/DML), serialized on the
        shared lock. Returns the cursor; do NOT fetch off it lazily — use
        ``execute_fetchall`` / ``execute_fetchone`` when you need rows."""
        return self._execute(sql, params)

    def execute_fetchall(self, sql: str, params: Any | None = None) -> list:
        """Execute + ``fetchall`` atomically under the lock (#2508)."""
        return self._execute(sql, params, fetch="all")

    def execute_fetchone(self, sql: str, params: Any | None = None):
        """Execute + ``fetchone`` atomically under the lock (#2508)."""
        return self._execute(sql, params, fetch="one")

    def _execute_fetch_with_columns(
        self,
        sql: str,
        params: Any | None = None,
        *,
        fetch: Literal["one", "all"] = "all",
    ) -> tuple[Any, list[str]]:
        """Fetch rows and column names atomically under the shared connection lock."""
        self._ensure_transaction_started()
        with self._transaction_gate:
            with self._lock:
                for attempt in range(_DUCKDB_WRITE_CONFLICT_RETRIES + 1):
                    try:
                        cur = (
                            self.conn.execute(sql)
                            if params is None
                            else self.conn.execute(sql, params)
                        )
                        columns = [desc[0] for desc in cur.description]
                        rows = cur.fetchone() if fetch == "one" else cur.fetchall()
                        return rows, columns
                    except duckdb.Error as exc:
                        if self._is_invalidated_error(exc):
                            logger.warning(
                                "DuckDB connection for %s was invalidated; reopening and retrying",
                                self.path,
                            )
                            self._reconnect_after_invalidated()
                            continue
                        if not self._is_write_conflict_error(exc):
                            raise
                        if attempt >= _DUCKDB_WRITE_CONFLICT_RETRIES:
                            raise RuntimeError(
                                "DuckDB write conflict did not resolve after "
                                f"{_DUCKDB_WRITE_CONFLICT_RETRIES} retries for {self.path}. "
                                "The library is receiving concurrent writes; retry the operation."
                            ) from exc
                        delay = _DUCKDB_WRITE_CONFLICT_BACKOFF_SECONDS * (attempt + 1)
                        logger.warning(
                            "DuckDB write conflict for %s; retrying in %.3fs (%s/%s)",
                            self.path,
                            delay,
                            attempt + 1,
                            _DUCKDB_WRITE_CONFLICT_RETRIES,
                        )
                        time.sleep(delay)
                raise RuntimeError("DuckDB execution retry loop exited unexpectedly")

    @property
    def in_transaction(self) -> bool:
        return getattr(self._tx_state, "depth", 0) > 0

    def add_after_commit_hook(self, hook: Callable[[], None]) -> None:
        if self.in_transaction:
            hooks = getattr(self._tx_state, "after_commit_hooks", None)
            if hooks is None:
                hooks = []
                self._tx_state.after_commit_hooks = hooks
            hooks.append(hook)
            return
        hook()

    def add_after_rollback_hook(self, hook: Callable[[], None]) -> None:
        """Run ``hook`` only if the current outer transaction rolls back."""
        if not self.in_transaction:
            raise RuntimeError("after-rollback hooks require an active transaction")
        hooks = getattr(self._tx_state, "after_rollback_hooks", None)
        if hooks is None:
            hooks = []
            self._tx_state.after_rollback_hooks = hooks
        hooks.append(hook)

    def _ensure_transaction_started(self) -> None:
        if not self.in_transaction or getattr(self._tx_state, "started", False):
            return
        self._transaction_gate.acquire()
        try:
            with self._lock:
                self.conn.execute("BEGIN TRANSACTION")
            self._tx_state.started = True
        except Exception:
            self._transaction_gate.release()
            raise

    @contextmanager
    def transaction(self):
        """Run a unit of work inside one serialized DuckDB transaction."""
        outermost = not self.in_transaction
        depth = getattr(self._tx_state, "depth", 0) + 1
        self._tx_state.depth = depth
        if outermost:
            self._tx_state.started = False
            self._tx_state.after_commit_hooks = []
            self._tx_state.after_rollback_hooks = []

        hooks: list[Callable[[], None]] = []
        started = False
        try:
            yield
            started = bool(getattr(self._tx_state, "started", False))
            if outermost and started:
                with self._lock:
                    self.conn.execute("COMMIT")
                hooks = list(getattr(self._tx_state, "after_commit_hooks", []))
        except Exception:
            started = bool(getattr(self._tx_state, "started", False))
            if outermost and started:
                with self._lock:
                    self.conn.execute("ROLLBACK")
            if outermost:
                hooks = list(getattr(self._tx_state, "after_rollback_hooks", []))
            raise
        finally:
            depth = getattr(self._tx_state, "depth", 1) - 1
            self._tx_state.depth = max(0, depth)
            if outermost:
                self._tx_state.after_commit_hooks = []
                self._tx_state.after_rollback_hooks = []
                self._tx_state.started = False
                if started:
                    self._transaction_gate.release()
                for hook in hooks:
                    hook()

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    @staticmethod
    def _dump_row(obj: BaseModel) -> dict[str, Any]:
        """Serialise a Pydantic instance into a DuckDB-ready column dict.

        Excludes computed fields and JSON-encodes nested structures, exactly as
        the single-row ``save`` path does. Shared with ``save_many`` so the
        batched path produces byte-identical column values (#2542).
        """
        model_cls = type(obj)
        computed_keys = (
            set(model_cls.model_computed_fields.keys())
            if hasattr(model_cls, "model_computed_fields")
            else set()
        )
        data = obj.model_dump(exclude=computed_keys)

        # Convert dict/list/tuple/Path fields for DuckDB (recursively handle
        # nested Pydantic models with datetimes).
        def _json_safe(value):
            if isinstance(value, BaseModel):
                return _json_safe(value.model_dump())
            elif isinstance(value, dict):
                return {k: _json_safe(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                return [_json_safe(item) for item in value]
            elif isinstance(value, datetime):
                return value.isoformat()
            return value

        for key, value in data.items():
            if isinstance(value, (dict, list, tuple)):
                data[key] = json.dumps(_json_safe(value))
            elif isinstance(value, Path):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
        return data

    @staticmethod
    def _upsert_sql(sql_table: str, cols: list[str], placeholders: str) -> str:
        """Build the DuckDB ON CONFLICT upsert statement for ``cols``.

        ``placeholders`` is the pre-rendered VALUES clause body (named ``$col``
        for single-row execute, positional ``?`` for executemany batches).
        """
        col_names = ", ".join(cols)
        values = placeholders if placeholders.startswith("(") else f"({placeholders})"
        update_cols = [c for c in cols if c != "id"]
        if update_cols:
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            return (
                f"INSERT INTO {sql_table} ({col_names}) VALUES {values} "
                f"ON CONFLICT (id) DO UPDATE SET {set_clause}"
            )
        # Edge case: a table whose only column is `id` — ON CONFLICT has
        # nothing to update, so DO NOTHING is the right semantics.
        return (
            f"INSERT INTO {sql_table} ({col_names}) VALUES {values} "
            f"ON CONFLICT (id) DO NOTHING"
        )

    def save(self, obj: BaseModel, auto_embed: bool = False) -> None:
        """Save a Pydantic object (insert or update by ID).

        Args:
            obj: Pydantic model instance to save
            auto_embed: If True, create embedding when obj has page_content
        """
        if type(obj).__name__ == "KnowledgeEntity":
            self._validate_entity_parent(obj)
        if type(obj).__name__ == "Note" and hasattr(obj, "body"):
            self._validate_note_parent(obj)
        if type(obj).__name__ == "Milestone":
            self._validate_milestone_parent(obj)

        sql_table = self._sql_table_name(obj)
        self._ensure_table(type(obj))

        data = self._dump_row(obj)

        # Build a native DuckDB UPSERT (#1120).
        #
        # Earlier versions of this method used `INSERT OR REPLACE INTO`,
        # which DuckDB documents but implements as a column-store append
        # path that is NOT a reliable PK upsert. Under sustained load
        # against tables that gained columns mid-flight, the append path raises:
        #
        #   Constraint Error: PRIMARY KEY or UNIQUE constraint violation:
        #     duplicate key "<id>"
        #
        # which then escalates to:
        #
        #   INTERNAL Error: Failed to append to PRIMARY_<table>_0
        #
        # — a `FatalException` that tears down the whole connection and,
        # with FastAPI in front, the whole uvicorn process. (#1120
        # crash signature.)
        #
        # `INSERT ... ON CONFLICT (id) DO UPDATE SET ... = EXCLUDED.*`
        # is DuckDB's first-class UPSERT and goes through the proper
        # update path on conflict — no append-side PK collision. The
        # typed save contract ("give me a Pydantic instance and I'll
        # persist it; idempotent on id") is unchanged; callers see no
        # SQL state.
        # ON CONFLICT requires that the target table actually has `id` as
        # the conflict key, which is true for every model in this layer
        # (PRIMARY KEY (id) is set in `_ensure_table`). The
        # SET <c> = EXCLUDED.<c> clause covers every non-key column;
        # without it, ON CONFLICT degenerates to DO NOTHING and we'd
        # silently drop updates.
        cols = list(data.keys())
        placeholders = ", ".join(f"${c}" for c in cols)
        sql = self._upsert_sql(sql_table, cols, placeholders)

        self._execute(sql, data)

        if type(obj).__name__ == "SavedSearch":
            self._save_saved_search_document(obj)
        if type(obj).__name__ == "KnowledgeEntity":
            self._save_filed_entity_document(obj)
        if type(obj).__name__ == "SpatialRoom":
            self._save_spatial_room_document(obj)
        if type(obj).__name__ == "ResearchProject":
            self._save_research_workspace_document(obj)
        if type(obj).__name__ == "ResearchPlan":
            self._save_research_plan_document(obj)
        if type(obj).__name__ == "ResearchTask":
            self._save_research_task_document(obj)
        if type(obj).__name__ == "ResearchStep":
            self._save_research_step_document(obj)
        if type(obj).__name__ == "Note" and hasattr(obj, "body"):
            self._save_note_document(obj)
        if type(obj).__name__ == "Milestone":
            self._save_milestone_document(obj)
        if type(obj).__name__ == "Workflow":
            self._save_workflow_document(obj)
        if type(obj).__name__ == "KnowledgeEntity":
            self.schedule_entity_embedding(obj)
        if type(obj).__name__ == "KnowledgeClaim":
            # ponytail: one shared post-save hook covers route + workflow claim writes.
            self.schedule_claim_embedding(obj)

        # Auto-embed if requested and has content
        # ponytail: bulk callers (importers / reindex loops) that save many
        # rows + embed should adopt save_many()/embed_many() instead of a
        # per-row save(auto_embed=True) loop — one transaction + one Lance
        # append amortises the single-connection lock at 100k images (#2542).
        if auto_embed and hasattr(obj, "page_content") and obj.page_content:
            self.embed(obj)

    def save_many(self, objs: Sequence[BaseModel]) -> int:
        """Batch-upsert many same-typed Pydantic objects in ONE transaction.

        Additive bulk path for the 100k-image save problem (#2542): instead of
        N separate ``save`` calls (N lock acquisitions + N autocommitted
        statements), this performs a single ``executemany`` inside one
        DuckDB transaction under the shared lock.

        Semantics:
        - All objects must be the same model type (one table, one column set).
        - All-or-nothing: a bad row aborts the whole batch (ROLLBACK) and the
          error is raised — never a silent partial write.
        - Empty input is a no-op returning 0.
        - Does NOT auto-embed; callers that also need vectors should pair this
          with ``embed_many`` so the embedding append batches too.

        Returns the number of rows written.
        """
        objs = list(objs)
        if not objs:
            return 0

        first_type = type(objs[0])
        for obj in objs:
            if type(obj) is not first_type:
                raise TypeError(
                    "save_many requires all objects to be the same model type; "
                    f"got {first_type.__name__} and {type(obj).__name__}"
                )

        sql_table = self._sql_table_name(objs[0])
        self._ensure_table(first_type)

        rows = [self._dump_row(obj) for obj in objs]
        cols = list(rows[0].keys())
        # Positional params in stable column order for every row. Missing keys
        # would silently shift columns, so demand a uniform shape up front.
        param_rows: list[list[Any]] = []
        for row in rows:
            if row.keys() != rows[0].keys():
                raise ValueError(
                    "save_many rows have inconsistent columns; refusing to "
                    "write a misaligned batch"
                )
            param_rows.append([row[c] for c in cols])

        with self._lock:
            for attempt in range(_DUCKDB_WRITE_CONFLICT_RETRIES + 1):
                try:
                    self.conn.execute("BEGIN TRANSACTION")
                    try:
                        # DuckDB's Python executemany still dispatches one UPSERT
                        # per row. Native multi-row VALUES is ~20x faster here.
                        # ponytail: 500 bounds SQL/parameter size; tune only from
                        # a measured larger-model or driver limit.
                        for start in range(0, len(param_rows), 500):
                            batch = param_rows[start : start + 500]
                            row_placeholders = f"({', '.join('?' for _ in cols)})"
                            placeholders = ", ".join(row_placeholders for _ in batch)
                            sql = self._upsert_sql(sql_table, cols, placeholders)
                            self.conn.execute(sql, [value for row in batch for value in row])
                    except Exception:
                        # Abort the partial batch — no half-written rows.
                        self.conn.execute("ROLLBACK")
                        raise
                    self.conn.execute("COMMIT")
                    return len(param_rows)
                except duckdb.Error as exc:
                    if self._is_invalidated_error(exc):
                        logger.warning(
                            "DuckDB connection for %s was invalidated during "
                            "save_many; reopening and retrying",
                            self.path,
                        )
                        self._reconnect_after_invalidated()
                        continue
                    if not self._is_write_conflict_error(exc):
                        raise
                    if attempt >= _DUCKDB_WRITE_CONFLICT_RETRIES:
                        raise RuntimeError(
                            "DuckDB write conflict did not resolve after "
                            f"{_DUCKDB_WRITE_CONFLICT_RETRIES} retries for "
                            f"{self.path} (save_many)."
                        ) from exc
                    delay = _DUCKDB_WRITE_CONFLICT_BACKOFF_SECONDS * (attempt + 1)
                    time.sleep(delay)
            raise RuntimeError("save_many retry loop exited unexpectedly")

    def _legacy_all_saved_search_rows(self) -> list[BaseModel]:
        """Read SavedSearch rows from the legacy table without node folding."""
        from fichero_server.models import SavedSearch

        sql_table = self._sql_table_name(SavedSearch)
        self._ensure_table(SavedSearch)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(SavedSearch, columns, row)) is not None
        ]

    def _legacy_all_research_project_rows(self) -> list[BaseModel]:
        """Read legacy ResearchProject rows without node folding."""
        from fichero_server.models.research import ResearchProject

        sql_table = self._sql_table_name(ResearchProject)
        self._ensure_table(ResearchProject)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(ResearchProject, columns, row)) is not None
        ]

    def _legacy_all_research_rows(self, model_cls: type[BaseModel]) -> list[BaseModel]:
        """Read legacy research rows without node folding."""
        sql_table = self._sql_table_name(model_cls)
        self._ensure_table(model_cls)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(model_cls, columns, row)) is not None
        ]

    def _legacy_all_spatial_room_rows(self) -> list[BaseModel]:
        """Read legacy SpatialRoom rows without node folding."""
        from fichero_server.models.canvas import SpatialRoom

        sql_table = self._sql_table_name(SpatialRoom)
        self._ensure_table(SpatialRoom)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(SpatialRoom, columns, row)) is not None
        ]

    def _legacy_all_knowledge_entity_rows(self) -> list[BaseModel]:
        """Read KnowledgeEntity rows without any node-tree bridge logic."""
        from fichero_server.models.knowledge import KnowledgeEntity

        sql_table = self._sql_table_name(KnowledgeEntity)
        self._ensure_table(KnowledgeEntity)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(KnowledgeEntity, columns, row)) is not None
        ]

    def _legacy_all_note_rows(self) -> list[BaseModel]:
        """Read Note rows without any node-tree bridge logic."""
        from fichero_server.models.knowledge import Note

        sql_table = self._sql_table_name(Note)
        self._ensure_table(Note)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(Note, columns, row)) is not None
        ]

    def _legacy_all_milestone_rows(self) -> list[BaseModel]:
        """Read Milestone rows without any node-tree bridge logic."""
        from fichero_server.models.knowledge import Milestone

        sql_table = self._sql_table_name(Milestone)
        self._ensure_table(Milestone)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(Milestone, columns, row)) is not None
        ]

    def _legacy_all_workflow_rows(self) -> list[BaseModel]:
        """Read Workflow rows without any node-tree bridge logic."""
        from fichero_server.models import Workflow

        sql_table = self._sql_table_name(Workflow)
        self._ensure_table(Workflow)
        with self._lock:
            rows = self._execute(f"SELECT * FROM {sql_table}").fetchall()
            columns = [desc[0] for desc in self.conn.description]
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(Workflow, columns, row)) is not None
        ]

    @staticmethod
    def _saved_search_from_document(doc: Any) -> BaseModel:
        """Hydrate a SavedSearch view-model from its folded document node."""
        from fichero_server.models import SavedSearch

        if doc.node_kind != _SAVED_SEARCH_NODE_KIND:
            raise ValueError(f"Document {doc.id} is not a saved-search node")

        attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
        query = attrs.get("query")
        if not isinstance(query, str) or not query.strip():
            for item in doc.curated_items or []:
                if (
                    isinstance(item, dict)
                    and item.get("id") == _SAVED_SEARCH_QUERY_ITEM_ID
                    and isinstance(item.get("query"), str)
                    and item["query"].strip()
                ):
                    query = item["query"]
                    break
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Saved-search node {doc.id} is missing its query payload")

        return SavedSearch(
            id=doc.id,
            query=query,
            is_smart_search=bool(attrs.get("is_smart_search", True)),
            filters=attrs.get("filters"),
            search_type=str(attrs.get("search_type", "hybrid")),
            sort_by=str(attrs.get("sort_by", "relevance")),
            sort_direction=str(attrs.get("sort_direction", "desc")),
            created_by=str(attrs.get("created_by", "system")),
            folder_path=str(attrs.get("folder_path", "/")),
            sort_order=doc.sort_order,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    def _all_folded_saved_searches(self) -> list[BaseModel]:
        """Return all saved searches from their folded document nodes."""
        from fichero_server.models import Document

        docs = self.query(Document, node_kind=_SAVED_SEARCH_NODE_KIND)
        return [self._saved_search_from_document(doc) for doc in docs]

    @staticmethod
    def _spatial_room_from_document(db: "Database", doc: Any) -> BaseModel:
        """Hydrate a SpatialRoom view-model from its folded room document."""
        from fichero_server.models.canvas import RoomType, SpatialRoom

        if doc.prototype_key != _ROOM_PROTOTYPE_KEY:
            raise ValueError(f"Document {doc.id} is not a room node")

        attrs = db._effective_prototype_attributes(doc)
        description = attrs.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"Room {doc.id} has invalid description payload")
        room_type_value = attrs.get("room_type", RoomType.research.value)
        try:
            room_type = RoomType(room_type_value)
        except Exception as exc:
            raise ValueError(
                f"Room {doc.id} has invalid room_type payload: {room_type_value!r}"
            ) from exc
        owner_id = attrs.get("owner_id", "user")
        if not isinstance(owner_id, str):
            raise ValueError(f"Room {doc.id} has invalid owner_id payload")
        metadata = attrs.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Room {doc.id} has invalid metadata payload")

        return SpatialRoom(
            id=doc.id,
            name=doc.name,
            description=description,
            room_type=room_type,
            owner_id=owner_id,
            metadata=metadata,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    def _all_folded_spatial_rooms(self) -> list[BaseModel]:
        """Return all mind-palace rooms from their folded document nodes."""
        from fichero_server.models import Document

        docs = self.query(Document, node_kind=_ROOM_NODE_KIND)
        return [self._spatial_room_from_document(self, doc) for doc in docs]

    def _validate_entity_parent(self, entity: BaseModel) -> None:
        """Filed entities must point at a live folder node."""
        parent_id = getattr(entity, "parent_id", None)
        if parent_id is None:
            return

        from fichero_server.models import DocType, Document

        parent = self.get(Document, parent_id)
        if parent is None or getattr(parent, "deleted_at", None) is not None:
            raise ValueError(f"Parent not found: {parent_id}")
        if parent.doc_type != DocType.folder:
            raise ValueError(f"Parent is not a folder: {parent_id}")

    def _validate_document_parent(
        self,
        parent_id: str,
        *,
        allowed_doc_types: set[Any] | None = None,
        expected_kind: str,
    ) -> Any:
        """Resolve and validate a live document parent."""
        from fichero_server.models import Document

        parent = self.get(Document, parent_id)
        if parent is None or getattr(parent, "deleted_at", None) is not None:
            raise ValueError(f"{expected_kind} parent not found: {parent_id}")
        if allowed_doc_types is not None and parent.doc_type not in allowed_doc_types:
            raise ValueError(f"{expected_kind} parent has invalid doc_type: {parent_id}")
        return parent

    def _note_parent_id(self, note: BaseModel) -> str | None:
        """Resolve a note's containment parent without changing the route schema."""
        folder_id = getattr(note, "folder_id", None)
        page_id = getattr(note, "page_id", None)
        if folder_id and page_id and folder_id != page_id:
            raise ValueError(
                f"Note {note.id} cannot target both folder_id={folder_id} and page_id={page_id}"
            )
        return folder_id or page_id

    def _validate_note_parent(self, note: BaseModel) -> None:
        """Folded notes may target a folder or page, and must resolve cleanly."""
        from fichero_server.models import DocType

        parent_id = self._note_parent_id(note)
        if parent_id is None:
            return
        parent = self._validate_document_parent(
            parent_id,
            allowed_doc_types={DocType.folder, DocType.page},
            expected_kind="Note",
        )
        if getattr(note, "folder_id", None) is not None and parent.doc_type != DocType.folder:
            raise ValueError(f"Note folder parent is not a folder: {parent_id}")
        if getattr(note, "page_id", None) is not None and parent.doc_type != DocType.page:
            raise ValueError(f"Note page parent is not a page: {parent_id}")

    def _validate_milestone_parent(self, milestone: BaseModel) -> None:
        """Milestones are folder-contained content nodes."""
        from fichero_server.models import DocType

        self._validate_document_parent(
            milestone.parent_id,
            allowed_doc_types={DocType.folder},
            expected_kind="Milestone",
        )

    def _seed_builtin_document_prototypes(self) -> None:
        """Ensure the fold's built-in folder/container prototypes exist."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.knowledge import (
            ClassificationDimension,
            ClassificationValue,
        )

        existing = {
            value.key: value
            for value in self.query(
                ClassificationValue,
                dimension=ClassificationDimension.document_prototype,
            )
        }
        for seed in _BUILTIN_DOCUMENT_PROTOTYPE_SEEDS:
            value = existing.get(seed["key"])
            if value is None:
                self.save(
                    ClassificationValue(
                        dimension=ClassificationDimension.document_prototype,
                        key=seed["key"],
                        label=seed["label"],
                        parent_key=seed.get("parent_key"),
                        attributes=dict(seed.get("attributes", {})),
                        color=seed.get("color"),
                        is_builtin=True,
                    )
                )
                continue

            changed = False
            if value.parent_key != seed.get("parent_key"):
                value.parent_key = seed.get("parent_key")
                changed = True
            merged_attributes = dict(value.attributes or {})
            for attr_key, attr_value in seed.get("attributes", {}).items():
                if attr_key not in merged_attributes:
                    merged_attributes[attr_key] = attr_value
                    changed = True
            if value.attributes != merged_attributes:
                value.attributes = merged_attributes
                changed = True
            if value.label != seed["label"]:
                value.label = seed["label"]
                changed = True
            if value.color is None and seed.get("color") is not None:
                value.color = seed["color"]
                changed = True
            if not value.is_builtin:
                value.is_builtin = True
                changed = True
            if changed:
                value.updated_at = datetime.now()
                self.save(value)

    def _seed_builtin_node_classes(self) -> None:
        """Ensure the built-in node_class values exist in fresh DB fixtures."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.knowledge import (
            ClassificationDimension,
            ClassificationValue,
        )

        existing = {
            value.key: value
            for value in self.query(
                ClassificationValue,
                dimension=ClassificationDimension.node_class,
            )
        }
        for seed in _BUILTIN_NODE_CLASS_SEEDS:
            if seed["key"] in existing:
                continue
            self.save(
                ClassificationValue(
                    dimension=ClassificationDimension.node_class,
                    key=seed["key"],
                    label=seed["label"],
                    color=seed["color"],
                    is_builtin=True,
                )
            )

    def _effective_prototype_attributes(self, doc: Any) -> dict[str, Any]:
        """Resolve inherited prototype attributes and overlay the node payload."""
        from fichero_server.models.node_prototypes import resolve_prototype_attributes

        attrs = dict(doc.attributes) if isinstance(doc.attributes, dict) else {}
        if not doc.prototype_key:
            return attrs
        effective = resolve_prototype_attributes(self, doc.prototype_key)
        effective.update(attrs)
        return effective

    @staticmethod
    def _research_project_from_document(db: "Database", doc: Any) -> BaseModel:
        """Hydrate a ResearchProject view-model from its workspace document."""
        from fichero_server.models.research import ProjectStatus, ResearchProject

        if doc.prototype_key != _RESEARCH_WORKSPACE_PROTOTYPE_KEY:
            raise ValueError(f"Document {doc.id} is not a research workspace node")

        attrs = db._effective_prototype_attributes(doc)
        description = attrs.get("description", "")
        if not isinstance(description, str):
            raise ValueError(
                f"Research workspace {doc.id} has invalid description payload"
            )
        created_by = attrs.get("created_by", "human")
        if not isinstance(created_by, str):
            raise ValueError(
                f"Research workspace {doc.id} has invalid created_by payload"
            )
        status_value = attrs.get("status", ProjectStatus.active.value)
        try:
            status = ProjectStatus(status_value)
        except Exception as exc:
            raise ValueError(
                f"Research workspace {doc.id} has invalid status payload: {status_value!r}"
            ) from exc
        metadata = attrs.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Research workspace {doc.id} has invalid metadata payload")
        destination = attrs.get("library_destination_folder_id")
        if destination is not None and not isinstance(destination, str):
            raise ValueError(
                f"Research workspace {doc.id} has invalid destination payload"
            )

        return ResearchProject(
            id=doc.id,
            name=doc.name,
            description=description,
            status=status,
            created_by=created_by,
            library_destination_folder_id=destination,
            metadata=metadata,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    def _all_folded_research_projects(self) -> list[BaseModel]:
        """Return all research workspaces from document nodes."""
        from fichero_server.models import Document

        docs = self.query(Document, prototype_key=_RESEARCH_WORKSPACE_PROTOTYPE_KEY)
        return [self._research_project_from_document(self, doc) for doc in docs]

    @staticmethod
    def _research_plan_from_document(doc: Any) -> BaseModel:
        """Hydrate a ResearchPlan view-model from its document node."""
        from fichero_server.models.research import PlanStatus, ResearchPlan

        if doc.prototype_key != _RESEARCH_PLAN_PROTOTYPE_KEY:
            raise ValueError(f"Document {doc.id} is not a research plan node")
        if not doc.parent_id:
            raise ValueError(f"Research plan {doc.id} is missing project parent_id")

        attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
        description = attrs.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"Research plan {doc.id} has invalid description payload")
        status_value = attrs.get("status", PlanStatus.draft.value)
        try:
            status = PlanStatus(status_value)
        except Exception as exc:
            raise ValueError(
                f"Research plan {doc.id} has invalid status payload: {status_value!r}"
            ) from exc
        order_index = attrs.get("order_index", 0)
        if not isinstance(order_index, int):
            raise ValueError(f"Research plan {doc.id} has invalid order_index payload")
        metadata = attrs.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Research plan {doc.id} has invalid metadata payload")

        return ResearchPlan(
            id=doc.id,
            project_id=doc.parent_id,
            name=doc.name,
            description=description,
            status=status,
            order_index=order_index,
            metadata=metadata,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    @staticmethod
    def _research_task_from_document(doc: Any) -> BaseModel:
        """Hydrate a ResearchTask view-model from its document node."""
        from fichero_server.models.research import ResearchTask, TaskStatus

        if doc.prototype_key != _RESEARCH_TASK_PROTOTYPE_KEY:
            raise ValueError(f"Document {doc.id} is not a research task node")
        if not doc.parent_id:
            raise ValueError(f"Research task {doc.id} is missing plan parent_id")

        attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
        description = attrs.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"Research task {doc.id} has invalid description payload")
        status_value = attrs.get("status", TaskStatus.pending.value)
        try:
            status = TaskStatus(status_value)
        except Exception as exc:
            raise ValueError(
                f"Research task {doc.id} has invalid status payload: {status_value!r}"
            ) from exc
        priority = attrs.get("priority", 0)
        if not isinstance(priority, int):
            raise ValueError(f"Research task {doc.id} has invalid priority payload")
        assigned_to = attrs.get("assigned_to")
        if assigned_to is not None and not isinstance(assigned_to, str):
            raise ValueError(f"Research task {doc.id} has invalid assigned_to payload")
        metadata = attrs.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Research task {doc.id} has invalid metadata payload")
        completed_at = attrs.get("completed_at")
        if isinstance(completed_at, str):
            try:
                completed_at = datetime.fromisoformat(completed_at)
            except ValueError as exc:
                raise ValueError(
                    f"Research task {doc.id} has invalid completed_at payload"
                ) from exc
        elif completed_at is not None and not hasattr(completed_at, "isoformat"):
            raise ValueError(f"Research task {doc.id} has invalid completed_at payload")

        return ResearchTask(
            id=doc.id,
            plan_id=doc.parent_id,
            name=doc.name,
            description=description,
            status=status,
            priority=priority,
            assigned_to=assigned_to,
            metadata=metadata,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _research_step_from_document(doc: Any) -> BaseModel:
        """Hydrate a ResearchStep view-model from its document node."""
        from fichero_server.models.research import ResearchStep, StepStatus, StepTool

        if doc.prototype_key != _RESEARCH_STEP_PROTOTYPE_KEY:
            raise ValueError(f"Document {doc.id} is not a research step node")
        if not doc.parent_id:
            raise ValueError(f"Research step {doc.id} is missing task parent_id")

        attrs = doc.attributes if isinstance(doc.attributes, dict) else {}
        tool_value = attrs.get("tool")
        try:
            tool = StepTool(tool_value)
        except Exception as exc:
            raise ValueError(
                f"Research step {doc.id} has invalid tool payload: {tool_value!r}"
            ) from exc
        description = attrs.get("description", "")
        if not isinstance(description, str):
            raise ValueError(f"Research step {doc.id} has invalid description payload")
        config = attrs.get("config", {})
        if not isinstance(config, dict):
            raise ValueError(f"Research step {doc.id} has invalid config payload")
        status_value = attrs.get("status", StepStatus.pending.value)
        try:
            status = StepStatus(status_value)
        except Exception as exc:
            raise ValueError(
                f"Research step {doc.id} has invalid status payload: {status_value!r}"
            ) from exc
        result = attrs.get("result", {})
        if not isinstance(result, dict):
            raise ValueError(f"Research step {doc.id} has invalid result payload")
        error = attrs.get("error")
        if error is not None and not isinstance(error, str):
            raise ValueError(f"Research step {doc.id} has invalid error payload")
        order_index = attrs.get("order_index", 0)
        if not isinstance(order_index, int):
            raise ValueError(f"Research step {doc.id} has invalid order_index payload")
        completed_at = attrs.get("completed_at")
        if isinstance(completed_at, str):
            try:
                completed_at = datetime.fromisoformat(completed_at)
            except ValueError as exc:
                raise ValueError(
                    f"Research step {doc.id} has invalid completed_at payload"
                ) from exc
        elif completed_at is not None and not hasattr(completed_at, "isoformat"):
            raise ValueError(f"Research step {doc.id} has invalid completed_at payload")

        return ResearchStep(
            id=doc.id,
            task_id=doc.parent_id,
            tool=tool,
            label=doc.name,
            description=description,
            config=config,
            status=status,
            result=result,
            error=error,
            order_index=order_index,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            completed_at=completed_at,
        )

    def _all_folded_research_plans(self) -> list[BaseModel]:
        from fichero_server.models import Document

        docs = self.query(Document, prototype_key=_RESEARCH_PLAN_PROTOTYPE_KEY)
        return [self._research_plan_from_document(doc) for doc in docs]

    def _all_folded_research_tasks(self) -> list[BaseModel]:
        from fichero_server.models import Document

        docs = self.query(Document, prototype_key=_RESEARCH_TASK_PROTOTYPE_KEY)
        return [self._research_task_from_document(doc) for doc in docs]

    def _all_folded_research_steps(self) -> list[BaseModel]:
        from fichero_server.models import Document

        docs = self.query(Document, prototype_key=_RESEARCH_STEP_PROTOTYPE_KEY)
        return [self._research_step_from_document(doc) for doc in docs]

    def get(self, model: Type[T], id: str) -> T | None:
        """Get a single object by ID."""
        if model.__name__ == "SavedSearch":
            from fichero_server.models import Document

            doc = self.get(Document, id)
            if doc is None or doc.node_kind != _SAVED_SEARCH_NODE_KIND:
                return None
            return cast(T, self._saved_search_from_document(doc))
        if model.__name__ == "SpatialRoom":
            from fichero_server.models import Document

            doc = self.get(Document, id)
            if doc is None:
                return None
            if doc.node_kind == _ROOM_NODE_KIND and doc.prototype_key != _ROOM_PROTOTYPE_KEY:
                raise ValueError(
                    f"Document {doc.id} is a room node but has prototype {doc.prototype_key!r}"
                )
            if doc.prototype_key != _ROOM_PROTOTYPE_KEY:
                return None
            return cast(T, self._spatial_room_from_document(self, doc))
        if model.__name__ == "ResearchProject":
            from fichero_server.models import Document

            doc = self.get(Document, id)
            if doc is None or doc.prototype_key != _RESEARCH_WORKSPACE_PROTOTYPE_KEY:
                return None
            return cast(T, self._research_project_from_document(self, doc))
        if model.__name__ == "ResearchPlan":
            from fichero_server.models import Document

            doc = self.get(Document, id)
            if doc is None or doc.prototype_key != _RESEARCH_PLAN_PROTOTYPE_KEY:
                return None
            return cast(T, self._research_plan_from_document(doc))
        if model.__name__ == "ResearchTask":
            from fichero_server.models import Document

            doc = self.get(Document, id)
            if doc is None or doc.prototype_key != _RESEARCH_TASK_PROTOTYPE_KEY:
                return None
            return cast(T, self._research_task_from_document(doc))
        if model.__name__ == "ResearchStep":
            from fichero_server.models import Document

            doc = self.get(Document, id)
            if doc is None or doc.prototype_key != _RESEARCH_STEP_PROTOTYPE_KEY:
                return None
            return cast(T, self._research_step_from_document(doc))

        sql_table = self._sql_table_name(model)
        self._ensure_table(model)

        result, columns = self._execute_fetch_with_columns(
            f"SELECT * FROM {sql_table} WHERE id = $id",
            {"id": id},
            fetch="one",
        )

        if result is None:
            return None

        return self._hydrate_row(model, columns, result)

    def all(self, model: Type[T]) -> list[T]:
        """Get all objects of a type."""
        if model.__name__ == "SavedSearch":
            return cast(list[T], self._all_folded_saved_searches())
        if model.__name__ == "SpatialRoom":
            return cast(list[T], self._all_folded_spatial_rooms())
        if model.__name__ == "ResearchProject":
            return cast(list[T], self._all_folded_research_projects())
        if model.__name__ == "ResearchPlan":
            return cast(list[T], self._all_folded_research_plans())
        if model.__name__ == "ResearchTask":
            return cast(list[T], self._all_folded_research_tasks())
        if model.__name__ == "ResearchStep":
            return cast(list[T], self._all_folded_research_steps())

        sql_table = self._sql_table_name(model)
        self._ensure_table(model)

        rows, columns = self._execute_fetch_with_columns(f"SELECT * FROM {sql_table}")

        if not rows:
            return []

        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(model, columns, row)) is not None
        ]

    def query(self, model: Type[T], **filters) -> list[T]:
        """Query with simple equality filters."""
        if model.__name__ == "SavedSearch":
            rows = self._all_folded_saved_searches()
            if not filters:
                return cast(list[T], rows)
            out: list[BaseModel] = []
            for row in rows:
                matches = True
                for key, value in filters.items():
                    if not hasattr(row, key):
                        raise ValueError(f"Invalid column name: {key}")
                    if getattr(row, key) != value:
                        matches = False
                        break
                if matches:
                    out.append(row)
            return cast(list[T], out)
        if model.__name__ == "SpatialRoom":
            rows = self._all_folded_spatial_rooms()
            if not filters:
                return cast(list[T], rows)
            out: list[BaseModel] = []
            for row in rows:
                matches = True
                for key, value in filters.items():
                    if not hasattr(row, key):
                        raise ValueError(f"Invalid column name: {key}")
                    if getattr(row, key) != value:
                        matches = False
                        break
                if matches:
                    out.append(row)
            return cast(list[T], out)
        if model.__name__ == "ResearchProject":
            rows = self._all_folded_research_projects()
            if not filters:
                return cast(list[T], rows)
            out: list[BaseModel] = []
            for row in rows:
                matches = True
                for key, value in filters.items():
                    if not hasattr(row, key):
                        raise ValueError(f"Invalid column name: {key}")
                    if getattr(row, key) != value:
                        matches = False
                        break
                if matches:
                    out.append(row)
            return cast(list[T], out)
        if model.__name__ in {"ResearchPlan", "ResearchTask", "ResearchStep"}:
            folded_lookup = {
                "ResearchPlan": self._all_folded_research_plans,
                "ResearchTask": self._all_folded_research_tasks,
                "ResearchStep": self._all_folded_research_steps,
            }
            rows = folded_lookup[model.__name__]()
            if not filters:
                return cast(list[T], rows)
            out: list[BaseModel] = []
            for row in rows:
                matches = True
                for key, value in filters.items():
                    if not hasattr(row, key):
                        raise ValueError(f"Invalid column name: {key}")
                    if getattr(row, key) != value:
                        matches = False
                        break
                if matches:
                    out.append(row)
            return cast(list[T], out)

        sql_table = self._sql_table_name(model)
        self._ensure_table(model)

        if not filters:
            return self.all(model)

        # Validate column names to prevent SQL injection
        for k in filters.keys():
            if not _VALID_IDENTIFIER.match(k):
                raise ValueError(f"Invalid column name: {k}")

        # Convert enum values to their string representation for queries
        # Separate None values (need IS NULL) from regular values (need = $param)
        query_filters = {}
        where_clauses = []

        for k, v in filters.items():
            if v is None:
                # Use IS NULL for None values
                where_clauses.append(f"{k} IS NULL")
            elif hasattr(v, "value"):  # It's an enum
                query_filters[k] = v.value
                where_clauses.append(f"{k} = ${k}")
            else:
                query_filters[k] = v
                where_clauses.append(f"{k} = ${k}")

        where = " AND ".join(where_clauses)
        rows, columns = self._execute_fetch_with_columns(
            f"SELECT * FROM {sql_table} WHERE {where}",
            query_filters,
        )

        if not rows:
            return []

        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(model, columns, row)) is not None
        ]

    def query_in(self, model: Type[T], column: str, values) -> list[T]:
        """Query rows where `column` matches any of `values` (SQL ``IN``).

        ``query`` only supports single-equality filters; this pushes a
        set-membership filter down to SQL with a parameterized ``IN (...)``
        so callers stop pulling a whole table into Python just to filter it
        (the ``list_entities`` document-scope hot path, #1815).

        ``values`` is de-duplicated and chunked (DuckDB caps bound
        parameters), and enum members are unwrapped to their ``.value`` to
        match how they are stored. Returns ``[]`` for an empty ``values``.
        """
        sql_table = self._sql_table_name(model)
        self._ensure_table(model)

        # Validate column name to prevent SQL injection (same guard as query()).
        if not _VALID_IDENTIFIER.match(column):
            raise ValueError(f"Invalid column name: {column}")

        # Normalize enums and de-dup while preserving determinism.
        normalized: list[Any] = []
        seen: set[Any] = set()
        for v in values:
            nv = v.value if hasattr(v, "value") else v
            if nv in seen:
                continue
            seen.add(nv)
            normalized.append(nv)

        if not normalized:
            return []

        out: list[T] = []
        # Chunk to stay well under DuckDB's bound-parameter ceiling on huge
        # folder scopes (mirrors _collect_folder_descendants_helper).
        for start in range(0, len(normalized), 500):
            chunk = normalized[start : start + 500]
            placeholders = ",".join(f"$v{i}" for i in range(len(chunk)))
            params = {f"v{i}": val for i, val in enumerate(chunk)}
            rows, columns = self._execute_fetch_with_columns(
                f"SELECT * FROM {sql_table} WHERE {column} IN ({placeholders})",
                params,
            )
            if not rows:
                continue
            out.extend(
                hydrated
                for row in rows
                if (hydrated := self._hydrate_row(model, columns, row)) is not None
            )
        return out

    def query_json_list_intersects(self, model: Type[T], column: str, values) -> list[T]:
        """Query JSON-list rows whose ``column`` contains any supplied id."""
        if not _VALID_IDENTIFIER.match(column):
            raise ValueError(f"Invalid column name: {column}")
        values = list(dict.fromkeys(value for value in values if value))
        if not values:
            return []
        sql_table = self._sql_table_name(model)
        self._ensure_table(model)
        out: list[T] = []
        for start in range(0, len(values), 200):
            chunk = values[start : start + 200]
            clauses = " OR ".join(f"{column} LIKE $v{i}" for i in range(len(chunk)))
            params = {f"v{i}": f'%"{value}"%' for i, value in enumerate(chunk)}
            rows, columns = self._execute_fetch_with_columns(
                f"SELECT * FROM {sql_table} WHERE {clauses}", params
            )
            out.extend(
                hydrated
                for row in rows
                if (hydrated := self._hydrate_row(model, columns, row)) is not None
            )
        return out

    def workflow_rows_for_list(self, folder_path: str | None = None) -> list["Workflow"]:
        """Load valid workflows, skipping legacy rows that no longer validate."""
        from fichero_server.models import Workflow

        sql_table = self._sql_table_name(Workflow)
        self._ensure_table(Workflow)
        if folder_path is None:
            rows, columns = self._execute_fetch_with_columns(f"SELECT * FROM {sql_table}")
        else:
            rows, columns = self._execute_fetch_with_columns(
                f"SELECT * FROM {sql_table} WHERE folder_path = ?",
                (folder_path,),
            )

        workflows: list[Workflow] = []
        for row in rows:
            raw = dict(zip(columns, row))
            if raw.get("id") is None:
                logger.warning("Skipping invalid workflow row with NULL id during list")
                continue
            try:
                workflows.append(Workflow(**self._parse_json_fields(Workflow, raw)))
            except Exception as exc:
                logger.warning(
                    "Skipping invalid workflow %s during list: %s",
                    raw.get("id", "<unknown>"),
                    exc,
                )
        return workflows

    def query_page(self, model: Type[T], *, limit: int, offset: int = 0) -> list[T]:
        """Return a stable, bounded page without hydrating the whole table."""
        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset must not be negative")

        sql_table = self._sql_table_name(model)
        self._ensure_table(model)
        rows, columns = self._execute_fetch_with_columns(
            f"SELECT * FROM {sql_table} ORDER BY id LIMIT $limit OFFSET $offset",
            {"limit": limit, "offset": offset},
        )
        return [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(model, columns, row)) is not None
        ]

    def artifacts_page(
        self,
        *,
        artifact_type: str | None = None,
        run_id: str | None = None,
        step_name: str | None = None,
        limit: int,
        offset: int = 0,
    ) -> tuple[list["Artifact"], int]:
        """One DB-side page of artifacts plus the total match count (#4319).

        Replaces the listing route's full-scan + Python-sort + slice: the
        WHERE, ORDER BY, LIMIT and OFFSET all run in DuckDB, so a large
        library never hydrates every artifact row per request.

        Ordering: newest first (``created_at DESC``) for the library-wide
        browse; a run-scoped listing (``run_id`` set) instead orders by
        pipeline ``sequence`` ascending with NULLs last (legacy artifacts
        persisted before #4313), then ``created_at``, so a run's passes read
        in execution order.
        """
        from fichero_server.models import Artifact

        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset must not be negative")

        self._ensure_table(Artifact)
        sql_table = self._sql_table_name(Artifact)

        clauses: list[str] = []
        params: dict[str, Any] = {}
        for column, value in (
            ("artifact_type", artifact_type),
            ("run_id", run_id),
            ("step_name", step_name),
        ):
            if value is not None:
                clauses.append(f"{column} = ${column}")
                params[column] = value
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        total_row = self._execute(
            f"SELECT COUNT(*) FROM {sql_table}{where}",
            dict(params) if params else None,
            fetch="one",
        )
        total = int(total_row[0]) if total_row else 0

        order = (
            "sequence ASC NULLS LAST, created_at ASC, id ASC"
            if run_id is not None
            else "created_at DESC, id DESC"
        )
        rows, columns = self._execute_fetch_with_columns(
            f"SELECT * FROM {sql_table}{where} "
            f"ORDER BY {order} LIMIT $page_limit OFFSET $page_offset",
            {**params, "page_limit": limit, "page_offset": offset},
        )
        items = [
            hydrated
            for row in rows
            if (hydrated := self._hydrate_row(Artifact, columns, row)) is not None
        ]
        return items, total

    def commit(self) -> None:
        """Commit pending DuckDB work through the typed DB wrapper."""
        self.conn.commit()

    def knowledge_claim_entity_id_values(
        self,
        *,
        source_document_id: str | None = None,
        entity_id: str | None = None,
    ) -> list[Any]:
        """Return raw ``entity_ids`` column values from knowledge claims.

        The column stores JSON/list payloads depending on migration vintage;
        callers keep the existing defensive parsing behavior.
        """
        if source_document_id is not None and entity_id is not None:
            rows = self._execute(
                """
                SELECT entity_ids FROM knowledgeclaims
                WHERE source_document_id = $source_document_id
                  AND entity_ids LIKE $needle
                """,
                {
                    "source_document_id": source_document_id,
                    "needle": f'%"{entity_id}"%',
                },
            ).fetchall()
        elif source_document_id is not None:
            rows = self._execute(
                "SELECT entity_ids FROM knowledgeclaims WHERE source_document_id = $id",
                {"id": source_document_id},
            ).fetchall()
        elif entity_id is not None:
            rows = self._execute(
                "SELECT entity_ids FROM knowledgeclaims WHERE entity_ids LIKE $needle",
                {"needle": f'%"{entity_id}"%'},
            ).fetchall()
        else:
            rows = self._execute("SELECT entity_ids FROM knowledgeclaims").fetchall()
        return [row[0] for row in rows]

    def knowledge_claim_source_document_ids_for_entity(
        self, entity_id: str
    ) -> list[str | None]:
        """Return source document ids for claims whose entity list mentions an id."""
        rows = self._execute(
            "SELECT source_document_id FROM knowledgeclaims WHERE entity_ids LIKE $needle",
            {"needle": f'%"{entity_id}"%'},
        ).fetchall()
        return [row[0] for row in rows]

    def knowledge_claims_for_seed_documents(
        self, doc_ids: set[str]
    ) -> list[Any]:
        """Claims linked to any seed document by source_document_id or source_ids."""
        from fichero_server.models.knowledge import KnowledgeClaim as KnowledgeClaimModel

        if not doc_ids:
            return []

        claims_by_id = {
            claim.id: claim
            for claim in self.query_in(
                KnowledgeClaimModel, "source_document_id", list(doc_ids)
            )
        }
        extra_ids: set[str] = set()
        doc_id_list = list(doc_ids)
        for start in range(0, len(doc_id_list), 200):
            chunk = doc_id_list[start : start + 200]
            clauses = " OR ".join(f"source_ids LIKE $d{i}" for i in range(len(chunk)))
            params = {f"d{i}": f'%"{doc_id}"%' for i, doc_id in enumerate(chunk)}
            rows = self.execute_fetchall(
                f"SELECT id FROM knowledgeclaims WHERE {clauses}",
                params,
            )
            extra_ids.update(claim_id for (claim_id,) in rows if claim_id)

        missing_ids = extra_ids - set(claims_by_id)
        if missing_ids:
            for claim in self.query_in(KnowledgeClaimModel, "id", list(missing_ids)):
                claims_by_id[claim.id] = claim
        return list(claims_by_id.values())

    def knowledge_claims_for_entity_frontier(
        self,
        entity_ids: set[str],
        *,
        exclude_ids: set[str] | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        """Claims whose entity_ids JSON list intersects the frontier ids."""
        from fichero_server.models.knowledge import KnowledgeClaim as KnowledgeClaimModel

        if not entity_ids or limit == 0:
            return []

        claim_ids: list[str] = []
        seen: set[str] = set()
        entity_id_list = list(entity_ids)
        excluded = list(exclude_ids or [])

        for start in range(0, len(entity_id_list), 50):
            remaining = None if limit is None else limit - len(claim_ids)
            if remaining is not None and remaining <= 0:
                break

            chunk = entity_id_list[start : start + 50]
            clauses = " OR ".join(f"entity_ids LIKE $e{i}" for i in range(len(chunk)))
            params = {f"e{i}": f'%"{entity_id}"%' for i, entity_id in enumerate(chunk)}
            sql = f"SELECT id FROM knowledgeclaims WHERE ({clauses})"
            if excluded:
                exclude_placeholders = ",".join(f"$x{i}" for i in range(len(excluded)))
                sql += f" AND id NOT IN ({exclude_placeholders})"
                params.update({f"x{i}": claim_id for i, claim_id in enumerate(excluded)})
            if remaining is not None:
                sql += f" LIMIT {remaining}"

            rows = self.execute_fetchall(sql, params)
            for (claim_id,) in rows:
                if not claim_id or claim_id in seen:
                    continue
                seen.add(claim_id)
                claim_ids.append(claim_id)

        return self.query_in(KnowledgeClaimModel, "id", claim_ids)

    def knowledge_entity_canonical_name(self, entity_id: str) -> str | None:
        """Return a single entity's canonical name, if present."""
        row = self._execute(
            "SELECT canonical_name FROM knowledgeentitys WHERE id = $id",
            {"id": entity_id},
        ).fetchone()
        return row[0] if row and row[0] else None

    def knowledge_entity_ids_scoped_to_documents(self, doc_ids: set[str]) -> set[str]:
        """Entity ids whose ``source_document_ids`` JSON list intersects doc ids."""
        if not doc_ids:
            return set()

        found: set[str] = set()
        doc_id_list = list(doc_ids)
        for start in range(0, len(doc_id_list), 200):
            chunk = doc_id_list[start : start + 200]
            clauses = " OR ".join(
                f"source_document_ids LIKE $d{i}" for i in range(len(chunk))
            )
            params = {f"d{i}": f'%"{doc_id}"%' for i, doc_id in enumerate(chunk)}
            rows = self._execute(
                f"SELECT id FROM knowledgeentitys WHERE {clauses}",
                params,
            ).fetchall()
            for (entity_id,) in rows:
                if entity_id:
                    found.add(entity_id)
        return found

    def entity_document_link_rows(self, entity_id: str, limit: int) -> list[tuple]:
        """Documents that mention an entity, with claim count and first excerpt."""
        return self._execute(
            """
            SELECT c.source_document_id,
                   d.name,
                   d.doc_type,
                   d.file_type,
                   COUNT(*) AS claim_count,
                   MIN(c.source_excerpt) AS first_excerpt
            FROM knowledgeclaims c
            LEFT JOIN documents d ON d.id = c.source_document_id
            WHERE c.entity_ids LIKE $needle
            GROUP BY c.source_document_id, d.name, d.doc_type, d.file_type
            ORDER BY claim_count DESC, d.name
            LIMIT $limit
            """,
            {"needle": f'%"{entity_id}"%', "limit": limit},
        ).fetchall()

    def knowledge_claim_excerpts_for_entity(
        self, entity_id: str, limit: int
    ) -> list[str]:
        """Representative non-empty claim excerpts for an entity."""
        rows = self._execute(
            """
            SELECT source_excerpt FROM knowledgeclaims
            WHERE entity_ids LIKE $needle
              AND source_excerpt IS NOT NULL
              AND length(source_excerpt) > 0
            ORDER BY length(source_excerpt) ASC
            LIMIT $limit
            """,
            {"needle": f'%"{entity_id}"%', "limit": limit},
        ).fetchall()
        return [excerpt for (excerpt,) in rows if excerpt]

    def entity_document_claim_counts(
        self, entity_id: str, limit: int
    ) -> list[tuple[str, int]]:
        """Source document ids and claim counts for biography assembly."""
        rows = self._execute(
            """
            SELECT source_document_id, COUNT(*) AS claim_count
            FROM knowledgeclaims
            WHERE entity_ids LIKE $needle
            GROUP BY source_document_id
            ORDER BY claim_count DESC
            LIMIT $limit
            """,
            {"needle": f'%"{entity_id}"%', "limit": limit},
        ).fetchall()
        return [(doc_id, int(claim_count or 0)) for doc_id, claim_count in rows]

    def artifact_data_for_types(self, artifact_types: Sequence[str]) -> list[Any]:
        """Return artifact data blobs for a fixed set of artifact types."""
        if not artifact_types:
            return []
        placeholders = ",".join(f"$t{i}" for i in range(len(artifact_types)))
        params = {f"t{i}": artifact_type for i, artifact_type in enumerate(artifact_types)}
        rows = self._execute(
            f"SELECT data FROM artifacts WHERE artifact_type IN ({placeholders})",
            params,
        ).fetchall()
        return [row[0] for row in rows]

    def document_page_content(self, document_id: str) -> str | None:
        """Return a document's full page content by id."""
        row = self._execute(
            "SELECT page_content FROM documents WHERE id = $id",
            {"id": document_id},
        ).fetchone()
        return row[0] if row else None

    def artifact_entity_document_matches(
        self,
        *,
        query: str,
        limit: int,
        artifact_types: Sequence[str],
    ) -> list[tuple]:
        """Documents whose extracted artifact JSON contains a query substring."""
        if not query.strip() or not artifact_types:
            return []
        placeholders = ",".join(f"$t{i}" for i in range(len(artifact_types)))
        params: dict[str, object] = {
            "needle": f"%{query.strip().lower()}%",
            "limit": limit,
        }
        for i, artifact_type in enumerate(artifact_types):
            params[f"t{i}"] = artifact_type
        return self._execute(
            f"""
            SELECT DISTINCT a.document_id, d.name, d.doc_type, d.file_type
            FROM artifacts a
            JOIN documents d ON d.id = a.document_id
            WHERE a.artifact_type IN ({placeholders})
              AND d.deleted_at IS NULL
              AND lower(CAST(a.data AS VARCHAR)) LIKE $needle
            LIMIT $limit
            """,
            params,
        ).fetchall()

    def artifact_content_matches(self, *, query: str, limit: int) -> list[tuple]:
        """Artifacts whose text content or structured data contains the query.

        The unified-object leg of search (#4118): transcriptions, summaries,
        translations, catalogues — anything a workflow emitted. Returns
        (document_id, document_name, artifact_type, body) rows; the route
        builds the display snippet. ponytail: substring match like the entity
        bridge — swap in FTS when artifact volume makes LIKE measurably slow.
        """
        if not query.strip():
            return []
        return self._execute(
            """
            SELECT a.document_id, d.name, a.artifact_type,
                   COALESCE(a.content, CAST(a.data AS VARCHAR)) AS body
            FROM artifacts a
            JOIN documents d ON d.id = a.document_id
            WHERE d.deleted_at IS NULL
              AND (
                lower(COALESCE(a.content, '')) LIKE $needle
                OR lower(COALESCE(CAST(a.data AS VARCHAR), '')) LIKE $needle
              )
            ORDER BY a.created_at DESC
            LIMIT $limit
            """,
            {"needle": f"%{query.strip().lower()}%", "limit": limit},
        ).fetchall()

    def recent_content_document_rows(self, limit: int) -> list[tuple]:
        """Most recently updated documents with non-empty page content."""
        return self._execute(
            """
            SELECT d.id, d.name, d.doc_type, d.file_type, d.updated_at, d.page_content
            FROM documents d
            WHERE d.deleted_at IS NULL
              AND d.page_content IS NOT NULL
              AND length(d.page_content) > 0
            ORDER BY d.updated_at DESC
            LIMIT $limit
            """,
            {"limit": limit},
        ).fetchall()

    def keyword_artifact_rows(self) -> list[tuple[Any, str]]:
        """Keyword artifact data plus document id for keyword cloud counts."""
        return self._execute(
            "SELECT data, document_id FROM artifacts WHERE artifact_type = 'keywords'"
        ).fetchall()

    def knowledge_table_signature(self, table_name: str) -> tuple[int, str]:
        """Return ``(count, max_updated_at)`` for cacheable KG tables."""
        if not _VALID_IDENTIFIER.match(table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        if table_name not in {"knowledgeclaims", "knowledgeentitys"}:
            raise ValueError(f"Unsupported knowledge table: {table_name}")
        row = self._execute(
            f"SELECT COUNT(*), MAX(updated_at) FROM {table_name}"
        ).fetchone()
        if not row:
            return (0, "")
        return (int(row[0] or 0), str(row[1]) if row[1] is not None else "")

    def delete(self, obj: BaseModel) -> None:
        """Delete an object by ID."""
        sql_table = self._sql_table_name(obj)
        self._ensure_table(type(obj))

        self._execute(f"DELETE FROM {sql_table} WHERE id = $id", {"id": obj.id})
        if type(obj).__name__ == "SavedSearch":
            self._delete_saved_search_document(obj.id)
        if type(obj).__name__ == "KnowledgeEntity":
            self._delete_filed_entity_document(obj.id)
        if type(obj).__name__ == "SpatialRoom":
            self._delete_spatial_room_document(obj.id)
        if type(obj).__name__ == "ResearchProject":
            self._delete_research_workspace_document(obj.id)
        if type(obj).__name__ in {"ResearchPlan", "ResearchTask", "ResearchStep"}:
            self._delete_research_content_document(obj.id)
        if type(obj).__name__ == "Note" and hasattr(obj, "body"):
            self._delete_note_document(obj.id)
        if type(obj).__name__ == "Milestone":
            self._delete_milestone_document(obj.id)
        if type(obj).__name__ == "Workflow":
            self._delete_workflow_document(obj.id)

    def _save_saved_search_document(self, saved: BaseModel) -> None:
        """Mirror a SavedSearch row into the document tree as a smart folder."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, saved.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({
            "node_class": "smart_folder",
            "saved_search_id": saved.id,
            "saved_search_query": saved.query,
            "saved_search_filters": saved.filters,
            "saved_search_is_smart_search": saved.is_smart_search,
            "saved_search_type": saved.search_type,
            "saved_search_sort_by": saved.sort_by,
            "saved_search_sort_direction": saved.sort_direction,
            "saved_search_created_by": saved.created_by,
            "saved_search_folder_path": saved.folder_path,
        })

        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "query": saved.query,
            "filters": saved.filters,
            "is_smart_search": saved.is_smart_search,
            "search_type": saved.search_type,
            "sort_by": saved.sort_by,
            "sort_direction": saved.sort_direction,
            "created_by": saved.created_by,
            "folder_path": saved.folder_path,
        })

        doc = existing or Document(id=saved.id, name=saved.query)
        doc.name = saved.query
        doc.node_kind = _SAVED_SEARCH_NODE_KIND
        doc.doc_type = DocType.folder
        doc.prototype_key = _SAVED_SEARCH_PROTOTYPE_KEY
        doc.sort_order = saved.sort_order
        doc.metadata = metadata
        doc.attributes = attributes
        doc.curated_items = [{
            "id": _SAVED_SEARCH_QUERY_ITEM_ID,
            "kind": "saved_search_query",
            "query": saved.query,
        }]
        doc.created_at = saved.created_at
        doc.updated_at = saved.updated_at
        self.save(doc)

    def _save_note_document(self, note: BaseModel) -> None:
        """Mirror a note row into the document tree."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, note.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({"node_class": _NOTE_NODE_KIND, "note_id": note.id})
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "body": note.body,
            "kind": note.kind.value,
            "tags": note.tags,
            "linked_note_ids": note.linked_note_ids,
            "linked_entity_ids": note.linked_entity_ids,
            "linked_claim_ids": note.linked_claim_ids,
            "linked_document_ids": note.linked_document_ids,
            "page_id": note.page_id,
            "folder_id": note.folder_id,
            "linked_structure_node_id": note.linked_structure_node_id,
            "address": note.address,
            "parent_address": note.parent_address,
            "author_type": note.author_type,
            "created_by": note.created_by,
        })

        doc = existing or Document(id=note.id, name=note.title or "Untitled note")
        doc.parent_id = self._note_parent_id(note)
        doc.name = note.title or note.address or "Untitled note"
        doc.node_kind = _NOTE_NODE_KIND
        doc.doc_type = DocType.file
        doc.prototype_key = _NOTE_PROTOTYPE_KEY
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = note.created_at
        doc.updated_at = note.updated_at
        self.save(doc)

    def _save_milestone_document(self, milestone: BaseModel) -> None:
        """Mirror a milestone row into the document tree."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, milestone.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({
            "node_class": _MILESTONE_NODE_KIND,
            "milestone_id": milestone.id,
        })
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "description": milestone.description,
            "status": milestone.status,
            "metadata": milestone.metadata,
            "created_by": milestone.created_by,
        })

        doc = existing or Document(id=milestone.id, name=milestone.title)
        doc.parent_id = milestone.parent_id
        doc.name = milestone.title
        doc.node_kind = _MILESTONE_NODE_KIND
        doc.doc_type = DocType.file
        doc.prototype_key = _MILESTONE_PROTOTYPE_KEY
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = milestone.created_at
        doc.updated_at = milestone.updated_at
        self.save(doc)

    def _save_workflow_document(self, workflow: BaseModel) -> None:
        """Mirror a Workflow row into the document tree for sidebar placement.

        MIRROR, not fold (#11 Phase 1): the ``workflows`` table stays the
        single source of truth — ``WorkflowStore``/the ``/api/workflows``
        routes keep reading and writing it directly, and ``get``/``all``/
        ``query`` for ``Workflow`` are deliberately NOT overridden here
        (unlike ``SavedSearch``). This mirror only exists so the workflow
        shows up as a node in the sidebar tree, same as
        ``_save_milestone_document``/``_save_note_document``.

        ``scope``/``read_only`` ride on the mirror document's ``attributes``
        dict (no new `workflows` table column): every system-seeded preset
        (``is_system=True``) is placed under the locked "Default Workflows"
        container and marked ``read_only``; everything else is a normal
        library-scoped, writable node at the tree root. ``read_only`` is
        ENFORCED on both write surfaces: workflow routes via
        ``_reject_if_read_only`` (403) and document update/move/delete via
        ``_reject_if_document_read_only`` in ``routes/document/documents.py``.
        Seeding bypasses both (direct ``db.save``), so re-seeds still work.
        """
        from fichero_server.models import DocType, Document

        is_system = bool(getattr(workflow, "is_system", False))
        if is_system:
            self._seed_default_workflows_container()
            container_parent_id = self._ensure_default_workflows_subfolder(
                workflow.folder_path
            )

        existing = self.get(Document, workflow.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({
            "node_class": _WORKFLOW_NODE_KIND,
            "workflow_id": workflow.id,
        })
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "format": workflow.format,
            "provider": workflow.provider,
            "tags": workflow.tags,
            "is_template": workflow.is_template,
            "is_system": is_system,
            "folder_path": workflow.folder_path,
            "scope": "global" if is_system else "library",
            "read_only": is_system,
        })

        doc = existing or Document(id=workflow.id, name=workflow.name)
        # SYSTEM presets must always render: pre-lock databases can hold
        # soft-deleted preset mirror rows (document deletes only started
        # refusing read_only nodes later), and without this a preset stays
        # invisible forever. Gated on is_system — resurrecting USER workflow
        # mirrors here would silently reverse a user's delete whenever any
        # save touches the workflow (e.g. a run updating updated_at).
        if is_system:
            doc.deleted_at = None
            doc.deleted_by = None
        doc.parent_id = (
            container_parent_id
            if is_system
            else (existing.parent_id if existing is not None else None)
        )
        doc.name = workflow.name
        doc.node_kind = _WORKFLOW_NODE_KIND
        doc.doc_type = DocType.file
        doc.prototype_key = _WORKFLOW_PROTOTYPE_KEY
        doc.sort_order = workflow.sort_order
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = workflow.created_at
        doc.updated_at = workflow.updated_at
        self.save(doc)

    def _seed_default_workflows_container(self) -> None:
        """Idempotently seed the locked, read-only "Default Workflows" folder.

        Deterministic id so reopening a library never mints a second
        container. Name/scope/read_only are re-asserted on every call —
        it's locked, so a user rename shouldn't stick.
        """
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models import DocType, Document

        existing = self.get(Document, _DEFAULT_WORKFLOWS_CONTAINER_ID)
        doc = existing or Document(
            id=_DEFAULT_WORKFLOWS_CONTAINER_ID, name="Default Workflows"
        )
        doc.name = "Default Workflows"
        doc.doc_type = DocType.folder
        doc.node_kind = _WORKFLOW_CONTAINER_NODE_KIND
        doc.prototype_key = _FOLDER_PROTOTYPE_KEY
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({"scope": "global", "read_only": True, "system": True})
        doc.attributes = attributes
        self.save(doc)

        # Drop legacy subfolder rows minted with a slash in their id (the
        # pre-fix scheme, e.g. "system-default-workflows:/Transcribe"). Those
        # ids can't be routed by /api/documents/{doc_id}/children, so they'd
        # linger as un-expandable duplicates once the ":"-joined nodes are
        # re-seeded by the backfill. The container id itself has no "/", so
        # this LIKE never removes it.
        self._execute(
            "DELETE FROM documents WHERE node_kind = $kind AND id LIKE '%/%'",
            {"kind": _WORKFLOW_CONTAINER_NODE_KIND},
        )

    def delete_default_workflow_container_nodes(self) -> None:
        """Drop the locked "Default Workflows" container and its subfolders.

        Used when healing a non-global library that was seeded with the
        presets before they became global-only (#4102). Scoped to the
        system container node kind, so a user's own workflow folders are
        untouched.
        """
        if not hasattr(self.conn, "execute"):
            return

        self._execute(
            "DELETE FROM documents WHERE node_kind = $kind",
            {"kind": _WORKFLOW_CONTAINER_NODE_KIND},
        )

    def _ensure_default_workflows_subfolder(self, folder_path: str | None) -> str:
        """Get-or-create the locked subfolder for a preset's ``folder_path``.

        Presets ship with a flat ``folder_path`` like ``"/Convert"`` or
        ``"/Transcribe"`` (see ``src/fichero_server/resources/default_workflows/*.json``).
        Root-level presets (``folder_path`` unset or ``"/"``) sit directly in
        the container — no subfolder. Everything else gets one locked
        subfolder node per distinct path segment, nested under the
        container, so the sidebar tree matches "Default Workflows > Convert
        > <preset>". The subfolder id is deterministic (derived from the
        path, not `_new_id()`), so re-seeding never mints a duplicate.

        Returns the id of the ``Document`` a preset mirror should use as its
        ``parent_id`` — either the subfolder id or the container id itself.
        """
        normalized = (folder_path or "/").strip()
        if normalized in ("", "/"):
            return _DEFAULT_WORKFLOWS_CONTAINER_ID

        from fichero_server.models import DocType, Document

        # A raw "/" in a document id breaks every /api/documents/{doc_id}/...
        # route: FastAPI's default `{doc_id}` param matches a single path
        # segment, so an id like "system-default-workflows:/Transcribe" fails to
        # route (children/ancestors/parent all 404). Join the path segments with
        # ":" instead so the id stays a single URL path segment (#11).
        segments = [seg for seg in normalized.split("/") if seg]
        subfolder_id = ":".join([_DEFAULT_WORKFLOWS_CONTAINER_ID, *segments])
        existing = self.get(Document, subfolder_id)
        doc = existing or Document(id=subfolder_id, name=normalized.strip("/"))
        doc.name = normalized.strip("/") or normalized
        doc.doc_type = DocType.folder
        doc.node_kind = _WORKFLOW_CONTAINER_NODE_KIND
        doc.prototype_key = _FOLDER_PROTOTYPE_KEY
        doc.parent_id = _DEFAULT_WORKFLOWS_CONTAINER_ID
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "scope": "global",
            "read_only": True,
            "system": True,
            "source_folder_path": normalized,
        })
        doc.attributes = attributes
        self.save(doc)
        return subfolder_id

    def _all_folded_workflows(self) -> list[BaseModel]:
        """Return the mirrored ``Document`` nodes for every workflow.

        Unlike ``_all_folded_saved_searches`` this returns raw ``Document``
        rows, not hydrated ``Workflow`` objects — reads for ``Workflow``
        stay on the real `workflows` table (see ``_save_workflow_document``).
        This is a tree-side helper for callers that want the mirror nodes
        (e.g. sidebar listing, tests), not a replacement read path.
        """
        from fichero_server.models import Document

        return self.query(Document, node_kind=_WORKFLOW_NODE_KIND)

    def _save_filed_entity_document(self, entity: BaseModel) -> None:
        """Mirror a filed KnowledgeEntity into the document tree."""
        from fichero_server.models import DocType, Document

        if getattr(entity, "parent_id", None) is None:
            self._delete_filed_entity_document(entity.id)
            return

        existing = self.get(Document, entity.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({
            "node_class": _ENTITY_NODE_KIND,
            "knowledge_entity_id": entity.id,
        })
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "entity_type": entity.entity_type.value,
            "aliases": entity.aliases,
            "description": entity.description,
            "language": entity.language,
            "entity_metadata": entity.metadata,
            "curation_state": entity.curation_state.value,
            "corroboration_count": entity.corroboration_count,
            "merged_into_id": entity.merged_into_id,
            "source_document_ids": entity.source_document_ids,
        })

        doc = existing or Document(id=entity.id, name=entity.canonical_name)
        doc.parent_id = entity.parent_id
        doc.name = entity.canonical_name
        doc.node_kind = _ENTITY_NODE_KIND
        doc.doc_type = DocType.file
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = entity.created_at
        doc.updated_at = entity.updated_at
        self.save(doc)

    def _delete_saved_search_document(self, saved_search_id: str) -> None:
        """Remove the mirrored document row for a saved search, if present."""
        from fichero_server.models import Document

        doc = self.get(Document, saved_search_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": saved_search_id})

    def _delete_filed_entity_document(self, entity_id: str) -> None:
        """Remove the mirrored document row for a filed entity, if present."""
        from fichero_server.models import Document

        doc = self.get(Document, entity_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": entity_id})

    def _delete_note_document(self, note_id: str) -> None:
        """Remove the mirrored document row for a note, if present."""
        from fichero_server.models import Document

        doc = self.get(Document, note_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": note_id})

    def _delete_milestone_document(self, milestone_id: str) -> None:
        """Remove the mirrored document row for a milestone, if present."""
        from fichero_server.models import Document

        doc = self.get(Document, milestone_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": milestone_id})

    def _delete_workflow_document(self, workflow_id: str) -> None:
        """Remove the mirrored document row for a workflow, if present.

        Never touches ``_DEFAULT_WORKFLOWS_CONTAINER_ID`` — only the
        per-workflow shadow shares an id with the deleted workflow row, so
        this can't accidentally delete the locked container.
        """
        from fichero_server.models import Document

        doc = self.get(Document, workflow_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": workflow_id})

    def _backfill_saved_search_documents(self) -> None:
        """Backfill existing saved_searches rows into same-id document nodes."""
        # ponytail: mocked connections in unit tests may only support close().
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models import SavedSearch

        table_name = self._table_name(SavedSearch)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for saved in self._legacy_all_saved_search_rows():
            self._save_saved_search_document(saved)

    def _backfill_filed_entity_documents(self) -> None:
        """Backfill filed entities into same-id document nodes."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.knowledge import KnowledgeEntity

        table_name = self._table_name(KnowledgeEntity)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for entity in self._legacy_all_knowledge_entity_rows():
            self._save_filed_entity_document(entity)

    def _backfill_note_documents(self) -> None:
        """Backfill legacy notes into same-id document nodes."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.knowledge import Note

        table_name = self._table_name(Note)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for note in self._legacy_all_note_rows():
            self._save_note_document(note)

    def _backfill_milestone_documents(self) -> None:
        """Backfill legacy milestones into same-id document nodes."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.knowledge import Milestone

        table_name = self._table_name(Milestone)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for milestone in self._legacy_all_milestone_rows():
            self._save_milestone_document(milestone)

    def _backfill_workflow_documents(self) -> None:
        """Backfill existing workflow rows into same-id mirrored document nodes."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models import Workflow

        table_name = self._table_name(Workflow)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for workflow in self._legacy_all_workflow_rows():
            self._save_workflow_document(workflow)

    def _save_research_workspace_document(self, project: BaseModel) -> None:
        """Mirror a ResearchProject row into the document tree as a workspace."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, project.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({
            "node_class": "research_workspace",
            "research_project_id": project.id,
        })
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "description": project.description,
            "status": project.status.value,
            "created_by": project.created_by,
            "library_destination_folder_id": project.library_destination_folder_id,
            "metadata": project.metadata,
        })

        doc = existing or Document(id=project.id, name=project.name)
        doc.name = project.name
        doc.node_kind = _RESEARCH_WORKSPACE_NODE_KIND
        doc.doc_type = DocType.folder
        doc.prototype_key = _RESEARCH_WORKSPACE_PROTOTYPE_KEY
        doc.is_workspace = True
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = project.created_at
        doc.updated_at = project.updated_at
        self.save(doc)

    def _save_spatial_room_document(self, room: BaseModel) -> None:
        """Mirror a SpatialRoom row into the document tree as a room node."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, room.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({
            "node_class": _ROOM_NODE_KIND,
            "mind_palace_room_id": room.id,
        })
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "description": room.description,
            "room_type": room.room_type.value,
            "owner_id": room.owner_id,
            "metadata": room.metadata,
        })

        doc = existing or Document(id=room.id, name=room.name)
        doc.name = room.name
        doc.node_kind = _ROOM_NODE_KIND
        doc.doc_type = DocType.folder
        doc.prototype_key = _ROOM_PROTOTYPE_KEY
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = room.created_at
        doc.updated_at = room.updated_at
        self.save(doc)

    def _save_research_plan_document(self, plan: BaseModel) -> None:
        """Mirror a ResearchPlan row into the document tree."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, plan.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({"node_class": "research_plan", "research_plan_id": plan.id})
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "description": plan.description,
            "status": plan.status.value,
            "order_index": plan.order_index,
            "metadata": plan.metadata,
        })

        doc = existing or Document(id=plan.id, name=plan.name)
        doc.parent_id = plan.project_id
        doc.name = plan.name
        doc.node_kind = _RESEARCH_PLAN_NODE_KIND
        doc.doc_type = DocType.folder
        doc.prototype_key = _RESEARCH_PLAN_PROTOTYPE_KEY
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = plan.created_at
        doc.updated_at = plan.updated_at
        self.save(doc)

    def _save_research_task_document(self, task: BaseModel) -> None:
        """Mirror a ResearchTask row into the document tree."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, task.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({"node_class": "research_task", "research_task_id": task.id})
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "description": task.description,
            "status": task.status.value,
            "priority": task.priority,
            "assigned_to": task.assigned_to,
            "metadata": task.metadata,
            "completed_at": task.completed_at,
        })

        doc = existing or Document(id=task.id, name=task.name)
        doc.parent_id = task.plan_id
        doc.name = task.name
        doc.node_kind = _RESEARCH_TASK_NODE_KIND
        doc.doc_type = DocType.folder
        doc.prototype_key = _RESEARCH_TASK_PROTOTYPE_KEY
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = task.created_at
        doc.updated_at = task.updated_at
        self.save(doc)

    def _save_research_step_document(self, step: BaseModel) -> None:
        """Mirror a ResearchStep row into the document tree."""
        from fichero_server.models import DocType, Document

        existing = self.get(Document, step.id)
        metadata = (
            dict(existing.metadata)
            if existing is not None and isinstance(existing.metadata, dict)
            else {}
        )
        metadata.update({"node_class": "research_step", "research_step_id": step.id})
        attributes = (
            dict(existing.attributes)
            if existing is not None and isinstance(existing.attributes, dict)
            else {}
        )
        attributes.update({
            "tool": step.tool.value,
            "description": step.description,
            "config": step.config,
            "status": step.status.value,
            "result": step.result,
            "error": step.error,
            "order_index": step.order_index,
            "completed_at": step.completed_at,
        })

        doc = existing or Document(id=step.id, name=step.label)
        doc.parent_id = step.task_id
        doc.name = step.label
        doc.node_kind = _RESEARCH_STEP_NODE_KIND
        doc.doc_type = DocType.file
        doc.prototype_key = _RESEARCH_STEP_PROTOTYPE_KEY
        doc.metadata = metadata
        doc.attributes = attributes
        doc.created_at = step.created_at
        doc.updated_at = step.updated_at
        self.save(doc)

    def _delete_research_workspace_document(self, project_id: str) -> None:
        """Remove the mirrored document row for a research workspace, if present."""
        from fichero_server.models import Document

        doc = self.get(Document, project_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": project_id})

    def _delete_spatial_room_document(self, room_id: str) -> None:
        """Remove the mirrored document row for a room, if present."""
        from fichero_server.models import Document

        doc = self.get(Document, room_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": room_id})

    def _delete_research_content_document(self, doc_id: str) -> None:
        """Remove the mirrored document row for a folded research content node."""
        from fichero_server.models import Document

        doc = self.get(Document, doc_id)
        if doc is None:
            return
        self._execute("DELETE FROM documents WHERE id = $id", {"id": doc_id})

    def _backfill_research_workspace_documents(self) -> None:
        """Backfill legacy research projects into workspace documents."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.research import ResearchProject

        table_name = self._table_name(ResearchProject)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for project in self._legacy_all_research_project_rows():
            self._save_research_workspace_document(project)

    def _backfill_spatial_room_documents(self) -> None:
        """Backfill legacy mind-palace rooms into room document nodes."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.canvas import SpatialRoom

        table_name = self._table_name(SpatialRoom)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for room in self._legacy_all_spatial_room_rows():
            self._save_spatial_room_document(room)

    def _backfill_research_plan_task_step_documents(self) -> None:
        """Backfill legacy research plan/task/step rows into document nodes."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.research import ResearchPlan, ResearchStep, ResearchTask

        for model_cls, saver in (
            (ResearchPlan, self._save_research_plan_document),
            (ResearchTask, self._save_research_task_document),
            (ResearchStep, self._save_research_step_document),
        ):
            table_name = self._table_name(model_cls)
            table_exists = self.execute_fetchone(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = $table_name
                """,
                {"table_name": table_name},
            )
            if not table_exists or int(table_exists[0] or 0) == 0:
                continue
            for row in self._legacy_all_research_rows(model_cls):
                saver(row)

    def _backfill_claim_links_to_library_links(self) -> None:
        """Mirror legacy claim-link rows into generic library-link rows."""
        if not hasattr(self.conn, "execute"):
            return

        from fichero_server.models.knowledge import (
            KnowledgeClaimLink,
            LibraryItemLink,
            LibraryItemType,
        )

        self._ensure_table(LibraryItemLink)

        table_name = self._table_name(KnowledgeClaimLink)
        table_exists = self.execute_fetchone(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = $table_name
            """,
            {"table_name": table_name},
        )
        if not table_exists or int(table_exists[0] or 0) == 0:
            return

        for link in self.all(KnowledgeClaimLink):
            self.save(LibraryItemLink(
                id=link.id,
                source_id=link.claim_id,
                source_type=LibraryItemType.claim,
                target_id=link.related_claim_id,
                target_type=LibraryItemType.claim,
                relation_type=link.relation_type,
                link_quality=link.link_quality,
                evidence=link.evidence,
                metadata=link.metadata,
                created_at=link.created_at,
            ))

    def count(self, model: Type[T], **filters) -> int:
        """Count objects matching filters."""
        sql_table = self._sql_table_name(model)
        self._ensure_table(model)

        if not filters:
            result = self._execute(f"SELECT COUNT(*) FROM {sql_table}").fetchone()
        else:
            # Validate column names to prevent SQL injection
            for k in filters.keys():
                if not _VALID_IDENTIFIER.match(k):
                    raise ValueError(f"Invalid column name: {k}")

            where = " AND ".join(f"{k} = ${k}" for k in filters.keys())
            result = self._execute(
                f"SELECT COUNT(*) FROM {sql_table} WHERE {where}", filters
            ).fetchone()

        return result[0] if result else 0

    # =========================================================================
    # LanceDB (Vector Storage)
    # =========================================================================

    @property
    def lance(self):
        """Lazy-load LanceDB connection."""
        if self._lance_db is None:
            import lancedb

            self._lance_path.mkdir(parents=True, exist_ok=True)
            self._lance_db = lancedb.connect(str(self._lance_path))
        return self._lance_db

    def _lance_tables(self) -> list[str]:
        """Return LanceDB table names across API versions."""
        raw_tables = (
            self.lance.list_tables()
            if hasattr(self.lance, "list_tables")
            else self.lance.table_names()
        )
        if hasattr(raw_tables, "tables"):
            raw_tables = raw_tables.tables
        elif isinstance(raw_tables, dict):
            raw_tables = raw_tables.get("tables", raw_tables)
        table_names: list[str] = []
        for table in raw_tables:
            if isinstance(table, str):
                table_names.append(table)
            elif hasattr(table, "name"):
                table_names.append(str(table.name))
            else:
                table_names.append(str(table))
        return table_names

    def _lance_table_field_names(self, table) -> set[str]:
        """Return the field names for a LanceDB table across API versions."""
        schema = getattr(table, "schema", None)
        if callable(schema):
            schema = schema()
        names = getattr(schema, "names", None)
        if names is not None:
            return {str(name) for name in names}
        fields = getattr(schema, "fields", None)
        if fields is not None:
            return {str(getattr(field, "name", field)) for field in fields}
        return set()

    def _lance_select_existing_fields(self, table, fields: list[str]) -> list[str]:
        """Keep Lance projections compatible with persisted table schemas."""
        available = self._lance_table_field_names(table)
        return [field for field in fields if not available or field in available]

    def _coerce_vectors_to_existing_schema(
        self, table_name: str, table, data: list[dict]
    ) -> list[dict]:
        """Evolve a legacy LanceDB table schema before append, then coerce.

        For each field present in the data but absent from the table:
        1. Attempt ``table.add_columns()`` to add the column in-place (#2225).
           ``embedding_model_id`` is the common case — legacy tables lack it so
           every append silently discards the model stamp.
        2. If the column add fails (e.g. older LanceDB or concurrent writer),
           fall through to stripping the field from the rows so the append
           succeeds rather than crashing.
        """
        fields = self._lance_table_field_names(table)
        if not fields:
            return data

        extra_fields = set().union(*(row.keys() - fields for row in data))
        if not extra_fields:
            return data

        still_extra: set[str] = set()
        for field_name in extra_fields:
            # Infer SQL expression: nullable varchar for string fields, else cast null.
            sample = next(
                (row[field_name] for row in data if row.get(field_name) is not None),
                None,
            )
            sql = "cast(null as string)" if sample is None or isinstance(sample, str) else "cast(null as double)"
            try:
                table.add_columns({field_name: sql})
                logger.info(
                    "LanceDB table %s: migrated legacy schema — added column %r",
                    table_name, field_name,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LanceDB table %s: could not add column %r (%s); "
                    "omitting field from append",
                    table_name, field_name, exc,
                )
                still_extra.add(field_name)

        if not still_extra:
            return data

        return [{key: value for key, value in row.items() if key not in still_extra} for row in data]

    def save_vectors(
        self,
        table_name: str,
        data: list[dict],
        *,
        replace: bool = False,
        key_field: str = "id",
    ) -> None:
        """Save data to LanceDB table (creates or appends).

        When ``replace`` is True, existing rows with the same key are deleted
        first so reindex/backfill passes stay idempotent.
        """
        if not data:
            return

        with self._lock:
            if table_name in self._lance_tables():
                table = self.lance.open_table(table_name)
                data = self._coerce_vectors_to_existing_schema(table_name, table, data)
                if replace:
                    for row in data:
                        key = row.get(key_field)
                        if key is None:
                            continue
                        safe_key = str(key).replace("'", "''")
                        table.delete(f"{key_field} = '{safe_key}'")
                table.add(data)
            else:
                self.lance.create_table(table_name, data)
            # One append == one LanceDB fragment. Count appends per table and
            # run a bounded compaction every N of them so 100k micro-appends
            # don't rot read performance (#2542). Compacting on every write
            # would be strictly worse, so it's gated on the interval.
            self._note_vector_append(table_name)

    def _note_vector_append(self, table_name: str) -> None:
        """Increment the per-table append counter and compact at the interval."""
        interval = _vector_compaction_interval()
        if interval <= 0:
            return
        count = self._vector_append_counts.get(table_name, 0) + 1
        if count >= interval:
            self._vector_append_counts[table_name] = 0
            self.compact_vectors(table_name)
        else:
            self._vector_append_counts[table_name] = count

    def compact_vectors(self, table_name: str | None = None) -> dict[str, bool]:
        """Compact (optimize) one or all LanceDB vector tables.

        Merges accumulated micro-fragments into larger files and prunes old
        versions via ``table.optimize()`` (#2542). Safe to call explicitly at
        the end of a bulk import; also fired automatically by the append-count
        trigger. Data is never lost — optimize only rewrites storage layout.

        Returns a map of ``table_name -> compacted?`` so callers/tests can see
        which tables were touched. A per-table failure is logged loudly and
        recorded as ``False`` rather than aborting the others; the data is
        intact either way (optimize is atomic per table).
        """
        results: dict[str, bool] = {}
        with self._lock:
            available = set(self._lance_tables())
            targets = (
                [table_name] if table_name is not None else sorted(available)
            )
            for name in targets:
                if name not in available:
                    results[name] = False
                    continue
                try:
                    self.lance.open_table(name).optimize()
                    self._vector_append_counts[name] = 0
                    results[name] = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "LanceDB compaction failed for table %s: %s", name, exc
                    )
                    results[name] = False
        return results

    def search_vectors(
        self, table_name: str, query_vector: list[float], limit: int = 10
    ) -> list[dict]:
        """Search LanceDB table by vector similarity."""
        if table_name not in self._lance_tables():
            return []

        table = self.lance.open_table(table_name)
        self.assert_vector_table_model_compatible(table_name)
        results = table.search(query_vector).limit(limit).to_list()
        return results

    # =========================================================================
    # Embedding Convenience Methods
    # =========================================================================

    def _delete_embedding_rows(self, field: str, value: str) -> None:
        """Delete embedding rows by a trusted field/value pair."""
        with self._lock:
            if EMBEDDINGS_TABLE not in self._lance_tables():
                return
            safe_value = value.replace("'", "''") if value else ""
            table = self.lance.open_table(EMBEDDINGS_TABLE)
            table.delete(f"{field} = '{safe_value}'")

    def save_embedding(
        self, doc: BaseModel, vector: list[float], text: str | None = None
    ) -> None:
        """Save one page/document-level embedding to LanceDB.

        Passage-level indexing is the default path through ``embed()``. This
        method remains the explicit fallback for legacy page/document vectors
        and tests that need to seed one vector by hand.

        Args:
            doc: Document model with id attribute
            vector: Embedding vector
            text: Optional text content (for retrieval display)
        """
        content = text or ""
        if hasattr(doc, "page_content") and doc.page_content:
            content = content or doc.page_content[:500]
        elif hasattr(doc, "name"):
            content = content or doc.name

        stored_vector = vector
        quantized_vector: list[int] | None = None
        quantized_scale: float | None = None
        if self._use_int8_embeddings():
            quantized_vector, quantized_scale = _quantize_int8(vector)
            stored_vector = _dequantize_int8(quantized_vector, quantized_scale)

        record = {
            "id": doc.id,
            "document_id": doc.id,
            "text": content,
            "vector": stored_vector,
            "embedding_scope": "page",
            "passage_id": "",
            "page_id": doc.id,
            "char_start": 0,
            "char_end": len(content) if content else None,
            # Store document metadata for search results display
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

        with self._lock:
            self._delete_embedding_rows("document_id", doc.id)
            self.save_vectors(EMBEDDINGS_TABLE, [record], replace=True)

    def save_passage_embeddings(self, doc: BaseModel, *, text: str | None = None) -> int:
        """Save passage/chunk-level embeddings for a document."""
        records = self.passage_embedding_records(doc, text=text)
        if not records:
            return 0
        with self._lock:
            self._delete_embedding_rows("document_id", doc.id)
            self.save_vectors(EMBEDDINGS_TABLE, records)
        return len(records)

    def search_similar(
        self, query_vector: list[float], limit: int = 10, model: Type[T] | None = None
    ) -> list[dict] | list[T]:
        """Find similar documents by vector search.

        Args:
            query_vector: Query embedding vector
            limit: Maximum results
            model: Optional model class to return full objects

        Returns:
            List of dicts (or model instances if model provided)
        """
        results = self.search_vectors(EMBEDDINGS_TABLE, query_vector, limit)

        if model is None:
            return results

        # Convert to model instances
        doc_ids = [r.get("document_id") or r.get("id") for r in results]
        return [self.get(model, id) for id in doc_ids if id]

    def semantic_related_documents(
        self, doc_id: str, limit: int = 10
    ) -> list[tuple[str, float]]:
        """Other documents semantically near ``doc_id``, best-first.

        Uses the document's own STORED vectors (no re-embedding), runs a
        neighbor search per vector, and keeps the best cosine similarity per
        other document. Returns [] when the doc has no embeddings — an honest
        empty, not a failure. Similarities are real cosine values in [0, 1]
        (vectors are L2-normalised; see the search() conversion, #481).
        """
        if EMBEDDINGS_TABLE not in self._lance_tables():
            return []

        safe_id = doc_id.replace("'", "''") if doc_id else ""
        table = self.lance.open_table(EMBEDDINGS_TABLE)
        self.assert_vector_table_model_compatible(EMBEDDINGS_TABLE)
        # ponytail: cap the seed vectors at 8 — enough passages to represent
        # a document; raise if long-doc recall ever measurably suffers.
        own_rows = (
            table.search()
            .where(f"id = '{safe_id}' OR document_id = '{safe_id}'")
            .limit(8)
            .to_list()
        )
        if not own_rows:
            return []

        best: dict[str, float] = {}
        for row in own_rows:
            vector = row.get("vector")
            if vector is None:
                continue
            hits = table.search(list(vector)).limit(limit * 4).to_list()
            for hit in hits:
                other_id = hit.get("document_id") or hit.get("id")
                if not other_id or other_id == doc_id:
                    continue
                distance = hit.get("_distance", 2.0)
                cos_sim = 1.0 - (distance * distance) / 2.0
                score = max(0.0, min(1.0, cos_sim))
                if score > best.get(other_id, -1.0):
                    best[other_id] = score

        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:limit]

    def delete_embedding(self, doc_id: str) -> bool:
        """Delete embedding for a document.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted
        """
        try:
            if EMBEDDINGS_TABLE not in self._lance_tables():
                return False

            # Validate doc_id to prevent injection
            if not doc_id or not _VALID_IDENTIFIER.match(doc_id.replace("-", "")):
                # UUIDs contain hex chars and hyphens - just sanitize quotes
                safe_id = doc_id.replace("'", "''")
            else:
                safe_id = doc_id

            table = self.lance.open_table(EMBEDDINGS_TABLE)
            table.delete(f"id = '{safe_id}' OR document_id = '{safe_id}'")
            return True
        except Exception as e:
            error = handle_error(
                e,
                default_message=f"Failed to delete embedding for document {doc_id}",
                category=ErrorCategory.DATABASE,
                context={"document_id": doc_id},
            )
            logger.warning("Embedding deletion failed: %s", error.message)
            return False

    def has_embedding(self, doc_id: str) -> bool:
        """Check if document has an embedding.

        Args:
            doc_id: Document ID

        Returns:
            True if embedding exists
        """
        try:
            if EMBEDDINGS_TABLE not in self._lance_tables():
                return False

            # Sanitize doc_id to prevent injection
            safe_id = doc_id.replace("'", "''") if doc_id else ""

            table = self.lance.open_table(EMBEDDINGS_TABLE)
            results = (
                table.search()
                .where(f"id = '{safe_id}' OR document_id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception:
            return False

    # =========================================================================
    # Semantic Search
    # =========================================================================

    def _embedding_text_for_document(self, doc: BaseModel) -> str:
        """Return the text payload that should be embedded for a document."""
        text = ""
        if hasattr(doc, "page_content") and doc.page_content:
            stripped = doc.page_content.strip()
            if _is_content_marker_only(stripped):
                text = doc.name if hasattr(doc, "name") and doc.name else ""
            else:
                text = doc.page_content
        elif hasattr(doc, "name") and doc.name:
            text = doc.name

        if not text or len(text.strip()) < MIN_CONTENT_LENGTH:
            logger.debug("Skipping embedding for %s: content too short", doc.id)
            return ""
        return text

    def embed(self, doc: BaseModel, *, mode: str = "passage") -> bool:
        """Create embedding for a document.

        Uses document's page_content if available, otherwise name. Passage
        embeddings are the default; page-level embedding remains available via
        ``mode="page"`` for legacy fallback/reindexing.

        Args:
            doc: Document model with id and optionally page_content

        Returns:
            True if embedding was created
        """
        # Marker-only content guard: when transcribe runs against a blank
        # or unreadable page it sets page_content to '[sin texto]' (or
        # '[ilegible]'). Embedding that literal string makes every
        # marker-only doc share an identical vector, and they cluster at
        # the top of every semantic query (the 95%-on-blank-doc bug
        # seen in a social-license search). Treat marker-only
        # content as 'no content' and fall back to the doc's name —
        # which at least varies per-doc and reflects the legal-case
        # / archive structure the user is browsing.
        text = self._embedding_text_for_document(doc)
        if not text:
            return False

        try:
            if mode == "page":
                vector = self._embed_text(text, role="passage")
                self.save_embedding(doc, vector, text[:500])
            else:
                count = self.save_passage_embeddings(doc, text=text)
                if count == 0:
                    return False
            logger.debug("Created %s embedding for %s", mode, doc.id)
            return True
        except Exception as e:
            logger.warning("Failed to create embedding for %s: %s", doc.id, e)
            return False

    def _collect_folder_descendants(self, folder_id: str) -> set[str]:
        """Wrap the free helper so callers don't reach into module level."""
        return _collect_folder_descendants_helper(self.conn, folder_id)

    def _has_indexed_page_children(self, document_id: str | None) -> bool:
        """True when a file-level document has page children in the vector index.

        Search should rank and return the matching page rows when they exist,
        not the parent PDF's whole-document text blob. If a legacy library has
        only the parent embedded, keep the parent result so search still works.
        """
        if not document_id:
            return False

        try:
            from fichero_server.models import DocType, Document

            doc = self.get(Document, document_id)
            if doc is None or doc.doc_type != DocType.file:
                return False

            pages = self.query(Document, parent_id=document_id, doc_type=DocType.page)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Page-child lookup failed for search result %s: %s", document_id, exc)
            return False

        return any(self.has_embedding(page.id) for page in pages)

    def _is_active_document_id(self, document_id: str | None) -> bool:
        """True when the document exists and is not soft-deleted."""
        if not document_id:
            return False
        try:
            from fichero_server.models import Document

            doc = self.get(Document, document_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Active-document lookup failed for %s: %s", document_id, exc
            )
            return False
        return bool(doc and getattr(doc, "deleted_at", None) is None)

    def enrich_search_results_with_kg(
        self, results: list[SearchResult], query: str
    ) -> list[SearchResult]:
        """Attach matching KG claim/entity ids for each result document.

        Uses KG rows and the result's indexed transcript excerpt only; it
        does not fetch document bodies. This keeps search responses rich
        without turning every hit into a whole-document read.
        """
        if not results or not query.strip():
            return results

        try:
            from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
        except Exception as exc:  # noqa: BLE001
            logger.debug("KG models unavailable during search enrichment: %s", exc)
            return results

        doc_ids = {r.document_id for r in results}
        terms = _search_match_terms(query)
        if not terms:
            return results

        try:
            claims = self.all(KnowledgeClaim)
            entities = self.all(KnowledgeEntity)
        except Exception as exc:  # noqa: BLE001
            logger.debug("KG lookup failed during search enrichment: %s", exc)
            return results

        entity_by_id = {entity.id: entity for entity in entities}
        matched_claims_by_doc: dict[str, set[str]] = {doc_id: set() for doc_id in doc_ids}
        matched_entities_by_doc: dict[str, set[str]] = {doc_id: set() for doc_id in doc_ids}

        def _matches(values: list[str | None]) -> bool:
            folded_values = [_fold_for_search(v or "") for v in values]
            return any(term in value for term in terms for value in folded_values)

        def _entity_matches(entity_id: str) -> bool:
            entity = entity_by_id.get(entity_id)
            if entity is None:
                return False
            values = [entity.canonical_name, entity.description, *entity.aliases]
            return _matches(values)

        for claim in claims:
            claim_doc_ids = set(claim.source_ids or [])
            if claim.source_document_id:
                claim_doc_ids.add(claim.source_document_id)
            relevant_doc_ids = claim_doc_ids & doc_ids
            if not relevant_doc_ids:
                continue

            entity_ids = {
                entity_id
                for entity_id in [
                    *claim.entity_ids,
                    claim.subject_entity_id,
                    claim.speaker_entity_id,
                    claim.subject_of_inquiry_entity_id,
                    claim.scribe_entity_id,
                    claim.editor_entity_id,
                ]
                if entity_id
            }
            matched_entity_ids = {
                entity_id for entity_id in entity_ids if _entity_matches(entity_id)
            }
            claim_matches = _matches(
                [
                    claim.text,
                    claim.source_excerpt,
                    claim.subject_canonical,
                    claim.predicate_verb,
                    claim.object_phrase,
                    claim.svo_subject,
                    claim.svo_verb,
                    claim.svo_object,
                ]
            )

            if not claim_matches and not matched_entity_ids:
                continue

            for doc_id in relevant_doc_ids:
                matched_claims_by_doc[doc_id].add(claim.id)
                matched_entities_by_doc[doc_id].update(matched_entity_ids)

        for result in results:
            result.kg_claim_ids = sorted(matched_claims_by_doc[result.document_id])
            result.kg_entity_ids = sorted(matched_entities_by_doc[result.document_id])
        return results

    def _expand_query_with_entity_aliases(self, query: str) -> tuple[list[str], set[str]]:
        """Expand a query with canonical + alias forms from matching entities."""
        terms = _search_match_terms(query)
        if not terms:
            return [], set()

        try:
            from fichero_server.models.knowledge import KnowledgeEntity

            entities = self.all(KnowledgeEntity)
        except Exception as exc:  # noqa: BLE001
            # Degrade to the raw terms, but don't hide WHY alias expansion is
            # off — a silent empty here masks a real KG/DB fault (#2507).
            logger.warning(
                "Query-term entity expansion failed; searching without aliases: %s",
                exc,
            )
            return terms, set()

        expanded = list(terms)
        matched_entity_ids: set[str] = set()
        seen_folded = set(terms)
        for entity in entities:
            surfaces = [entity.canonical_name, *entity.aliases]
            folded_surfaces = [_fold_for_search(s or "") for s in surfaces]
            if not any(
                term in folded_surface or folded_surface in term
                for term in terms
                for folded_surface in folded_surfaces
                if folded_surface
            ):
                continue
            matched_entity_ids.add(entity.id)
            for folded_surface in folded_surfaces:
                if (
                    folded_surface
                    and len(folded_surface) > 1
                    and folded_surface not in seen_folded
                ):
                    expanded.append(folded_surface)
                    seen_folded.add(folded_surface)
        return expanded[:12], matched_entity_ids

    def _entity_bonus_doc_ids(self, matched_entity_ids: set[str]) -> set[str]:
        """Documents linked to claims mentioning matched entities."""
        if not matched_entity_ids:
            return set()
        try:
            from fichero_server.models.knowledge import KnowledgeClaim

            claims = self.all(KnowledgeClaim)
        except Exception as exc:  # noqa: BLE001
            # Rank without the entity boost, but surface the fault rather than
            # silently returning no boosted docs (#2507).
            logger.warning(
                "Entity-bonus doc lookup failed; ranking without entity boost: %s",
                exc,
            )
            return set()

        boosted: set[str] = set()
        for claim in claims:
            claim_entity_ids = set(claim.entity_ids or [])
            if claim.subject_entity_id:
                claim_entity_ids.add(claim.subject_entity_id)
            if claim.speaker_entity_id:
                claim_entity_ids.add(claim.speaker_entity_id)
            if claim.subject_of_inquiry_entity_id:
                claim_entity_ids.add(claim.subject_of_inquiry_entity_id)
            if claim.scribe_entity_id:
                claim_entity_ids.add(claim.scribe_entity_id)
            if claim.editor_entity_id:
                claim_entity_ids.add(claim.editor_entity_id)
            if not (claim_entity_ids & matched_entity_ids):
                continue
            if claim.source_document_id:
                boosted.add(claim.source_document_id)
            boosted.update(claim.source_ids or [])
        return boosted

    def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.0,
        search_type: str = "hybrid",
        filters: dict | None = None,
        sort_by: str = "relevance",
        sort_order: str = "desc",
        offset: int = 0,
        use_fuzzy_match: bool = False,
        highlight_results: bool = True,
    ) -> tuple[list[SearchResult], int, dict]:
        """Enhanced search for documents with hybrid search capabilities.

        Args:
            query: Search query text
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)
            search_type: "semantic", "fulltext", or "hybrid"
            filters: Advanced filters (doc_type, file_type, date ranges, etc.)
            sort_by: "relevance", "date", "name", "size"
            sort_order: "asc" or "desc"
            offset: Pagination offset
            use_fuzzy_match: Use fuzzy matching for full-text search
            highlight_results: Highlight search terms in results

        Returns:
            Tuple of (results, total_count, search_stats)
        """

        if not query or not query.strip():
            return [], 0, {"search_type": "none"}

        start_time = time.time()
        results = []
        total_count = 0
        expanded_terms, matched_entity_ids = self._expand_query_with_entity_aliases(query)
        semantic_query = " ".join(expanded_terms) if expanded_terms else query
        search_stats = {
            "search_type": search_type,
            "execution_time_ms": 0,
            "filters_applied": filters or {},
        }

        try:
            # Initialize results storage
            semantic_results = []
            fulltext_results = []

            # Check if embeddings table exists
            has_embeddings = EMBEDDINGS_TABLE in self._lance_tables()

            # Perform semantic search if requested and available
            if search_type in ["semantic", "hybrid"] and has_embeddings:
                try:
                    # Embed query
                    query_vector = self._embed_text(semantic_query)

                    # Search vectors. Candidate count mirrors the FTS leg
                    # (#4113): the old `limit * 2` ignored `offset`, so deep
                    # pages ran out of semantic candidates and silently
                    # degraded toward fulltext-only ordering.
                    raw_results = self.search_vectors(
                        EMBEDDINGS_TABLE,
                        query_vector,
                        max(limit * 4, offset + limit * 2),
                    )

                    # Convert to SearchResult, filter by score
                    for r in raw_results:
                        document_id = r.get("document_id") or r.get("id")
                        if not self._is_active_document_id(document_id):
                            continue
                        if self._has_indexed_page_children(document_id):
                            continue

                        # LanceDB returns _distance (L2; lower is better).
                        # Vectors are L2-normalised at index + query time
                        # (see db_embeddings._l2_normalize), so L2² = 2 - 2·cos.
                        # That makes `cos = 1 - L2²/2` a real cosine similarity
                        # in [-1, 1], clamped to [0, 1] for ranking.
                        # Without normalisation distances are 200–500 and the
                        # old `1/(1+d)` collapsed everything to ~0.003 (#481).
                        distance = r.get("_distance", 2.0)
                        cos_sim = 1.0 - (distance * distance) / 2.0
                        score = max(0.0, min(1.0, cos_sim))

                        if score < min_score:
                            continue

                        semantic_results.append(
                            {
                                "document_id": document_id,
                                "score": score,
                                "content": r.get("text", ""),
                                "metadata": {
                                    "name": r.get("name"),
                                    "doc_type": r.get("doc_type"),
                                    "file_type": r.get("file_type"),
                                    "created_at": r.get("created_at"),
                                    "updated_at": r.get("updated_at"),
                                    "embedding_scope": r.get("embedding_scope"),
                                    "passage_id": r.get("passage_id"),
                                    "page_id": r.get("page_id"),
                                    "char_start": r.get("char_start"),
                                    "char_end": r.get("char_end"),
                                },
                            }
                        )
                except EmbeddingSpaceMismatchError:
                    raise
                except Exception as e:
                    logger.warning("Semantic search failed: %s", e)

            # Perform full-text search if requested
            if search_type in ["fulltext", "hybrid"]:
                try:
                    # Use DuckDB for full-text search
                    if has_embeddings:
                        table = self.lance.open_table(EMBEDDINGS_TABLE)
                        folded_terms = expanded_terms or [_fold_for_search(query)]
                        candidate_limit = max(limit * 4, offset + limit * 2)
                        raw_fulltext_hits: list[dict] = []
                        if not use_fuzzy_match:
                            raw_fulltext_hits = (
                                table.search(query, query_type="fts", fts_columns="text")
                                .select(
                                    self._lance_select_existing_fields(
                                        table,
                                        [
                                        "document_id",
                                        "id",
                                        "text",
                                        "name",
                                        "doc_type",
                                        "file_type",
                                        "created_at",
                                        "updated_at",
                                        "embedding_scope",
                                        "passage_id",
                                        "page_id",
                                        "char_start",
                                        "char_end",
                                        ],
                                    )
                                )
                                .limit(candidate_limit)
                                .to_list()
                            )

                        if raw_fulltext_hits:
                            for row in raw_fulltext_hits:
                                document_id = row.get("document_id") or row.get("id")
                                if not self._is_active_document_id(document_id):
                                    continue
                                if self._has_indexed_page_children(document_id):
                                    continue
                                folded_content = _fold_for_search(str(row.get("text") or ""))
                                if not any(term and term in folded_content for term in folded_terms):
                                    continue

                                lexical_score = float(row.get("_score", 0.0))
                                fulltext_results.append(
                                    {
                                        "document_id": document_id,
                                        "score": lexical_score,
                                        "content": row.get("text", ""),
                                        "metadata": {
                                            "name": row.get("name"),
                                            "doc_type": row.get("doc_type"),
                                            "file_type": row.get("file_type"),
                                            "created_at": row.get("created_at"),
                                            "updated_at": row.get("updated_at"),
                                            "bm25_score": lexical_score,
                                            "embedding_scope": row.get("embedding_scope"),
                                            "passage_id": row.get("passage_id"),
                                            "page_id": row.get("page_id"),
                                            "char_start": row.get("char_start"),
                                            "char_end": row.get("char_end"),
                                        },
                                    }
                                )
                        else:
                            # ponytail: fuzzy matching and zero-hit accent edge cases still
                            # use the old corpus scan until we can index folded text.
                            all_docs = table.to_pandas()
                            normalised_text = all_docs["text"].astype(str).map(_fold_for_search)
                            mask = (
                                _fuzzy_contains_any_term(normalised_text, folded_terms)
                                if use_fuzzy_match
                                else _contains_any_term(normalised_text, folded_terms)
                            )

                            fulltext_docs = all_docs[mask].copy()
                            fulltext_docs["folded_text"] = (
                                fulltext_docs["text"].astype(str).map(_fold_for_search)
                            )
                            bm25_scores = _bm25_scores(
                                fulltext_docs["folded_text"].tolist(),
                                [t for t in folded_terms if t],
                            )
                            fulltext_docs["bm25"] = bm25_scores

                            for _, row in fulltext_docs.sort_values("bm25", ascending=False).iterrows():
                                document_id = row.get("document_id") or row.get("id")
                                if not self._is_active_document_id(document_id):
                                    continue
                                if self._has_indexed_page_children(document_id):
                                    continue

                                lexical_score = float(row.get("bm25", 0.0))
                                fulltext_results.append(
                                    {
                                        "document_id": document_id,
                                        "score": lexical_score,
                                        "content": row.get("text", ""),
                                        "metadata": {
                                            "name": row.get("name"),
                                            "doc_type": row.get("doc_type"),
                                            "file_type": row.get("file_type"),
                                            "created_at": row.get("created_at"),
                                            "updated_at": row.get("updated_at"),
                                            "bm25_score": lexical_score,
                                            "embedding_scope": row.get("embedding_scope"),
                                            "passage_id": row.get("passage_id"),
                                            "page_id": row.get("page_id"),
                                            "char_start": row.get("char_start"),
                                            "char_end": row.get("char_end"),
                                        },
                                    }
                                )

                        max_bm25 = max((result["score"] for result in fulltext_results), default=0.0)
                        for result in fulltext_results:
                            result["score"] = (
                                max(0.0, min(1.0, result["score"] / max_bm25))
                                if max_bm25 > 0
                                else 1.0
                            )
                except Exception as e:
                    logger.warning("Full-text search failed: %s", e)

            # Hybrid combiner: Reciprocal Rank Fusion (RRF).
            #
            # RRF ranks each list independently and sums 1/(k+rank) across
            # lists. A doc that ranks #1 in fulltext AND #1 in semantic
            # scores 2/(k+1); ranking only in one list scores half that.
            # The k=60 constant is the standard literature value (Cormack
            # et al., 2009) — small enough that top ranks dominate, large
            # enough that lower ranks still contribute.
            #
            # RRF replaces an earlier max(score) hack which broke when
            # semantic + fulltext scores live on different scales. With
            # L2-normalised embeddings semantic scores are real cosines
            # in [0,1], but fulltext is still 1.0 perfect-match —
            # combining them by max() over-weighted any string match. RRF
            # ignores absolute scores and uses only ordering, which is
            # exactly the right thing when the two retrievers are
            # calibrated differently. (#481)
            combined_results = []
            if search_type == "hybrid":
                rrf_k = 60
                merged: dict[str, dict] = {}

                def _rrf_add(items: list[dict], source: str) -> None:
                    for rank, item in enumerate(items):
                        doc_id = item["document_id"]
                        contribution = 1.0 / (rrf_k + rank + 1)
                        if doc_id in merged:
                            prior = merged[doc_id]
                            prior["_rrf"] += contribution
                            if source == "fulltext":
                                prior["_lexical_score"] = max(
                                    prior.get("_lexical_score", 0.0),
                                    item.get("score", 0.0),
                                )
                            prior["match_sources"] = sorted(
                                set(prior["match_sources"]) | {source}
                            )
                            # Prefer fulltext content snippet (real text)
                            # over semantic excerpt when both available.
                            if source == "fulltext" and item.get("content"):
                                prior["content"] = item["content"]
                        else:
                            enriched = dict(item)
                            enriched["_rrf"] = contribution
                            enriched["_lexical_score"] = (
                                item.get("score", 0.0) if source == "fulltext" else 0.0
                            )
                            enriched["match_sources"] = [source]
                            merged[doc_id] = enriched

                _rrf_add(semantic_results, "semantic")
                _rrf_add(fulltext_results, "fulltext")

                # Project the RRF score into [0, 1] for UI display:
                # the theoretical max with both lists ranking the doc #1
                # is 2/(k+1); divide by that for a normalised [0, 1].
                rrf_max = 2.0 / (rrf_k + 1)
                for item in merged.values():
                    item["score"] = min(1.0, item["_rrf"] / rrf_max)
                    item.pop("_rrf", None)
                    # ponytail: exact/keyword matches need a small edge over
                    # semantic-only neighbours when RRF ties them at 0.5.
                    item["score"] = min(
                        1.0,
                        item["score"] + (0.1 * item.pop("_lexical_score", 0.0)),
                    )
                # Apply min_score to the normalised RRF projection.
                # Docs that appear only in semantic results and rank poorly
                # get RRF scores of ~0.40-0.44 in a 15-doc corpus — the
                # tight 42-50% band that returns the whole library for a
                # rare query (#1054). The pre-RRF semantic filter (above)
                # already removed scores below min_score in cosine space;
                # this second pass catches docs that scraped past that floor
                # but then ranked near the bottom of the fusion list.
                if min_score > 0:
                    combined_results = [
                        r for r in merged.values() if r["score"] >= min_score
                    ]
                else:
                    combined_results = list(merged.values())
            elif search_type == "semantic":
                combined_results = semantic_results
            elif search_type == "fulltext":
                combined_results = fulltext_results

            # Entity-aware rank bonus: when query aliases resolve to a
            # canonical entity, nudge docs linked to that entity upward.
            boosted_doc_ids = self._entity_bonus_doc_ids(matched_entity_ids)
            if boosted_doc_ids:
                for item in combined_results:
                    if item["document_id"] in boosted_doc_ids:
                        item["score"] = min(1.0, item["score"] + 0.1)

            # Apply filters
            if filters:
                # Per-folder scope: when filters['folder_id'] is set, drop
                # results that aren't descendants of that folder. Walks
                # parent_id one hop at a time to keep the query simple;
                # for deeply nested trees the recursive variant could be
                # added later. Resolved once before the per-result loop.
                folder_descendants: set[str] | None = None
                if "folder_id" in filters and filters["folder_id"]:
                    folder_descendants = self._collect_folder_descendants(
                        str(filters["folder_id"])
                    )

                filtered_results = []
                for result in combined_results:
                    metadata = result["metadata"]
                    match = True

                    if folder_descendants is not None:
                        if result["document_id"] not in folder_descendants:
                            match = False

                    # Filter by doc_type
                    if (
                        "doc_type" in filters
                        and metadata.get("doc_type") != filters["doc_type"]
                    ):
                        match = False

                    # Filter by file_type
                    if (
                        "file_type" in filters
                        and metadata.get("file_type") != filters["file_type"]
                    ):
                        match = False

                    # Filter by date range
                    if "date_from" in filters or "date_to" in filters:
                        created_at = metadata.get("created_at")
                        if created_at:
                            try:
                                created_date = datetime.fromisoformat(created_at)
                                if "date_from" in filters:
                                    from_date = datetime.fromisoformat(
                                        filters["date_from"]
                                    )
                                    if created_date < from_date:
                                        match = False
                                if "date_to" in filters:
                                    to_date = datetime.fromisoformat(filters["date_to"])
                                    if created_date > to_date:
                                        match = False
                            except (ValueError, TypeError):
                                pass

                    if match:
                        filtered_results.append(result)
                combined_results = filtered_results

            # Sort results
            if sort_by == "relevance":
                combined_results.sort(
                    key=lambda x: x["score"], reverse=(sort_order == "desc")
                )
            elif sort_by == "date" and any(
                r["metadata"].get("created_at") for r in combined_results
            ):
                combined_results.sort(
                    key=lambda x: x["metadata"].get("created_at", ""),
                    reverse=(sort_order == "desc"),
                )
            elif sort_by == "name":
                combined_results.sort(
                    key=lambda x: x["metadata"].get("name", ""),
                    reverse=(sort_order == "desc"),
                )
            elif sort_by == "size":
                # sort_by="size" was validated at the route but silently fell
                # through to insertion order (#4109). The result rows don't
                # carry a size, so look it up per document — the candidate
                # set is at most a few multiples of `limit`, so per-id gets
                # are fine here. Docs without a recorded file_size sort last.
                from fichero_server.models import Document as _SizeDoc

                doc_sizes: dict[str, int] = {}
                for item in combined_results:
                    doc = self.get(_SizeDoc, item["document_id"])
                    size = doc.file_size if doc is not None else None
                    doc_sizes[item["document_id"]] = (
                        size if isinstance(size, int) else -1
                    )
                combined_results.sort(
                    key=lambda x: doc_sizes.get(x["document_id"], -1),
                    reverse=(sort_order == "desc"),
                )

            # Apply pagination
            total_count = len(combined_results)
            paginated_results = combined_results[offset : offset + limit]

            # Convert to SearchResult objects with highlighting
            for result in paginated_results:
                content = result["content"]
                highlights = None
                transcript_excerpts = _build_transcript_excerpts(
                    document_id=result["document_id"],
                    content=content,
                    query=query,
                )

                if highlight_results and query:
                    # Simple highlighting - find query in content
                    # Escape special regex characters in query
                    escaped_query = re.escape(query)
                    # Find all occurrences (case insensitive)
                    matches = re.finditer(escaped_query, content, re.IGNORECASE)
                    highlights = []
                    for match in matches:
                        start = max(0, match.start() - 20)
                        end = min(len(content), match.end() + 20)
                        snippet = content[start:end]
                        # Highlight the matched text
                        highlighted = snippet.replace(
                            match.group(), f"**{match.group()}**"
                        )
                        highlights.append(highlighted)

                results.append(
                    SearchResult(
                        document_id=result["document_id"],
                        score=result["score"],
                        content_preview=_search_result_preview(
                            result["content"],
                            transcript_excerpts,
                        ),
                        metadata=result["metadata"],
                        highlights=highlights,
                        transcript_excerpts=transcript_excerpts,
                    )
                )

            self.enrich_search_results_with_kg(results, query)

            # Calculate execution time
            execution_time = time.time() - start_time
            search_stats["execution_time_ms"] = execution_time * 1000
            search_stats["total_results"] = total_count
            search_stats["returned_results"] = len(results)
            search_stats["has_more"] = (offset + len(results)) < total_count

            return results, total_count, search_stats

        except EmbeddingSpaceMismatchError:
            raise
        except Exception as e:
            # Prefer raise over silent fallback (#4109): returning ([], 0,
            # {"error": ...}) made a FAILED search indistinguishable from an
            # empty one — HTTP 200 with zero results. Raise typed so the route
            # can answer 500 and the UI can say "search failed", not "no hits".
            logger.error("Search failed: %s", e)
            raise SearchExecutionError(f"search failed: {e}") from e

    # =========================================================================
    # Trace JSONL Export (for debug logs)
    # =========================================================================
    # reindex_all, embedding_stats, and embedding helpers are in DatabaseEmbeddingMixin
    # (fichero_server.db.embeddings)

    def export_traces_jsonl(self, run_id: str, path: str | Path | None = None) -> Path:
        """Export all traces for a run to JSONL file.

        Per DATA_MODEL_PLAN: Full trace logs go to JSONL files for debug.

        Args:
            run_id: Run ID to export traces for
            path: Output path, or auto-generates in traces/ dir

        Returns:
            Path to the JSONL file
        """
        from fichero_server.models import Trace

        traces = self.query(Trace, run_id=run_id)

        if path is None:
            traces_dir = self.path.parent / "traces"
            traces_dir.mkdir(exist_ok=True)
            path = traces_dir / f"{run_id}.jsonl"
        else:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            for trace in traces:
                f.write(trace.model_dump_json() + "\n")

        logger.debug("Exported %s traces to %s", len(traces), path)
        return path

    def import_traces_jsonl(self, path: str | Path) -> int:
        """Import traces from JSONL file.

        Args:
            path: Path to JSONL file

        Returns:
            Number of traces imported
        """
        from fichero_server.models import Trace

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Trace file not found: {path}")

        count = 0
        with open(path) as f:
            for line in f:
                if line.strip():
                    trace = Trace.model_validate_json(line)
                    self.save(trace)
                    count += 1

        logger.debug("Imported %s traces from %s", count, path)
        return count

    # =========================================================================
    # Parquet Export/Import
    # =========================================================================

    def export_parquet(self, model: Type[T], path: str | Path) -> None:
        """Export a table to Parquet file."""
        sql_table = self._sql_table_name(model)
        self._ensure_table(model)
        self.conn.execute(f"COPY {sql_table} TO '{path}' (FORMAT PARQUET)")

    def export_jsonl_as_parquet(
        self,
        jsonl_path: str | Path,
        output_path: str | Path,
        *,
        empty: bool = False,
    ) -> None:
        """Convert JSON Lines to Parquet through the managed DuckDB connection."""
        destination_path = str(output_path).replace("'", "''")
        relation = "read_json_auto(?)"
        if empty:
            relation = f"(SELECT * FROM {relation} WHERE FALSE)"
        self.execute(
            f"COPY (SELECT * FROM {relation}) TO '{destination_path}' (FORMAT PARQUET)",
            (str(jsonl_path),),
        )

    def import_parquet(self, model: Type[T], path: str | Path) -> int:
        """Import from Parquet file, returns count of imported rows."""
        sql_table = self._sql_table_name(model)
        self._ensure_table(model)
        library_root = self.path.parent
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = library_root / candidate
        confined_path = resolve_under_allowed_roots(candidate, [library_root])
        if confined_path is None:
            raise ValueError(f"Parquet path must stay inside the library package: {path}")

        parquet_columns = self.conn.from_parquet(str(confined_path)).columns
        for column in parquet_columns:
            _validated_identifier(column, kind="Parquet column name")

        # Count before
        before = self.count(model)

        # Import
        self.conn.execute(f"""
            INSERT INTO {sql_table}
            SELECT * FROM read_parquet(?)
        """, [str(confined_path)])

        # Return new rows
        after = self.count(model)
        return after - before

    # =========================================================================
    # Helpers
    # =========================================================================

    def _parse_json_fields(self, model: Type[BaseModel], data: dict) -> dict:
        """Parse JSON string fields back to Python dicts/lists/tuples."""
        result = {}
        for name, field_info in model.model_fields.items():
            value = data.get(name)
            if value is None:
                # For non-Optional fields, substitute the field's default when the
                # DB returns NULL (common after schema migration adds a new column).
                annotation = field_info.annotation
                raw_origin = get_origin(annotation)
                is_optional = raw_origin is Union or raw_origin is UnionType
                if not is_optional:
                    inner = annotation
                    inner_origin = get_origin(inner)
                    if inner is dict or inner_origin is dict or inner is list or inner_origin is list:
                        default_factory = getattr(field_info, "default_factory", None)
                        if callable(default_factory):
                            result[name] = default_factory()
                            continue
                    # Scalar default (e.g. enum fields added after initial schema).
                    scalar_default = field_info.default
                    if not isinstance(scalar_default, PydanticUndefinedType):
                        result[name] = scalar_default
                        continue
                result[name] = value
                continue

            # Check if field expects dict, list, or tuple
            annotation = field_info.annotation
            origin = get_origin(annotation)

            # Handle Optional types (Union or | syntax)
            if origin is Union or origin is UnionType:
                args = get_args(annotation)
                for arg in args:
                    if arg is not type(None):
                        annotation = arg
                        origin = get_origin(annotation)
                        break

            # Re-check origin after unwrapping Optional
            inner_origin = get_origin(annotation)

            # If field expects dict/list and we got a string, parse it
            if (
                annotation is dict
                or inner_origin is dict
                or annotation is list
                or inner_origin is list
            ):
                if isinstance(value, str):
                    try:
                        result[name] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[name] = value
                else:
                    result[name] = value
            # If field expects tuple, parse JSON and convert to tuple
            elif annotation is tuple or inner_origin is tuple:
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        result[name] = (
                            tuple(parsed) if isinstance(parsed, list) else value
                        )
                    except (json.JSONDecodeError, TypeError):
                        result[name] = value
                elif isinstance(value, list):
                    result[name] = tuple(value)
                else:
                    result[name] = value
            # If field expects a nested Pydantic model, parse JSON and
            # reconstruct the typed instance. Without this, fields like
            # `KnowledgeClaim.claim_geo: GeoPoint | None` (#1123) and the
            # latent `KnowledgeClaim.source_metadata: SourceMetadata | None`
            # come back as raw JSON strings and fail Pydantic validation
            # on load. Save side already JSON-encodes BaseModel via the
            # `_json_safe` recursion in `Database.save`; this is the
            # symmetric read-side handling.
            elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        result[name] = (
                            annotation.model_validate(parsed)
                            if isinstance(parsed, dict)
                            else value
                        )
                    except (json.JSONDecodeError, TypeError):
                        result[name] = value
                else:
                    result[name] = value
            else:
                result[name] = value

        return result

    def _hydrate_row(
        self,
        model: Type[T],
        columns: Sequence[str],
        row: Sequence[Any],
    ) -> T | None:
        """Convert a raw DuckDB row to a typed model, skipping null-PK ghosts.

        DuckDB can surface legacy/corrupt rows with every field NULL even when
        the table declares ``PRIMARY KEY (id)``. Those rows are not addressable
        by the typed API and should not make ordinary table scans fail.
        """
        raw = dict(zip(columns, row))
        if "id" in model.model_fields and raw.get("id") is None:
            logger.warning(
                "Skipping invalid %s row with NULL id in %s",
                model.__name__,
                self.path,
            )
            return None
        return model(**self._parse_json_fields(model, raw))

    def _table_name(self, obj_or_model) -> str:
        """Get table name from model class (lowercase + 's')."""
        if isinstance(obj_or_model, type) and obj_or_model.__name__ == "CanvasLayout":
            return "canvas_layout"
        if (
            not isinstance(obj_or_model, type)
            and type(obj_or_model).__name__ == "CanvasLayout"
        ):
            return "canvas_layout"
        if isinstance(obj_or_model, type):
            return obj_or_model.__name__.lower() + "s"
        return type(obj_or_model).__name__.lower() + "s"

    def _sql_table_name(self, obj_or_model) -> str:
        """Quote a table name for DuckDB SQL."""
        return f'"{self._table_name(obj_or_model)}"'

    def _ensure_table(self, model: Type[BaseModel]) -> None:
        """Create table if it doesn't exist."""
        table = self._table_name(model)
        sql_table = self._sql_table_name(model)

        with self._lock:
            # The schema is immutable for the lifetime of a healthy connection.
            # _materialize_schema() discards each entry before reconciliation,
            # and _reconnect_after_invalidated() clears the whole set, so both
            # existing invalidation paths still force a fresh check.
            if table in self._tables_created:
                return

            def _execute_locked(sql: str):
                for attempt in range(_DUCKDB_WRITE_CONFLICT_RETRIES + 1):
                    try:
                        return self.conn.execute(sql)
                    except duckdb.Error as exc:
                        if self._is_invalidated_error(exc):
                            logger.warning(
                                "DuckDB connection for %s was invalidated during schema reconciliation; reopening and retrying",
                                self.path,
                            )
                            self._reconnect_after_invalidated()
                            continue
                        if not self._is_write_conflict_error(exc):
                            raise
                        if attempt >= _DUCKDB_WRITE_CONFLICT_RETRIES:
                            raise RuntimeError(
                                "DuckDB write conflict did not resolve after "
                                f"{_DUCKDB_WRITE_CONFLICT_RETRIES} retries for {self.path}. "
                                "The library is receiving concurrent writes; retry the operation."
                            ) from exc
                        delay = _DUCKDB_WRITE_CONFLICT_BACKOFF_SECONDS * (attempt + 1)
                        logger.warning(
                            "DuckDB write conflict for %s during schema reconciliation; retrying in %.3fs (%s/%s)",
                            self.path,
                            delay,
                            attempt + 1,
                            _DUCKDB_WRITE_CONFLICT_RETRIES,
                        )
                        time.sleep(delay)
                raise RuntimeError("DuckDB schema reconciliation retry loop exited unexpectedly")

            first_reconcile_this_connection = table not in self._tables_created

            # Build column definitions from Pydantic model
            columns = []
            for name, field_info in model.model_fields.items():
                col_type = self._python_to_duckdb_type(field_info.annotation)
                columns.append(f"{name} {col_type}")

            if first_reconcile_this_connection:
                _execute_locked(f"""
                    CREATE TABLE IF NOT EXISTS {sql_table} (
                        {", ".join(columns)},
                        PRIMARY KEY (id)
                    )
                """)

            # Reconcile columns for tables that already existed from an earlier
            # schema. The 0.0.x no-migration rule says "add the field to the model
            # and fresh DBs pick it up" — but a pre-existing library (created before
            # the field was added) keeps its old table and CREATE TABLE IF NOT
            # EXISTS is a no-op for it. Without this, `save()` of a model with a new
            # field hits "Table X does not have a column named Y" (e.g.
            # provenance_chain on a Document table from before that field landed).
            # ADD COLUMN is non-destructive and idempotent, so this is the generic
            # mechanism that makes the no-migration rule hold for existing DBs too.
            try:
                existing = {
                    row[1]
                    for row in _execute_locked(f"PRAGMA table_info({sql_table})").fetchall()
                }
            except Exception:
                existing = {
                    row[0]
                    for row in _execute_locked(
                        f"SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name = '{table}'"
                    ).fetchall()
                }
            for name, field_info in model.model_fields.items():
                if name not in existing:
                    col_type = self._python_to_duckdb_type(field_info.annotation)
                    _execute_locked(
                        f"ALTER TABLE {sql_table} ADD COLUMN {name} {col_type}"
                    )

            self._tables_created.add(table)

            # Apply knowledge-table indices once both knowledgeclaims AND
            # knowledgeentitys exist. Cheap (each CREATE INDEX IF NOT EXISTS
            # is a no-op when already present); critical for query latency
            # at 50K+ claims. (#991 — scaling-review bottleneck 2)
            if first_reconcile_this_connection and table in {"knowledgeclaims", "knowledgeentitys"}:
                from fichero_server.db.migrations.schema import migrate_knowledge_indices
                migrate_knowledge_indices(self.conn)

    def _python_to_duckdb_type(self, python_type) -> str:
        """Map Python types to DuckDB types."""
        type_map = {
            str: "VARCHAR",
            int: "INTEGER",
            float: "DOUBLE",
            bool: "BOOLEAN",
            datetime: "TIMESTAMP",
            dict: "JSON",
            list: "JSON",
            tuple: "JSON",
        }

        # Handle Optional, Union types (including | syntax)
        origin = get_origin(python_type)
        if origin is Union or origin is UnionType:
            args = get_args(python_type)
            # Get first non-None type
            for arg in args:
                if arg is not type(None):
                    python_type = arg
                    break

        # Handle Enum
        if hasattr(python_type, "__mro__") and any(
            c.__name__ == "Enum" for c in getattr(python_type, "__mro__", [])
        ):
            return "VARCHAR"

        # Handle parameterized types like tuple[int, int, int, int]
        origin = get_origin(python_type)
        if origin is not None:
            return type_map.get(origin, "VARCHAR")

        return type_map.get(python_type, "VARCHAR")

    def close(self) -> None:
        """Release database and vector-store handles."""
        self._lance_db = None
        self.conn.close()

    def _migrate_workflow_table(self) -> None:
        """Delegate to db_migrations.migrate_workflow_table."""
        from fichero_server.db.migrations.schema import migrate_workflow_table
        migrate_workflow_table(self.conn)

    def _migrate_saved_search_table(self) -> None:
        """Delegate to db_migrations.migrate_saved_search_table."""
        from fichero_server.db.migrations.schema import migrate_saved_search_table
        migrate_saved_search_table(self.conn)

    def _migrate_provider_refs_table(self) -> None:
        """Delegate to db_migrations.migrate_provider_refs_table."""
        from fichero_server.db.migrations.schema import migrate_provider_refs_table
        migrate_provider_refs_table(self.conn)

    def _migrate_activity_tables(self) -> None:
        """Delegate to db_migrations.migrate_activity_tables."""
        from fichero_server.db.migrations.schema import migrate_activity_tables
        migrate_activity_tables(self.conn)

    def _migrate_checkpoint_tables(self) -> None:
        """Delegate to db_migrations.migrate_checkpoint_tables."""
        from fichero_server.db.migrations.schema import migrate_checkpoint_tables
        migrate_checkpoint_tables(self.conn)


# Backward-compatibility alias used by older tests/tooling that patch `fichero_server.db.db`.
db = db_manager
