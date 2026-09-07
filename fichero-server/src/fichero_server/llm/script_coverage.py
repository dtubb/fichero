"""Producer for LOOVE-style tokenizer-coverage JSON.

The *consumer* half already exists — ``llm.language_coverage`` loads derived
LOOVE-style coverage JSON from ``default_coverage_dir()`` and turns it into a
``LanguageCoverageRecord`` (score band, tier counts, fertility). Nothing wrote
that JSON. This module is the missing producer: given a model's tokenizer and a
set of languages, it classifies each script's exemplar characters into loove's
four tiers and emits JSON in the *exact* shape ``language_coverage`` parses.

loove's tiers (github.com/apjanco/loove):

- Tier 0 — dedicated single-character token (weight 1.0). The model sees the
           letter.
- Tier 1 — survives only inside multi-token merges (0.7). Blurrier.
- Tier 2 — survives only as raw UTF-8 byte-fallback tokens (0.2). Bytes, not
           letters — where yat (ѣ), Coptic, cuneiform fall.
- Tier 3 — can't round-trip at all → unk / loss (0.0). The character is gone.

Plus fertility = tokens per character / per word on a sample (the token tax).

Pure-Python, offline, deterministic: no model inference, no network. tiktoken /
transformers are lazy-imported inside the loader so importing this module stays
cheap and free of hard dependencies. When no tokenizer can be obtained for a
model, the producer writes *no file* rather than a guess — the consumer then
falls back to its own transparent heuristic. That is the honest-absence
principle, not a silent substitution.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Tier -> weight (loove's weights). coverage_score is the mean weight over a
# script's exemplar chars, in [0, 1] — matching language_coverage.score_band.
TIER_WEIGHTS: dict[int, float] = {0: 1.0, 1: 0.7, 2: 0.2, 3: 0.0}


@runtime_checkable
class Tokenizer(Protocol):
    """Minimal shape shared by tiktoken and HF AutoTokenizer."""

    def encode(self, text: str) -> list[int]: ...

    def decode(self, ids: list[int]) -> str: ...


# ---------------------------------------------------------------------------
# Exemplar table — a *starter* set, keyed by Unicode script name (matching the
# `script` field on language_coverage.LanguageSpec). Not the full 8000-language
# sweep (YAGNI).
#
# ponytail: hardcoded starter set covering the scripts that matter for the SCOOP
# demo. A dozen chars per script is plenty to score a tokenizer. Expand from
# CLDR exemplar sets (per-language `exemplarCharacters`) when a real library
# turns up a script not represented here — the producer simply skips languages
# whose script is absent, so the consumer falls back cleanly.
# ---------------------------------------------------------------------------
SCRIPT_EXEMPLARS: dict[str, str] = {
    "Latin": "abcdefghijklmnopqrstuvwxyzáéíóúñçüöäàèìòùâêîôûãõ",
    "Cyrillic": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    # Pre-1918 Russian orthography — letters *removed* by the reform, so a
    # modern tokenizer usually has no dedicated token for them: byte-fallback or
    # unk. The loove demo money-shot. Score a language against it by passing a
    # LanguageSpec with script="Cyrillic_Pre1918".
    "Cyrillic_Pre1918": "ѣѵіѳ",  # yat, izhitsa, decimal-i, fita
    "Greek": "αβγδεζηθικλμνξοπρστυφχψω",
    "Coptic": "ⲁⲃⲅⲇⲉⲍⲏⲑ",
    "Georgian": "აბგდევზთიკლ",
    "Armenian": "աբգդեզէըթժ",
}

# Representative sample strings for fertility. Falls back to exemplar chars.
SCRIPT_SAMPLES: dict[str, str] = {
    "Latin": "the quick brown fox jumps over the lazy dog",
    "Cyrillic": "быстрая коричневая лиса прыгает через ленивую собаку",
    "Cyrillic_Pre1918": "въ лѣто отъ сотворенія міра",
    "Greek": "η γρήγορη καφέ αλεπού πηδάει πάνω από το τεμπέλικο σκυλί",
    "Coptic": "ⲁⲛⲟⲕ ⲡⲉ ⲡⲟⲩⲟⲉⲓⲛ",
}

_BYTE_MARKER_RE = re.compile(r"<0x[0-9A-Fa-f]{2}>")


def _is_byte_fallback_token(piece: str) -> bool:
    """Does this decoded token piece look like raw byte fallback?

    HF byte-fallback tokens render as ``<0xD1>``; a lone byte decoded as UTF-8
    yields the U+FFFD replacement char. Either marks byte fallback.
    """
    if "�" in piece:
        return True
    stripped = piece.strip()
    return bool(_BYTE_MARKER_RE.fullmatch(stripped))


def classify_char(tokenizer: Tokenizer, char: str) -> int:
    """Classify one character into tier 0-3 against ``tokenizer``.

    - tier 0: encodes to exactly one token that decodes back to the char
    - tier 1: round-trips in >1 token, none byte-fallback
    - tier 2: only survives via byte-fallback tokens
    - tier 3: cannot round-trip (unk / loss)
    """
    try:
        ids = tokenizer.encode(char)
    except Exception:
        return 3
    if not ids:
        return 3
    try:
        decoded = tokenizer.decode(ids)
    except Exception:
        return 3
    if decoded != char:
        return 3

    pieces: list[str] = []
    for tid in ids:
        try:
            pieces.append(tokenizer.decode([tid]))
        except Exception:
            pieces.append("�")  # undecodable alone => byte-level fallback

    any_byte_fallback = any(_is_byte_fallback_token(p) for p in pieces)
    if len(ids) == 1 and not any_byte_fallback:
        return 0
    if any_byte_fallback:
        return 2
    return 1


def _exemplars_for(script: str | None) -> str | None:
    if not script:
        return None
    return SCRIPT_EXEMPLARS.get(script)


def _fertility_block(tokenizer: Tokenizer, sample: str) -> dict[str, Any] | None:
    """Fertility metrics in language_coverage's LanguageFertility shape."""
    if not sample:
        return None
    try:
        ids = tokenizer.encode(sample)
    except Exception:
        return None
    sample_chars = len(sample)
    sample_tokens = len(ids)
    words = [w for w in sample.split() if w]
    return {
        "tokens_per_char": sample_tokens / sample_chars if sample_chars else None,
        "tokens_per_word": sample_tokens / len(words) if words else None,
        "sample_chars": sample_chars,
        "sample_tokens": sample_tokens,
    }


