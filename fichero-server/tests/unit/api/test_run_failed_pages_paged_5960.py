"""`activity.run.failed-pages-paged` (#5960): every failed page of a run with its one reason, beyond the account's first ten."""
from __future__ import annotations

from fichero_server.api.main import app
from fichero_server.api.routes.system.activity_pages import failed_only, page_states
from tests.unit.api.test_run_page_states_5960 import _page, _stage_run


def _tree(failures: int) -> dict:
    pages = [_page(str(i), f"IMG_{i:03}", "failed", f"Kraken could not read line {i}") for i in range(failures)]
    pages += [_page("ok", "IMG_ok", "done")]
    read = _stage_run("w2", {"read-a-line": pages})
    return {"id": "r1", "kind": "run-a-recipe", "state": "running", "children": [read],
            "stages": [{"steps": ["read-a-line"], "child_id": "w2"}]}


def test_every_failed_page_is_listed_past_the_accounts_first_ten_each_with_its_reason():
    failed = failed_only(page_states(_tree(24), stage=None))
    assert len(failed) == 24
    assert failed[-1]["reason"] == "Kraken could not read line 23" and all(p["state"] == "failed" for p in failed)


def test_a_run_with_no_failure_lists_none():
    assert failed_only(page_states(_tree(0), stage=None)) == []


def test_the_route_exists_and_pages():
    op = app.openapi()["paths"]["/api/activity/jobs/{job_id}/failed-pages"]["get"]
    assert {"offset", "limit", "stage"} <= {p["name"] for p in op["parameters"]}
