"""What this Mac can run and the shape of a local catalog row: the leaf the local-model side owns.

`local_models.py` exposes it; `local_inference.py` and `mlx_model_store.py` both ask it, so the store
never imports `local_inference` (#4080, `engine.llm-no-local-inference-mlx-cycle`). It imports nothing from
`llm/` but `providers`.
"""

from __future__ import annotations

import os
import platform
import subprocess
from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from fichero_server.llm.providers import ProviderType


class LocalModelHardwareError(RuntimeError):
    """Raised when the current machine cannot safely run a managed local model."""


class LocalModelSource(str, Enum):
    """Where a local catalog entry originates."""

    bundled = "bundled"
    app_cache = "app_cache"
    user_configured = "user_configured"
    remote_catalog = "remote_catalog"


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


GIB = 1024**3


def gib(n_bytes: float) -> float:
    """Bytes as the GB the Mac says (powers of 1024): the one conversion for memory and model sizes (#5833)."""
    return n_bytes / GIB


def _memory_gb_label(memory_bytes: int) -> str:
    return f"{max(1, round(gib(memory_bytes)))} GB"


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
