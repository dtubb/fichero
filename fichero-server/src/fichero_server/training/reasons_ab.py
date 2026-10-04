"""Does a student learn better from a palaeographer's reasons? The A/B decides (#4642, `distill.reasoning.ab-decides`).

The contenders (the answer-only student, the reasoning students, the teacher, a cheap baseline) read
the HELD-OUT checked lines, each asked as it was trained (its arm's prompt), and are scored against the
checked text with the one CER (`workflows.transcription_accuracy`, summed over lines: total edits over
total reference characters) and a WER the same way over words. A reasoning student is also asked with the
answer-only prompt, its reasoning switched off, since at a million pages the reasoning is the cost. For
a `why` contender, how many of its errors fall on the lines it called uncertain is reported.

The reasoning student is adopted only if its CER beats the answer-only student's by more than the noise
band (0.5 CER points, the project's ruling); the result is written on every Fichero-trained contender's
card either way. Speed is seconds per line here; peak memory on a 16 GB Mac is not visible from the
engine (the model runs in the MLX server) and is recorded as not measured.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fichero_server.training.reasons import READ, Line, parse_reasons, split_thinking

#: 0.5 CER points (Sergio project ruling, 2026-10-03): smaller differences are noise.
NOISE_BAND = 0.005
ARMS = ("answer", "why", "thinking")


@dataclass(frozen=True)
class Contender:
    label: str
    provider: str
    model: str
    arm: str = "answer"  # how it is asked: as it was trained
    reasoning: bool = True  # False: a reasoning student asked with the answer-only prompt
    role: str = "student"  # student, teacher or baseline: only students are adopted


@dataclass
class Score:
    label: str
    model: str
    arm: str
    reasoning: bool
    role: str = "student"
    lines: int = 0
    unread: int = 0
    char_edits: int = 0
    chars: int = 0
    word_edits: int = 0
    words: int = 0
    seconds: float = 0.0
    errors: int = 0
    errors_on_uncertain: int = 0
    flagged_uncertain: int = 0

    @property
    def cer(self) -> float | None:
        return self.char_edits / self.chars if self.chars else None

    @property
    def wer(self) -> float | None:
        return self.word_edits / self.words if self.words else None

    def summary(self) -> dict[str, Any]:
        out = {"label": self.label, "model": self.model, "arm": self.arm, "reasoning": self.reasoning, "role": self.role,
               "lines": self.lines, "unread": self.unread, "cer": self.cer, "wer": self.wer,
               "seconds_per_line": round(self.seconds / self.lines, 3) if self.lines else None,
               "peak_memory_gb": None, "peak_memory_note": "not measured: the model runs in the MLX server"}
        if self.arm == "why" and self.reasoning:
            out["uncertain"] = {"flagged": self.flagged_uncertain, "errors": self.errors,
                                "errors_on_flagged": self.errors_on_uncertain}
        return out


def answer_text(raw: str, arm: str) -> tuple[str | None, bool]:
    """The reading in a contender's answer, as its arm writes it, and whether it called the line uncertain."""
    from fichero_server.llm.line_reader import parse_answer

    answer, _thinking = split_thinking(raw)
    if arm == "why":
        parsed = parse_reasons(answer, 1)
        if not parsed or parsed[0] is None:
            return None, False
        return parsed[0]["text"], bool(parsed[0].get("uncertain"))
    parsed = parse_answer(answer, 1)
    return (parsed[0] if parsed else None), False


def _word_edits(reference: str, hypothesis: str) -> tuple[int, int]:
    """Word-level edit distance, on the exact character distance with each distinct word as one character."""
    from fichero_server.llm.multilingual import levenshtein_distance

    vocab: dict[str, str] = {}

    def code(words: list[str]) -> str:
        return "".join(vocab.setdefault(w, chr(0xE000 + len(vocab))) for w in words)

    ref, hyp = reference.split(), hypothesis.split()
    return levenshtein_distance(code(ref), code(hyp)), len(ref)


def score_line(score: Score, checked: str, read: str | None, uncertain: bool) -> None:
    from fichero_server.workflows.transcription_accuracy import RunComparisonError, character_error_rate

    score.lines += 1
    try:
        cer = character_error_rate(checked, read or "")
    except RunComparisonError:
        return
    score.char_edits += cer.distance
    score.chars += cer.reference_chars
    edits, words = _word_edits(checked, read or "")
    score.word_edits += edits
    score.words += words
    score.unread += read is None
    wrong = cer.distance > 0
    score.errors += wrong
    score.flagged_uncertain += uncertain
    score.errors_on_uncertain += wrong and uncertain


Ask = Callable[[Contender, list[str], str], Awaitable[str]]


