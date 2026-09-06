"""Remote HPC batch helpers for ACEnet/SLURM execution.

This module intentionally starts as pure, testable building blocks:
- bundle manifest assembly for selected files + workflow metadata
- SLURM script rendering
- squeue output parsing for progress polling
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
import json
import shlex

from fichero_server.workflows.run_status import RunStatus


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


# =============================================================================
# HPC cluster configuration (plan §4/§6 — DB stores config refs, never secrets)
# =============================================================================


class HpcConfigError(ValueError):
    """A cluster config is missing a required field or has a bad value."""


@dataclass(frozen=True)
class HpcClusterConfig:
    """A configured Slurm compute target.

    Mirrors the plan's §4 rule: the app/library DB records only a *reference*
    to the connection — the SSH ``Host`` alias the user already has in
    ``~/.ssh/config``, their username, the remote base directory, and the
    default partition/account. **No key material or secret is ever stored
    here**; auth is the user's own ssh-agent/keychain-backed key.

    ``cluster_id``/``name`` are UI identity; everything else is what the engine
    needs to shell out to ``ssh``/``rsync``/``sbatch``.
    """

    cluster_id: str
    name: str
    host_alias: str
    username: str
    remote_base_dir: str
    partition: str = "default"
    account: str | None = None
    ssh_port: int = 22

    def validate(self) -> None:
        """Raise :class:`HpcConfigError` if a required field is missing/blank.

        Called at save time (mirrors ``validate_provider_config``) so a
        half-filled cluster row never reaches a submission attempt.
        """
        required = {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "host_alias": self.host_alias,
            "username": self.username,
            "remote_base_dir": self.remote_base_dir,
            "partition": self.partition,
        }
        missing = [k for k, v in required.items() if not (v or "").strip()]
        if missing:
            raise HpcConfigError(
                "HPC cluster config missing required field(s): "
                + ", ".join(sorted(missing))
            )
        if not (1 <= self.ssh_port <= 65535):
            raise HpcConfigError(f"ssh_port out of range: {self.ssh_port}")
        # Remote base dir must be an absolute POSIX path — scratch/project space
        # is always given as an absolute path, and a relative one would resolve
        # against the login node's home unpredictably.
        if not self.remote_base_dir.startswith("/"):
            raise HpcConfigError(
                f"remote_base_dir must be an absolute path: {self.remote_base_dir!r}"
            )

    def to_public_dict(self) -> dict[str, Any]:
        """Non-secret fields for API responses / persistence (all are non-secret)."""
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "host_alias": self.host_alias,
            "username": self.username,
            "remote_base_dir": self.remote_base_dir,
            "partition": self.partition,
            "account": self.account,
            "ssh_port": self.ssh_port,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HpcClusterConfig":
        """Rebuild a config from persisted JSON (unknown keys ignored)."""
        return cls(
            cluster_id=str(data.get("cluster_id", "")),
            name=str(data.get("name", "")),
            host_alias=str(data.get("host_alias", "")),
            username=str(data.get("username", "")),
            remote_base_dir=str(data.get("remote_base_dir", "")),
            partition=str(data.get("partition", "default") or "default"),
            account=(data.get("account") or None),
            ssh_port=int(data.get("ssh_port", 22) or 22),
        )

    def remote_workdir(self, run_id: str) -> str:
        """Run-scoped remote workdir — ``<base>/fichero/runs/<run_id>`` (§2)."""
        base = self.remote_base_dir.rstrip("/")
        return f"{base}/fichero/runs/{run_id}"


# =============================================================================
# Slurm ⇄ Fichero run-status mapping (plan §3 table)
# =============================================================================

# Slurm job/task state string -> canonical RunStatus. States not listed are
# treated conservatively as `running` (still in flight) by `map_slurm_state`,
# so an unrecognized transient state never dead-ends a run.
#
# NOTE (plan §3): a task is only truly `completed` once its results are LANDED
# in the library — Slurm's COMPLETED is a signal to go fetch, not the source of
# truth. This mapping reports what Slurm says; the poll loop is responsible for
# holding a task at `running` until landing succeeds. See map_slurm_state's
# `landed` argument.
_SLURM_STATE_MAP: dict[str, RunStatus] = {
    "PENDING": RunStatus.running,
    "CONFIGURING": RunStatus.running,
    "RUNNING": RunStatus.running,
    "COMPLETING": RunStatus.running,
    "RESIZING": RunStatus.running,
    "REQUEUED": RunStatus.running,
    "SUSPENDED": RunStatus.paused,
    "COMPLETED": RunStatus.completed,
    "FAILED": RunStatus.failed,
    "TIMEOUT": RunStatus.failed,
    "OUT_OF_MEMORY": RunStatus.failed,
    "NODE_FAIL": RunStatus.failed,
    "BOOT_FAIL": RunStatus.failed,
    "DEADLINE": RunStatus.failed,
    "PREEMPTED": RunStatus.failed,
    "CANCELLED": RunStatus.cancelled,
}

# Slurm states that mean "queued, not yet running" — the run stays `running`
# but the step detail should say so (queue position via squeue).
QUEUED_SLURM_STATES: frozenset[str] = frozenset({"PENDING", "CONFIGURING"})


def normalize_slurm_state(state: str) -> str:
    """Strip trailing annotations Slurm appends, e.g. ``CANCELLED by 12345``.

    ``sacct`` reports cancellations as ``CANCELLED by <uid>``; the leading
    token is the canonical state. Also upper-cases and strips a ``+`` suffix
    Slurm uses for truncated states (``CANCELLED+``).
    """
    token = (state or "").strip().split()[0] if (state or "").strip() else ""
    return token.upper().rstrip("+")


def map_slurm_state(state: str, *, landed: bool = True) -> RunStatus:
    """Map a Slurm job/task state onto the canonical :class:`RunStatus`.

    ``landed`` encodes the plan's §3 invariant: a Slurm ``COMPLETED`` task is
    only reported ``completed`` once its results are landed in the library;
    until then it is still ``running`` (Slurm exit is a signal to fetch, never
    the completion source of truth). Failures/cancellations map through
    regardless of landing.
    """
    canonical = _SLURM_STATE_MAP.get(normalize_slurm_state(state), RunStatus.running)
    if canonical is RunStatus.completed and not landed:
        return RunStatus.running
    return canonical


def is_terminal_slurm_state(state: str) -> bool:
    """True if Slurm considers this job/task finished (won't change further)."""
    return map_slurm_state(state, landed=True) in {
        RunStatus.completed,
        RunStatus.failed,
        RunStatus.cancelled,
    }


# =============================================================================
# Array-job directive (plan §3 — one run = one array job; sparse resubmission)
# =============================================================================


def _compress_indices(indices: list[int]) -> str:
    """Compress a sorted, de-duplicated index list into Slurm array syntax.

    ``[0,1,2,3]`` -> ``"0-3"``; ``[0,2,3,4,7]`` -> ``"0,2-4,7"``. Slurm accepts
    both range and comma-separated sparse lists, so a re-submit after a partial
    failure can pass only the missing indices (plan §3 idempotent resubmit).
    """
    if not indices:
        raise HpcConfigError("array index list is empty")
    ordered = sorted(set(indices))
    if ordered[0] < 0:
        raise HpcConfigError(f"array indices must be >= 0: {ordered[0]}")
    parts: list[str] = []
    start = prev = ordered[0]
    for idx in ordered[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = idx
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(parts)


def build_array_directive(indices: list[int], *, throttle: int = 0) -> str:
    """Render the ``#SBATCH --array=`` value for a set of task indices.

    ``throttle`` (>0) caps concurrently-running tasks via Slurm's ``%N`` syntax
    — the plan's per-provider fairness knob (§3). ``build_array_directive(
    [0,1,2,3], throttle=2)`` -> ``"--array=0-3%2"``.
    """
    body = _compress_indices(indices)
    if throttle and throttle > 0:
        body = f"{body}%{throttle}"
    return f"--array={body}"


# =============================================================================
# Submitter seam (plan §C/§8 — SshCliSubmitter now, RestdSubmitter later;
# a scriptable fake keeps the poll loop / state mapping testable clusterless)
# =============================================================================


@dataclass(frozen=True)
class SubmitResult:
    """Outcome of a submission: the Slurm job id + the workdir it was staged in."""

    job_id: str
    remote_workdir: str


class SlurmSubmitter(Protocol):
    """The narrow surface the engine drives to run a job on a cluster.

    Two real implementations are planned: ``SshCliSubmitter`` (``ssh sbatch`` /
    ``sacct`` / ``scancel``, the v0 path) and a future ``RestdSubmitter`` over
    ``slurmrestd``. Isolating them here means Option C is a drop-in upgrade, not
    a fork (plan §C).
    """

    def submit(self, spec: "RemoteRunSpec") -> SubmitResult: ...

    def poll(self, job_id: str) -> dict[str, str]: ...

    def cancel(self, job_id: str) -> None: ...


@dataclass(frozen=True)
class RemoteRunSpec:
    """Everything needed to stage and submit one workflow run as an array job.

    Built engine-side from a cluster config + a bundle manifest + the selected
    input indices. It carries the rendered sbatch script and the array directive
    so a submitter only has to transport and invoke — no policy lives in the
    submitter.
    """

    cluster: HpcClusterConfig
    manifest: BundleManifest
    remote_workdir: str
    sbatch_script: str
    array_directive: str
    throttle: int = 0


def build_remote_run_spec(
    *,
    cluster: HpcClusterConfig,
    manifest: BundleManifest,
    input_indices: list[int],
    job_config: SlurmJobConfig | None = None,
    throttle: int = 0,
    runner_command: list[str] | None = None,
) -> RemoteRunSpec:
    """Assemble a :class:`RemoteRunSpec` for a run (pure — no I/O, no cluster).

    This is the engine-side job-spec construction the plan's §2/§3 describe:
    resolve the remote workdir from the cluster + run id, render the array
    directive from the selected indices, and render the sbatch script (reusing
    the existing ``build_slurm_script``) with the array directive folded into
    the extra ``#SBATCH`` lines. A dry-run submission returns this spec without
    ever touching SSH.
    """
    cluster.validate()
    array_directive = build_array_directive(input_indices, throttle=throttle)
    workdir = cluster.remote_workdir(manifest.run_id)
    base_config = job_config or SlurmJobConfig(
        job_name=f"fichero-{manifest.workflow_name}"[:63],
        partition=cluster.partition,
    )
    # Fold the array directive + account into the sbatch header via extra lines,
    # so build_slurm_script stays the single script renderer (iterate-not-replace).
    extra = list(base_config.extra_sbatch_lines)
    extra.append(f"#SBATCH {array_directive}")
    if cluster.account:
        extra.append(f"#SBATCH --account={cluster.account}")
    effective = SlurmJobConfig(
        job_name=base_config.job_name,
        partition=base_config.partition,
        time_limit=base_config.time_limit,
        cpus_per_task=base_config.cpus_per_task,
        mem_gb=base_config.mem_gb,
        gpus=base_config.gpus,
        extra_sbatch_lines=extra,
    )
    command = runner_command or [
        "python",
        "runner/run_task.py",
        "--manifest",
        "manifest.json",
        "--index",
        "${SLURM_ARRAY_TASK_ID}",
    ]
    script = build_slurm_script(
        config=effective,
        remote_workdir=workdir,
        runner_command=command,
    )
    return RemoteRunSpec(
        cluster=cluster,
        manifest=manifest,
        remote_workdir=workdir,
        sbatch_script=script,
        array_directive=array_directive,
        throttle=throttle,
    )


class DryRunSubmitter:
    """A no-cluster submitter that records calls and returns scripted state.

    The §8 fake: exercises the submit/poll/cancel contract, the poll loop, and
    the Slurm→RunStatus mapping without a real cluster. ``poll`` returns the
    next scripted state map each call (repeating the last once exhausted), so a
    test can drive PENDING → RUNNING → COMPLETED deterministically.
    """

    def __init__(
        self,
        *,
        job_id: str = "dryrun-1",
        state_sequence: list[dict[str, str]] | None = None,
    ) -> None:
        self.job_id = job_id
        self._states = list(state_sequence or [])
        self._poll_count = 0
        self.submitted: list[RemoteRunSpec] = []
        self.cancelled: list[str] = []

    def submit(self, spec: RemoteRunSpec) -> SubmitResult:
        self.submitted.append(spec)
        return SubmitResult(job_id=self.job_id, remote_workdir=spec.remote_workdir)

    def poll(self, job_id: str) -> dict[str, str]:
        if not self._states:
            return {}
        idx = min(self._poll_count, len(self._states) - 1)
        self._poll_count += 1
        return dict(self._states[idx])

    def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)


def build_ssh_command(
    cluster: HpcClusterConfig, remote_command: list[str]
) -> list[str]:
    """Render the argv for running ``remote_command`` on the cluster over SSH.

    Uses the user's own ``Host`` alias (plan §4) and a ControlMaster-friendly
    invocation. Pure command construction — this does NOT execute anything; the
    v0 slice builds and returns commands so they can be reviewed and unit-tested
    before any real shell-out is wired.
    """
    joined = " ".join(shlex.quote(part) for part in remote_command)
    return [
        "ssh",
        "-p",
        str(cluster.ssh_port),
        f"{cluster.username}@{cluster.host_alias}",
        joined,
    ]


def build_sinfo_probe_command(cluster: HpcClusterConfig) -> list[str]:
    """Build the SSH argv for a Test-connection probe (``sinfo`` on a partition).

    The plan's §6 Test-connection button checks SSH reachability + ``sinfo``.
    This renders that command; executing it is a later wiring step.
    """
    return build_ssh_command(
        cluster, ["sinfo", "-p", cluster.partition, "-h", "-o", "%P|%a|%D"]
    )
