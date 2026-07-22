"""Research Agents sandboxed tool routes — web search, browser navigate, document fetch.

TRUST BOUNDARY — CAPABILITY ISOLATION
======================================
This module enforces a strict data-diode between the internet-egress layer and the
user's private corpus (documents, KG, notes):

  INTERNET ──(inward-only)──▶ import gate ──▶ Library (Document rows)
                                                        │
                                                        ▼
                                          (read-only, never flows back out)

Rules that MUST hold for every endpoint in this file:
1. SSRF guard (see _is_safe_url / _is_sandbox_violation) — blocks loopback, RFC-1918,
   cloud-metadata, and non-HTTP/S schemes on all outbound requests, including redirect hops.
2. Internet-egress endpoints (web-search, browser-navigate) carry NO db dependency.
   They cannot read or write the corpus — they are purely internet-facing.
3. Import endpoints (document-fetch, browser-save) accept a `db` reference but use it
   WRITE-ONLY: they never query existing documents/KG rows and never include corpus data
   in the outbound HTTP request or its headers. The only information that flows outward
   is {url, HTTP headers}; bytes flow inward as a new Document.
4. If a future AI sub-agent drives browsing, it MUST be run as an isolated agent whose
   tool list is restricted to internet-egress tools only (search/fetch/navigate).
   It MUST NOT be given library-read or KG-read tools. The sub-agent produces a URL;
   the import gate is the only crossing point into the library.

All routes perform SSRF-safe URL validation before making external HTTP requests.
Internal/private IP ranges and blocked URL schemes are rejected at the boundary.
"""

import ipaddress
import asyncio
import logging
import re
import socket
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Depends, HTTPException

if TYPE_CHECKING:
    # Type-only: httpx is imported lazily in the tool handlers (#3985); the
    # helper's "httpx.AsyncClient"/"httpx.Response" annotations still need it.
    import httpx

from fichero.api.main import get_library_database_for_write
from fichero.db import Database
from fichero.models import DocType, Document
from fichero.models.research import (
    BrowserNavigateRequest,
    BrowserNavigateResponse,
    BrowserSaveRequest,
    BrowserSaveResponse,
    DocumentFetchRequest,
    DocumentFetchResponse,
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# URL schemes that are never allowed in sandboxed requests
_SANDBOX_BLOCKED_SCHEMES = frozenset(
    [
        "file",
        "ftp",
        "ftps",
        "s3",
        "smb",
        "ssh",
        "telnet",
        "gopher",
        "ldap",
        "ldaps",
    ]
)

# Internal/private IP networks that should be blocked
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),       # private A
    ipaddress.ip_network("172.16.0.0/12"),    # private B
    ipaddress.ip_network("192.168.0.0/16"),   # private C
    ipaddress.ip_network("169.254.0.0/16"),   # link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),        # current network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped IPv6
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]

# Cloud metadata endpoints
_CLOUD_METADATA_HOSTS = frozenset(
    [
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.googleapis.com",
        "169.254.170.2",
        "169.254.170.1",
    ]
)


async def _is_internal_ip(hostname: str | None) -> bool:
    """Check if a hostname or IP is internal/private."""
    if not hostname:
        return False

    if hostname.lower() in _CLOUD_METADATA_HOSTS:
        return True

    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                return True
        return False
    except ValueError:
        pass

    try:
        addrs = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
        for addr_info in addrs:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for network in _BLOCKED_NETWORKS:
                    if ip in network:
                        return True
            except ValueError:
                continue
    except (socket.gaierror, socket.herror):
        pass

    return False


