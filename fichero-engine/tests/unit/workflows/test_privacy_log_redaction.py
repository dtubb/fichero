from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from fichero.llm import LLMConfig
from fichero.workflows.tools.extract import _parse_json_response
from fichero.workflows.tools.classify_script import classify_script


def test_extract_parse_failure_logs_identifier_not_payload(caplog) -> None:
    caplog.set_level("WARNING")

    payload = "secret ssn 123-45-6789"
    result = _parse_json_response(payload, file_label="/tmp/private-page.png")

    assert result == {}
    assert "could not parse JSON from model output for /tmp/private-page.png" in caplog.text
    assert payload not in caplog.text


@pytest.mark.asyncio
async def test_classify_script_parse_failure_logs_identifier_not_payload(caplog) -> None:
    caplog.set_level("WARNING")

    raw = {
        "results": [
            {
                "file": "/tmp/private-page.png",
                "text": "secret diagnosis text",
            }
        ],
        "files": [],
        "documents": [],
        "value": None,
    }

    with patch(
        "fichero.workflows.tools.classify_script.process_vision",
        new=AsyncMock(return_value=raw),
    ):
        await classify_script(
            inputs={},
            state={"library_path": "/lib"},
            llm_config=LLMConfig(provider="openai", model="gpt-4o", api_key="test-key"),
        )

    assert "classify_script: could not parse JSON from model output for /tmp/private-page.png" in caplog.text
    assert "secret diagnosis text" not in caplog.text
