"""Where a row runs (`activity.window.toolbar-tabs`, the Where tab; #6588, decision 23).

Spec: `docs/contributor_manual/specs/ui/activity-pane.md`. The Where tab lists each run by where it runs (This Mac, Other
Mac, Cloud, Cluster) and its lane. The engine says so on each listed row (`runs_on`, `lane`): the app only shows it.
WHY: the owner asked where work runs ("this Mac, another Mac, the cloud, a cluster") and the list had no such fact.
"""
from __future__ import annotations

from types import SimpleNamespace

from fichero_server.api.routes.system import activity
from fichero_server.execution import jobs
from fichero_server.remote_read import job as read_job


def test_local_work_runs_on_this_mac_and_names_its_lane():
    from fichero_server import kept_export

    kept_export.register_job_kinds()
    assert activity._runs_on(kept_export.KIND, None, None) == "this-mac"
    assert activity._lane_of(kept_export.KIND) == "database"


def test_priced_calls_and_the_remote_lane_run_in_the_cloud():
    assert activity._runs_on("ask-a-model", None, 0.0) == "cloud", "a priced call, even at $0, went to the cloud"
    jobs.register_kind("test-remote-kind-6588", None, model=None, lane="remote", name="A remote call")
    assert activity._runs_on("test-remote-kind-6588", None, None) == "cloud"


def test_a_remote_read_runs_on_a_cluster_or_in_the_cloud_by_its_target():
    hugging_face = SimpleNamespace(target=read_job.TARGET)
    cluster = SimpleNamespace(target="narval")
    assert activity._runs_on(read_job.KIND, hugging_face, None) == "cloud"
    assert activity._runs_on(read_job.KIND, cluster, None) == "cluster"


def test_the_listed_row_carries_where_it_runs(client, db, tmp_path):
    from fichero_server import kept_export

    folder = tmp_path / "Where"
    folder.mkdir()
    export_id = client.post("/api/export/kept", json={"folder": str(folder), "format": "plain-text", "per": "page"}).json()["id"]
    job_id = kept_export.write_now(db, export_id)
    jobs.pause_job(db, job_id, True)
    row = next(j for j in client.get("/api/activity/jobs").json()["jobs"] if j["id"] == job_id)
    assert (row["runs_on"], row["lane"]) == ("this-mac", "database")
