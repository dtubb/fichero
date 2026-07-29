"""
Unit tests for DuckDB Checkpointer.

Tests the AsyncDuckDBCheckpointer implementation against LangGraph's
BaseCheckpointSaver interface.
"""

import asyncio
import pickle
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer, JsonCheckpointSerializer


@pytest.fixture
def temp_db():
    """Create a temporary DuckDB database for testing."""
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / 'test.duckdb'

    yield db_path

    # Cleanup - use rmtree to handle .wal and other DuckDB files
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def checkpointer(temp_db):
    """Create a checkpointer instance for testing."""
    return AsyncDuckDBCheckpointer.from_db_path(temp_db)


@pytest.fixture
def sample_checkpoint():
    """Create a sample checkpoint for testing."""
    return {
        "id": str(uuid4()),
        "type": "checkpoint",
        "channel_values": {"messages": ["hello", "world"]},
        "channel_versions": {"messages": 1},
        "versions_seen": {"messages": 1},
    }


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return {
        "source": "test",
        "step": 1,
        "writes": {},
    }


class TestCheckpointerSetup:
    """Test checkpointer initialization and setup."""

    def test_from_db_path_creates_database(self, temp_db):
        """Test that from_db_path creates database file."""
        # Database should be created
        checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
        assert temp_db.exists()
        assert checkpointer.conn is not None

    def test_tables_created_on_init(self, checkpointer):
        """Test that checkpoint tables are created on initialization."""
        # Check checkpoints table
        result = checkpointer.conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'checkpoints'
        """).fetchone()
        assert result is not None

        # Check checkpoint_writes table
        result = checkpointer.conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_name = 'checkpoint_writes'
        """).fetchone()
        assert result is not None

    def test_checkpoints_table_schema(self, checkpointer):
        """Test that checkpoints table has correct schema."""
        result = checkpointer.conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'checkpoints'
            ORDER BY ordinal_position
        """).fetchall()

        columns = {row[0]: row[1] for row in result}
        assert 'thread_id' in columns
        assert 'checkpoint_ns' in columns
        assert 'checkpoint_id' in columns
        assert 'parent_checkpoint_id' in columns
        assert 'checkpoint' in columns
        assert 'metadata' in columns

    def test_checkpoint_writes_table_schema(self, checkpointer):
        """Test that checkpoint_writes table has correct schema."""
        result = checkpointer.conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'checkpoint_writes'
            ORDER BY ordinal_position
        """).fetchall()

        columns = {row[0]: row[1] for row in result}
        assert 'thread_id' in columns
        assert 'checkpoint_ns' in columns
        assert 'checkpoint_id' in columns
        assert 'task_id' in columns
        assert 'idx' in columns
        assert 'channel' in columns
        assert 'value' in columns


def test_json_checkpoint_serializer_rejects_pickle_payload(monkeypatch):
    """A malicious pickle blob is not deserialized by the checkpoint serializer."""
    called = False

    def fake_system(command):
        nonlocal called
        called = True
        return 0

    class Evil:
        def __reduce__(self):
            import os

            return os.system, ("echo exploited",)

    monkeypatch.setattr("os.system", fake_system)

    serializer = JsonCheckpointSerializer()
    with pytest.raises(Exception):
        serializer.loads(pickle.dumps(Evil()))

    assert called is False


@pytest.mark.asyncio
async def test_checkpointer_round_trips_json_checkpoint(temp_db):
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(temp_db)
    checkpoint = {
        "id": "checkpoint-json",
        "type": "checkpoint",
        "channel_values": {"score": 0.75, "status": "done"},
        "channel_versions": {"score": 1},
        "versions_seen": {"source": {"score": 1}},
    }
    metadata = {"source": "unit", "writes": {}}
    config = {"configurable": {"thread_id": "thread-json"}}

    saved = await checkpointer.aput(config, checkpoint, metadata, {})
    loaded = await checkpointer.aget_tuple(saved)

    assert loaded is not None
    assert loaded.checkpoint == checkpoint
    assert loaded.metadata == metadata


