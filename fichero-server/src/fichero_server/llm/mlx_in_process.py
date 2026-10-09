"""MLX's own model servers, run inside the engine (#4973, ruled 2026-10-09: everything ships inside the app).

The app's engine is a Briefcase executable, not a Python interpreter, and the sandbox lets it neither build
a Python runtime after install nor start a process of its own. So MLX (mlx, mlx-lm, mlx-vlm) is bundled
at build time (`scripts/install_mlx_into_engine_bundle.py`) and its servers run here on a thread, on the
profile's loopback port, speaking the same OpenAI API: everything that calls the model is unchanged.
A vision model gets mlx_vlm's FastAPI server (it reads images, #4560); a text model gets mlx_lm's.

A dev engine (a real Python) keeps the separate-process path in `local_inference.py`;
`FICHERO_MLX_IN_PROCESS=1` forces this one there for testing.
"""

from __future__ import annotations

import gc
import importlib
import importlib.util
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any

from fichero_server.llm.local_inference import ManagedLocalInferenceProcess

logger = logging.getLogger(__name__)

#: mlx_lm.server reads its settings from `sys.argv` in `main()`; one start at a time sets it.
_ARGV_LOCK = threading.Lock()


def bundled_mlx_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("mlx", "mlx_lm", "mlx_vlm"))


def runs_in_process() -> bool:
    """True in the app's engine (no Python of its own) when MLX is bundled, or when forced."""
    if os.environ.get("FICHERO_MLX_IN_PROCESS") == "1":
        return bundled_mlx_available()
    return not Path(sys.executable).name.lower().startswith("python") and bundled_mlx_available()


#: A model's need above this share of the Mac's memory is a tight fit: its KV cache is quantized harder
#: and earlier, so a long answer (a thinking model's reasoning above all) can't push the Mac over.
TIGHT_SHARE = 0.5


def kv_settings(need_bytes: int | None, physical_bytes: int | None) -> dict[str, str]:
    """mlx_vlm's cache and batching settings for one model on this Mac (#5641; maintainer 2026-10-09:
    good defaults, tuned by recipes later).

    The KV cache grows with every token read and written. Quantized only past `QUANTIZED_KV_START`
    tokens, a page read stays at full precision and only a long output is compressed: 8 bits from
    token 5000 (mlx_vlm's own start) is close to lossless. A tight fit gets 4 bits from token 1024,
    so the model fits rather than fails. One page at a time on a Mac of 16 GB or less (a batch holds a
    cache per page); up to 4 on a bigger one. Each is overridden by its environment variable, so a
    setting can be tried without a build."""
    total = physical_bytes or 0
    tight = bool(need_bytes and total and need_bytes > total * TIGHT_SHARE)
    settings = {
        "KV_BITS": "4" if tight else "8",
        "QUANTIZED_KV_START": "1024" if tight else "5000",
        "KV_QUANT_SCHEME": "uniform",
        "MLX_VLM_MAX_NUM_SEQS": "1" if not total or total <= 16 * 1024**3 else "4",
    }
    return {key: os.environ.get(f"FICHERO_{key}", value) for key, value in settings.items()}


