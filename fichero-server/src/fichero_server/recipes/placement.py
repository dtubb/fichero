"""Where a step runs, by the project's scale (`source.recipe.placement-by-scale`, #5589).

A pure rule: about 100 or 1,000 pages run on this Mac; about 100,000 belong on a cluster, but only where the person
has allowed pages to leave and the project has bound a cluster to the step (`source.recipe.runs-on-binds-to-a-target`).
"""
from __future__ import annotations

#: Pages above which a step runs remotely, unless the plan sets another (the plan's to set).
PLACEMENT_THRESHOLD = 10_000


def place_step(pages: int, *, pages_may_leave: bool, bound_cluster: str | None,
               threshold: int = PLACEMENT_THRESHOLD) -> dict[str, str | None]:
    """`{place: this-mac|cluster, target, why}`: what the plan shows beside the step."""
    if pages <= threshold:
        return {"place": "this-mac", "target": None, "why": f"{pages:,} pages run well on this Mac"}
    if not pages_may_leave:
        return {"place": "this-mac", "target": None,
                "why": f"{pages:,} pages would suit a cluster, but pages may not leave this Mac"}
    if not bound_cluster:
        return {"place": "this-mac", "target": None,
                "why": f"{pages:,} pages would suit a cluster. No cluster is set up for this project"}
    return {"place": "cluster", "target": bound_cluster, "why": f"{pages:,} pages are more than this Mac should read"}
