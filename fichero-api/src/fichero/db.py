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
from typing import TypeVar, Type, get_origin, get_args, Union, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import json
import logging
import re
import time
import duckdb
from pydantic import BaseModel
from fichero.errors import ErrorCategory, handle_error, retry_on_failure

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Minimum content length to create embedding
MIN_CONTENT_LENGTH = 10

# Default embedding model (FastEmbed - no scikit-learn dependency)
# Using multilingual model for Spanish + English support
DEFAULT_MODEL = "intfloat/multilingual-e5-large"

# Valid identifier pattern for SQL column/table names
_VALID_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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


class Database:
    """Simple Pythonic wrapper for DuckDB + LanceDB."""

    def __init__(self, path: str | Path | None = None):
        """
        Initialize database connection.

        Args:
            path: Path to database file. Defaults to ~/Library/Application Support/com.tubb.fichero/library.duckdb
        """
        if path is None:
            from fichero.storage import settings

            path = settings.db_path
        else:
            path = Path(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = duckdb.connect(str(path))
        self._lance_path = path.parent / "vectors"
        self._lance_db = None  # Lazy init
        self._embedder = None  # Lazy init
        self._tables_created: set[str] = set()

        # Migrate tables if needed
        self._migrate_workflow_table()
        self._migrate_saved_search_table()
        self._migrate_provider_refs_table()

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
        # Get text to embed
        text = ""
        if hasattr(doc, "page_content") and doc.page_content:
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
                        # LanceDB returns _distance (lower is better)
                        # Convert to score (higher is better, 0-1 range)
                        distance = r.get("_distance", 1.0)
                        score = 1.0 / (1.0 + distance)

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

                        # Filter by query text (simple full-text search)
                        if use_fuzzy_match:
                            # Simple fuzzy matching - could be enhanced with proper fuzzy search library
                            mask = all_docs["text"].str.contains(
                                query, case=False, regex=False
                            )
                        else:
                            mask = all_docs["text"].str.contains(
                                query, case=False, regex=False
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

            # Combine results for hybrid search
            combined_results = []
            if search_type == "hybrid":
                # Combine semantic and full-text results
                combined_results = semantic_results + fulltext_results
                # Remove duplicates
                seen_ids = set()
                unique_results = []
                for result in combined_results:
                    if result["document_id"] not in seen_ids:
                        seen_ids.add(result["document_id"])
                        unique_results.append(result)
                combined_results = unique_results
            elif search_type == "semantic":
                combined_results = semantic_results
            elif search_type == "fulltext":
                combined_results = fulltext_results

            # Apply filters
            if filters:
                filtered_results = []
                for result in combined_results:
                    metadata = result["metadata"]
                    match = True

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

    def reindex_all(self, on_progress: Callable[[int, int], None] | None = None) -> int:
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

        for i, doc in enumerate(docs):
            if self.embed(doc):
                indexed += 1

            if on_progress:
                on_progress(indexed, total)

        logger.info("Reindexed %s/%s documents", indexed, total)
        return indexed

    def embedding_stats(self) -> dict:
        """Get statistics about embeddings.

        Returns:
            Dict with indexed_count, table_exists
        """
        try:
            if "embeddings" not in self._lance_tables():
                return {"indexed_count": 0, "table_exists": False}

            table = self.lance.open_table("embeddings")
            count = table.count_rows()
            return {"indexed_count": count, "table_exists": True}
        except Exception:
            return {"indexed_count": 0, "table_exists": False}

    def _get_embedding_model_name(self) -> str:
        """Get configured embedding model, defaulting to multilingual-e5-large."""
        try:
            from fichero.app_db import get_app_db

            model = get_app_db().get_setting("default_embeddings_model")
            if model:
                return model
        except Exception:
            pass
        return DEFAULT_MODEL

    def _ensure_embedder(self) -> None:
        """Lazy-load the embedding model.

        Uses FastEmbed (ONNX-based, no scikit-learn dependency).
        Reads configured model from app settings, falls back to DEFAULT_MODEL.
        """
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding
                from fichero.local_models import MODELS_BASE

                model_name = self._get_embedding_model_name()
                cache_dir = MODELS_BASE / "embeddings"
                cache_dir.mkdir(parents=True, exist_ok=True)
                self._embedder = TextEmbedding(
                    model_name=model_name,
                    cache_dir=str(cache_dir),
                )
                logger.info(
                    "Loaded embedding model: %s (cache_dir=%s)",
                    model_name,
                    cache_dir,
                )
            except ImportError:
                raise ImportError(
                    "fastembed not installed. Install with: pip install fastembed"
                )

    def _embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Uses FastEmbed for local ONNX-based embedding.
        Lazy-loads the model on first use.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector)
        """
        self._ensure_embedder()
        # FastEmbed returns a generator, get first result
        embeddings = list(self._embedder.embed([text]))
        return embeddings[0].tolist()

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
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
        embeddings = list(self._embedder.embed(texts))
        return [e.tolist() for e in embeddings]

    # =========================================================================
    # Trace JSONL Export (for debug logs)
    # =========================================================================

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

    @retry_on_failure(max_attempts=2, delay_seconds=0.5)
    def _migrate_workflow_table(self) -> None:
        """Migrate workflows table to new schema if needed."""
        try:
            # First check if table exists
            table_exists = (
                self.conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'workflows'
            """).fetchone()[0]
                > 0
            )

            if not table_exists:
                # Table doesn't exist, no migration needed
                logger.debug("Workflows table does not exist, skipping migration")
                return

            # Check current schema
            result = self.conn.execute("PRAGMA table_info('workflows')").fetchall()
            columns = [row[1] for row in result]

            # If old schema (has 'steps' but not 'format'), migrate
            if "steps" in columns and "format" not in columns:
                logger.info("Migrating workflows table to new schema...")

                # Add new columns
                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN format VARCHAR DEFAULT 'steps'
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN nodes JSON DEFAULT []
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN edges JSON DEFAULT []
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN folder_path VARCHAR DEFAULT '/'
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN sort_order INTEGER DEFAULT 0
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN is_template BOOLEAN DEFAULT FALSE
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN tags JSON DEFAULT []
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN provider VARCHAR DEFAULT ''
                """)

                self.conn.execute("""
                    ALTER TABLE workflows 
                    ADD COLUMN model VARCHAR DEFAULT ''
                """)

                # Migrate existing data: convert steps to placeholder nodes/edges
                self.conn.execute("""
                    UPDATE workflows 
                    SET format = 'steps'
                    WHERE format IS NULL OR format = ''
                """)

                logger.info("Workflows table migration completed")

        except Exception as e:
            error = handle_error(
                e,
                default_message="Workflow table migration failed",
                category=ErrorCategory.DATABASE,
                context={"operation": "workflow_table_migration"},
            )
            logger.warning("Migration failed: %s", error.message)
            raise  # Re-raise to trigger retry

    def _migrate_saved_search_table(self) -> None:
        """Migrate saved_searches table to add missing columns."""
        try:
            # Check if table exists using DuckDB's information_schema
            table_exists = (
                self.conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'saved_searches'
            """).fetchone()[0]
                > 0
            )

            if not table_exists:
                # Table doesn't exist, nothing to migrate
                logger.debug("Saved searches table does not exist, skipping migration")
                return

            # Check current schema
            result = self.conn.execute("PRAGMA table_info('saved_searches')").fetchall()
            columns = {row[1]: row for row in result}

            # Add folder_path if missing
            if "folder_path" not in columns:
                logger.info(
                    "Migrating saved_searches table: adding folder_path column..."
                )
                self.conn.execute("""
                    ALTER TABLE saved_searches
                    ADD COLUMN folder_path VARCHAR DEFAULT '/'
                """)

            # Add sort_order if missing
            if "sort_order" not in columns:
                logger.info(
                    "Migrating saved_searches table: adding sort_order column..."
                )
                self.conn.execute("""
                    ALTER TABLE saved_searches
                    ADD COLUMN sort_order INTEGER DEFAULT 0
                """)

            # Add sort_direction if missing
            if "sort_direction" not in columns:
                logger.info(
                    "Migrating saved_searches table: adding sort_direction column..."
                )
                self.conn.execute("""
                    ALTER TABLE saved_searches
                    ADD COLUMN sort_direction VARCHAR DEFAULT 'desc'
                """)

            logger.info("Saved searches table migration completed")

        except Exception as e:
            # Table might not exist or other issue
            logger.warning(f"Saved searches migration check failed: {e}")

    def _migrate_provider_refs_table(self) -> None:
        """Create provider_refs table if it doesn't exist.

        This table tracks which app-wide providers a library references.
        Actual provider config is stored in app.duckdb.
        """
        try:
            # Check if table exists
            table_exists = (
                self.conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'provider_refs'
            """).fetchone()[0]
                > 0
            )

            if table_exists:
                logger.debug("provider_refs table already exists")
                return

            # Create the table
            logger.info("Creating provider_refs table...")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_refs (
                    id VARCHAR PRIMARY KEY,
                    provider_id VARCHAR NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index on provider_id for fast lookups
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_provider_refs_provider
                ON provider_refs(provider_id)
            """)

            logger.info("provider_refs table created successfully")

        except Exception as e:
            logger.warning(f"provider_refs table creation failed: {e}")

    def _migrate_activity_tables(self):
        """Ensure activity tracking tables exist.

        Creates the activities table for storing workflow execution events.
        This enables the Activity sidebar to show historical data.
        """
        try:
            # Activities table - stores workflow, node, and batch events
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    level TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    message TEXT NOT NULL,
                    workflow_id TEXT,
                    batch_id TEXT,
                    thread_id TEXT,
                    node_id TEXT,
                    metadata JSON,
                    duration_ms FLOAT,
                    error TEXT
                )
            """)

            # Indexes for efficient queries
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_timestamp
                ON activities(timestamp DESC)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_type
                ON activities(type)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_workflow_id
                ON activities(workflow_id)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_batch_id
                ON activities(batch_id)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_thread_id
                ON activities(thread_id)
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_activities_level
                ON activities(level)
            """)

            logger.info("Activity tables migration completed")

        except Exception as e:
            logger.warning(f"Activity tables migration failed: {e}")

    def _migrate_checkpoint_tables(self):
        """Ensure LangGraph checkpoint tables exist.

        Creates the checkpoints and checkpoint_writes tables for workflow
        state persistence. This enables viewing Graph history in Activity sidebar.
        """
        try:
            # Checkpoints table - stores workflow execution state
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    type TEXT,
                    checkpoint BLOB,
                    metadata BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
            """)

            # Writes table - stores pending checkpoint writes
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    type TEXT,
                    value BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                )
            """)

            logger.info("Checkpoint tables migration completed")

        except Exception as e:
            logger.warning(f"Checkpoint tables migration failed: {e}")


