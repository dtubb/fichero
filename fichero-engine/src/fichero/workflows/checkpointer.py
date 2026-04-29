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
import pickle
from pathlib import Path
from typing import Any, AsyncIterator

import duckdb
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
)

logger = logging.getLogger(__name__)


class PickleSerializer(SerializerProtocol):
    """Default serializer using pickle."""

    def dumps(self, obj: Any) -> bytes:
        return pickle.dumps(obj)

    def loads(self, data: bytes) -> Any:
        return pickle.loads(data)


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
            serde: Serializer for checkpoint data (defaults to pickle)
        """
        super().__init__(serde=serde or PickleSerializer())
        self.conn = conn
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

        conn = duckdb.connect(str(db_path))
        return cls(conn)

    def _setup(self) -> None:
        """Create checkpoint tables if they don't exist."""
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
        checkpoint_blob = self.serde.dumps(checkpoint)
        metadata_blob = self.serde.dumps(metadata)

        # Insert checkpoint (run in thread pool since DuckDB doesn't have native async)
        # Use ON CONFLICT for DuckDB (not INSERT OR REPLACE which is SQLite syntax)
        await asyncio.to_thread(
            self.conn.execute,
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

        result = await asyncio.to_thread(self.conn.execute, query, params)
        row = result.fetchone()

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
        writes_result = await asyncio.to_thread(
            self.conn.execute,
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
            for task_id, channel, value in writes_result.fetchall()
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

        result = await asyncio.to_thread(self.conn.execute, query, params)

        for row in result.fetchall():
            checkpoint_blob, metadata_blob, parent_id, checkpoint_id = row

            checkpoint = self.serde.loads(bytes(checkpoint_blob))
            metadata = self.serde.loads(bytes(metadata_blob))

            # Get pending writes for this checkpoint
            writes_result = await asyncio.to_thread(
                self.conn.execute,
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
                for task_id, channel, value in writes_result.fetchall()
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

            await asyncio.to_thread(
                self.conn.execute,
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await asyncio.to_thread(self.conn.close)


# Convenience function to get checkpointer from default DB path
def get_checkpointer() -> AsyncDuckDBCheckpointer:
    """
    Get checkpointer using default Fichero database.

    Returns:
        AsyncDuckDBCheckpointer instance
    """
    from fichero.storage import settings

    return AsyncDuckDBCheckpointer.from_db_path(settings.db_path)