class InProcessLocalInferenceProcess(ManagedLocalInferenceProcess):
    """The managed process's contract (start, stop, is_running) with MLX's server on a thread."""

    def __init__(self, profile: Any, **kwargs: Any) -> None:
        super().__init__(profile, **kwargs)
        self._thread: threading.Thread | None = None
        self._stop_server: Any = None
        self._unload: Any = None

    async def start(self) -> None:
        if self.is_running():
            return
        model_spec = self._model_spec()
        self._refuse_if_memory_is_short()
        try:
            from fichero_server.llm.mlx_model_store import get_mlx_model_store

            os.environ.update(get_mlx_model_store().env())
        except Exception:  # noqa: BLE001 -- the store's cache paths are optional settings
            logger.debug("MLX model store environment not applied", exc_info=True)
        self.last_error = None
        self._gone = False
        port = self._port()
        if self._model_is_vision():
            self._start_vision(model_spec, port)
        else:
            self._start_text(model_spec, port)
        self.pid = os.getpid()

    def _start_vision(self, model_spec: str, port: int) -> None:
        import uvicorn

        os.environ["MLX_VLM_PRELOAD_MODEL"] = model_spec
        os.environ.update(kv_settings(*self._need_and_total()))
        server = uvicorn.Server(uvicorn.Config("mlx_vlm.server:app", host="127.0.0.1", port=port,
                                               log_level="warning", workers=1, server_header=False))
        app_module = importlib.import_module("mlx_vlm.server.app")

        def stop() -> None:
            server.should_exit = True

        self._stop_server, self._unload = stop, getattr(app_module, "unload_model_sync", None)
        self._run_on_thread(server.run, f"mlx-vlm:{port}")

    def _start_text(self, model_spec: str, port: int) -> None:
        from http.server import ThreadingHTTPServer

        mlx_server = importlib.import_module("mlx_lm.server")
        held: dict[str, Any] = {}

        class Held(ThreadingHTTPServer):
            def __init__(inner, *args: Any, **kwargs: Any) -> None:  # noqa: N805
                super().__init__(*args, **kwargs)
                held["httpd"] = inner

        def run(host: str, port_: int, model_provider: Any, **_: Any) -> None:
            generator = mlx_server.ResponseGenerator(
                model_provider, mlx_server.LRUPromptCache(model_provider.cli_args.prompt_cache_size))
            held["generator"] = generator
            mlx_server._run_http_server(host, port_, generator, server_class=Held)

        def serve() -> None:
            # ponytail: main() parses sys.argv; a lock keeps two starts from crossing. Upgrade path: build
            # the Namespace ourselves if mlx_lm ever exposes its parser.
            with _ARGV_LOCK:
                saved_argv, saved_run = sys.argv, mlx_server.run
                sys.argv = ["mlx_lm.server", "--model", model_spec, "--host", "127.0.0.1", "--port", str(port)]
                mlx_server.run = run
                try:
                    mlx_server.main()
                finally:
                    sys.argv, mlx_server.run = saved_argv, saved_run

        def stop() -> None:
            if "httpd" in held:
                held["httpd"].shutdown()
            if "generator" in held:
                held["generator"].stop_and_join()
            held.clear()

        self._stop_server, self._unload = stop, None
        self._run_on_thread(serve, f"mlx-lm:{port}")

    def _need_and_total(self) -> tuple[int | None, int | None]:
        """The model's estimated need and this Mac's memory, for `kv_settings` (None when unknown)."""
        from fichero_server.llm import kraken_runtime
        from fichero_server.llm.local_inference import mlx_memory_need_bytes
        from fichero_server.llm.mlx_model_store import get_mlx_model_store

        try:
            need = mlx_memory_need_bytes(get_mlx_model_store().spec(self.profile.model_id))
        except KeyError:
            need = None
        return need, kraken_runtime._physical_memory_bytes()

    def _run_on_thread(self, target: Any, name: str) -> None:
        def body() -> None:
            try:
                target()
            except BaseException as exc:  # noqa: BLE001 -- said as the server's last error, never swallowed
                self.last_error = f"The local model server stopped: {exc}"
                logger.exception("In-process MLX server %s stopped", name)

        self._thread = threading.Thread(target=body, name=name, daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            self.pid = None
            return
        if self._stop_server:
            self._stop_server()
        thread.join(timeout=max(self.stop_grace_seconds, 10.0))
        if self._unload:
            self._unload()
        self._stop_server = self._unload = None
        gc.collect()
        try:
            import mlx.core as mx

            mx.clear_cache()
        except Exception:  # noqa: BLE001 -- freeing is best effort; the memory check stays the guard
            logger.debug("mx.clear_cache failed", exc_info=True)
        self.pid = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    async def finalize_last_error(self) -> str | None:
        return self.last_error
