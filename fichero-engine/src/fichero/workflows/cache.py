"""
Node Result Cache

Caches expensive node results (LLM calls) in DuckDB to avoid re-processing
unchanged files. Cache keys are based on:
- workflow_id: Isolates caches between workflows
- node_id: Which node in the workflow
- tool: The tool being used (describe, transcribe, etc.)
- config: Node configuration (prompt, model, etc.)
- file identity: path + mtime + size (fast, reliable)

Invalidation:
- Automatic: File changes, config changes, model changes all produce new keys
- Manual: Clear via API endpoint
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


# Tools that benefit from caching (expensive LLM operations)
CACHEABLE_TOOLS = {
    "describe",
    "transcribe",
    "summarize",
    "entities",
    "handwriting",
    "caption",
    "classify",
    "tags",
    "keywords",
    "sentiment",
    "questions",
    "extract",
    "analyze",
}


class NodeCache:
    """
    DuckDB-backed cache for node execution results.

    Usage:
        cache = NodeCache(db_path)

        # Check cache
        result = cache.get(cache_key)
        if result is not None:
            return result

        # Compute result
        result = expensive_operation()

        # Store in cache
        cache.set(cache_key, result, workflow_id, node_id, tool, file_path)
    """

    # Schema version for migrations
    SCHEMA_VERSION = 1

    def __init__(self, db_path: str | Path):
        """
        Initialize cache with DuckDB connection.

        Args:
            db_path: Path to the library's DuckDB file
        """
        self.db_path = Path(db_path)
        self.conn = duckdb.connect(str(self.db_path))
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create cache table if it doesn't exist."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS node_cache (
                cache_key TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                tool TEXT NOT NULL,
                file_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result_json TEXT NOT NULL
            )
        """)

        # Create indexes for efficient querying
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_workflow
            ON node_cache(workflow_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_workflow_node
            ON node_cache(workflow_id, node_id)
        """)

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """
        Retrieve cached result.

        Args:
            cache_key: The cache key to look up

        Returns:
            Cached result dict, or None if not found
        """
        try:
            result = self.conn.execute(
                "SELECT result_json FROM node_cache WHERE cache_key = ?", [cache_key]
            ).fetchone()

            if result:
                logger.debug(f"Cache hit: {cache_key[:16]}...")
                return json.loads(result[0])

            logger.debug(f"Cache miss: {cache_key[:16]}...")
            return None

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    def set(
        self,
        cache_key: str,
        result: dict[str, Any],
        workflow_id: str,
        node_id: str,
        tool: str,
        file_path: str | None = None,
    ) -> None:
        """
        Store result in cache.

        Args:
            cache_key: The cache key
            result: The result to cache (must be JSON-serializable)
            workflow_id: Workflow ID for grouping
            node_id: Node ID for grouping
            tool: Tool name
            file_path: Optional file path for debugging
        """
        try:
            result_json = json.dumps(result)

            self.conn.execute(
                """
                INSERT OR REPLACE INTO node_cache
                (cache_key, workflow_id, node_id, tool, file_path, created_at, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    cache_key,
                    workflow_id,
                    node_id,
                    tool,
                    file_path,
                    datetime.now(timezone.utc),
                    result_json,
                ],
            )

            logger.debug(f"Cache set: {cache_key[:16]}... for {tool}")

        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    def clear_workflow(self, workflow_id: str) -> int:
        """
        Clear all cached results for a workflow.

        Args:
            workflow_id: Workflow to clear cache for

        Returns:
            Number of entries deleted
        """
        result = self.conn.execute(
            "DELETE FROM node_cache WHERE workflow_id = ? RETURNING cache_key",
            [workflow_id],
        ).fetchall()

        count = len(result)
        logger.info(f"Cleared {count} cache entries for workflow {workflow_id}")
        return count

    def clear_node(self, workflow_id: str, node_id: str) -> int:
        """
        Clear cached results for a specific node.

        Args:
            workflow_id: Workflow ID
            node_id: Node to clear cache for

        Returns:
            Number of entries deleted
        """
        result = self.conn.execute(
            "DELETE FROM node_cache WHERE workflow_id = ? AND node_id = ? RETURNING cache_key",
            [workflow_id, node_id],
        ).fetchall()

        count = len(result)
        logger.info(f"Cleared {count} cache entries for node {node_id}")
        return count

    def clear_all(self) -> int:
        """
        Clear entire cache.

        Returns:
            Number of entries deleted
        """
        result = self.conn.execute(
            "DELETE FROM node_cache RETURNING cache_key"
        ).fetchall()

        count = len(result)
        logger.info(f"Cleared entire cache: {count} entries")
        return count

    def get_stats(self, workflow_id: str | None = None) -> dict[str, Any]:
        """
        Get cache statistics.

        Args:
            workflow_id: Optional workflow to filter by

        Returns:
            Dict with cache statistics
        """
        if workflow_id:
            result = self.conn.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    COUNT(DISTINCT node_id) as nodes_cached,
                    COUNT(DISTINCT tool) as tools_cached,
                    MIN(created_at) as oldest_entry,
                    MAX(created_at) as newest_entry
                FROM node_cache
                WHERE workflow_id = ?
            """,
                [workflow_id],
            ).fetchone()
        else:
            result = self.conn.execute("""
                SELECT
                    COUNT(*) as total_entries,
                    COUNT(DISTINCT workflow_id) as workflows_cached,
                    COUNT(DISTINCT tool) as tools_cached,
                    MIN(created_at) as oldest_entry,
                    MAX(created_at) as newest_entry
                FROM node_cache
            """).fetchone()

        return {
            "total_entries": result[0],
            "workflows_cached" if not workflow_id else "nodes_cached": result[1],
            "tools_cached": result[2],
            "oldest_entry": result[3].isoformat() if result[3] else None,
            "newest_entry": result[4].isoformat() if result[4] else None,
        }

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()


def compute_cache_key(
    workflow_id: str,
    node_id: str,
    tool: str,
    config: dict[str, Any],
    provider: str,
    model: str,
    file_path: str,
    document_id: str | None = None,
) -> str:
    """
    Compute cache key for a node execution.

    The key incorporates all factors that could affect the output:
    - Workflow and node identity
    - Tool being used
    - Configuration (prompt, parameters)
    - LLM provider and model
    - File identity (path + mtime + size)
    - Document identity (when distinct from file_path — required for
      per-page PDF fan-out so the six page children of one PDF don't
      collide on the parent's path. Without this the cache returned the
      page-1 result for pages 2-6, which produced Davidson ×6 #896.)

    Args:
        workflow_id: Workflow ID
        node_id: Node ID within workflow
        tool: Tool name (describe, transcribe, etc.)
        config: Node configuration dict
        provider: LLM provider name
        model: LLM model name
        file_path: Path to the input file
        document_id: Optional unique Document.id — pass for per-page
            fan-out so page children of one PDF don't share a key.

    Returns:
        32-character hex cache key
    """
    # Get file identity (path + mtime + size)
    file_identity = _get_file_identity(file_path)

    # Serialize config deterministically
    config_str = json.dumps(config, sort_keys=True, default=str)

    # Combine all parts
    key_parts = "|".join(
        [
            workflow_id,
            node_id,
            tool,
            config_str,
            provider or "",
            model or "",
            file_identity,
            document_id or "",
        ]
    )

    # Hash to fixed-length key
    return hashlib.sha256(key_parts.encode()).hexdigest()[:32]


def _get_file_identity(file_path: str) -> str:
    """
    Get file identity string for cache key.

    Uses path + mtime + size for fast, reliable identity.

    Args:
        file_path: Path to file

    Returns:
        Identity string like "path:mtime:size"
    """
    try:
        stat = os.stat(file_path)
        return f"{file_path}:{stat.st_mtime}:{stat.st_size}"
    except OSError:
        # File doesn't exist or can't be accessed
        return f"{file_path}:unknown"


# Global cache instance (initialized per-library)
_cache_instances: dict[str, NodeCache] = {}


def get_node_cache(db_path: str | Path) -> NodeCache:
    """
    Get or create NodeCache instance for a library.

    Args:
        db_path: Path to library's DuckDB file

    Returns:
        NodeCache instance
    """
    db_path_str = str(db_path)

    if db_path_str not in _cache_instances:
        _cache_instances[db_path_str] = NodeCache(db_path)

    return _cache_instances[db_path_str]
