"""Hugging Face Jobs as a place to train (#5398, `compute.target.add-huggingface`, `compute.transfer.hub-carrier`).

A training set goes up into a PRIVATE bucket of the person's own account (`<namespace>/fichero-training`),
one folder per job: `<job>/data` (the set and its base reader) and `<job>/out` (what the Job writes).
The bucket is mounted into the Job at `/work`, the Job runs Fichero's own trainer script
(`hf_kraken_train.py`), and its output comes home from the same bucket.

The token is the one Fichero holds for the `huggingface` provider (Settings), never a recipe, a file
or the package (`compute.secret.never-in-a-recipe`, `compute.package.no-secrets`): it is passed to
the API client here and nowhere else. The Job always gets an explicit time limit (the service's
default is 30 minutes, `compute.job.costs-shown-where-known`), and the price of its hardware is read
from the service before sending.

`HfApi` is the only boundary: tests replace it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

TRAINER = Path(__file__).with_name("hf_kraken_train.py")
LORA_TRAINER = Path(__file__).with_name("hf_vision_lora_train.py")
BUCKET_NAME = "fichero-training"
MOUNT = "/work"
#: A T4 is plenty for a Kraken reader (~5 M parameters); the price is read before sending.
DEFAULT_FLAVOR = "t4-small"
#: Always explicit: the service ends a Job at 30 minutes unless told otherwise.
DEFAULT_TIMEOUT = "4h"
#: Hardware that fits a 7B vision model's LoRA in bf16 (24 GB of GPU, and enough RAM to load ~15 GB of
#: weights); the cheapest listed is chosen. `a10g-small` is left out: its 15 GB of RAM is less than the
#: bf16 weights it would have to load.
LORA_FLAVORS = ("l4x1", "a10g-large")

#: Hugging Face's stages, in the words a job row carries.
DONE, FAILED, CANCELLED, WAITING, RUNNING = "done", "failed", "cancelled", "waiting", "running"
_STAGES = {"COMPLETED": DONE, "ERROR": FAILED, "CANCELED": CANCELLED, "DELETED": CANCELLED,
           "SCHEDULING": WAITING, "RUNNING": RUNNING}


class NoHuggingFaceToken(RuntimeError):
    """No Hugging Face token is set in Fichero."""


def hf_token() -> str:
    """The token Fichero holds for the `huggingface` provider, or a refusal that says where to add it."""
    from fichero_server.llm import get_api_key

    token = get_api_key("huggingface")
    if not token:
        raise NoHuggingFaceToken(
            "No Hugging Face token: add one in Settings (AI providers, Hugging Face). It needs "
            "permission to run Jobs and to write to your buckets.")
    return token


@dataclass
class FarStatus:
    """Where a Job is, in a job row's words, and the service's own message."""

    state: str
    stage: str
    message: str | None


class HfJobsTarget:
    """One person's Hugging Face account, as a place to send a training set and run a trainer."""

    def __init__(self, token: str | None = None, api: Any | None = None) -> None:
        if api is None:
            import huggingface_hub
            from huggingface_hub import HfApi

            api = HfApi()
            # Buckets and Jobs are recent; an older copy (it arrives through transformers, >=1.5) would
            # fail somewhere inside a run. Refused here by name instead (rule 0).
            if not all(hasattr(api, name) for name in ("sync_bucket", "create_bucket", "run_uv_job")):
                raise RuntimeError(
                    f"huggingface_hub {huggingface_hub.__version__} has no Jobs buckets; training on "
                    "Hugging Face needs a newer huggingface_hub (1.17 is known to work)")
        self.api = api
        self.token = token or hf_token()
        self._namespace: str | None = None

    @property
    def namespace(self) -> str:
        if self._namespace is None:
            self._namespace = self.api.whoami(token=self.token)["name"]
        return self._namespace

    @property
    def bucket(self) -> str:
        return f"{self.namespace}/{BUCKET_NAME}"

    def _uri(self, job_key: str, part: str) -> str:
        return f"hf://buckets/{self.bucket}/{job_key}/{part}"

    def price_per_hour(self, flavor: str) -> float | None:
        """The hardware's price in US dollars an hour, as the service lists it; None when unlisted."""
        for row in self.api.list_jobs_hardware(token=self.token):
            if row.name == flavor:
                per = {"second": 3600, "minute": 60, "hour": 1}.get(str(row.unit_label), None)
                return round(float(row.unit_cost_usd) * per, 4) if per else None
        return None

    def send(self, local_dir: str | Path, job_key: str) -> str:
        """Put a prepared folder into the job's `data` folder in the private bucket."""
        self.api.create_bucket(self.bucket, private=True, exist_ok=True, token=self.token)
        self.api.sync_bucket(str(local_dir), self._uri(job_key, "data"), token=self.token)
        return self._uri(job_key, "data")

    def cheapest(self, flavors: tuple[str, ...] | list[str]) -> str:
        """The flavour among these with the lowest listed price an hour; refused when none is listed."""
        priced = [(price, name) for name in flavors if (price := self.price_per_hour(name)) is not None]
        if not priced:
            raise ValueError(f"none of {', '.join(flavors)} is listed by Hugging Face Jobs")
        return min(priced)[1]

    def submit(self, job_key: str, *, script_args: list[str], script: Path = TRAINER,
               flavor: str = DEFAULT_FLAVOR, timeout: str = DEFAULT_TIMEOUT) -> str:
        """Start one of Fichero's trainer scripts on the sent data; returns the Job's id."""
        from huggingface_hub import Volume

        if not timeout:
            raise ValueError("a Hugging Face Job needs an explicit time limit (the service's default is 30 minutes)")
        info = self.api.run_uv_job(
            str(script), script_args=script_args, flavor=flavor, timeout=timeout,
            labels={"fichero-job": job_key},
            volumes=[Volume(type="bucket", source=self.bucket, mount_path=MOUNT)],
            token=self.token,
        )
        return info.id


    def status(self, far_id: str) -> FarStatus:
        info = self.api.inspect_job(job_id=far_id, token=self.token)
        stage = str(getattr(info.status.stage, "value", info.status.stage))
        return FarStatus(state=_STAGES.get(stage, RUNNING), stage=stage, message=info.status.message)

    def last_lines(self, far_id: str, n: int = 20) -> list[str]:
        return [str(line).rstrip() for line in self.api.fetch_job_logs(job_id=far_id, tail=n, token=self.token)]

    def cancel(self, far_id: str) -> None:
        self.api.cancel_job(job_id=far_id, token=self.token)

    def fetch(self, job_key: str, local_dir: str | Path) -> Path:
        """Bring the job's `out` folder home."""
        local = Path(local_dir)
        local.mkdir(parents=True, exist_ok=True)
        self.api.sync_bucket(self._uri(job_key, "out"), str(local), token=self.token)
        return local


def job_root(job_key: str) -> str:
    """Where a job's folders are, inside the Job."""
    return f"{MOUNT}/{job_key}"


def kraken_args(job_key: str, *, base_file: str | None, model_name: str) -> list[str]:
    root = job_root(job_key)
    return ["--data", f"{root}/data", "--out", f"{root}/out", "--base", base_file or "", "--name", model_name]


def lora_args(job_key: str, *, base_repo: str, epochs: int, rank: int) -> list[str]:
    root = job_root(job_key)
    return ["--data", f"{root}/data", "--out", f"{root}/out", "--base", base_repo,
            "--epochs", str(epochs), "--rank", str(rank)]
