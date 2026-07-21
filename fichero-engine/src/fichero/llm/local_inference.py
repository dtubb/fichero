"""Typed local inference profiles and app-managed service lifecycle.

This module is intentionally backend-only and testable without a real MLX
server.  The default transport speaks to loopback HTTP, while tests can inject
fake process and health clients.
"""

from __future__ import annotations

import asyncio
from collections import deque
from functools import lru_cache
import ipaddress
import os
import platform
import subprocess
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, field_validator, model_validator

from fichero.providers import ProviderType, get_provider_info


class LocalInferenceValidationError(ValueError):
    """Raised when a local inference profile violates the local-only boundary."""


class LocalInferenceRuntimeMissingError(RuntimeError):
    """Raised when the managed local runtime/interpreter is unavailable."""


class LocalModelNotInstalledError(RuntimeError):
    """Raised when a managed local model has not been downloaded yet."""


class LocalModelHardwareError(RuntimeError):
    """Raised when the current machine cannot safely run a managed local model."""


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

    async def start(self) -> None:
        if self.is_running():
            return
        model_spec = self._model_spec()
        python_executable = self._python_executable()
        argv = [
            python_executable,
            *self._command(),
            "--model",
            model_spec,
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port()),
        ]
        self.last_error = None
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
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=self.stop_grace_seconds)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        await self._join_stream_tasks()
        self._update_last_error()
        self._process = None
        self.pid = None

    def is_running(self) -> bool:
        if self._process is None:
            return False
        if self._process.returncode is None:
            return True
        self._update_last_error()
        return False

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
            from fichero.mlx_runtime import get_mlx_runtime

            return str(get_mlx_runtime().require_python_path())
        except RuntimeError as exc:
            self.last_error = str(exc)
            raise LocalInferenceRuntimeMissingError(str(exc)) from exc

    def _model_spec(self) -> str:
        try:
            from fichero.mlx_model_store import get_mlx_model_store

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
        return ["-m", "mlx_lm", "server"]

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
            from fichero.mlx_model_store import get_mlx_model_store

            env.update(get_mlx_model_store().env())
        except Exception:
            pass
        return env

    def _update_last_error(self) -> None:
        if self._process is None or self._process.returncode in {None, 0}:
            return
        excerpt = next(
            (line for line in reversed(self._recent_stderr) if line),
            next((line for line in reversed(self._recent_stdout) if line), ""),
        )
        suffix = f": {excerpt}" if excerpt else ""
        self.last_error = f"local inference process exited {self._process.returncode}{suffix}"


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
        timeout = timeout_seconds if timeout_seconds is not None else self.profile.timeout_seconds
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
        return urljoin(str(self.profile.base_url).rstrip("/") + "/", self.profile.healthcheck_path.lstrip("/"))

    def _parse_health(self, payload: dict[str, Any]) -> LocalInferenceServiceHealth:
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
