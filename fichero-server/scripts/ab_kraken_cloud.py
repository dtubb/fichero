#!/usr/bin/env python3
"""A/B harness: Kraken alone, variant A (Kraken, then a model re-reads only the unsure lines) and variant B (Kraken finds
the lines, the model reads every line), on a folder of page images (#5894; spec `source.recipe.reader-variants-measured`).

A script only: no app change, no engine, no token. It runs in the engine's venv (kraken, torch), as `bench_reading.py`
does, on the test Mac (the M4), and measures the MODEL CALL of each variant, not the recipe step around it: it calls
`kraken_runtime` for Kraken, `llm.re_ask_lines.re_ask` for A with the step's own lines per request
(`lines_per_request_for`) and the step's own `sanitize_transcription` on each answer, and `llm.line_reader.read_lines` for B.
What the step adds (the database, the pass, the skip of lines already answered) is not exercised here.

  python fichero-server/scripts/ab_kraken_cloud.py --pages DIR --out DIR [--model fake] [--bar 0.6] [--cap 1.00]
  python fichero-server/scripts/ab_kraken_cloud.py --pages DIR --out DIR --model anthropic:claude-haiku-5-5 \\
         --reference-model anthropic:<the strongest> --bar 0.6          (later: each model of Claude and Gemini)

--model fake is the dry run: a stub that answers a fixed text, no network, no key, cost 0. Nothing here reads a key from
anywhere; a real model needs its provider key in the environment, as the engine's own calls do. It refuses to run unless
FICHERO_BASE_PATH is set to a scratch directory (never the app's own state under ~/Library): the Kraken reader is read
from there, and nothing of the owner's can be reached.

THE REFERENCE is a read made by the strongest model on every line. It is LABELLED "model reference, not ground truth" in
every report: a CER against it measures agreement with a model, and says nothing of the page when the model is wrong.

COST is the registry's per-token price (`llm.model_types.estimate_cost`) times the tokens the call reported
(`llm.collect_usage`) when there are any, else an estimate (images: pixels / 750; prompt and answer: characters / 4). Before
each call its worst case (the images, the prompt and the whole `max_tokens`) is RESERVED against `--cap` (US$1 by default),
so calls running at once cannot together pass it; the reservation is replaced by the real cost when the call ends. A call
that cannot be reserved is not made and the run stops there, reporting what it has. A model with no price in
the registry is refused (a cap cannot be kept without one).

Writes to --out: report.md (the numbers), sheet.html (ten lines per variant side by side, with each line's picture, for
the owner), lines.json (every line of every variant) and crops/.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

LABEL = "model reference, not ground truth"
FAKE_TEXT = "texto de prueba"
FAKE_REFERENCE_TEXT = "texto de referencia"
GOOD_LINE_CER = 0.10  # a line is "good" when Kraken's text is within this CER of the reference
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


class CapReached(RuntimeError):
    """The next call could take the total past the cap: it is not made."""


@dataclass
class Ledger:
    """What the model calls cost, per stage and page; `check` is called before each call."""

    cap: float
    spent: float = 0.0
    reserved: float = 0.0
    calls: int = 0
    by_stage: dict[str, float] = field(default_factory=dict)
    by_page: dict[str, float] = field(default_factory=dict)
    stage: str = ""
    page: str = ""

    def reserve(self, upcoming: float) -> float:
        """Keep `upcoming` (a call's worst case) against the cap, or refuse. No await sits between the check and the
        reservation, so calls running at once on one loop cannot both pass a cap that fits one."""
        if self.spent + self.reserved + upcoming > self.cap:
            raise CapReached(f"the next call could cost ${upcoming:.4f}; ${self.spent:.4f} of ${self.cap:.2f} is spent "
                             f"and ${self.reserved:.4f} is held by calls under way")
        self.reserved += upcoming
        return upcoming

    def release(self, held: float) -> None:
        self.reserved = max(0.0, self.reserved - held)

    def settle(self, held: float, actual: float) -> None:
        """A call ended: its reservation gives way to what it cost."""
        self.release(held)
        self.add(actual)

    def add(self, cost: float) -> None:
        self.spent += cost
        self.calls += 1
        self.by_stage[self.stage] = self.by_stage.get(self.stage, 0.0) + cost
        self.by_page[self.page] = self.by_page.get(self.page, 0.0) + cost


# ---------------------------------------------------------------- measures


def _edit_distance(a: list, b: list) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = row
    return previous[-1]


def line_errors(reference: str, hypothesis: str) -> tuple[int, int, int, int] | None:
    """(character errors, reference characters, word errors, reference words) of one line, or None when the reference
    has nothing to measure against. CER is the repository's exact one (`transcription_accuracy`)."""
    from fichero_server.workflows.transcription_accuracy import character_error_rate

    if not (reference or "").strip():
        return None
    score = character_error_rate(reference, hypothesis or "")
    ref_words, hyp_words = reference.split(), (hypothesis or "").split()
    return score.distance, score.reference_chars, _edit_distance(ref_words, hyp_words), len(ref_words)


def rates(pairs: list[tuple[str, str]]) -> dict:
    """Micro CER and WER over (reference, hypothesis) lines: total errors over total reference length."""
    ce = cn = we = wn = 0
    for ref, hyp in pairs:
        got = line_errors(ref, hyp)
        if got:
            ce, cn, we, wn = ce + got[0], cn + got[1], we + got[2], wn + got[3]
    return {"cer": ce / cn if cn else None, "wer": we / wn if wn else None, "lines": len(pairs), "reference_chars": cn}


def calibration(kraken: list[dict], bar: float) -> dict:
    """Is a garbled Kraken line a low-certainty one? The worst-CER decile of lines (at least one) and the good lines
    (CER <= GOOD_LINE_CER), each with the share that falls BELOW the bar (i.e. would be sent in variant A). A line with no
    stated certainty counts as unsure, as variant A sends it."""
    scored = []
    for line in kraken:
        got = line_errors(line["reference"], line["kraken"])
        if got and got[1]:
            scored.append((got[0] / got[1], line["confidence"]))
    if not scored:
        return {"lines": 0}
    below = lambda c: c is None or c < bar  # noqa: E731
    worst = sorted(scored, key=lambda s: -s[0])[: max(1, len(scored) // 10)]
    good = [s for s in scored if s[0] <= GOOD_LINE_CER]
    return {"lines": len(scored), "bar": bar, "worst_decile_lines": len(worst),
            "worst_decile_below_bar": sum(below(c) for _e, c in worst) / len(worst),
            "good_lines": len(good), "good_below_bar": (sum(below(c) for _e, c in good) / len(good)) if good else None,
            "share_sent": sum(below(c) for _e, c in scored) / len(scored)}


# ---------------------------------------------------------------- the model, fake or real


_REAL_VISION = None


def _real_vision():
    """The engine's own `llm.vision`, kept once so a second install never wraps an adapter (and bills twice)."""
    global _REAL_VISION
    if _REAL_VISION is None:
        from fichero_server import llm

        _REAL_VISION = llm.vision
    return _REAL_VISION


def install_model(spec: str, ledger: Ledger):
    """Replace `fichero_server.llm.vision` with a counting, capping adapter and return the LLMConfig to call with.
    `fake`: a stub answering a fixed text for each image (a JSON array, as both callers expect). `provider:model`: the
    real call, priced and capped."""
    from fichero_server import llm

    _real_vision()
    if spec in ("fake", "fake-reference"):
        text = FAKE_REFERENCE_TEXT if spec == "fake-reference" else FAKE_TEXT

        async def fake(images, prompt, config, **kw):
            ledger.add(0.0)
            return json.dumps([text] * len(images))

        llm.vision = fake
        return llm.LLMConfig(provider="fake", model=spec)

    provider, _, model = spec.partition(":")
    if not model:
        raise SystemExit(f"--model {spec!r}: give 'fake' or 'provider:model' (anthropic, google)")
    from fichero_server.llm.model_types import estimate_cost

    if estimate_cost(model, 1, 1) is None:
        raise SystemExit(f"no price for {model} in the registry: a cap cannot be kept without one")
    real = _real_vision()

    async def priced(images, prompt, config, **kw):
        tokens_in = sum(_image_tokens(i) for i in images) + len(prompt) // 4
        held = ledger.reserve(estimate_cost(config.model, tokens_in, config.max_tokens) or 0.0)
        try:
            with llm.collect_usage() as used:
                raw = await real(images=images, prompt=prompt, config=config, **kw)
        except BaseException:
            ledger.release(held)  # a failed call is not billed here; the provider's own bill is the last word
            raise
        # The tokens the call reported, when it reported any; the estimate only when it did not.
        got_in = sum(int(u.get("input_tokens") or 0) for u in used)
        got_out = sum(int(u.get("output_tokens") or 0) for u in used)
        ledger.settle(held, estimate_cost(config.model, got_in or tokens_in, got_out or max(1, len(str(raw)) // 4)) or 0.0)
        return raw

    llm.vision = priced
    return llm.LLMConfig(provider=provider, model=model, temperature=0.0)


def _image_tokens(data_uri: str) -> int:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[1]))) as im:
            return max(1, im.width * im.height // 750)
    except Exception:  # noqa: BLE001 -- an image we cannot size is priced as a large one: the cap errs on the safe side
        return 1600


# ---------------------------------------------------------------- the three readings of a page


def kraken_lines(image: Path, reader_ref: str) -> list[dict]:
    """Kraken finds and reads the page's lines: [{'id', 'text', 'confidence', 'polygon'}] in reading order."""
    from fichero_server.llm.kraken_runtime import recognize_to_geometry, resolve_recognition_model
    from fichero_server.media.ocr_geometry import OCRGeometryLevel

    path, model_id = resolve_recognition_model(reader_ref)
    geometry = recognize_to_geometry(str(image), path, model_id=model_id, rendition_id=None)
    return [{"id": str(i), "text": b.text or "", "confidence": b.confidence, "polygon": b.metadata["polygon_px"],
             "box": b}
            for i, b in enumerate(x for x in geometry.boxes if x.level == OCRGeometryLevel.LINE
                                  and x.metadata.get("polygon_px"))]


async def reading_by_model(image: Path, lines: list[dict], config, language: str | None) -> dict[str, str]:
    """Variant B / the reference: the model reads EVERY line (the line reader, as a vision reader of Kraken's lines)."""
    from fichero_server.llm.line_reader import read_lines
    from fichero_server.media.ocr_geometry import OCRGeometryResult

    boxes = [dict_box for dict_box in (line["box"].model_copy(update={"text": "", "metadata": {
        **line["box"].metadata, "line_id": line["id"]}}) for line in lines)]
    geometry = OCRGeometryResult(text="", provider="kraken", model="kraken", boxes=boxes, source="kraken-blla",
                                 metadata={})
    out = await read_lines(str(image), geometry, config, language=language)
    return {b.metadata["line_id"]: b.text for b in out.boxes if b.metadata.get("line_id") and b.text}


async def reading_unsure(image: Path, lines: list[dict], config, language: str | None, bar: float
                         ) -> tuple[dict[str, str], int]:
    """Variant A: the model re-reads only the lines Kraken was under `bar` sure of (a line with no stated certainty is
    sent): the same call `correct` with `only_below_confidence` makes. (answers by line id, lines sent)."""
    from fichero_server.llm.re_ask_lines import re_ask

    unsure = [{"id": line["id"], "text": line["text"], "polygon": line["polygon"]}
              for line in lines if line["confidence"] is None or line["confidence"] < bar]
    if not unsure:
        return {}, 0
    from fichero_server.llm.line_reader import LINES_PER_CALL
    from fichero_server.recipes.cards import lines_per_request_for
    from fichero_server.workflows.tools.transcription_output import sanitize_transcription

    answers, _left = await re_ask(str(image), unsure, "", config,
                                  batch=lines_per_request_for(str(config.model)) or LINES_PER_CALL, language=language)
    for line_id in list(answers):  # the step's guard: commentary is not a line (#4496)
        try:
            answers[line_id] = sanitize_transcription(answers[line_id])
        except Exception:  # noqa: BLE001 -- the step keeps the first reader's text for such a line, so does this
            del answers[line_id]
    return answers, len(unsure)


# ---------------------------------------------------------------- the run


def run(pages: Path, out: Path, *, model: str, reference_model: str | None, bar: float, cap: float,
        reader_ref: str, language: str | None, kraken=kraken_lines) -> dict:
    ledger = Ledger(cap=cap)
    images = sorted(p for p in pages.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"no page images in {pages}")
    ref_spec = reference_model or ("fake-reference" if model == "fake" else model)
    rows: list[dict] = []
    stopped = None
    sent = total = 0
    for image in images:
        ledger.page = image.name
        lines = kraken(image, reader_ref)
        try:
            ledger.stage = "reference"
            ref_config = install_model(ref_spec, ledger)
            reference = asyncio.run(reading_by_model(image, lines, ref_config, language))
            ledger.stage = "A"
            a_config = install_model(model, ledger)
            a_answers, n = asyncio.run(reading_unsure(image, lines, a_config, language, bar))
            ledger.stage = "B"
            b_answers = asyncio.run(reading_by_model(image, lines, a_config, language))
        except CapReached as exc:
            stopped = f"{image.name}: {exc}"
            break
        sent, total = sent + n, total + len(lines)
        for line in lines:
            rows.append({"page": image.name, "id": line["id"], "confidence": line["confidence"],
                         "polygon": line["polygon"], "kraken": line["text"],
                         "A": a_answers.get(line["id"], line["text"]), "B": b_answers.get(line["id"], ""),
                         "reference": reference.get(line["id"], ""), "sent_in_A": line["id"] in a_answers})
    report = summarise(rows, ledger, bar=bar, sent=sent, total=total, stopped=stopped, model=model, reference=ref_spec,
                       pages=len(images))
    write_outputs(out, rows, report, images)
    return report


def summarise(rows, ledger: Ledger, *, bar, sent, total, stopped, model, reference, pages) -> dict:
    measured = [r for r in rows if r["reference"].strip()]
    return {
        "label": LABEL, "model": model, "reference_model": reference, "pages_planned": pages,
        "pages_done": len({r["page"] for r in rows}), "lines": len(rows), "lines_with_reference": len(measured),
        "kraken": rates([(r["reference"], r["kraken"]) for r in measured]),
        "A": rates([(r["reference"], r["A"]) for r in measured]),
        "B": rates([(r["reference"], r["B"]) for r in measured]),
        "A_lines_sent": sent, "A_lines_total": total, "A_share_sent": (sent / total) if total else None,
        "calibration": calibration(measured, bar),
        "cost": {"total": ledger.spent, "cap": ledger.cap, "calls": ledger.calls, "by_stage": ledger.by_stage,
                 "by_page": ledger.by_page, "per_page": (ledger.spent / pages) if pages else None,
                 "estimated": model != "fake"},
        "stopped": stopped,
    }


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def write_outputs(out: Path, rows: list[dict], report: dict, images: list[Path]) -> None:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    crops = out / "crops"
    crops.mkdir(exist_ok=True)
    pages = {p.name: p for p in images}
    shown = sorted((r for r in rows if r["reference"].strip()),
                   key=lambda r: -(line_errors(r["reference"], r["kraken"]) or (0, 1, 0, 1))[0]
                   / max(1, (line_errors(r["reference"], r["kraken"]) or (0, 1, 0, 1))[1]))[:10]
    for n, row in enumerate(shown):
        with Image.open(pages[row["page"]]) as im:
            xs, ys = [p[0] for p in row["polygon"]], [p[1] for p in row["polygon"]]
            box = (max(0, int(min(xs))), max(0, int(min(ys))), min(im.width, int(max(xs))), min(im.height, int(max(ys))))
            if box[2] > box[0] and box[3] > box[1]:
                im.convert("RGB").crop(box).save(crops / f"{n:02}.png")
        row["crop"] = f"crops/{n:02}.png"
    (out / "lines.json").write_text(json.dumps({"label": LABEL, "lines": [
        {k: v for k, v in r.items() if k != "box"} for r in rows]}, indent=1), encoding="utf-8")
    (out / "report.md").write_text(_report_md(report), encoding="utf-8")
    (out / "sheet.html").write_text(_sheet_html(shown, report), encoding="utf-8")


def _report_md(r: dict) -> str:
    c, cal = r["cost"], r["calibration"]
    lines = [f"# Kraken, A and B on {r['pages_done']} of {r['pages_planned']} pages",
             f"\nAll CER and WER below are against a **{r['label']}** ({r['reference_model']}), over "
             f"{r['lines_with_reference']} of {r['lines']} lines. Model for A and B: {r['model']}.\n",
             "| | CER | WER |", "|---|---|---|"]
    for name, key in (("Kraken alone", "kraken"), ("A: Kraken, then the model on unsure lines", "A"),
                      ("B: the model reads every line", "B")):
        lines.append(f"| {name} | {_pct(r[key]['cer'])} | {_pct(r[key]['wer'])} |")
    lines += [f"\nVariant A sent {r['A_lines_sent']} of {r['A_lines_total']} lines ({_pct(r['A_share_sent'])}).",
              f"\n## Calibration (bar {cal.get('bar')})\n"
              f"Worst-CER decile ({cal.get('worst_decile_lines')} lines): {_pct(cal.get('worst_decile_below_bar'))} fall "
              f"below the bar (would be sent). Good lines (CER <= {GOOD_LINE_CER:.0%}, {cal.get('good_lines')} lines): "
              f"{_pct(cal.get('good_below_bar'))} fall below it. If the first is not far above the second, Kraken is "
              "confidently wrong and A cannot find its bad lines.",
              f"\n## Cost{' (estimated from the registry price)' if c['estimated'] else ' (fake model: none)'}\n"
              f"Total ${c['total']:.4f} of the ${c['cap']:.2f} cap over {c['calls']} calls; per page "
              f"${(c['per_page'] or 0):.4f}. By stage: "
              + ", ".join(f"{k or '-'} ${v:.4f}" for k, v in c["by_stage"].items())]
    if r["stopped"]:
        lines.append(f"\n**Stopped at the cap:** {r['stopped']}")
    return "\n".join(lines) + "\n"


def _sheet_html(shown: list[dict], r: dict) -> str:
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    body = "".join(
        f"<tr><td><img src='{row.get('crop', '')}' style='max-width:420px'></td><td>{esc(row['kraken'])}</td>"
        f"<td>{esc(row['A'])}{' (sent)' if row['sent_in_A'] else ''}</td><td>{esc(row['B'])}</td>"
        f"<td>{esc(row['reference'])}</td></tr>" for row in shown)
    return ("<!doctype html><meta charset=utf-8><title>Kraken, A and B</title><style>body{font:14px system-ui;margin:2em}"
            "td,th{border:1px solid #888;padding:6px;vertical-align:top}table{border-collapse:collapse}</style>"
            f"<h1>The ten lines Kraken read worst</h1><p>The last column is a <b>{LABEL}</b> ({esc(r['reference_model'])}), "
            "not what the page says.</p><table><tr><th>Line</th><th>Kraken</th><th>A</th><th>B</th><th>Reference</th></tr>"
            f"{body}</table>")


def require_scratch_state() -> None:
    """Refuse to run unless FICHERO_BASE_PATH names a scratch directory, never the app's own state."""
    import os

    base = os.environ.get("FICHERO_BASE_PATH", "").strip()
    if not base:
        raise SystemExit("set FICHERO_BASE_PATH to a scratch directory holding kraken-models (a copy of the seeded reader)")
    resolved = Path(base).expanduser().resolve()
    if (Path.home() / "Library") in (resolved, *resolved.parents):
        raise SystemExit(f"FICHERO_BASE_PATH={base} is under ~/Library, where the app keeps its own state: use a scratch directory")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", default="fake", help="'fake' (the dry run) or provider:model for A and B")
    ap.add_argument("--reference-model", help="the strongest model, for the reference read (default: --model; fake: fake)")
    ap.add_argument("--bar", type=float, default=0.6, help="variant A's certainty bar X")
    ap.add_argument("--cap", type=float, default=1.0, help="US$ cap over every call, reference included")
    ap.add_argument("--reader", default=None, help="the Kraken reader (a catalogue id or a .mlmodel path)")
    ap.add_argument("--language", default="es")
    args = ap.parse_args(argv)
    require_scratch_state()
    reader = args.reader
    if reader is None:
        from fichero_server.recipes.cards import kraken_reader_for

        reader = kraken_reader_for({"zenodo": "10.5281/zenodo.21788410"})  # the seeded PP-OCRv6 medium
    report = run(args.pages, args.out, model=args.model, reference_model=args.reference_model, bar=args.bar,
                 cap=args.cap, reader_ref=reader, language=args.language)
    print((args.out / "report.md").read_text(encoding="utf-8"))
    return 0 if not report["stopped"] else 2


if __name__ == "__main__":
    sys.exit(main())
