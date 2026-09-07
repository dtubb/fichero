"""Producer for LOOVE-style tokenizer-coverage records.

The *consumer* half already exists — ``llm.language_coverage`` turns derived
LOOVE-style coverage JSON into a ``LanguageCoverageRecord`` (score band, tier
counts, fertility) and serves it through ``recommend_language_fit`` /
``evaluate_language_fit`` and the ``/language-fit`` endpoint. Nothing produced
that JSON. This module is the missing producer, and it speaks the consumer's
own types.

It classifies a script's exemplar characters against a model's tokenizer into
loove's four tiers, computes a weighted coverage score + fertility, and:

- ``coverage_for_model`` assembles a ``LanguageCoverageRecord`` in memory, and
- ``write_coverage_record`` writes JSON into ``default_coverage_dir()`` in the
  exact shape ``_load_derived_record`` reads back, so ``evaluate_language_fit``
  serves it as ``status="derived"``.

loove tiers → weights: tier 0 dedicated single token (1.0), tier 1 merge-only
(0.7), tier 2 byte-fallback (0.2), tier 3 unk/loss (0.0). coverage_score is the
mean weight over exemplars, in [0, 1] — matching ``language_coverage.score_band``.

Pure-Python, offline, deterministic: no model inference, no network.
tiktoken / transformers are lazy-imported inside the loader so importing this
module stays cheap. Honest unknown: when no tokenizer can be obtained (some
cloud models publish none), the record has ``coverage_score=None`` and a
``tokenizer_unavailable`` reason — never a guessed number. Writing that explicit
unknown is deliberate: it suppresses the consumer's heuristic guess, which is
what would otherwise fill the gap.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fichero_server.llm.language_coverage import (
    LanguageCoverageRecord,
    LanguageCoverageSource,
    LanguageFertility,
    LanguageSpec,
    LanguageTierCounts,
    default_coverage_dir,
    normalized_model_id,
    score_band,
)
from fichero_server.llm.language_coverage import _safe_filename  # producer/consumer pair

# loove tier → weight. coverage_score = mean weight over a script's exemplars.
TIER_WEIGHTS: dict[int, float] = {0: 1.0, 1: 0.7, 2: 0.2, 3: 0.0}


@runtime_checkable
class Tokenizer(Protocol):
    """Minimal shape shared by tiktoken and HF AutoTokenizer."""

    def encode(self, text: str) -> list[int]: ...

    def decode(self, ids: list[int]) -> str: ...


# ---------------------------------------------------------------------------
# Exemplar table — a *starter* set, keyed by Unicode script name (matching the
# ``script`` field on language_coverage.LanguageSpec). Not the full
# 8000-language sweep (YAGNI).
#
# ponytail: hardcoded starter set covering the scripts that matter for the SCOOP
# demo. A dozen chars per script is plenty to score a tokenizer. Expand from
# CLDR exemplar sets (per-language `exemplarCharacters`) when a real library
# turns up a script not represented here — languages whose script is absent get
# an honest unsupported_language record rather than a fabricated score.
# ---------------------------------------------------------------------------
SCRIPT_EXEMPLARS: dict[str, str] = {
    "Latin": "abcdefghijklmnopqrstuvwxyzáéíóúñçüöäàèìòùâêîôûãõ",
    "Cyrillic": "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    # Pre-1918 Russian orthography — letters *removed* by the reform, so a
    # modern tokenizer usually has no dedicated token for them: byte-fallback or
    # unk. The loove demo money-shot. Score a language against it with a
    # LanguageSpec whose script is "Cyrillic_Pre1918".
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

TOKENIZER_UNAVAILABLE = "tokenizer_unavailable"


def _is_byte_fallback_token(piece: str) -> bool:
    """Does this decoded token piece look like raw byte fallback?

    HF byte-fallback tokens render as ``<0xD1>``; a lone byte decoded as UTF-8
    yields the U+FFFD replacement char. Either marks byte fallback.
    """
    if "�" in piece:
        return True
    return bool(_BYTE_MARKER_RE.fullmatch(piece.strip()))


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


def _fertility(tokenizer: Tokenizer, sample: str) -> LanguageFertility | None:
    """Fertility metrics in the consumer's LanguageFertility shape."""
    if not sample:
        return None
    try:
        ids = tokenizer.encode(sample)
    except Exception:
        return None
    sample_chars = len(sample)
    sample_tokens = len(ids)
    words = [w for w in sample.split() if w]
    return LanguageFertility(
        tokens_per_char=sample_tokens / sample_chars if sample_chars else None,
        tokens_per_word=sample_tokens / len(words) if words else None,
        sample_chars=sample_chars,
        sample_tokens=sample_tokens,
    )


def _tier_counts(tokenizer: Tokenizer, exemplars: str) -> tuple[LanguageTierCounts, float]:
    """Count exemplar chars per tier and return (counts, coverage_score)."""
    counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for ch in exemplars:
        counts[classify_char(tokenizer, ch)] += 1
    total = len(exemplars)
    score = sum(TIER_WEIGHTS[t] * n for t, n in counts.items()) / total if total else 0.0
    return (
        LanguageTierCounts(
            tier_0_native=counts[0],
            tier_1_embedded=counts[1],
            tier_2_byte_fallback=counts[2],
            tier_3_unreachable=counts[3],
            total_chars=total,
        ),
        score,
    )


