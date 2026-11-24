"""One trainer in three places, proven on Hugging Face first, the cheapest place first
(`compute.tune.one-trainer-three-places`, `compute.tune.proven-on-huggingface-first`, `compute.tune.where-cheapest-first`).

No Job is submitted and nothing is bought: "the image" is the same package entry run as a child process with the
arguments the Job would get; Hugging Face is only asked what it WOULD be sent (`HfApi` replaced at the boundary).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from fichero_server.training import one_trainer, tune_places
from fichero_server.training.hf_jobs import HfJobsTarget, job_root, package_args
from tests.unit.training.test_hf_jobs_target import FakeApi

HERE = Path(__file__).resolve().parents[3]


def stub_trainer(data: Path, out: Path, say) -> dict:
    """Two epochs over the set's lines; the 'model' is a file; it reads the held-out lines back with one slip."""
    lines = sorted((data / "lines.txt").read_text(encoding="utf-8").splitlines())
    for epoch in (1, 2):
        say(f"epoch {epoch} of 2 over {len(lines)} lines")
    (out / "model.bin").write_bytes(b"model:" + "|".join(lines).encode())
    held = (data / "held_out.txt").read_text(encoding="utf-8").splitlines()
    return {"model": "model.bin", "held_out": [(t, t.replace("a", "o", 1)) for t in held]}


