"""The cost fields the client reads, pinned in the committed schema.

The whole point of the 2026-09-03 cost work is that "we could not price this"
is a state the client can SEE. That only holds if the schema keeps `cost_usd`
nullable — a non-nullable float is the type-system version of `or 0.0`, and it
would push the lie back into the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_PATH = REPO_ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json"


@pytest.fixture(scope="module")
def schemas() -> dict:
    return json.loads(SCHEMA_PATH.read_text())["components"]["schemas"]


def _is_nullable(prop: dict) -> bool:
    """FastAPI renders `float | None` as anyOf[number, null]."""
    if prop.get("nullable") is True:
        return True
    return any(
        variant.get("type") == "null" for variant in prop.get("anyOf", []) if isinstance(variant, dict)
    )


def test_run_usage_response_is_published(schemas: dict) -> None:
    usage = schemas["RunUsageResponse"]["properties"]
    for field in (
        "model_calls",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cost_usd",
        "priced",
        "partially_priced",
        "estimated_tokens",
        "unpriced_models",
    ):
        assert field in usage, f"RunUsageResponse lost {field}"


def test_run_usage_cost_is_nullable(schemas: dict) -> None:
    assert _is_nullable(schemas["RunUsageResponse"]["properties"]["cost_usd"])


def test_workflow_run_carries_usage(schemas: dict) -> None:
    assert "run_usage" in schemas["WorkflowRunResponse"]["properties"]


def test_comparison_result_cost_is_nullable(schemas: dict) -> None:
    # The sibling defect (fix-then-sweep): model comparison reported 0.0 for
    # models with no registry price.
    props = schemas["ModelResultResponse"]["properties"]
    assert _is_nullable(props["cost_usd"])
    assert "cost_priced" in props
    assert "tokens_estimated" in props

    totals = schemas["ComparisonResultResponse"]["properties"]
    assert _is_nullable(totals["total_cost_usd"])
    assert "total_cost_priced" in totals
    assert "unpriced_models" in totals


def test_cost_estimate_is_nullable_and_says_whether_it_priced(schemas: dict) -> None:
    item = schemas["CostEstimateItem"]["properties"]
    assert _is_nullable(item["estimated_cost_usd"])
    assert "priced" in item

    response = schemas["CostEstimateResponse"]["properties"]
    assert _is_nullable(response["total_estimated_cost_usd"])
    assert "all_models_priced" in response
