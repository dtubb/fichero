"""A Slurm cluster as a place to send a read package and run its shards (#5457, `compute.hpc.slurm-target`).

The same small surface `HfJobsTarget` has (`send/submit/statuses/status/fetch_part/cancel/last_lines`), so
the read-at-scale loop (`remote_read/job.py`) runs on a cluster as it does on Hugging Face. All it needs
from the world is a `Shell` (a login connection: run a command, put a file, get a file), so the logic is
tested without a cluster; the real one is SSH in the engine's process (`compute.connect.ssh-in-process`).

One difference from Hugging Face: a read is ONE Slurm array (`sbatch --array`), not a Job per shard, so
`submit` takes the shards and returns the array's id, and a shard's id is `<array>_<shard>` (Slurm's own).
`statuses` is one `sacct` call for the whole array (`compute.hpc.status-from-sacct`).
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Protocol

from fichero_server.training.hf_jobs import CANCELLED, DONE, FAILED, RUNNING, WAITING, FarStatus
from fichero_server.workflows.remote_jobs import HpcClusterConfig, build_ssh_command, normalize_slurm_state

#: Slurm's states in a job row's words (`compute.hpc.failure-states-in-words`); anything else is still going.
_WORDS = {
    "PENDING": (WAITING, "waiting in the queue"),
    "CONFIGURING": (WAITING, "waiting for a node"),
    "COMPLETED": (DONE, None),
    "CANCELLED": (CANCELLED, "cancelled"),
    "TIMEOUT": (FAILED, "ran out of time before it finished"),
    "OUT_OF_MEMORY": (FAILED, "ran out of memory"),
    "NODE_FAIL": (FAILED, "the node failed under it"),
    "PREEMPTED": (FAILED, "was pre-empted by another job"),
    "FAILED": (FAILED, "failed; the last lines of its log say why"),
}


class Shell(Protocol):
    """A login connection to the cluster."""

    def run(self, argv: list[str]) -> tuple[int, str, str]: ...
    def put(self, local: Path, remote: str) -> None: ...
    def put_text(self, text: str, remote: str) -> None: ...
    def get(self, remote: str, local: Path) -> None: ...


class SlurmError(RuntimeError):
    pass


def parse_sacct(output: str) -> dict[str, FarStatus]:
    """`sacct -X -P -n -o JobID,State` → {task id: status}. Rows are `123_4|COMPLETED`; a pending array
    is one row `123_[0-19]|PENDING`, which is every task of it still waiting."""
    found: dict[str, FarStatus] = {}
    for raw in output.splitlines():
        if "|" not in raw:
            continue
        task, state = (part.strip() for part in raw.split("|", 2)[:2])
        word = normalize_slurm_state(state)
        kind, message = _WORDS.get(word, (RUNNING, None))
        status = FarStatus(state=kind, stage=word, message=message)
        if "[" in task:  # 123_[0-2,5] or 123_[0-19%4]
            head, _, span = task.partition("_[")
            for part in span.rstrip("]").split("%")[0].split(","):
                lo, _, hi = part.partition("-")
                for i in range(int(lo), int(hi or lo) + 1):
                    found.setdefault(f"{head}_{i}", status)
        else:
            found[task] = status
    return found


class SlurmTarget:
    def __init__(self, cluster: HpcClusterConfig, shell: Shell) -> None:
        cluster.validate()
        self.cluster, self.shell = cluster, shell

    def _dir(self, job_key: str) -> str:
        return self.cluster.remote_workdir(job_key)

    def _run(self, argv: list[str]) -> str:
        code, out, err = self.shell.run(argv)
        if code:
            raise SlurmError(f"{argv[0]} failed on {self.cluster.name} ({code}): {(err or out).strip()[:300]}")
        return out

    def send(self, local_dir: str | Path, job_key: str) -> str:
        """Put the package's files into the run's folder (a few tars, not a file per page)."""
        base = Path(local_dir)
        remote = self._dir(job_key)
        files = sorted(p for p in base.rglob("*") if p.is_file())
        dirs = sorted({str(Path(remote, p.relative_to(base).parent)) for p in files})
        self._run(["mkdir", "-p", *dirs])
        for path in files:
            self.shell.put(path, f"{remote}/{path.relative_to(base).as_posix()}")
        return remote

    def submit(self, job_key: str, *, script: str) -> str:
        """Write the sbatch script beside the package and submit it; returns the array's id."""
        path = f"{self._dir(job_key)}/_fichero/read.sbatch"
        self.shell.put_text(script, path)
        out = self._run(["sbatch", "--parsable", path]).strip().split(";")[0]
        if not out.isdigit():
            raise SlurmError(f"sbatch gave no job id: {out[:100]!r}")
        return out

    def statuses(self, array_id: str) -> dict[str, FarStatus]:
        """Every task of one array, in ONE `sacct` call."""
        return parse_sacct(self._run(["sacct", "-j", array_id, "-X", "-P", "-n", "-o", "JobID,State"]))

    def status(self, far_id: str) -> FarStatus:
        found = self.statuses(far_id.split("_")[0])
        if far_id not in found:
            raise SlurmError(f"Slurm does not know {far_id} (yet)")
        return found[far_id]

    def fetch_part(self, job_key: str, part: str, local_dir: str | Path) -> Path:
        """Bring one shard's results home: the tar its task wrote beside the package."""
        local = Path(local_dir)
        local.mkdir(parents=True, exist_ok=True)
        self.shell.get(f"{self._dir(job_key)}/out/{part}.tar", local / f"{part}.tar")
        return local

    def last_lines(self, far_id: str, n: int = 40, *, job_key: str | None = None) -> list[str]:
        """The task's own log (`slurm-<array>_<task>.out` in the run's folder)."""
        if job_key is None:
            return []
        log = f"{self._dir(job_key)}/slurm-{far_id}.out"
        return self._run(["tail", "-n", str(n), log]).splitlines()

    def cancel(self, far_id: str) -> None:
        self._run(["scancel", far_id])

    def price_per_hour(self, flavor: str) -> float | None:
        return None  # a cluster allocation is not bought by the hour (outside the spend cap)