class TestCheckpointSaveLoad:
    """Test checkpoint save and load operations."""

    @pytest.mark.asyncio
    async def test_aput_saves_checkpoint(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that aput saves checkpoint to database."""
        thread_id = "test-thread-1"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }

        # Save checkpoint
        result = await checkpointer.aput(
            config, sample_checkpoint, sample_metadata, {}
        )

        # Verify return value
        assert result["configurable"]["thread_id"] == thread_id
        assert result["configurable"]["checkpoint_id"] == sample_checkpoint["id"]

        # Verify saved in database
        row = checkpointer.conn.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ?",
            [thread_id]
        ).fetchone()
        assert row is not None
        assert row[0] == sample_checkpoint["id"]

    @pytest.mark.asyncio
    async def test_aget_tuple_retrieves_checkpoint(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that aget_tuple retrieves saved checkpoint."""
        thread_id = "test-thread-2"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }

        # Save checkpoint
        await checkpointer.aput(config, sample_checkpoint, sample_metadata, {})

        # Retrieve checkpoint
        result = await checkpointer.aget_tuple(config)

        assert result is not None
        assert result.checkpoint["id"] == sample_checkpoint["id"]
        assert result.checkpoint["channel_values"] == sample_checkpoint["channel_values"]
        assert result.metadata["source"] == sample_metadata["source"]
        assert result.config["configurable"]["thread_id"] == thread_id

    @pytest.mark.asyncio
    async def test_aget_tuple_returns_none_when_not_found(self, checkpointer):
        """Test that aget_tuple returns None for non-existent checkpoint."""
        config = {
            "configurable": {
                "thread_id": "non-existent-thread",
                "checkpoint_ns": "",
            }
        }

        result = await checkpointer.aget_tuple(config)
        assert result is None

    @pytest.mark.asyncio
    async def test_aget_tuple_with_checkpoint_id(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test retrieving specific checkpoint by ID."""
        thread_id = "test-thread-3"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }

        # Save first checkpoint
        await checkpointer.aput(config, sample_checkpoint, sample_metadata, {})

        # Save second checkpoint
        checkpoint_2 = sample_checkpoint.copy()
        checkpoint_2["id"] = str(uuid4())
        checkpoint_2["parent_checkpoint_id"] = sample_checkpoint["id"]
        await checkpointer.aput(config, checkpoint_2, sample_metadata, {})

        # Retrieve specific checkpoint
        config_with_id = config.copy()
        config_with_id["configurable"]["checkpoint_id"] = sample_checkpoint["id"]
        result = await checkpointer.aget_tuple(config_with_id)

        assert result is not None
        assert result.checkpoint["id"] == sample_checkpoint["id"]

    @pytest.mark.asyncio
    async def test_aput_compacts_outputs_before_persisting_checkpoint(
        self, checkpointer, sample_metadata
    ):
        checkpoint = {
            "id": str(uuid4()),
            "type": "checkpoint",
            "channel_values": {
                "outputs": {
                    "tx": {
                        "text": "joined",
                        "texts": ["page 1", "page 2"],
                        "results": [{"file": "a"}, {"file": "b"}],
                        "values": ["v1", "v2"],
                    }
                }
            },
            "channel_versions": {"outputs": 1},
            "versions_seen": {"source": {"outputs": 1}},
        }
        config = {"configurable": {"thread_id": "compact-thread", "checkpoint_ns": ""}}

        await checkpointer.aput(config, checkpoint, sample_metadata, {})
        result = await checkpointer.aget_tuple(config)

        assert result is not None
        tx = result.checkpoint["channel_values"]["outputs"]["tx"]
        assert tx["text"] == "joined"
        assert tx["text_count"] == 2
        assert tx["result_count"] == 2
        assert tx["value_count"] == 2
        assert "texts" not in tx
        assert "results" not in tx
        assert "values" not in tx


class TestThreadIsolation:
    """Test that checkpoints are properly isolated by thread."""

    @pytest.mark.asyncio
    async def test_threads_are_isolated(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that different threads don't interfere with each other."""
        thread_1 = "thread-1"
        thread_2 = "thread-2"

        config_1 = {"configurable": {"thread_id": thread_1, "checkpoint_ns": ""}}
        config_2 = {"configurable": {"thread_id": thread_2, "checkpoint_ns": ""}}

        # Save checkpoint for thread 1
        checkpoint_1 = sample_checkpoint.copy()
        checkpoint_1["id"] = str(uuid4())
        await checkpointer.aput(config_1, checkpoint_1, sample_metadata, {})

        # Save checkpoint for thread 2
        checkpoint_2 = sample_checkpoint.copy()
        checkpoint_2["id"] = str(uuid4())
        await checkpointer.aput(config_2, checkpoint_2, sample_metadata, {})

        # Retrieve from thread 1
        result_1 = await checkpointer.aget_tuple(config_1)
        assert result_1.checkpoint["id"] == checkpoint_1["id"]

        # Retrieve from thread 2
        result_2 = await checkpointer.aget_tuple(config_2)
        assert result_2.checkpoint["id"] == checkpoint_2["id"]

    @pytest.mark.asyncio
    async def test_checkpoint_namespace_isolation(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that checkpoint namespaces are isolated."""
        thread_id = "test-thread"

        config_ns1 = {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": "namespace-1"}
        }
        config_ns2 = {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": "namespace-2"}
        }

        # Save checkpoint in namespace 1
        checkpoint_1 = sample_checkpoint.copy()
        checkpoint_1["id"] = str(uuid4())
        await checkpointer.aput(config_ns1, checkpoint_1, sample_metadata, {})

        # Save checkpoint in namespace 2
        checkpoint_2 = sample_checkpoint.copy()
        checkpoint_2["id"] = str(uuid4())
        await checkpointer.aput(config_ns2, checkpoint_2, sample_metadata, {})

        # Retrieve from namespace 1
        result_1 = await checkpointer.aget_tuple(config_ns1)
        assert result_1.checkpoint["id"] == checkpoint_1["id"]

        # Retrieve from namespace 2
        result_2 = await checkpointer.aget_tuple(config_ns2)
        assert result_2.checkpoint["id"] == checkpoint_2["id"]


class TestPendingWrites:
    """Test pending checkpoint writes functionality."""

    @pytest.mark.asyncio
    async def test_aput_writes_saves_writes(self, checkpointer, sample_checkpoint, sample_metadata):
        """Test that aput_writes saves pending writes."""
        thread_id = "test-thread"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": sample_checkpoint["id"],
            }
        }

        # Save checkpoint first
        await checkpointer.aput(
            config, sample_checkpoint, sample_metadata, {}
        )

        # Save writes
        writes = [
            ("messages", "new message 1"),
            ("messages", "new message 2"),
        ]
        await checkpointer.aput_writes(config, writes, task_id="task-1")

        # Verify writes in database
        result = checkpointer.conn.execute("""
            SELECT channel, idx FROM checkpoint_writes
            WHERE thread_id = ? AND checkpoint_id = ?
            ORDER BY idx
        """, [thread_id, sample_checkpoint["id"]]).fetchall()

        assert len(result) == 2
        assert result[0][0] == "messages"
        assert result[0][1] == 0
        assert result[1][0] == "messages"
        assert result[1][1] == 1

    @pytest.mark.asyncio
    async def test_aget_tuple_includes_pending_writes(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that aget_tuple returns pending writes."""
        thread_id = "test-thread"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": sample_checkpoint["id"],
            }
        }

        # Save checkpoint
        await checkpointer.aput(config, sample_checkpoint, sample_metadata, {})

        # Save writes
        writes = [("messages", "new message")]
        await checkpointer.aput_writes(config, writes, task_id="task-1")

        # Retrieve checkpoint
        config_retrieve = {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
        }
        result = await checkpointer.aget_tuple(config_retrieve)

        assert result is not None
        assert len(result.pending_writes) == 1
        assert result.pending_writes[0][0] == "task-1"
        assert result.pending_writes[0][1] == "messages"
        assert result.pending_writes[0][2] == "new message"


