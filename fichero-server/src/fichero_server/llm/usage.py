"""What a run actually spent — typed, priced, and honest about what it cannot price.

Daniel, 2026-09-03: "are we properly logging and showing in activity the cost
of each run, and does our estimate of cost reflect reality?" The answer was no
twice over. Ordinary workflow runs recorded no tokens and no cost at all, and
the one cost path that existed (`model_comparison`) turned "I have no price for
this model" into ``0.0`` — a free run, stated as fact, for a call that billed.

This module is the single place that turns raw model-call records into money:

* :class:`ModelCallUsage` — one provider call, with REAL provider-reported
  tokens where langchain surfaced them (``AIMessage.usage_metadata``, the
  langchain-core ≥1.x standard shape) and an explicitly flagged estimate when
  it did not.
* :class:`UsageTotals` — the per-node / per-run aggregate the Activity record
  carries.

Three states, never collapsed into each other:

  priced        the registry knew this model — ``cost_usd`` is a number.
  free          the provider runs on-device or in-process (Apple, MLX, mock);
                ``cost_usd`` is ``0.0`` and that zero is a CLAIM we can defend.
  unpriced      nobody could price it — ``cost_usd`` is ``None`` and the model
                id lands in ``unpriced_models`` so the client can say so.

A zero that means "free" and a zero that means "we don't know" look identical
on screen, which is exactly how a cost display becomes a lie. Hence ``None``.
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field

__all__ = [
    "ModelCallUsage",
    "UsageTotals",
    "price_call",
    "aggregate_usage",
    "provider_is_free",
    "usage_from_message",
]


def provider_is_free(provider: str | None) -> bool:
    """True when calling this provider spends nothing — on-device or built-in.

    Delegates to the provider registry (`is_local` / `is_builtin`), the same
    source `provider_preview._provider_is_billable` uses. A second hand-kept
    list of "free" provider names here would be the first one to go stale.

    An unknown provider is NOT free: if we cannot establish that something runs
    on this machine, "free" is the expensive guess.
    """
    if not provider:
        return False
    from fichero_server.llm.providers import get_provider_info

    info = get_provider_info(provider.strip().lower())
    if info is None:
        return False
    return bool(info.is_local or info.is_builtin)


class ModelCallUsage(BaseModel):
    """One model call: who was called, what it consumed, what it cost."""

    provider: str = ""
    model: str = ""
    kind: str = "chat"
    """chat | structured | vision | transcription — the call shape."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    """Input tokens served from the provider's prompt cache, billed cheaper.

    From ``usage_metadata["input_token_details"]["cache_read"]``. Included in
    ``input_tokens`` by the langchain contract, so pricing subtracts it out
    rather than adding it on.
    """

    estimated: bool = False
    """True when the provider returned NO usage and the tokens are a
    character-count guess. Never inferred — set by the recording site."""

    method: str | None = None

    cost_usd: float | None = None
    """None means unpriced. It never means free — see :attr:`free`."""

    priced: bool = False
    """True when ``cost_usd`` is a defensible number (including a free 0.0)."""

    free: bool = False
    """True when the call genuinely cost nothing (on-device / built-in)."""

    @property
    def unpriced(self) -> bool:
        return not self.priced


class UsageTotals(BaseModel):
    """Tokens and money for a set of calls — one node, or a whole run."""

    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0

    cost_usd: float | None = None
    """Sum of the priced calls, or None when NOTHING could be priced."""

    priced: bool = False
    """True when every call in the set could be priced."""

    partially_priced: bool = False
    """True when some calls priced and some did not — the total is a FLOOR,
    not the cost. A partial total presented as the cost is the same lie in a
    smaller font."""

    estimated_tokens: bool = False
    """True when at least one call's tokens are a guess rather than the
    provider's own count."""

    unpriced_models: list[str] = Field(default_factory=list)
    """Distinct model ids nobody could price, so the client can name them."""

    calls: list[ModelCallUsage] = Field(default_factory=list)

    def to_activity_metadata(self) -> dict[str, Any]:
        """The flat shape the Activity record carries.

        Activity metadata is stringified for the client, so this stays scalar.
        `cost_usd` is ABSENT when unpriced — a missing key reads as unknown,
        while `0.0` reads as free.
        """
        if not self.model_calls:
            return {}
        data: dict[str, Any] = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model_calls": self.model_calls,
            "cost_priced": self.priced,
        }
        if self.cost_usd is not None:
            data["cost_usd"] = round(self.cost_usd, 6)
        if self.cache_read_tokens:
            data["cache_read_tokens"] = self.cache_read_tokens
        if self.estimated_tokens:
            data["tokens_estimated"] = True
        if self.partially_priced:
            data["cost_partial"] = True
        if self.unpriced_models:
            data["unpriced_models"] = ",".join(self.unpriced_models)
        return data


