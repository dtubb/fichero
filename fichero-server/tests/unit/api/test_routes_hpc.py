"""Tests for the HPC (Slurm) cluster connection routes at /api/hpc/...

Config-first first slice: configure a cluster, list/get/delete it, run the
dry-run Test-connection probe, and dry-run-submit a workflow run as a Slurm
array job spec — all without a real cluster.
"""


def _cluster_body(**overrides):
    body = {
        "name": "ACEnet",
        "host_alias": "acenet",
        "username": "researcher",
        "remote_base_dir": "/scratch/researcher",
        "partition": "gpu",
        "account": "def-lab",
    }
    body.update(overrides)
    return body


class TestConfigureCluster:
    def test_create_then_list_and_get(self, client):
        r = client.post("/api/hpc/clusters", json=_cluster_body())
        assert r.status_code == 200, r.text
        created = r.json()
        cid = created["cluster_id"]
        assert created["host_alias"] == "acenet"

        r = client.get("/api/hpc/clusters")
        assert r.status_code == 200
        listing = r.json()
        assert listing["count"] == 1
        assert listing["items"][0]["cluster_id"] == cid

        r = client.get(f"/api/hpc/clusters/{cid}")
        assert r.status_code == 200
        assert r.json()["partition"] == "gpu"

    def test_update_in_place_by_id(self, client):
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.post(
            "/api/hpc/clusters",
            json=_cluster_body(cluster_id=cid, partition="cpu", name="ACEnet CPU"),
        )
        assert r.status_code == 200
        assert client.get("/api/hpc/clusters").json()["count"] == 1
        assert r.json()["partition"] == "cpu"

    def test_invalid_config_rejected(self, client):
        r = client.post("/api/hpc/clusters", json=_cluster_body(remote_base_dir="relative"))
        assert r.status_code == 400
        assert "absolute" in r.json()["detail"].lower()

    def test_missing_field_rejected(self, client):
        r = client.post("/api/hpc/clusters", json=_cluster_body(username="  "))
        assert r.status_code == 400

    def test_delete(self, client):
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        assert client.delete(f"/api/hpc/clusters/{cid}").status_code == 200
        assert client.get("/api/hpc/clusters").json()["count"] == 0
        assert client.delete(f"/api/hpc/clusters/{cid}").status_code == 404

    def test_get_missing_is_404(self, client):
        assert client.get("/api/hpc/clusters/nope").status_code == 404


class TestTestConnection:
    def test_dry_run_probe_returns_command(self, client):
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.post(f"/api/hpc/clusters/{cid}/test")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["probe_command"][0] == "ssh"
        assert any("sinfo -p gpu" in part for part in data["probe_command"])

    def test_test_missing_cluster_is_404(self, client):
        assert client.post("/api/hpc/clusters/nope/test").status_code == 404


class TestDryRunSubmit:
    def test_builds_array_job_spec(self, client):
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.post(
            f"/api/hpc/clusters/{cid}/dry-run-submit",
            json={
                "workflow_id": "wf-1",
                "workflow_name": "Transcribe",
                "run_id": "run-7",
                "input_files": ["/a.pdf", "/b.pdf", "/c.pdf"],
                "throttle": 2,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["task_count"] == 3
        assert data["array_directive"] == "--array=0-2%2"
        assert data["remote_workdir"] == "/scratch/researcher/fichero/runs/run-7"
        assert "#SBATCH --array=0-2%2" in data["sbatch_script"]

    def test_empty_inputs_rejected(self, client):
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.post(
            f"/api/hpc/clusters/{cid}/dry-run-submit",
            json={
                "workflow_id": "wf-1",
                "workflow_name": "Transcribe",
                "run_id": "run-7",
                "input_files": [],
            },
        )
        assert r.status_code == 400

    def test_submit_missing_cluster_is_404(self, client):
        r = client.post(
            "/api/hpc/clusters/nope/dry-run-submit",
            json={
                "workflow_id": "wf-1",
                "workflow_name": "Transcribe",
                "run_id": "run-7",
                "input_files": ["/a.pdf"],
            },
        )
        assert r.status_code == 404
