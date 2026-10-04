"""A reading run as a Slurm array job under Apptainer, e.g. on ACENET (#5398 slice 2).

`compute.job.array-by-shard`: one array task per shard of the read package, each running Fichero's
runner inside the server image (one Apptainer file in project space, `--nv` for the GPU).
`compute.job.sparse-resubmit`: naming the failed shards gives an array of only those (`--array=3,7`).
Compute nodes have no internet, so a package with IIIF pages is prefetched first on the login node
(`runner.py --prefetch`), politely, into the package.

This DESCRIBES the run (the sbatch script, the array, the commands); it sends nothing. Live
submission over SSH waits for the cluster account (`compute.job.live-submit`); until then
`SshCliSubmitter` stays disabled and this is what "show me what will run" shows.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

from fichero_server.remote_read.package import ReadPackage
from fichero_server.workflows.remote_jobs import (
    HpcClusterConfig,
    RemoteRunSpec,
    SlurmJobConfig,
    build_bundle_manifest,
    build_remote_run_spec,
    build_ssh_command,
)

IMAGE = "fichero-server.sif"


@dataclass(frozen=True)
class SlurmRead:
    spec: RemoteRunSpec
    #: Run on the login node before `sbatch`; None when the package has no IIIF pages.
    prefetch: list[str] | None


def image_path(cluster: HpcClusterConfig) -> str:
    """Where the login node keeps the Apptainer file: project space, shared by every run."""
    return f"{cluster.remote_base_dir.rstrip('/')}/fichero/images/{IMAGE}"


def describe_slurm_read(cluster: HpcClusterConfig, package: ReadPackage, *, shards: list[int] | None = None,
                        gpus: int = 1, time_limit: str = "02:00:00", mem_gb: int = 32, cpus: int = 8,
                        throttle: int = 0) -> SlurmRead:
    """The array job that reads `shards` (all of them by default) of a package sent to the cluster."""
    indices = list(range(len(package.shards))) if shards is None else sorted(set(shards))
    unknown = [i for i in indices if not 0 <= i < len(package.shards)]
    if unknown:
        raise ValueError(f"no shard {unknown[0]}: the package has {len(package.shards)}")
    manifest = build_bundle_manifest(workflow_id="read-at-scale", workflow_name="read-at-scale",
                                     input_files=[s["id"] for s in package.sources], library_path=".",
                                     run_id=package.job_id)
    image = image_path(cluster)
    apptainer = ["apptainer", "exec", *(["--nv"] if gpus else []), "--bind", ".:/package", image, "python"]
    command = [*apptainer, "/package/_fichero/runner.py", "--package", "/package",
               "--shard", "${SLURM_ARRAY_TASK_ID}", "--out", "/package/out",
               "--device", "cuda:0" if gpus else "cpu"]
    # Slurm's own slurm-%A_%a.out keeps each task's last lines (a failed shard's reason).
    config = SlurmJobConfig(job_name=f"fichero-read-{package.job_id[:8]}", partition=cluster.partition,
                            time_limit=time_limit, cpus_per_task=cpus, mem_gb=mem_gb, gpus=gpus)
    spec = build_remote_run_spec(cluster=cluster, manifest=manifest, input_indices=indices, job_config=config,
                                 throttle=throttle, runner_command=command)
    prefetch = None
    if any(s.get("iiif_service") for s in package.sources):
        on_login = (f"cd {shlex.quote(spec.remote_workdir)} && "
                    f"apptainer exec --bind .:/package {shlex.quote(image)} python /package/_fichero/runner.py "
                    "--package /package --prefetch")
        prefetch = build_ssh_command(cluster, ["bash", "-lc", on_login])
    return SlurmRead(spec=spec, prefetch=prefetch)
