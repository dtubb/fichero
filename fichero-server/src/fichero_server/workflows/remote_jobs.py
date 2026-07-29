"""Remote HPC batch helpers for ACEnet/SLURM execution.

This module intentionally starts as pure, testable building blocks:
- bundle manifest assembly for selected files + workflow metadata
- SLURM script rendering
- squeue output parsing for progress polling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import shlex


@dataclass(frozen=True)
class RemoteConnectionConfig:
    hostname: str
    username: str
    remote_workdir: str
    ssh_port: int = 22


@dataclass(frozen=True)
class SlurmJobConfig:
    job_name: str = "fichero-workflow"
    partition: str = "default"
    time_limit: str = "02:00:00"
    cpus_per_task: int = 4
    mem_gb: int = 8
    gpus: int = 0
    extra_sbatch_lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BundleManifest:
    workflow_id: str
    workflow_name: str
    input_files: list[str]
    library_path: str
    run_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "workflow_id": self.workflow_id,
                "workflow_name": self.workflow_name,
                "input_files": self.input_files,
                "library_path": self.library_path,
                "run_id": self.run_id,
                "metadata": self.metadata,
            },
            indent=2,
            sort_keys=True,
        )


def build_bundle_manifest(
    *,
    workflow_id: str,
    workflow_name: str,
    input_files: list[str],
    library_path: str,
    run_id: str,
    metadata: dict[str, Any] | None = None,
) -> BundleManifest:
    """Build a deterministic bundle manifest for a remote run."""
    normalized = [str(Path(p)) for p in input_files]
    return BundleManifest(
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        input_files=normalized,
        library_path=str(Path(library_path)),
        run_id=run_id,
        metadata=metadata or {},
    )


def write_manifest(manifest: BundleManifest, destination: str | Path) -> Path:
    """Write manifest JSON to disk and return the resolved path."""
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(manifest.to_json(), encoding="utf-8")
    return target


def build_slurm_script(
    *,
    config: SlurmJobConfig,
    remote_workdir: str,
    runner_command: list[str],
) -> str:
    """Render an sbatch script for a workflow run bundle."""
    cmd = " ".join(shlex.quote(part) for part in runner_command)
    lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={config.job_name}",
        f"#SBATCH --partition={config.partition}",
        f"#SBATCH --time={config.time_limit}",
        f"#SBATCH --cpus-per-task={config.cpus_per_task}",
        f"#SBATCH --mem={config.mem_gb}G",
    ]
    if config.gpus > 0:
        lines.append(f"#SBATCH --gres=gpu:{config.gpus}")
    lines.extend(config.extra_sbatch_lines)
    lines.extend(
        [
            "set -euo pipefail",
            f"cd {shlex.quote(remote_workdir)}",
            cmd,
        ]
    )
    return "\n".join(lines) + "\n"


def parse_squeue_output(output: str) -> dict[str, str]:
    """Parse `squeue -h -o '%i|%T'` output into {job_id: status}."""
    status_by_job: dict[str, str] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" not in line:
            continue
        job_id, status = line.split("|", 1)
        job_id = job_id.strip()
        status = status.strip()
        if job_id:
            status_by_job[job_id] = status
    return status_by_job