async def _is_safe_url(url: str, allow_userinfo: bool = False) -> tuple[bool, str]:
    """Comprehensive URL safety check for sandboxed requests."""
    if not url:
        return False, "URL is empty"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    scheme = parsed.scheme.lower()
    if not scheme:
        return False, "URL must have a scheme (http:// or https://)"

    if scheme in _SANDBOX_BLOCKED_SCHEMES:
        return False, f"URL scheme '{parsed.scheme}' is not allowed"

    if scheme not in ("http", "https"):
        return False, f"URL scheme '{parsed.scheme}' is not allowed (only http/https)"

    if not allow_userinfo and (parsed.username or parsed.password):
        return False, "URLs with embedded credentials are not allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must have a hostname"

    if await _is_internal_ip(hostname):
        return False, f"Internal addresses are not allowed: {hostname}"

    if re.match(r"^0[xX][0-9a-fA-F]+", hostname) or re.match(r"^\d+$", hostname):
        if await _is_internal_ip(hostname):
            return False, "Numeric IP addresses are not allowed"

    # Basic traversal hardening for path confusion vectors.
    if "/../" in parsed.path or parsed.path.endswith("/.."):
        return False, "Path traversal patterns are not allowed"

    # Disallow blocked schemes in query/fragment payloads used as redirect gadgets.
    query_and_fragment = f"{parsed.query} {parsed.fragment}".lower()
    if any(f"{blocked}://" in query_and_fragment for blocked in _SANDBOX_BLOCKED_SCHEMES):
        return False, "Embedded blocked URL schemes are not allowed"

    return True, ""


async def _is_sandbox_violation(url: str) -> bool:
    """Check if URL violates sandbox constraints."""
    is_safe, _ = await _is_safe_url(url)
    return not is_safe


