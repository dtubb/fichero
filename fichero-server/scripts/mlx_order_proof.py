#!/usr/bin/env python3
"""MLX speed and memory in the model order (#5930 follow-up; owner 2026-10-20): Kraken block -> MLX (one model, one call at a time)
-> unload -> Kraken again. One process, on the M4 only, on a scratch FICHERO_BASE_PATH with a COPY of the dev seed models. Script
only: it never downloads (the model must already be in the scratch store) and it reads the pages from a folder of copies.

  python scripts/mlx_order_proof.py --images DIR --kraken-model M.safetensors --mlx Qwen2.5-VL-3B --pages 5

Prints one line per step (rss GB now, MLX active/peak GB, seconds): kraken block, mlx load, each page (s/page, tokens), unload,
kraken again. Free RAM is checked before the load (the model's measured size x 1.5 must be under 80% of it) and the run stops in
words otherwise. The reads are written to --out/<model>/<page>.txt for the CER step (ab_kraken_cloud.py scores them)."""

from __future__ import annotations

import argparse
import gc
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gil_proof  # noqa: E402  (free_ram_gb, therm, pages_in)

PROMPT = "Transcribe all the handwritten text on this page exactly as written, line by line. Output only the text."


def rss_gb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # bytes on macOS: the PEAK so far, not now
    return peak / 1024**3


def now_rss_gb() -> float:
    import subprocess

    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    return int(out) / 1024**2 if out else float("nan")  # KB -> GB


def say(step: str, began: float, extra: str = "") -> None:
    gpu = ""
    try:
        import mlx.core as mx

        gpu = f" mlx active {mx.get_active_memory() / 1024**3:.2f} GB peak {mx.get_peak_memory() / 1024**3:.2f} GB"
    except Exception:  # noqa: BLE001 -- mlx not imported yet is fine
        pass
    print(f"| {step}: {time.perf_counter() - began:.2f} s; rss now {now_rss_gb():.2f} GB, process peak {rss_gb():.2f} GB;{gpu} "
          f"free {gil_proof.free_ram_gb() or float('nan'):.1f} GB; {gil_proof.therm()} {extra}|", flush=True)


def kraken_block(args, label: str) -> None:
    import bench_reading

    began = time.perf_counter()
    pages, _ = bench_reading.run(args.kraken_model, args.pages, args.images, 1)
    say(f"{label} ({len(pages)} pages at N=1)", began)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--kraken-model", required=True)
    ap.add_argument("--mlx", required=True, help="a Qwen VL model_id of the engine's catalogue, installed in the scratch store")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    from fichero_server.security.real_data_guard import refuse_real_base

    refuse_real_base(os.environ.get("FICHERO_BASE_PATH"))
    from fichero_server.llm import local_model_choice as choice
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, get_mlx_model_store

    spec = next((s for s in MANAGED_MLX_MODELS.values() if args.mlx.lower() in (s.model_id.lower(), s.repo_id.lower())), None)
    if spec is None:
        sys.exit(f"--mlx {args.mlx!r}: not in the catalogue ({', '.join(MANAGED_MLX_MODELS)})")
    ok, refusal = choice.runs_here(spec, "vision")
    if not ok:
        sys.exit(f"{spec.model_id}: the memory gate says no ({refusal}); stopped, nothing loaded")
    store = get_mlx_model_store()
    if not store.is_complete(spec):
        sys.exit(f"{spec.model_id} is not installed in the scratch store ({store.root}); this script never downloads")
    free = gil_proof.free_ram_gb()
    need = spec.download_size_bytes * 1.5 / 1024**3
    if free is not None and need > 0.8 * free:
        sys.exit(f"{spec.model_id}: {need:.1f} GB needed (size x 1.5) is over 80% of the {free:.1f} GB free; stopped")
    print(f"model {spec.model_id} ({spec.repo_id}), disk size {spec.download_size_bytes / 1024**3:.2f} GB, gate passed, "
          f"free {free:.1f} GB", flush=True)

    kraken_block(args, "1 kraken block")

    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    import mlx.core as mx

    path = str(store.snapshot_path(spec))
    began = time.perf_counter()
    model, processor = load(path)
    config = load_config(path)
    say("2 mlx load", began)

    out = args.out / spec.model_id.replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    prompt = apply_chat_template(processor, config, PROMPT, num_images=1)
    times = []
    for page in gil_proof.pages_in(args.images, args.pages):
        began = time.perf_counter()
        result = generate(model, processor, prompt, image=[str(page)], max_tokens=args.max_tokens, verbose=False)
        text = getattr(result, "text", result)
        took = time.perf_counter() - began
        times.append(took)
        (out / f"{page.stem}.txt").write_text(text, encoding="utf-8")
        say(f"3 page {page.name}", began, f"{len(text)} chars ")
    print(f"| mlx s/page mean {sum(times) / len(times):.2f}, first {times[0]:.2f}, rest {sum(times[1:]) / max(1, len(times) - 1):.2f} |")

    began = time.perf_counter()
    del model, processor
    gc.collect()
    mx.clear_cache()
    say("4 mlx unload", began)

    kraken_block(args, "5 kraken again after the unload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
