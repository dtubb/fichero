"""The Kraken trainer runs every base with one schedule and an epoch ceiling (#5448), tested to the spec
(docs/contributor_manual/specs/compute/jobs-and-fine-tuning.md): `compute.tune.kraken-schedule-is-fixed`.

The public surface is the script Fichero ships to the Hugging Face Job (`training/hf_kraken_train.py`), run as the
Job runs it, with a stand-in `ketos` on PATH that records the command it was given.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import fichero_server.training as training

TRAINER = Path(training.__file__).parent / "hf_kraken_train.py"


def _run(tmp_path: Path, *extra: str) -> list[str]:
    data = tmp_path / "data"
    (data / "base").mkdir(parents=True)
    (data / "page.xml").write_text("<PcGts/>")
    (data / "base" / "medium.safetensors").write_bytes(b"x")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen = tmp_path / "argv.json"
    fake = bin_dir / "ketos"
    fake.write_text(f"#!{sys.executable}\nimport json, sys\njson.dump(sys.argv[1:], open({str(seen)!r}, 'w'))\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    subprocess.run([sys.executable, str(TRAINER), "--data", str(data), "--out", str(tmp_path / "out"),
                    "--device", "cpu", *extra], check=True, env=env)
    return json.loads(seen.read_text())


def _value(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_compute_tune_kraken_schedule_is_fixed__from_a_base(tmp_path):
    """compute.tune.kraken-schedule-is-fixed: "a Kraken fine-tune runs with the same learning-rate schedule
    (constant) and a ceiling on epochs (50, early stopping inside it) whatever schedule its base reader carries"
    -- the PP-OCRv6 base's cosine schedule with no ceiling made ketos stop at once (#5448)."""
    argv = _run(tmp_path, "--base", "medium.safetensors")
    assert _value(argv, "--schedule") == "constant"
    assert _value(argv, "-N") == "50" and _value(argv, "-q") == "early"
    assert _value(argv, "-i").endswith("base/medium.safetensors")


def test_compute_tune_kraken_schedule_is_fixed__from_nothing(tmp_path):
    """compute.tune.kraken-schedule-is-fixed: the same schedule and ceiling when there is no base."""
    argv = _run(tmp_path)
    assert _value(argv, "--schedule") == "constant" and _value(argv, "-N") == "50" and "-i" not in argv
