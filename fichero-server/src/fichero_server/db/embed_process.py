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
import threading
from typing import Any

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


def _cached(model_name: str, cache_dir: str) -> bool:
    """Whether the model's files are already in the cache, so loading needs no Hub call."""
    from fichero_server.db.embeddings import SUPPORTED_EMBEDDING_SPACES
    from fichero_server.llm.local_models import _fastembed_source_repo

    # The pinned e5's fastembed name is an alias; its files live under the repo fastembed fetches it from
    # (qdrant/multilingual-e5-large-onnx), in that exact folder: a sibling (-instruct, or intfloat's own non-onnx
    # format, which fastembed cannot load) is not it. A model fastembed does not list is fetched from its own name.
    space = SUPPORTED_EMBEDDING_SPACES.get(model_name.lower())
    source = space.source_model_name if space else model_name
    folder = "models--" + (_fastembed_source_repo(source) or source).replace("/", "--")
    try:
        return any(d.name.lower() == folder.lower() and os.path.isdir(os.path.join(d.path, "snapshots")) for d in os.scandir(cache_dir))
    except OSError:
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
    if _cached(model_name, cache_dir):
        env["HF_HUB_OFFLINE"] = "1"
    env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"
    return env


def materialise_model_links(cache_dir: str) -> None:
    """Make every symlinked file under the cache's snapshot folders a real file in place (#6024).

    The Hugging Face cache links snapshot files into blobs/; onnxruntime refuses external data
    (model.onnx_data) whose resolved path leaves the model folder. A hard link keeps the disk cost nil;
    a copy is the fallback across volumes. The blob stays, so the cache still finds it.
    """
    for dirpath, _dirs, files in os.walk(cache_dir):
        if os.sep + "snapshots" + os.sep not in dirpath + os.sep:
            continue
        for name in files:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                continue
            target = os.path.realpath(path)
            if not os.path.isfile(target):
                continue
            tmp = path + ".fichero-tmp"
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
    """fastembed's `TextEmbedding`, with the cache's links made real first and once more if the load still escapes (#6024)."""
    from fastembed import TextEmbedding

    materialise_model_links(cache_dir)
    try:
        return TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)
    except Exception as exc:  # noqa: BLE001 -- a fresh download links its files after the first look
        if "escapes model directory" not in str(exc):
            raise
        materialise_model_links(cache_dir)
        return TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)


def _serve(conn: Any, model_name: str, cache_dir: str, threads: int, env: dict[str, str]) -> None:
    """The child: load the model, say so, then answer batches until the pipe closes."""
    os.environ.update(env)
    try:
        try:  # the engine asks nothing of Microsoft's servers (#5847: a telemetry thread sat in NetworkInformation)
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

    def close(self) -> None:
        """End the child; the engine goes on. Safe to call twice."""
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
