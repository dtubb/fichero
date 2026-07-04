"""Optional Bonjour/mDNS advertisement for the Fichero engine.

Bonjour only helps clients find a running engine on the local network. It is
not authorization: API token/device authentication is still required.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fichero import __version__
from fichero.bind_host import resolve_bind_host
from fichero.remote_access_tls import _validate_public_base_url

SERVICE_TYPE = "_fichero._tcp.local."
DEFAULT_PORT = 8765
ENABLE_ENV = "FICHERO_ENABLE_BONJOUR"
PORT_ENV = "FICHERO_BONJOUR_PORT"
NAME_ENV = "FICHERO_BONJOUR_NAME"
SPKI_ENV = "FICHERO_TLS_SPKI_HASH"
PUBLIC_URL_ENV = "FICHERO_PUBLIC_BASE_URL"
TRUE_VALUES = {"1", "true", "yes", "on"}

logger = logging.getLogger(__name__)


class BonjourUnavailable(RuntimeError):
    """Raised when the optional zeroconf runtime is unavailable."""


@dataclass(frozen=True)
class BonjourConfig:
    enabled: bool
    host: str
    port: int
    service_name: str
    version: str
    spki_hash: str
    public_url: str


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUE_VALUES


def _safe_instance_name(raw_name: str) -> str:
    name = raw_name.strip() or "Fichero Engine"
    return name.replace(".", "-")


def _safe_host_label(raw_name: str) -> str:
    name = _safe_instance_name(raw_name)
    cleaned = "".join(char if char.isalnum() or char == "-" else "-" for char in name)
    return cleaned.strip("-") or "fichero-engine"


def _default_service_name() -> str:
    hostname = socket.gethostname().strip() or "Mac"
    return f"Fichero Engine on {_safe_instance_name(hostname)}"


def build_bonjour_config(
    env: Mapping[str, str] | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    version: str = __version__,
) -> BonjourConfig:
    """Build explicit Bonjour settings from environment and bind policy."""

    source = env if env is not None else os.environ
    enabled = _is_truthy(source.get(ENABLE_ENV))
    resolved_host = resolve_bind_host(source, host=host)
    raw_port = str(port if port is not None else source.get(PORT_ENV, DEFAULT_PORT))
    resolved_port = int(raw_port)
    if not 1 <= resolved_port <= 65535:
        raise ValueError(f"{PORT_ENV} must be between 1 and 65535")

    configured_name = source.get(NAME_ENV)
    service_name = _safe_instance_name(
        configured_name if configured_name is not None else _default_service_name()
    )
    spki_hash = source.get(SPKI_ENV, "").strip()
    public_url = source.get(PUBLIC_URL_ENV, "").strip()
    if public_url:
        _validate_public_base_url(public_url)
    return BonjourConfig(
        enabled=enabled,
        host=resolved_host,
        port=resolved_port,
        service_name=service_name,
        version=version,
        spki_hash=spki_hash,
        public_url=public_url,
    )


def _packed_address(host: str) -> bytes | None:
    if host == "localhost":
        host = "127.0.0.1"
    try:
        return ipaddress.ip_address(host).packed
    except ValueError:
        return None


def _txt_properties(config: BonjourConfig) -> dict[str, str]:
    properties = {
        "version": config.version,
        "api": "1",
        # Bonjour TXT is unauthenticated discovery metadata. Never advertise
        # a trust anchor here; QR / explicit confirmation owns SPKI provenance.
        "spki": "",
        # When configured, this is the actual private URL clients should pair
        # against (for example a Tailscale URL or other explicitly managed
        # private transport). Bonjour is presence, not transport security.
        "public_url": config.public_url,
    }
    return properties


def build_service_info(
    config: BonjourConfig,
    *,
    service_info_cls: type[Any],
) -> Any:
    """Create a zeroconf.ServiceInfo-compatible object for tests/runtime."""

    address = _packed_address(config.host)
    addresses = [address] if address is not None else []
    return service_info_cls(
        SERVICE_TYPE,
        f"{config.service_name}.{SERVICE_TYPE}",
        addresses=addresses,
        port=config.port,
        properties=_txt_properties(config),
        server=f"{_safe_host_label(socket.gethostname())}.local.",
    )


def _load_zeroconf_classes() -> tuple[type[Any], type[Any]]:
    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError as exc:
        raise BonjourUnavailable(
            "Install the optional zeroconf dependency to enable Bonjour discovery."
        ) from exc
    return Zeroconf, ServiceInfo


class BonjourAdvertiser:
    """Small lifecycle wrapper around zeroconf registration."""

    def __init__(
        self,
        config: BonjourConfig,
        *,
        zeroconf_cls: type[Any] | None = None,
        service_info_cls: type[Any] | None = None,
    ) -> None:
        self.config = config
        self._zeroconf_cls = zeroconf_cls
        self._service_info_cls = service_info_cls
        self._zeroconf: Any | None = None
        self._service_info: Any | None = None

    @property
    def service_info(self) -> Any | None:
        return self._service_info

    def start(self) -> None:
        if self._zeroconf is not None:
            return
        zeroconf_cls = self._zeroconf_cls
        service_info_cls = self._service_info_cls
        if zeroconf_cls is None or service_info_cls is None:
            zeroconf_cls, service_info_cls = _load_zeroconf_classes()

        service_info = build_service_info(
            self.config,
            service_info_cls=service_info_cls,
        )
        zeroconf = zeroconf_cls()
        try:
            zeroconf.register_service(service_info)
        except Exception:
            close = getattr(zeroconf, "close", None)
            if callable(close):
                close()
            raise
        self._zeroconf = zeroconf
        self._service_info = service_info

    def stop(self) -> None:
        zeroconf = self._zeroconf
        service_info = self._service_info
        self._zeroconf = None
        self._service_info = None
        if zeroconf is None:
            return
        try:
            if service_info is not None:
                zeroconf.unregister_service(service_info)
        finally:
            zeroconf.close()


def start_bonjour_advertiser(
    env: Mapping[str, str] | None = None,
    *,
    zeroconf_cls: type[Any] | None = None,
    service_info_cls: type[Any] | None = None,
    log: logging.Logger | None = None,
) -> BonjourAdvertiser | None:
    """Start Bonjour only when explicitly enabled; never block app startup."""

    active_log = log or logger
    source = env if env is not None else os.environ
    if not _is_truthy(source.get(ENABLE_ENV)):
        return None

    advertiser: BonjourAdvertiser | None = None
    try:
        config = build_bonjour_config(env)
        advertiser = BonjourAdvertiser(
            config,
            zeroconf_cls=zeroconf_cls,
            service_info_cls=service_info_cls,
        )
        advertiser.start()
    except BonjourUnavailable as exc:
        active_log.warning("Bonjour discovery disabled: %s", exc)
        return None
    except (OSError, ValueError) as exc:
        active_log.warning("Bonjour discovery disabled by invalid configuration: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - optional discovery must not brick startup.
        active_log.warning("Bonjour discovery failed to start: %s", exc)
        if advertiser is not None:
            advertiser.stop()
        return None

    active_log.info(
        "Bonjour discovery advertising %s on %s:%d",
        SERVICE_TYPE,
        config.host,
        config.port,
    )
    return advertiser