def language_coverage_payload(tokenizer: Tokenizer, language: Any) -> dict[str, Any] | None:
    """Per-language coverage dict in the exact shape language_coverage parses.

    ``language`` is a language_coverage.LanguageSpec (or anything with ``code``,
    ``name``, ``script``). Returns None when the script has no exemplar table —
    the producer then omits the language, and the consumer falls back.
    """
    script = getattr(language, "script", None)
    exemplars = _exemplars_for(script)
    if not exemplars:
        return None

    tiers = [classify_char(tokenizer, ch) for ch in exemplars]
    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for t in tiers:
        counts[t] += 1
    total = len(tiers)
    coverage_score = sum(TIER_WEIGHTS[t] for t in tiers) / total if total else None

    sample = SCRIPT_SAMPLES.get(script, exemplars)
    payload: dict[str, Any] = {
        "language": getattr(language, "code", None),
        "language_name": getattr(language, "name", None),
        "script": script,
        "coverage_score": coverage_score,
        "tier_counts": {
            "tier_0_native": counts[0],
            "tier_1_embedded": counts[1],
            "tier_2_byte_fallback": counts[2],
            "tier_3_unreachable": counts[3],
            "total_chars": total,
        },
    }
    fertility = _fertility_block(tokenizer, sample)
    if fertility is not None:
        payload["fertility"] = fertility
    return payload


def build_coverage_document(
    model_id: str, tokenizer: Tokenizer, languages: list[Any]
) -> dict[str, Any]:
    """Root coverage document: {model_id, generated_at, coverage: {code: ...}}.

    Only languages whose script has an exemplar table are included.
    """
    coverage: dict[str, Any] = {}
    for lang in languages:
        payload = language_coverage_payload(tokenizer, lang)
        if payload is not None:
            coverage[getattr(lang, "code")] = payload
    return {
        "model_id": model_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": coverage,
    }


def load_tokenizer(model_id: str) -> Tokenizer | None:
    """Best-effort tokenizer for a model id, or None if none is obtainable.

    OpenAI-family ids go through tiktoken; everything else (local / MLX / HF ids)
    through HF ``AutoTokenizer``. Both imports are lazy so this module stays
    importable without tiktoken/transformers. Returns None when no tokenizer can
    be built — the caller must then write no file rather than guess.
    """
    if not model_id:
        return None
    lowered = model_id.lower()
    bare = lowered.split("/")[-1]

    openai_markers = ("gpt-", "gpt3", "gpt4", "o1", "o3", "o4", "text-embedding", "davinci")
    if bare.startswith(openai_markers) or lowered.startswith("openai"):
        try:
            import tiktoken  # noqa: PLC0415  (lazy on purpose)
        except Exception:
            return None
        try:
            return tiktoken.encoding_for_model(bare)  # type: ignore[return-value]
        except Exception:
            try:
                return tiktoken.get_encoding("cl100k_base")  # type: ignore[return-value]
            except Exception:
                return None

    try:
        from transformers import AutoTokenizer  # noqa: PLC0415  (lazy on purpose)
    except Exception:
        return None
    try:
        return AutoTokenizer.from_pretrained(model_id)  # type: ignore[return-value]
    except Exception:
        return None


def _coverage_path(provider: str, model: str, coverage_dir: Path) -> Path:
    """Filename the consumer's _coverage_file_for looks for, first candidate."""
    # Reuse the consumer's exact sanitizer so the file lands where it reads.
    from fichero_server.llm.language_coverage import _safe_filename  # noqa: PLC0415

    return coverage_dir / f"{_safe_filename(provider)}__{_safe_filename(model)}.json"


def write_coverage_file(
    provider: str,
    model_id: str,
    languages: list[Any],
    *,
    tokenizer: Tokenizer | None = None,
    coverage_dir: Path | None = None,
) -> Path | None:
    """Produce and write a model's coverage JSON where language_coverage reads it.

    Returns the written path, or None when no tokenizer is obtainable (honest
    absence — the consumer falls back to its heuristic; we never fabricate a
    derived file). ``tokenizer`` may be supplied directly (tests / preloaded);
    otherwise it is loaded from ``model_id``.
    """
    tok = tokenizer if tokenizer is not None else load_tokenizer(model_id)
    if tok is None:
        return None

    from fichero_server.llm.language_coverage import default_coverage_dir  # noqa: PLC0415

    out_dir = coverage_dir or default_coverage_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    document = build_coverage_document(model_id, tok, languages)
    path = _coverage_path(provider, model_id, out_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic
    return path
