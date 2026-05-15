"""
Fichero Database Layer

Simple Pythonic wrapper for DuckDB + LanceDB.
- DuckDB: Documents, artifacts, workflows, runs
- LanceDB: Vector search (embeddings)

Usage:
    from fichero.db import db
    from fichero.models import Document, Artifact, Workflow, Run

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

from pathlib import Path
from types import UnionType
from typing import TypeVar, Type, get_origin, get_args, Union, Any
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import re
import time
import unicodedata
import duckdb
from pydantic import BaseModel
from fichero.db_embeddings import DatabaseEmbeddingMixin
from fichero.db_manager import DatabaseManager, db_manager  # noqa: F401
from fichero.errors import ErrorCategory, handle_error

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Minimum content length to create embedding
MIN_CONTENT_LENGTH = 10

# Default embedding model (FastEmbed - no scikit-learn dependency)
# Using multilingual model for Spanish + English support
DEFAULT_MODEL = "intfloat/multilingual-e5-large"

# Valid identifier pattern for SQL column/table names
_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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


# Markers transcribe writes when a page is blank or unreadable. When
# page_content is just a marker, embedding it makes every marker-only
# doc share an identical vector and cluster at the top of every
# semantic query (#481 follow-up). _is_content_marker_only catches
# this so db.embed() can fall back to the doc's name.
_MARKER_PATTERNS = (
    "[sin texto]",
    "[ilegible]",
    "[no text]",
    "[blank]",
    "[empty]",
    "[unreadable]",
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


@dataclass
class SearchResult:
    """Search result with score and document reference."""

    document_id: str
    score: float
    content_preview: str
    metadata: dict[str, Any]
    highlights: list[str] | None = None  # Highlighted text snippets

    def __repr__(self) -> str:
        preview = (
            self.content_preview[:50] + "..."
            if len(self.content_preview) > 50
            else self.content_preview
        )
        return f"SearchResult(id={self.document_id}, score={self.score:.3f}, preview='{preview}')"


class Database(DatabaseEmbeddingMixin):
    """Simple Pythonic wrapper for DuckDB + LanceDB."""

    def __init__(self, path: str | Path | None = None):
        """
        Initialize database connection.

        Args:
            path: Path to database file. Defaults to ~/Library/Application Support/com.fichero.fichero/library.duckdb
        """
        if path is None:
            from fichero.storage import settings

            path = settings.db_path
        else:
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = duckdb.connect(str(path))
        self.duck = self.conn  # Alias used by ActionStore and other direct SQL callers
        self._lance_path = path.parent / "vectors"
        self._lance_db = None  # Lazy init
        self._embedder = None  # Lazy init
        self._tables_created: set[str] = set()

        # Migrate tables if needed
        from fichero.db_migrations import (
            migrate_document_table,
            migrate_knowledge_claims_provider_model,
            migrate_workflow_table,
            migrate_saved_search_table,
            migrate_provider_refs_table,
        )
        migrate_document_table(self.conn)
        migrate_workflow_table(self.conn)
        migrate_saved_search_table(self.conn)
        migrate_provider_refs_table(self.conn)
        migrate_knowledge_claims_provider_model(self.conn)

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    def save(self, obj: BaseModel, auto_embed: bool = False) -> None:
        """Save a Pydantic object (insert or update by ID).

        Args:
            obj: Pydantic model instance to save
            auto_embed: If True, create embedding when obj has page_content
        """
        table = self._table_name(obj)
        self._ensure_table(type(obj))

        # Exclude computed fields (they're derived, not stored)
        model_cls = type(obj)
        computed_keys = (
            set(model_cls.model_computed_fields.keys())
            if hasattr(model_cls, "model_computed_fields")
            else set()
        )
        data = obj.model_dump(exclude=computed_keys)

        # Convert dict/list/tuple/Path fields for DuckDB (recursively handle nested Pydantic models with datetimes)
        def _json_safe(obj):
            """Recursively convert Pydantic models and datetime for JSON serialization."""
            if isinstance(obj, BaseModel):
                return _json_safe(obj.model_dump())
            elif isinstance(obj, dict):
                return {k: _json_safe(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [_json_safe(item) for item in obj]
            elif isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        for key, value in data.items():
            if isinstance(value, (dict, list, tuple)):
                data[key] = json.dumps(_json_safe(value))
            elif isinstance(value, Path):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()

        # Build upsert query
        cols = list(data.keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(f"${c}" for c in cols)

        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
            data,
        )

        # Auto-embed if requested and has content
        if auto_embed and hasattr(obj, "page_content") and obj.page_content:
            self.embed(obj)

    def get(self, model: Type[T], id: str) -> T | None:
        """Get a single object by ID."""
        table = self._table_name(model)
        self._ensure_table(model)

        result = self.conn.execute(
            f"SELECT * FROM {table} WHERE id = $id", {"id": id}
        ).fetchone()

        if result is None:
            return None

        columns = [desc[0] for desc in self.conn.description]
        row_dict = self._parse_json_fields(model, dict(zip(columns, result)))
        return model(**row_dict)

    def all(self, model: Type[T]) -> list[T]:
        """Get all objects of a type."""
        table = self._table_name(model)
        self._ensure_table(model)

        rows = self.conn.execute(f"SELECT * FROM {table}").fetchall()

        if not rows:
            return []

        columns = [desc[0] for desc in self.conn.description]
        return [
            model(**self._parse_json_fields(model, dict(zip(columns, row))))
            for row in rows
        ]

    def query(self, model: Type[T], **filters) -> list[T]:
        """Query with simple equality filters."""
        table = self._table_name(model)
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
        rows = self.conn.execute(
            f"SELECT * FROM {table} WHERE {where}", query_filters
        ).fetchall()

        if not rows:
            return []

        columns = [desc[0] for desc in self.conn.description]
        return [
            model(**self._parse_json_fields(model, dict(zip(columns, row))))
            for row in rows
        ]

    def delete(self, obj: BaseModel) -> None:
        """Delete an object by ID."""
        table = self._table_name(obj)
        self._ensure_table(type(obj))

        self.conn.execute(f"DELETE FROM {table} WHERE id = $id", {"id": obj.id})

    def count(self, model: Type[T], **filters) -> int:
        """Count objects matching filters."""
        table = self._table_name(model)
        self._ensure_table(model)

        if not filters:
            result = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        else:
            # Validate column names to prevent SQL injection
            for k in filters.keys():
                if not _VALID_IDENTIFIER.match(k):
                    raise ValueError(f"Invalid column name: {k}")

            where = " AND ".join(f"{k} = ${k}" for k in filters.keys())
            result = self.conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {where}", filters
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

    def save_vectors(self, table_name: str, data: list[dict]) -> None:
        """Save data to LanceDB table (creates or appends)."""
        if table_name in self._lance_tables():
            table = self.lance.open_table(table_name)
            table.add(data)
        else:
            self.lance.create_table(table_name, data)

    def search_vectors(
        self, table_name: str, query_vector: list[float], limit: int = 10
    ) -> list[dict]:
        """Search LanceDB table by vector similarity."""
        if table_name not in self._lance_tables():
            return []

        table = self.lance.open_table(table_name)
        results = table.search(query_vector).limit(limit).to_list()
        return results

    # =========================================================================
    # Embedding Convenience Methods
    # =========================================================================

    def save_embedding(
        self, doc: BaseModel, vector: list[float], text: str | None = None
    ) -> None:
        """Save document embedding to LanceDB.

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

        record = {
            "id": doc.id,
            "document_id": doc.id,
            "text": content,
            "vector": vector,
            # Store document metadata for search results display
            "name": getattr(doc, "name", None),
            "doc_type": getattr(doc, "doc_type", None).value
            if hasattr(doc, "doc_type") and doc.doc_type
            else None,
            "file_type": getattr(doc, "file_type", None).value
            if hasattr(doc, "file_type") and doc.file_type
            else None,
        }

        self.save_vectors("embeddings", [record])

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
        results = self.search_vectors("embeddings", query_vector, limit)

        if model is None:
            return results

        # Convert to model instances
        doc_ids = [r.get("document_id") or r.get("id") for r in results]
        return [self.get(model, id) for id in doc_ids if id]

    def delete_embedding(self, doc_id: str) -> bool:
        """Delete embedding for a document.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted
        """
        try:
            if "embeddings" not in self._lance_tables():
                return False

            # Validate doc_id to prevent injection
            if not doc_id or not _VALID_IDENTIFIER.match(doc_id.replace("-", "")):
                # UUIDs contain hex chars and hyphens - just sanitize quotes
                safe_id = doc_id.replace("'", "''")
            else:
                safe_id = doc_id

            table = self.lance.open_table("embeddings")
            table.delete(f"id = '{safe_id}'")
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
            if "embeddings" not in self._lance_tables():
                return False

            # Sanitize doc_id to prevent injection
            safe_id = doc_id.replace("'", "''") if doc_id else ""

            table = self.lance.open_table("embeddings")
            results = table.search().where(f"id = '{safe_id}'").limit(1).to_list()
            return len(results) > 0
        except Exception:
            return False

    # =========================================================================
    # Semantic Search
    # =========================================================================

    def embed(self, doc: BaseModel) -> bool:
        """Create embedding for a document.

        Uses document's page_content if available, otherwise name.
        Embedding is stored in LanceDB for vector search.

        Args:
            doc: Document model with id and optionally page_content

        Returns:
            True if embedding was created
        """
        # Get text to embed.
        #
        # Marker-only content guard: when transcribe runs against a blank
        # or unreadable page it sets page_content to '[sin texto]' (or
        # '[ilegible]'). Embedding that literal string makes every
        # marker-only doc share an identical vector, and they cluster at
        # the top of every semantic query (the 95%-on-blank-doc bug
        # Daniel hit on the social-license search). Treat marker-only
        # content as 'no content' and fall back to the doc's name —
        # which at least varies per-doc and reflects the legal-case
        # / archive structure the user is browsing.
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
            return False

        try:
            vector = self._embed_text(text)
            self.save_embedding(doc, vector, text[:500])
            logger.debug("Created embedding for %s", doc.id)
            return True
        except Exception as e:
            logger.warning("Failed to create embedding for %s: %s", doc.id, e)
            return False

    def _collect_folder_descendants(self, folder_id: str) -> set[str]:
        """Wrap the free helper so callers don't reach into module level."""
        return _collect_folder_descendants_helper(self.conn, folder_id)

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
            has_embeddings = "embeddings" in self._lance_tables()

            # Perform semantic search if requested and available
            if search_type in ["semantic", "hybrid"] and has_embeddings:
                try:
                    # Embed query
                    query_vector = self._embed_text(query)

                    # Search vectors
                    table = self.lance.open_table("embeddings")
                    raw_results = (
                        table.search(query_vector).limit(limit * 2).to_list()
                    )  # Get more for hybrid

                    # Convert to SearchResult, filter by score
                    for r in raw_results:
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
                                "document_id": r.get("document_id") or r.get("id"),
                                "score": score,
                                "content": r.get("text", ""),
                                "metadata": {
                                    "name": r.get("name"),
                                    "doc_type": r.get("doc_type"),
                                    "file_type": r.get("file_type"),
                                    "created_at": r.get("created_at"),
                                    "updated_at": r.get("updated_at"),
                                },
                            }
                        )
                except Exception as e:
                    logger.warning("Semantic search failed: %s", e)

            # Perform full-text search if requested
            if search_type in ["fulltext", "hybrid"]:
                try:
                    # Use DuckDB for full-text search
                    if has_embeddings:
                        # Get all documents from embeddings table for full-text search
                        table = self.lance.open_table("embeddings")
                        all_docs = table.to_pandas()

                        # Accent-insensitive match: NFD-decompose both
                        # query and indexed text, strip combining diacritics.
                        # 'Quibdó' / 'Quibdo' / 'QUIBDÓ' all match. Critical
                        # for Spanish/Latin manuscript corpora where the
                        # user types ASCII but the text is fully diacritic.
                        # See _fold_for_search.
                        normalised_query = _fold_for_search(query)
                        normalised_text = all_docs["text"].astype(str).map(_fold_for_search)
                        # Phrase mode: a quoted query like '"el escribano"' is
                        # already-stripped at the caller; we just match its
                        # full collapsed form. Substring fallback otherwise.
                        mask = normalised_text.str.contains(
                            normalised_query, case=False, regex=False, na=False
                        )

                        fulltext_docs = all_docs[mask]

                        # Convert to results format
                        for _, row in fulltext_docs.iterrows():
                            fulltext_results.append(
                                {
                                    "document_id": row.get("document_id")
                                    or row.get("id"),
                                    "score": 1.0,  # Full-text match gets high score
                                    "content": row.get("text", ""),
                                    "metadata": {
                                        "name": row.get("name"),
                                        "doc_type": row.get("doc_type"),
                                        "file_type": row.get("file_type"),
                                        "created_at": row.get("created_at"),
                                        "updated_at": row.get("updated_at"),
                                    },
                                }
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
                combined_results = list(merged.values())
            elif search_type == "semantic":
                combined_results = semantic_results
            elif search_type == "fulltext":
                combined_results = fulltext_results

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

            # Apply pagination
            total_count = len(combined_results)
            paginated_results = combined_results[offset : offset + limit]

            # Convert to SearchResult objects with highlighting
            for result in paginated_results:
                content = result["content"]
                highlights = None

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
                        content_preview=result["content"][:200] + "..."
                        if len(result["content"]) > 200
                        else result["content"],
                        metadata=result["metadata"],
                        highlights=highlights,
                    )
                )

            # Calculate execution time
            execution_time = time.time() - start_time
            search_stats["execution_time_ms"] = execution_time * 1000
            search_stats["total_results"] = total_count
            search_stats["returned_results"] = len(results)
            search_stats["has_more"] = (offset + len(results)) < total_count

            return results, total_count, search_stats

        except Exception as e:
            logger.warning("Search failed: %s", e)
            return [], 0, {"search_type": search_type, "error": str(e)}

    # =========================================================================
    # Trace JSONL Export (for debug logs)
    # =========================================================================
    # reindex_all, embedding_stats, and embedding helpers are in DatabaseEmbeddingMixin
    # (fichero.db_embeddings)

    def export_traces_jsonl(self, run_id: str, path: str | Path | None = None) -> Path:
        """Export all traces for a run to JSONL file.

        Per DATA_MODEL_PLAN: Full trace logs go to JSONL files for debug.

        Args:
            run_id: Run ID to export traces for
            path: Output path, or auto-generates in traces/ dir

        Returns:
            Path to the JSONL file
        """
        from fichero.models import Trace

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
        from fichero.models import Trace

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
        table = self._table_name(model)
        self._ensure_table(model)
        self.conn.execute(f"COPY {table} TO '{path}' (FORMAT PARQUET)")

    def import_parquet(self, model: Type[T], path: str | Path) -> int:
        """Import from Parquet file, returns count of imported rows."""
        table = self._table_name(model)
        self._ensure_table(model)

        # Count before
        before = self.count(model)

        # Import
        self.conn.execute(f"""
            INSERT INTO {table}
            SELECT * FROM read_parquet('{path}')
        """)

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
                # For non-Optional dict/list fields with a default_factory, use
                # the default instead of None to prevent Pydantic ValidationError
                # when a DB column is NULL (e.g. after schema migration).
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
            else:
                result[name] = value

        return result

    def _table_name(self, obj_or_model) -> str:
        """Get table name from model class (lowercase + 's')."""
        if isinstance(obj_or_model, type):
            return obj_or_model.__name__.lower() + "s"
        return type(obj_or_model).__name__.lower() + "s"

    def _ensure_table(self, model: Type[BaseModel]) -> None:
        """Create table if it doesn't exist."""
        table = self._table_name(model)

        if table in self._tables_created:
            return

        # Build column definitions from Pydantic model
        columns = []
        for name, field_info in model.model_fields.items():
            col_type = self._python_to_duckdb_type(field_info.annotation)
            columns.append(f"{name} {col_type}")

        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                {", ".join(columns)},
                PRIMARY KEY (id)
            )
        """)

        self._tables_created.add(table)

        # Apply knowledge-table indices once both knowledgeclaims AND
        # knowledgeentitys exist. Cheap (each CREATE INDEX IF NOT EXISTS
        # is a no-op when already present); critical for query latency
        # at 50K+ claims. (#991 — scaling-review bottleneck 2)
        if table in {"knowledgeclaims", "knowledgeentitys"}:
            from fichero.db_migrations import migrate_knowledge_indices
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
        """Close database connection."""
        self.conn.close()

    def _migrate_workflow_table(self) -> None:
        """Delegate to db_migrations.migrate_workflow_table."""
        from fichero.db_migrations import migrate_workflow_table
        migrate_workflow_table(self.conn)

    def _migrate_saved_search_table(self) -> None:
        """Delegate to db_migrations.migrate_saved_search_table."""
        from fichero.db_migrations import migrate_saved_search_table
        migrate_saved_search_table(self.conn)

    def _migrate_provider_refs_table(self) -> None:
        """Delegate to db_migrations.migrate_provider_refs_table."""
        from fichero.db_migrations import migrate_provider_refs_table
        migrate_provider_refs_table(self.conn)

    def _migrate_activity_tables(self) -> None:
        """Delegate to db_migrations.migrate_activity_tables."""
        from fichero.db_migrations import migrate_activity_tables
        migrate_activity_tables(self.conn)

    def _migrate_checkpoint_tables(self) -> None:
        """Delegate to db_migrations.migrate_checkpoint_tables."""
        from fichero.db_migrations import migrate_checkpoint_tables
        migrate_checkpoint_tables(self.conn)


# Backward-compatibility alias used by older tests/tooling that patch `fichero.db.db`.
db = db_manager
