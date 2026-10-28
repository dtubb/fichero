"""The search embedder in a process of its own (#5847).

fastembed's `TextEmbedding(...)` creates an onnxruntime `InferenceSession`, and `InferenceSession::Initialize` held the
GIL for 18 minutes on the owner's Mac (a sample showed the main thread waiting for it): every thread, the event loop
and `/api/health` included, was frozen, and the app gave up on the engine. A thread cannot help against a call that
keeps the GIL, so the model lives in a forked child: its Initialize and its embedding hold only the child's GIL, a
child that does not answer in time is killed (the job fails in words, the engine goes on), and the engine's loop is
never held.

Forked, not exec'd, for the reason `loaders/kreuzberg_cache._fork_worker` gives: the shipped engine has no Python of its
own, and re-execing its sandboxed stub hangs. The child only reads texts and writes vectors.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import pickle
import signal
import socket
import threading
import time
from multiprocessing.connection import Connection
from typing import Any, NamedTuple, NoReturn

logger = logging.getLogger(__name__)

#: How long the child may take to load the model before it is killed and the embed job fails.
INIT_TIMEOUT_SECONDS = 300.0
#: How long one batch of texts may take.
EMBED_TIMEOUT_SECONDS = 600.0
#: A child that crashes mid-batch is started again this many times before the batch fails.
MAX_RESTARTS = 2


class EmbedderUnavailable(RuntimeError):
    """The embedding model could not be loaded or answer in time; the message is for the person."""


def load_failure_words(payload: str, cached: bool) -> str:
    """What a failed model load says to a person, in words (P2: eight "Could not find the model tar.gz" errors in a real
    run were engine text). A model that is not in the cache and could not be fetched is the usual cause; Activity shows
    this sentence as the embed job's reason, so search never stops indexing without saying why."""
    text = str(payload)
    missing = any(mark in text.lower() for mark in ("tar.gz", "could not find the model", "offline", "connection",
                                                    "name or service not known", "max retries", "timed out"))
    if missing and not cached:
        return ("Search can't index yet: its model isn't downloaded, and fetching it failed. Check the internet "
                "connection; it tries again later and nothing already indexed is lost.")
    return f"The search model could not be loaded: {text}"


def in_process() -> bool:
    """FICHERO_EMBED_IN_PROCESS=1 loads the model in the engine itself, as before (tests and bare tools)."""
    return os.environ.get("FICHERO_EMBED_IN_PROCESS") == "1"


def _model_files(fastembed_name: str) -> list[str]:
    """The files fastembed loads the model from, relative to its snapshot: its ONNX file, the ONNX file's extra parts
    (a 2 GB model's weights live beside it), its config and the tokenizer."""
    from fastembed import TextEmbedding

    for entry in TextEmbedding._list_supported_models():
        if entry.model.lower() == fastembed_name.lower():
            return ["config.json", "tokenizer.json", entry.model_file, *entry.additional_files]
    return ["config.json", "tokenizer.json", "model.onnx"]


def _cached(model_name: str, cache_dir: str) -> bool:
    """Whether every file of the model is in the cache, so loading needs no Hub call. A folder is not enough: a download
    that died leaves a partial one, and the child then fails to load it offline (#6218, the M4 rerun)."""
    from fichero_server.db.embeddings import SUPPORTED_EMBEDDING_SPACES, _register_fastembed_model_for_space
    from fichero_server.llm.local_models import _fastembed_source_repo

    # The pinned e5's fastembed name is an alias; its files live under the repo fastembed fetches it from
    # (qdrant/multilingual-e5-large-onnx), in that exact folder: a sibling (-instruct, or intfloat's own non-onnx
    # format, which fastembed cannot load) is not it. A model fastembed does not list is fetched from its own name.
    space = SUPPORTED_EMBEDDING_SPACES.get(model_name.lower())
    source = space.source_model_name if space else model_name
    folder = "models--" + (_fastembed_source_repo(source) or source).replace("/", "--")
    try:
        if space is not None:
            _register_fastembed_model_for_space(space)
        files = _model_files(space.fastembed_model_name if space else model_name)
        for d in os.scandir(cache_dir):
            snapshots = os.path.join(d.path, "snapshots")
            if d.name.lower() == folder.lower() and os.path.isdir(snapshots):
                # isfile follows the snapshot's link into blobs/: a link to a blob that never arrived is not a file.
                return any(all(os.path.isfile(os.path.join(snap.path, f)) and os.path.getsize(os.path.join(snap.path, f))
                               for f in files) for snap in os.scandir(snapshots) if snap.is_dir())
        return False
    except (OSError, ImportError):
        return False


