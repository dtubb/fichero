"""Coverage for the classify-text workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import classify_text as tool


def test_prompt_builder_supports_single_and_multi_label_modes():
    single = tool.build_classify_text_prompt({"categories": ["letter", "invoice"]})
    multi = tool.build_classify_text_prompt(
        {"categories": ["letter", "invoice"], "multi_label": True}
    )

    assert "exactly ONE category" in single
    assert "letter, invoice" in single
    assert "one or more categories" in multi
    assert '"categories"' in multi


def test_prompt_builder_uses_default_categories():
    prompt = tool.build_classify_text_prompt({})

    assert all(category in prompt for category in tool.DEFAULT_CATEGORIES)


def test_classify_forwards_inputs_to_process_text(monkeypatch):
    calls = []

    async def fake_process_text(**kwargs):
        calls.append(kwargs)
        return {"classification": "letter"}

    monkeypatch.setattr(tool, "process_text", fake_process_text)
    inputs = {
        "text": "A letter",
        "categories": ["letter", "invoice"],
        "multi_label": True,
        "documents": ["doc-1"],
        "context": "archive",
        "metadata": {"page": 1},
        "temperature": 0.4,
        "save_to_db": False,
        "save_to_file": True,
    }

    result = asyncio.run(tool.classify_text(inputs, {"library_path": "/tmp/lib", "task_id": "task-1"}, object()))

    assert result == {"classification": "letter"}
    assert calls[0]["output_format"] == "json"
    assert calls[0]["reference_values"] == {"category": ["letter", "invoice"]}
    assert calls[0]["library_path"] == "/tmp/lib"
    assert calls[0]["task_id"] == "task-1"
    assert calls[0]["save_to_db"] is False
    assert calls[0]["save_to_file_flag"] is True


def test_classify_uses_explicit_prompt_and_choice_output(monkeypatch):
    captured = {}

    async def fake_process_text(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(tool, "process_text", fake_process_text)

    asyncio.run(
        tool.classify_text(
            {
                "text": "memo",
                "prompt": "custom prompt",
                "categories": ["memo"],
                "output_format": "choice",
                "reference_values": {"category": ["memo"]},
            },
            {},
            object(),
        )
    )

    assert captured["prompt"] == "custom prompt"
    assert captured["output_format"] == "choice"
