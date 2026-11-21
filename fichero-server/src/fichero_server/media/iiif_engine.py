"""The engine's one IIIF fetcher (`source/iiif.md`, `iiif.fetch.*`): every address and redirect is checked with
`is_safe_url` and must be https, bodies are capped at 64 MB, four requests per host, 429/503 retried
(`media.iiif_fetch.PoliteFetcher`). A refusal is a `FetchFailed` carrying a sentence."""
from __future__ import annotations

import asyncio
import concurrent.futures
import urllib.parse

from fichero_server.media import iiif_fetch
from fichero_server.media.iiif_fetch import FetchFailed, PoliteFetcher
from fichero_server.security.url_security import is_safe_url

PER_HOST = 4
MAX_REDIRECTS = 5
_REDIRECTS = {301, 302, 303, 307, 308}
_FETCHER: PoliteFetcher | None = None


def refusal(url: str) -> str:
    """Why this address may not be fetched ('' when it may)."""
    if urllib.parse.urlsplit(url).scheme.lower() != "https":
        return "refused: only https addresses are fetched for IIIF"
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        ok, why = asyncio.run(is_safe_url(url))
    else:  # called from a thread that has a loop: check on a thread of its own
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            ok, why = pool.submit(asyncio.run, is_safe_url(url)).result()
    return "" if ok else f"refused: {why}"


def safe_get(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """A `Getter` that checks the address, and each redirect's address, before asking."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        why = refusal(current)
        if why:
            raise FetchFailed(current, None, why)
        status, headers, body = iiif_fetch.urllib_get_once(current, timeout)
        if status in _REDIRECTS and headers.get("location"):
            current = urllib.parse.urljoin(current, headers["location"])
            continue
        return status, headers, body
    raise FetchFailed(url, None, f"refused: more than {MAX_REDIRECTS} redirects")


def engine_fetcher() -> PoliteFetcher:
    global _FETCHER
    if _FETCHER is None:
        _FETCHER = PoliteFetcher(get=safe_get, per_host=PER_HOST, retries=3)
    return _FETCHER
