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
import duckdb
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Minimum content length to create embedding
MIN_CONTENT_LENGTH = 10

# Default embedding model (FastEmbed - no scikit-learn dependency)
# Using multilingual model for Spanish + English support
DEFAULT_MODEL = "intfloat/multilingual-e5-large"

# Valid identifier pattern for SQL column/table names
_VALID_IDENTIFIER = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


@dataclass
class SearchResult:
    """Search result with score and document reference."""
    document_id: str
    score: float
    content_preview: str
    metadata: dict[str, Any]

    def __repr__(self) -> str:
        preview = self.content_preview[:50] + "..." if len(self.content_preview) > 50 else self.content_preview
        return f"SearchResult(id={self.document_id}, score={self.score:.3f}, preview='{preview}')"


class Database:
    """Simple Pythonic wrapper for DuckDB + LanceDB."""

    def __init__(self, path: str | Path | None = None):
        """
        Initialize database connection.

        Args:
            path: Path to database file. Defaults to ~/Library/Application Support/ca.tubb.fichero/library.duckdb
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
        
        # Migrate workflows table if needed
        self._migrate_workflow_table()

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
        computed_keys = set(model_cls.model_computed_fields.keys()) if hasattr(model_cls, 'model_computed_fields') else set()
        data = obj.model_dump(exclude=computed_keys)

        # Convert dict/list/tuple/Path fields for DuckDB
        for key, value in data.items():
            if isinstance(value, (dict, list, tuple)):
                data[key] = json.dumps(value)
            elif isinstance(value, Path):
                data[key] = str(value)

        # Build upsert query
        cols = list(data.keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(f"${c}" for c in cols)

        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
            data
        )

        # Auto-embed if requested and has content
        if auto_embed and hasattr(obj, 'page_content') and obj.page_content:
            self.embed(obj)

    def get(self, model: Type[T], id: str) -> T | None:
        """Get a single object by ID."""
        table = self._table_name(model)
        self._ensure_table(model)

        result = self.conn.execute(
            f"SELECT * FROM {table} WHERE id = $id",
            {"id": id}
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
        query_filters = {}
        for k, v in filters.items():
            if hasattr(v, 'value'):  # It's an enum
                query_filters[k] = v.value
            else:
                query_filters[k] = v

        where = " AND ".join(f"{k} = ${k}" for k in query_filters.keys())
        rows = self.conn.execute(
            f"SELECT * FROM {table} WHERE {where}",
            query_filters
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

        self.conn.execute(
            f"DELETE FROM {table} WHERE id = $id",
            {"id": obj.id}
        )

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
                f"SELECT COUNT(*) FROM {table} WHERE {where}",
                filters
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

    def save_vectors(self, table_name: str, data: list[dict]) -> None:
        """Save data to LanceDB table (creates or appends)."""
        if table_name in self.lance.table_names():
            table = self.lance.open_table(table_name)
            table.add(data)
        else:
            self.lance.create_table(table_name, data)

    def search_vectors(
        self,
        table_name: str,
        query_vector: list[float],
        limit: int = 10
    ) -> list[dict]:
        """Search LanceDB table by vector similarity."""
        if table_name not in self.lance.table_names():
            return []

        table = self.lance.open_table(table_name)
        results = table.search(query_vector).limit(limit).to_list()
        return results

    # =========================================================================
    # Embedding Convenience Methods
    # =========================================================================

    def save_embedding(
        self,
        doc: BaseModel,
        vector: list[float],
        text: str | None = None
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
            "doc_type": getattr(doc, "doc_type", None).value if hasattr(doc, "doc_type") and doc.doc_type else None,
            "file_type": getattr(doc, "file_type", None).value if hasattr(doc, "file_type") and doc.file_type else None,
        }

        self.save_vectors("embeddings", [record])

    def search_similar(
        self,
        query_vector: list[float],
        limit: int = 10,
        model: Type[T] | None = None
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
            if "embeddings" not in self.lance.table_names():
                return False

            # Validate doc_id to prevent injection
            if not doc_id or not _VALID_IDENTIFIER.match(doc_id.replace('-', '')):
                # UUIDs contain hex chars and hyphens - just sanitize quotes
                safe_id = doc_id.replace("'", "''")
            else:
                safe_id = doc_id

            table = self.lance.open_table("embeddings")
            table.delete(f"id = '{safe_id}'")
            return True
        except Exception:
            return False

    def has_embedding(self, doc_id: str) -> bool:
        """Check if document has an embedding.

        Args:
            doc_id: Document ID

        Returns:
            True if embedding exists
        """
        try:
            if "embeddings" not in self.lance.table_names():
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
    ) -> list[SearchResult]:
        """Semantic search for documents.

        Args:
            query: Search query text
            limit: Maximum results to return
            min_score: Minimum similarity score (0-1)

        Returns:
            List of SearchResult objects ordered by relevance
        """
        if not query or not query.strip():
            return []

        try:
            if "embeddings" not in self.lance.table_names():
                logger.debug("No embeddings table exists")
                return []

            # Embed query
            query_vector = self._embed_text(query)

            # Search vectors
            table = self.lance.open_table("embeddings")
            raw_results = table.search(query_vector).limit(limit).to_list()

            # Convert to SearchResult, filter by score
            results = []
            for r in raw_results:
                # LanceDB returns _distance (lower is better)
                # Convert to score (higher is better, 0-1 range)
                distance = r.get("_distance", 1.0)
                score = 1.0 / (1.0 + distance)

                if score < min_score:
                    continue

                results.append(SearchResult(
                    document_id=r.get("document_id") or r.get("id"),
                    score=score,
                    content_preview=r.get("text", ""),
                    metadata={
                        "name": r.get("name"),
                        "doc_type": r.get("doc_type"),
                        "file_type": r.get("file_type"),
                    }
                ))

            return results

        except Exception as e:
            logger.warning("Search failed: %s", e)
            return []

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
            if "embeddings" not in self.lance.table_names():
                return {"indexed_count": 0, "table_exists": False}

            table = self.lance.open_table("embeddings")
            count = table.count_rows()
            return {"indexed_count": count, "table_exists": True}
        except Exception:
            return {"indexed_count": 0, "table_exists": False}

    def _ensure_embedder(self) -> None:
        """Lazy-load the embedding model.

        Uses FastEmbed (ONNX-based, no scikit-learn dependency).
        """
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding
                self._embedder = TextEmbedding(model_name=DEFAULT_MODEL)
                logger.debug("Loaded embedding model: %s", DEFAULT_MODEL)
            except ImportError:
                raise ImportError(
                    "fastembed not installed. "
                    "Install with: pip install fastembed"
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

        with open(path, 'w') as f:
            for trace in traces:
                f.write(trace.model_dump_json() + '\n')

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
            if (annotation is dict or inner_origin is dict or
                annotation is list or inner_origin is list):
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
                        result[name] = tuple(parsed) if isinstance(parsed, list) else value
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
                {', '.join(columns)},
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
    
    def _migrate_workflow_table(self) -> None:
        """Migrate workflows table to new schema if needed."""
        try:
            # First check if table exists
            table_exists = self.conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'workflows'
            """).fetchone()[0] > 0
            
            if not table_exists:
                # Table doesn't exist, no migration needed
                logger.debug("Workflows table does not exist, skipping migration")
                return
            
            # Check current schema
            result = self.conn.execute("PRAGMA table_info('workflows')").fetchall()
            columns = [row[1] for row in result]
            
            # If old schema (has 'steps' but not 'format'), migrate
            if 'steps' in columns and 'format' not in columns:
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
            # Table might not exist or other issue
            logger.warning(f"Migration check failed: {e}")

    def _migrate_saved_search_table(self) -> None:
        """Migrate saved_searches table to add missing columns."""
        try:
            # Check if table exists using DuckDB's information_schema
            table_exists = self.conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'saved_searches'
            """).fetchone()[0] > 0
            
            if not table_exists:
                # Table doesn't exist, nothing to migrate
                logger.debug("Saved searches table does not exist, skipping migration")
                return
            
            # Check current schema
            result = self.conn.execute("PRAGMA table_info('saved_searches')").fetchall()
            columns = {row[1]: row for row in result}
            
            # Add folder_path if missing
            if 'folder_path' not in columns:
                logger.info("Migrating saved_searches table: adding folder_path column...")
                self.conn.execute("""
                    ALTER TABLE saved_searches 
                    ADD COLUMN folder_path VARCHAR DEFAULT '/'
                """)
            
            # Add sort_order if missing
            if 'sort_order' not in columns:
                logger.info("Migrating saved_searches table: adding sort_order column...")
                self.conn.execute("""
                    ALTER TABLE saved_searches 
                    ADD COLUMN sort_order INTEGER DEFAULT 0
                """)
            
            logger.info("Saved searches table migration completed")
            
        except Exception as e:
            # Table might not exist or other issue
            logger.warning(f"Saved searches migration check failed: {e}")


# Global instance - can be overridden for testing
db = Database()
db._migrate_workflow_table()
db._migrate_saved_search_table()
