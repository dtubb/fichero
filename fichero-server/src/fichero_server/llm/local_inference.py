"""Typed local inference profiles and app-managed service lifecycle.

This module is intentionally backend-only and testable without a real MLX
server.  The default transport speaks to loopback HTTP, while tests can inject
fake process and health clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import deque
from contextvars import ContextVar
from functools import lru_cache
import ipaddress
import logging
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator, model_validator

from fichero_server.execution.throttle import MemoryShortError
from fichero_server.llm.providers import ProviderType, get_provider_info

logger = logging.getLogger(__name__)


class LocalInferenceValidationError(ValueError):
    """Raised when a local inference profile violates the local-only boundary."""


class LocalInferenceRuntimeMissingError(RuntimeError):
    """Raised when the managed local runtime/interpreter is unavailable."""


class LocalModelNotInstalledError(RuntimeError):
    """Raised when a managed local model has not been downloaded yet."""


class LocalModelHardwareError(RuntimeError):
    """Raised when the current machine cannot safely run a managed local model."""


class LocalModelMemoryUnavailableError(LocalModelHardwareError):
    """This Mac cannot load the model: it is too big for this Mac's memory at all, or memory stayed
    short past `MEMORY_WAIT_LIMIT_SECONDS` (#5221, #5537). A failure, said in words a person can act
    on: what it needs, what this Mac has, and a model that would fit. A model that merely does not
    fit RIGHT NOW is a `LocalModelMemoryShortError` instead: its page waits."""


class LocalModelMemoryShortError(MemoryShortError):
    """Not now: the model fits this Mac but not the memory free at this moment (#5537). A
    `MemoryShortError`, so the page WAITS for memory (`wait_for_memory_to_load`), it does not fail."""


#: A load's need: the model's weights -- 4-bit weights ARE the resident size, and the catalog's
#: download size (a trained model's own weight files, `mlx_model_store.spec`) is that size -- plus a
#: margin for what reading a page allocates on top (KV cache, activations, the vision tower's image
#: tensors). #5537: the old estimate, weights x 1.2 + 1.5 GB, asked 4.9-5.0 GB for the 3B, and with
#: macOS's own free count at 64% of the 8 GB Air (5.1 GB) it refused the trained 3B that had read 6
#: pages on that Mac before the guard. Weights + 1 GB asks 3.9 GB for the 3B.
#: ponytail: the 1 GB margin is set from that evidence (the 3B 4-bit read pages on 8 GB), not from a
#: profile of the server. Re-measure: read pages with the model on an 8 GB Mac and take the model
#: server's peak resident memory, which a run's account now reports (`run_usage.
#: model_server_peak_memory_bytes`), minus its weights; `FICHERO_MLX_MEMORY_NEED_MB` overrides the
#: whole need on one machine.
_MLX_LOAD_MARGIN_BYTES = 1 * 1024**3
_MLX_MEMORY_NEED_ENV_VAR = "FICHERO_MLX_MEMORY_NEED_MB"
#: The ceiling: a model whose need is above this share of the Mac's physical memory is too big for
#: it and is refused up front (never waited for: no amount of waiting frees the OS and the app). On
#: an 8 GB Mac that is 6 GB, so models up to ~5 GB of weights: the 3B (2.9 GB) loads, the 7B/8B
#: 4-bit (5.3-5.4 GB) do not. ponytail: a share, not a measurement of what macOS and the app keep.
_MLX_CEILING_SHARE = 0.75

#: How long a model load waits for memory before its page fails with the reason (#5537). Well under
#: the lane's hold limit (`execution.jobs.HOLD_LIMIT_SECONDS`, 900 s), which ends a slot held longer:
#: the wait, the server's start (30-300 s) and the page's read all happen inside that one slot.
MEMORY_WAIT_LIMIT_SECONDS = 300.0
#: How often a load waiting for memory looks again.
MEMORY_LOOK_AGAIN_SECONDS = 5.0


def mlx_memory_need_bytes(spec: Any) -> int:
    """How much free memory loading this catalog model and reading a page with it needs."""
    override = os.environ.get(_MLX_MEMORY_NEED_ENV_VAR)
    if override:
        try:
            return int(float(override) * 1024 * 1024)
        except ValueError:
            logger.warning("%s=%r is not a number; using the estimate", _MLX_MEMORY_NEED_ENV_VAR, override)
    return int(spec.download_size_bytes) + _MLX_LOAD_MARGIN_BYTES


def assert_memory_available_for_model(
    spec: Any,
    *,
    catalog: Any = None,
    available_bytes: Any = None,
    pressure_level: Any = None,
    physical_bytes: Any = None,
) -> None:
    """Decide BEFORE the model's process starts whether loading it now is safe (#5221, #5537).

    Too big for this Mac at all (its need above `_MLX_CEILING_SHARE` of physical memory): refused
    for good, `LocalModelMemoryUnavailableError`, with a model that would fit. Otherwise THE memory
    check, `throttle.memory_short`, with this model's need: short of memory, or pressure CRITICAL,
    raises `LocalModelMemoryShortError` -- the load waits. The readers are injectable so a test never
    depends on the real machine."""
    from fichero_server.execution.throttle import memory_short
    from fichero_server.llm import kraken_runtime

    need = mlx_memory_need_bytes(spec)
    total = (physical_bytes or kraken_runtime._physical_memory_bytes)()
    gb = lambda n: f"{n / 1024**3:.1f} GB"  # noqa: E731
    if total and need > total * _MLX_CEILING_SHARE:
        ceiling = int(total * _MLX_CEILING_SHARE)
        fits = _smaller_models_that_fit(spec, ceiling, catalog)
        raise LocalModelMemoryUnavailableError(
            f"{spec.display_name} needs about {gb(need)} to load and read a page, more than this Mac's "
            f"{gb(total)} of memory can give a model (about {gb(ceiling)})."
            + (f" Use a smaller model: {', '.join(fits)}." if fits else ""))
    reason = memory_short(
        available_bytes=available_bytes or kraken_runtime._available_memory_bytes,
        pressure_level=pressure_level or kraken_runtime._memory_pressure_level,
        need_bytes=need, what=spec.display_name)
    if reason is not None:
        raise LocalModelMemoryShortError(reason)


def release_idle_engine_models() -> list[str]:
    """Let go of the models this engine holds and nothing is using right now (#5537, rule 3 of
    'Models in memory'): Kraken's resident readers (unless a page is reading with them) and every
    embedding model no embed or search holds. The model servers are not touched here: a switch to
    another model stops the old server first (`manager_serving`). Returns what was released."""
    import sys

    released: list[str] = []
    kraken = sys.modules.get("fichero_server.llm.kraken_runtime")
    if kraken is not None and kraken._INFERENCE_LOCK.acquire(blocking=False):
        try:
            if kraken._RESIDENT:
                kraken.release_resident_models()
                released.append("Kraken")
        finally:
            kraken._INFERENCE_LOCK.release()
    embeddings = sys.modules.get("fichero_server.db.embeddings")
    if embeddings is not None:
        released += embeddings.release_idle_embedders(idle_seconds=0)
    return released


async def wait_for_memory_to_load(
    spec: Any,
    *,
    check: Any = None,
    release: Any = None,
    note: Any = None,
    stopped: Any = None,
    limit_seconds: float | None = None,
    look_again_seconds: float | None = None,
) -> None:
    """Return when `spec` can load now; until then the page WAITS, never fails at once (#5537).

    Each time memory is short it first lets go of the engine's own idle models (`release`), then
    looks again; still short, the reason ("Waiting: memory is tight: <model> needs about X GB …,
    this Mac has about Y GB free") goes on the page's row (`note`) and it sleeps and looks again.
    After `limit_seconds` it fails with that reason (`LocalModelMemoryUnavailableError`). A model
    too big for this Mac fails at once. `stopped()` (the run's Stop or Pause) ends the wait by
    raising what it returns. Everything is injectable for tests."""
    check = check or assert_memory_available_for_model
    release = release or release_idle_engine_models
    limit = MEMORY_WAIT_LIMIT_SECONDS if limit_seconds is None else limit_seconds
    look_again = MEMORY_LOOK_AGAIN_SECONDS if look_again_seconds is None else look_again_seconds
    deadline = time.monotonic() + limit
    while True:
        try:
            check(spec)
            return
        except MemoryShortError as exc:
            freed = release()
            if freed:
                logger.info("Released %s to load %s", ", ".join(freed), spec.display_name)
                try:
                    check(spec)
                    return
                except MemoryShortError as again:
                    exc = again
            reason = str(exc)
        if time.monotonic() >= deadline:
            raise LocalModelMemoryUnavailableError(
                f"{reason}. Waited {limit / 60:.0f} minutes for memory; close other apps, then run "
                "the page again.")
        if note is not None:
            note(reason)
        if stopped is not None and (signal := stopped()) is not None:
            raise signal
        await asyncio.sleep(look_again)


def _smaller_models_that_fit(spec: Any, free: int | None, catalog: Any = None) -> list[str]:
    """Catalog models that can do everything `spec` does whose load fits in `free`, the most
    capable that fits first: at most two names. Every capability, not any one (#5534): a vision
    model refused while reading a page was offered Qwen3 4B Instruct and Llama 3.2 3B, which read
    no images -- they share only 'text' with it."""
    if free is None:
        return []
    if catalog is None:
        from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS

        catalog = MANAGED_MLX_MODELS.values()
    wanted = set(spec.capabilities)
    fits = [
        other for other in catalog
        if other.model_id != spec.model_id and wanted <= set(other.capabilities)
        and mlx_memory_need_bytes(other) <= free
    ]
    fits.sort(key=mlx_memory_need_bytes, reverse=True)   # the most capable that fits, first
    return [other.display_name for other in fits[:2]]


#: How many reads at once one local model server may be asked, at most (#5537): the page fan-out's
#: own default (`builder._DEFAULT_VISION_FAN_OUT_CONCURRENCY`).
LOCAL_READS_CEILING = 4
#: The share of physical memory a model server's weights and its reads may hold together; the rest
#: is macOS's, the app's and the engine's (Kraken finding lines beside it).
_LOCAL_READS_SHARE = 0.5


def local_reads_at_once(spec: Any, *, physical_bytes: Any = None) -> int:
    """How many reads (pages, or a page's line batches) one local model server is asked at once on
    this Mac: decided from the model's need and the Mac's memory, the one place that decides it (#5537).

    ponytail: the rule is (half the Mac's memory - the weights) / the per-read margin, at least 1, at
    most `LOCAL_READS_CEILING` (4). The weights are loaded once and shared; each read in flight adds
    about the margin (KV cache, activations, the image tensors). 8 GB Mac, 3B (2.9 GB): (4 - 2.9) / 1
    = 1 -- one at a time (the Air, 2026-10-06: four at once ran it out of memory mid-read). 16 GB, 3B:
    4. 16 GB, 8B (5.4 GB): 2. Half, not `_MLX_CEILING_SHARE`: the load check asks whether the model
    fits at all; this asks how much more the reads may take beside the OS, the app and Kraken.
    Re-measure with the run's peak memory (`run_usage.model_server_peak_memory_bytes`)."""
    from fichero_server.llm import kraken_runtime

    total = (physical_bytes or kraken_runtime._physical_memory_bytes)()
    if not total:
        return 1
    weights = max(0, mlx_memory_need_bytes(spec) - _MLX_LOAD_MARGIN_BYTES)
    fits = int((total * _LOCAL_READS_SHARE - weights) // _MLX_LOAD_MARGIN_BYTES)
    return max(1, min(LOCAL_READS_CEILING, fits))


def local_read_plan(spec: Any, *, physical_bytes: Any = None) -> str:
    """The plan's words for a local model before Start (#5537, rule 8): its need, how many pages at
    once it reads on this Mac, and the peak that comes to (the weights once, a margin per read)."""
    from fichero_server.llm import kraken_runtime

    total = (physical_bytes or kraken_runtime._physical_memory_bytes)()
    at_once = local_reads_at_once(spec, physical_bytes=lambda: total)
    need = mlx_memory_need_bytes(spec)
    peak = need + (at_once - 1) * _MLX_LOAD_MARGIN_BYTES
    gb = lambda n: f"{n / 1024**3:.1f} GB"  # noqa: E731
    mac = f"this Mac ({gb(total)})" if total else "this Mac"
    pages = "one page at a time" if at_once == 1 else f"{at_once} pages at once"
    return f"{spec.display_name} needs about {gb(need)}; on {mac} it reads {pages}, about {gb(peak)} at most"


_reads_lock = threading.Lock()
_reads_in_flight = 0
#: True while this task holds a local read slot: a call inside one does not ask for a second.
_holding_read: ContextVar[bool] = ContextVar("fichero_holding_local_read", default=False)
#: How often a read waiting for a slot looks again.
_READ_LOOK_AGAIN_SECONDS = 0.05


@contextlib.asynccontextmanager
async def local_read_slot(at_once: int):
    """Hold one of `at_once` slots on the local model server for one request (#5537). One count for
    the whole engine, across every run's event loop (each workflow run has its own): the server is
    one process per Mac, whichever run asks it. Re-entrant within a task."""
    global _reads_in_flight
    if _holding_read.get():
        yield
        return
    while True:
        with _reads_lock:
            if _reads_in_flight < max(1, at_once):
                _reads_in_flight += 1
                break
        await asyncio.sleep(_READ_LOOK_AGAIN_SECONDS)
    token = _holding_read.set(True)
    try:
        yield
    finally:
        _holding_read.reset(token)
        with _reads_lock:
            _reads_in_flight -= 1


class LocalModelServerStoppedError(RuntimeError):
    """The local model server stopped while it was reading (#5537): the page's cause names it and the
    server's last output, and the page is read once more after the server restarts (`page_retry`)."""


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return True  # nothing to look at: trust the handle
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


class LocalServiceState(str, Enum):
    """Lifecycle state for an app-managed local inference service."""

    stopped = "stopped"
    starting = "starting"
    healthy = "healthy"
    degraded = "degraded"
    failed = "failed"


class LocalProviderStartupPolicy(str, Enum):
    """When the app should start a managed local provider."""

    on_demand = "on_demand"
    eager = "eager"
    manual = "manual"


class LocalModelSource(str, Enum):
    """Where a local catalog entry originates."""

    bundled = "bundled"
    app_cache = "app_cache"
    user_configured = "user_configured"
    remote_catalog = "remote_catalog"


class LocalProviderProfile(BaseModel):
    """Configuration for an app-managed, local-only inference provider."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    name: str
    provider_type: ProviderType
    model_id: str
    base_url: HttpUrl
    local_only: bool = True
    allows_paid_fallbacks: bool = False
    managed_by_app: bool = True
    startup_policy: LocalProviderStartupPolicy = LocalProviderStartupPolicy.on_demand
    healthcheck_path: str = "/health"
    timeout_seconds: float = Field(default=5.0, ge=0)
    #: Cold-start budget, distinct from the per-probe timeout above. Loading
    #: an 8B MLX model takes ~30-60s on Apple silicon; reusing the 5s health
    #: probe timeout as the whole startup deadline made every on-demand cold
    #: start fail its triggering workflow run ("health check unavailable
    #: during startup"), which then succeeded on manual retry once the model
    #: finished loading (2026-09-02, live on the Marshall exercise).
    #: 300, not 120 (#4560). The 120s budget was measured against
    #: `mlx_lm server`, which binds its port and THEN loads. `mlx_vlm.server`
    #: — the one every vision model now uses, because mlx-lm cannot read an
    #: image — preloads the model and processor BEFORE uvicorn listens, so the
    #: port simply refuses connections for the whole load and the probe sees
    #: "All connection attempts failed" rather than an unhealthy server.
    #: Measured: a 3B 4-bit VLM on a memory-pressured 16 GB M1 needed longer
    #: than 145s to bind, and the run that triggered it failed with a startup
    #: timeout over a model that was loading perfectly well. The ceiling costs
    #: nothing when it is not reached — health is polled, so a fast start
    #: still returns fast.
    startup_timeout_seconds: float = Field(default=300.0, ge=0)
    max_concurrency: int = Field(default=1, ge=1)
    visible_in_ui: bool = True
    supported: bool = True
    unsupported_reason: str | None = None
    python_executable: str | None = None
    command: list[str] = Field(default_factory=list)

    @field_validator("healthcheck_path")
    @classmethod
    def _healthcheck_path_must_be_absolute(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("healthcheck_path must start with '/'")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _timeout_seconds_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        return value

    @model_validator(mode="after")
    def _enforce_local_only_boundary(self) -> LocalProviderProfile:
        enforce_local_provider_profile(self)
        return self


class LocalModelCatalogEntry(BaseModel):
    """Typed catalog entry for a local inference model."""

    model_config = ConfigDict(use_enum_values=True)

    provider_type: ProviderType
    model_id: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)
    installed: bool = False
    download_size_bytes: int | None = Field(default=None, ge=0)
    disk_usage_bytes: int | None = Field(default=None, ge=0)
    min_memory_bytes: int | None = Field(default=None, ge=0)
    memory_class: str | None = None
    supported: bool = True
    unsupported_reason: str | None = None
    #: One line on what the model is for, and what is known about it here.
    note: str | None = None
    #: "verified" once someone has run it in Fichero, "untested" otherwise.
    #: Never inferred from a model's reputation.
    tested_status: str = "untested"
    license_label: str | None = None
    source: LocalModelSource = LocalModelSource.user_configured


class LocalInferenceCapabilities(BaseModel):
    """Cached facts about the current machine for local-model gating."""

    system: str
    machine: str
    is_apple_silicon: bool
    subprocess_capable: bool = True
    physical_memory_bytes: int | None = Field(default=None, ge=0)
    macos_version: str | None = None


def _memory_gb_label(memory_bytes: int) -> str:
    gib = max(1, round(memory_bytes / (1024**3)))
    return f"{gib} GB"


def _required_memory_label(min_memory_bytes: int) -> str:
    return f"needs {_memory_gb_label(min_memory_bytes)} unified memory"


def _sysctl_memory_bytes() -> int | None:
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    raw = result.stdout.strip()
    return int(raw) if raw.isdigit() else None


@lru_cache(maxsize=1)
def get_local_inference_capabilities() -> LocalInferenceCapabilities:
    system = platform.system()
    machine = platform.machine().lower()
    return LocalInferenceCapabilities(
        system=system,
        machine=machine,
        is_apple_silicon=system == "Darwin" and machine == "arm64",
        subprocess_capable=os.environ.get("FICHERO_SUBPROCESS_CAPABLE", "1").strip().lower()
        not in {"0", "false", "no"},
        physical_memory_bytes=_sysctl_memory_bytes() if system == "Darwin" else None,
        macos_version=platform.mac_ver()[0] or None,
    )


def clear_local_inference_capabilities_cache() -> None:
    get_local_inference_capabilities.cache_clear()


def check_local_model_hardware(
    *,
    display_name: str,
    min_memory_bytes: int | None,
    capabilities: LocalInferenceCapabilities | None = None,
) -> tuple[bool, str | None]:
    current = capabilities or get_local_inference_capabilities()
    if not current.subprocess_capable:
        return False, "not available on this device"
    if not current.is_apple_silicon:
        return False, f"{display_name} requires Apple Silicon; this Mac is {current.machine or 'unknown'}"
    if min_memory_bytes and current.physical_memory_bytes and current.physical_memory_bytes < min_memory_bytes:
        return (
            False,
            f"{display_name} {_required_memory_label(min_memory_bytes)}; this Mac has "
            f"{_memory_gb_label(current.physical_memory_bytes)}",
        )
    return True, None


class ToolSpec(BaseModel):
    """Local inference tool declaration passed to OpenAI-compatible servers."""

    name: str
    description: str | None = None
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCallEnvelope(BaseModel):
    """Typed tool-call envelope; downstream code should not inspect raw extras."""

    tool_name: str
    call_id: str
    arguments_json: dict[str, Any] = Field(default_factory=dict)
    validation_error: str | None = None
    approved: bool | None = None


class StructuredOutputEnvelope(BaseModel):
    """Typed structured-output envelope with visible validation failures."""

    schema_name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    validation_error: str | None = None
    raw_text: str | None = None


class LocalChatMessage(BaseModel):
    """OpenAI-compatible chat message for local inference requests."""

    role: str
    content: str


class TokenUsage(BaseModel):
    """Token usage returned by a local inference provider."""

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class LocalInferenceRequest(BaseModel):
    """Typed request contract for the service-manager inference layer."""

    model_config = ConfigDict(use_enum_values=True)

    profile_id: str
    provider: ProviderType
    model: str
    messages: list[LocalChatMessage]
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    response_format: dict[str, Any] | None = None
    tools: list[ToolSpec] = Field(default_factory=list)
    stream: bool = False
    run_id: str | None = None


class LocalInferenceResult(BaseModel):
    """Typed result contract for local inference."""

    model_config = ConfigDict(use_enum_values=True)

    provider: ProviderType
    model: str
    output_text: str
    structured_output: StructuredOutputEnvelope | None = None
    tool_calls: list[ToolCallEnvelope] = Field(default_factory=list)
    usage: TokenUsage | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    fallback_used: bool = False
    fallback_provider: ProviderType | None = None
    local_only_enforced: bool = True
    activity_log_id: str | None = None


class LocalInferenceServiceHealth(BaseModel):
    """Health details returned by an app-managed local inference service."""

    reachable: StrictBool
    model_loaded: StrictBool = False
    model_loading: StrictBool = False
    configured_model_id: str | None = None
    warm: StrictBool = False
    memory_warning: str | None = None
    last_error: str | None = None

    @property
    def healthy(self) -> bool:
        """Whether the service is ready for inference."""
        return self.reachable and self.model_loaded and not self.last_error


class LocalInferenceServiceStatus(BaseModel):
    """Snapshot of the local service lifecycle state."""

    model_config = ConfigDict(use_enum_values=True)

    profile_id: str
    provider_type: ProviderType
    state: LocalServiceState
    healthy: bool
    base_url: HttpUrl
    model_id: str | None = None
    pid: int | None = None
    started_at: datetime | None = None
    restart_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    memory_warning: str | None = None
    uptime_seconds: float | None = Field(default=None, ge=0)


class LocalInferenceProcess(Protocol):
    """Process adapter for app-managed local inference servers."""

    pid: int | None
    last_error: str | None

    async def start(self) -> None:
        """Start the local process."""

    async def stop(self) -> None:
        """Stop the local process."""

    def is_running(self) -> bool:
        """Return whether the process is still running."""


class ExternalLocalInferenceProcess:
    """Process adapter for an app-owned server started outside this backend.

    The Swift app can own the real process lifecycle while the backend exposes
    a typed control/status surface and still validates loopback health.
    """

    def __init__(self) -> None:
        self.pid: int | None = None
        self._running = False
        self.last_error: str | None = None

    async def start(self) -> None:
        self.last_error = None
        self._running = True

    async def stop(self) -> None:
        self._running = False
        self.pid = None

    def is_running(self) -> bool:
        return self._running


#: What the model server runs first (#5529): a thread that ends it as soon as the engine that started
#: it is gone, then the server itself (`-m module args` or `script args`, as given). Without it a server
#: outlived an engine that was killed or crashed (its shutdown never ran): an `mlx_vlm.server` was found
#: reparented to launchd, holding ~5.7 GB, with nothing to ask it anything. Its first argument is the
#: engine's pid, given rather than read: an engine that dies while the server is still starting would
#: otherwise leave it watching launchd. Stdlib only: it runs in the model runtime's own Python.
DIES_WITH_ITS_ENGINE = """
import os, runpy, sys, threading, time
engine = int(sys.argv[1])
def watch():
    while os.getppid() == engine:
        time.sleep(1.0)
    os._exit(0)
threading.Thread(target=watch, name="dies-with-its-engine", daemon=True).start()
args = sys.argv[2:]
if args[:1] == ["-m"]:
    sys.argv = [args[1]] + args[2:]
    runpy.run_module(args[1], run_name="__main__", alter_sys=True)
else:
    sys.argv = args
    runpy.run_path(args[0], run_name="__main__")
"""


class ManagedLocalInferenceProcess:
    """Spawn and supervise a loopback-only local inference subprocess."""

    def __init__(
        self,
        profile: LocalProviderProfile,
        *,
        stop_grace_seconds: float = 2.0,
        output_buffer_lines: int = 50,
    ) -> None:
        self.profile = profile
        self.stop_grace_seconds = stop_grace_seconds
        self.pid: int | None = None
        self.last_error: str | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._recent_stdout: deque[str] = deque(maxlen=output_buffer_lines)
        self._recent_stderr: deque[str] = deque(maxlen=output_buffer_lines)
        #: Its process is gone though its handle never heard (`is_running`).
        self._gone = False
        #: The process whose exit was written to the log (`_log_exit`).
        self._exit_logged: Any = None

    async def start(self) -> None:
        if self.is_running():
            return
        model_spec = self._model_spec()
        self._refuse_if_memory_is_short()
        python_executable = self._python_executable()
        argv = [
            python_executable,
            "-c",
            DIES_WITH_ITS_ENGINE,
            str(os.getpid()),
            *self._command(),
            "--model",
            model_spec,
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port()),
        ]
        self.last_error = None
        self._gone = False
        self._recent_stdout.clear()
        self._recent_stderr.clear()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._environment(),
            )
        except FileNotFoundError as exc:
            self._process = None
            self.pid = None
            self.last_error = (
                f"Local inference runtime not found: {python_executable}. "
                "Provision the local MLX runtime before starting oMLX."
            )
            raise LocalInferenceRuntimeMissingError(self.last_error) from exc
        self.pid = self._process.pid
        self._stdout_task = asyncio.create_task(
            self._drain_stream(self._process.stdout, self._recent_stdout)
        )
        self._stderr_task = asyncio.create_task(
            self._drain_stream(self._process.stderr, self._recent_stderr)
        )

    async def stop(self) -> None:
        process = self._process
        if process is None:
            self.pid = None
            return
        try:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=self.stop_grace_seconds)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
            await self._join_stream_tasks()
            self._update_last_error()
        except (RuntimeError, ProcessLookupError):
            # ProcessLookupError: the loop that started it has closed its transport (the idle stop
            # runs on a timer's own loop, #5529); the pid still names our child.
            # The asyncio subprocess handle is BOUND to the event loop that
            # spawned it — and the on-demand start path spawns it from a
            # workflow run's loop, while the stop endpoint runs on the API
            # loop. Awaiting wait() there raises "got Future … attached to a
            # different loop", the stop route 500ed, and the manager kept
            # reporting a stale healthy pid forever (2026-09-02, live).
            # Signals are loop-free and always correct for our own child.
            await self._stop_via_signals(process)
        self._process = None
        self.pid = None

    async def _stop_via_signals(self, process: Any) -> None:
        """Terminate the child by pid when its loop-bound handle is unusable."""
        import signal

        pid = getattr(process, "pid", None) or self.pid
        if not pid:
            return
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + self.stop_grace_seconds
            while time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return

    def is_running(self) -> bool:
        if self._process is None:
            return False
        if self._process.returncode is None:
            if _pid_alive(getattr(self._process, "pid", None)):
                return True
            # Gone, but its handle never heard (#5537): the run whose loop started it has ended, so
            # nothing sets the return code; the pid says it.
            self._gone = True
        self._update_last_error()
        self._log_exit()
        return False

    def _log_exit(self) -> None:
        """Write the server's last output to the engine log, once per process, when it is found to
        have exited (#5537: the Air's server died mid-read and its stderr was kept nowhere)."""
        if self._exit_logged is self._process:
            return
        self._exit_logged = self._process
        lines = [line for line in (*self._recent_stdout, *self._recent_stderr) if line and line.strip()]
        logger.error("The local model server (%s, pid %s) exited: %s. Its last output:\n%s",
                     self.profile.model_id, self.pid, self.last_error or "no reason given",
                     "\n".join(lines[-20:]) or "(none)")

    async def _drain_stream(
        self,
        stream: asyncio.StreamReader | None,
        sink: deque[str],
    ) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            sink.append(line.decode("utf-8", errors="replace").rstrip())
        while True:
            remainder = await stream.read(4096)
            if not remainder:
                break
            sink.append(remainder.decode("utf-8", errors="replace").rstrip())

    async def _join_stream_tasks(self) -> None:
        tasks = [task for task in (self._stdout_task, self._stderr_task) if task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._stdout_task = None
        self._stderr_task = None

    async def finalize_last_error(self) -> str | None:
        if self._process is None or self._process.returncode in {None, 0}:
            return self.last_error
        await self._join_stream_tasks()
        self._update_last_error()
        return self.last_error

    def _python_executable(self) -> str:
        candidate = (self.profile.python_executable or "").strip()
        if candidate:
            return candidate
        try:
            from fichero_server.llm.mlx_runtime import get_mlx_runtime

            return str(get_mlx_runtime().require_python_path())
        except RuntimeError as exc:
            self.last_error = str(exc)
            raise LocalInferenceRuntimeMissingError(str(exc)) from exc

    def _refuse_if_memory_is_short(self) -> None:
        """#5221: a catalog model is refused BEFORE its process loads it when this Mac cannot hold
        it right now. The last word: a page's call has already waited for memory
        (`wait_for_memory_to_load`, #5537) before it asks the server to start. A user-configured model (not in the catalog) has no known size: not checked."""
        from fichero_server.llm.mlx_model_store import get_mlx_model_store

        if os.environ.get("FICHERO_SKIP_MLX_MEMORY_GUARD") == "1":
            return  # the test suite: its fake sidecars load nothing, and must not read this Mac
        try:
            spec = get_mlx_model_store().spec(self.profile.model_id)
        except KeyError:
            return
        try:
            assert_memory_available_for_model(spec)
        except (LocalModelMemoryUnavailableError, LocalModelMemoryShortError) as exc:
            self.last_error = str(exc)
            raise

    def _model_spec(self) -> str:
        try:
            from fichero_server.llm.mlx_model_store import get_mlx_model_store

            store = get_mlx_model_store()
            spec = store.spec(self.profile.model_id)
            store.require_supported(spec)
            if self.profile.command:
                return self.profile.model_id
            return store.resolve_model_path(self.profile.model_id)
        except KeyError:
            if self.profile.command:
                return self.profile.model_id
            raise
        except LocalModelHardwareError as exc:
            self.last_error = str(exc)
            raise
        except FileNotFoundError as exc:
            self.last_error = str(exc)
            raise LocalModelNotInstalledError(str(exc)) from exc

    def _command(self) -> list[str]:
        if self.profile.command:
            return list(self.profile.command)
        # A vision model needs a server that can READ the image (#4560).
        # `mlx_lm server` rejects every image_url content part outright --
        # "Only 'text' content type is supported." -- so pointing it at an OCR
        # VLM produced a sidecar that loaded 5 GB of weights and then 404'd the
        # only request anyone wanted to make of it. mlx_vlm's server speaks the
        # same OpenAI shape (`--model`, `--host`, `--port`, `GET /health`) and
        # does decode images, so vision models get that one instead.
        if self._model_is_vision():
            return ["-m", "mlx_vlm.server"]
        return ["-m", "mlx_lm", "server"]

    def _model_is_vision(self) -> bool:
        """Whether the profile's model is a vision model per the managed catalog.

        Unknown models (a user-configured repo id that is not in
        MANAGED_MLX_MODELS) fall back to the text server, which is the
        conservative answer: mlx-lm loads text models mlx-vlm would refuse.
        """
        try:
            from fichero_server.llm.mlx_model_store import get_mlx_model_store

            return "vision" in get_mlx_model_store().spec(self.profile.model_id).capabilities
        except KeyError:
            return False

    def _port(self) -> int:
        parsed = urlparse(str(self.profile.base_url))
        if parsed.port is None:
            raise LocalInferenceValidationError(
                f"Managed local inference base_url must include an explicit port: {self.profile.base_url}"
            )
        return parsed.port

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        try:
            from fichero_server.llm.mlx_model_store import get_mlx_model_store

            env.update(get_mlx_model_store().env())
        except Exception:
            pass
        return env

    #: Lines that look like a CAUSE rather than a farewell. uvicorn's last word
    #: on any failed start is "INFO:     Application shutdown complete.", so
    #: taking the final line verbatim reported that as the reason a sidecar
    #: died -- observed live (#4560): a server that could not bind its port
    #: because another copy already held it was reported as
    #: "local inference process exited 3: INFO: Application shutdown complete."
    #: The real line, "[Errno 48] Address already in use", was sitting three
    #: lines up in the same buffer.
    _ERROR_HINTS = (
        "error",
        "errno",
        "exception",
        "traceback",
        "already in use",
        "not found",
        "no module named",
        "failed",
        "refused",
        "permission denied",
    )

    @classmethod
    def _most_informative(cls, lines: deque[str]) -> str | None:
        """The last line that names a cause, else the last non-empty line."""
        for line in reversed(lines):
            if line and any(hint in line.lower() for hint in cls._ERROR_HINTS):
                return line
        return next((line for line in reversed(lines) if line), None)

    def output_tail(self, lines: int = 3) -> str | None:
        """The server's last few lines of output (stderr first), for a failure that says why (#5534):
        a server that was slow to start, or loaded and then refused, leaves its reason here."""
        source = self._recent_stderr if any(self._recent_stderr) else self._recent_stdout
        tail = [line.strip() for line in source if line and line.strip()][-lines:]
        return " | ".join(tail) or None

    def _update_last_error(self) -> None:
        if self._process is None or (self._process.returncode is None and not self._gone):
            return
        if self._process.returncode == 0:
            return
        excerpt = (
            self._most_informative(self._recent_stderr)
            or self._most_informative(self._recent_stdout)
            or ""
        )
        suffix = f": {excerpt}" if excerpt else ""
        code = self._process.returncode
        self.last_error = f"local inference process exited{'' if code is None else f' {code}'}{suffix}"


class LocalHealthClient(Protocol):
    """Health transport adapter."""

    async def get_json(self, url: str, timeout_seconds: float) -> dict[str, Any]:
        """Return parsed JSON from a health endpoint."""


class HttpxLocalHealthClient:
    """HTTP health client for loopback-only local services."""

    async def get_json(self, url: str, timeout_seconds: float) -> dict[str, Any]:
        import httpx  # lazy (#3985): keep off the engine boot path

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("health response must be a JSON object")
        return payload


def is_loopback_url(url: str) -> bool:
    """Return whether a URL targets loopback HTTP(S)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower()
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def enforce_local_provider_profile(profile: LocalProviderProfile) -> None:
    """Reject profiles that could silently escape to cloud providers."""
    provider_info = get_provider_info(profile.provider_type)
    if provider_info is None:
        raise LocalInferenceValidationError(f"Unknown provider: {profile.provider_type}")
    if not provider_info.is_local:
        raise LocalInferenceValidationError(
            f"Local profile cannot target cloud provider: {profile.provider_type}"
        )
    if profile.local_only and profile.allows_paid_fallbacks:
        raise LocalInferenceValidationError(
            "local_only profiles cannot allow paid/cloud fallbacks"
        )
    if profile.managed_by_app and not is_loopback_url(str(profile.base_url)):
        raise LocalInferenceValidationError(
            "app-managed local inference profiles must use a loopback base_url"
        )


class LocalInferenceServiceManager:
    """Manage one app-owned loopback local inference service."""

    def __init__(
        self,
        profile: LocalProviderProfile,
        process: LocalInferenceProcess,
        health_client: LocalHealthClient | None = None,
        *,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        enforce_local_provider_profile(profile)
        self.profile = profile
        self.process = process
        self.health_client = health_client or HttpxLocalHealthClient()
        self.poll_interval_seconds = poll_interval_seconds
        self.state = LocalServiceState.stopped
        self.started_at: datetime | None = None
        self.restart_count = 0
        self.last_error: str | None = None
        self.memory_warning: str | None = None

    async def start(self, timeout_seconds: float | None = None) -> LocalInferenceServiceStatus:
        """Start the process and wait until it is healthy or fails."""
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else self.profile.startup_timeout_seconds
        )
        if self.state in {LocalServiceState.healthy, LocalServiceState.degraded} and self.process.is_running():
            return self.status()

        if self.state != LocalServiceState.stopped:
            self.restart_count += 1

        self.state = LocalServiceState.starting
        self.last_error = None
        await self.process.start()
        self.started_at = datetime.now(UTC)

        deadline = time.monotonic() + timeout
        status = await self._startup_health()
        while not status.healthy and status.state == LocalServiceState.starting:
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(self.poll_interval_seconds)
            status = await self._startup_health()

        if status.healthy:
            return status

        if status.state == LocalServiceState.starting:
            self.state = LocalServiceState.failed
            self.last_error = status.last_error or "local inference service did not become healthy"
            return self.status()

        return status

    async def stop(self) -> LocalInferenceServiceStatus:
        """Stop the process and mark the service stopped."""
        await self.process.stop()
        self.state = LocalServiceState.stopped
        self.started_at = None
        self.last_error = None
        self.memory_warning = None
        return self.status()

    async def health(self) -> LocalInferenceServiceStatus:
        """Poll service health and update lifecycle state."""
        if self.state == LocalServiceState.stopped:
            return self.status()

        if not self.process.is_running():
            self.state = LocalServiceState.failed
            finalize_last_error = getattr(self.process, "finalize_last_error", None)
            self.last_error = (
                await finalize_last_error() if callable(finalize_last_error) else None
                or self.process.last_error
                or "local inference process is not running"
            )
            return self.status()

        try:
            payload = await self.health_client.get_json(
                self._health_url(),
                self.profile.timeout_seconds,
            )
            health = self._parse_health(payload)
        except TimeoutError as exc:
            self.state = LocalServiceState.failed
            self.last_error = f"health check timed out: {exc}"
            return self.status()
        except Exception as exc:
            self.state = LocalServiceState.failed
            self.last_error = f"health check failed: {exc}"
            return self.status()

        return self._status_from_health(health)

    async def _startup_health(self) -> LocalInferenceServiceStatus:
        """Poll startup health while keeping transient transport failures retryable."""
        import httpx  # lazy (#3985): keep off the engine boot path

        if self.state == LocalServiceState.stopped:
            return self.status()

        if not self.process.is_running():
            self.state = LocalServiceState.failed
            finalize_last_error = getattr(self.process, "finalize_last_error", None)
            self.last_error = (
                await finalize_last_error() if callable(finalize_last_error) else None
                or self.process.last_error
                or "local inference process is not running"
            )
            return self.status()

        try:
            payload = await self.health_client.get_json(
                self._health_url(),
                self.profile.timeout_seconds,
            )
            health = self._parse_health(payload)
        except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
            self.state = LocalServiceState.starting
            self.last_error = f"health check unavailable during startup: {exc}"
            return self.status()
        except Exception as exc:
            self.state = LocalServiceState.failed
            self.last_error = f"health check failed: {exc}"
            return self.status()

        return self._status_from_health(health, startup=True)

    def _status_from_health(
        self,
        health: LocalInferenceServiceHealth,
        *,
        startup: bool = False,
    ) -> LocalInferenceServiceStatus:
        """Update lifecycle state from a parsed health response."""
        self.memory_warning = health.memory_warning
        self.last_error = health.last_error
        if health.healthy:
            self.state = LocalServiceState.healthy
        elif startup and health.reachable and not health.model_loaded:
            self.state = LocalServiceState.starting
        elif health.reachable and health.model_loading:
            self.state = LocalServiceState.starting
        elif health.reachable:
            self.state = LocalServiceState.degraded
        else:
            self.state = LocalServiceState.failed
        return self.status()

    async def restart_after_crash(self, timeout_seconds: float | None = None) -> LocalInferenceServiceStatus:
        """Restart after a detected crash and account for the restart."""
        self.state = LocalServiceState.failed
        self.last_error = "local inference process crashed"
        return await self.start(timeout_seconds=timeout_seconds)

    def status(self) -> LocalInferenceServiceStatus:
        """Return the current service status."""
        uptime: float | None = None
        if self.started_at is not None and self.state != LocalServiceState.stopped:
            uptime = max(0.0, (datetime.now(UTC) - self.started_at).total_seconds())
        return LocalInferenceServiceStatus(
            profile_id=self.profile.id,
            provider_type=self.profile.provider_type,
            state=self.state,
            healthy=self.state == LocalServiceState.healthy,
            base_url=self.profile.base_url,
            model_id=self.profile.model_id,
            pid=self.process.pid,
            started_at=self.started_at,
            restart_count=self.restart_count,
            last_error=self.last_error,
            memory_warning=self.memory_warning,
            uptime_seconds=uptime,
        )

    def _health_url(self) -> str:
        # healthcheck_path is validated ABSOLUTE ("/health"), so resolve it
        # from the server root, not under the API prefix. base_url carries
        # the OpenAI-compatible "/v1" prefix, and mlx_lm's server answers
        # GET /health at the root — the old join produced /v1/health, which
        # 404s on the real runtime, so a perfectly healthy managed oMLX
        # server was reported "unavailable" on every workflow run
        # (2026-09-02, live). The unit fake accepted both paths, which is
        # how the wrong join stayed green.
        return urljoin(str(self.profile.base_url), self.profile.healthcheck_path)

    def _parse_health(self, payload: dict[str, Any]) -> LocalInferenceServiceHealth:
        # mlx_lm's real server answers GET /health with just {"status": "ok"}
        # — no reachable/model_loaded fields. Parsing that through the rich
        # shape below defaulted model_loaded=False, so a ready runtime sat
        # permanently 'degraded' and every omlx workflow run failed with
        # 'local inference service did not become healthy' (2026-09-02,
        # live). A bare status field IS the whole contract for that server:
        # "ok" means up and serving the model it was started with.
        if "status" in payload and not any(
            k in payload for k in ("reachable", "model_loaded", "loaded")
        ):
            ok = str(payload.get("status", "")).lower() in {"ok", "healthy", "ready"}
            return LocalInferenceServiceHealth(
                reachable=ok,
                model_loaded=ok,
                warm=ok,
                configured_model_id=payload.get("model_id"),
                last_error=None if ok else f"status={payload.get('status')!r}",
            )
        try:
            return LocalInferenceServiceHealth(
                reachable=payload.get("reachable", True),
                model_loaded=payload.get("model_loaded", payload.get("loaded", False)),
                model_loading=payload.get("model_loading", payload.get("loading", False)),
                configured_model_id=payload.get("configured_model_id") or payload.get("model_id"),
                warm=payload.get("warm", False),
                memory_warning=payload.get("memory_warning"),
                last_error=payload.get("last_error") or payload.get("error"),
            )
        except Exception as exc:
            raise ValueError(f"malformed health response: {exc}") from exc


__all__ = [
    "ExternalLocalInferenceProcess",
    "HttpxLocalHealthClient",
    "LocalChatMessage",
    "LocalHealthClient",
    "LocalInferenceProcess",
    "LocalInferenceRequest",
    "LocalInferenceResult",
    "LocalInferenceCapabilities",
    "LocalModelNotInstalledError",
    "LocalModelHardwareError",
    "LocalInferenceRuntimeMissingError",
    "LocalInferenceServiceHealth",
    "LocalInferenceServiceManager",
    "LocalInferenceServiceStatus",
    "LocalInferenceValidationError",
    "LocalModelCatalogEntry",
    "LocalModelSource",
    "ManagedLocalInferenceProcess",
    "LocalProviderProfile",
    "LocalProviderStartupPolicy",
    "LocalServiceState",
    "check_local_model_hardware",
    "clear_local_inference_capabilities_cache",
    "StructuredOutputEnvelope",
    "TokenUsage",
    "ToolCallEnvelope",
    "ToolSpec",
    "enforce_local_provider_profile",
    "get_local_inference_capabilities",
    "is_loopback_url",
]
