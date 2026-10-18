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

import os
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

    def send(self, local_dir: str | Path, job_key: str, *, into: str = "") -> str:
        """Put the package's files into the run's folder (a few tars, not a file per page), or a folder in it."""
        base = Path(local_dir)
        remote = f"{self._dir(job_key)}/{into}" if into else self._dir(job_key)
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

    def remove(self, job_key: str) -> None:
        """Take the run's folder off the cluster: the downscaled pages, the package and what came back. Only ever one
        run's own folder: a key that is empty or names another folder is refused, never removed."""
        if not job_key or "/" in job_key or job_key in (".", ".."):
            raise ValueError(f"not a run's key: {job_key!r}")
        self._run(["rm", "-rf", self._dir(job_key)])

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

    def _ssh(self, remote: str, *, batch: bool = True, **kw) -> "subprocess.CompletedProcess":
        if "stdout" not in kw:
            kw.setdefault("capture_output", True)
        return subprocess.run(build_ssh_command(self.cluster, remote, key=self._key, control_dir=self._control_dir,
                                                ssh=self.ssh, batch=batch), **kw)

    def open_master(self, *, prompts=None, timeout: float = 300) -> None:
        """Open the one connection. With `prompts` (a `PromptBroker`) ssh may ask for the second factor: its own
        prompt text goes to the app through the broker and the answer is not kept."""
        if prompts is None:
            done = self._ssh("true", timeout=timeout)
        else:
            from fichero_server.remote_read.ssh_prompts import AskpassServer

            mark = len(prompts.log)
            # the prompt gives up a little before the whole attempt does, so its reason can be told
            server = AskpassServer(prompts, timeout=timeout - min(10.0, timeout * 0.5))
            try:
                done = self._ssh("true", batch=False, timeout=timeout, env={**os.environ, **server.env()})
            except subprocess.TimeoutExpired as exc:
                raise SlurmError(f"the sign-in to {self.cluster.name} timed out after {timeout:g} s") from exc
            finally:
                server.close()
            if done.returncode and any(reason == "expired" for _id, reason in prompts.log[mark:]):
                raise SlurmError(f"the sign-in to {self.cluster.name} expired before the prompt was answered: "
                                 "sign in again and answer within the time")
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


def _walltime(timeout: str) -> str:
    """`2h` / `90m` / `01:30:00` → Slurm's HH:MM:SS."""
    if timeout.endswith(("h", "m")):
        minutes = int(timeout[:-1]) * (60 if timeout.endswith("h") else 1)
        return f"{minutes // 60:02d}:{minutes % 60:02d}:00"
    return timeout


class SlurmReadTarget(SlurmTarget):
    """`SlurmTarget` in the shape `remote_read/job.py` drives (`target='cluster'`): the loop sends a shard at
    a time, so each is its own single-task `sbatch --array=<n>` (id `<job>_<n>`, Slurm's own), the loop's
    `max_in_flight` throttles, and a finished shard's results come home as the folder `land()` reads.

    ponytail: `flavor` means nothing on a cluster (one GPU a task); the site's own gres is the cluster's setting."""

    def __init__(self, cluster: HpcClusterConfig, shell: Shell) -> None:
        super().__init__(cluster, shell)
        self._package = None
        self._sent: dict[str, list[str]] = {}  # job_key → the Slurm job ids submitted

    def send(self, local_dir: str | Path, job_key: str) -> str:
        import json

        from fichero_server.remote_read.package import ReadPackage

        job = json.loads((Path(local_dir) / "job.json").read_text(encoding="utf-8"))
        self._package = ReadPackage(job_id=job_key, sources=job["sources"], shards=job["shards"])
        return super().send(local_dir, job_key)

    def submit(self, job_key: str, *, script: str = "", flavor: str = "", timeout: str = "2h",
               script_args=None, dependencies=None, labels: dict[str, str] | None = None) -> str:
        from fichero_server.remote_read.slurm import describe_slurm_read

        shard = int((labels or {})["fichero-shard"])
        spec = describe_slurm_read(self.cluster, self._package, shards=[shard], time_limit=_walltime(timeout)).spec
        name = f"shard-{shard:05d}"
        # the runner leaves a folder; one tar of it is what comes home in one transfer
        text = spec.sbatch_script.rstrip("\n") + f"\ntar -C out/{name} -cf out/{name}.tar .\n"
        self.shell.put_text(text, f"{self._dir(job_key)}/_fichero/read-{shard}.sbatch")
        out = self._run(["sbatch", "--parsable", f"{self._dir(job_key)}/_fichero/read-{shard}.sbatch"])
        job_id = out.strip().split(";")[0]
        if not job_id.isdigit():
            raise SlurmError(f"sbatch gave no job id: {job_id[:100]!r}")
        self._sent.setdefault(job_key, []).append(job_id)
        return f"{job_id}_{shard}"

    def statuses(self, job_key: str) -> dict[str, FarStatus]:
        ids = ",".join(dict.fromkeys(self._sent.get(job_key, [])))
        return parse_sacct(self._run(["sacct", "-j", ids, "-X", "-P", "-n", "-o", "JobID,State"])) if ids else {}

    def last_lines(self, far_id: str, n: int = 40, *, job_key: str | None = None) -> list[str]:
        return super().last_lines(far_id, n, job_key=job_key or next(reversed(self._sent), None))

    def fetch_part(self, job_key: str, part: str, local_dir: str | Path) -> Path:
        import tarfile

        local = Path(local_dir)
        local.mkdir(parents=True, exist_ok=True)
        tar_path = local.with_suffix(".tar")
        self.shell.get(f"{self._dir(job_key)}/out/{part}.tar", tar_path)
        with tarfile.open(tar_path) as tar:
            tar.extractall(local, filter="data")
        tar_path.unlink()
        return local


