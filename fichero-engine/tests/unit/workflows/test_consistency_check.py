import pytest

from fichero.llm import LLMConfig
from fichero.workflows.registry import get_tool
from fichero.workflows.tools.consistency_check import consistency_check, find_inconsistencies


def test_consistency_check_flags_mismatched_sum_and_name_spelling():
    flags = find_inconsistencies("quinientos treinta por 3 = 1,500. Juan Pérez firmó. Juan Peres otorgó.")

    assert any(flag["type"] == "numeral" for flag in flags)
    assert any(flag["type"] == "name" for flag in flags)
    assert get_tool("consistency-check") is not None


def test_consistency_check_handles_grouped_figures_and_ignores_correct_arithmetic():
    flags = find_inconsistencies("1.200 × 3 = 3,500. 4 x 5 = 20.")

    assert len(flags) == 1
    assert flags[0]["type"] == "numeral"
    assert flags[0]["message"].endswith("expected 3600")


def test_consistency_check_normalizes_accents_and_only_adds_requested_formula_flags():
    text = "José García firmó. José Garcíá compareció. Ante mí, otorga y doy fe."

    assert find_inconsistencies(text) == [
        {
            "type": "name",
            "message": "Possible inconsistent name spelling: José García / José Garcíá",
        }
    ]
    assert find_inconsistencies(text, check_formula_completeness=True) == [
        {
            "type": "name",
            "message": "Possible inconsistent name spelling: José García / José Garcíá",
        }
    ]


@pytest.mark.asyncio
async def test_consistency_tool_uses_state_text_and_reports_formula_gaps():
    result = await consistency_check(
        {"check_formula_completeness": True},
        {"text": "Dos por 2 = 5"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] is None
    assert result["count"] == 4
    assert result["inconsistencies"][0] == {
        "type": "numeral",
        "message": "Dos por 2 = 5: expected 4",
    }
    assert {flag["message"] for flag in result["inconsistencies"][1:]} == {
        "Missing notarial formula marker: ante mi",
        "Missing notarial formula marker: otorga",
        "Missing notarial formula marker: doy fe",
    }
