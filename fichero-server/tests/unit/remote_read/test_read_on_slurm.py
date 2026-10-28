"""A reading run described as a Slurm array job under Apptainer, e.g. on ACENET (#5398 slice 2).

Nothing is sent: live submission waits for the cluster account. What is pinned is what WOULD run,
and the parts of it that run here for real: the sbatch script under bash, and the login node's
prefetch feeding a shard that has no internet.
"""
from __future__ import annotations

import io
import json
import os
import subprocess

import pytest
from PIL import Image

from fichero_server.remote_read import runner
from fichero_server.remote_read.package import ReadPackage
from fichero_server.remote_read.slurm import describe_slurm_read
from fichero_server.workflows.remote_jobs import HpcClusterConfig, SlurmJobConfig, build_slurm_script

ACENET = HpcClusterConfig(cluster_id="siku", name="Siku", host_alias="siku", username="historian",
                          remote_base_dir="/project/def-lab/historian", partition="gpu", account="def-lab")


def _package(n_sources, shard_size=50, iiif=False):
    sources = [{"id": f"s{i}", **({"iiif_service": f"https://iiif.example/img/{i}"} if iiif else
                                  {"image": f"images/{i}.jpg"})} for i in range(n_sources)]
    shards = [list(range(i, min(i + shard_size, n_sources))) for i in range(0, n_sources, shard_size)]
    return ReadPackage(job_id="read-0001-abcdef", sources=sources, shards=shards)


def test_a_thousand_pages_at_fifty_are_one_array_of_twenty_under_apptainer():
    """WHY (`compute.job.array-by-shard`, the spec's own test): 1,000 sources at 50 a shard is ONE
    array job, `--array=0-19`, each task running Fichero's runner inside the server image on a GPU."""
    run = describe_slurm_read(ACENET, _package(1000))
    script = run.spec.sbatch_script
    assert run.spec.array_directive == "--array=0-19"
    assert "#SBATCH --array=0-19" in script and "#SBATCH --account=def-lab" in script
    assert "#SBATCH --gres=gpu:1" in script
    assert "apptainer exec --nv --bind .:/package /project/def-lab/historian/fichero/images/fichero-server.sif" in script


def test_only_the_failed_shards_are_sent_again():
    """WHY (`compute.job.sparse-resubmit`, the spec's fixture): shards 3 and 7 of 10 failed; the
    re-send is an array of exactly those two."""
    run = describe_slurm_read(ACENET, _package(500), shards=[7, 3])
    assert run.spec.array_directive == "--array=3,7"
    with pytest.raises(ValueError, match="no shard 10"):
        describe_slurm_read(ACENET, _package(500), shards=[10])


def test_each_array_task_receives_its_own_index(tmp_path):
    """WHY (a defect this slice found): the script quoted `${SLURM_ARRAY_TASK_ID}` in single quotes,
    so every task of an array read the literal text and the same (no) shard. Run under bash here."""
    script = build_slurm_script(config=SlurmJobConfig(), remote_workdir=str(tmp_path),
                                runner_command=["echo", "--shard", "${SLURM_ARRAY_TASK_ID}", "it's"])
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                          env={**os.environ, "SLURM_ARRAY_TASK_ID": "7"}, check=True)
    assert done.stdout == "--shard 7 it's\n"


def test_iiif_pages_prefetched_into_the_package_are_read_offline_and_nothing_runs_on_the_login_node(tmp_path):
    """WHY (compute nodes have no internet; `compute.hpc.nothing-heavy-on-a-login-node`): a package of IIIF pages is
    prefetched into itself before it is sent (on this Mac, `SlurmReadTarget.send`); a shard then reads without a single
    request, and the run's description has no login-node step."""
    run = describe_slurm_read(ACENET, _package(3, iiif=True))
    assert not hasattr(run, "prefetch") and "--prefetch" not in run.spec.sbatch_script

    package = tmp_path / "pkg"
    (package / "_fichero").mkdir(parents=True)
    (package / "_fichero" / "iiif_fetch.py").write_bytes(
        (runner.Path(runner.__file__).parent.parent / "media" / "iiif_fetch.py").read_bytes())
    made = _package(3, shard_size=3, iiif=True)
    (package / "job.json").write_text(json.dumps({"step": {"reader": "vlm", "card": "c"}, "stage": ["read"], "fetch": {"longest": 800},
                                                  "shards": made.shards, "sources": made.sources}))

    def server(url, timeout):
        data = io.BytesIO()
        Image.new("RGB", (600, 800), "white").save(data, format="JPEG")
        return 200, {}, data.getvalue()

    assert runner.prefetch(package, get=server)["failed"] == {}

    def offline(url, timeout):
        raise AssertionError(f"a compute node fetched {url}")

    outcome = runner.run_shard(package, 0, tmp_path / "out", reader=lambda image: [], get=offline)
    assert all(v["ok"] and v["size"] == [600, 800] for v in outcome["sources"].values())


def test_the_script_fits_the_site_account_typed_gpu_signal_offline_and_no_forced_partition():
    """WHY (`compute.hpc.sbatch-fits-the-site`): ACENET wants an account, a typed GPU, a warning signal
    before the time limit and a requeue; compute nodes are offline; and a site with no named partition
    must not be handed `--partition=default`."""
    script = build_slurm_script(
        config=SlurmJobConfig(gpus=1, gpu_type="h100", account="def-lab", signal_seconds=90),
        remote_workdir="/p", runner_command=["true"])
    for line in ("#SBATCH --account=def-lab", "#SBATCH --gres=gpu:h100:1", "#SBATCH --signal=B:USR1@90",
                 "#SBATCH --requeue", "export HF_HUB_OFFLINE=1"):
        assert line in script
    assert "--partition" not in script
    named = build_slurm_script(config=SlurmJobConfig(partition="gpu_h100"), remote_workdir="/p", runner_command=["true"])
    assert "#SBATCH --partition=gpu_h100" in named and "--gres" not in named


def test_a_cluster_without_a_partition_is_valid_and_its_sinfo_probe_names_none():
    """WHY (`compute.hpc.sbatch-fits-the-site`): the partition is optional, not required."""
    from fichero_server.workflows.remote_jobs import build_sinfo_probe_command
    bare = HpcClusterConfig(cluster_id="r", name="Rorqual", host_alias="rorqual", username="u",
                            remote_base_dir="/project/def-lab/u", account="def-lab")
    assert bare.validate() is None
    assert "-p" not in build_sinfo_probe_command(bare)[-1].split()
    assert "--partition" not in describe_slurm_read(bare, _package(10)).spec.sbatch_script