async def _safe_http_get(
    client: "httpx.AsyncClient",
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    max_redirects: int = 5,
) -> "httpx.Response":
    """GET with explicit redirect validation to prevent SSRF redirect bypass."""
    current_url = url
    for _ in range(max_redirects + 1):
        is_safe, error = await _is_safe_url(current_url)
        if not is_safe:
            raise HTTPException(status_code=400, detail=f"URL not allowed: {error}")

        response = await client.get(
            current_url,
            headers=headers,
            params=params,
            follow_redirects=False,
        )

        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise HTTPException(status_code=400, detail="Redirect missing location")
            next_url = urljoin(str(current_url), location)
            is_safe, error = await _is_safe_url(next_url)
            if not is_safe:
                raise HTTPException(
                    status_code=400,
                    detail=f"Redirect target not allowed: {error}",
                )
            current_url = next_url
            params = None
            continue

        response.raise_for_status()
        return response

    raise HTTPException(status_code=400, detail="Too many redirects")


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tool: Web Search
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tools/web-search", response_model=WebSearchResponse)
async def execute_web_search(
    request: WebSearchRequest,
) -> WebSearchResponse:
    """Execute a web search using httpx (sandboxed — no filesystem/CLI escape)."""
    import httpx  # lazy (#3985): keep off the engine boot path

    if not request.query or len(request.query.strip()) < 2:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 2 characters",
        )

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(request.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        ) as client:
            # DuckDuckGo HTML lite (no API key needed)
            params = {
                "q": request.query,
                "kl": request.language or "en-us",
            }
            resp = await _safe_http_get(
                client,
                "https://html.duckduckgo.com/html/",
                params=params,
            )
            html = resp.text if isinstance(resp.text, str) else str(resp.text)

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Web search timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Search provider error: {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Web search failed: {str(e)}")

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Parse DuckDuckGo HTML results (simple regex, no external parser)
    results: list[WebSearchResult] = []

    # DuckDuckGo HTML format: <a href="..." class="result__a">Title</a>
    # followed by <a href="..." class="result__url">url</a> and <p class="result__snippet">snippet</p>
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__url"[^>]*>(.*?)</a>.*?'
        r'<p[^>]+class="result__snippet"[^>]*>(.*?)</p>',
        re.DOTALL | re.IGNORECASE,
    )
    for i, match in enumerate(link_pattern.finditer(html)):
        if i >= request.max_results:
            break
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        url = match.group(2).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        # Validate search results using comprehensive security check
        if url:
            is_safe, _ = await _is_safe_url(url)
            if is_safe:
                results.append(
                    WebSearchResult(
                        title=title[:500] if title else "",
                        url=url,
                        snippet=snippet[:1000] if snippet else "",
                    )
                )

    return WebSearchResponse(
        query=request.query,
        results=results,
        total_results=len(results),
        execution_time_ms=elapsed_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tool: Browser Navigate
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tools/browser-navigate", response_model=BrowserNavigateResponse)
async def execute_browser_navigate(
    request: BrowserNavigateRequest,
) -> BrowserNavigateResponse:
    """Navigate to a URL and extract content (sandboxed — no filesystem/CLI escape)."""
    import httpx  # lazy (#3985): keep off the engine boot path

    if await _is_sandbox_violation(request.url):
        raise HTTPException(
            status_code=400,
            detail="URL scheme not allowed in sandboxed browser",
        )

    # Comprehensive URL validation (SSRF protection)
    is_safe, error_msg = await _is_safe_url(request.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"URL not allowed: {error_msg}")

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(request.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=10),
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            resp = await _safe_http_get(client, request.url, headers=headers)
            html_content = resp.text if isinstance(resp.text, str) else str(resp.text)

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Browser navigation timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Navigation error: {e.response.status_code}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Browser navigation failed: {str(e)}"
        )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Extract title and links
    title_match = re.search(
        r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL
    )
    title = title_match.group(1).strip() if title_match else None
    title = re.sub(r"<[^>]+>", "", title or "").strip()

    # Extract href links
    link_pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)
    links: list[str] = []
    for match in link_pattern.finditer(html_content):
        href = match.group(1)
        # Validate extracted links using comprehensive security check
        if href.startswith("http"):
            is_safe, _ = await _is_safe_url(href)
            if is_safe:
                links.append(href)

    return BrowserNavigateResponse(
        url=request.url,
        title=title[:500] if title else None,
        html_content=html_content[:50000]
        if html_content
        else None,  # truncate large pages
        screenshot_base64=None,  # screenshot not yet implemented
        extracted_links=links[:100],  # limit links
        execution_time_ms=elapsed_ms,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sandboxed Tool: Document Fetch
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tools/document-fetch", response_model=DocumentFetchResponse)
async def execute_document_fetch(
    request: DocumentFetchRequest,
    db: Database = Depends(get_library_database_for_write),
) -> DocumentFetchResponse:
    """Fetch a document URL and optionally save as Layer 1 Source (sandboxed)."""
    import httpx  # lazy (#3985): keep off the engine boot path

    if await _is_sandbox_violation(request.url):
        raise HTTPException(
            status_code=400,
            detail="URL scheme not allowed in sandboxed fetch",
        )

    # Comprehensive URL validation (SSRF protection)
    is_safe, error_msg = await _is_safe_url(request.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"URL not allowed: {error_msg}")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                ),
            }
            resp = await _safe_http_get(client, request.url, headers=headers)
            content = resp.text if isinstance(resp.text, str) else str(resp.text)
            content_type = str(resp.headers.get("content-type", "text/plain"))
            # Extract title from HTML or use URL
            if "text/html" in content_type:
                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
                )
                title = title_match.group(1).strip() if title_match else request.url
                title = re.sub(r"<[^>]+>", "", title).strip()
            else:
                title = request.url.split("/")[-1]

    except HTTPException:
        raise
    except httpx.TimeoutException:
        return DocumentFetchResponse(
            url=request.url,
            title=None,
            content=None,
            content_type=None,
            source_id=None,
            success=False,
            error="Fetch timed out",
        )
    except Exception as e:
        return DocumentFetchResponse(
            url=request.url,
            title=None,
            content=None,
            content_type=None,
            source_id=None,
            success=False,
            error=f"Fetch failed: {str(e)}",
        )

    # Optionally create a Layer 1 Source document
    source_id = None
    save_error: str | None = None
    if request.create_as_source:
        try:
            doc = Document(
                name=title[:255] if title else request.url,
                # A fetched web page is a file-type document. (#2507: the old
                # value was a non-existent DocType member, so this save always
                # raised AttributeError — silently swallowed, making "save as
                # source" a no-op until now.)
                doc_type=DocType.file,
                path=request.url,
                page_content=content[:50000],  # store truncated content
                metadata={
                    "source_url": request.url,
                    "content_type": content_type,
                    "research_project_id": request.project_id,
                    "fetched_at": datetime.now().isoformat(),
                    **request.metadata,
                },
            )
            db.save(doc)
            source_id = doc.id
        except Exception as exc:
            # #2507: the fetch itself succeeded, but the optional source save
            # failed. Never swallow it silently (the caller would believe the
            # page was saved). Log loudly and surface the failure in the
            # response so source_id=None is explained, not masked.
            logger.warning(
                "fetch_document: fetched %s but failed to save it as a "
                "source document: %s",
                request.url,
                exc,
            )
            save_error = f"Fetched but failed to save as source: {exc}"

    return DocumentFetchResponse(
        url=request.url,
        title=title[:500] if title else None,
        content=content[:50000] if content else None,
        content_type=content_type,
        source_id=source_id,
        success=True,
        error=save_error,
    )