def _child_env(model_name: str, cache_dir: str) -> dict[str, str]:
    """The environment the child must have BEFORE it touches the network, worked out in the parent (#5847 review 257).

    fastembed asks the Hub on every load, and urllib's macOS proxy lookup (`_scproxy`, CoreFoundation) is not safe after
    a fork. urllib skips it when a proxy variable is set, so the parent's answer goes in as variables (`no_proxy` makes
    the lookup count as answered even when there is no proxy); a cached model loads offline.
    """
    import urllib.request

    env = {f"{scheme}_proxy": url for scheme, url in urllib.request.getproxies().items() if scheme != "no"}
    env["no_proxy"] = urllib.request.getproxies().get("no") or "localhost,127.0.0.1"
    env["HF_HUB_OFFLINE"] = "1"  # the child never fetches: `RemoteEmbedder` refuses an uncached model before forking (#6218)
    env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
    return env


def materialise_model_links(cache_dir: str) -> None:
    """Make every symlinked file under the cache's snapshot folders a real file in place (#6024).

    The Hugging Face cache links snapshot files into blobs/; onnxruntime refuses external data
    (model.onnx_data) whose resolved path leaves the model folder. A hard link keeps the disk cost nil;
    a copy is the fallback across volumes. The blob stays, so the cache still finds it.
    """
    root = os.path.realpath(cache_dir) + os.sep
    for dirpath, _dirs, files in os.walk(cache_dir):
        if os.sep + "snapshots" + os.sep not in dirpath + os.sep:
            continue
        for name in files:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                continue
            target = os.path.realpath(path)
            if not os.path.isfile(target) or not target.startswith(root):
                continue  # only the cache's own blobs: a link that leads out of it is not ours to copy or replace
            tmp = f"{path}.{os.getpid()}.fichero-tmp"
            try:
                try:
                    os.link(target, tmp)
                except OSError:
                    import shutil

                    shutil.copyfile(target, tmp)
                os.replace(tmp, path)
            except OSError as exc:
                logger.warning("could not make %s a real file: %s", path, exc)
                if os.path.lexists(tmp):
                    os.unlink(tmp)


def load_text_embedding(model_name: str, cache_dir: str, threads: int) -> Any:
    """fastembed's `TextEmbedding`, retried once with the cache's links made real if the load escapes the model folder (#6024)."""
    from fastembed import TextEmbedding

    try:  # only a load that fails this way touches the cache: a model that loads is never rewritten
        return TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)
    except Exception as exc:  # noqa: BLE001 -- the cache's files are links into blobs/
        if "escapes model directory" not in str(exc):
            raise
        materialise_model_links(cache_dir)
        return TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)


def _let_go_of_the_engines_files(keep: int) -> None:
    """The forked child inherits every file the engine had open, its LISTENING SOCKET among them: a child that outlives a
    SIGKILLed engine would keep that socket live, and the next engine could not start (`engine.orphan-child-lets-go`,
    #6176). Close everything but the standard streams and the child's own pipe end."""
    try:
        fds = [int(name) for name in os.listdir("/dev/fd")]
    except OSError:  # no /dev/fd: close the likely range
        fds = list(range(3, 1024))
    for fd in fds:
        if fd > 2 and fd != keep:
            try:
                os.close(fd)
            except OSError:  # the directory listing's own descriptor, or one already gone
                pass


def _stop_lancedbs_loop() -> None:
    """lancedb's after-fork hook starts a fresh loop thread in this child; the child never uses LanceDB, and closing the
    engine's files closes that loop's kqueue, so its thread died with "Bad file descriptor" (#6237). Stop it first."""
    import sys

    background = sys.modules.get("lancedb.background_loop")
    if background is None:
        return
    try:
        background.LOOP.loop.call_soon_threadsafe(background.LOOP.loop.stop)
    except RuntimeError:  # its loop already closed: nothing left to stop
        return
    background.LOOP.thread.join(5)


