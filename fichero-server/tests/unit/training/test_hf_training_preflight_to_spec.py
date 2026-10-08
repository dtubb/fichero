"""Training on Hugging Face checks the token first and sizes the Kraken batch to the GPU (#5526, #5527;
`compute.tune.hf-token-checked-first`, `compute.tune.kraken-batch-fits-the-gpu`).

`HfApi` and the Hub are replaced at the boundary; no network, no real token. The Keychain and the app's
supplied keys are replaced too, so nothing here reads the person's real token.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_server.training import hf_jobs
from fichero_server.training import job as training_job
from fichero_server.training.hf_jobs import HfJobsTarget, HuggingFaceTokenRejected, NoHuggingFaceToken
from tests.unit.training.test_hf_jobs_target import FakeApi
from tests.unit.training.test_training_job import (  # noqa: F401  (fixtures)
    FakeHub, _request, _start, _subject, isolated, notebook,
)

APP_TOKEN, KEYCHAIN_TOKEN = "hf_app_stale", "hf_keychain_good"


class Refused(Exception):
    """What huggingface_hub raises for a refused token: an HTTP error carrying the response."""

    def __init__(self, message="Invalid user token.", status=401):
        super().__init__(message)
        self.response = type("R", (), {"status_code": status})()


class TokenApi(FakeApi):
    """Answers `whoami` per token: refused, or an account with the given access."""

    def __init__(self, answers):
        super().__init__()
        self.answers = answers

    def whoami(self, **kw):
        self._record("whoami", **kw)
        answer = self.answers[kw["token"]]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _account(role="fineGrained", scoped=("repo.write", "job.write"), name="historian"):
    access = {"role": role}
    if role == "fineGrained":
        access["fineGrained"] = {"global": ["discussion.write"],
                                 "scoped": [{"entity": {"type": "user", "name": name}, "permissions": list(scoped)}]}
    return {"name": name, "auth": {"type": "access_token", "accessToken": access}}


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    """Where each token comes from: none supplied, none in the Keychain, unless a test says so."""
    where = {"supplied": None, "keychain": None}
    monkeypatch.setattr("fichero_server.security.provider_keys.supplied_api_key",
                        lambda provider: where["supplied"] if provider == "huggingface" else None)
    monkeypatch.setattr("fichero_server.security.keychain.get_api_key",
                        lambda provider: where["keychain"] if provider == "huggingface" else None)
    return where


# --- compute.tune.hf-token-checked-first ------------------------------------------------------------------


def test_a_stale_app_token_is_refused_in_words_naming_both_tokens_and_never_swapped(tokens):
    """WHY (#5526): Sergio's runs failed after ten minutes with "Invalid user token." while the Keychain
    held a valid one. The refusal must say it was the app's token, that the Keychain's differs and is
    accepted, and Fichero must not quietly train with the other one (raise, never fall back)."""
    tokens.update(supplied=APP_TOKEN, keychain=KEYCHAIN_TOKEN)
    api = TokenApi({APP_TOKEN: Refused(), KEYCHAIN_TOKEN: _account()})
    target = HfJobsTarget(token=APP_TOKEN, api=api)

    with pytest.raises(HuggingFaceTokenRejected) as refused:
        target.check_token()
    words = str(refused.value)
    assert words.startswith("Hugging Face rejected the token")
    assert "the token the app supplied" in words and "Invalid user token." in words
    assert "Keychain" in words and "accepts it" in words and "historian" in words
    assert APP_TOKEN not in words and KEYCHAIN_TOKEN not in words, "a token is never written out"
    assert target.token == APP_TOKEN, "the other token is described, never used"


def test_a_refused_keychain_token_says_it_was_the_keychains(tokens):
    tokens.update(keychain=KEYCHAIN_TOKEN)
    target = HfJobsTarget(token=KEYCHAIN_TOKEN, api=TokenApi({KEYCHAIN_TOKEN: Refused()}))
    with pytest.raises(HuggingFaceTokenRejected, match="the token in the Keychain was refused"):
        target.check_token()


def test_a_token_that_may_not_run_jobs_is_refused_with_what_it_lacks(tokens):
    """WHY: a read-only or narrow fine-grained token passes `whoami` and fails only at sending; the
    refusal names the permission and what it is for."""
    tokens.update(keychain=KEYCHAIN_TOKEN)
    narrow = HfJobsTarget(token=KEYCHAIN_TOKEN, api=TokenApi({KEYCHAIN_TOKEN: _account(scoped=("repo.write",))}))
    with pytest.raises(HuggingFaceTokenRejected, match=r"may not run Jobs \(job\.write missing\)") as refused:
        narrow.check_token()
    assert "the token in the Keychain" in str(refused.value)

    read_only = HfJobsTarget(token=KEYCHAIN_TOKEN, api=TokenApi({KEYCHAIN_TOKEN: _account(role="read")}))
    with pytest.raises(HuggingFaceTokenRejected, match="job.write, repo.write missing"):
        read_only.check_token()


def test_a_token_that_may_do_the_work_passes_and_names_the_account(tokens):
    for answer in (_account(), _account(role="write"), {"name": "historian"}):
        assert HfJobsTarget(token=APP_TOKEN, api=TokenApi({APP_TOKEN: answer})).check_token() == "historian"


def test_a_refused_token_is_a_missing_usable_token_to_the_routes():
    """The routes answer `NoHuggingFaceToken` with 412 and the out-of-reach rule counts it as unreachable."""
    assert issubclass(HuggingFaceTokenRejected, NoHuggingFaceToken)
    assert hf_jobs.cannot_reach(HuggingFaceTokenRejected("x"))


class RefusingHub(FakeHub):
    """A Hub whose token check passes `passes` times, then refuses."""

    def __init__(self, passes=0, refuse_at_send=False, **kw):
        super().__init__(**kw)
        self.passes, self.refuse_at_send, self.checks = passes, refuse_at_send, 0

    def check_token(self):
        self.checks += 1
        if self.checks > self.passes:
            raise HuggingFaceTokenRejected("Hugging Face rejected the token: the token the app supplied was refused")
        return "historian"

    def rejected(self, exc):
        return HuggingFaceTokenRejected(f"Hugging Face rejected the token: the token the app supplied was refused ({exc})")

    def send(self, local_dir, job_key):
        if self.refuse_at_send:
            raise Refused()
        super().send(local_dir, job_key)


def test_a_refused_token_queues_nothing(db, notebook):
    with pytest.raises(HuggingFaceTokenRejected):
        _start(db, notebook, RefusingHub())
    assert db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ?", [training_job.KIND])[0] == 0


def test_a_token_refused_when_the_job_runs_ends_it_before_preparing(db, notebook):
    """WHY (#5526): the token is checked again when the job is taken up (it may have changed while it
    waited), before minutes of preparing; nothing is prepared or sent."""
    hub = RefusingHub(passes=1)
    started = _start(db, notebook, hub)
    with pytest.raises(HuggingFaceTokenRejected, match="rejected the token"):
        training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    phases = [h["phase"] for h in training_job.status(db, started["job_id"])["history"]]
    assert "preparing" not in phases and hub.sent == [] and hub.submitted == []


def test_a_token_refused_at_sending_says_the_token_not_a_failed_job(db, notebook):
    hub = RefusingHub(passes=2, refuse_at_send=True)
    started = _start(db, notebook, hub)
    with pytest.raises(HuggingFaceTokenRejected, match=r"^Hugging Face rejected the token.*Invalid user token"):
        training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)


# --- compute.tune.kraken-batch-fits-the-gpu ---------------------------------------------------------------


def _batch_sent(hub):
    args = hub.submitted[0]["script_args"]
    return int(args[args.index("--batch") + 1])


@pytest.mark.parametrize(("over", "expected"), [
    ({}, 8),                               # a 16 GB T4: measured to run out at 16 (#5527)
    ({"batch_size": 4}, 4),                # asked: as asked, like training on this Mac
    ({"flavor": "a10g-large"}, 16),        # nothing measured: ketos's own
])
def test_the_batch_is_asked_or_sized_to_the_gpu_and_on_the_row(db, notebook, over, expected):
    hub = FakeHub()
    started = _start(db, notebook, hub, **over)
    assert started["batch_size"] == expected
    training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)
    assert _batch_sent(hub) == expected
    assert training_job.status(db, started["job_id"])["batch_size"] == expected


def test_a_job_out_of_gpu_memory_says_too_big_at_batch_n(db, notebook):
    """WHY (#5527): an OOM read as a generic failure leaves the person only paying for a bigger GPU;
    it names the hardware, the batch and both ways out, and keeps the service's reason after it."""
    class OomHub(FakeHub):
        def last_lines(self, far_id, n=40):
            return ["Epoch 0", "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 1.2 GiB",
                    "subprocess.CalledProcessError: Command '['ketos', ...]' returned non-zero exit status 1."]

    hub = OomHub(stages=("running", "failed"), message="Job exited with code 1")
    started = _start(db, notebook, hub)
    with pytest.raises(RuntimeError, match=r"^Too big for this GPU \(t4-small\) at batch 8: try a smaller batch or "
                                           r"a larger GPU\. Hugging Face: Job exited with code 1"):
        training_job.run(db, _subject(db, started["job_id"]), target=hub, sleep=lambda s: None)


def test_the_trainer_passes_the_batch_to_ketos(tmp_path):
    """The Job's script runs `ketos train -B <batch>` (a stand-in `ketos` records what it was given)."""
    data, out, bin_dir = tmp_path / "data", tmp_path / "out", tmp_path / "bin"
    for d in (data, bin_dir):
        d.mkdir()
    (data / "p1.xml").write_text("<PcGts/>")
    record = tmp_path / "argv.txt"
    ketos = bin_dir / "ketos"
    ketos.write_text(f"#!/bin/sh\necho \"$@\" > {record}\n")
    ketos.chmod(ketos.stat().st_mode | stat.S_IEXEC)
    script = Path(hf_jobs.TRAINER)
    subprocess.run([sys.executable, str(script), "--data", str(data), "--out", str(out), "--device", "cpu",
                    "--batch", "8"], check=True, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"})
    argv = record.read_text().split()
    assert argv[argv.index("-B") + 1] == "8"
