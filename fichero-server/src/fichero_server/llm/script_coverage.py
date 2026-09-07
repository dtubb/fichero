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
    # Arabic base letters (isolated forms) — RTL, but coverage classifies each
    # codepoint independently.
    "Arabic": "ابتثجحخدذرزسشصضطظعغفقكلمنهوي",
    # Hebrew alphabet (no final-form variants in this starter set).
    "Hebrew": "אבגדהוזחטיכלמנסעפצקרשת",
}

# Representative sample strings for fertility. Falls back to exemplar chars.
SCRIPT_SAMPLES: dict[str, str] = {
    "Latin": "the quick brown fox jumps over the lazy dog",
    "Cyrillic": "быстрая коричневая лиса прыгает через ленивую собаку",
    "Cyrillic_Pre1918": "въ лѣто отъ сотворенія міра",
    "Greek": "η γρήγορη καφέ αλεπού πηδάει πάνω από το τεμπέλικο σκυλί",
    "Coptic": "ⲁⲛⲟⲕ ⲡⲉ ⲡⲟⲩⲟⲉⲓⲛ",
    "Arabic": "السلام عليكم ورحمة الله وبركاته",
    "Hebrew": "השועל החום המהיר קופץ מעל הכלב העצלן",
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
def load_tokenizer(model_id: str, allow_download: bool = True) -> Tokenizer | None:
    """Best-effort tokenizer for a model id, or None if none is obtainable.

    OpenAI-family ids go through tiktoken; everything else (local / MLX / HF ids)
    through HF ``AutoTokenizer``. Both imports are lazy so this module stays
    importable without tiktoken/transformers.

    ``allow_download`` (default True): the HF path fetches the model's TOKENIZER
    FILES ONLY (tokenizer.json / vocab / merges — KB–MB), never the multi-GB
    weights. This is deliberate — loove must run for real to be worth anything,
    so it downloads the tiny tokenizer to compute genuine coverage and the result
    is cached. Set False to restrict to already-on-disk tokenizers.

    Returns None when no tokenizer can be built — a model with no published
    tokenizer (Apple), a vision-only model, or a gated model needing a token that
    isn't set. The caller then emits an honest unknown record — never a guess.

    Cached so a model's tokenizer is fetched/loaded at most once per process.
    # ponytail: lru_cache also memoizes a None result, so we don't re-attempt a
    # failed/gated HF fetch every call; a transient failure stays cached until
    # restart (delete the cache dir or restart to retry).
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
        # Fetches tokenizer files only (never weights). A gated/vision-only/
        # unpublished model raises here -> None -> honest unknown, never a crash.
        return AutoTokenizer.from_pretrained(  # type: ignore[return-value]
            model_id, local_files_only=not allow_download
        )
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


def _upsert_coverage_entries(
    provider: str,
    model_id: str,
    entries: dict[str, dict[str, Any]],
    coverage_dir: Path,
    *,
    provenance: str,
) -> Path:
    """Merge per-language ``entries`` into the model's cache file, atomically.

    A model accrues one small entry per requested language — we never store the
    whole 5 MB source file, only the filtered languages we were asked for.
    """
    out_dir = coverage_dir or default_coverage_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = _target_path(provider, model_id, out_dir)

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
    coverage.update(entries)

    document["model_id"] = normalized_model_id(provider, model_id)
    document["generated_at"] = datetime.now(timezone.utc).isoformat()
    document["coverage_provider"] = provenance  # surfaces as a provenance note
    document["coverage"] = coverage

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic
    return path


def write_coverage_record(
    model_id: str,
    language: LanguageSpec,
    *,
    provider: str = "",
    coverage_dir: Path | None = None,
    tokenizer: Tokenizer | None = None,
) -> Path | None:
    """Write one (model, language) coverage entry from OUR own tokenizer compute.

    Returns the written path, or None when there is nothing real to record — no
    tokenizer, or a script with no exemplar table. In that case we write NO file
    so the consumer returns honest unknown; we never fabricate a derived score.
    (Any pre-existing file is left untouched and its path returned.)
    """
    record = coverage_for_model(
        model_id, language, provider=provider, tokenizer=tokenizer
    )
    out_dir = coverage_dir or default_coverage_dir()
    path = _target_path(provider, model_id, out_dir)
    if record.coverage_score is None:
        return path if path.is_file() else None
    return _upsert_coverage_entries(
        provider,
        model_id,
        {language.code: _record_to_payload(record)},
        out_dir,
        provenance="fichero-local-tokenizer",
    )


# ---------------------------------------------------------------------------
# Consume Andy Janco's authoritative published coverage (HF Space apjanco/loove)
# ---------------------------------------------------------------------------

ANDY_COVERAGE_BASE = (
    "https://huggingface.co/spaces/apjanco/loove/resolve/main/data/coverage"
)
ANDY_PROVENANCE = "apjanco/loove"


def andy_coverage_filename(model_id: str) -> str:
    """Andy's per-model file name: repo id with '/' -> '__' (OpenAI ids as-is)."""
    return f"{model_id.replace('/', '__')}.json"


def _http_get_bytes(url: str, timeout: float = 30.0) -> bytes:
    """GET raw bytes. Module-level so tests can stub it (kept dependency-free)."""
    import urllib.request  # noqa: PLC0415 (lazy: importing this module stays cheap)

    req = urllib.request.Request(url, headers={"User-Agent": "fichero-loove"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


@lru_cache(maxsize=4)
def _fetch_andy_doc(model_id: str) -> dict[str, Any] | None:
    """Fetch + parse Andy's full coverage doc for a model, or None if absent.

    Cached (small maxsize) so several languages for one model reuse a single
    download within the process instead of re-fetching the ~5 MB file each time.
    404 / network error / bad JSON -> None (caller falls back). Never raises.
    # ponytail: maxsize=4 holds at most ~4 * 5 MB; bump only if the matrix widens.
    """
    url = f"{ANDY_COVERAGE_BASE}/{andy_coverage_filename(model_id)}"
    try:
        raw = _http_get_bytes(url)
        doc = json.loads(raw)
    except Exception:
        return None
    return doc if isinstance(doc, dict) else None


def _adapt_andy_entry(code: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Transform one of Andy's per-language entries into our per-language payload.

    main.weighted_score -> coverage_score; main.tierN_count -> tier_counts;
    fertility -> our fertility shape. His script (ISO-15924), glottocode, family,
    lat/long and is_historical are carried through for a future map.
    """
    main = entry.get("main")
    if not isinstance(main, dict):
        return None
    score = main.get("weighted_score")
    total = main.get("total", 0) or 0
    payload: dict[str, Any] = {
        "language": code,
        "language_name": entry.get("name") or code,
        "script": entry.get("script"),  # ISO-15924 (e.g. "Latn", "Copt")
        "coverage_score": score,
        "tier_counts": {
            "tier_0_native": int(main.get("tier0_count", 0) or 0),
            "tier_1_embedded": int(main.get("tier1_count", 0) or 0),
            "tier_2_byte_fallback": int(main.get("tier2_count", 0) or 0),
            "tier_3_unreachable": int(main.get("tier3_count", 0) or 0),
            "total_chars": int(total),
        },
    }
    fert = entry.get("fertility")
    if isinstance(fert, dict):
        payload["fertility"] = {
            "tokens_per_char": fert.get("tokens_per_char"),
            "tokens_per_word": fert.get("tokens_per_word"),
            "sample_chars": fert.get("sample_chars"),
            "sample_tokens": fert.get("sample_tokens"),
        }
    # Geo / provenance extras carried through for a future map (not surfaced in
    # the record yet — that needs schema fields, deferred).
    for key in ("glottocode", "iso639_3", "family_name", "latitude", "longitude", "is_historical"):
        if entry.get(key) is not None:
            payload[key] = entry[key]
    return payload


def fetch_andy_coverage(
    model_id: str, language_codes: list[str]
) -> dict[str, dict[str, Any]] | None:
    """Andy's coverage for a model, filtered to exactly ``language_codes``.

    Returns {code: our-per-language-payload} for the codes he actually has, or
    None if his file is missing entirely / has none of them. Only the requested
    languages are kept — the ~5 MB source is never stored.
    """
    doc = _fetch_andy_doc(model_id)
    if doc is None:
        return None
    langs = doc.get("languages")
    if not isinstance(langs, dict):
        return None
    out: dict[str, dict[str, Any]] = {}
    for code in language_codes:
        entry = langs.get(code)
        if isinstance(entry, dict):
            adapted = _adapt_andy_entry(code, entry)
            if adapted is not None and adapted.get("coverage_score") is not None:
                out[code] = adapted
    return out or None


def ensure_coverage(
    model_id: str,
    language: LanguageSpec,
    *,
    provider: str = "",
    coverage_dir: Path | None = None,
    tokenizer: Tokenizer | None = None,
    allow_fetch: bool = True,
) -> Path | None:
    """Ensure a cached coverage entry exists for (model, language).

    Precedence (all honest, never heuristic):
      1. Andy's authoritative published file (fetched, filtered, cached), else
      2. our own tokenizer computation, else
      3. nothing written -> caller returns honest unknown.
    """
    out_dir = coverage_dir or default_coverage_dir()
    if allow_fetch and language.code:
        entries = fetch_andy_coverage(model_id, [language.code])
        if entries:
            return _upsert_coverage_entries(
                provider, model_id, entries, out_dir, provenance=ANDY_PROVENANCE
            )
    return write_coverage_record(
        model_id, language, provider=provider, coverage_dir=out_dir, tokenizer=tokenizer
    )
