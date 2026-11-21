"""The engine's one IIIF fetcher (`source/iiif.md`, `iiif.fetch.*`): every address and redirect must be https, with no
credentials, on a name that resolves only to global addresses; bodies are capped at 64 MB, four requests per host,
429/503 retried (`media.iiif_fetch.PoliteFetcher`). A refusal is a `FetchFailed` carrying a sentence."""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse

from fichero_server.media import iiif_fetch
from fichero_server.media.iiif_fetch import FetchFailed, PoliteFetcher

MAX_REDIRECTS = 5
_FETCHER: PoliteFetcher | None = None


def refusal(url: str) -> str:
    """Why this address may not be fetched ('' when it may): not https, credentials, no resolution, or any non-global address."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() != "https" or not parts.hostname:
        return "refused: only https addresses are fetched for IIIF"
    if parts.username or parts.password:
        return "refused: an address with credentials in it"
    try:
        found = {info[4][0].split("%")[0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except socket.gaierror:
        return f"refused: {parts.hostname} does not resolve"
    if not found or not all(ipaddress.ip_address(a).is_global for a in found):
        return f"refused: {parts.hostname} is not a public address"
    return ""


def safe_get(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """A `Getter` that checks each address, redirects included, before asking."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        why = refusal(current)
        if why:
            raise FetchFailed(current, None, why)
        status, headers, body = iiif_fetch.urllib_get_once(current, timeout)
        if status in (301, 302, 303, 307, 308) and headers.get("location"):
            current = urllib.parse.urljoin(current, headers["location"])
            continue
        return status, headers, body
    raise FetchFailed(url, None, f"refused: more than {MAX_REDIRECTS} redirects")


def engine_fetcher() -> PoliteFetcher:
    """The one fetcher the engine uses for every IIIF request."""
    global _FETCHER
    if _FETCHER is None:
        _FETCHER = PoliteFetcher(get=safe_get, per_host=4, retries=3)
    return _FETCHER
