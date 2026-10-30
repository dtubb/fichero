"""The cloud spend caps on the Start plan, and the plan's pricing they share (#6295, `ai.where.cloud-spend-cap`): the models of
the plan's cap line and of the change, the cap's one refusal, the first pages in Finder order and the estimate over a set of pages. Moved out of
`api/routes/system/recipes.py`, which is over a thousand lines; the route that changes the caps is `recipe_cloud_cap.py`."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CloudCapChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cap_usd: Optional[float] = Field(default=None, ge=0, description=(
        "the most the project's cloud calls may cost a month, in US$ (0 is a cap); left out: unchanged"))
    project_cap_usd: Optional[float] = Field(default=None, ge=0, description=(
        "the most the project may spend on cloud calls in all, across months (`answers.cloud_project_cap_usd`); "
        "left out: unchanged"))
    clear_project_cap: bool = Field(default=False, description="remove the project's total cap (no such limit)")

    @model_validator(mode="after")
    def _says_something(self) -> "CloudCapChange":
        if self.cap_usd is None and self.project_cap_usd is None and not self.clear_project_cap:
            raise ValueError("send the monthly cap, the project cap, or clear_project_cap")
        if self.project_cap_usd is not None and self.clear_project_cap:
            raise ValueError("a project cap is set or cleared, not both")
        return self


class CloudCapChanged(BaseModel):
    cap_usd: float = Field(description="the project's monthly cloud cap now")
    project_cap_usd: Optional[float] = Field(default=None, description="the project's total cloud cap now; null: none")
    audit_id: str = Field(description="the audit row of the change; Undo reverses it")


class CloudCapLine(BaseModel):
    """The project's cloud spend cap against this run's estimate (`ai.where.cloud-spend-cap`, #5943, #5987)."""

    cap_usd: float = Field(description="the project's cloud spending cap for a month (`answers.cloud_spend_cap_usd`), US$10 unless set")
    spent_usd: float = Field(description="what its cloud calls have cost this (UTC) month, assumed prices included")
    remaining_usd: float = Field(description="what the cap leaves this month")
    estimate_usd: Optional[float] = Field(default=None, description="this run's estimated cloud cost; null when a model has no listed price")
    over: bool = Field(description="the estimate is more than the cap leaves: Start asks first")
    over_month: bool = Field(default=False, description="the estimate is more than the monthly cap leaves")
    over_project: bool = Field(default=False, description="the estimate is more than the project's total cap leaves")
    needed_cap_usd: Optional[float] = Field(default=None, description=(
        "when `over_month`: the monthly cap under which this run's estimate fits (what is booked this month plus the estimate, "
        "to the cent, no margin); Set Up offers it as \"Raise the cap to N\" (#6295); null otherwise"))
    project_cap_usd: Optional[float] = Field(default=None, description=(
        "the most the project may spend on cloud calls in all (`answers.cloud_project_cap_usd`); null: no such limit"))
    project_spent_usd: float = Field(default=0.0, description="what its cloud calls have cost in all, across months")
    project_remaining_usd: Optional[float] = Field(default=None, description=(
        "what the project's total cap leaves, `project_cap_usd` less `project_spent_usd`, not below 0; null: no total cap"))
    refusal: Optional[str] = Field(default=None, description=(
        "when `over`: the sentence this cap adds to the plan's `refusals`, exactly, so a client can tell which refusal is the cap's "
        "without reading its words; null otherwise"))
    needed_project_cap_usd: Optional[float] = Field(default=None, description=(
        "when `over_project`: the project cap under which this run's estimate fits (spent in all plus the estimate, to the cent)"))
    pages: int = Field(default=0, description="the pages the estimate is for")
    fewer_pages: Optional[int] = Field(default=None, description=(
        "when `over`: how many of the project's first pages, in Finder order, fit what the caps leave at this run's per-page "
        "estimate; null when none fit or the run is not over"))
    unpriced_models: list[str] = Field(default_factory=list, description=(
        "`provider/model` of cloud models in this plan with no listed price that the project has not accepted: listed apart, "
        "counted at an assumed price per call; pressing Start accepts them (`cloud.accept_unpriced`), never a refusal (#6259)"))
    note: Optional[str] = Field(default=None, description=(
        "one sentence naming the unpriced models and the assumed price per call they are counted at; null when there are none"))
    unpriced: bool = Field(description="the estimate is unknown (a cloud model with no listed price): asked about, never $0")
    assumed_calls: int = Field(default=0, description="calls this month booked at the assumed price of a model with no listed price")
    assumed_usd: float = Field(default=0.0, description="what those calls were booked at: counted against the cap, listed apart")


def only_if_set(**named: Any) -> dict[str, Any]:
    """The keyword arguments that were given: `_start_plan` is called with `first_pages` only for a first-pages run."""
    return {key: value for key, value in named.items() if value is not None}


def first_pages_of(db: Any, count: int) -> list[str]:
    """The first `count` pages of the project in Finder order (the order a run reads them in, #5849): what "run fewer pages"
    runs (#6295)."""
    from fichero_server.recipes.done import pages_for

    return pages_for(db, {}, None)[:count]


def cap_refusals(plan: dict) -> None:
    """The cap's one refusal: an estimate over what the cap leaves, asked before the run, not after the money is gone (#5987).
    A model with no listed price never refuses (#6259): the cap line lists it apart at the assumed price, and Start is the yes."""
    line = plan["cloud_cap"]
    if not line["over"]:
        return
    said = [f"This run is estimated at US${line['estimate_usd']:,.2f} of cloud spending"]
    if line["over_month"]:
        said.append(f"more than the US${line['remaining_usd']:,.2f} your project's monthly cap leaves this month "
                    f"(cap US${line['cap_usd']:,.2f} a month). Raise the monthly cap to US${line['needed_cap_usd']:,.2f}")
    if line["over_project"]:
        said.append(f"more than the US${line['project_remaining_usd']:,.2f} your project's total cap leaves (cap US${line['project_cap_usd']:,.2f} "
                    f"in all). Raise the project cap to US${line['needed_project_cap_usd']:,.2f}")
    fewer = f", or run the first {line['fewer_pages']} pages" if line.get("fewer_pages") else ", or run fewer pages"
    line["refusal"] = ", ".join(said[:1]) + ": " + "; and ".join(said[1:]) + f"{fewer}, or choose a cheaper model."
    plan["refusals"] = [*plan["refusals"], line["refusal"]]


def first_pages_that_fit(db: Any, plan: dict[str, Any], line: dict[str, Any], pages: int, price: Callable[[set[str]], dict[str, Any]]) -> Optional[int]:
    """The most first pages (Finder order) whose own estimate, priced as the plan prices it (only what each step has still to
    do, review passes by their lines), fits what the caps leave; None when not even one page does. Found by halving, since the
    price only grows with the pages; the price is the plan's best estimate, no margin (#6295). `price(pages)` is the plan's own
    estimate over those pages (`recipes._estimate_on`)."""
    left = [line["remaining_usd"]]
    if line["project_remaining_usd"] is not None:
        left.append(line["project_remaining_usd"])
    room = min(left)
    first = first_pages_of(db, pages)

    def fits(count: int) -> bool:
        cost = price(set(first[:count]))["total_cost_usd"]
        return cost is not None and cost <= room + 1e-9

    low, high = 0, len(first) - 1  # `low` fits (no page costs nothing); the whole run does not
    while low < high:
        middle = (low + high + 1) // 2
        low, high = (middle, high) if fits(middle) else (low, middle - 1)
    return low or None


def lines_known(db: Any, workflows: list[dict[str, Any]], page_ids: list[str]) -> dict[str, Any] | None:
    """What the project already holds of Kraken's lines, for pricing a run that sends only the unsure ones (variant A);
    None when no run has a bar, so no plan pays for the scan."""
    from fichero_server.recipes.done import kraken_lines_known
    from fichero_server.recipes.start import certainty_bar

    has_bar = any(certainty_bar(w) is not None for w in workflows if w.get("job") == "correct")
    return kraken_lines_known(db, page_ids) if has_bar else None


def catalogue_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The plan's Catalogue runs, priced by `estimate` (one call a folder, before Start)."""
    return [r for r in runs if r.get("card") == "catalogue"]


def folders_covering(db: Any, page_ids: list[str]) -> int:
    """How many folders a Catalogue run over these pages describes (each folder above them, once; those already described are not priced)."""
    from fichero_server.recipes.catalogue_step import folders_to_describe

    return len(folders_to_describe(db, page_ids)[0]) if page_ids else 0


def estimate_on(db: Any, plan: dict[str, Any], pages: dict[str, Any], within: set[str] | None, memo: dict) -> dict[str, Any]:
    """The plan's estimate over `pages` (`done.material` of `within`): each run priced on the pages it has still to do, the
    review passes on their lines, the Catalogue step on its folders. The one pricing Start's plan and "run fewer pages" share."""
    from fichero_server.recipes.done import todo_counts
    from fichero_server.recipes.start import estimate

    return estimate(plan["workflows"], pages["pages"], lines_known(db, plan["workflows"], pages["ids"]),
                    catalogue=catalogue_runs(plan["runs"]), folders=folders_covering(db, pages["ids"]),
                    todo=todo_counts(db, plan, within, memo=memo))
