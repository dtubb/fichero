"""The engine gives memory back, and waits for it instead of failing (#5529, #5524).

Measured 2026-10-06: a dev engine reached an 18 GB footprint in 25 minutes of one bake-off (5 pages x 3
Kraken readers) and 28 GB across several. The cause, read off the live engine with `heap`: 8,418 compiled
MPS graphs and ~6 GB of their bookkeeping. Kraken read on Apple's GPU, where torch compiles a graph for
every new line shape and keeps all of them for the life of the process (~160 MB per page of new lines in
a harness; nothing on the CPU, where the same reader was also faster). Beside it: an `mlx_vlm.server`
orphaned to launchd holding ~5.7 GB, Kraken's readers kept until the next model switch, and two memory
checks with different rules (the throttle released a job, the Kraken guard failed it at 2.3 GB free).

Kraken itself is faked at its seams here (a stub reader that allocates a known buffer); no torch work,
no model, nothing downloaded. Nothing reads this Mac's memory: every reading is injected.
"""
from __future__ import annotations

import asyncio
import gc
import os
import signal
import subprocess
import sys
import textwrap
import time
import weakref

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.llm import kraken_runtime
from fichero_server.llm.kraken_runtime import KrakenMemoryUnavailableError

GB = 1024**3


def _wait_for(predicate, seconds=20.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def mac(monkeypatch):
    """This Mac's memory as the one check reads it, switchable; the other signals never hold work."""
    state = {"free": 8 * GB, "pressure": 1}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setattr(kraken_runtime, "_available_memory_bytes", lambda: state["free"])
    monkeypatch.setattr(kraken_runtime, "_memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "PROBES", [(throttle.memory_is_tight, True)])
    return state


class TestOneMemoryCheck:
    """#5524: "one memory check with one margin"."""

    @pytest.mark.parametrize("free,pressure", [
        (8 * GB, 1), (8 * GB, 2), (8 * GB, 4), (int(2.3 * GB), 1), (int(2.3 * GB), 2), (int(2.6 * GB), 2),
        (None, 1), (None, 4),
    ])
    def test_the_throttle_and_the_kraken_guard_give_the_same_answer(self, mac, free, pressure):
        """WHY: the throttle released a job (it read only pressure) and the Kraken guard then failed it
        at 2.3 GB free ('needs 2.5 GB'). Both now ask `throttle.memory_short`: for any reading, the
        throttle holds exactly when the guard would refuse, with the same words and numbers."""
        mac.update(free=free, pressure=pressure)
        held = throttle.why_wait()
        try:
            kraken_runtime.assert_memory_available_for_kraken()
            refused = None
        except KrakenMemoryUnavailableError as exc:
            refused = str(exc)
        assert (held is None) == (refused is None), (held, refused)
        if held is not None:
            assert held.startswith(throttle.MEMORY_REASON)
            assert refused.startswith(held)

    def test_the_reason_names_both_numbers(self, mac):
        """WHY: 'memory is tight' alone cannot be acted on, and two checks quoting different numbers was
        the contradiction the person saw. The one reason says what is needed and what is free."""
        mac.update(free=int(2.3 * GB), pressure=1)
        reason = throttle.why_wait()
        assert "2.5 GB" in reason and "2.3 GB" in reason, reason

    def test_both_checks_call_the_one_function(self, mac, monkeypatch):
        """WHY: the same answer today could drift tomorrow if each kept its own copy of the rule; both
        must go through `memory_short` itself."""
        calls = []
        real = throttle.memory_short

        def spy(**kw):
            calls.append(kw)
            return real(**kw)

        monkeypatch.setattr(throttle, "memory_short", spy)
        throttle.why_wait()
        kraken_runtime.assert_memory_available_for_kraken()
        assert len(calls) == 2


class TestAJobThatDoesNotFitWaits:
    """#5524: "a run stopped on memory pauses and keeps what it measured"; never 'failed' for memory."""

    def test_a_stored_job_whose_model_does_not_fit_goes_back_to_waiting_then_runs(self, db, mac, monkeypatch):
        """WHY: memory can drop between the throttle releasing a job and its model loading. The guard's
        refusal used to fail the job ('needs about 2.5 GB'); a bake-off then lost every page it had read.
        Now the row goes back to `waiting` with the reason (the attempt not counted), the same check holds
        it, and it runs when memory is back."""
        attempts = []

        def run(db, subject):
            attempts.append(subject)
            if len(attempts) == 1:
                mac["free"] = int(2.2 * GB)  # memory dropped after the throttle let it go
            kraken_runtime.assert_memory_available_for_kraken()
            return "read"

        monkeypatch.setitem(jobs.KINDS, "t-kraken", jobs.Kind(run=run, model=None))
        job_id = jobs.enqueue(db, "t-kraken", "bake-off")
        assert _wait_for(lambda: db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id])[1]
                         and "2.2 GB" in db.execute_fetchone("SELECT reason FROM jobs WHERE id = ?", [job_id])[0])
        state, reason, tries = db.execute_fetchone("SELECT state, reason, attempts FROM jobs WHERE id = ?", [job_id])
        assert state == "waiting" and reason.startswith(throttle.MEMORY_REASON) and tries == 0
        time.sleep(0.2)
        assert len(attempts) == 1  # held by the same check while memory is short

        mac["free"] = 8 * GB
        assert _wait_for(lambda: db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0] == "done")
        assert len(attempts) == 2

    def test_handed_in_work_whose_model_does_not_fit_waits_for_its_caller(self, db, mac):
        """WHY: a run's page is handed to the lane by a caller that waits on it. A memory refusal failed
        that page; now it waits on the lane (its row says why) and the caller gets the reading."""
        tries = []

        def read():
            tries.append(1)
            kraken_runtime.assert_memory_available_for_kraken()
            return "lines"

        mac["free"] = 8 * GB
        future = jobs.submit(db, "find-lines", "page-1", model="kraken:blla",
                             fn=lambda: (mac.update(free=int(2.0 * GB)) if not tries else None, read())[1])
        assert _wait_for(lambda: (db.execute_fetchone("SELECT reason FROM jobs WHERE subject = 'page-1'") or [None])[0]
                         is not None and "2.0 GB" in db.execute_fetchone(
                             "SELECT reason FROM jobs WHERE subject = 'page-1'")[0])
        assert not future.done()
        mac["free"] = 8 * GB
        assert future.result(20) == "lines"
        assert db.execute_fetchone("SELECT state FROM jobs WHERE subject = 'page-1'")[0] == "done"