def _serve(conn: Any, model_name: str, cache_dir: str, threads: int, env: dict[str, str]) -> None:
    """The child: load the model, say so, then answer batches until the pipe closes or its engine is gone."""
    os.environ.update(env)
    engine_pid = os.getppid()
    _stop_lancedbs_loop()
    _let_go_of_the_engines_files(conn.fileno())
    try:
        # A fake model imports no onnxruntime: a test's process is not launched with OBJC_DISABLE_INITIALIZE_FORK_SAFETY, as
        # the app launches the engine (EmbeddedBackendService+Spawn.swift), and an ObjC class first set up in a fork crashes.
        try:  # the engine asks nothing of Microsoft's servers (#5847: a telemetry thread sat in NetworkInformation)
            if not os.environ.get("FICHERO_EMBED_FAKE_INIT_SECONDS"):
                import onnxruntime

                onnxruntime.disable_telemetry_events()
        except Exception as exc:  # noqa: BLE001 -- an older onnxruntime has no such switch
            os.environ["FICHERO_EMBED_TELEMETRY_SWITCH"] = f"missing: {type(exc).__name__}"  # the child's own note
            logger.warning("embedder child: onnxruntime telemetry switch unavailable: %s", exc)
        if os.environ.get("FICHERO_EMBED_FAKE_INIT_SECONDS"):  # tests: a slow, fake model load
            import time

            time.sleep(float(os.environ["FICHERO_EMBED_FAKE_INIT_SECONDS"]))
            model = None
        else:
            model = load_text_embedding(model_name, cache_dir, threads)
        conn.send(("ready", None))
        while True:
            try:
                while not conn.poll(2.0):  # an idle child still notices that its engine was killed (it is re-parented)
                    if os.getppid() != engine_pid:
                        os._exit(0)
                texts = conn.recv()
            except EOFError:
                break
            try:
                if model is None and "crash" in texts and not os.path.exists(os.environ.get("FICHERO_EMBED_FAKE_CRASH", "-")):
                    open(os.environ["FICHERO_EMBED_FAKE_CRASH"], "w").close()  # tests: die once mid-batch
                    os._exit(1)
                if model is None:
                    vectors = [[float(len(t)), 1.0] for t in texts]
                else:
                    vectors = [v.tolist() if hasattr(v, "tolist") else list(v) for v in model.embed(texts)]
                conn.send(("vectors", vectors))
            except Exception as exc:  # noqa: BLE001 -- the batch fails in words, the child stays
                conn.send(("error", f"{type(exc).__name__}: {exc}"))
    except BaseException as exc:  # noqa: BLE001 -- say why the model did not load, then die
        try:
            conn.send(("error", f"{type(exc).__name__}: {exc}"))
        except Exception as sent:  # noqa: BLE001 -- the pipe is gone with the parent: nobody is left to tell
            os.environ["FICHERO_EMBED_LAST_WORDS_LOST"] = type(sent).__name__
            logger.warning("embedder child: could not report why it stopped: %s", sent)
    finally:
        os._exit(0)


class _Seed(NamedTuple):
    control: socket.socket
    pid: int


#: The seed the engine forked at start (`start_seed`); None in a test or a dev server that did not make one, where the
#: embedder forks the engine itself as before.
_SEED: _Seed | None = None
_SEED_LOCK = threading.Lock()


def start_seed() -> None:
    """Fork the seed (`activity.lane.embedder-forks-before-threads`, #6237): called once at the engine's start, before
    uvicorn's loop, LanceDB's loop or any other thread exists. It does nothing but fork a worker on request, so a worker
    never inherits a thread or a selector of the running engine (LanceDB's loop died in one with "Bad file descriptor")."""
    global _SEED
    if _SEED is not None or in_process():
        return
    ours, theirs = socket.socketpair()
    pid = os.fork()
    if pid == 0:
        ours.close()
        _seed(theirs)
    theirs.close()
    _SEED = _Seed(ours, pid)


def stop_seed() -> None:
    """End the seed (tests; the engine's own end closes its socket, and the seed leaves when it reads the end)."""
    global _SEED
    if _SEED is None:
        return
    _SEED.control.close()
    _wait_gone(_SEED.pid, 5)
    _SEED = None


def _recv_exactly(sock: socket.socket, n: int, first: bytes = b"") -> bytes:
    data = first
    while len(data) < n:
        more = sock.recv(n - len(data))
        if not more:
            raise EOFError("the other end closed")
        data += more
    return data


def _seed(control: socket.socket) -> NoReturn:
    """The seed: fork one worker (`_serve`) for each request, hand back its pid, and leave when the engine is gone."""
    try:
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)  # its workers are reaped by the system: none is left a zombie
        _let_go_of_the_engines_files(control.fileno())
        while True:
            head, fds, _flags, _addr = socket.recv_fds(control, 8, 1)
            if not head:
                break  # the engine closed its end, or died
            args = pickle.loads(_recv_exactly(control, int.from_bytes(_recv_exactly(control, 8, head), "big")))
            pid = os.fork()
            if pid == 0:
                control.close()
                signal.signal(signal.SIGCHLD, signal.SIG_DFL)
                _serve(Connection(fds[0]), *args)
            os.close(fds[0])
            control.sendall(pid.to_bytes(8, "big"))
    except BaseException as exc:  # noqa: BLE001 -- the seed only leaves; the engine's next ask says it is gone
        os.environ["FICHERO_SEED_LEFT"] = type(exc).__name__
    finally:
        os._exit(0)


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:  # the pid was reused by another user's process: ours is gone
        return True
    return False


def _wait_gone(pid: int, seconds: float) -> None:
    end = time.monotonic() + seconds
    while not _gone(pid) and time.monotonic() < end:
        try:  # the engine's own child (the seed itself) is reaped here; a seed's worker is reaped by the seed
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        time.sleep(0.02)


class _SeedWorker:
    """A worker the seed forked, as `multiprocessing.Process` stands for one the engine forked: alive, terminate, kill,
    join. It is the seed's child, so the engine signals it by pid."""

    def __init__(self, pid: int, parent: int) -> None:
        self.pid, self.parent = pid, parent

    def is_alive(self) -> bool:
        return not _gone(self.pid)

    def terminate(self) -> None:
        self._signal(signal.SIGTERM)

    def kill(self) -> None:
        self._signal(signal.SIGKILL)

    def join(self, timeout: float | None = None) -> None:
        _wait_gone(self.pid, 5 if timeout is None else timeout)

    def _signal(self, sig: int) -> None:
        try:
            os.kill(self.pid, sig)
        except ProcessLookupError:
            pass


def _ask_the_seed(seed: _Seed, args: tuple) -> tuple[Connection, _SeedWorker]:
    """A worker forked by the seed, with `args` for `_serve`, and the engine's end of its pipe."""
    ours, theirs = socket.socketpair()
    payload = pickle.dumps(args)
    try:
        with _SEED_LOCK:
            socket.send_fds(seed.control, [len(payload).to_bytes(8, "big") + payload], [theirs.fileno()])
            pid = int.from_bytes(_recv_exactly(seed.control, 8), "big")
    finally:
        theirs.close()
    return Connection(ours.detach()), _SeedWorker(pid, seed.pid)


