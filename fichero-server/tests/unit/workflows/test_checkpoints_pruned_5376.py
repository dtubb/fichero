"""A run keeps only its last checkpoint (#5376, `activity.run.checkpoints-pruned`): with `keep_last_only` a save drops
the thread's earlier checkpoints and their writes (another thread and another namespace are untouched), and the
engine's run path builds its checkpointer that way. The default keeps every checkpoint, as history tools expect."""
import asyncio
from uuid import uuid4

from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer


def _cp():
    return {"id": str(uuid4()), "type": "checkpoint", "channel_values": {"m": ["x"]},
            "channel_versions": {"m": 1}, "versions_seen": {"m": 1}}


def _cfg(thread, ns=""):
    return {"configurable": {"thread_id": thread, "checkpoint_ns": ns}}


async def _count(cp, config):
    return len([t async for t in cp.alist(config)])


async def _save_three(cp, thread, ns=""):
    for _ in range(3):
        c = _cp()
        await cp.aput(_cfg(thread, ns), c, {"source": "t", "step": 1, "writes": {}}, {})
        await cp.aput_writes({"configurable": {"thread_id": thread, "checkpoint_ns": ns,
                                               "checkpoint_id": c["id"]}}, [("m", "w")], task_id="t")
    return c


def test_keep_last_only_leaves_one_checkpoint_and_its_writes(tmp_path):
    async def run():
        cp = AsyncDuckDBCheckpointer.from_db_path(tmp_path / "a.duckdb", keep_last_only=True)
        last = await _save_three(cp, "run-1")
        assert await _count(cp, _cfg("run-1")) == 1
        got = await cp.aget_tuple(_cfg("run-1"))
        assert got.checkpoint["id"] == last["id"] and len(got.pending_writes) == 1
        rows = cp.conn.execute("select count(*) from checkpoint_writes where thread_id='run-1'").fetchone()[0]
        assert rows == 1

    asyncio.run(run())


def test_pruning_touches_only_its_own_thread_and_namespace(tmp_path):
    async def run():
        cp = AsyncDuckDBCheckpointer.from_db_path(tmp_path / "b.duckdb", keep_last_only=True)
        await _save_three(cp, "run-1")
        await _save_three(cp, "run-2")
        await _save_three(cp, "run-1", ns="sub")
        assert [await _count(cp, _cfg("run-1")), await _count(cp, _cfg("run-2")),
                await _count(cp, _cfg("run-1", "sub"))] == [1, 1, 1]

    asyncio.run(run())


def test_by_default_every_checkpoint_is_kept(tmp_path):
    async def run():
        cp = AsyncDuckDBCheckpointer.from_db_path(tmp_path / "c.duckdb")
        await _save_three(cp, "run-1")
        assert await _count(cp, _cfg("run-1")) == 3

    asyncio.run(run())


def test_the_run_path_builds_a_pruning_checkpointer():
    import inspect

    from fichero_server.workflows import runtime

    assert "keep_last_only=True" in inspect.getsource(runtime.create_compiled_app)
