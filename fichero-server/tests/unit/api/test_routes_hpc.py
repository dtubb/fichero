"""Tests for the HPC (Slurm) cluster connection routes at /api/hpc/...

Config-first first slice: configure a cluster, list/get/delete it, run the
dry-run Test-connection probe, and dry-run-submit a workflow run as a Slurm
array job spec — all without a real cluster.
"""

import importlib.util
from pathlib import Path

# scripts/ is not a package: load the repo's scan helper by path (see test_scan_files_skips_nested_worktrees).
_SCAN = Path(__file__).resolve().parents[4] / "scripts" / "_scan_files.py"
_spec = importlib.util.spec_from_file_location("_scan_files", _SCAN)
assert _spec and _spec.loader
scan_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan_files)


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
        assert r.status_code == 422  # strict username pattern (security)

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


class TestSignInAndKey:
    """`compute.connect.second-factor-passes-through`, `compute.secret.fichero-makes-the-key`: the app pushes the
    cluster's key, lists the prompts ssh is waiting on, and answers them."""

    def test_the_key_is_pushed_and_removed_and_never_read_back(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.put(f"/api/hpc/clusters/{cid}/key", json={"private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\nk\n"})
        assert r.status_code == 200 and r.json() == {"cluster_id": cid, "has_key": True}
        assert "private_key" not in client.get(f"/api/hpc/clusters/{cid}").text
        assert client.delete(f"/api/hpc/clusters/{cid}/key").json()["has_key"] is False

    def test_a_prompt_ssh_waits_on_is_listed_then_answered(self, client):
        from fichero_server.remote_read.ssh_prompts import prompt_broker
        import threading

        out = {}
        t = threading.Thread(target=lambda: out.update(a=prompt_broker().ask("Duo passcode: ", timeout=10)))
        t.start()
        while not (items := client.get("/api/hpc/prompts").json()["items"]):
            threading.Event().wait(0.01)
        assert items[0]["prompt"] == "Duo passcode: "
        assert client.post(f"/api/hpc/prompts/{items[0]['id']}", json={"answer": "123456"}).status_code == 200
        t.join(5)
        assert out["a"] == "123456" and client.get("/api/hpc/prompts").json()["items"] == []
        assert client.post("/api/hpc/prompts/999", json={"answer": "x"}).status_code == 404

    def test_sign_in_without_a_key_is_refused_by_name(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.post(f"/api/hpc/clusters/{cid}/sign-in")
        assert r.status_code == 409 and "key" in r.json()["detail"].lower()

    def test_check_runs_the_steps_live_and_says_so(self, client, monkeypatch):
        from fichero_server.api.routes.ai import hpc

        class Shell:
            def run(self, argv):
                return (1, "", "no scheduler") if argv[0] == "sinfo" else (0, "ok\n", "")

        monkeypatch.setattr(hpc, "_shell_for", lambda cfg, cluster_id: Shell())
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        body = client.post(f"/api/hpc/clusters/{cid}/check").json()
        assert body["ok"] is False
        assert {s["name"]: s["state"] for s in body["steps"]}["gpus"] == "failed"

    def test_listing_the_prompts_is_owner_only_like_answering(self):
        from fichero_server.api.routes.ai import hpc

        def deps(path, method):
            route = next(r for r in hpc.router.routes if r.path.endswith(path) and method in r.methods)
            return {d.call for d in route.dependant.dependencies}

        assert hpc._require_owner_or_bootstrap in deps("/prompts", "GET")

    def test_answering_an_expired_prompt_says_expired(self, client):
        from fichero_server.remote_read.ssh_prompts import SecondFactorRefused, prompt_broker

        broker = prompt_broker()
        try:
            broker.ask("Duo passcode: ", timeout=0.05)
        except SecondFactorRefused:
            pass
        pid = next(i for i in range(1, 10_000) if broker.ended(str(i)) == "expired")
        r = client.post(f"/api/hpc/prompts/{pid}", json={"answer": "123456"})
        assert r.status_code == 410 and "expired" in r.json()["detail"]


class TestMakeTheKey:
    """`compute.secret.fichero-makes-the-key`: the engine makes the cluster's key pair; the public half is shown (and
    can be shown again) to be added in CCDB; the private half never leaves the engine's folder."""

    def test_make_show_again_and_remove(self, client, tmp_path, monkeypatch):
        import shutil
        import stat

        import pytest

        if not shutil.which("ssh-keygen"):
            pytest.skip("no ssh-keygen here")
        monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        r = client.post(f"/api/hpc/clusters/{cid}/key/make")
        assert r.status_code == 200, r.text
        public = r.json()["public_key"]
        assert public.startswith("ssh-ed25519 ") and "PRIVATE" not in r.text
        private = tmp_path / "hpc-keys" / cid / "id_ed25519"
        assert stat.S_IMODE(private.stat().st_mode) == 0o600
        assert client.get(f"/api/hpc/clusters/{cid}/key/public").json()["public_key"] == public  # shown again, same
        again = client.post(f"/api/hpc/clusters/{cid}/key/make")
        assert again.status_code == 409  # never silently replace a key the person already put in CCDB
        client.delete(f"/api/hpc/clusters/{cid}/key")
        assert client.get(f"/api/hpc/clusters/{cid}/key/public").status_code == 404


class TestThePrivateKeyStaysInTheEngineFolder:
    """The ruling on `compute.secret.fichero-makes-the-key` (2026-10-17): the key is a plain 0600 file in the
    engine's 0700 folder, so the key goes with its cluster and nothing else carries it out."""

    def test_deleting_the_cluster_deletes_its_key(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("FICHERO_BASE_PATH", str(tmp_path))
        from fichero_server.remote_read.ssh_prompts import cluster_key_path, store_cluster_key

        cid = client.post("/api/hpc/clusters", json=_cluster_body()).json()["cluster_id"]
        store_cluster_key(cid, "-----BEGIN OPENSSH PRIVATE KEY-----\nk\n")
        assert cluster_key_path(cid).exists()
        assert client.delete(f"/api/hpc/clusters/{cid}").status_code == 200
        assert not cluster_key_path(cid).exists() and not cluster_key_path(cid).parent.exists()

    def test_only_the_key_module_and_its_routes_know_where_keys_live(self):
        import pathlib

        import fichero_server

        root = pathlib.Path(fichero_server.__file__).parent
        allowed = {"remote_read/ssh_prompts.py", "api/routes/ai/hpc.py"}
        users = {
            str(p.relative_to(root))
            for p in scan_files.scan_rglob(root, "*.py")
            if any(w in p.read_text() for w in ("hpc-keys", "cluster_key_path", "store_cluster_key"))
        }
        assert users <= allowed, f"another module reaches the private keys (export, sync or backup?): {users - allowed}"