class StubReader:
    """A reader that holds a known buffer, as a loaded Kraken model holds its weights."""

    BYTES = 8 * 1024 * 1024
    alive: "weakref.WeakSet[StubReader]" = weakref.WeakSet()

    def __init__(self, path: str):
        self.path = path
        self.weights = bytearray(self.BYTES)
        StubReader.alive.add(self)


class TestKrakenLetsGoOfItsReaders:
    @pytest.fixture(autouse=True)
    def empty(self, monkeypatch):
        kraken_runtime.release_resident_models()
        yield
        kraken_runtime.release_resident_models()

    def test_kraken_reads_on_the_cpu_unless_the_gpu_is_chosen(self, monkeypatch):
        """WHY (#5529, the measured cause): on Apple's GPU torch compiles and keeps a graph for every new
        line shape, so the engine grew without end (8,418 graphs in one engine). The CPU stays flat and
        was faster for the same reader. `auto`, the default, is the CPU; only an explicit `gpu` uses it."""
        from fichero_server.core import compute_preferences as cp

        assert cp.torch_accelerator("auto") == "cpu"
        assert cp.torch_accelerator("cpu") == "cpu"
        monkeypatch.setattr(cp, "compute_preferences", lambda: {"priority": "balanced", "device": "auto"})
        config = kraken_runtime._reader_config(lambda **kw: kw)
        assert config["accelerator"] == "cpu"

    def test_many_pages_and_readers_keep_one_reader_in_memory(self):
        """WHY: a bake-off reads every page with each candidate in turn; memory must stay bounded by one
        reader (a different one replaces it), never grow with pages or candidates."""
        import tracemalloc

        tracemalloc.start()
        try:
            peaks = []
            for _round in range(3):
                for model in ("catmus", "mccatmus", "ppocr"):
                    for _page in range(5):
                        kraken_runtime._resident("read", model, lambda m=model: StubReader(m))
                        assert len(StubReader.alive) == 1
                gc.collect()
                peaks.append(tracemalloc.get_traced_memory()[0])
        finally:
            tracemalloc.stop()
        assert max(peaks) - min(peaks) < StubReader.BYTES // 2, peaks
        assert peaks[-1] < 2 * StubReader.BYTES, peaks

    def test_an_idle_reader_is_let_go(self, monkeypatch):
        """WHY: a job with no model of its own (a bake-off, a line check) never switched the lane's model,
        so the last reader, the line finder and the reader's two line-extraction processes stayed in the
        engine for good. After a quiet spell with no page they are let go."""
        monkeypatch.setattr(kraken_runtime, "IDLE_RELEASE_SECONDS", 0.05)
        kraken_runtime._resident("read", "catmus", lambda: StubReader("catmus"))
        with kraken_runtime._INFERENCE_LOCK:
            kraken_runtime._release_when_idle()
        assert _wait_for(lambda: not kraken_runtime._RESIDENT and len(StubReader.alive) == 0, 5.0)

    def test_a_reader_in_use_is_not_let_go(self, monkeypatch):
        """WHY: the idle release must never pull the reader out from under a page being read."""
        kraken_runtime._resident("read", "catmus", lambda: StubReader("catmus"))
        with kraken_runtime._INFERENCE_LOCK:
            kraken_runtime._release_if_idle()
            assert "read" in kraken_runtime._RESIDENT
        kraken_runtime._release_if_idle()
        assert not kraken_runtime._RESIDENT


class TestTheModelServerEndsWithTheEngine:
    """#5529: "the engine owns its model server's lifetime"."""

    def test_the_server_ends_when_the_engine_that_started_it_is_killed(self, tmp_path):
        """WHY: an engine killed or crashed never runs its shutdown, and its `mlx_vlm.server` lived on,
        reparented to launchd, holding ~5.7 GB. The server is started through `DIES_WITH_ITS_ENGINE`,
        which ends it once its parent is gone."""
        from fichero_server.llm.local_inference import DIES_WITH_ITS_ENGINE

        server = tmp_path / "server.py"
        server.write_text("import time\ntime.sleep(120)\n")
        engine = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
            import os, subprocess, sys, time
            child = subprocess.Popen([sys.executable, "-c", {DIES_WITH_ITS_ENGINE!r}, str(os.getpid()),
                                      {str(server)!r}])
            print(child.pid, flush=True)
            time.sleep(120)
        """)], stdout=subprocess.PIPE, text=True)
        child = int(engine.stdout.readline())
        try:
            os.kill(child, 0)  # running while its engine lives
            engine.kill()
            engine.wait(10)

            def gone():
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    return True
                return False

            assert _wait_for(gone, 10.0)
        finally:
            for pid in (engine.pid, child):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_the_engine_starts_its_server_through_the_wrapper(self, monkeypatch):
        """WHY: the wrapper only helps if the engine's own start path uses it, naming the engine's pid."""
        from fichero_server.llm import local_inference
        from fichero_server.llm.local_inference import (
            DIES_WITH_ITS_ENGINE,
            LocalInferenceRuntimeMissingError,
            LocalProviderProfile,
            ManagedLocalInferenceProcess,
        )

        seen = []

        async def spawn(*argv, **kw):
            seen.append(list(argv))
            raise FileNotFoundError(argv[0])

        monkeypatch.setattr(local_inference.asyncio, "create_subprocess_exec", spawn)
        profile = LocalProviderProfile(id="app-omlx", name="Local", provider_type="omlx", model_id="m",
                                       base_url="http://127.0.0.1:8766/v1", python_executable=sys.executable,
                                       command=["-m", "mlx_vlm.server"])
        with pytest.raises(LocalInferenceRuntimeMissingError):
            asyncio.run(ManagedLocalInferenceProcess(profile).start())
        assert seen[0][:6] == [sys.executable, "-c", DIES_WITH_ITS_ENGINE, str(os.getpid()), "-m", "mlx_vlm.server"]

    def test_the_wrapper_runs_a_module_with_its_arguments(self, tmp_path):
        """WHY: the servers are started as `-m mlx_vlm.server --model ...`; the wrapper in front must
        hand the module exactly its own arguments, or the server starts with none."""
        from fichero_server.llm.local_inference import DIES_WITH_ITS_ENGINE

        data = tmp_path / "x.json"
        data.write_text('{"a": 1}')
        out = subprocess.run([sys.executable, "-c", DIES_WITH_ITS_ENGINE, str(os.getpid()), "-m", "json.tool",
                              "--compact", str(data)],
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == '{"a":1}'

    def _manager(self):
        from fichero_server.llm.local_inference import LocalInferenceServiceManager, LocalProviderProfile

        class Process:
            pid = 4242
            last_error = None

            def __init__(self):
                self.running, self.stops = True, 0

            async def start(self):
                self.running = True

            async def stop(self):
                self.stops += 1
                self.running = False

            def is_running(self):
                return self.running

        profile = LocalProviderProfile(id="app-omlx", name="Local", provider_type="omlx", model_id="m",
                                       base_url="http://127.0.0.1:8766/v1", managed_by_app=True)
        return LocalInferenceServiceManager(profile, Process())

    def test_an_idle_server_is_stopped_and_one_in_use_is_kept(self, monkeypatch):
        """WHY: the server does not give its model's memory back by itself; one nobody has asked anything
        for a while is stopped. Each request asks for it first and so keeps it running."""
        from fichero_server.api.routes.ai import local_inference as routes

        monkeypatch.setattr(routes, "IDLE_STOP_SECONDS", 0.3)
        manager = self._manager()
        monkeypatch.setitem(routes._MANAGERS, manager.profile.id, manager)
        for _ in range(5):  # in use: asked for more often than the idle spell
            routes._stop_when_idle(manager)
            time.sleep(0.1)
        assert manager.process.stops == 0
        assert _wait_for(lambda: manager.process.stops == 1, 5.0)
        assert not manager.process.is_running()

    def test_engine_shutdown_stops_the_server_and_its_idle_timer(self, monkeypatch):
        """WHY: the engine ending is the server's end too; a timer left armed would fire on a stopped
        engine's manager."""
        from fichero_server.api.routes.ai import local_inference as routes

        monkeypatch.setattr(routes, "IDLE_STOP_SECONDS", 30.0)
        manager = self._manager()
        monkeypatch.setitem(routes._MANAGERS, manager.profile.id, manager)
        routes._stop_when_idle(manager)
        asyncio.run(routes.shutdown_managed_local_inference_services())
        assert manager.process.stops == 1
        assert routes._IDLE_TIMERS == {}
