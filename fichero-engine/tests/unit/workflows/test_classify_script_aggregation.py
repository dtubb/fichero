"""Unit tests for classify_script aggregation behaviour.

#2237 — mixed/multi-page selections were collapsed to the single
highest-confidence script_type.  A batch whose pages have distinct
types must now surface script_type="mixed" so downstream routing
can handle them explicitly rather than silently applying one branch
to all items.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, patch

from fichero.llm import LLMConfig
from fichero.workflows.tools.classify_script import classify_script

_LLM = LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


def _raw_result_for(*script_types_and_confidences):
    """Build the fake ``raw`` dict that process_vision would return."""
    results = []
    for index, (stype, conf) in enumerate(script_types_and_confidences):
        results.append({
            "file": f"page-{index + 1}.png",
            "document_id": f"page-{index + 1}",
            "text": json.dumps({
                "script_type": stype,
                "confidence": conf,
                "notes": "",
            }),
        })
    return {
        "results": results,
        "files": [],
        "documents": [],
        "value": None,
    }


@pytest.mark.asyncio
async def test_uniform_batch_keeps_its_script_type():
    """#2237: a batch where all items agree must keep the agreed type (not "mixed")."""
    raw = _raw_result_for(("htr", 0.85), ("htr", 0.90))

    with patch(
        "fichero.workflows.tools.classify_script.process_vision",
        new=AsyncMock(return_value=raw),
    ):
        result = await classify_script(
            inputs={},
            state={"library_path": "/lib"},
            llm_config=_LLM,
        )

    assert result["script_type"] == "htr", (
        "uniform htr batch must return script_type='htr', not 'mixed'"
    )
    assert result["confidence"] == 0.90, "confidence should be the max across the batch"
    assert not result["needs_human_selection"], "high-confidence uniform batch must not need human"


@pytest.mark.asyncio
async def test_mixed_batch_surfaces_mixed_type():
    """#2237: a batch with different script_types must return script_type='mixed'.

    Before the fix, the highest-confidence item ('htr', 0.9) silently won,
    causing all pages to be routed to the HTR branch even though some are
    typescript.
    """
    raw = _raw_result_for(("htr", 0.90), ("typescript", 0.80))

    with patch(
        "fichero.workflows.tools.classify_script.process_vision",
        new=AsyncMock(return_value=raw),
    ):
        result = await classify_script(
            inputs={},
            state={"library_path": "/lib"},
            llm_config=_LLM,
        )

    assert result["script_type"] == "mixed", (
        "#2237: mixed batch must surface script_type='mixed', not one dominant type"
    )
    assert result["needs_human_selection"] is True, (
        "#2237: mixed batch must always set needs_human_selection=True"
    )
    # Per-item data must still be present for the caller
    profiles = result["value"]["profiles"]
    assert len(profiles) == 2, "both per-item profiles must be preserved"
    types_in_profiles = {p["script_type"] for p in profiles}
    assert types_in_profiles == {"htr", "typescript"}, "both types must appear in profiles"
    assert [profile["document_id"] for profile in profiles] == ["page-1", "page-2"]


@pytest.mark.asyncio
async def test_mixed_batch_three_types():
    """#2237: three-type batch must also surface 'mixed'."""
    raw = _raw_result_for(("typescript", 0.95), ("htr", 0.80), ("paleography", 0.70))

    with patch(
        "fichero.workflows.tools.classify_script.process_vision",
        new=AsyncMock(return_value=raw),
    ):
        result = await classify_script(
            inputs={},
            state={"library_path": "/lib"},
            llm_config=_LLM,
        )

    assert result["script_type"] == "mixed", "#2237: three-type batch must be 'mixed'"
    assert result["needs_human_selection"] is True


@pytest.mark.asyncio
async def test_empty_batch_returns_safe_defaults():
    """Edge: empty results list must not crash and must return safe defaults."""
    raw = {"results": [], "files": [], "documents": [], "value": None}

    with patch(
        "fichero.workflows.tools.classify_script.process_vision",
        new=AsyncMock(return_value=raw),
    ):
        result = await classify_script(
            inputs={},
            state={"library_path": "/lib"},
            llm_config=_LLM,
        )

    assert result["script_type"] == "manuscript", "empty batch must fall back to 'manuscript'"
    assert result["value"]["profiles"] == [], "empty batch must have empty profiles list"


@pytest.mark.asyncio
async def test_low_confidence_uniform_batch_needs_human():
    """Low-confidence uniform batch must set needs_human_selection regardless of type."""
    raw = _raw_result_for(("manuscript", 0.45), ("manuscript", 0.50))

    with patch(
        "fichero.workflows.tools.classify_script.process_vision",
        new=AsyncMock(return_value=raw),
    ):
        result = await classify_script(
            inputs={},
            state={"library_path": "/lib"},
            llm_config=_LLM,
        )

    assert result["script_type"] == "manuscript"
    assert result["needs_human_selection"] is True, (
        "confidence 0.50 < threshold 0.6 must trigger needs_human_selection"
    )
