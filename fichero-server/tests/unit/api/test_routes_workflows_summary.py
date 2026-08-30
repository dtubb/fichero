"""GET /api/workflows?summary=true — the lean list payload.

The full list carries every preset's whole node/edge graph: 263 KB to name
50 workflows, decoded on the way to drawing a folder of labels, which is
the spin when a workflow folder opens in the sidebar (2026-08-28). Callers
that only draw labels ask for the summary; the graph stays one
GET /api/workflows/{id} away.
"""

from __future__ import annotations


class TestWorkflowSummaryList:
    def test_summary_omits_graphs_but_keeps_their_counts(self, client):
        client.post("/api/workflows/reinstall-defaults")

        full = client.get("/api/workflows").json()["items"]
        lean = client.get("/api/workflows", params={"summary": "true"}).json()["items"]

        assert len(lean) == len(full) and full, "summary must not drop workflows"
        by_id = {w["id"]: w for w in full}
        for item in lean:
            original = by_id[item["id"]]
            # The graphs are gone...
            assert item["nodes"] == []
            assert item["edges"] == []
            # ...but what the sidebar actually reads survives, including the
            # count it used to get by measuring `nodes`.
            assert item["node_count"] == len(original["nodes"])
            assert item["edge_count"] == len(original["edges"])
            assert item["name"] == original["name"]
            assert item["folder_path"] == original["folder_path"]
            # Run eligibility is decided by the engine and must not need the
            # graph to be present (#3804).
            assert item["direct_runnable"] == original["direct_runnable"]
            assert item["requires_vision"] == original["requires_vision"]
            assert item["accepts_model_override"] == original["accepts_model_override"]

    def test_summary_is_materially_smaller(self, client):
        client.post("/api/workflows/reinstall-defaults")

        full = client.get("/api/workflows").content
        lean = client.get("/api/workflows", params={"summary": "true"}).content
        assert len(lean) * 2 < len(full), (
            f"summary saved too little to be worth it: "
            f"{len(full)} -> {len(lean)} bytes"
        )

    def test_default_is_unchanged_so_existing_callers_keep_their_graphs(self, client):
        client.post("/api/workflows/reinstall-defaults")

        items = client.get("/api/workflows").json()["items"]
        assert any(w["nodes"] for w in items), "the canvas still needs the graph"
        # node_count is populated on the full payload too, so a client can
        # migrate to it without first flipping to summary.
        for workflow in items:
            assert workflow["node_count"] == len(workflow["nodes"])

    def test_single_workflow_fetch_still_carries_the_graph(self, client):
        client.post("/api/workflows/reinstall-defaults")

        lean = client.get("/api/workflows", params={"summary": "true"}).json()["items"]
        target = next(w for w in lean if w["node_count"] > 0)

        detail = client.get(f"/api/workflows/{target['id']}").json()
        assert len(detail["nodes"]) == target["node_count"], (
            "the summary's escape hatch must return what the summary omitted"
        )
