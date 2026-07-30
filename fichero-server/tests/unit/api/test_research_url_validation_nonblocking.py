"""Regression tests for async/non-blocking SSRF URL validation (#461)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero_server.api.routes.research import tools as api_research_tools
from fichero_server.workflows.tools import research as workflow_research


@pytest.mark.asyncio
async def test_api_route_url_validation_offloads_dns_lookup_to_thread(monkeypatch):
    to_thread = AsyncMock(return_value=[(None, None, None, None, ("93.184.216.34", 0))])
    monkeypatch.setattr(api_research_tools.asyncio, "to_thread", to_thread)

    safe, error = await api_research_tools._is_safe_url("https://example.com/path")
    assert safe is True
    assert error == ""
    to_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_tool_url_validation_offloads_dns_lookup_to_thread(monkeypatch):
    to_thread = AsyncMock(return_value=[(None, None, None, None, ("93.184.216.34", 0))])
    monkeypatch.setattr(workflow_research.asyncio, "to_thread", to_thread)

    safe, error = await workflow_research._is_safe_url("https://example.com/path")
    assert safe is True
    assert error == ""
    to_thread.assert_awaited_once()