async def measure(lines: list[Line], photos: dict[str, Path], contenders: list[Contender], *, ask: Ask,
                  language: str | None = None, concurrent: int = 2) -> list[Score]:
    """Every contender reads every held-out line, one line a call, as it was trained."""
    from PIL import Image

    from fichero_server.llm.line_reader import _crop_data_uri
    from fichero_server.llm.line_reader import prompt_for as answer_prompt
    from fichero_server.training import reasons

    pages = {doc_id: Image.open(path) for doc_id, path in photos.items()}
    crops = {line.line_id: _crop_data_uri(pages[line.document_id], line.polygon) for line in lines}
    gate = asyncio.Semaphore(concurrent)
    scores = []
    for contender in contenders:
        arm = contender.arm if contender.reasoning else "answer"
        prompt = reasons.prompt_for(READ, 1, language) if arm == "why" else answer_prompt(1, language)
        score = Score(contender.label, contender.model, contender.arm, contender.reasoning, contender.role)

        async def one(line: Line) -> tuple[Line, str, float]:
            async with gate:
                started = time.monotonic()
                raw = await ask(contender, [crops[line.line_id]], prompt)
                return line, raw, time.monotonic() - started

        for line, raw, seconds in await asyncio.gather(*(one(line) for line in lines)):
            read, uncertain = answer_text(raw, arm)
            score_line(score, line.checked, read, uncertain)
            score.seconds += seconds
        scores.append(score)
    return scores


def decide(scores: list[Score], *, noise_band: float = NOISE_BAND) -> dict[str, Any]:
    """Each reasoning student against the answer-only student: adopted only beyond the noise band."""
    students = [s for s in scores if s.role == "student"]
    answer = next((s for s in students if s.arm == "answer" and s.cer is not None), None)
    verdicts = {}
    for s in students:
        if s.arm not in ("why", "thinking") or not s.reasoning or s.cer is None or answer is None:
            continue
        gain = answer.cer - s.cer
        verdicts[s.label] = {"against": answer.label, "cer": s.cer, "answer_only_cer": answer.cer,
                             "gain": round(gain, 6), "adopted": gain > noise_band,
                             "why": (f"beats the answer-only student by {gain:.4f} CER, beyond the noise band "
                                     f"({noise_band})") if gain > noise_band else
                                    (f"within the noise band ({gain:+.4f} against {noise_band}): the answer-only "
                                     "student stays")}
    return {"noise_band": noise_band, "verdicts": verdicts, "scores": [s.summary() for s in scores],
            "measured_at": datetime.now(timezone.utc).isoformat()}


def record_on_cards(result: dict[str, Any], contenders: list[Contender], *, held_out: list[str]) -> list[str]:
    """Write the A/B on every Fichero-trained contender's card, adopted or not; returns the models written."""
    from fichero_server.llm.mlx_model_store import TRAINED_CARD, TRAINED_ORG, get_mlx_model_store

    store = get_mlx_model_store()
    written = []
    for model in sorted({c.model.removeprefix("omlx/") for c in contenders}):
        if not model.startswith(f"{TRAINED_ORG}/"):
            continue
        path = store.trained_dir(model) / TRAINED_CARD
        if not path.is_file():
            continue
        card = json.loads(path.read_text(encoding="utf-8"))
        card.setdefault("reasons_ab", []).append({**result, "held_out": held_out})
        path.write_text(json.dumps(card, indent=1), encoding="utf-8")
        written.append(model)
    return written


def default_ask() -> Ask:
    async def ask(contender: Contender, images: list[str], prompt: str) -> str:
        from fichero_server.llm import LLMConfig, vision

        return await vision(images=images, prompt=prompt, config=LLMConfig(provider=contender.provider,
                                                                         model=contender.model))
    return ask


async def run_ab(db: Any, *, checked: str, held_out_ids: list[str], contenders: list[Contender],
                 language: str | None = None, ask: Ask | None = None,
                 noise_band: float = NOISE_BAND) -> dict[str, Any]:
    """Measure, decide and record: the whole A/B on the held-out checked pages."""
    from fichero_server.training.reasons import checked_lines

    if not held_out_ids:
        raise ValueError("name the held-out checked pages: the A/B is measured only on pages no arm trained on")
    unknown = [c.arm for c in contenders if c.arm not in ARMS]
    if unknown:
        raise ValueError(f"no arm {unknown[0]!r}: answer, why or thinking")
    asked = list(contenders)
    for c in contenders:  # a reasoning student is also measured with its reasoning switched off
        if c.arm != "answer" and c.reasoning:
            asked.append(Contender(f"{c.label} (no reasoning)", c.provider, c.model, c.arm, False, c.role))
    lines, photos, missing = checked_lines(db, scope_ids=held_out_ids, checked=checked)
    if not lines:
        raise ValueError(f"no checked lines on the held-out pages ({len(missing)} missing)")
    scores = await measure(lines, photos, asked, ask=ask or default_ask(), language=language)
    result = decide(scores, noise_band=noise_band)
    result["missing"] = missing
    result["cards"] = record_on_cards(result, contenders, held_out=held_out_ids)
    return result
