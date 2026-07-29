"""
Research Agent Tools

Workflow tools for systematic research using sandboxed web search, browser
navigation, and document fetch. These tools are the Layer 0 interface for
research agents — they expose the research agent sandbox tools (web search,
browser navigate, document fetch) as LangChain tools registered in the
workflow registry.

Unlike the FastAPI routes in research_agents.py (which are HTTP endpoints),
these tools call the underlying HTTP logic directly for use in LangGraph
workflows without HTTP overhead.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx

from fichero_server.security.url_security import is_internal_ip, is_safe_url
from fichero_server.workflows.types import State, PortDef, DataType
from fichero_server.workflows.registry import register_tool
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)
_ASYNCIO_FOR_TEST_COMPAT = asyncio

# Maximum allowed content size (10MB)
_MAX_CONTENT_SIZE = 10 * 1024 * 1024
_MAX_REDIRECTS = 5


async def _is_internal_ip(hostname: str | None) -> bool:
    return await is_internal_ip(hostname)


async def _is_safe_url(url: str, allow_userinfo: bool = False) -> tuple[bool, str]:
    return await is_safe_url(url, allow_userinfo=allow_userinfo)


async def _get_with_safe_redirects(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    max_redirects: int = _MAX_REDIRECTS,
) -> httpx.Response:
    """GET a URL while re-validating every redirect target against SSRF rules."""

    current_url = url
    current_params = params
    for _ in range(max_redirects + 1):
        is_safe, error_msg = await _is_safe_url(current_url)
        if not is_safe:
            raise ValueError(f"URL not allowed: {error_msg}")

        response = await client.get(
            current_url,
            headers=headers,
            params=current_params,
            follow_redirects=False,
        )
        if response.status_code not in (301, 302, 303, 307, 308):
            return response

        location = response.headers.get("location")
        if not location:
            return response
        response_url = getattr(response, "url", None)
        base_url = str(response_url) if isinstance(response_url, httpx.URL) else current_url
        current_url = urljoin(base_url, location)
        current_params = None

    raise ValueError(f"Redirect limit exceeded ({max_redirects})")


def _check_content_size(content: bytes | str, max_size: int = _MAX_CONTENT_SIZE) -> tuple[bool, str]:
    """Check if content size is within limits.

    Args:
        content: Content to check
        max_size: Maximum allowed size in bytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    if isinstance(content, str):
        size = len(content.encode("utf-8"))
    else:
        size = len(content)

    if size > max_size:
        return False, f"Content size {size} exceeds maximum {max_size}"

    return True, ""


async def _is_sandbox_violation(url: str) -> bool:
    """Check if URL violates sandbox constraints.

    DEPRECATED: Use _is_safe_url() instead for comprehensive validation.
    """
    is_safe, _ = await _is_safe_url(url)
    return not is_safe


# =============================================================================
# Web Search Tool
# =============================================================================


