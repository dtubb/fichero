"""scripts/report_engine_ux_coverage.py and the matrix's "a new route is named in a spec" rule (#7067).

The known-gaps list froze 313 engine operations with no owner. The report says, for each, whether a spec names it, whether that
spec has an app behaviour for it, and whether that behaviour is still [GAP]; the matrix guard fails a route no spec names.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(_SCRIPTS))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


report = _load("report_engine_ux_coverage")

S = "docs/contributor_manual" + "/specs"
OPENAPI = {"paths": {
    "/api/models": {"get": {"operationId": "list_models_api_models_get"}},
    "/api/models/{model_id}": {"get": {"operationId": "get_model_api_models__model_id__get"}},
    "/api/cluster/nodes": {"get": {"operationId": "cluster_nodes_api_cluster_nodes_get"}},
    "/api/cluster/jobs": {"get": {"operationId": "cluster_jobs_api_cluster_jobs_get"}},
    "/api/lonely": {"get": {"operationId": "lonely_api_lonely_get"}},
}}
GAPS = {"GET /api/models": "", "GET /api/models/{model_id}": "", "GET /api/cluster/nodes": "", "GET /api/cluster/jobs": "", "GET /api/lonely": ""}


def _root(tmp_path: Path) -> Path:
    specs = tmp_path / "docs" / "contributor_manual" / "specs"
    specs.mkdir(parents=True)
    (specs / "models.md").write_text(
        "- `m.list` — **[GAP]** (#1) the app lists models from `GET /api/models`.\n"
        "- `m.engine` — **[OK]** the engine returns one model from `/api/models/{model_id}`. *Test:* `t.py`\n", encoding="utf-8")
    (specs / "cluster.md").write_text(
        "- `c.nodes` — **[OK]** the app shows `/api/cluster/nodes`. *Test:* `fichero/Tests/Unit/general/ClusterTests.swift`\n"
        "- `c.jobs` — **[OK]** the engine lists jobs, operation cluster_jobs_api_cluster_jobs_get. *Test:* `t.py`\n", encoding="utf-8")
    return tmp_path


def test_each_known_gap_lands_in_one_bucket_no_spec_no_app_behaviour_or_app_behaviour_still_gap(tmp_path):
    r = report.classify(_root(tmp_path), GAPS, OPENAPI)
    assert r["no_spec"] == ["GET /api/lonely"]
    assert r["spec_no_app_behaviour"] == ["GET /api/cluster/jobs", "GET /api/models/{model_id}"]
    assert r["app_behaviour_still_gap"] == ["GET /api/models"]
    # GET /api/cluster/nodes has an [OK] app behaviour with a Swift test: in no bucket
    assert "GET /api/cluster/nodes" not in sum(r.values(), [])


def test_a_path_is_not_named_by_a_longer_sibling_path(tmp_path):
    root = _root(tmp_path)
    (root / S + "/models.md").write_text("- `m.x` — **[GAP]** (#1) the app uses `/api/models/{model_id}`.\n", encoding="utf-8")
    assert "GET /api/models" in report.classify(root, GAPS, OPENAPI)["no_spec"]


def test_the_report_prints_the_three_counts_the_ux_count_and_the_top_twenty(tmp_path, capsys):
    root = _root(tmp_path)
    text = report.render(report.classify(root, GAPS, OPENAPI), report.no_ux_count(root), top=20)
    assert "no spec names it: 1" in text and "spec but no app behaviour: 2" in text and "app behaviour still [GAP]: 1" in text
    assert "app features whose spec has no UX section: 2" in text
    assert "GET /api/lonely" in text


def test_the_top_twenty_cap_holds(tmp_path):
    gaps = {f"GET /api/x{i}": "" for i in range(30)}
    api = {"paths": {f"/api/x{i}": {"get": {"operationId": f"x{i}"}} for i in range(30)}}
    text = report.render(report.classify(_root(tmp_path), gaps, api), 0, top=20)
    assert "no spec names it: 30" in text and text.count("GET /api/x") == 20


def test_unnamed_operations_lists_every_operation_no_spec_names(tmp_path):
    assert report.unnamed_operations(_root(tmp_path), OPENAPI) == ["GET /api/lonely"]


def test_the_matrix_fails_a_route_no_spec_names_unless_it_is_baselined():
    matrix = _load("check_endpoint_coverage_matrix")
    assert matrix.spec_unnamed_failures(["GET /api/a", "GET /api/b"], {"GET /api/a"}) == ["GET /api/b"]
    assert matrix.spec_unnamed_failures(["GET /api/a"], {"GET /api/a", "GET /api/gone"}) == []


def test_the_repo_has_no_unnamed_route_outside_the_baseline():
    matrix = _load("check_endpoint_coverage_matrix")
    _p, api = matrix.load_openapi()
    unnamed = report.unnamed_operations(matrix.ROOT, api)
    assert matrix.spec_unnamed_failures(unnamed, matrix.SPEC_UNNAMED_BASELINE) == []