class TestCheckpointList:
    """Test listing checkpoints."""

    @pytest.mark.asyncio
    async def test_alist_returns_all_checkpoints(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that alist returns all checkpoints for a thread."""
        thread_id = "test-thread"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

        # Save 3 checkpoints
        checkpoint_ids = []
        for i in range(3):
            checkpoint = sample_checkpoint.copy()
            checkpoint["id"] = str(uuid4())
            if i > 0:
                checkpoint["parent_checkpoint_id"] = checkpoint_ids[-1]
            await checkpointer.aput(config, checkpoint, sample_metadata, {})
            checkpoint_ids.append(checkpoint["id"])

        # List checkpoints
        checkpoints = []
        async for cp in checkpointer.alist(config):
            checkpoints.append(cp)

        # Should return all 3 checkpoints
        assert len(checkpoints) == 3
        # All checkpoint IDs should be present (order not guaranteed with UUIDs)
        returned_ids = {cp.checkpoint["id"] for cp in checkpoints}
        assert returned_ids == set(checkpoint_ids)

    @pytest.mark.asyncio
    async def test_alist_with_limit(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that alist respects limit parameter."""
        thread_id = "test-thread"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

        # Save 5 checkpoints
        for i in range(5):
            checkpoint = sample_checkpoint.copy()
            checkpoint["id"] = str(uuid4())
            await checkpointer.aput(config, checkpoint, sample_metadata, {})

        # List with limit
        checkpoints = []
        async for cp in checkpointer.alist(config, limit=2):
            checkpoints.append(cp)

        assert len(checkpoints) == 2


class TestParentCheckpoint:
    """Test parent checkpoint relationships."""

    @pytest.mark.asyncio
    async def test_parent_checkpoint_config(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that parent checkpoint config is returned."""
        thread_id = "test-thread"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

        # Save parent checkpoint
        parent = sample_checkpoint.copy()
        parent["id"] = str(uuid4())
        await checkpointer.aput(config, parent, sample_metadata, {})

        # Save child checkpoint
        child = sample_checkpoint.copy()
        child["id"] = str(uuid4())
        child["parent_checkpoint_id"] = parent["id"]
        await checkpointer.aput(config, child, sample_metadata, {})

        # Retrieve child explicitly by ID (not relying on ORDER BY with random UUIDs)
        child_config = config.copy()
        child_config["configurable"]["checkpoint_id"] = child["id"]
        result = await checkpointer.aget_tuple(child_config)

        assert result is not None
        assert result.parent_config is not None
        assert result.parent_config["configurable"]["checkpoint_id"] == parent["id"]

    @pytest.mark.asyncio
    async def test_no_parent_checkpoint(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Test that parent_config is None when no parent."""
        thread_id = "test-thread"
        config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

        # Save checkpoint without parent
        await checkpointer.aput(config, sample_checkpoint, sample_metadata, {})

        # Retrieve checkpoint
        result = await checkpointer.aget_tuple(config)

        assert result is not None
        assert result.parent_config is None


class TestDeleteThread:
    """Test adelete_thread routes through the typed public API (#1116)."""

    @pytest.mark.asyncio
    async def test_adelete_thread_removes_all_state(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """adelete_thread clears both checkpoints and checkpoint_writes."""
        thread_id = "thread-to-delete"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
                "checkpoint_id": sample_checkpoint["id"],
            }
        }

        # Seed checkpoint + pending writes
        await checkpointer.aput(config, sample_checkpoint, sample_metadata, {})
        await checkpointer.aput_writes(
            config,
            [("messages", "pending-1"), ("messages", "pending-2")],
            task_id="task-1",
        )

        # Sanity: rows exist before delete
        cp_before = checkpointer.conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", [thread_id]
        ).fetchone()[0]
        wr_before = checkpointer.conn.execute(
            "SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = ?",
            [thread_id],
        ).fetchone()[0]
        assert cp_before == 1
        assert wr_before == 2

        deleted = await checkpointer.adelete_thread(thread_id)
        assert deleted == cp_before + wr_before  # 3

        # Both tables empty for this thread
        cp_after = checkpointer.conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", [thread_id]
        ).fetchone()[0]
        wr_after = checkpointer.conn.execute(
            "SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = ?",
            [thread_id],
        ).fetchone()[0]
        assert cp_after == 0
        assert wr_after == 0

    @pytest.mark.asyncio
    async def test_adelete_thread_only_targets_named_thread(
        self, checkpointer, sample_checkpoint, sample_metadata
    ):
        """Other threads' state must survive the delete."""
        keep_id = "keep-thread"
        drop_id = "drop-thread"

        for tid in (keep_id, drop_id):
            cp = sample_checkpoint.copy()
            cp["id"] = str(uuid4())
            cfg = {
                "configurable": {
                    "thread_id": tid,
                    "checkpoint_ns": "",
                    "checkpoint_id": cp["id"],
                }
            }
            await checkpointer.aput(cfg, cp, sample_metadata, {})
            await checkpointer.aput_writes(
                cfg, [("messages", f"w-{tid}")], task_id="t"
            )

        await checkpointer.adelete_thread(drop_id)

        keep_cp = checkpointer.conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", [keep_id]
        ).fetchone()[0]
        keep_wr = checkpointer.conn.execute(
            "SELECT COUNT(*) FROM checkpoint_writes WHERE thread_id = ?",
            [keep_id],
        ).fetchone()[0]
        assert keep_cp == 1
        assert keep_wr == 1

    @pytest.mark.asyncio
    async def test_adelete_thread_missing_returns_zero(self, checkpointer):
        """Deleting an unknown thread is a no-op that returns 0."""
        deleted = await checkpointer.adelete_thread("does-not-exist")
        assert deleted == 0


