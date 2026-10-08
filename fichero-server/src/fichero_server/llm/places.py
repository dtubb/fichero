"""Where a model runs, worked out from the address its calls go to (`ai.where.place-is-by-address`).

A place is this Mac, a machine of the person's own, or the company that runs the model. The
provider type does not decide it: an Ollama or LM Studio server is "local" only when its address
is on this Mac. A remote Ollama (a Server URL off loopback) keeps no pages here, so it meets the
egress gate, takes the network lane and is not priced as free (#5586).

The address is the provider row's Server URL, the same one Settings lists models from, and every
call to that row uses it: chat, a workflow run, the model list (#5587). This module is the one
place that answers both questions; the gate, the lane, pricing and the model factory ask it.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

__all__ = [
    "OWN_MACHINE",
    "PROVIDER",
    "THIS_MAC",
    "address_is_on_this_mac",
    "is_loopback_url",
    "place_of",
    "row_server_url",
    "runs_on_this_mac",
    "server_address",
    "with_row_address",
]

#: The model runs on this Mac (in-process, the OS's own, or a server at a loopback address).
THIS_MAC = "this_mac"
#: A model server the person runs on another machine (a Server URL off loopback).
OWN_MACHINE = "own_machine"
#: The company or service that runs the model (a cloud provider).
PROVIDER = "provider"

#: Servers that speak OpenAI's API under `/v1`, whose row Server URL is the server's root
#: (`http://host:11434`), as Settings asks for it.
_V1_SERVERS = frozenset({"ollama", "lmstudio"})
#: The engine's own MLX server: its address is the engine's to set (the managed profile), not a row's.
_ENGINE_MANAGED = frozenset({"omlx"})


def is_loopback_url(url: str) -> bool:
    """Whether an http(s) URL targets loopback (`localhost`, 127.0.0.0/8, ::1)."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def address_is_on_this_mac(address: str | None) -> bool:
    """Whether a model server's address is on this Mac: a loopback URL or a unix socket.

    Anything else, a `.local` name included (Bonjour names another machine as readily as this
    one), is elsewhere: when it cannot be shown to be here, pages are treated as leaving."""
    text = (address or "").strip()
    if not text:
        return False
    if text.startswith("/") or text.lower().startswith(("unix:", "http+unix:")):
        return True
    return is_loopback_url(text)


def _norm(provider: str | None) -> str:
    return (provider or "").strip().lower()


def row_server_url(provider: str | None) -> str | None:
    """The Server URL of the person's provider row of this type, or None. The first row with one;
    the model list reads it here too."""
    provider = _norm(provider)
    if not provider:
        return None
    try:
        from fichero_server.db.app import get_app_db  # noqa: PLC0415

        for row in get_app_db().list_providers():
            row_type = getattr(getattr(row, "provider_type", None), "value", None)
            api_base = (getattr(row, "api_base", None) or "").strip()
            if row_type == provider and api_base:
                return api_base
    except Exception as exc:  # no app database (a bare test, a tool run outside the engine)
        logger.debug("Provider Server URL lookup failed for %s: %s", provider, exc)
        return None  # no row is readable: the provider's default address
    return None


def _row_url_for_calls(provider: str) -> str | None:
    # The engine's own MLX server is reached at its managed profile's address, not a row's.
    return None if provider in _ENGINE_MANAGED else row_server_url(provider)


def with_row_address(config: Any) -> Any:
    """The config with its provider row's Server URL as `api_base`, when it names none."""
    if config is None or (getattr(config, "api_base", None) or "").strip():
        return config
    url = _row_url_for_calls(_norm(getattr(config, "provider", None)))
    return dataclasses.replace(config, api_base=url) if url else config


def server_address(config: Any) -> str | None:
    """The base URL a call with this config goes to: its own `api_base`, else its provider row's
    Server URL, else the provider's default. An Ollama or LM Studio root gains its `/v1`."""
    from fichero_server.llm import _OPENAI_COMPATIBLE_BASE_URLS  # noqa: PLC0415

    provider = _norm(getattr(config, "provider", None))
    base = ((getattr(config, "api_base", None) or "").strip()
            or _row_url_for_calls(provider)
            or _OPENAI_COMPATIBLE_BASE_URLS.get(provider))
    if not base:
        return None
    base = base.rstrip("/")
    if provider in _V1_SERVERS and not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def place_of(config: Any) -> str:
    """Where a call with this config runs: `this_mac`, `own_machine` or `provider`.

    The OS's own models and the built-in debug model run in-process. A model server type (MLX,
    Ollama, LM Studio) runs on this Mac only when its address is here; elsewhere it is the
    person's own machine. A cloud provider type stays the provider's even at a loopback address:
    a proxy on this Mac may forward the pages on."""
    from fichero_server.llm.providers import get_provider_info  # noqa: PLC0415

    info = get_provider_info(_norm(getattr(config, "provider", None)))
    if info is None:
        return PROVIDER
    if info.is_builtin:
        return THIS_MAC
    if not info.is_local:
        return PROVIDER
    return THIS_MAC if address_is_on_this_mac(server_address(config)) else OWN_MACHINE


def runs_on_this_mac(config: Any) -> bool:
    """Whether a call with this config keeps its pages on this Mac."""
    return place_of(config) == THIS_MAC
