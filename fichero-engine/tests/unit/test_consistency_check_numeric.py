from fichero.workflows.tools.consistency_check import find_inconsistencies


def test_consistency_check_flags_numeric_and_missing_formula_markers() -> None:
    flags = find_inconsistencies("12 x 4 = 47", check_formula_completeness=True)

    assert {flag["type"] for flag in flags} == {"numeral", "formula"}
    assert any("expected 48" in flag["message"] for flag in flags)
    assert len([flag for flag in flags if flag["type"] == "formula"]) == 3
