"""Deterministic model recommendation contracts and scoring.

The recommender composes local metadata only: Settings rows, provider catalog
privacy posture, and language-coverage metadata. It never calls model
providers, tokenizes documents, downloads model data, or estimates from user
content.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from fichero.llm.language_coverage import (
    LanguageCoverageRecord,
    LanguageFitModelSpec,
    LanguageSpec,
    language_spec,
    recommend_language_fit,
)
from fichero.llm.model_profiles import provider_is_local_or_builtin
from fichero.llm.providers import get_provider_info


RecommendationSource = Literal["explicit", "settings"]
CostStatus = Literal["free", "known", "unknown"]
PrivacyPosture = Literal["builtin_local", "local", "cloud", "unknown"]
AvailabilityStatus = Literal["enabled", "disabled", "refused"]


class ModelRecommendationCandidate(BaseModel):
    """Model metadata available to the local recommender."""

    provider: str
    model: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    input_price_per_million: float | None = Field(
        default=None,
        ge=0.0,
        description="Input token price per million tokens, when known.",
    )
    output_price_per_million: float | None = Field(
        default=None,
        ge=0.0,
        description="Output token price per million tokens, when known.",
    )
    source: RecommendationSource = "explicit"
    notes: list[str] = Field(default_factory=list)

    @field_validator("provider", mode="before")
    @classmethod
    def _normalize_provider(cls, value: object) -> str:
        return str(value or "").strip().lower()

    @field_validator("model", mode="before")
    @classmethod
    def _strip_model(cls, value: object) -> str:
        return str(value or "").strip()


class ModelRecommendationRequest(BaseModel):
    """Request contract for no-network model recommendations."""

    language: str = Field(..., description="BCP-47-ish language code to score.")
    task: str | None = Field(
        default=None,
        description="Human-readable task label for recommendation reasons.",
    )
    capability: str | None = Field(
        default="text",
        description="Capability required by the caller, such as text or vision.",
    )
    candidates: list[ModelRecommendationCandidate] = Field(
        default_factory=list,
        description="Optional explicit candidates; Settings models are used when omitted.",
    )
    local_only: bool = Field(
        default=False,
        description="Refuse cloud providers when the caller requires local execution.",
    )
    private: bool = Field(
        default=False,
        description="Refuse cloud providers when the task is private.",
    )

    @field_validator("language", mode="before")
    @classmethod
    def _strip_language(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("capability", mode="before")
    @classmethod
    def _normalize_capability(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        return normalized or None


class ModelRecommendationCost(BaseModel):
    """Typed cost metadata for one candidate."""

    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    status: CostStatus
    note: str


class ModelRecommendationScores(BaseModel):
    """Score components normalized to 0..1."""

    language_fit: float | None
    cost: float
    privacy: float
    availability: float
    capability: float


class ModelRecommendationItem(BaseModel):
    """Ranked model recommendation item."""

    provider: str
    model: str
    rank: int
    total_score: float
    component_scores: ModelRecommendationScores
    language_fit: LanguageCoverageRecord
    privacy_posture: PrivacyPosture
    cost: ModelRecommendationCost
    availability_status: AvailabilityStatus
    enabled: bool
    available: bool
    source: RecommendationSource
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ModelRecommendationResponse(BaseModel):
    """Response contract for ranked no-network model recommendations."""

    language: LanguageSpec
    task: str | None = None
    capability: str | None = None
    local_only: bool = False
    private: bool = False
    items: list[ModelRecommendationItem]
    privacy_note: str = (
        "Recommendations are computed from local Settings, provider metadata, "
        "and local derived language-coverage data or heuristics. No cloud calls "
        "are made, no model invocation occurs, and no user documents are tokenized."
    )
    source_note: str = (
        "Language fit uses #1820 LOOVE-derived tokenizer/language coverage when "
        "available; it is one component of the #2204/#2116 model-picker metadata."
    )


def build_model_recommendations(
    request: ModelRecommendationRequest,
    *,
    settings_candidates: list[ModelRecommendationCandidate] | None = None,
) -> ModelRecommendationResponse:
    """Rank explicit or Settings-backed candidates without network access."""

    candidates = request.candidates or settings_candidates or []
    language = language_spec(request.language)
    fit_by_key = _language_fit_by_key(request.language, candidates)
    items = [
        _score_candidate(request, candidate, fit_by_key[_candidate_key(candidate)])
        for candidate in candidates
        if candidate.provider and candidate.model
    ]
    items.sort(
        key=lambda item: (
            item.available,
            item.total_score,
            item.component_scores.language_fit or -1.0,
            item.component_scores.cost,
            item.provider,
            item.model,
        ),
        reverse=True,
    )
    ranked = [
        item.model_copy(update={"rank": index})
        for index, item in enumerate(items, start=1)
    ]
    return ModelRecommendationResponse(
        language=language,
        task=request.task,
        capability=request.capability,
        local_only=request.local_only,
        private=request.private,
        items=ranked,
    )


def _language_fit_by_key(
    language: str,
    candidates: list[ModelRecommendationCandidate],
) -> dict[tuple[str, str], LanguageCoverageRecord]:
    response = recommend_language_fit(
        language,
        [
            LanguageFitModelSpec(provider=candidate.provider, model=candidate.model)
            for candidate in candidates
            if candidate.provider and candidate.model
        ],
    )
    return {
        (record.provider, record.model): record
        for record in response.results
    }


def _score_candidate(
    request: ModelRecommendationRequest,
    candidate: ModelRecommendationCandidate,
    language_fit: LanguageCoverageRecord,
) -> ModelRecommendationItem:
    privacy_posture = _privacy_posture(candidate.provider)
    capability_score, capability_warning = _capability_score(
        request.capability,
        candidate.capabilities,
    )
    cost = _cost_metadata(candidate, privacy_posture)
    cost_score = _cost_score(cost)
    privacy_score = _privacy_score(privacy_posture, request)
    availability_status, availability_reason = _availability_status(
        candidate,
        privacy_posture,
        request,
    )
    availability_score = 1.0 if availability_status == "enabled" else 0.0
    language_score = language_fit.coverage_score
    total_score = _total_score(
        language_score=language_score,
        cost_score=cost_score,
        privacy_score=privacy_score,
        availability_score=availability_score,
        capability_score=capability_score,
    )
    if availability_status != "enabled":
        total_score = 0.0

    warnings = [*language_fit.warnings]
    if capability_warning:
        warnings.append(capability_warning)
    if cost.status == "unknown":
        warnings.append("Cost metadata is unknown; it was not treated as free.")
    if availability_status == "refused":
        warnings.append(availability_reason)

    reasons = _reason_strings(
        request=request,
        candidate=candidate,
        language_fit=language_fit,
        privacy_posture=privacy_posture,
        cost=cost,
        availability_reason=availability_reason,
        capability_score=capability_score,
    )
    return ModelRecommendationItem(
        provider=candidate.provider,
        model=candidate.model,
        rank=0,
        total_score=total_score,
        component_scores=ModelRecommendationScores(
            language_fit=language_score,
            cost=cost_score,
            privacy=privacy_score,
            availability=availability_score,
            capability=capability_score,
        ),
        language_fit=language_fit,
        privacy_posture=privacy_posture,
        cost=cost,
        availability_status=availability_status,
        enabled=candidate.enabled,
        available=availability_status == "enabled",
        source=candidate.source,
        reasons=reasons,
        warnings=warnings,
    )


def _candidate_key(candidate: ModelRecommendationCandidate) -> tuple[str, str]:
    return (candidate.provider, candidate.model)


def _privacy_posture(provider: str) -> PrivacyPosture:
    info = get_provider_info(provider)
    if info is None:
        return "unknown"
    if info.is_builtin:
        return "builtin_local"
    if info.is_local:
        return "local"
    return "cloud"


def _capability_score(
    required_capability: str | None,
    capabilities: list[str],
) -> tuple[float, str | None]:
    if not required_capability:
        return 1.0, None
    normalized = {capability.strip().lower() for capability in capabilities}
    if not normalized:
        return 0.8, (
            f"Capability metadata is unknown; assuming '{required_capability}' "
            "may be supported."
        )
    if required_capability in normalized:
        return 1.0, None
    return 0.0, f"Candidate does not advertise required capability '{required_capability}'."


def _cost_metadata(
    candidate: ModelRecommendationCandidate,
    privacy_posture: PrivacyPosture,
) -> ModelRecommendationCost:
    input_price = candidate.input_price_per_million
    output_price = candidate.output_price_per_million
    if input_price is None or output_price is None:
        if provider_is_local_or_builtin(candidate.provider):
            return ModelRecommendationCost(
                input_price_per_million=input_price,
                output_price_per_million=output_price,
                status="free",
                note="Local/builtin provider; no cloud token cost is expected.",
            )
        return ModelRecommendationCost(
            input_price_per_million=input_price,
            output_price_per_million=output_price,
            status="unknown",
            note="Settings did not include complete pricing metadata.",
        )
    total = input_price + output_price
    if total == 0 and privacy_posture in {"builtin_local", "local"}:
        return ModelRecommendationCost(
            input_price_per_million=input_price,
            output_price_per_million=output_price,
            status="free",
            note="Configured as zero-cost local/builtin inference.",
        )
    return ModelRecommendationCost(
        input_price_per_million=input_price,
        output_price_per_million=output_price,
        status="known",
        note=(
            f"Configured cost is ${input_price:g} input + ${output_price:g} "
            "output per million tokens."
        ),
    )


def _cost_score(cost: ModelRecommendationCost) -> float:
    if cost.status == "free":
        return 1.0
    if cost.status == "unknown":
        return 0.35
    total = (cost.input_price_per_million or 0.0) + (
        cost.output_price_per_million or 0.0
    )
    if total <= 0:
        return 0.9
    return round(max(0.05, 1.0 - min(total / 50.0, 0.95)), 3)


def _privacy_score(
    posture: PrivacyPosture,
    request: ModelRecommendationRequest,
) -> float:
    if posture == "builtin_local":
        return 1.0
    if posture == "local":
        return 0.95
    if posture == "unknown":
        return 0.4 if (request.local_only or request.private) else 0.65
    if request.local_only or request.private:
        return 0.0
    return 0.55


def _availability_status(
    candidate: ModelRecommendationCandidate,
    posture: PrivacyPosture,
    request: ModelRecommendationRequest,
) -> tuple[AvailabilityStatus, str]:
    if not candidate.enabled:
        return "disabled", "Candidate is disabled in Settings or request metadata."
    if (request.local_only or request.private) and posture == "cloud":
        return (
            "refused",
            "Cloud provider refused because local_only/private mode requires "
            "local or builtin inference.",
        )
    return "enabled", "Candidate is enabled and passes local privacy constraints."


def _total_score(
    *,
    language_score: float | None,
    cost_score: float,
    privacy_score: float,
    availability_score: float,
    capability_score: float,
) -> float:
    normalized_language = language_score if language_score is not None else 0.3
    total = (
        normalized_language * 0.45
        + cost_score * 0.20
        + privacy_score * 0.20
        + availability_score * 0.10
        + capability_score * 0.05
    )
    return round(max(0.0, min(total, 1.0)), 3)


def _reason_strings(
    *,
    request: ModelRecommendationRequest,
    candidate: ModelRecommendationCandidate,
    language_fit: LanguageCoverageRecord,
    privacy_posture: PrivacyPosture,
    cost: ModelRecommendationCost,
    availability_reason: str,
    capability_score: float,
) -> list[str]:
    reasons = [
        (
            f"{language_fit.score_band} language fit for "
            f"{language_fit.language.name} via {language_fit.source.kind}."
        ),
        cost.note,
        f"Privacy posture is {privacy_posture.replace('_', ' ')}.",
        availability_reason,
        f"Candidate came from {candidate.source} metadata.",
    ]
    if request.task:
        reasons.append(f"Ranked for task: {request.task}.")
    if request.capability:
        if capability_score == 1.0:
            reasons.append(f"Advertises required capability '{request.capability}'.")
        elif capability_score > 0.0:
            reasons.append(
                f"Capability '{request.capability}' is not declared but metadata is sparse."
            )
    if candidate.notes:
        reasons.extend(candidate.notes)
    return reasons
