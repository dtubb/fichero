"""DOI + ISBN online metadata resolvers (#910).

Free, no-API-key endpoints:
- **Crossref** (api.crossref.org) — journal articles + books; DOI → metadata
- **OpenAlex** (api.openalex.org) — broader academic coverage + citations
- **Open Library** (openlibrary.org) — books by ISBN

All offline-by-default. Callers opt in via the user setting or per
request. Rate-limited via httpx + simple in-process cache so
repeated lookups during a session are free.

Returns SourceMetadata-shaped dicts that merge cleanly with #908's
extractor output. See ``fichero_server.bibliography.extractor.extract_full``
for the orchestration pattern.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


CROSSREF_URL = "https://api.crossref.org/works/{doi}"
OPENALEX_URL = "https://api.openalex.org/works/doi:{doi}"
OPEN_LIBRARY_URL = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"

# Per-DOI / per-ISBN cache for the lifetime of the engine process.
_cache: dict[str, dict[str, Any]] = {}


# Polite User-Agent — Crossref + OpenAlex publish guidelines asking
# for one so they can contact you if your queries misbehave.
_USER_AGENT = "Fichero/0.1 (mailto:dtubb@users.noreply.github.com)"


def _normalize_doi(doi: str) -> str:
    """Strip URL prefixes ('https://doi.org/...') and whitespace."""
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix.lower()):
            doi = doi[len(prefix):]
    return doi.strip().rstrip("/")


def _normalize_isbn(isbn: str) -> str:
    return re.sub(r"[^0-9X]", "", isbn.upper())


async def resolve_doi(doi: str, timeout: float = 10.0) -> dict[str, Any]:
    """Resolve a DOI via Crossref → SourceMetadata-shaped dict.

    Empty dict on miss / network failure / disabled offline mode.
    Cached per-process so repeated lookups in one session don't
    hammer the API.
    """
    doi = _normalize_doi(doi)
    if not doi:
        return {}
    cache_key = f"doi:{doi}"
    if cache_key in _cache:
        return _cache[cache_key]

    try:
        import httpx
    except ImportError:
        logger.warning("httpx not available; DOI lookup disabled")
        return {}

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(CROSSREF_URL.format(doi=doi))
            if response.status_code != 200:
                logger.info("Crossref DOI miss: %s (status=%s)", doi, response.status_code)
                _cache[cache_key] = {}
                return {}
            payload = response.json().get("message", {})
    except Exception as exc:
        logger.warning("Crossref DOI lookup failed for %s: %s", doi, exc)
        return {}

    out: dict[str, Any] = {"doi": doi}
    titles = payload.get("title") or []
    if titles:
        out["title"] = titles[0]
    authors = payload.get("author") or []
    if authors:
        names = []
        for a in authors:
            family = a.get("family", "")
            given = a.get("given", "")
            if family and given:
                names.append(f"{family}, {given}")
            elif family:
                names.append(family)
        if names:
            out["authors"] = names
    issued = payload.get("issued", {}).get("date-parts") or [[None]]
    year = issued[0][0]
    if year:
        out["date"] = str(year)
    if payload.get("publisher"):
        out["publisher"] = payload["publisher"]
    container_titles = payload.get("container-title") or []
    if container_titles:
        out["journal"] = container_titles[0]
    if payload.get("volume"):
        out["volume"] = str(payload["volume"])
    if payload.get("issue"):
        out["issue"] = str(payload["issue"])
    if payload.get("page"):
        out["pages"] = str(payload["page"])
    if payload.get("ISBN"):
        isbns = payload["ISBN"]
        if isinstance(isbns, list) and isbns:
            isbn = _normalize_isbn(isbns[0])
            if len(isbn) == 13:
                out["isbn_13"] = isbn
            elif len(isbn) == 10:
                out["isbn_10"] = isbn
    if payload.get("ISSN"):
        issns = payload["ISSN"]
        if isinstance(issns, list) and issns:
            out["issn"] = issns[0]
    if payload.get("language"):
        out["language"] = payload["language"]
    out.setdefault("metadata", {})["crossref"] = True

    _cache[cache_key] = out
    return out


async def resolve_isbn(isbn: str, timeout: float = 10.0) -> dict[str, Any]:
    """Resolve an ISBN via Open Library → SourceMetadata-shaped dict."""
    isbn = _normalize_isbn(isbn)
    if not isbn:
        return {}
    cache_key = f"isbn:{isbn}"
    if cache_key in _cache:
        return _cache[cache_key]

    try:
        import httpx
    except ImportError:
        return {}

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(OPEN_LIBRARY_URL.format(isbn=isbn))
            if response.status_code != 200:
                _cache[cache_key] = {}
                return {}
            payload = response.json().get(f"ISBN:{isbn}", {})
    except Exception as exc:
        logger.warning("Open Library ISBN lookup failed for %s: %s", isbn, exc)
        return {}

    if not payload:
        _cache[cache_key] = {}
        return {}

    out: dict[str, Any] = {"isbn_13" if len(isbn) == 13 else "isbn_10": isbn}
    if payload.get("title"):
        out["title"] = payload["title"]
    if payload.get("authors"):
        out["authors"] = [a.get("name", "") for a in payload["authors"] if a.get("name")]
    if payload.get("publish_date"):
        out["date"] = payload["publish_date"]
    if payload.get("publishers"):
        out["publisher"] = payload["publishers"][0].get("name", "")
    out.setdefault("metadata", {})["open_library"] = True

    _cache[cache_key] = out
    return out


async def resolve_many(
    dois: list[str] | None = None,
    isbns: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Batch resolve. Returns ``{doi-or-isbn: metadata}``.

    Runs lookups concurrently so a 50-DOI batch finishes in roughly
    one Crossref round-trip.
    """
    tasks: list[tuple[str, asyncio.Task]] = []
    for d in dois or []:
        tasks.append((d, asyncio.create_task(resolve_doi(d))))
    for i in isbns or []:
        tasks.append((i, asyncio.create_task(resolve_isbn(i))))
    results = await asyncio.gather(*[t for _, t in tasks])
    return {key: result for (key, _), result in zip(tasks, results)}