@lru_cache(maxsize=64)
def load_tokenizer(model_id: str) -> Tokenizer | None:
    """Best-effort tokenizer for a model id, or None if none is obtainable.

    OpenAI-family ids go through tiktoken; everything else (local / MLX / HF ids)
    through HF ``AutoTokenizer``. Both imports are lazy so this module stays
    importable without tiktoken/transformers. Returns None when no tokenizer can
    be built — the caller then emits an honest ``tokenizer_unavailable`` record.

    Cached so a model's tokenizer is loaded at most once per process (the lazy
    fit trigger calls this on every miss).
    # ponytail: lru_cache also memoizes a None result, so we don't re-attempt a
    # failed HF load every call; a transient failure stays cached until restart.
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
        # local_files_only: never hit the network. A configured/provisioned model
        # already has its tokenizer on disk; anything else is honestly "no
        # tokenizer" and the consumer falls back to its heuristic.
        return AutoTokenizer.from_pretrained(model_id, local_files_only=True)  # type: ignore[return-value]
    except Exception:
        return None


def coverage_for_model(
    model_id: str,
    language: LanguageSpec,
    *,
    provider: str = "",
    tokenizer: Tokenizer | None = None,
) -> LanguageCoverageRecord:
    """Assemble a LanguageCoverageRecord for one (model, language) in memory.

    ``tokenizer`` may be supplied (tests / preloaded); otherwise it is loaded
    from ``model_id``. Honest unknowns:

    - no tokenizer  -> coverage_score=None, band "unknown", tokenizer_unavailable
                       reason (never a guess).
    - unknown script -> status "unsupported_language" (no exemplar table to score
                       it), so the consumer can fall back transparently.
    """
    nmid = normalized_model_id(provider, model_id)

    tok = tokenizer if tokenizer is not None else load_tokenizer(model_id)
    if tok is None:
        return LanguageCoverageRecord(
            provider=provider,
            model=model_id,
            normalized_model_id=nmid,
            language=language,
            coverage_score=None,
            score_band=score_band(None),
            tier_counts=None,
            fertility=None,
            source=LanguageCoverageSource(
                kind="missing", model_id=nmid, notes=[TOKENIZER_UNAVAILABLE]
            ),
            status="derived",
            warnings=[
                "No tokenizer could be loaded for this model; coverage is "
                "unknown and no heuristic guess is made."
            ],
        )

    exemplars = SCRIPT_EXEMPLARS.get(language.script or "")
    if not exemplars:
        warning = (
            f"No exemplar table for script '{language.script}'; cannot derive "
            "tokenizer coverage for this language."
        )
        return LanguageCoverageRecord(
            provider=provider,
            model=model_id,
            normalized_model_id=nmid,
            language=language,
            coverage_score=None,
            score_band=score_band(None),
            tier_counts=None,
            fertility=None,
            source=LanguageCoverageSource(kind="missing", model_id=nmid, notes=[warning]),
            status="unsupported_language",
            warnings=[warning],
        )

    counts, score = _tier_counts(tok, exemplars)
    sample = SCRIPT_SAMPLES.get(language.script or "", exemplars)
    return LanguageCoverageRecord(
        provider=provider,
        model=model_id,
        normalized_model_id=nmid,
        language=language,
        coverage_score=score,
        score_band=score_band(score),
        tier_counts=counts,
        fertility=_fertility(tok, sample),
        source=LanguageCoverageSource(
            kind="loove_derived_json",
            model_id=nmid,
            notes=["Derived from local tokenizer; no model inference, no network."],
        ),
        status="derived",
        warnings=[],
    )


def _record_to_payload(record: LanguageCoverageRecord) -> dict[str, Any]:
    """Serialize a record into the per-language JSON _load_derived_record reads."""
    payload: dict[str, Any] = {
        "language": record.language.code,
        "language_name": record.language.name,
        "script": record.language.script,
        "coverage_score": record.coverage_score,
    }
    if record.tier_counts is not None:
        payload["tier_counts"] = record.tier_counts.model_dump()
    if record.fertility is not None:
        payload["fertility"] = record.fertility.model_dump()
    if record.source.notes:
        payload["notes"] = list(record.source.notes)
    return payload


def _target_path(provider: str, model_id: str, coverage_dir: Path) -> Path:
    """The file the consumer's _coverage_file_for looks up (its first candidate)."""
    safe_model = _safe_filename(model_id)
    if provider:
        return coverage_dir / f"{_safe_filename(provider)}__{safe_model}.json"
    return coverage_dir / f"{safe_model}.json"


def write_coverage_record(
    model_id: str,
    language: LanguageSpec,
    *,
    provider: str = "",
    coverage_dir: Path | None = None,
    tokenizer: Tokenizer | None = None,
) -> Path | None:
    """Write one (model, language) coverage entry where language_coverage reads it.

    Merges into the model's existing file (a model accrues one entry per detected
    script) and writes atomically. Returns the written path, or None when there
    is nothing real to record — no tokenizer, or a script with no exemplar table.
    In that case we write NO file so the consumer falls back to its transparent
    heuristic; we never fabricate a derived score. (Any pre-existing file is left
    untouched and its path returned.)
    """
    record = coverage_for_model(
        model_id, language, provider=provider, tokenizer=tokenizer
    )
    out_dir = coverage_dir or default_coverage_dir()
    path = _target_path(provider, model_id, out_dir)

    if record.coverage_score is None:
        return path if path.is_file() else None

    out_dir.mkdir(parents=True, exist_ok=True)
    document: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                document = existing
        except (OSError, json.JSONDecodeError):
            document = {}  # unreadable -> start fresh rather than fail

    coverage = document.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}

    coverage[language.code] = _record_to_payload(record)

    document["model_id"] = normalized_model_id(provider, model_id)
    document["generated_at"] = datetime.now(timezone.utc).isoformat()
    document["coverage"] = coverage

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic
    return path
