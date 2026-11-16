"""`designer.budget.beside-the-estimate` (#6295): the plan's cloud line carries both caps, what is spent and left, and the run cap
Start proposes (the estimate, no margin). The Budget block is read from it; the app works out none of it."""
from __future__ import annotations

from fichero_server.llm import spend
from fichero_server.recipes.cloud_cap import CloudCapLine


def _library(tmp_path) -> str:
    (tmp_path / "P.fichero" / "recipe").mkdir(parents=True)
    (tmp_path / "P.fichero" / "recipe" / "setup.yaml").write_text("cloud_spend_cap_usd: 20\ncloud_project_cap_usd: 50\n")
    return str(tmp_path / "P.fichero")


def test_the_line_carries_both_caps_what_is_left_and_the_proposed_run_cap(tmp_path):
    library = _library(tmp_path)
    spend._book(library, 5.0)
    line = spend.plan_line(library, estimate_usd=3.456, pages=30)
    assert (line["cap_usd"], line["remaining_usd"]) == (20.0, 15.0)
    assert (line["project_cap_usd"], line["project_remaining_usd"]) == (50.0, 45.0)
    assert line["proposed_run_cap_usd"] == 3.46  # the estimate itself, no margin
    CloudCapLine(**line, fixes=[])


def test_an_unknown_or_free_estimate_proposes_no_run_cap(tmp_path):
    library = _library(tmp_path)
    assert spend.plan_line(library, estimate_usd=None)["proposed_run_cap_usd"] is None
    assert spend.plan_line(library, estimate_usd=0.0)["proposed_run_cap_usd"] is None
