#!/usr/bin/env python3
"""A/B harness: Kraken alone, variant A (Kraken, then a model re-reads only the unsure lines) and variant B (Kraken finds
the lines, the model reads every line), on a folder of page images (#5894; spec `source.recipe.reader-variants-measured`).

A script only: no app change, no engine, no token. It runs in the engine's venv (kraken, torch), as `bench_reading.py`
does, on the test Mac (the M4), and measures the MODEL CALL of each variant, not the recipe step around it: it calls
`kraken_runtime` for Kraken, `llm.re_ask_lines.re_ask` for A with the step's own lines per request
(`lines_per_request_for`) and the step's own `sanitize_transcription` on each answer, and `llm.line_reader.read_lines` for B (with the page, reduced, once per request beside the batch of
lines, as the recipe's vision reader sends it; the cost reported for B includes it).
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
import os
import re
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

LABEL = "model reference, not ground truth"
FAKE_TEXT = "texto de prueba"
FAKE_REFERENCE_TEXT = "texto de referencia"
GOOD_LINE_CER = 0.10  # a line is "good" when Kraken's text is within this CER of the reference
WIDE_PX = 120  # a polygon narrower than this is a fragment (a mark, a stray stroke), not a line
#: The script a language is written in, by the first word of a letter's Unicode name; all the languages the harness meets are Latin.
SCRIPT_OF = {"es": "LATIN", "en": "LATIN", "fr": "LATIN", "de": "LATIN", "it": "LATIN", "pt": "LATIN", "la": "LATIN"}
ORDINALS = "ªº"  # Spanish No, 1o: letters by Unicode, but Latin writing
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
#: Where the owner may keep provider keys when they are not in the app's Settings (one KEY=value per line, mode 600).
AB_ENV = Path("~/.config/fichero/ab.env")
HOSTED_NOT_LOCAL = "hosted, not local"
LINES_PER_CALL_FOR_ESTIMATE = 8  # `llm.line_reader.LINES_PER_CALL`
#: The three cloud models of the 2026-10-20 live run, through OpenRouter (prices from the vendored registry, `resources/model_prices.json`):
#: the cheapest current Claude vision model ($1 / $5 per M tokens), the cheapest current Gemini ($0.25 / $1.5, ai.google.dev/pricing/gemini-3),
#: and a hosted Qwen VL ($0.21 / $0.63) standing in for the local MLX arm until the M4 has disk for it. The strongest of the three
#: (Claude) is the reference.
OPENROUTER_CLAUDE = "anthropic/claude-haiku-4.5"
OPENROUTER_GEMINI = "google/gemini-3.1-flash-lite-preview"
OPENROUTER_QWEN = "qwen/qwen-vl-plus"


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


def cost_of(provider: str, model: str, tokens_in: int, tokens_out: int) -> float | None:
    """The registry's price for a call; for an aggregator its own entry first (`openrouter/anthropic/claude-haiku-4.5`), so a
    model it lists under another price is not priced as the maker's."""
    from fichero_server.llm.model_types import estimate_cost

    for name in (f"{provider}/{model}", model):
        got = estimate_cost(name, tokens_in, tokens_out)
        if got is not None:
            return got
    return None


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
            # B sends the page once beside the lines: the answer is one text for each LINE image the prompt names.
            n = int(re.search(r"(\d+) (?:line )?images", prompt).group(1))
            return json.dumps([text] * n)

        llm.vision = fake
        return llm.LLMConfig(provider="fake", model=spec)

    provider, _, model = spec.partition(":")
    if not model:
        raise SystemExit(f"--model {spec!r}: give 'fake' or 'provider:model' (anthropic, google)")
    if cost_of(provider, model, 1, 1) is None:
        raise SystemExit(f"no price for {provider}:{model} in the registry: a cap cannot be kept without one")
    real = _real_vision()

    async def priced(images, prompt, config, **kw):
        tokens_in = sum(_image_tokens(i) for i in images) + len(prompt) // 4
        held = ledger.reserve(cost_of(config.provider, config.model, tokens_in, config.max_tokens) or 0.0)
        try:
            with llm.collect_usage() as used:
                raw = await real(images=images, prompt=prompt, config=config, **kw)
        except BaseException:
            ledger.release(held)  # a failed call is not billed here; the provider's own bill is the last word
            raise
        # The tokens the call reported, when it reported any; the estimate only when it did not.
        got_in = sum(int(u.get("input_tokens") or 0) for u in used)
        got_out = sum(int(u.get("output_tokens") or 0) for u in used)
        ledger.settle(held, cost_of(config.provider, config.model, got_in or tokens_in,
                                    got_out or max(1, len(str(raw)) // 4)) or 0.0)
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


# ---------------------------------------------------------------- provider keys, the engine's way


def read_env_file(path: Path, *, log=print) -> dict[str, str]:
    """The KEY=value lines of the owner's key file. Refused when group- or world-readable (a key must not be); the NAMES
    found are logged, never a value."""
    path = Path(path).expanduser()
    if not path.exists():
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f"{path} is readable by others (mode {mode:o}): run `chmod 600 {path}` and try again; it was not read")
    found: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            value = value.strip().strip("'\"")
            if name.strip().removeprefix("export ").strip() and value:
                found[name.strip().removeprefix("export ").strip()] = value
    log(f"{path}: found {', '.join(sorted(found)) or 'no keys'} (names only)")
    return found


#: Other names a provider's key goes by in the environment or the key file.
KEY_ALIASES = {"huggingface": ("HF_TOKEN",)}


#: Key values this process has resolved (the keychain's, the key file's): scrubbed by VALUE, whatever shape they have.
_KNOWN_SECRETS: set[str] = set()


def scrub(text: str, environ=None) -> str:
    """`text` with every secret in it replaced: the value of any *_API_KEY / *_TOKEN variable in the environment, and anything shaped
    like a provider key (sk-..., hf_...). Failures are written to report.md; a key must never reach it."""
    import re

    environ = os.environ if environ is None else environ
    for secret in _KNOWN_SECRETS:
        text = text.replace(secret, "<key>")
    for name, value in environ.items():
        if value and len(value) >= 8 and (name.endswith("_API_KEY") or name.endswith("_TOKEN") or name == "HF_TOKEN"):
            text = text.replace(value, "<key>")
    return re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|hf_[A-Za-z0-9]{8,}|AIza[A-Za-z0-9_-]{20,})", "<key>", text)


def ensure_provider_key(provider: str, *, env_file: Path | None = None, lookup=None, environ=None, log=print) -> str:
    """Make `provider`'s key available to the engine's own lookup (`llm.get_api_key`: app-supplied, then the keychain, then the
    environment) and say where it came from, in words. The keychain is asked through the engine's `lookup_api_key`, never a
    copy of its logic. A locked or unreachable keychain (over SSH, or an item that belongs to the app) is SAID, then the key
    file is read; a key found there is put in the process environment under the provider's own variable name. Returns the source
    ("keychain", "environment", "the key file"). Never prints a value. SystemExit naming the key looked for when there is none."""
    from fichero_server.llm.providers import get_provider_info
    from fichero_server.security.keychain import ProviderKeyState, lookup_api_key

    environ = os.environ if environ is None else environ
    info = get_provider_info(provider)
    variable = info.api_key_env if info and info.api_key_env else f"{provider.upper()}_API_KEY"
    answer = (lookup or lookup_api_key)(provider)
    if answer.state is ProviderKeyState.FOUND:
        if answer.key and len(answer.key) >= 8:
            _KNOWN_SECRETS.add(answer.key)
        log(f"{provider}: key found in the keychain")
        return "keychain"
    if answer.state is ProviderKeyState.UNREADABLE:
        log(f"{provider}: the keychain holds a key but this process cannot read it ({answer.detail or 'no detail'}): "
            "it is locked, or over SSH there is no session to unlock it, or the item belongs to the app and a plain python "
            "process is not trusted by it. Looking in the key file instead.")
    names = (variable, *KEY_ALIASES.get(provider, ()))
    if (hit := next((n for n in names if environ.get(n)), None)):
        environ[variable] = environ[hit]
        if len(environ[hit]) >= 8:
            _KNOWN_SECRETS.add(environ[hit])
        log(f"{provider}: key found in the environment ({hit})")
        return "environment"
    found = read_env_file(env_file or AB_ENV, log=log)
    if (hit := next((n for n in names if found.get(n)), None)):
        environ[variable] = found[hit]
        if len(found[hit]) >= 8:
            _KNOWN_SECRETS.add(found[hit])
        from fichero_server.llm import clear_api_key_cache

        clear_api_key_cache(provider)
        log(f"{provider}: key found in the key file ({hit})")
        return "the key file"
    raise SystemExit(f"no {provider} key: looked for it in the keychain (add it in Settings > AI providers), the environment "
                     f"and {variable} in {env_file or AB_ENV}")


# ---------------------------------------------------------------- the estimate, before any spend


PROMPT_TOKENS_PER_CALL = 400  # an assumption: the line reader's instructions, per call of up to LINES_PER_CALL lines


def crop_tokens(spec: str, polygon: list) -> int:
    """What one line's picture costs in input tokens, by the model's family: Gemini counts 258 per 768 px tile, Qwen VL one
    per 28x28 px, the others one per 750 px (the harness's own rule); the crop is the teacher's cut (`line_cut.crop_line`)."""
    import math

    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    w, h = min(1600.0, w + 2 * h / 3), h + 2 * h / 3
    name = spec.lower()
    if "gemini" in name:
        return 258 * math.ceil(w / 768) * math.ceil(h / 768)
    if "qwen" in name:
        return max(1, int(w * h) // 784)
    return max(1, int(w * h) // 750)


def estimate_arms(lines_json: str | Path, arm_specs: dict[str, str], *, bar: float = 0.6, cap: float = 1.0) -> list[dict]:
    """The cost of each cloud arm on the lines in a free run's `lines.json` (the harness's own output: Kraken's lines with their
    polygons, certainty and a reading), from the registry price: input = the line pictures + a prompt per call, output =
    ~chars/3.5 + 6 tokens a line (a JSON string each). `arm_specs`: arm name -> provider:model; an arm called "reference" or
    "B..." reads every line, "A..." only the lines under the bar (and sends their text too). Nothing is called."""
    data = json.loads(Path(lines_json).read_text(encoding="utf-8"))
    rows = data["lines"]
    chars = [max(len(str(r.get(k) or "")) for k in ("kraken", "vision", "reference")) for r in rows]
    out = []
    for arm, spec in arm_specs.items():
        provider, _, model = spec.partition(":")
        sent = [(r, c) for r, c in zip(rows, chars) if variant_of(arm) != "A" or r["confidence"] is None or r["confidence"] < bar]
        calls = -(-len(sent) // LINES_PER_CALL_FOR_ESTIMATE) if sent else 0
        tokens_in = sum(crop_tokens(spec, r["polygon"]) + (c // 4 if variant_of(arm) == "A" else 0) for r, c in sent) \
            + PROMPT_TOKENS_PER_CALL * calls
        tokens_out = sum(int(c / 3.5) + 6 for _r, c in sent)
        cost = cost_of(provider, model, tokens_in, tokens_out)
        worst = cost_of(provider, model, tokens_in // max(1, calls) , 192 * LINES_PER_CALL_FOR_ESTIMATE + 32) if calls else 0.0
        out.append({"arm": arm, "spec": spec, "lines": len(sent), "calls": calls, "tokens_in": tokens_in, "tokens_out": tokens_out,
                    "usd": cost, "worst_call_reserved": worst})
    total = sum(e["usd"] or 0.0 for e in out)
    for e in out:
        e["cap"], e["total"], e["over_cap"] = cap, total, total > cap
    return out


def estimate_markdown(rows: list[dict]) -> str:
    lines = ["| arm | model | lines | calls | tokens in | tokens out | est. US$ | held per call |", "|---|---|---|---|---|---|---|---|"]
    for e in rows:
        usd = "NO PRICE" if e["usd"] is None else f"{e['usd']:.4f}"
        lines.append(f"| {e['arm']} | {e['spec']} | {e['lines']} | {e['calls']} | {e['tokens_in']} | {e['tokens_out']} | {usd} | "
                     f"{(e['worst_call_reserved'] or 0):.4f} |")
    total = rows[0]["total"] if rows else 0.0
    cap = rows[0]["cap"] if rows else 1.0
    lines.append(f"\n**Total ${total:.4f} of the ${cap:.2f} cap** ({'OVER: drop an arm' if total > cap else 'fits'}). Estimates, not bills: "
                 f"pictures by each family's own rule, {PROMPT_TOKENS_PER_CALL} prompt tokens a call. 'Held per call' is what the cap "
                 "reserves while one call is under way (its whole output ceiling), so the run can stop a little before the total.")
    return "\n".join(lines)


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


async def reading_by_model(image: Path, lines: list[dict], config, language: str | None, *, apple: bool = False
                           ) -> dict[str, str]:
    """Variant B / the reference / the free arms: a reader reads EVERY line of Kraken's (the line reader, as a vision
    reader of Kraken's lines; `apple`: Apple Vision on each line's own picture, `config` unused)."""
    from fichero_server.llm.line_reader import read_lines
    from fichero_server.media.ocr_geometry import OCRGeometryResult

    boxes = [dict_box for dict_box in (line["box"].model_copy(update={"text": "", "metadata": {
        **line["box"].metadata, "line_id": line["id"]}}) for line in lines)]
    geometry = OCRGeometryResult(text="", provider="kraken", model="kraken", boxes=boxes, source="kraken-blla",
                                 metadata={})
    out = await read_lines(str(image), geometry, config, language=language, apple=apple)
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


# ---------------------------------------------------------------- the free arms, the arms, the agreement

#: Every arm reads the SAME lines (Kraken's segmentation), keyed by line id, so they are scored the same way.
DEFAULT_ARMS = "kraken,A,B"
VISION_LANGUAGE = "es-ES"  # Apple Vision is given a locale, never 'auto'
FAKE_ARM_TEXT = {"vision": "texto vision", "mlx": "texto mlx"}
#: Which arm is the strongest reader when there is no cloud model to be the reference.
REFERENCE_ORDER = ("mlx", "vision", "kraken")


def kind_of(arm: str) -> str:
    return "mlx" if arm.startswith("mlx:") else arm


def variant_of(arm: str) -> str | None:
    """"A" or "B" for a cloud arm, bare (`A`: the --model) or on its own model (`B:openrouter:anthropic/claude-haiku-4.5`)."""
    head = arm.split(":", 1)[0]
    return head if head in ("A", "B") else None


def cloud_spec(arm: str, default: str) -> str:
    """The `provider:model` a cloud arm reads with: its own after the variant, else `--model`."""
    return arm.split(":", 1)[1] if ":" in arm else default


def parse_arms(text: str) -> list[str]:
    """`kraken,vision,mlx:auto,A,B` -> the arm names, in the order shown. kraken is always an arm: the lines are its."""
    arms = []
    for raw in (x.strip() for x in text.split(",")):
        cloud_on_its_own = raw[:2] in ("A:", "B:") and raw.count(":") >= 2
        if raw in ("kraken", "A", "B", "vision") or cloud_on_its_own or (raw.startswith("mlx:") and len(raw) > 4):
            if raw not in arms:
                arms.append(raw)
        elif raw:
            raise SystemExit(f"--arms {raw!r}: one of kraken, vision, mlx:<model or auto>, A, B, A:<provider:model>, B:<provider:model>")
    if "kraken" not in arms:
        arms.insert(0, "kraken")
    return arms


def pick_mlx(wanted: str, *, log=print) -> tuple[str, object, dict]:
    """(the arm's name, its LLMConfig, what was chosen and why) for `mlx:<wanted>`: a Qwen VL from the engine's own catalogue that this Mac may
    run for reading a page (`local_model_choice.runs_here`, the memory gate) and that is already installed: the harness
    never downloads (the M4's disk is nearly full) and never goes over the gate. `auto`: the engine's own choice among
    Qwen VL models (installed first, then the larger). The repo id and why are LOGGED and land in the report."""
    from fichero_server import llm
    from fichero_server.llm import local_model_choice as choice
    from fichero_server.llm.mlx_model_store import MANAGED_MLX_MODELS, get_mlx_model_store

    store = get_mlx_model_store()

    qwen = [s for s in MANAGED_MLX_MODELS.values() if "vision" in s.capabilities and "qwen" in s.model_id.lower()]
    if wanted == "auto":
        picked = choice.choose_local_model("vision", catalog=qwen, store=store)
        if picked.model_id is None:
            raise SystemExit(f"mlx:auto: {picked.reason}")
        spec, why = next(s for s in qwen if s.model_id == picked.model_id), picked.reason
    else:
        found = [s for s in qwen if wanted.lower() in (s.model_id.lower(), s.repo_id.lower())]
        if not found:
            raise SystemExit(f"mlx:{wanted}: not a Qwen VL in the catalogue ({', '.join(s.model_id for s in qwen)})")
        spec = found[0]
        ok, refusal = choice.runs_here(spec, "vision")
        if not ok:
            raise SystemExit(f"mlx:{wanted}: this Mac may not run it ({refusal}): not over the memory gate")
        why = f"named on the command line; {spec.display_name} passes the memory gate for reading a page"
    if not store.is_complete(spec):
        raise SystemExit(f"mlx:{spec.model_id} ({spec.repo_id}) is not installed; this harness never downloads: "
                         "install it in the app's Settings first")
    from fichero_server.llm.local_inference import local_reads_at_once

    reads = local_reads_at_once(spec)
    log(f"mlx arm: {spec.repo_id} ({spec.model_id}); {why}; {reads} reads at once beside the app")
    return f"mlx:{spec.model_id}", llm.LLMConfig(provider="omlx", model=spec.model_id, temperature=0.0), \
        {"repo": spec.repo_id, "model": spec.model_id, "why": why, "reads_at_once": reads}


def free_reader(arm: str, *, fake: bool, config=None, language: str = VISION_LANGUAGE):
    """The async reader of a free arm: (image, lines) -> {line id: text}. `fake`: a stub, for the dry run anywhere."""
    if fake:
        text = FAKE_ARM_TEXT[kind_of(arm)]

        async def stub(image, lines):
            return {line["id"]: text for line in lines}

        return stub
    if arm == "vision":
        return lambda image, lines: reading_by_model(image, lines, None, language, apple=True)
    return lambda image, lines: reading_by_model(image, lines, config, language)


def reference_arm_for(arms: list[str], explicit: str | None, cloud_reference: bool) -> str | None:
    """The arm whose read is the reference: the named one, else (no cloud model to be it) the strongest free arm present.
    None: the cloud reference model reads. A (the unsure lines only) is never one."""
    if explicit:
        if explicit not in arms or variant_of(explicit) == "A":
            raise SystemExit(f"--reference-arm {explicit!r}: not a full reading among --arms {','.join(arms)}")
        return explicit
    if cloud_reference:
        return None
    for kind in REFERENCE_ORDER:
        found = [a for a in arms if kind_of(a) == kind]
        if found:
            if kind == "kraken":
                raise SystemExit("--arms has only kraken: add vision or mlx:<model>, or give --reference-model")
            return found[0]
    raise SystemExit("no arm to be the reference")


def _same(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def agreement(rows: list[dict], arms: list[str]) -> dict:
    """With three or more independent readers (A reads only some lines, so it is not one), per line: every reader that
    answered gave the same text (`all agree`: probably right) or they split (the lines to look at). Sets
    `row['agreement']` ('agree' | 'split' | None when fewer than two answered) and says the share."""
    readers = [a for a in arms if variant_of(a) != "A"]
    if len(readers) < 3:
        return {"readers": readers, "scored": 0}
    agree = split = 0
    for row in rows:
        said = {a: _same(row.get(a)) for a in readers if (row.get(a) or "").strip()}
        if len(said) < 2:
            row["agreement"] = None
        elif len(set(said.values())) == 1:
            row["agreement"], agree = "agree", agree + 1
        else:
            row["agreement"], split = "split", split + 1
    scored = agree + split
    return {"readers": readers, "scored": scored, "all_agree": agree, "split": split,
            "share_agree": (agree / scored) if scored else None}


# ---------------------------------------------------------------- the run


def run(pages: Path, out: Path, *, model: str, reference_model: str | None, bar: float, cap: float,
        reader_ref: str, language: str | None, kraken=kraken_lines, arms: list[str] | None = None,
        reference_arm: str | None = None, readers: dict | None = None, mlx_choice: dict | None = None,
        fake_arms: bool = False, env_file: Path | None = None) -> dict:
    """`arms`: which readings to make, all on Kraken's own lines (default kraken, A, B). `readers`: an arm's async
    (image, lines) -> {line id: text}, for tests; a free arm without one gets the real reader, or a stub when
    `fake_arms` (`--fake-arms`, the dry run anywhere; `--model fake` is only the cloud models' stub). An arm that fails on a page leaves its cells empty and says why; the others go on."""
    import time

    require_scratch_state()  # every entry that reads a Kraken reader or calls a model, not only main()
    arms = arms or parse_arms(DEFAULT_ARMS)
    readers = dict(readers or {})
    mlx_choice = dict(mlx_choice or {})
    cloud_arms = [a for a in arms if variant_of(a)]
    cloud = bool(cloud_arms)
    ref_arm = reference_arm_for(arms, reference_arm, cloud or reference_model is not None)
    fake = fake_arms
    for arm in arms:  # the real free arms, made once, before any page: a refused model stops the run here
        if arm in readers or arm == "kraken" or variant_of(arm):
            continue
        if kind_of(arm) == "mlx" and not fake:
            name, config, mlx_choice[arm] = pick_mlx(arm.split(":", 1)[1])
            readers[arm] = free_reader(arm, fake=False, config=config)
        else:
            readers[arm] = free_reader(arm, fake=fake)
    ledger = Ledger(cap=cap)
    # every cloud model priced and its key found before any page: a refusal stops the run here ('fake' has none)
    for spec in dict.fromkeys([cloud_spec(a, model) for a in cloud_arms] + ([reference_model] if reference_model else [])):
        provider, _, name = spec.partition(":")
        if provider != "fake" and name:
            if cost_of(provider, name, 1, 1) is None:
                raise SystemExit(f"no price for {spec} in the registry: a cap cannot be kept without one")
            ensure_provider_key(provider, env_file=env_file)
    images = sorted(p for p in pages.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"no page images in {pages}")
    ref_spec = (f"{ref_arm} arm" if ref_arm else reference_model or ("fake-reference" if model == "fake" else model))
    rows: list[dict] = []
    failures: list[dict] = []
    seconds: dict[str, list[float]] = {}
    stopped = None
    sent = total = 0

    def timed(name: str, make):
        began = time.perf_counter()
        try:
            return make()
        except CapReached:
            raise
        except Exception as exc:  # noqa: BLE001 -- an arm that fails leaves its cells empty with a reason; the rest go on
            failures.append({"arm": name, "page": ledger.page, "why": scrub(f"{type(exc).__name__}: {exc}")[:240]})
            return {}
        finally:
            seconds.setdefault(name, []).append(time.perf_counter() - began)

    for image in images:
        ledger.page = image.name
        began = time.perf_counter()
        lines = kraken(image, reader_ref)
        seconds.setdefault("kraken", []).append(time.perf_counter() - began)
        answers: dict[str, dict] = {}
        n = 0
        try:
            for arm in arms:  # the free arms: no model cost, no cap; through the engine's own vision, never the priced wrapper
                if arm in readers:
                    if not fake:
                        from fichero_server import llm

                        llm.vision = _real_vision()
                    ledger.stage = arm
                    answers[arm] = timed(arm, lambda arm=arm: _free_call(readers[arm], image, lines))
            if ref_arm is None:
                ledger.stage = "reference"
                ref_config = install_model(ref_spec, ledger)
                answers["reference"] = timed("reference", lambda: asyncio.run(
                    reading_by_model(image, lines, ref_config, language)))
            for arm in cloud_arms:  # each cloud arm reads on its own model; one ledger, one cap, over all of them
                config = install_model(cloud_spec(arm, model), ledger)
                ledger.stage = arm
                if variant_of(arm) == "A":
                    got = timed(arm, lambda config=config: _Counted(*asyncio.run(reading_unsure(image, lines, config, language, bar))))
                    answers[arm] = dict(got)
                    n += getattr(got, "count", 0)
                else:
                    answers[arm] = timed(arm, lambda config=config: asyncio.run(reading_by_model(image, lines, config, language)))
        except CapReached as exc:
            stopped = f"{image.name}: {exc}"
            break
        sent, total = sent + n, total + len(lines)
        for line in lines:
            row = {"page": image.name, "id": line["id"], "confidence": line["confidence"], "polygon": line["polygon"],
                   "kraken": line["text"],
                   "sent_in_A": any(line["id"] in answers.get(a, {}) for a in cloud_arms if variant_of(a) == "A")}
            for arm in arms:
                if variant_of(arm) == "A":
                    row[arm] = answers.get(arm, {}).get(line["id"], line["text"])
                    row[f"sent:{arm}"] = line["id"] in answers.get(arm, {})
                elif arm != "kraken":
                    row[arm] = answers.get(arm, {}).get(line["id"], "")
            row["reference"] = (row.get(ref_arm) or "") if ref_arm else answers.get("reference", {}).get(line["id"], "")
            rows.append(row)
    report = summarise(rows, ledger, bar=bar, sent=sent, total=total, stopped=stopped, model=model, reference=ref_spec,
                       pages=len(images), arms=arms, ref_arm=ref_arm, seconds=seconds, failures=failures,
                       mlx_choice=mlx_choice, language=language)
    write_outputs(out, rows, report, images)
    return report


def _free_call(reader, image, lines):
    return asyncio.run(reader(image, lines))


class _Counted(dict):
    """A's answers by line id, with how many lines it sent (`timed` hands back one value)."""

    def __init__(self, answers, count):
        super().__init__(answers)
        self.count = count


def outside_script(text: str, language: str | None) -> bool:
    """Whether the text has a letter outside the script its language is written in (Cyrillic in a Spanish line): a reader that
    wrote one did not read the page's hand, whatever the language it was told."""
    import unicodedata

    script = SCRIPT_OF.get((language or "es").split("-")[0].lower(), "LATIN")
    def foreign(ch: str) -> bool:
        name = unicodedata.name(ch, "")
        # ᵒ ᵉ ʳ (MODIFIER LETTER SMALL ...) are the superscripts of early-modern abbreviations (q̃ᵉ, Sʳ), written by a good reader
        return ch.isalpha() and ch not in ORDINALS and not name.startswith((script, "MODIFIER LETTER"))

    return any(foreign(ch) for ch in text or "")


def _width(row: dict) -> float:
    xs = [p[0] for p in row["polygon"]]
    return max(xs) - min(xs)


def summarise(rows, ledger: Ledger, *, bar, sent, total, stopped, model, reference, pages, arms=None, ref_arm=None,
              seconds=None, failures=None, mlx_choice=None, language="es") -> dict:
    arms = arms or parse_arms(DEFAULT_ARMS)
    measured = [r for r in rows if r["reference"].strip()]
    done = len({r["page"] for r in rows})
    label = LABEL if ref_arm is None else f"model reference ({ref_arm}), not ground truth"
    wide = [r for r in measured if _width(r) >= WIDE_PX]
    per_arm = {}
    for arm in arms:
        times = (seconds or {}).get(arm, [])
        per_arm[arm] = {**(rates([(r["reference"], r.get(arm, "")) for r in measured]) if arm != ref_arm
                           else {"cer": None, "wer": None, "lines": 0, "reference_chars": 0, "is_reference": True}),
                        "wide": rates([(r["reference"], r.get(arm, "")) for r in wide]) if arm != ref_arm else None,
                        "s_per_page": (sum(times) / len(times)) if times else None,
                        "usd_per_page": (ledger.by_stage.get(arm, 0.0) / done) if done else None,
                        "lines_read": sum(1 for r in rows if (r.get(arm) or "").strip()),
                        "off_script_lines": sum(1 for r in rows if outside_script(r.get(arm) or "", language)),
                        "pages_failed": len([f for f in (failures or []) if f["arm"] == arm])}
    return {
        "label": label, "model": model, "reference_model": reference, "pages_planned": pages, "arms": arms,
        "reference_arm": ref_arm, "pages_done": done, "lines": len(rows), "lines_with_reference": len(measured),
        "fragments": {"px": WIDE_PX, "lines": sum(1 for r in rows if _width(r) < WIDE_PX), "of": len(rows)},
        "per_arm": per_arm, "kraken": per_arm["kraken"], "A": per_arm.get("A"), "B": per_arm.get("B"),
        "A_lines_sent": sent, "A_lines_total": total, "A_share_sent": (sent / total) if total else None,
        "calibration": calibration(measured, bar), "agreement": agreement(rows, arms), "failures": failures or [],
        "mlx": mlx_choice or {},
        "cost": {"total": ledger.spent, "cap": ledger.cap, "calls": ledger.calls, "by_stage": ledger.by_stage,
                 "by_page": ledger.by_page, "per_page": (ledger.spent / pages) if pages else None,
                 "estimated": model != "fake" and (any(variant_of(a) for a in arms) or ref_arm is None)},
        "stopped": stopped,
    }


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _shown(rows: list[dict]) -> list[dict]:
    """The lines for the owner's sheet: where the readers split first, then the lines Kraken read worst."""
    def worst(r):
        got = line_errors(r["reference"], r["kraken"]) or (0, 1, 0, 1)
        return -got[0] / max(1, got[1])

    split = [r for r in rows if r.get("agreement") == "split"][:30]
    rest = sorted((r for r in rows if r["reference"].strip() and r not in split), key=worst)
    return split + rest[: max(0, 10 - len(split))]


def write_outputs(out: Path, rows: list[dict], report: dict, images: list[Path]) -> None:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    crops = out / "crops"
    crops.mkdir(exist_ok=True)
    pages = {p.name: p for p in images}
    shown = _shown(rows)
    for n, row in enumerate(shown):
        with Image.open(pages[row["page"]]) as im:
            xs, ys = [p[0] for p in row["polygon"]], [p[1] for p in row["polygon"]]
            box = (max(0, int(min(xs))), max(0, int(min(ys))), min(im.width, int(max(xs))), min(im.height, int(max(ys))))
            if box[2] > box[0] and box[3] > box[1]:
                im.convert("RGB").crop(box).save(crops / f"{n:02}.png")
        row["crop"] = f"crops/{n:02}.png"
    (out / "lines.json").write_text(json.dumps({"label": report["label"], "arms": report["arms"], "lines": [
        {k: v for k, v in r.items() if k != "box"} for r in rows]}, indent=1), encoding="utf-8")
    (out / "report.md").write_text(_report_md(report), encoding="utf-8")
    (out / "sheet.html").write_text(_sheet_html(shown, report), encoding="utf-8")


def _arm_title(arm: str, r: dict) -> str:
    if variant_of(arm) and ":" in arm:  # a cloud arm on its own model
        what = {"A": "Kraken, then the model on unsure lines", "B": "the model reads every line"}[variant_of(arm)]
        spec = arm.split(":", 1)[1]
        hosted = f" ({HOSTED_NOT_LOCAL})" if "qwen" in spec.lower() else ""
        return f"{variant_of(arm)} on {spec}: {what}{hosted}"
    return {"kraken": "Kraken alone", "vision": f"Apple Vision ({VISION_LANGUAGE})",
            "A": "A: Kraken, then the model on unsure lines", "B": "B: the model reads every line"
            }.get(arm, f"{arm} (local, MLX)" if arm.startswith("mlx:") else arm)


def _report_md(r: dict) -> str:
    c, cal, ag = r["cost"], r["calibration"], r["agreement"]
    lines = [f"# {', '.join(r['arms'])} on {r['pages_done']} of {r['pages_planned']} pages",
             f"\nAll CER and WER below are against a **{r['label']}** ({r['reference_model']}), over "
             f"{r['lines_with_reference']} of {r['lines']} lines. All arms read the same lines, Kraken's. Model for A and "
             f"B: {r['model']} (unless an arm names its own).\n",
             "| arm | CER | WER | s/page | $/page | lines read | off-script lines |", "|---|---|---|---|---|---|---|"]
    for arm in r["arms"]:
        m = r["per_arm"][arm]
        spp = "n/a" if m["s_per_page"] is None else f"{m['s_per_page']:.1f}"
        usd = "n/a" if m["usd_per_page"] is None else f"${m['usd_per_page']:.4f}"
        errs = ("the reference", "the reference") if m.get("is_reference") else (_pct(m["cer"]), _pct(m["wer"]))
        lines.append(f"| {_arm_title(arm, r)} | {errs[0]} | {errs[1]} | {spp} | {usd} | {m['lines_read']} | {m['off_script_lines']} |")
    lines.append("\nOff-script lines: lines with a letter outside the language's script (Cyrillic in a Spanish line); a reader "
                 "that writes one did not read the hand, whatever language it was told.")
    frag = r["fragments"]
    lines += [f"\n### On lines at least {frag['px']} px wide\n{frag['lines']} of {frag['of']} lines are narrower: fragments, "
              "not lines, which a reader may rightly leave empty. The same arms without them:\n",
              "| arm | CER | WER | lines |", "|---|---|---|---|"]
    for arm in r["arms"]:
        w = r["per_arm"][arm].get("wide")
        lines.append(f"| {_arm_title(arm, r)} | " + (f"{_pct(w['cer'])} | {_pct(w['wer'])} | {w['lines']} |" if w
                                                      else "the reference | the reference | |"))
    if any(variant_of(a) == "A" for a in r["arms"]):
        lines.append(f"\nVariant A sent {r['A_lines_sent']} of {r['A_lines_total']} lines ({_pct(r['A_share_sent'])}).")
    for arm, got in r["mlx"].items():
        lines.append(f"\nLocal model for `{arm}`: {got['repo']} ({got['model']}); {got['why']}; {got['reads_at_once']} reads at once.")
    if ag.get("scored"):
        lines.append(f"\n## Agreement ({', '.join(ag['readers'])})\n"
                     f"{ag['all_agree']} of {ag['scored']} lines read by two or more readers: all agree "
                     f"({_pct(ag['share_agree'])}, probably right); {ag['split']} split (the sheet lists them first).")
    lines += [f"\n## Calibration (bar {cal.get('bar')})\n"
              f"Worst-CER decile ({cal.get('worst_decile_lines')} lines): {_pct(cal.get('worst_decile_below_bar'))} fall "
              f"below the bar (would be sent). Good lines (CER <= {GOOD_LINE_CER:.0%}, {cal.get('good_lines')} lines): "
              f"{_pct(cal.get('good_below_bar'))} fall below it. If the first is not far above the second, Kraken is "
              "confidently wrong and A cannot find its bad lines.",
              f"\n## Cost{' (estimated from the registry price)' if c['estimated'] else ' (fake model or free arms: none)'}\n"
              f"Total ${c['total']:.4f} of the ${c['cap']:.2f} cap over {c['calls']} calls; per page "
              f"${(c['per_page'] or 0):.4f}. By stage: "
              + ", ".join(f"{k or '-'} ${v:.4f}" for k, v in c["by_stage"].items())]
    if r["failures"]:
        lines.append("\n## Arms that failed (their cells are empty)\n" + "\n".join(
            f"- {f['arm']} on {f['page']}: {f['why']}" for f in r["failures"]))
    if r["stopped"]:
        lines.append(f"\n**Stopped at the cap:** {r['stopped']}")
    return "\n".join(lines) + "\n"


def _sheet_html(shown: list[dict], r: dict) -> str:
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    arms = r["arms"]
    body = "".join(
        f"<tr><td><img src='{row.get('crop', '')}' style='max-width:420px'></td>"
        + "".join(f"<td>{esc(row.get(a, ''))}{' (sent)' if variant_of(a) == 'A' and row.get('sent:' + a, row['sent_in_A']) else ''}</td>" for a in arms)
        + f"<td>{esc(row['reference'])}</td><td>{esc(row.get('agreement') or '')}</td></tr>" for row in shown)
    heads = "".join(f"<th>{esc(_arm_title(a, r))}</th>" for a in arms)
    return ("<!doctype html><meta charset=utf-8><title>Readers on Kraken's lines</title><style>body{font:14px system-ui;"
            "margin:2em}td,th{border:1px solid #888;padding:6px;vertical-align:top}table{border-collapse:collapse}</style>"
            f"<h1>Where the readers split, then the lines Kraken read worst</h1><p>The reference column is a "
            f"<b>{esc(r['label'])}</b> ({esc(r['reference_model'])}), not what the page says.</p>"
            f"<table><tr><th>Line</th>{heads}<th>Reference</th><th>Readers</th></tr>{body}</table>")


#: Where the app and the owner keep their own things, under the home directory: never a scratch directory.
OWNER_PLACES = ("Library", "Fichero", "Fichero Projects")


def require_scratch_state() -> None:
    """Refuse to run unless FICHERO_BASE_PATH names a scratch directory: not the app's state (~/Library) and not where
    the owner's projects live (~/Fichero, ~/Fichero Projects), nor inside any of them. Compared after resolve(), so a
    symlink or `..` cannot slip past, and without regard to case (macOS volumes ignore it)."""
    import os

    base = os.environ.get("FICHERO_BASE_PATH", "").strip()
    if not base:
        raise SystemExit("set FICHERO_BASE_PATH to a scratch directory holding kraken-models (a copy of the seeded reader)")
    resolved = Path(base).expanduser().resolve()
    here = [str(q).casefold() for q in (resolved, *resolved.parents)]
    for place in OWNER_PLACES:
        if str((Path.home() / place).resolve()).casefold() in here:
            raise SystemExit(f"FICHERO_BASE_PATH={base} is in ~/{place}, where the app or the owner keeps their own "
                             "things: use a scratch directory")


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
    ap.add_argument("--arms", default=DEFAULT_ARMS, help="comma list of readings, all on Kraken's lines: kraken, vision "
                    "(Apple Vision es-ES), mlx:<Qwen VL model id, or auto> (a local MLX model, installed, within the "
                    "memory gate), A, B (the cloud --model), A:<provider:model> / B:<provider:model> (a cloud model of its own, e.g. "
                    "B:openrouter:anthropic/claude-haiku-4.5)")
    ap.add_argument("--env-file", type=Path, default=AB_ENV, help="where provider keys are looked for when the keychain has none "
                    "(KEY=value lines, mode 600); the keychain, then the environment, are asked first")
    ap.add_argument("--estimate-from", type=Path, help="a free run's lines.json: print each cloud arm's estimated cost on its "
                    "lines (from --arms and --reference-model) and exit; nothing is called, nothing is spent")
    ap.add_argument("--fake-arms", action="store_true", help="free arms answer stub text: the dry run on any machine")
    ap.add_argument("--reference-arm", help="an arm to be the reference when no cloud model is (default: the strongest "
                    "free arm present, mlx then vision)")
    args = ap.parse_args(argv)
    arms = parse_arms(args.arms)
    if args.estimate_from:
        specs = {a: cloud_spec(a, args.model) for a in arms if variant_of(a)}
        if args.reference_model:
            specs["reference"] = args.reference_model
        print(estimate_markdown(estimate_arms(args.estimate_from, specs, bar=args.bar, cap=args.cap)))
        return 0
    reader = args.reader
    if reader is None:
        from fichero_server.recipes.cards import kraken_reader_for

        reader = kraken_reader_for({"zenodo": "10.5281/zenodo.21788410"})  # the seeded PP-OCRv6 medium
    report = run(args.pages, args.out, model=args.model, reference_model=args.reference_model, bar=args.bar,
                 cap=args.cap, reader_ref=reader, language=args.language, arms=arms,
                 reference_arm=args.reference_arm, fake_arms=args.fake_arms, env_file=args.env_file)
    print((args.out / "report.md").read_text(encoding="utf-8"))
    return 0 if not report["stopped"] else 2


if __name__ == "__main__":
    sys.exit(main())
