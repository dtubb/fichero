"""Opt-in per-tool canned-invocation smoke over the live registry (#4326).

Every EXECUTABLE registered workflow tool (the #4322 palette contract —
``list_executable_tools``) gets one canned single invocation through the same
``tool(inputs=…, state=…, llm_config=…)`` call the graph builder makes:

- LLM-backed tools (``uses_llm``) run against the built-in deterministic
  ``mock`` provider (#1566) — the REAL dispatch path with a zero-cost model.
- Pure tools run for real against seeded fixture docs + a real fixture image.

The check is deliberately shallow: the invocation must return a dict without
raising and — outside the documented canned-input gaps below — without the
hard-abort ``error`` key (#839 contract: "error" aborts a workflow). It exists
so "tool exists in the palette but explodes on first invocation" can never
survive to a user, complementing scripts/verify_workflows.sh which runs whole
default workflows against a real on-device model.

Opt-in (the normal gate stays fast): skipped unless FICHERO_WORKFLOW_E2E=1.

Run:
    FICHERO_WORKFLOW_E2E=1 PYTHONPATH=fichero-server/src \
        .venv/bin/pytest fichero-server/tests/integration/test_workflow_tool_smoke.py -q
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from tests.fixture_paths import sample_file

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("FICHERO_WORKFLOW_E2E") != "1",
        reason="opt-in per-tool smoke: set FICHERO_WORKFLOW_E2E=1 to run (#4326)",
    ),
]

FIXTURE_TEXT = (
    "Regression Person signed the fixture deed in Regression Place in 1842."
)

# Tools whose canned single invocation is KNOWN not to complete cleanly with
# generic inputs (they need run-scoped context a lone invocation cannot fake:
# prior-node outputs, an MCP server, network/browser access, an interactive
# review answer, multiple configured providers, …). For these the bar is
# "invocation is survivable" — a dict result OR a clean typed error, never a
# crash of the process. Keep this list SHORT and justified; an entry here is
# a canned-input gap, not a licence for the tool to be broken in real
# workflows.
CANNED_INPUT_GAPS: dict[str, str] = {
    "agent": "needs a configured agent loop / chat context",
    "cli_agent": "needs an interactive CLI agent session",
    "mcp": "needs a live MCP server connection",
    "multi_agent": "needs a configured multi-agent ensemble",
    "sub_workflow": "needs a saved child workflow id in config (typed ValidationError)",
    "human_review": "pauses on a human-in-the-loop interrupt by design",
    "model_comparison": "needs >=2 configured providers to compare",
    "research_browser_navigate": "needs live browser/network access",
    "research_document_fetch": "needs live network access",
    "research_web_search": "needs a configured search provider",
    "agent_coordinator": "needs sub-agents declared in node config",
    "supervisor_agent": "needs worker agents declared in node config",
    "swarm_agent": "needs swarm agents declared in node config",
    "audio_transcribe": "needs the optional openai-whisper install",
    "organize_same_documents": "consumes upstream similarity clusters",
}


# Tools whose canonical input is a second shape than "one text file":
IMAGE_TOOLS_EXTRA = {"zoom", "recombine_segments", "segment_images", "split_images"}
PDF_TOOLS = {"split_chapters", "detect_structure", "book_structure", "book_index"}
PAIR_IMAGE_TOOLS = {"compare", "similarity"}  # require >= 2 images
FOLDER_TARGET_TOOLS = {"organize_same_documents", "summarize_folder", "folder"}


def _tool_names() -> list[str]:
    from fichero_server.workflows import registry as workflow_registry

    return sorted(t.name for t in workflow_registry.list_executable_tools())


@pytest.fixture(scope="module")
def smoke_library(tmp_path_factory) -> dict:
    """One seeded library + fixture docs shared by every tool invocation."""
    from tests.integration._seedlib import seed

    from fichero_server.db import db_manager
    from fichero_server.models import DocType, Document, FileType

    root = tmp_path_factory.mktemp("tool-smoke")
    library_path = root / "tool-smoke.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    image_src = sample_file("sample.jpg")
    image_path = root / "smoke-page.jpg"
    image_path.write_bytes(image_src.read_bytes())
    image_path_2 = root / "smoke-page-2.jpg"
    image_path_2.write_bytes(image_src.read_bytes())

    pdf_src = sample_file("multipage.pdf")
    pdf_path = root / "smoke-book.pdf"
    pdf_path.write_bytes(pdf_src.read_bytes())

    text_path = root / "smoke-note.txt"
    text_path.write_text(FIXTURE_TEXT, encoding="utf-8")

    output_dir = root / "smoke-output"
    output_dir.mkdir()

    folder = Document(
        id="tool-smoke-folder", name="Tool smoke folder", doc_type=DocType.folder
    )
    text_doc = Document(
        id="tool-smoke-text",
        parent_id=folder.id,
        name=text_path.name,
        path=str(text_path),
        doc_type=DocType.file,
        file_type=FileType.text,
        page_content=FIXTURE_TEXT,
    )
    image_doc = Document(
        id="tool-smoke-image",
        parent_id=folder.id,
        name=image_path.name,
        path=str(image_path),
        doc_type=DocType.file,
        file_type=FileType.image,
    )
    image_doc_2 = Document(
        id="tool-smoke-image-2",
        parent_id=folder.id,
        name=image_path_2.name,
        path=str(image_path_2),
        doc_type=DocType.file,
        file_type=FileType.image,
    )
    pdf_doc = Document(
        id="tool-smoke-pdf",
        parent_id=folder.id,
        name=pdf_path.name,
        path=str(pdf_path),
        doc_type=DocType.file,
        file_type=FileType.pdf,
    )
    for doc in (folder, text_doc, image_doc, image_doc_2, pdf_doc):
        db.save(doc)

    return {
        "library_path": library_path,
        "folder_id": folder.id,
        "collection_id": "test-collection",  # seeded by _seedlib.seed
        "text_doc": text_doc,
        "image_doc": image_doc,
        "image_doc_2": image_doc_2,
        "pdf_doc": pdf_doc,
        "image_path": image_path,
        "image_path_2": image_path_2,
        "pdf_path": pdf_path,
        "text_path": text_path,
        "output_dir": output_dir,
    }


def _canned_inputs(tool_def, smoke_library: dict) -> dict:
    """A generous canned input superset mirroring what real graphs pass."""
    name = tool_def.name
    is_vision = (
        tool_def.category in {"vision", "convert"}
        or "image" in name
        or name in IMAGE_TOOLS_EXTRA
    )
    if name in PDF_TOOLS:
        docs = [smoke_library["pdf_doc"]]
        paths = [smoke_library["pdf_path"]]
    elif name in PAIR_IMAGE_TOOLS:
        docs = [smoke_library["image_doc"], smoke_library["image_doc_2"]]
        paths = [smoke_library["image_path"], smoke_library["image_path_2"]]
    elif is_vision:
        docs = [smoke_library["image_doc"]]
        paths = [smoke_library["image_path"]]
    else:
        docs = [smoke_library["text_doc"]]
        paths = [smoke_library["text_path"]]

    selected = (
        [smoke_library["folder_id"]]
        if name in FOLDER_TARGET_TOOLS
        else [doc.id for doc in docs]
    )
    doc_payloads = [
        {"id": doc.id, "name": doc.name, "path": str(path)}
        for doc, path in zip(docs, paths)
    ]
    return {
        "selected_doc_ids": selected,
        "doc_ids": [doc.id for doc in docs],
        "documents": doc_payloads,
        "files": [str(path) for path in paths],
        "file_paths": [str(path) for path in paths],
        "text": FIXTURE_TEXT,
        "value": FIXTURE_TEXT,
        "texts": [FIXTURE_TEXT],
        "content": FIXTURE_TEXT,
        "records": [{"doc_id": docs[0].id, "text": FIXTURE_TEXT}],
        "context": None,
        "metadata": None,
        # Node config travels as inputs["_config"] on the real call path.
        "_config": {"output_dir": str(smoke_library["output_dir"])},
        # Agent-family tools take an explicit task; harmless elsewhere.
        "task": "Summarize the fixture text in one sentence.",
        # Container-scoped tools.
        "folder_id": smoke_library["folder_id"],
        "collection_id": smoke_library["collection_id"],
        # Sink tools.
        "output_dir": str(smoke_library["output_dir"]),
    }


@pytest.mark.parametrize("tool_name", _tool_names())
def test_registered_tool_survives_one_canned_invocation(
    tool_name: str,
    smoke_library: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows import registry as workflow_registry
    from fichero_server.workflows.runtime import build_initial_state

    tool_def = workflow_registry.get_tool_def(tool_name)
    assert tool_def is not None, f"executable tool {tool_name} has no ToolDef"
    tool_fn = workflow_registry.get_tool(tool_name)
    assert tool_fn is not None, f"executable tool {tool_name} has no implementation"

    # Keep the smoke hermetic: no vector writes, no similarity lookups.
    from fichero_server.db import Database

    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.find_similar", lambda *args, **kwargs: []
    )
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.index_entity", lambda *args, **kwargs: None
    )

    # Mocked model for LLM-backed tools: chat/chat_structured route through
    # the built-in deterministic ``mock`` provider (#1566). The VISION chat
    # path has no mock branch (``llm.vision`` falls through to LangChain and
    # raises "Unknown LLM provider: 'mock'" — see the #4326 lane notes), so
    # the vision-model seam is stubbed deterministically here instead.
    # JSON so structured consumers can parse it; text consumers (transcribe)
    # just treat the string as page text. similarity validates a strict
    # (extra="forbid") schema, so it gets its exact shape.
    if tool_name == "similarity":
        _mock_vision_text = (
            '{"overall_similarity": 0.9, "aspect_scores": [],'
            ' "most_similar": "1", "most_different": "2", "notes": "mock",'
            ' "same_document_clusters": [{"cluster_id": "c1",'
            ' "member_indexes": [0, 1], "similarity_score": 0.9}]}'
        )
    else:
        _mock_vision_text = '{"clusters": [], "groups": [], "text": "mock vision output"}'

    async def _mock_vision(images, prompt, config, **kwargs):
        return _mock_vision_text

    async def _mock_vision_batch(image_groups, prompt, config, **kwargs):
        return [_mock_vision_text for _ in image_groups]

    import sys as _sys

    import fichero_server.llm as _llm

    _real_vision = _llm.vision
    _real_vision_batch = _llm.vision_batch
    monkeypatch.setattr("fichero_server.llm.vision", _mock_vision)
    monkeypatch.setattr("fichero_server.llm.vision_batch", _mock_vision_batch)
    # Tool modules bind `from fichero_server.llm import vision` at import
    # time; rebind those names too so the seam holds everywhere.
    for module_name, module in list(_sys.modules.items()):
        if not module_name.startswith("fichero_server.workflows.tools"):
            continue
        if getattr(module, "vision", None) is _real_vision:
            monkeypatch.setattr(module, "vision", _mock_vision)
        if getattr(module, "vision_batch", None) is _real_vision_batch:
            monkeypatch.setattr(module, "vision_batch", _mock_vision_batch)

    inputs = _canned_inputs(tool_def, smoke_library)
    state = build_initial_state(
        {"selected_doc_ids": inputs["selected_doc_ids"]},
        library_path=str(smoke_library["library_path"]),
    )
    state["workflow_id"] = f"tool-smoke-{tool_name}"
    state["task_id"] = f"tool-smoke-{tool_name}"

    llm_config = LLMConfig(provider="mock", model="mock")

    async def invoke():
        return await asyncio.wait_for(
            tool_fn(inputs=inputs, state=state, llm_config=llm_config),
            timeout=120,
        )

    if tool_name in CANNED_INPUT_GAPS:
        # Documented canned-input gap: the invocation must be SURVIVABLE —
        # a dict result or a clean typed error, never a hang or a crash of
        # the harness. Timeouts still fail loudly.
        try:
            result = asyncio.run(invoke())
        except asyncio.TimeoutError:
            pytest.fail(f"{tool_name}: canned invocation hung past 120s")
        except Exception:
            return  # typed refusal on missing context is acceptable here
        assert isinstance(result, dict), (
            f"{tool_name}: tool contract is a dict result, got {type(result)!r}"
        )
        return

    result = asyncio.run(invoke())
    assert isinstance(result, dict), (
        f"{tool_name}: tool contract is a dict result, got {type(result)!r}"
    )
    error = result.get("error")
    assert not error, f"{tool_name}: canned invocation returned error: {error!r}"
