"""One trainer, run the same way in three places (`compute.tune.one-trainer-three-places`, #5119, #5397).

`run_package(data, out, trainer)` is the whole path: it calls the trainer, scores the held-out lines it returns, and
writes `train.log`, `scores.json` and the model file into `out`. This Mac calls it in the engine's process; Hugging Face
Jobs and a cluster run `python one_trainer.py --data D --out O --trainer module:function` (the image's "run a
package" mode, `hf_jobs.package_args`). Same set, same log (timing lines start with `time ` and nothing else varies),
same score.

The trainer is `trainer(data, out, say) -> {"model": <file name in out>, "held_out": [(truth, reading), ...]}`.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

PACKAGE = Path(__file__)

Trainer = Callable[[Path, Path, Callable[[str], None]], dict[str, Any]]


def character_error_rate(pairs: list[tuple[str, str]]) -> float:
    from fichero_server.llm.multilingual import levenshtein_distance

    total = sum(len(truth) for truth, _ in pairs)
    return sum(levenshtein_distance(truth, read) for truth, read in pairs) / total


def run_package(data: Path, out: Path, trainer: Trainer) -> dict[str, Any]:
    data, out = Path(data), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    started = time.monotonic()

    def say(line: str) -> None:
        log.append(line)
        print(line, flush=True)

    made = trainer(data, out, say)
    held = [(truth, read) for truth, read in made["held_out"]]
    if not held or not sum(len(truth) for truth, _ in held):
        raise ValueError("the trainer returned no held-out lines to score")
    scores = {"cer": character_error_rate(held), "lines": len(held), "model": made["model"]}
    log.append(f"time {time.monotonic() - started:.2f}s")
    (out / "train.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    (out / "scores.json").write_text(json.dumps(scores, sort_keys=True), encoding="utf-8")
    return scores


def load_trainer(spec: str) -> Trainer:
    module, _, name = spec.partition(":")
    return getattr(importlib.import_module(module), name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--trainer", required=True, help="module:function")
    args = parser.parse_args(argv)
    run_package(Path(args.data), Path(args.out), load_trainer(args.trainer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