# Multi-library database manager for package documents
class DatabaseManager:
    """Manages multiple Database instances for package documents.

    Each .fichero package contains its own database files:
    - MyLibrary.fichero/fichero.duckdb
    - MyLibrary.fichero/lance/

    The manager maintains a pool of open Database connections.
    """

    def __init__(self):
        self._databases: dict[str, Database] = {}
        self._lock = __import__("threading").Lock()
        logger.info("DatabaseManager initialized")

    def get_database(self, package_path: str | Path) -> Database:
        """Get or create Database instance for a package.

        Args:
            package_path: Path to the .fichero package directory
                         (e.g., /Users/name/Documents/MyLibrary.fichero)

        Returns:
            Database instance for this package
        """
        package_path = Path(package_path)
        package_str = str(package_path)

        with self._lock:
            if package_str not in self._databases:
                # Create new database connection for this package
                db_path = package_path / "fichero.duckdb"

                logger.info(f"Creating database connection for package: {package_str}")

                # Create the database instance
                db = Database(path=db_path)

                # Run migrations
                db._migrate_workflow_table()
                db._migrate_saved_search_table()
                db._migrate_provider_refs_table()
                db._migrate_activity_tables()
                db._migrate_checkpoint_tables()

                self._databases[package_str] = db
                logger.info(f"Database connection created: {db_path}")

            return self._databases[package_str]

    def close_database(self, package_path: str | Path):
        """Close database connection for a package."""
        package_str = str(Path(package_path))

        with self._lock:
            if package_str in self._databases:
                db = self._databases[package_str]
                db.conn.close()
                del self._databases[package_str]
                logger.info(f"Closed database connection: {package_str}")

    @property
    def active_count(self) -> int:
        """Return the number of currently open database connections."""
        return len(self._databases)

    def close_all(self):
        """Close all database connections."""
        with self._lock:
            for package_path, db in list(self._databases.items()):
                db.conn.close()
                logger.info(f"Closed database: {package_path}")
            self._databases.clear()
            logger.info("All database connections closed")


# Global database manager for package documents
db_manager = DatabaseManager()

# Backward-compatibility alias used by older tests/tooling that patch `fichero.db.db`.
db = db_manager
