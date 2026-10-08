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
#: ketos's own batch size (lines a step), used where nothing smaller has been measured.
KETOS_BATCH = 16
#: ponytail: measured ceilings only, by hardware (#5527). Both T4 flavours are one 16 GB T4; PP-OCRv6's medium
#: base ran it out of memory at 16 (job f3923a0e, 2026-10-06), so 8 there. Add a row only from a measured run.
KRAKEN_BATCH_BY_FLAVOR = {"t4-small": 8, "t4-medium": 8}
#: What a Job's log says when the GPU ran out of memory (torch's error and its older message).
_OOM_MARKS = ("OutOfMemoryError", "CUDA out of memory")
#: What a Job needs the token to allow (fine-grained token permissions).
NEEDED_PERMISSIONS = {"job.write": "run Jobs", "repo.write": "write to your repositories and buckets"}
APP_SUPPLIED = "the token the app supplied"

#: Hugging Face's stages, in the words a job row carries.
DONE, FAILED, CANCELLED, WAITING, RUNNING = "done", "failed", "cancelled", "waiting", "running"
_STAGES = {"COMPLETED": DONE, "ERROR": FAILED, "CANCELED": CANCELLED, "DELETED": CANCELLED,
           "SCHEDULING": WAITING, "RUNNING": RUNNING}


class NoHuggingFaceToken(RuntimeError):
    """No Hugging Face token is set in Fichero."""


class HuggingFaceTokenRejected(NoHuggingFaceToken):
    """Hugging Face refused the token Fichero used, or it lacks a permission the work needs (#5526). A
    kind of `NoHuggingFaceToken`: no usable token, refused before anything is sent where it can be."""


def kraken_batch(flavor: str, asked: int | None) -> int:
    """The batch a Kraken training runs at: the one asked for, else the measured ceiling for this hardware."""
    return asked or KRAKEN_BATCH_BY_FLAVOR.get(flavor, KETOS_BATCH)


def ran_out_of_gpu_memory(lines: list[str]) -> bool:
    return any(mark in line for line in lines for mark in _OOM_MARKS)


def token_source(token: str) -> str:
    """Where the token in use came from, in words (#5526): the app's push wins over the Keychain."""
    from fichero_server.security.provider_keys import supplied_api_key

    if supplied_api_key("huggingface") == token:
        return APP_SUPPLIED
    return "the token in the Keychain" if _keychain_token() == token else "the token in the environment"


def _keychain_token() -> str | None:
    """The Keychain's Hugging Face token, read only to say whether it differs; never used in its place."""
    try:
        from fichero_server.security.keychain import get_api_key

        return get_api_key("huggingface")
    except Exception:  # noqa: BLE001 -- only for the words of a refusal
        return None


def _refused(exc: BaseException) -> bool:
    return getattr(getattr(exc, "response", None), "status_code", None) in (401, 403)


def _lacks(whoami: dict[str, Any]) -> list[str]:
    """The permissions the work needs that this token's answer to `whoami` does not grant. An answer that
    carries no role (an older service) is not refused on a guess."""
    access = (whoami.get("auth") or {}).get("accessToken") or {}
    role = access.get("role")
    if role in (None, "write", "admin"):
        return []
    if role != "fineGrained":
        return list(NEEDED_PERMISSIONS)
    grants = access.get("fineGrained") or {}
    have = set(grants.get("global") or [])
    for scoped in grants.get("scoped") or []:
        if (scoped.get("entity") or {}).get("name") == whoami.get("name"):
            have |= set(scoped.get("permissions") or [])
    return [p for p in NEEDED_PERMISSIONS if p not in have]


def cannot_reach(exc: BaseException) -> bool:
    """Whether this failure means THIS engine cannot reach Hugging Face for the person (no token it
    can read, or one the service refuses), as against the Job itself failing (#5449). An engine that
    adopts a library whose Job it cannot reach must not fail the row: the Job may still be running."""
    if isinstance(exc, NoHuggingFaceToken):
        return True
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) in (401, 403)


