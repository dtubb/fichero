"""A refused Start offers the fixes as typed buttons (`designer.budget.refusal-offers-the-fix`, #6295): raise the cap that
refuses (to the dollar), change the dearest step's model, run the first N pages that fit. The engine serves them."""
from __future__ import annotations

from fichero_server.recipes.cloud_cap import CapFix, CloudCapLine, fixes_for

EST = {"runs": [{"workflow": "translate", "cost_usd": 3.0}, {"workflow": "describe", "cost_usd": 9.5}, {"workflow": "free", "cost_usd": 0}]}


def test_a_run_that_is_not_over_offers_nothing():
    assert fixes_for({"over": False}, EST) == (None, [])


def test_a_monthly_refusal_offers_raise_change_and_fewer():
    line = {"over": True, "over_month": True, "needed_cap_usd": 12.35, "fewer_pages": 40}
    dearest, fixes = fixes_for(line, EST)
    assert dearest == "describe"
    assert fixes == [{"kind": "raise-cap", "cap": "monthly", "raise_to_usd": 13.0},
                     {"kind": "change-model", "step": "describe"},
                     {"kind": "run-fewer-pages", "pages_that_fit": 40}]
    assert all(CapFix(**f) for f in fixes)


def test_a_project_refusal_names_the_project_cap_and_no_fewer_pages_when_none_fit():
    line = {"over": True, "over_project": True, "needed_project_cap_usd": 6.0, "fewer_pages": None}
    _, fixes = fixes_for(line, EST)
    assert [f["kind"] for f in fixes] == ["raise-cap", "change-model"]
    assert fixes[0]["cap"] == "project" and fixes[0]["raise_to_usd"] == 6.0


def test_the_line_model_carries_both_fields():
    assert {"fixes", "dearest_step"} <= set(CloudCapLine.model_fields)