def _set(root: Path) -> Path:
    data = root / "data"
    data.mkdir(parents=True)
    (data / "lines.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (data / "held_out.txt").write_text("banana\ncabana\n", encoding="utf-8")
    return data


def _timings_out(log: str) -> str:
    return "\n".join(line for line in log.splitlines() if not line.startswith("time "))


def test_the_same_set_here_and_through_the_job_gives_the_same_log_and_cer(tmp_path):
    data = _set(tmp_path / "a")
    here = one_trainer.run_package(data, tmp_path / "here", stub_trainer)

    # what the Job is sent, run as the image would run it (a child process, the same package entry)
    api = FakeApi()
    target = HfJobsTarget(token="hf_x", api=api)
    args = package_args("job-1", trainer="tests.unit.training.test_hf_trainer_in_the_image:stub_trainer")
    target.submit("job-1", script_args=args, script=one_trainer.PACKAGE)
    (_, sent, kw), = [c for c in api.calls if c[0] == "run_uv_job"]
    assert kw["script_args"] == args and f"--data {job_root('job-1')}/data" in " ".join(args)
    mapped = [a.replace(job_root("job-1"), str(tmp_path / "job")) for a in args]
    _set(tmp_path / "job")
    done = subprocess.run([sys.executable, "-m", "fichero_server.training.one_trainer", *mapped], cwd=HERE,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr

    log_here = (tmp_path / "here" / "train.log").read_text(encoding="utf-8")
    log_job = (tmp_path / "job" / "out" / "train.log").read_text(encoding="utf-8")
    assert re.search(r"^time ", log_here, re.M) and _timings_out(log_here) == _timings_out(log_job)
    scores = json.loads((tmp_path / "job" / "out" / "scores.json").read_text(encoding="utf-8"))
    assert scores["cer"] == here["cer"] == pytest.approx(2 / 12) and scores["lines"] == 2
    assert (tmp_path / "here" / "model.bin").read_bytes() == (tmp_path / "job" / "out" / "model.bin").read_bytes()


def test_a_trainer_that_returns_no_held_out_lines_fails_loudly(tmp_path):
    data = _set(tmp_path)
    (data / "held_out.txt").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no held-out lines"):
        one_trainer.run_package(data, tmp_path / "out", stub_trainer)


def _run(date, cer, digest="sha256:abc", hardware="t4-small"):
    return {"date": date, "image_digest": digest, "hardware": hardware, "cer": cer}


def test_two_runs_within_the_band_prove_the_recipe_and_the_proof_is_in_the_file(tmp_path):
    recipe = tmp_path / "kraken.recipe.json"
    recipe.write_text(json.dumps({"kind": "train-kraken-recognition", "epochs": 2}), encoding="utf-8")
    runs = [_run("2026-11-20", 0.052), _run("2026-11-22", 0.055)]
    proof = tune_places.record_proof(recipe, runs, band=0.01)
    stored = json.loads(recipe.read_text(encoding="utf-8"))
    assert stored["proven_on_huggingface"] == proof and proof["runs"] == runs and proof["band"] == 0.01
    assert stored["epochs"] == 2  # the rest of the recipe is as it was
    assert tune_places.cluster_offer(recipe) == {"offered": True, "note": None}


def test_runs_outside_the_band_or_too_few_prove_nothing_and_a_cluster_is_told_so(tmp_path):
    recipe = tmp_path / "r.recipe.json"
    recipe.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not within the band"):
        tune_places.record_proof(recipe, [_run("2026-11-20", 0.05), _run("2026-11-22", 0.09)], band=0.01)
    with pytest.raises(ValueError, match="two runs"):
        tune_places.record_proof(recipe, [_run("2026-11-20", 0.05)], band=0.01)
    assert json.loads(recipe.read_text(encoding="utf-8")) == {}  # nothing was written
    assert tune_places.cluster_offer(recipe) == {"offered": True, "note": "not yet proven on Hugging Face"}
    with pytest.raises(ValueError, match="image digest"):
        tune_places.record_proof(recipe, [_run("2026-11-20", 0.05, digest=""), _run("2026-11-22", 0.05)], band=0.01)


def test_a_kraken_card_that_fits_this_mac_trains_here_and_a_3b_lora_goes_to_huggingface():
    mac = tune_places.Mac(memory_gb=16, embedder_gb=2)
    kraken = tune_places.choose_place(tune_places.Card("kraken", needs_gb=4), mac, bound={"gpu-service": "huggingface-jobs"})
    assert kraken["place"] == "this-mac" and "4 GB" in kraken["reason"] and "14 GB" in kraken["reason"]
    lora = tune_places.choose_place(tune_places.Card("3B LoRA", needs_gb=24), mac, bound={"gpu-service": "huggingface-jobs"})
    assert lora["place"] == "huggingface-jobs" and "24 GB" in lora["reason"] and "does not fit" in lora["reason"]


def test_without_a_gpu_service_it_is_the_cluster_and_with_neither_it_is_refused():
    mac = tune_places.Mac(memory_gb=16, embedder_gb=2)
    big = tune_places.Card("3B LoRA", needs_gb=24)
    assert tune_places.choose_place(big, mac, bound={"cluster": "rorqual"})["place"] == "rorqual"
    with pytest.raises(ValueError, match="no place"):
        tune_places.choose_place(big, mac, bound={})


def test_a_costlier_place_is_chosen_only_with_the_evidence_shown():
    mac = tune_places.Mac(memory_gb=16, embedder_gb=2)
    card = tune_places.Card("kraken", needs_gb=4)
    bound = {"gpu-service": "huggingface-jobs"}
    chosen = tune_places.choose_place(card, mac, bound=bound, evidence={"huggingface-jobs": {"cer": 0.04, "cost_usd": 1.2}})
    assert chosen["place"] == "this-mac"  # evidence for a costlier place does not move a card that fits here
    shown = chosen["costlier_evidence"]
    assert shown == {"huggingface-jobs": {"cer": 0.04, "cost_usd": 1.2}}
    moved = tune_places.choose_place(card, mac, bound=bound, prefer="huggingface-jobs",
                                     evidence={"huggingface-jobs": {"cer": 0.04, "cost_usd": 1.2}})
    assert moved["place"] == "huggingface-jobs" and "cer 0.04" in moved["reason"]
    with pytest.raises(ValueError, match="evidence"):
        tune_places.choose_place(card, mac, bound=bound, prefer="huggingface-jobs")
