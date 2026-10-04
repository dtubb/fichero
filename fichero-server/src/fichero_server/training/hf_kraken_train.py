# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["kraken==7.1.1"]
# ///
"""Fine-tune a Kraken reader INSIDE a Hugging Face Job (#5398). Shipped with Fichero; sent as the
Job's script by `training.hf_jobs`, never edited per run.

    --data  a training set made by `training.kraken_set` (PAGE XML beside each photograph,
            manifest.json), with the base reader under base/
    --out   where the checkpoints and the best model go; synced home after the Job
    --base  the base reader's file name under data/base/ (none: train from nothing)

The held-out pages are not in --data: they stay home and are scored there. Exits non-zero when
there is nothing to train on, so the Job fails with a reason rather than finishing empty.
"""
import argparse
import glob
import os
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--data", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--base", default="")
parser.add_argument("--name", default="model")
parser.add_argument("--device", default="cuda:0")
args = parser.parse_args()

pages = sorted(glob.glob(os.path.join(args.data, "*.xml")))
print(f"{len(pages)} pages of training lines", flush=True)
if not pages:
    sys.exit(f"no training pages under {args.data}")
os.makedirs(args.out, exist_ok=True)
command = ["ketos", "-d", args.device, "--workers", "4"]
if args.device.startswith("cuda"):
    command += ["--precision", "16-mixed"]
# One schedule and an epoch ceiling for every base (`compute.tune.kraken-schedule-is-fixed`, #5448): a base that
# carries a cosine schedule (PP-OCRv6) has an infinite step count under early stopping with no ceiling, and ketos
# stops at once.
command += ["train", "-f", "page", "-q", "early", "-N", "50", "--min-epochs", "5", "--lag", "5",
            "--schedule", "constant", "-B", "16", "-p", "0.9", "-o", os.path.join(args.out, args.name)]
if args.base:
    command += ["-i", os.path.join(args.data, "base", args.base), "--resize", "union"]
subprocess.run([*command, *pages], check=True)
