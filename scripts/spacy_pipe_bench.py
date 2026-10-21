"""Does `nlp.pipe(texts, batch_size=32)` beat one `nlp(text)` per page? (`runtime.spacy.never-blocks`: the micro-batcher is built only if it
is 1.5x or better). Run on the M4 only, after the MLX 3B run; it loads the engine's spaCy pipelines and nothing else.

    python scripts/spacy_pipe_bench.py [--pages 200] [--words 150] [--models es_core_news_sm,es_core_news_md] [--repeats 3]
                                       [--texts DIR]

Prints, per pipeline, seconds for the per-page loop and for `pipe`, the ratio (per-page / pipe), and whether it clears 1.5x.
The texts are Spanish page-sized passages built from a FIVE-sentence list, so every run reads the same words; real pages are more varied
(more names, longer sentences), so `--texts DIR` reads every *.txt in a folder instead (one page each; a folder of real transcriptions).
Each repeat runs the two arms in alternating order (per page first, then pipe first), so neither always pays for a cold cache."""
from __future__ import annotations

import argparse
import statistics
import time
from pathlib import Path

SENTENCES = (
    "Don Juan de Mosquera vendió una casa en la calle de San Pedro a Francisco Pérez por trescientos pesos.",
    "El escribano de la ciudad de Quito dio fe del otorgamiento de la escritura el día doce de marzo.",
    "Doña María de la Cruz, viuda de Antonio Ramírez, declaró que dejaba sus bienes a sus hijos.",
    "Los testigos fueron Pedro de Lara, Juan Gómez y Diego de Salazar, vecinos de esta villa.",
    "Pagó la cantidad en reales de plata y se obligó a no enajenar la hacienda sin licencia.",
)
CLEARS = 1.5


def passage(words: int, seed: int) -> str:
    out, n = [], 0
    while n < words:
        sentence = SENTENCES[(seed + len(out)) % len(SENTENCES)]
        out.append(sentence)
        n += len(sentence.split())
    return " ".join(out)


def _seconds(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def compare(per_page, piped, repeats: int) -> tuple[float, float]:
    """(median seconds per page-by-page, median seconds piped); each arm warmed once, the order alternating on every repeat."""
    per_page()
    piped()
    a, b = [], []
    for i in range(repeats):
        arms = [(a, per_page), (b, piped)]
        for out, fn in (arms if i % 2 == 0 else arms[::-1]):
            out.append(_seconds(fn))
    return statistics.median(a), statistics.median(b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pages", type=int, default=200)
    ap.add_argument("--words", type=int, default=150)
    ap.add_argument("--models", default="es_core_news_sm,es_core_news_md")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--texts", help="a folder of *.txt pages to use instead of the generated passages")
    args = ap.parse_args()

    from fichero_server.llm.local_models import load_spacy_pipeline

    if args.texts:
        texts = [p.read_text() for p in sorted(Path(args.texts).glob("*.txt"))][: args.pages]
        if not texts:
            print(f"no *.txt pages in {args.texts}: nothing to time")
            return 1
        words = sum(len(t.split()) for t in texts) // len(texts)
        print(f"{len(texts)} real pages from {args.texts}, about {words} words each, batch_size={args.batch_size}, median of {args.repeats}")
    else:
        texts = [passage(args.words, i) for i in range(args.pages)]
        print(f"{args.pages} generated pages of about {args.words} words from {len(SENTENCES)} rotated sentences "
              f"(less varied than real pages: use --texts DIR for those), batch_size={args.batch_size}, median of {args.repeats}")
    for name in args.models.split(","):
        try:
            nlp = load_spacy_pipeline(name)
        except Exception as exc:  # noqa: BLE001 -- a pipeline not installed here is reported, the rest still run
            print(f"{name}: not available here ({exc})")
            continue
        per_page, piped = compare(lambda: [nlp(t) for t in texts], lambda: list(nlp.pipe(texts, batch_size=args.batch_size)),
                                  args.repeats)
        ratio = per_page / piped
        print(f"{name}: per page {per_page:.2f} s, pipe {piped:.2f} s, ratio {ratio:.2f}x -> "
              f"{'builds the batcher' if ratio >= CLEARS else 'no batcher: write the numbers in the spec line'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
