#!/usr/bin/env python3
"""spaCy `nlp(text)` per page against `nlp.pipe(texts, batch_size=32)` (`runtime.spacy.batched-and-off-the-loop`, design
`step-major-design-2026-10-21.md` Proposal B). The engine reads names with one `nlp(text)` call per page; the micro-batcher
is built only if `pipe` beats that by >= 1.5x (the lead's rule), so this prints the ratio and exits 0 only then.

  python fichero-server/scripts/bench_spacy_pipe.py [--pages 200] [--model en_core_web_sm] [--batch-size 32] [--runs 3]

Needs the engine's venv with the pipeline installed; touches nothing of the person's (no library, no engine). Run it on the
M4 on AC with nothing else busy. The page texts are short synthetic letters of about 60 words (the proxy: a real diary page
is longer, which favours `pipe` less, so a result near 1.5x wants a rerun on a few real pages: --texts FILE, one page a line).
Prints pages a second for each, the ratio, and the median of --runs (the first run warms the model and is dropped).
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

SAMPLE = ("In the year {n} the vecino Juan de Mendoza of Cartagena sold a house on the calle de San Juan to Maria Lopez, "
          "widow of Pedro Garcia, for four hundred pesos, before the notary Francisco de la Torre, who wrote this letter "
          "at Seville on the third of May and sent it to his cousin Diego in Lima with the fleet, asking for news of the "
          "family, the harvest and the price of silver at Potosi.")


def texts_from(path: str | None, pages: int) -> list[str]:
    if path:
        lines = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
        return (lines * (pages // max(1, len(lines)) + 1))[:pages]
    return [SAMPLE.format(n=1500 + i % 200) for i in range(pages)]


def per_page(nlp, texts: list[str]) -> float:
    started = time.perf_counter()
    for text in texts:
        nlp(text)
    return time.perf_counter() - started


def piped(nlp, texts: list[str], batch_size: int) -> float:
    started = time.perf_counter()
    for _ in nlp.pipe(texts, batch_size=batch_size):
        pass
    return time.perf_counter() - started


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pages", type=int, default=200)
    ap.add_argument("--model", default="en_core_web_sm")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--texts", help="a file of page texts, one a line, instead of the synthetic letters")
    args = ap.parse_args()
    import spacy

    nlp = spacy.load(args.model)
    texts = texts_from(args.texts, args.pages)
    per_page(nlp, texts[:10])  # warm the model; not counted
    solo, batched = [], []
    for _ in range(max(1, args.runs)):
        solo.append(per_page(nlp, texts))
        batched.append(piped(nlp, texts, args.batch_size))
    s, b = statistics.median(solo), statistics.median(batched)
    ratio = s / b
    print(f"{args.model}: {len(texts)} pages, median of {len(solo)} runs")
    print(f"  nlp(text) per page      {len(texts) / s:8.1f} pages/s  ({s:.2f} s)")
    print(f"  nlp.pipe(batch_size={args.batch_size:<3}) {len(texts) / b:8.1f} pages/s  ({b:.2f} s)")
    print(f"  ratio pipe/per-page     {ratio:8.2f}x  ({'build the micro-batcher' if ratio >= 1.5 else 'keep per-page; write these numbers in the spec line'})")
    return 0 if ratio >= 1.5 else 1


if __name__ == "__main__":
    sys.exit(main())
