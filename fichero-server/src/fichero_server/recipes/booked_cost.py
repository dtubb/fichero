"""The estimate learns from what the project has booked (`designer.budget.estimate-from-booked-usage`, #6294): once calls of the same model
and job are booked on the page jobs' rows, the per-page figure is the median booked cost a page, labelled measured with the page count;
until then the token assumption stands. No margin is added: the figure shown is Fichero's best estimate."""
from __future__ import annotations

import json
import statistics
from typing import Any

#: How many of the latest finished page jobs of a kind are read.
MOST_ROWS = 2000


def per_page(db: Any, job: str, provider: str, model: str) -> tuple[float, int] | None:
    """`(median dollars a page, pages)` over the pages whose `job` rows booked priced calls of this provider and model; None when none did.
    A page with several rows (a retry, a review pass each) counts once, the rows summed."""
    from fichero_server.execution.jobs import finished_details
    from fichero_server.llm.usage import aggregate_usage

    rows = finished_details(db, job, MOST_ROWS)
    by_page: dict[str, list[dict[str, Any]]] = {}
    for subject, detail in rows:
        try:
            usage = (json.loads(detail) or {}).get("usage", [])
        except (TypeError, ValueError):
            continue
        mine = [u for u in usage if u.get("provider") == provider and u.get("model") == model]
        if mine:
            by_page.setdefault(str(subject), []).extend(mine)
    costs = []
    for entries in by_page.values():
        totals = aggregate_usage(entries)
        if totals.priced and totals.cost_usd:
            costs.append(totals.cost_usd)
    return (statistics.median(costs), len(costs)) if costs else None


def for_workflows(db: Any, workflows: list[dict[str, Any]]) -> dict[tuple[str, str, str], tuple[float, int]]:
    """`per_page` for each cloud run of a plan, keyed `(job, provider, model)`; a run with nothing booked is absent."""
    out: dict[tuple[str, str, str], tuple[float, int]] = {}
    for w in workflows:
        provider, model, job = w.get("provider_override"), w.get("model_override"), w.get("job")
        if not (provider and model and job) or not str(w.get("runs_on")).startswith("cloud") or (job, provider, model) in out:
            continue
        found = per_page(db, job, provider, model)
        if found is not None:
            out[(job, provider, model)] = found
    return out