def usage_from_message(message: Any) -> dict[str, int] | None:
    """Provider-reported token usage from a langchain ``AIMessage``.

    ``usage_metadata`` is the langchain-core ≥1.x standard shape:
    ``input_tokens`` / ``output_tokens`` / ``total_tokens`` plus optional
    ``input_token_details`` (``cache_read``, ``cache_creation``) and
    ``output_token_details`` (``reasoning``). Reasoning tokens are already
    inside ``output_tokens``, so they are not added again here.

    Returns None when the provider reported nothing — the caller must then
    flag whatever it substitutes as an estimate.
    """
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict) or not usage:
        return None
    details = usage.get("input_token_details")
    cache_read = 0
    if isinstance(details, dict):
        try:
            cache_read = int(details.get("cache_read") or 0)
        except (TypeError, ValueError):
            cache_read = 0
    return {
        "input_tokens": int(usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "cache_read_tokens": cache_read,
    }


def _registry_entry(model: str, provider: str = "") -> dict[str, Any] | None:
    """Look the model up in the price registry, provider included.

    The registry keys gateway models by the GATEWAY: OpenRouter's Qwen row is
    ``openrouter/qwen/qwen3.6-plus``, while the engine records the model as
    ``qwen/qwen3.6-plus`` with provider ``openrouter``. Looking up the model
    alone missed every such row: replayed against the engine log on
    2026-09-03, 417 of 659 real calls came back unpriced, and adding the
    provider prefix priced all 659 ($0.50 → $5.72 for the same traffic). An
    unfound row is an unpriced call, and the provider is right there.

    Guessing is still refused: no dot-for-dash rewriting, no nearest-name
    match. An unfound model stays unpriced rather than borrowing a price from
    a model that merely looks similar.
    """
    from fichero_server.llm.model_types import _resolve_entry

    name = (model or "").strip()
    if not name:
        return None
    candidates = [name]
    prefix = (provider or "").strip().lower()
    if prefix and not name.lower().startswith(f"{prefix}/"):
        candidates.append(f"{prefix}/{name}")
    for candidate in candidates:
        try:
            entry = _resolve_entry(candidate)
        except Exception:  # pragma: no cover - registry read is defensive
            return None
        if entry:
            return entry
    return None


def price_call(entry: dict[str, Any] | ModelCallUsage) -> ModelCallUsage:
    """Price one recorded model call.

    Accepts the raw dict the `_record_usage` collector appends, or an already
    built :class:`ModelCallUsage`. Pricing rules, in order:

    1. On-device / built-in provider → ``0.0``, priced, free.
    2. Registry entry with input AND output per-token costs → the arithmetic,
       with cache-read input billed at the cheaper cache rate when the
       registry names one.
    3. Anything else → ``cost_usd is None``, ``priced is False``. Never 0.0.
    """
    call = entry if isinstance(entry, ModelCallUsage) else ModelCallUsage(
        provider=str(entry.get("provider") or ""),
        model=str(entry.get("model") or ""),
        kind=str(entry.get("kind") or "chat"),
        input_tokens=int(entry.get("input_tokens") or 0),
        output_tokens=int(entry.get("output_tokens") or 0),
        total_tokens=int(
            entry.get("total_tokens")
            or (int(entry.get("input_tokens") or 0) + int(entry.get("output_tokens") or 0))
        ),
        cache_read_tokens=int(entry.get("cache_read_tokens") or 0),
        estimated=bool(entry.get("estimated")),
        method=entry.get("method"),
    )

    if provider_is_free(call.provider):
        # A defensible zero: Apple Intelligence / MLX / mock ran on this
        # machine. "$0.00" here is a claim, not a placeholder.
        return call.model_copy(update={"cost_usd": 0.0, "priced": True, "free": True})

    registry = _registry_entry(call.model, call.provider)
    if not registry:
        return call
    input_cost = registry.get("input_cost_per_token")
    output_cost = registry.get("output_cost_per_token")
    if input_cost is None or output_cost is None:
        return call

    cached = min(max(call.cache_read_tokens, 0), max(call.input_tokens, 0))
    fresh_input = max(call.input_tokens, 0) - cached
    cache_cost = registry.get("cache_read_input_token_cost")
    cost = fresh_input * input_cost + max(call.output_tokens, 0) * output_cost
    cost += cached * (cache_cost if cache_cost is not None else input_cost)
    return call.model_copy(update={"cost_usd": cost, "priced": True, "free": False})


def aggregate_usage(entries: Iterable[dict[str, Any] | ModelCallUsage]) -> UsageTotals:
    """Sum a set of model calls into one honest total.

    The aggregate is priced only when EVERY call priced. One unpriceable call
    makes the sum a floor (``partially_priced``), and no priceable call at all
    leaves ``cost_usd`` as None.
    """
    calls = [price_call(e) for e in entries]
    if not calls:
        return UsageTotals()

    priced_calls = [c for c in calls if c.priced]
    unpriced_models: list[str] = []
    for call in calls:
        if not call.priced and call.model and call.model not in unpriced_models:
            unpriced_models.append(call.model)

    cost = sum(c.cost_usd or 0.0 for c in priced_calls) if priced_calls else None
    return UsageTotals(
        model_calls=len(calls),
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        total_tokens=sum(c.total_tokens for c in calls),
        cache_read_tokens=sum(c.cache_read_tokens for c in calls),
        cost_usd=cost,
        priced=bool(priced_calls) and not unpriced_models,
        partially_priced=bool(priced_calls) and bool(unpriced_models),
        estimated_tokens=any(c.estimated for c in calls),
        unpriced_models=unpriced_models,
        calls=calls,
    )