@register_tool(
    name="research_web_search",
    display_name="Web Search",
    description="Search the web using DuckDuckGo HTML (sandboxed). "
    "Returns title, URL, snippet, and relevance for each result.",
    category="research",
    icon="magnifyingglass",
    color="blue",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="query",
            name="Query",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Search query string",
        ),
    ],
    output_ports=[
        PortDef(
            id="results",
            name="Results",
            port_type="output",
            data_type=DataType.JSON,
            description="List of search results with title, url, snippet",
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Number of results returned",
        ),
        PortDef(
            id="query_out",
            name="Query",
            port_type="output",
            data_type=DataType.TEXT,
            description="The query that was executed",
        ),
        PortDef(
            id="execution_time_ms",
            name="Execution Time",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Time taken in milliseconds",
        ),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Maximum number of results to return",
            },
            "language": {
                "type": "string",
                "default": "en-us",
                "description": "DuckDuckGo language/region code (e.g., 'en-us', 'es-es')",
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 30,
                "minimum": 5,
                "maximum": 120,
                "description": "Request timeout in seconds",
            },
        },
    },
    sort_order=200,
)
async def research_web_search(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Execute a web search using DuckDuckGo HTML.

    Args:
        inputs: Must contain 'query'. Optional: 'max_results', 'language', 'timeout_seconds'.
        state: Workflow state (unused for web search).
        llm_config: Not used for this tool.

    Returns:
        Dict with results (list), count (int), query_out (str), execution_time_ms (int).
    """
    query = inputs.get("query", "").strip()
    if len(query) < 2:
        return {
            "results": [],
            "count": 0,
            "query_out": query,
            "execution_time_ms": 0,
            "error": "Search query must be at least 2 characters",
        }

    max_results = inputs.get("max_results", 10)
    language = inputs.get("language", "en-us")
    timeout_seconds = inputs.get("timeout_seconds", 30)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        ) as client:
            params = {"q": query, "kl": language}
            resp = await _get_with_safe_redirects(
                client,
                "https://html.duckduckgo.com/html/",
                params=params,
            )
            resp.raise_for_status()
            html = resp.text

    except httpx.TimeoutException:
        return {
            "results": [],
            "count": 0,
            "query_out": query,
            "execution_time_ms": int((time.monotonic() - start) * 1000),
            "error": "Web search timed out",
        }
    except httpx.HTTPStatusError as e:
        return {
            "results": [],
            "count": 0,
            "query_out": query,
            "execution_time_ms": int((time.monotonic() - start) * 1000),
            "error": f"Search provider error: {e.response.status_code}",
        }
    except Exception as e:
        return {
            "results": [],
            "count": 0,
            "query_out": query,
            "execution_time_ms": int((time.monotonic() - start) * 1000),
            "error": f"Web search failed: {str(e)}",
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Parse DuckDuckGo HTML results
    results: list[dict[str, Any]] = []
    link_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__url"[^>]*>(.*?)</a>.*?'
        r'<p[^>]+class="result__snippet"[^>]*>(.*?)</p>',
        re.DOTALL | re.IGNORECASE,
    )
    for i, match in enumerate(link_pattern.finditer(html)):
        if i >= max_results:
            break
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        url = match.group(2).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        # Validate search results using comprehensive security check
        if url:
            is_safe, _ = await _is_safe_url(url)
            if is_safe:
                results.append(
                    {
                        "title": title[:500] if title else "",
                        "url": url,
                        "snippet": snippet[:1000] if snippet else "",
                    }
                )

    logger.info(f"Web search '{query}': {len(results)} results in {elapsed_ms}ms")

    return {
        "results": results,
        "count": len(results),
        "query_out": query,
        "execution_time_ms": elapsed_ms,
    }


# =============================================================================
# Browser Navigate Tool
# =============================================================================


@register_tool(
    name="research_browser_navigate",
    display_name="Browser Navigate",
    description="Navigate to a URL and extract page content, title, and links. "
    "Sandboxed — only http/https URLs allowed.",
    category="research",
    icon="globe",
    color="blue",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="url",
            name="URL",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="URL to navigate to (http or https only)",
        ),
    ],
    output_ports=[
        PortDef(
            id="url",
            name="URL",
            port_type="output",
            data_type=DataType.TEXT,
            description="Final URL after redirects",
        ),
        PortDef(
            id="title",
            name="Title",
            port_type="output",
            data_type=DataType.TEXT,
            description="Page title",
        ),
        PortDef(
            id="html_content",
            name="HTML",
            port_type="output",
            data_type=DataType.TEXT,
            description="Extracted HTML content (truncated to 50k chars)",
        ),
        PortDef(
            id="extracted_links",
            name="Links",
            port_type="output",
            data_type=DataType.JSON,
            description="List of HTTP/HTTPS links found on the page",
        ),
        PortDef(
            id="execution_time_ms",
            name="Execution Time",
            port_type="output",
            data_type=DataType.NUMBER,
            description="Time taken in milliseconds",
        ),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "wait_for_selectors": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
                "description": "CSS selectors to wait for (not implemented yet — placeholder)",
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 30,
                "minimum": 5,
                "maximum": 120,
                "description": "Request timeout in seconds",
            },
        },
    },
    sort_order=201,
)
async def research_browser_navigate(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Navigate to a URL and extract page content.

    Args:
        inputs: Must contain 'url'. Optional: 'wait_for_selectors', 'timeout_seconds'.
        state: Workflow state (unused).
        llm_config: Not used for this tool.

    Returns:
        Dict with url, title, html_content, extracted_links, execution_time_ms.
    """
    url = inputs.get("url", "").strip()
    if not url:
        return {
            "url": "",
            "title": None,
            "html_content": None,
            "extracted_links": [],
            "execution_time_ms": 0,
            "error": "No URL provided",
        }

    if await _is_sandbox_violation(url):
        return {
            "url": url,
            "title": None,
            "html_content": None,
            "extracted_links": [],
            "execution_time_ms": 0,
            "error": "URL scheme not allowed in sandboxed browser (only http/https)",
        }

    # Comprehensive URL validation (SSRF protection)
    is_safe, error_msg = await _is_safe_url(url)
    if not is_safe:
        return {
            "url": url,
            "title": None,
            "html_content": None,
            "extracted_links": [],
            "execution_time_ms": 0,
            "error": f"URL not allowed: {error_msg}",
        }

    timeout_seconds = inputs.get("timeout_seconds", 30)

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=False,
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
            resp = await _get_with_safe_redirects(client, url, headers=headers)
            resp.raise_for_status()
            html_content = resp.text

    except httpx.TimeoutException:
        return {
            "url": url,
            "title": None,
            "html_content": None,
            "extracted_links": [],
            "execution_time_ms": int((time.monotonic() - start) * 1000),
            "error": "Browser navigation timed out",
        }
    except httpx.HTTPStatusError as e:
        return {
            "url": url,
            "title": None,
            "html_content": None,
            "extracted_links": [],
            "execution_time_ms": int((time.monotonic() - start) * 1000),
            "error": f"Navigation error: {e.response.status_code}",
        }
    except Exception as e:
        return {
            "url": url,
            "title": None,
            "html_content": None,
            "extracted_links": [],
            "execution_time_ms": int((time.monotonic() - start) * 1000),
            "error": f"Browser navigation failed: {str(e)}",
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)

    # Extract title
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

    logger.info(
        f"Browser navigate '{url}': title={title!r}, links={len(links)} in {elapsed_ms}ms"
    )

    return {
        "url": url,
        "title": title[:500] if title else None,
        "html_content": html_content[:50000] if html_content else None,
        "extracted_links": links[:100],
        "execution_time_ms": elapsed_ms,
    }


# =============================================================================
# Document Fetch Tool
# =============================================================================


@register_tool(
    name="research_document_fetch",
    display_name="Document Fetch",
    description="Fetch a document from a URL and optionally save as a Layer 1 Source "
    "in the Fichero database. Sandboxed — only http/https URLs allowed.",
    category="research",
    icon="doc.text",
    color="blue",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="url",
            name="URL",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="URL of the document to fetch",
        ),
        PortDef(
            id="project_id",
            name="Project ID",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Research project ID to save the source under",
        ),
    ],
    output_ports=[
        PortDef(
            id="url",
            name="URL",
            port_type="output",
            data_type=DataType.TEXT,
            description="Document URL",
        ),
        PortDef(
            id="title",
            name="Title",
            port_type="output",
            data_type=DataType.TEXT,
            description="Document title extracted from HTML or URL",
        ),
        PortDef(
            id="content",
            name="Content",
            port_type="output",
            data_type=DataType.TEXT,
            description="Document content (truncated to 50k chars)",
        ),
        PortDef(
            id="content_type",
            name="Content Type",
            port_type="output",
            data_type=DataType.TEXT,
            description="HTTP content-type header",
        ),
        PortDef(
            id="source_id",
            name="Source ID",
            port_type="output",
            data_type=DataType.TEXT,
            description="Fichero Source ID if created",
        ),
        PortDef(
            id="success",
            name="Success",
            port_type="output",
            data_type=DataType.BOOLEAN,
            description="Whether fetch succeeded",
        ),
        PortDef(
            id="error",
            name="Error",
            port_type="output",
            data_type=DataType.TEXT,
            description="Error message if failed",
        ),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "create_as_source": {
                "type": "boolean",
                "default": True,
                "description": "Whether to save the document as a Layer 1 Source in Fichero",
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 60,
                "minimum": 5,
                "maximum": 120,
                "description": "Request timeout in seconds",
            },
        },
    },
    sort_order=202,
)
async def research_document_fetch(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Fetch a document from a URL and optionally save as a Layer 1 Source.

    Args:
        inputs: Must contain 'url' and 'project_id'. Optional: 'create_as_source',
                'timeout_seconds'.
        state: Workflow state (used for library_path if creating a Source).
        llm_config: Not used for this tool.

    Returns:
        Dict with url, title, content, content_type, source_id, success, error.
    """
    url = inputs.get("url", "").strip()
    project_id = inputs.get("project_id", "").strip()

    if not url:
        return {
            "url": "",
            "title": None,
            "content": None,
            "content_type": None,
            "source_id": None,
            "success": False,
            "error": "No URL provided",
        }

    if await _is_sandbox_violation(url):
        return {
            "url": url,
            "title": None,
            "content": None,
            "content_type": None,
            "source_id": None,
            "success": False,
            "error": "URL scheme not allowed in sandboxed fetch (only http/https)",
        }

    # Comprehensive URL validation (SSRF protection)
    is_safe, error_msg = await _is_safe_url(url)
    if not is_safe:
        return {
            "url": url,
            "title": None,
            "content": None,
            "content_type": None,
            "source_id": None,
            "success": False,
            "error": f"URL not allowed: {error_msg}",
        }

    create_as_source = inputs.get("create_as_source", True)
    timeout_seconds = inputs.get("timeout_seconds", 60)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=False,
        ) as client:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                ),
            }
            resp = await _get_with_safe_redirects(client, url, headers=headers)
            resp.raise_for_status()
            content = resp.text
            content_type = resp.headers.get("content-type", "text/plain")

            # Extract title from HTML or use URL
            if "text/html" in content_type:
                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL
                )
                title = title_match.group(1).strip() if title_match else url
                title = re.sub(r"<[^>]+>", "", title).strip()
            else:
                title = url.split("/")[-1][:255]

    except httpx.TimeoutException:
        return {
            "url": url,
            "title": None,
            "content": None,
            "content_type": None,
            "source_id": None,
            "success": False,
            "error": "Fetch timed out",
        }
    except Exception as e:
        return {
            "url": url,
            "title": None,
            "content": None,
            "content_type": None,
            "source_id": None,
            "success": False,
            "error": f"Fetch failed: {str(e)}",
        }

    # Optionally create a Layer 1 Source document
    source_id = None
    if create_as_source and project_id:
        library_path = state.get("library_path")
        if library_path:
            try:
                from fichero_server.db import db_manager
                from fichero_server.models import Document, DocType

                db = db_manager.get_database(library_path)
                doc = Document(
                    name=title[:255] if title else url,
                    # #2507: the old value was a non-existent DocType member —
                    # this save always raised AttributeError (logged, but the
                    # source was never created). A web page is a file-type doc.
                    doc_type=DocType.file,
                    path=url,
                    page_content=content[:50000],
                    metadata={
                        "source_url": url,
                        "content_type": content_type,
                        "research_project_id": project_id,
                        "fetched_at": datetime.now().isoformat(),
                    },
                )
                db.save(doc)
                source_id = doc.id
                logger.info(f"Document fetch '{url}': created source {source_id}")
            except Exception as e:
                # Don't fail the fetch if save fails
                logger.warning(f"Document fetch '{url}': failed to save source: {e}")

    logger.info(f"Document fetch '{url}': title={title!r}, source_id={source_id}")

    return {
        "url": url,
        "title": title[:500] if title else None,
        "content": content[:50000] if content else None,
        "content_type": content_type,
        "source_id": source_id,
        "success": True,
        "error": None,
    }