class RemoteEmbedder:
    """Stands where fastembed's `TextEmbedding` stood: `embed(texts)` returns one vector per text."""

    close_failure: str | None = None  # why the last pipe close failed (the process is ended regardless)
    release_failure: str | None = None  # why a release in `__del__` failed

    def __init__(self, model_name: str, cache_dir: str, threads: int,
                 init_timeout: float | None = None, embed_timeout: float | None = None) -> None:
        self.model_name = model_name
        self._init_timeout = INIT_TIMEOUT_SECONDS if init_timeout is None else init_timeout
        self._embed_timeout = EMBED_TIMEOUT_SECONDS if embed_timeout is None else embed_timeout
        self._lock = threading.Lock()
        self._cache_dir, self._threads = cache_dir, threads
        self._start()

    def _start(self) -> None:
        self._conn = self._process = None
        if not _cached(self.model_name, self._cache_dir):  # also under the fake-init test switch: a test fakes the cache too
            # A forked child that downloads dies with the threads it was forked beside (LanceDB's event loop: "Bad file
            # descriptor", #6218): the app's download job fetches it in the engine, and the embed waits for it.
            raise EmbedderUnavailable("The search model is not downloaded yet: it is being fetched, and embedding for "
                                      "search waits for it.")
        if _SEED is not None:  # forked by the seed, never by the running engine (#6237); it gets the engine's env as now
            env = {**os.environ, **_child_env(self.model_name, self._cache_dir)}
            try:
                self._conn, self._process = _ask_the_seed(_SEED, (self.model_name, self._cache_dir, self._threads, env))
            except (OSError, EOFError) as exc:
                raise EmbedderUnavailable("The search model's process could not be started; embedding for search "
                                          "will try again later.") from exc
        else:  # no seed (a test, a dev server started without `main`): the engine forks it, as before
            context = multiprocessing.get_context("fork")
            self._conn, child = context.Pipe(duplex=True)
            self._process = context.Process(
                target=_serve, args=(child, self.model_name, self._cache_dir, self._threads,
                                     _child_env(self.model_name, self._cache_dir)), daemon=True)
            self._process.start()
            child.close()
        try:
            ready = self._conn.poll(self._init_timeout)
            if not ready:
                self.close()
                raise EmbedderUnavailable(
                    f"The search model took more than {self._init_timeout / 60:g} minutes to load, so it was stopped. "
                    "Embedding for search will try again later."
                )
            kind, payload = self._conn.recv()
        except (EOFError, OSError) as exc:
            self.close()
            raise EmbedderUnavailable("The search model's process stopped while loading the model; "
                                      "embedding for search will try again later.") from exc
        if kind != "ready":
            self.close()
            raise EmbedderUnavailable(load_failure_words(payload, _cached(self.model_name, self._cache_dir)))

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            for attempt in range(MAX_RESTARTS + 1):
                if not self._process.is_alive():  # it died since the last batch: start it again
                    self._start()
                try:
                    self._conn.send(list(texts))
                    if not self._conn.poll(self._embed_timeout):
                        self.close()
                        from fichero_server.execution.throttle import MemoryShortError, memory_is_busy

                        if memory_is_busy():  # slow because the Mac is short of memory: try again, do not fail the job (#23)
                            raise MemoryShortError(
                                "Waiting: memory is tight, so embedding for search was slow; it will try again.")
                        raise EmbedderUnavailable(
                            f"Embedding for search took more than {self._embed_timeout / 60:g} minutes, so it was stopped.")
                    kind, payload = self._conn.recv()
                    break
                except (EOFError, OSError):  # the child crashed mid-batch
                    self.close()
                    if attempt == MAX_RESTARTS:
                        raise EmbedderUnavailable(
                            "The search model's process stopped and did not come back; embedding for search "
                            "will try again later.") from None
        if kind != "vectors":
            raise EmbedderUnavailable(f"Embedding for search failed: {payload}")
        return payload

    def alive(self) -> bool:
        return self._process.is_alive()

    def parent_pid(self) -> int | None:
        """The process that forked the worker: the seed's pid, or the engine's own without a seed."""
        return getattr(self._process, "parent", None) or os.getpid()

    def close(self) -> None:
        """End the child; the engine goes on. Safe to call twice, and on one refused before any fork."""
        if self._process is None:
            return
        try:
            self._conn.close()
        except Exception as exc:  # noqa: BLE001 -- already closed or the pipe broke; the process is ended below
            self.close_failure = f"{type(exc).__name__}: {exc}"
            logger.warning("embedder: closing the pipe failed: %s", exc)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(5)

    def __del__(self) -> None:  # the ONNX session goes with its process when the embedder is released
        try:
            self.close()
        except Exception as exc:  # noqa: BLE001 -- interpreter shutdown: kept on the class, nothing can be raised here
            RemoteEmbedder.release_failure = f"{type(exc).__name__}: {exc}"
            logger.warning("embedder: release failed: %s", exc)