# ─── Extension to mime → file extension lookup ───────────────────────────────

_MIME_TO_EXT: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/tiff": ".tif",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/json": ".json",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


def _ext_from_content_type(content_type: str | None, url: str) -> str:
    """Best-effort extension from Content-Type, falling back to URL path."""
    if content_type:
        mime = content_type.split(";")[0].strip().lower()
        if mime in _MIME_TO_EXT:
            return _MIME_TO_EXT[mime]
    # Fall back to URL path extension
    from pathlib import Path as _Path
    suffix = _Path(urlparse(url).path).suffix
    return suffix if suffix else ".bin"


@router.post("/tools/browser-save", response_model=BrowserSaveResponse)
async def browser_save(
    request: BrowserSaveRequest,
    db: Database = Depends(get_library_database_for_write),
) -> BrowserSaveResponse:
    """Download a URL as raw bytes and import it into the library as a real Document."""
    import httpx  # lazy (#3985): keep off the engine boot path
    import tempfile
    from pathlib import Path as _Path
    from fichero.ingest import ingest_file, IngestMode

    if await _is_sandbox_violation(request.url):
        raise HTTPException(status_code=400, detail="URL scheme not allowed in sandboxed fetch")

    is_safe, error_msg = await _is_safe_url(request.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"URL not allowed: {error_msg}")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=10.0),
            follow_redirects=False,
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                ),
            }
            resp = await _safe_http_get(client, request.url, headers=headers)
            content_type = str(resp.headers.get("content-type", "application/octet-stream"))
            raw_bytes: bytes = resp.content
    except HTTPException:
        raise
    except httpx.TimeoutException:
        return BrowserSaveResponse(url=request.url, success=False, error="Fetch timed out")
    except Exception as e:
        return BrowserSaveResponse(url=request.url, success=False, error=f"Fetch failed: {e}")

    ext = _ext_from_content_type(content_type, request.url)

    # Derive display name: caller suggestion > URL basename > "download"
    if request.suggested_name:
        display_name = request.suggested_name
        if not _Path(display_name).suffix:
            display_name += ext
    else:
        url_basename = _Path(urlparse(request.url).path).name
        display_name = url_basename if url_basename else f"download{ext}"

    fd, temp_path_str = tempfile.mkstemp(suffix=ext, prefix="fichero_browser_save_")
    temp_path = _Path(temp_path_str)
    try:
        import os
        with os.fdopen(fd, "wb") as f:
            f.write(raw_bytes)

        package_path = _Path(db.path).parent
        doc = ingest_file(
            path=temp_path,
            mode=IngestMode.COPY,
            parent_id=request.parent_folder_id,
            extract_metadata=True,
            extract_text=True,
            save=True,
            db=db,
            package_path=package_path,
        )

        # Fix display name (ingest derives from temp filename)
        if doc.name != display_name:
            doc.name = display_name
            db.save(doc)

        # Tag with research context
        doc.metadata = {
            **(doc.metadata or {}),
            "source_url": request.url,
            "research_project_id": request.project_id,
            "content_type": content_type,
            "saved_at": datetime.now().isoformat(),
            **request.metadata,
        }
        db.save(doc)

        return BrowserSaveResponse(
            url=request.url,
            document_id=doc.id,
            document_name=doc.name,
            file_path=doc.path,
            content_type=content_type,
            size_bytes=len(raw_bytes),
            success=True,
            error=None,
        )
    except Exception as e:
        return BrowserSaveResponse(url=request.url, success=False, error=f"Import failed: {e}")
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass
