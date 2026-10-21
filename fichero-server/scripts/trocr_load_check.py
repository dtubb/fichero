#!/usr/bin/env python3
"""Does a TrOCR repository load and read under the transformers this build ships? (#5981, `source.onboard.model-search-trocr-loads-under-the-bundle`)

`economy_htr` says TrOCR needs `transformers<5` (TRIDIS v1 loads under 4.x, v2's packaging is broken); the bundle has 5.x. Whether a given
repository loads under 5 is one check per repository, and this is it: on the M4 only, on a scratch FICHERO_BASE_PATH (the weights land in its
store, safetensors only at the commit the Hub names, through the engine's own `trocr_runtime`), one repository per process, so a crash is a row.

  python scripts/trocr_load_check.py --image DIR_OR_FILE --repo ZihCiLin/... --repo Archatext/... --out result.json

Each row: repo, transformers and torch versions, loaded (yes/no), the error in words, seconds to load and to read, and the text read from each
crop (a line image; a page image is read as one line, which says only that the model runs). Prints one line per repository and writes the JSON.
The text is not ground truth: a repository that loads and prints something is "loads", never "reads well" (that is a bake-off's job)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

IMAGES = (".png", ".jpg", ".jpeg", ".tif", ".tiff")


def crops_in(path: Path, limit: int) -> list[str]:
    files = [path] if path.is_file() else sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGES)
    return [str(p) for p in files[:limit]]


def check_one(repo: str, crops: list[str]) -> dict:
    """Load `repo` and read `crops`, in this process, by the engine's own code path. Never raises: a failure is the row."""
    row: dict = {"repo": repo, "loaded": False, "error": None, "load_seconds": None, "read_seconds": None, "texts": []}
    try:
        import torch
        import transformers

        row.update(transformers=transformers.__version__, torch=torch.__version__)
        import importlib

        economy_htr = importlib.import_module("fichero_server.workflows.tools.economy_htr")  # honours a replaced module

        began = time.perf_counter()
        economy_htr._load_trocr(repo)
        row.update(loaded=True, load_seconds=round(time.perf_counter() - began, 2))
        began = time.perf_counter()
        row.update(texts=economy_htr.trocr_transcribe_lines(crops, repo), read_seconds=round(time.perf_counter() - began, 2))
    except Exception as exc:  # noqa: BLE001 -- the check's whole job is to say what failed
        row["error"] = f"{type(exc).__name__}: {exc}"[:600]
    return row


def run_in_own_process(repo: str, image: Path, limit: int) -> dict:
    """One repository per process, so a crash (a signal) is a row, not the end of the check."""
    done = subprocess.run([sys.executable, __file__, "--one", repo, "--image", str(image), "--limit", str(limit)],
                          capture_output=True, text=True, timeout=1800)
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("{"):
            row = json.loads(line)
            row["exit"] = done.returncode  # negative = a signal at exit (#5929), after the row was printed
            return row
    return {"repo": repo, "loaded": False, "error": f"the process left no result (exit {done.returncode}): {done.stderr[-300:]}",
            "exit": done.returncode, "texts": []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True, help="a line image, or a folder of them")
    ap.add_argument("--repo", action="append", default=[])
    ap.add_argument("--one", help="internal: check this repository in this process and print its row as JSON")
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    from fichero_server.security.real_data_guard import refuse_real_base

    refuse_real_base(os.environ.get("FICHERO_BASE_PATH"))
    if args.one:
        print(json.dumps(check_one(args.one, crops_in(args.image, args.limit)), ensure_ascii=False), flush=True)
        try:
            from fichero_server.core.fast_exit import leave  # the engine's way out with torch loaded (#5929), where it exists
        except ImportError:
            return 0
        leave(0)
        return 0
    rows = [run_in_own_process(repo, args.image, args.limit) for repo in args.repo]
    for row in rows:
        print(f"| {row['repo']}: loaded {'yes' if row['loaded'] else 'NO'}; transformers {row.get('transformers')}; "
              f"{row.get('error') or 'read ' + str(len(row['texts'])) + ' crop(s) in ' + str(row.get('read_seconds')) + ' s'}; exit {row.get('exit')} |")
    if args.out:
        args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
