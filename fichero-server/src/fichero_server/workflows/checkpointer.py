"""
DuckDB Checkpointer for LangGraph

Custom implementation of LangGraph's BaseCheckpointSaver using DuckDB.
This keeps all workflow data (definitions + execution state) in one database.

Schema adapted from LangGraph's SQLite checkpointer:
https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/

Tables:
- checkpoints: Workflow execution state snapshots
- writes: Pending checkpoint writes
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, AsyncIterator

import duckdb
from fichero_server.core.duckdb_session import connect_utc
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
)

from fichero_server.workflows.types import compact_output_for_state

logger = logging.getLogger(__name__)


def _compact_checkpoint(checkpoint: Checkpoint) -> Checkpoint:
    """Trim redundant State.outputs payloads before persisting checkpoints."""
    compact = dict(checkpoint)
    channel_values = compact.get("channel_values")
    if not isinstance(channel_values, dict):
        return compact

    outputs = channel_values.get("outputs")
    if not isinstance(outputs, dict):
        return compact

    compact_channel_values = dict(channel_values)
    compact_channel_values["outputs"] = {
        node_id: compact_output_for_state(node_output)
        for node_id, node_output in outputs.items()
    }
    compact["channel_values"] = compact_channel_values
    return compact


class JsonCheckpointSerializer(SerializerProtocol):
    """Adapter for LangGraph's safe JSON/msgpack serializer."""

    def __init__(self) -> None:
        self._serde = JsonPlusSerializer()

    def dumps(self, obj: Any) -> bytes:
        serde_type, payload = self._serde.dumps_typed(obj)
        return serde_type.encode("ascii") + b"\n" + payload

    def loads(self, data: bytes) -> Any:
        serde_type, sep, payload = data.partition(b"\n")
        if not sep:
            raise ValueError("Invalid JSON checkpoint payload")
        return self._serde.loads_typed((serde_type.decode("ascii"), payload))


class AsyncDuckDBCheckpointer(BaseCheckpointSaver):
    """
    Async DuckDB implementation of LangGraph checkpointer.

    Stores workflow execution state in DuckDB database, allowing workflows
    to pause/resume using LangGraph's durable execution.

    Usage:
        checkpointer = AsyncDuckDBCheckpointer.from_db_path("~/Library/Application Support/Fichero/fichero.duckdb")

        # Compile graph with checkpointer
        graph = workflow_builder.compile(checkpointer=checkpointer)

        # Execute with thread ID
        result = await graph.ainvoke(
            {"input": "data"},
            config={"configurable": {"thread_id": "workflow-123"}}
        )

        # Resume from last checkpoint
        result = await graph.ainvoke(
            None,  # None = resume
            config={"configurable": {"thread_id": "workflow-123"}}
        )
    """

    def __init__(
        self,
        conn: duckdb.DuckDBPyConnection,
        serde: SerializerProtocol | None = None,
    ):
        """
        Initialize checkpointer with DuckDB connection.

        Args:
            conn: DuckDB connection
            serde: Serializer for checkpoint data (defaults to JsonPlusSerializer)
        """
        super().__init__(serde=serde or JsonCheckpointSerializer())
        # ponytail: already locked / not a managed shared conn (#2508). This is
        # the checkpointer's OWN raw duckdb connection (opened by from_db_path),
        # not the package's managed Database. Every access below is already
        # serialized on this object's own RLock (self._lock), so it is internally
        # thread-safe; Database._lock and the locked execute() helpers do not
        # apply because this connection is not the managed shared one.
        self.conn = conn
        self._lock = threading.RLock()
        self._setup()
        logger.info("Initialized DuckDB checkpointer")

    @classmethod
    def from_db_path(cls, db_path: str | Path) -> "AsyncDuckDBCheckpointer":
        """
        Create checkpointer from database path.

        Args:
            db_path: Path to DuckDB file

        Returns:
            AsyncDuckDBCheckpointer instance
        """
        db_path = Path(db_path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = connect_utc(str(db_path))
        return cls(conn)

    def _setup(self) -> None:
        """Create checkpoint tables if they don't exist."""
        with self._lock:
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

        logger.debug("Checkpoint tables created/verified")

    async def _execute_locked(
        self,
        query: str,
        params: list[Any] | None = None,
    ) -> None:
        """Run a statement against the shared DuckDB connection under lock."""

        def _run() -> None:
            with self._lock:
                if params is None:
                    self.conn.execute(query)
                else:
                    self.conn.execute(query, params)

        await asyncio.to_thread(_run)

    async def _fetchone_locked(
        self,
        query: str,
        params: list[Any] | None = None,
    ) -> Any:
        """Execute and consume one row atomically on the shared connection."""

        def _run() -> Any:
            with self._lock:
                if params is None:
                    cur = self.conn.execute(query)
                else:
                    cur = self.conn.execute(query, params)
                return cur.fetchone()

        return await asyncio.to_thread(_run)

    async def _fetchall_locked(
        self,
        query: str,
        params: list[Any] | None = None,
    ) -> list[Any]:
        """Execute and consume all rows atomically on the shared connection."""

        def _run() -> list[Any]:
            with self._lock:
                if params is None:
                    cur = self.conn.execute(query)
                else:
                    cur = self.conn.execute(query, params)
                return cur.fetchall()

        return await asyncio.to_thread(_run)

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Save a checkpoint asynchronously.

        Args:
            config: Configuration containing thread_id and checkpoint_ns
            checkpoint: Checkpoint data to save
            metadata: Checkpoint metadata
            new_versions: New channel versions

        Returns:
            Updated configuration
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]

        # Serialize checkpoint and metadata
        checkpoint_blob = self.serde.dumps(_compact_checkpoint(checkpoint))
        metadata_blob = self.serde.dumps(metadata)

        # Insert checkpoint (run in thread pool since DuckDB doesn't have native async)
        # Use ON CONFLICT for DuckDB (not INSERT OR REPLACE which is SQLite syntax)
        await self._execute_locked(
            """
            INSERT INTO checkpoints
            (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO UPDATE SET
                parent_checkpoint_id = excluded.parent_checkpoint_id,
                type = excluded.type,
                checkpoint = excluded.checkpoint,
                metadata = excluded.metadata
            """,
            [
                thread_id,
                checkpoint_ns,
                checkpoint_id,
                checkpoint.get("parent_checkpoint_id"),
                checkpoint.get("type"),
                checkpoint_blob,
                metadata_blob,
            ],
        )

        logger.debug(
            f"Saved checkpoint: thread_id={thread_id}, "
            f"checkpoint_id={checkpoint_id}, ns={checkpoint_ns}"
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aget_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """
        Get the latest checkpoint for a thread asynchronously.

        Args:
            config: Configuration containing thread_id and optional checkpoint_ns

        Returns:
            CheckpointTuple or None if not found
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        # Query for checkpoint
        if checkpoint_id:
            # Get specific checkpoint
            query = """
                SELECT checkpoint, metadata, parent_checkpoint_id, checkpoint_id
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
            """
            params = [thread_id, checkpoint_ns, checkpoint_id]
        else:
            # Get latest checkpoint
            query = """
                SELECT checkpoint, metadata, parent_checkpoint_id, checkpoint_id
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
            """
            params = [thread_id, checkpoint_ns]

        row = await self._fetchone_locked(query, params)

        if not row:
            logger.debug(
                f"No checkpoint found: thread_id={thread_id}, ns={checkpoint_ns}"
            )
            return None

        checkpoint_blob, metadata_blob, parent_id, checkpoint_id = row

        # Deserialize
        checkpoint = self.serde.loads(bytes(checkpoint_blob))
        metadata = self.serde.loads(bytes(metadata_blob))

        # Get pending writes
        writes_rows = await self._fetchall_locked(
            """
            SELECT task_id, channel, value
            FROM checkpoint_writes
            WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
            ORDER BY idx
            """,
            [thread_id, checkpoint_ns, checkpoint_id],
        )

        pending_writes = [
            (task_id, channel, self.serde.loads(bytes(value)))
            for task_id, channel, value in writes_rows
        ]

        logger.debug(
            f"Retrieved checkpoint: thread_id={thread_id}, "
            f"checkpoint_id={checkpoint_id}, writes={len(pending_writes)}"
        )

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_id,
                }
            }
            if parent_id
            else None,
            pending_writes=pending_writes,
        )

    async def alist(
        self,
        config: dict[str, Any],
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """
        List checkpoints for a thread asynchronously.

        Args:
            config: Configuration containing thread_id
            filter: Optional filter criteria
            before: Optional checkpoint to start before
            limit: Maximum number of checkpoints to return

        Yields:
            CheckpointTuple instances
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        query = """
            SELECT checkpoint, metadata, parent_checkpoint_id, checkpoint_id
            FROM checkpoints
            WHERE thread_id = ? AND checkpoint_ns = ?
            ORDER BY checkpoint_id DESC
        """
        params: list[Any] = [thread_id, checkpoint_ns]

        # Use parameterized query to prevent SQL injection
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        rows = await self._fetchall_locked(query, params)

        for row in rows:
            checkpoint_blob, metadata_blob, parent_id, checkpoint_id = row

            checkpoint = self.serde.loads(bytes(checkpoint_blob))
            metadata = self.serde.loads(bytes(metadata_blob))

            # Get pending writes for this checkpoint
            writes_rows = await self._fetchall_locked(
                """
                SELECT task_id, channel, value
                FROM checkpoint_writes
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                ORDER BY idx
                """,
                [thread_id, checkpoint_ns, checkpoint_id],
            )

            pending_writes = [
                (task_id, channel, self.serde.loads(bytes(value)))
                for task_id, channel, value in writes_rows
            ]

            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": parent_id,
                    }
                }
                if parent_id
                else None,
                pending_writes=pending_writes,
            )

    async def aput_writes(
        self,
        config: dict[str, Any],
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """
        Save pending writes for a checkpoint.

        Args:
            config: Configuration containing thread_id, checkpoint_ns, checkpoint_id
            writes: List of (channel, value) tuples
            task_id: ID of the task making the writes
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        # Insert each write
        # Use ON CONFLICT for DuckDB (not INSERT OR REPLACE which is SQLite syntax)
        for idx, (channel, value) in enumerate(writes):
            value_blob = self.serde.dumps(value)

            await self._execute_locked(
                """
                INSERT INTO checkpoint_writes
                (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO UPDATE SET
                    channel = excluded.channel,
                    value = excluded.value
                """,
                [
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    idx,
                    channel,
                    value_blob,
                ],
            )

        logger.debug(
            f"Saved {len(writes)} writes: thread_id={thread_id}, "
            f"checkpoint_id={checkpoint_id}, task_id={task_id}"
        )

    async def adelete_thread(self, thread_id: str) -> int:
        """
        Delete all checkpointer state for a thread.

        Removes rows from every table this checkpointer owns:
          - checkpoints (declared in _setup)
          - checkpoint_writes (declared in _setup)

        Wrapped in a single transaction so a partial delete cannot orphan
        rows across the linked tables. If a future LangGraph schema change
        adds another linked table, add it here.

        Args:
            thread_id: Thread ID whose state should be removed.

        Returns:
            Total rows deleted across all checkpointer-owned tables.
        """

        def _delete() -> int:
            total = 0
            with self._lock:
                self.conn.execute("BEGIN TRANSACTION")
                try:
                    for table in ("checkpoints", "checkpoint_writes"):
                        result = self.conn.execute(
                            f"DELETE FROM {table} WHERE thread_id = ? RETURNING 1",
                            [thread_id],
                        )
                        rows = result.fetchall()
                        total += len(rows)
                    self.conn.execute("COMMIT")
                except Exception:
                    self.conn.execute("ROLLBACK")
                    raise
            return total

        deleted = await asyncio.to_thread(_delete)
        logger.info(
            f"Deleted checkpointer state: thread_id={thread_id}, rows={deleted}"
        )
        return deleted

    async def alist_threads(self, limit: int = 100) -> list[str]:
        """Return distinct thread IDs from the checkpoints table (#1122).

        Replaces the raw conn.execute call in the threads route so the
        checkpointer owns all SQL against its own schema.

        Args:
            limit: Maximum number of thread IDs to return (most-recent first).

        Returns:
            List of thread ID strings.
        """

        def _list() -> list[str]:
            with self._lock:
                result = self.conn.execute(
                    """
                    SELECT DISTINCT thread_id
                    FROM checkpoints
                    ORDER BY checkpoint_id DESC
                    LIMIT ?
                    """,
                    [limit],
                )
                return [row[0] for row in result.fetchall()]

        return await asyncio.to_thread(_list)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        with self._lock:
            self.conn.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        def _close() -> None:
            with self._lock:
                self.conn.close()

        await asyncio.to_thread(_close)


# Convenience function to get checkpointer from default DB path
def get_checkpointer() -> AsyncDuckDBCheckpointer:
    """
    Get checkpointer using default Fichero database.

    Returns:
        AsyncDuckDBCheckpointer instance
    """
    from fichero_server.db.storage import settings

    return AsyncDuckDBCheckpointer.from_db_path(settings.db_path)