class NoKey(RuntimeError):
    """No private key to connect with: refused by name, never a password prompt or another key."""


class SshShell:
    """The login connection, by the system `ssh` binary (stdlib, no dependency): one ControlMaster
    connection is reused by every call (`compute.connect.one-connection-reused`), so a second factor is
    asked once, when the master is opened, and never again for the session.

    ponytail: the master is opened by `open_master()`, which needs the person's second factor answered where
    ssh asks (a terminal or SSH_ASKPASS); passing the prompt through the app is the upgrade, not built.
    """

    def __init__(self, cluster: HpcClusterConfig, key: Path, control_dir: Path, *, ssh: str = "ssh") -> None:
        if not Path(key).is_file():
            raise NoKey(f"no key at {key}: make one in Settings (Compute) and add its public half in CCDB")
        self.cluster, self.ssh = cluster, ssh
        self._key, self._control_dir = Path(key), Path(control_dir)

    def _ssh(self, remote: str, **kw) -> "subprocess.CompletedProcess":
        if "stdout" not in kw:
            kw.setdefault("capture_output", True)
        return subprocess.run(
            build_ssh_command(self.cluster, remote, key=self._key, control_dir=self._control_dir, ssh=self.ssh), **kw)

    def open_master(self) -> None:
        done = self._ssh("true", timeout=300)
        if done.returncode:
            raise SlurmError(f"could not connect to {self.cluster.name}: {done.stderr.decode(errors='replace').strip()[:300]}")

    def run(self, argv: list[str]) -> tuple[int, str, str]:
        done = self._ssh(" ".join(shlex.quote(a) for a in argv))
        return done.returncode, done.stdout.decode(errors="replace"), done.stderr.decode(errors="replace")

    def put_text(self, text: str, remote: str) -> None:
        self._put(text.encode(), remote)

    def put(self, local: Path, remote: str) -> None:
        with open(local, "rb") as f:
            self._put(f, remote)

    def _put(self, src, remote: str) -> None:
        done = self._ssh(f"cat > {shlex.quote(remote)}", **({"input": src} if isinstance(src, bytes) else {"stdin": src}))
        if done.returncode:
            raise SlurmError(f"could not write {remote}: {done.stderr.decode(errors='replace').strip()[:300]}")

    def get(self, remote: str, local: Path) -> None:
        with open(local, "wb") as f:
            done = self._ssh(f"cat {shlex.quote(remote)}", stdout=f, stderr=subprocess.PIPE)
        if done.returncode:
            raise SlurmError(f"could not read {remote}: {done.stderr.decode(errors='replace').strip()[:300]}")
