"""Owner ruling 2026-10-25 (#6127): when the hosted reader fails on a page it is retried with backoff (the one retry layer,
`ai.where.one-retry-policy`, #5944), then the page is FAILED, with no text for it: Kraken's text is never put in its place.

Driven through `process_vision` and the real `call_with_breaker`; only the provider's call, the sleep and the writers are
stubbed. The tool writes page text (`update_page_content=True`), so "no text" is what the failure path does, not the setting;
the same run with an answer is the control that proves the writers would have been called.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.circuit_breaker import DEFAULT_MAX_RETRIES
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision
from tests.unit.workflows.test_parallel_fanout_no_semaphore_deadlock import _fresh_vision_semaphore  # noqa: F401 -- autouse

MODULE = "fichero_server.workflows.tools.vision_base"


async def _read(tmp_path, vision, test_package, db):
    """A real page document in a real database: its text is read back, so "nothing written" is observed, not assumed.
    Returns (process_vision's outcome, the page as stored afterwards)."""
    image = tmp_path / "page.png"
    image.write_bytes(b"\x89PNG stub")
    page = Document(name="page.png", doc_type=DocType.file, file_type=FileType.image, path=str(image))
    db.save(page)
    with (
        patch(f"{MODULE}.file_to_data_uri", return_value="data:image/png;base64,AAAA"),
        patch("fichero_server.llm.vision", new=vision),
    ):
        outcome = await process_vision(
            files=[str(image)], documents=[page.model_dump(mode="json")], prompt="Read.",
            llm_config=LLMConfig(provider="openai", model="gpt-4o", api_key="k"), library_path=test_package, task_id=None,
            tool_config=VisionToolConfig(artifact_type="transcription", update_page_content=True, trigger_embedding=False,
                                         supports_apple_vision=True),
            vision_mode="llm")
    return outcome, db.get(Document, page.id), db.query(Artifact, document_id=page.id)


@pytest.mark.asyncio
async def test_a_hosted_call_that_fails_every_try_is_retried_with_backoff_then_the_page_is_failed(
        tmp_path, monkeypatch, test_package, db):
    waits: list[float] = []

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(cb.asyncio, "sleep", fake_sleep)
    vision = AsyncMock(side_effect=RuntimeError("429 Too Many Requests"))
    result, page, artifacts = await _read(tmp_path, vision, test_package, db)
    assert vision.await_count == 1 + DEFAULT_MAX_RETRIES  # the first try and every retry, no more (5)
    assert len(waits) == DEFAULT_MAX_RETRIES and waits == sorted(waits) and waits[-1] > waits[0]  # backing off
    assert result["results"][0]["error"]  # the page failed, with its reason
    assert not any(result.get("texts") or [])
    assert not page.page_content and not list(artifacts)  # and nothing was written for it: no page text, no artifact


@pytest.mark.asyncio
async def test_control_the_same_read_with_an_answer_does_write(tmp_path, test_package, db):
    """Without this the test above could pass because the writers are never reached at all."""
    result, page, artifacts = await _read(tmp_path, AsyncMock(return_value="Yten dixo el testigo"), test_package, db)
    assert "error" not in result["results"][0]
    assert page.page_content == "Yten dixo el testigo" and list(artifacts)
