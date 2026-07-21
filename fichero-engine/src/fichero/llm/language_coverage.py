"""Local model/language coverage contracts.

This module consumes derived LOOVE-style tokenizer coverage JSON when available.
It never downloads tokenizer data, calls model providers, or inspects user text.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from fichero.db.storage import settings


ScoreBand = Literal["excellent", "good", "limited", "poor", "unknown"]
FitStatus = Literal[
    "derived",
    "heuristic",
    "unsupported_language",
    "invalid_coverage_file",
]


class LanguageSpec(BaseModel):
    """Language identity used for tokenizer-coverage lookup."""

    code: str
    name: str
    script: str | None = None


class LanguageTierCounts(BaseModel):
    """LOOVE tier counts for exemplar characters."""

    tier_0_native: int = Field(
        default=0,
        description="Characters represented as native single-character tokens.",
    )
    tier_1_embedded: int = Field(
        default=0,
        description="Characters embedded inside multi-character tokens.",
    )
    tier_2_byte_fallback: int = Field(
        default=0,
        description="Characters represented through byte fallback tokens.",
    )
    tier_3_unreachable: int = Field(
        default=0,
        description="Characters not reachable by the tokenizer.",
    )
    total_chars: int = 0


class LanguageFertility(BaseModel):
    """Optional LOOVE fertility metrics from sample text."""

    tokens_per_char: float | None = None
    tokens_per_word: float | None = None
    sample_chars: int | None = None
    sample_tokens: int | None = None


class LanguageCoverageSource(BaseModel):
    """Where the score came from."""

    kind: Literal["loove_derived_json", "heuristic_fallback", "missing"] = "missing"
    model_id: str | None = None
    coverage_path: str | None = None
    generated_at: str | None = None
    notes: list[str] = Field(default_factory=list)


class LanguageCoverageRecord(BaseModel):
    """Per-model language fit result."""

    provider: str
    model: str
    normalized_model_id: str
    language: LanguageSpec
    coverage_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Weighted tokenizer coverage score, not model intelligence.",
    )
    score_band: ScoreBand = "unknown"
    tier_counts: LanguageTierCounts | None = None
    fertility: LanguageFertility | None = None
    source: LanguageCoverageSource
    status: FitStatus
    warnings: list[str] = Field(default_factory=list)


class LanguageFitModelSpec(BaseModel):
    """Provider/model query contract for language-fit recommendations."""

    provider: str
    model: str


class LanguageFitRequest(BaseModel):
    """Batch request contract for future callers."""

    language: str
    models: list[LanguageFitModelSpec] = Field(default_factory=list)


class LanguageFitResponse(BaseModel):
    """Language-fit recommendation response."""

    language: LanguageSpec
    results: list[LanguageCoverageRecord]
    privacy_note: str = (
        "Language fit is computed from local derived coverage metadata or a "
        "transparent heuristic fallback. No cloud calls are made and no user "
        "documents are tokenized."
    )
    source_note: str = (
        "LOOVE-derived data measures tokenizer/language coverage; it does not "
        "measure model intelligence or task quality directly."
    )


_COMMON_LANGUAGES: dict[str, LanguageSpec] = {
    "ar": LanguageSpec(code="ar", name="Arabic", script="Arabic"),
    "bn": LanguageSpec(code="bn", name="Bengali", script="Bengali"),
    "cs": LanguageSpec(code="cs", name="Czech", script="Latin"),
    "da": LanguageSpec(code="da", name="Danish", script="Latin"),
    "de": LanguageSpec(code="de", name="German", script="Latin"),
    "el": LanguageSpec(code="el", name="Greek", script="Greek"),
    "en": LanguageSpec(code="en", name="English", script="Latin"),
    "es": LanguageSpec(code="es", name="Spanish", script="Latin"),
    "fi": LanguageSpec(code="fi", name="Finnish", script="Latin"),
    "fr": LanguageSpec(code="fr", name="French", script="Latin"),
    "he": LanguageSpec(code="he", name="Hebrew", script="Hebrew"),
    "hi": LanguageSpec(code="hi", name="Hindi", script="Devanagari"),
    "it": LanguageSpec(code="it", name="Italian", script="Latin"),
    "ja": LanguageSpec(code="ja", name="Japanese", script="Jpan"),
    "ko": LanguageSpec(code="ko", name="Korean", script="Hangul"),
    "nl": LanguageSpec(code="nl", name="Dutch", script="Latin"),
    "no": LanguageSpec(code="no", name="Norwegian", script="Latin"),
    "pl": LanguageSpec(code="pl", name="Polish", script="Latin"),
    "pt": LanguageSpec(code="pt", name="Portuguese", script="Latin"),
    "ru": LanguageSpec(code="ru", name="Russian", script="Cyrillic"),
    "sv": LanguageSpec(code="sv", name="Swedish", script="Latin"),
    "th": LanguageSpec(code="th", name="Thai", script="Thai"),
    "tr": LanguageSpec(code="tr", name="Turkish", script="Latin"),
    "uk": LanguageSpec(code="uk", name="Ukrainian", script="Cyrillic"),
    "vi": LanguageSpec(code="vi", name="Vietnamese", script="Latin"),
    "zh": LanguageSpec(code="zh", name="Chinese", script="Han"),
}


def normalize_language_code(language: str) -> str:
    """Normalize a BCP-47-ish language code to a lookup key."""

    return (language or "").strip().replace("_", "-").split("-", maxsplit=1)[0].lower()


def language_spec(language: str) -> LanguageSpec:
    """Return a known language spec or an unsupported placeholder."""

    code = normalize_language_code(language)
    return _COMMON_LANGUAGES.get(code) or LanguageSpec(
        code=code,
        name=code or "unknown",
        script=None,
    )


def normalize_model_spec(provider: str, model: str) -> LanguageFitModelSpec:
    """Normalize provider/model identifiers without changing the API model id."""

    return LanguageFitModelSpec(provider=provider.strip().lower(), model=model.strip())


def normalized_model_id(provider: str, model: str) -> str:
    """Stable model identity key for lookup and response display."""

    spec = normalize_model_spec(provider, model)
    model_key = re.sub(r"\s+", "", spec.model).lower()
    return f"{spec.provider}/{model_key}"


def score_band(score: float | None) -> ScoreBand:
    """Classify a coverage score into a coarse recommendation band."""

    if score is None:
        return "unknown"
    if score >= 0.90:
        return "excellent"
    if score >= 0.75:
        return "good"
    if score >= 0.50:
        return "limited"
    return "poor"


def default_coverage_dir() -> Path:
    """Return the local directory for derived LOOVE-style coverage JSON."""

    override = os.environ.get("FICHERO_LANGUAGE_COVERAGE_DIR")
    if override:
        return Path(override).expanduser()
    return settings.base_path / "language_coverage" / "coverage"


def recommend_language_fit(
    language: str,
    models: list[LanguageFitModelSpec],
    *,
    coverage_dir: Path | None = None,
) -> LanguageFitResponse:
    """Score models for one language using local derived data or heuristics."""

    lang = language_spec(language)
    return LanguageFitResponse(
        language=lang,
        results=[
            evaluate_language_fit(model, lang, coverage_dir=coverage_dir)
            for model in models
        ],
    )


def evaluate_language_fit(
    model: LanguageFitModelSpec,
    language: LanguageSpec,
    *,
    coverage_dir: Path | None = None,
) -> LanguageCoverageRecord:
    """Evaluate one provider/model pair for one language."""

    spec = normalize_model_spec(model.provider, model.model)
    derived = _load_derived_record(spec, language, coverage_dir or default_coverage_dir())
    if derived is not None:
        return derived
    if not language.code or language.code not in _COMMON_LANGUAGES:
        return _unsupported_language_record(spec, language)
    return _heuristic_record(spec, language)


def _unsupported_language_record(
    spec: LanguageFitModelSpec,
    language: LanguageSpec,
) -> LanguageCoverageRecord:
    warning = (
        f"No local language metadata is available for '{language.code}'. "
        "Add a derived LOOVE coverage JSON file to score it."
    )
    return LanguageCoverageRecord(
        provider=spec.provider,
        model=spec.model,
        normalized_model_id=normalized_model_id(spec.provider, spec.model),
        language=language,
        coverage_score=None,
        score_band="unknown",
        tier_counts=None,
        fertility=None,
        source=LanguageCoverageSource(kind="missing", notes=[warning]),
        status="unsupported_language",
        warnings=[warning],
    )


def _heuristic_record(
    spec: LanguageFitModelSpec,
    language: LanguageSpec,
) -> LanguageCoverageRecord:
    score = _heuristic_score(spec, language)
    warning = (
        "No LOOVE-derived coverage file was found for this model; score is a "
        "transparent heuristic and should be replaced with derived coverage data."
    )
    return LanguageCoverageRecord(
        provider=spec.provider,
        model=spec.model,
        normalized_model_id=normalized_model_id(spec.provider, spec.model),
        language=language,
        coverage_score=score,
        score_band=score_band(score),
        tier_counts=_synthetic_tier_counts(score),
        fertility=None,
        source=LanguageCoverageSource(
            kind="heuristic_fallback",
            model_id=normalized_model_id(spec.provider, spec.model),
            notes=[warning],
        ),
        status="heuristic",
        warnings=[warning],
    )


def _heuristic_score(spec: LanguageFitModelSpec, language: LanguageSpec) -> float:
    script = language.script or ""
    model_key = normalized_model_id(spec.provider, spec.model)
    script_base = {
        "Latin": 0.86,
        "Cyrillic": 0.78,
        "Greek": 0.76,
        "Arabic": 0.68,
        "Hebrew": 0.68,
        "Devanagari": 0.64,
        "Bengali": 0.62,
        "Han": 0.66,
        "Jpan": 0.64,
        "Hangul": 0.66,
        "Thai": 0.60,
    }.get(script, 0.50)
    if any(marker in model_key for marker in ("gpt-4", "gpt-5", "claude", "gemini")):
        script_base += 0.04
    if any(marker in model_key for marker in ("qwen", "yi-", "baichuan")):
        if script in {"Han", "Jpan", "Hangul"}:
            script_base += 0.10
    if any(marker in model_key for marker in ("llama", "mistral", "mixtral")):
        script_base -= 0.03
    return round(min(max(script_base, 0.05), 0.95), 3)


def _synthetic_tier_counts(score: float) -> LanguageTierCounts:
    total = 100
    tier_0 = int(score * total * 0.72)
    tier_1 = int(score * total) - tier_0
    tier_2 = max(0, total - tier_0 - tier_1)
    return LanguageTierCounts(
        tier_0_native=tier_0,
        tier_1_embedded=tier_1,
        tier_2_byte_fallback=tier_2,
        tier_3_unreachable=0,
        total_chars=total,
    )


def _load_derived_record(
    spec: LanguageFitModelSpec,
    language: LanguageSpec,
    coverage_dir: Path,
) -> LanguageCoverageRecord | None:
    path = _coverage_file_for(spec, coverage_dir)
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warning = f"Could not read derived coverage file {path}: {exc}"
        return LanguageCoverageRecord(
            provider=spec.provider,
            model=spec.model,
            normalized_model_id=normalized_model_id(spec.provider, spec.model),
            language=language,
            coverage_score=None,
            score_band="unknown",
            tier_counts=None,
            fertility=None,
            source=LanguageCoverageSource(
                kind="loove_derived_json",
                coverage_path=str(path),
                notes=[warning],
            ),
            status="invalid_coverage_file",
            warnings=[warning],
        )

    language_payload = _find_language_payload(payload, language.code)
    if language_payload is None:
        return None
    return _record_from_payload(spec, language, language_payload, payload, path)


def _coverage_file_for(spec: LanguageFitModelSpec, coverage_dir: Path) -> Path | None:
    safe_provider = _safe_filename(spec.provider)
    safe_model = _safe_filename(spec.model)
    candidates = [
        coverage_dir / f"{safe_provider}__{safe_model}.json",
        coverage_dir / f"{safe_model}.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value.strip()).strip("._").lower()


def _find_language_payload(payload: Any, language_code: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    containers: list[Any] = [
        payload.get("coverage"),
        payload.get("languages"),
        payload.get("language_coverage"),
        payload,
    ]
    for container in containers:
        if isinstance(container, dict):
            item = container.get(language_code)
            if isinstance(item, dict):
                return item
        if isinstance(container, list):
            found = _find_language_in_list(container, language_code)
            if found is not None:
                return found
    for key in ("items", "results"):
        container = payload.get(key)
        if isinstance(container, list):
            found = _find_language_in_list(container, language_code)
            if found is not None:
                return found
    return None


def _find_language_in_list(items: list[Any], language_code: str) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        item_code = normalize_language_code(
            str(item.get("language") or item.get("code") or item.get("language_code") or "")
        )
        if item_code == language_code:
            return item
    return None


def _record_from_payload(
    spec: LanguageFitModelSpec,
    language: LanguageSpec,
    language_payload: dict[str, Any],
    root_payload: dict[str, Any],
    path: Path,
) -> LanguageCoverageRecord:
    score = _optional_float(
        language_payload.get("coverage_score"),
        language_payload.get("weighted_coverage_score"),
        language_payload.get("score"),
        language_payload.get("coverage"),
    )
    language_name = (
        language_payload.get("language_name")
        or language_payload.get("name")
        or language.name
    )
    script = language_payload.get("script") or language.script
    return LanguageCoverageRecord(
        provider=spec.provider,
        model=spec.model,
        normalized_model_id=normalized_model_id(spec.provider, spec.model),
        language=LanguageSpec(code=language.code, name=str(language_name), script=script),
        coverage_score=score,
        score_band=score_band(score),
        tier_counts=_tier_counts(language_payload),
        fertility=_fertility(language_payload),
        source=LanguageCoverageSource(
            kind="loove_derived_json",
            model_id=str(root_payload.get("model_id") or spec.model),
            coverage_path=str(path),
            generated_at=(
                str(root_payload["generated_at"])
                if root_payload.get("generated_at") is not None
                else None
            ),
            notes=[
                "Loaded from local derived LOOVE-style coverage JSON.",
                "Raw tokenizer vocabulary is not redistributed by this endpoint.",
            ],
        ),
        status="derived",
        warnings=[],
    )


def _tier_counts(payload: dict[str, Any]) -> LanguageTierCounts | None:
    raw = payload.get("tier_counts") or payload.get("tiers") or payload
    if not isinstance(raw, dict):
        return None
    tier_0 = _int_value(raw, "tier_0_native", "tier0", "tier_0", "0", 0)
    tier_1 = _int_value(raw, "tier_1_embedded", "tier1", "tier_1", "1", 0)
    tier_2 = _int_value(raw, "tier_2_byte_fallback", "tier2", "tier_2", "2", 0)
    tier_3 = _int_value(raw, "tier_3_unreachable", "tier3", "tier_3", "3", 0)
    total = _int_value(raw, "total_chars", "sample_chars", "total", default=0)
    if total <= 0:
        total = tier_0 + tier_1 + tier_2 + tier_3
    if total <= 0 and not any((tier_0, tier_1, tier_2, tier_3)):
        return None
    return LanguageTierCounts(
        tier_0_native=tier_0,
        tier_1_embedded=tier_1,
        tier_2_byte_fallback=tier_2,
        tier_3_unreachable=tier_3,
        total_chars=total,
    )


def _fertility(payload: dict[str, Any]) -> LanguageFertility | None:
    raw = payload.get("fertility")
    if not isinstance(raw, dict):
        raw = payload
    fertility = LanguageFertility(
        tokens_per_char=_optional_float(raw.get("tokens_per_char")),
        tokens_per_word=_optional_float(raw.get("tokens_per_word")),
        sample_chars=_optional_int(raw.get("sample_chars")),
        sample_tokens=_optional_int(raw.get("sample_tokens")),
    )
    if not any(value is not None for value in fertility.model_dump().values()):
        return None
    return fertility


def _optional_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_value(raw: dict[str, Any], *keys: str, default: int = 0) -> int:
    for key in keys:
        if key not in raw:
            continue
        parsed = _optional_int(raw[key])
        if parsed is not None:
            return parsed
    return default