@pytest.mark.asyncio
async def test_checkpointer_serializes_shared_connection_under_concurrency(
    checkpointer,
    sample_checkpoint,
):
    """Concurrent reads/writes on one shared connection do not corrupt row shape."""

    async def worker(index: int) -> None:
        thread_id = f"thread-{index}"
        base_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "",
            }
        }

        previous_id: str | None = None
        for version in range(5):
            checkpoint = sample_checkpoint.copy()
            checkpoint["id"] = str(uuid4())
            checkpoint["channel_values"] = {
                "messages": [f"thread-{index}", f"version-{version}"]
            }
            checkpoint["channel_versions"] = {"messages": version + 1}
            checkpoint["versions_seen"] = {"messages": version + 1}
            if previous_id:
                checkpoint["parent_checkpoint_id"] = previous_id

            metadata = {
                "source": "concurrency",
                "step": version,
                "writes": {},
            }

            saved = await checkpointer.aput(base_config, checkpoint, metadata, {})
            message = f"pending-{index}-{version}"
            await checkpointer.aput_writes(
                saved,
                [("messages", message)],
                task_id=f"task-{index}",
            )

            loaded = await checkpointer.aget_tuple(saved)
            assert loaded is not None
            assert loaded.config["configurable"]["thread_id"] == thread_id
            assert loaded.config["configurable"]["checkpoint_id"] == checkpoint["id"]
            assert loaded.checkpoint["id"] == checkpoint["id"]
            assert loaded.metadata["source"] == "concurrency"
            assert loaded.pending_writes == [
                (f"task-{index}", "messages", message)
            ]
            if previous_id is None:
                assert loaded.parent_config is None
            else:
                assert loaded.parent_config is not None
                assert (
                    loaded.parent_config["configurable"]["checkpoint_id"]
                    == previous_id
                )

            previous_id = checkpoint["id"]

        latest = await checkpointer.aget_tuple(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": "",
                    "checkpoint_id": previous_id,
                }
            }
        )
        assert latest is not None
        assert latest.config["configurable"]["thread_id"] == thread_id
        assert latest.checkpoint["id"] == previous_id
        assert len(latest.pending_writes) == 1

    await asyncio.gather(*(worker(index) for index in range(8)))


class TestContextManagers:
    """Test context manager support."""

    def test_sync_context_manager(self, temp_db):
        """Test that checkpointer works as sync context manager."""
        with AsyncDuckDBCheckpointer.from_db_path(temp_db) as checkpointer:
            # Verify connection works
            result = checkpointer.conn.execute("SELECT 1").fetchone()
            assert result[0] == 1

        # Connection should be closed after exiting
        # Note: DuckDB connections can be used after close, but this tests the exit works

    @pytest.mark.asyncio
    async def test_async_context_manager(self, temp_db):
        """Test that checkpointer works as async context manager."""
        async with AsyncDuckDBCheckpointer.from_db_path(temp_db) as checkpointer:
            # Verify connection works
            result = await asyncio.to_thread(
                checkpointer.conn.execute, "SELECT 1"
            )
            row = result.fetchone()
            assert row[0] == 1