class SlurmTrainTarget(SlurmTarget):
    """`SlurmTarget` in the shape `training/job.py` drives (`TrainKrakenRequest.target` a cluster's id, #5769): the
    training set goes to the run's `data/`, ONE GPU job runs Fichero's own trainer inside the server image with the
    runs folder bound as `/work` (so the trainer's paths are the ones it has on Hugging Face), and `out/` comes home
    as one tar the job writes as its last line.

    ponytail: Kraken only; the vision LoRA needs the Hub's base weights staged first (compute nodes are offline)."""

    def _runs(self) -> str:
        return self._dir(".").rsplit("/", 1)[0]

    def check_token(self) -> str:
        return self.cluster.name  # the key and the sign-in are the target's own (#5238)

    def rejected(self, exc: BaseException) -> Exception:
        return SlurmError(f"{self.cluster.name} refused it: {exc}")

    def cheapest(self, flavors) -> str:
        return ""  # one GPU a job; the site's gres is the cluster's setting

    def send(self, local_dir: str | Path, job_key: str, *, into: str = "data") -> str:
        return super().send(local_dir, job_key, into=into)

    def submit(self, job_key: str, *, script_args: list[str], script: Path, flavor: str = "", timeout: str = "4h",
               dependencies=None, labels=None) -> str:
        from fichero_server.remote_read.slurm import image_path
        from fichero_server.workflows.remote_jobs import SlurmJobConfig, build_slurm_script

        here, script = self._dir(job_key), Path(script)
        self.shell.put(script, f"{here}/_fichero/{script.name}")
        command = ["apptainer", "exec", "--nv", "--bind", f"{self._runs()}:/work", image_path(self.cluster), "python",
                   f"/work/{job_key}/_fichero/{script.name}", *script_args]
        config = SlurmJobConfig(job_name=f"fichero-train-{job_key[:8]}", partition=self.cluster.partition,
                                account=self.cluster.account, time_limit=_walltime(timeout), cpus_per_task=8,
                                mem_gb=32, gpus=1, extra_sbatch_lines=[f"#SBATCH --output={self._runs()}/slurm-%j.out"])
        text = build_slurm_script(config=config, remote_workdir=here, runner_command=command).rstrip("\n")
        self.shell.put_text(text + "\ntar -C out -cf out.tar .\n", f"{here}/_fichero/train.sbatch")
        job_id = self._run(["sbatch", "--parsable", f"{here}/_fichero/train.sbatch"]).strip().split(";")[0]
        if not job_id.isdigit():
            raise SlurmError(f"sbatch gave no job id: {job_id[:100]!r}")
        return job_id

    def last_lines(self, far_id: str, n: int = 40, *, job_key: str | None = None) -> list[str]:
        try:
            return self._run(["tail", "-n", str(n), f"{self._runs()}/slurm-{far_id}.out"]).splitlines()
        except SlurmError:
            return []  # no log yet: the failure's own words still say why

    def fetch(self, job_key: str, local_dir: str | Path) -> Path:
        import tarfile

        local = Path(local_dir)
        local.mkdir(parents=True, exist_ok=True)
        tar_path = local.with_suffix(".tar")
        self.shell.get(f"{self._dir(job_key)}/out.tar", tar_path)
        with tarfile.open(tar_path) as tar:
            tar.extractall(local, filter="data")
        tar_path.unlink()
        return local