def out_of_reach_reason(what: str) -> str:
    """The row's words when this engine cannot follow a Job that may still run there."""
    return (f"Needs attention: this engine can't read the Hugging Face token, so it can't follow {what} "
            "here. It may still be running (and costing) on Hugging Face: add the token in Settings (AI "
            "providers, Hugging Face), or follow or stop it from a Fichero that has it.")


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

    def check_token(self) -> str:
        """Ask Hugging Face who this token is and whether it may run Jobs and write the bucket, before
        anything is prepared (#5526); returns the account name. Refused with words: which token was used,
        what it lacks, and, when the app's token is refused while the Keychain holds a different one the
        service accepts, both. The other token is never used instead (raise, never fall back)."""
        try:
            me = self.api.whoami(token=self.token)
        except Exception as exc:
            if not _refused(exc):
                raise
            raise self.rejected(exc) from exc
        if lacks := _lacks(me):
            raise HuggingFaceTokenRejected(
                f"Hugging Face rejected the token for training: it accepts {token_source(self.token)} (account "
                f"{me.get('name')}), but that token may not " + " or ".join(NEEDED_PERMISSIONS[p] for p in lacks)
                + f" ({', '.join(lacks)} missing). Give it those permissions on huggingface.co, or save one that "
                "has them in Settings (AI providers, Hugging Face).")
        self._namespace = me["name"]
        return self._namespace

    def rejected(self, exc: BaseException) -> HuggingFaceTokenRejected:
        """The refusal for a token the service refused (HTTP 401/403), in words (#5526)."""
        source = token_source(self.token)
        said = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        words = f"Hugging Face rejected the token: {source} was refused ({said})."
        other = _keychain_token()
        if source == APP_SUPPLIED and other and other != self.token:
            try:
                name = self.api.whoami(token=other).get("name")
            except Exception:  # noqa: BLE001 -- the Keychain's one is only described, never used
                name = None
            if name:
                return HuggingFaceTokenRejected(
                    words + f" The token in the Keychain is a different one and Hugging Face accepts it (account "
                    f"{name}); Fichero does not switch tokens on its own: save the right one in the app's Settings "
                    "(AI providers, Hugging Face) so the app supplies it, then start again.")
        return HuggingFaceTokenRejected(words + " Save a valid token in Settings (AI providers, Hugging Face); it "
                                                "needs permission to run Jobs and to write to your buckets.")

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
               flavor: str = DEFAULT_FLAVOR, timeout: str = DEFAULT_TIMEOUT,
               dependencies: list[str] | None = None, labels: dict[str, str] | None = None) -> str:
        """Start one of Fichero's scripts (a trainer, or the reading runner for one shard) on the sent
        data; returns the Job's id. Every Job of one Fichero job carries its `fichero-job` label."""
        from huggingface_hub import Volume

        if not timeout:
            raise ValueError("a Hugging Face Job needs an explicit time limit (the service's default is 30 minutes)")
        extra = {"dependencies": dependencies} if dependencies else {}
        info = self.api.run_uv_job(
            str(script), script_args=script_args, flavor=flavor, timeout=timeout,
            labels={**(labels or {}), "fichero-job": job_key},
            volumes=[Volume(type="bucket", source=self.bucket, mount_path=MOUNT)],
            token=self.token, **extra,
        )
        return info.id

    def statuses(self, job_key: str) -> dict[str, FarStatus]:
        """Every Job of one Fichero job, in ONE call (`compute.job.poll-is-gentle`): a reading run of a
        hundred shards is not a hundred requests a minute."""
        found: dict[str, FarStatus] = {}
        for info in self.api.list_jobs(token=self.token):
            if (getattr(info, "labels", None) or {}).get("fichero-job") != job_key:
                continue
            stage = str(getattr(info.status.stage, "value", info.status.stage))
            found[info.id] = FarStatus(state=_STAGES.get(stage, RUNNING), stage=stage, message=info.status.message)
        return found

    def fetch_part(self, job_key: str, part: str, local_dir: str | Path) -> Path:
        """Bring one part of the job's `out` folder home (one shard's results)."""
        local = Path(local_dir)
        local.mkdir(parents=True, exist_ok=True)
        self.api.sync_bucket(f"{self._uri(job_key, 'out')}/{part}", str(local), token=self.token)
        return local

    def status(self, far_id: str) -> FarStatus:
        info = self.api.inspect_job(job_id=far_id, token=self.token)
        stage = str(getattr(info.status.stage, "value", info.status.stage))
        return FarStatus(state=_STAGES.get(stage, RUNNING), stage=stage, message=info.status.message)

    def last_lines(self, far_id: str, n: int = 40) -> list[str]:
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


def kraken_args(job_key: str, *, base_file: str | None, model_name: str, batch_size: int = KETOS_BATCH) -> list[str]:
    root = job_root(job_key)
    return ["--data", f"{root}/data", "--out", f"{root}/out", "--base", base_file or "", "--name", model_name,
            "--batch", str(batch_size)]


def lora_args(job_key: str, *, base_repo: str, epochs: int, rank: int, arm: str = "answer",
              all_lines: bool = False) -> list[str]:
    root = job_root(job_key)
    return ["--data", f"{root}/data", "--out", f"{root}/out", "--base", base_repo,
            "--epochs", str(epochs), "--rank", str(rank), "--arm", arm, *(["--all-lines"] if all_lines else [])]
