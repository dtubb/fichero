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


class EmbedderUnavailable(RuntimeError):
    """The embedding model could not be loaded or answer in time; the message is for the person."""


def in_process() -> bool:
    """FICHERO_EMBED_IN_PROCESS=1 loads the model in the engine itself, as before (tests and bare tools)."""
    return os.environ.get("FICHERO_EMBED_IN_PROCESS") == "1"


def _serve(conn: Any, model_name: str, cache_dir: str, threads: int) -> None:
    """The child: load the model, say so, then answer batches until the pipe closes."""
    try:
        try:  # the engine asks nothing of Microsoft's servers (#5847: a telemetry thread sat in NetworkInformation)
            import onnxruntime

            onnxruntime.disable_telemetry_events()
        except Exception:  # noqa: BLE001 -- an older onnxruntime has no such switch
            pass
        if os.environ.get("FICHERO_EMBED_FAKE_INIT_SECONDS"):  # tests: a slow, fake model load
            import time

            time.sleep(float(os.environ["FICHERO_EMBED_FAKE_INIT_SECONDS"]))
            model = None
        else:
            from fastembed import TextEmbedding

            model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=threads)
        conn.send(("ready", None))
        while True:
            try:
                texts = conn.recv()
            except EOFError:
                break
            try:
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
        except Exception:  # noqa: BLE001
            pass
    finally:
        os._exit(0)


class RemoteEmbedder:
    """Stands where fastembed's `TextEmbedding` stood: `embed(texts)` returns one vector per text."""

    def __init__(self, model_name: str, cache_dir: str, threads: int,
                 init_timeout: float | None = None, embed_timeout: float | None = None) -> None:
        self.model_name = model_name
        self._init_timeout = INIT_TIMEOUT_SECONDS if init_timeout is None else init_timeout
        self._embed_timeout = EMBED_TIMEOUT_SECONDS if embed_timeout is None else embed_timeout
        self._lock = threading.Lock()
        context = multiprocessing.get_context("fork")
        self._conn, child = context.Pipe(duplex=True)
        self._process = context.Process(target=_serve, args=(child, model_name, cache_dir, threads), daemon=True)
        self._process.start()
        child.close()
        if not self._conn.poll(self._init_timeout):
            self.close()
            raise EmbedderUnavailable(
                f"The search model took more than {self._init_timeout / 60:g} minutes to load, so it was stopped. "
                "Embedding for search will try again later."
            )
        kind, payload = self._conn.recv()
        if kind != "ready":
            self.close()
            raise EmbedderUnavailable(f"The search model could not be loaded: {payload}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            try:
                self._conn.send(list(texts))
                if not self._conn.poll(self._embed_timeout):
                    raise EmbedderUnavailable(
                        f"Embedding for search took more than {self._embed_timeout / 60:g} minutes, so it was stopped.")
                kind, payload = self._conn.recv()
            except (EOFError, OSError, BrokenPipeError) as exc:
                self.close()
                raise EmbedderUnavailable("The search model's process stopped; embedding will start it again.") from exc
            except EmbedderUnavailable:
                self.close()
                raise
        if kind != "vectors":
            raise EmbedderUnavailable(f"Embedding for search failed: {payload}")
        return payload

    def alive(self) -> bool:
        return self._process.is_alive()

    def close(self) -> None:
        """End the child; the engine goes on. Safe to call twice."""
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(5)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(5)

    def __del__(self) -> None:  # the ONNX session goes with its process when the embedder is released
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass
