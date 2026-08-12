"""Vision calls record episodes (2026-08-12): the ledger's first live wire.

process_vision's save seam records one training-grade episode per model
exchange — prompt, raw output, thinking, model identity, page/document
subject — under the library the builder put in context. The text-format
passthrough returns BEFORE the seam, so reading a .md file records
nothing (a passthrough is not a model call).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.observability import episodes
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision


def _tool_config() -> VisionToolConfig:
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=False,
        trigger_embedding=False,
        supports_apple_vision=True,
    )


def _ledger(package: Path) -> list[dict]:
    files = sorted((package / "episodes").glob("*.jsonl"))
    rows: list[dict] = []
    for f in files:
        rows += [json.loads(line) for line in f.read_text().splitlines() if line]
    return rows


@pytest.mark.asyncio
async def test_llm_vision_call_records_an_episode(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfakebytes")
    package = tmp_path / "lib.fichero"
    package.mkdir()

    lib_token = episodes.set_library(str(package))
    run_token = episodes.set_run_context(
        {"thread_id": "t-1", "workflow_id": "wf", "node": "transcribe"}
    )
    try:
        with (
            patch(
                "fichero_server.workflows.tools.vision_base.save_artifact",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "fichero_server.llm.vision",
                new=AsyncMock(return_value="transcribed words"),
            ),
        ):
            result = await process_vision(
                files=[str(image)],
                documents=[],
                prompt="Transcribe this page.",
                llm_config=LLMConfig(provider="mock", model="mock-vl"),
                library_path="",  # no db writes; the ledger context is separate
                task_id=None,
                tool_config=_tool_config(),
                vision_mode="llm",
            )
    finally:
        episodes.set_run_context(None)
        episodes.set_library(None)
        _ = (lib_token, run_token)

    assert "transcribed words" in result["text"]
    rows = _ledger(package)
    assert len(rows) == 1, f"expected one episode, got {len(rows)}"
    row = rows[0]
    assert row["kind"] == "model_call"
    assert row["run"]["node"] == "transcribe"
    assert row["exchange"]["prompt"].startswith("Transcribe")
    assert row["exchange"]["output"] == "transcribed words"
    assert row["model"]["use_case"] == "transcription"
    assert row["subject"]["file"].endswith("scan.png")


@pytest.mark.asyncio
async def test_text_passthrough_records_no_episode(tmp_path: Path) -> None:
    md = tmp_path / "notes.md"
    md.write_text("# Heading\n\nBody.\n", encoding="utf-8")
    package = tmp_path / "lib.fichero"
    package.mkdir()

    episodes.set_library(str(package))
    try:
        with patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ):
            await process_vision(
                files=[str(md)],
                documents=[],
                prompt="Transcribe this page.",
                llm_config=LLMConfig(provider="mock", model="mock-vl"),
                library_path="",
                task_id=None,
                tool_config=_tool_config(),
                vision_mode="llm",
            )
    finally:
        episodes.set_library(None)

    assert not (package / "episodes").exists(), "passthrough is not a model call"


@pytest.mark.asyncio
async def test_thread_episodes_endpoint_returns_run_records(client, db):
    """GET /threads/{id}/episodes — the per-node inspection surface."""
    from pathlib import Path as _Path

    library = str(_Path(str(db.path)).parent)
    lib_token = episodes.set_library(library)
    run_token = episodes.set_run_context(
        {"thread_id": "t-ep-1", "workflow_id": "wf", "node": "transcribe"}
    )
    try:
        episodes.record(
            subject={"document_id": "doc-1"},
            model={"provider": "mock", "model": "m", "use_case": "transcription"},
            exchange={"prompt": "p", "output": "o", "thinking": "t"},
        )
        episodes.set_run_context(
            {"thread_id": "OTHER", "workflow_id": "wf", "node": "transcribe"}
        )
        episodes.record(exchange={"prompt": "not ours"})
    finally:
        episodes.set_run_context(None)
        episodes.set_library(None)
        _ = (lib_token, run_token)

    r = client.get("/api/workflow-execution/threads/t-ep-1/episodes")
    assert r.status_code == 200
    payload = r.json()
    assert payload["count"] == 1
    record = payload["episodes"][0]
    assert record["run"]["node"] == "transcribe"
    assert record["exchange"]["thinking"] == "t"
