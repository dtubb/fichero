from fichero.workflows.registry import get_tool
from fichero.workflows.tools.consistency_check import find_inconsistencies


def test_consistency_check_flags_mismatched_sum_and_name_spelling():
    flags = find_inconsistencies("quinientos treinta por 3 = 1,500. Juan Pérez firmó. Juan Peres otorgó.")

    assert any(flag["type"] == "numeral" for flag in flags)
    assert any(flag["type"] == "name" for flag in flags)
    assert get_tool("consistency-check") is not None
