"""
Model Comparison Engine

Runs the same prompt against multiple LLM models in parallel,
tracking cost, latency, and response quality for comparison.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

from pydantic import BaseModel, Field

from fichero.llm import get_langchain_model, LLMConfig, get_model_info

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ModelResult:
    """Result from a single model execution."""
    provider: str
    model: str
    response: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "response": self.response,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class ComparisonResult:
    """Result of comparing multiple models."""
    prompt: str
    models_compared: list[str]
    results: list[ModelResult]
    fastest_model: str | None = None
    cheapest_model: str | None = None
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    comparison_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "models_compared": self.models_compared,
            "results": [r.to_dict() for r in self.results],
            "fastest_model": self.fastest_model,
            "cheapest_model": self.cheapest_model,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_ms": self.total_latency_ms,
            "comparison_id": self.comparison_id,
            "timestamp": self.timestamp,
        }


class ModelSpec(BaseModel):
    """Specification for a model to compare."""
    provider: str = Field(..., description="LLM provider (openai, anthropic, etc)")
    model: str = Field(..., description="Model name")
    temperature: float = Field(default=0.7, description="Temperature setting")
    max_tokens: int | None = Field(default=None, description="Max output tokens")


class ComparisonRequest(BaseModel):
    """Request to compare multiple models."""
    prompt: str = Field(..., description="Prompt to send to all models")
    models: list[ModelSpec] = Field(..., description="Models to compare")
    system_prompt: str | None = Field(default=None, description="Optional system prompt")
    timeout_seconds: int = Field(default=120, description="Timeout per model")
    include_cost_tracking: bool = Field(default=True, description="Track costs")


# =============================================================================
# Cost Estimation
# =============================================================================

# Pricing per 1M tokens (input/output) - approximate as of 2024
MODEL_PRICING = {
    # OpenAI
    "gpt-4o": (5.0, 15.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "gpt-4": (30.0, 60.0),
    "gpt-3.5-turbo": (0.50, 1.50),
    # Anthropic
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-5-haiku-20241022": (1.0, 5.0),
    "claude-3-opus-20240229": (15.0, 75.0),
    "claude-3-sonnet-20240229": (3.0, 15.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
    # Google
    "gemini-1.5-pro": (3.50, 10.50),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-pro": (0.50, 1.50),
    # Mistral
    "mistral-large-latest": (3.0, 9.0),
    "mistral-medium-latest": (2.7, 8.1),
    "mistral-small-latest": (1.0, 3.0),
    # Local (free)
    "llama3.2": (0.0, 0.0),
    "llama3.1": (0.0, 0.0),
    "mistral": (0.0, 0.0),
    "codellama": (0.0, 0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost for a model run."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Check for partial matches
        for model_name, prices in MODEL_PRICING.items():
            if model_name in model.lower() or model.lower() in model_name:
                pricing = prices
                break

    if not pricing:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * pricing[0]
    output_cost = (output_tokens / 1_000_000) * pricing[1]
    return input_cost + output_cost


# =============================================================================
# Model Comparison Engine
# =============================================================================

class ModelComparisonEngine:
    """Engine for running comparisons across multiple models."""

    def __init__(self):
        self.comparison_history: list[ComparisonResult] = []

    async def compare(self, request: ComparisonRequest) -> ComparisonResult:
        """Run comparison across all specified models.

        Args:
            request: Comparison request with prompt and model specs

        Returns:
            ComparisonResult with all model responses and metrics
        """
        import uuid
        comparison_id = str(uuid.uuid4())[:8]

        logger.info(f"Starting comparison {comparison_id} with {len(request.models)} models")

        # Run all models in parallel
        tasks = [
            self._run_model(spec, request.prompt, request.system_prompt, request.timeout_seconds)
            for spec in request.models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        model_results: list[ModelResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                spec = request.models[i]
                model_results.append(ModelResult(
                    provider=spec.provider,
                    model=spec.model,
                    response="",
                    latency_ms=0,
                    error=str(result),
                ))
            else:
                model_results.append(result)

        # Calculate aggregate stats
        successful_results = [r for r in model_results if not r.error]

        fastest_model = None
        cheapest_model = None
        if successful_results:
            fastest = min(successful_results, key=lambda r: r.latency_ms)
            fastest_model = f"{fastest.provider}/{fastest.model}"

            if request.include_cost_tracking:
                cheapest = min(successful_results, key=lambda r: r.cost_usd)
                cheapest_model = f"{cheapest.provider}/{cheapest.model}"

        total_cost = sum(r.cost_usd for r in model_results)
        total_latency = sum(r.latency_ms for r in model_results)

        comparison = ComparisonResult(
            prompt=request.prompt,
            models_compared=[f"{s.provider}/{s.model}" for s in request.models],
            results=model_results,
            fastest_model=fastest_model,
            cheapest_model=cheapest_model,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency,
            comparison_id=comparison_id,
        )

        self.comparison_history.append(comparison)

        logger.info(
            f"Comparison {comparison_id} complete: "
            f"{len(successful_results)}/{len(model_results)} successful, "
            f"fastest={fastest_model}, cheapest={cheapest_model}"
        )

        return comparison

    async def _run_model(
        self,
        spec: ModelSpec,
        prompt: str,
        system_prompt: str | None,
        timeout_seconds: int,
    ) -> ModelResult:
        """Run a single model and collect metrics."""
        start_time = time.time()

        try:
            config = LLMConfig(
                provider=spec.provider,
                model=spec.model,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
            )

            model = get_langchain_model(config)

            # Build messages
            from langchain_core.messages import HumanMessage, SystemMessage
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))

            # Run with timeout
            response = await asyncio.wait_for(
                model.ainvoke(messages),
                timeout=timeout_seconds,
            )

            latency_ms = (time.time() - start_time) * 1000

            # Extract token counts if available
            input_tokens = 0
            output_tokens = 0

            if hasattr(response, "response_metadata"):
                metadata = response.response_metadata
                if "usage" in metadata:
                    usage = metadata["usage"]
                    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
                elif "token_usage" in metadata:
                    usage = metadata["token_usage"]
                    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))

            # Estimate tokens if not available
            if input_tokens == 0:
                # Rough estimate: ~4 chars per token
                input_tokens = len(prompt) // 4
            if output_tokens == 0:
                output_tokens = len(response.content) // 4

            cost = estimate_cost(spec.model, input_tokens, output_tokens)

            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response=response.content,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )

        except asyncio.TimeoutError:
            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=f"Timeout after {timeout_seconds}s",
            )
        except Exception as e:
            logger.exception(f"Model {spec.provider}/{spec.model} failed: {e}")
            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
            )

    def get_history(self, limit: int = 10) -> list[dict]:
        """Get recent comparison history."""
        return [c.to_dict() for c in self.comparison_history[-limit:]]

    def get_comparison(self, comparison_id: str) -> ComparisonResult | None:
        """Get a specific comparison by ID."""
        for c in self.comparison_history:
            if c.comparison_id == comparison_id:
                return c
        return None


# Global engine instance
_engine: ModelComparisonEngine | None = None


def get_comparison_engine() -> ModelComparisonEngine:
    """Get or create the global comparison engine."""
    global _engine
    if _engine is None:
        _engine = ModelComparisonEngine()
    return _engine


# =============================================================================
# Workflow Tool Registration
# =============================================================================

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool


@register_tool(
    name="model_comparison",
    display_name="Model Comparison",
    description="Compare responses from multiple LLM models",
    category="llm",
    icon="square.split.2x2",
    color="teal",
    uses_llm=True,
    supports_streaming=False,
    input_ports=[
        PortDef(
            id="prompt",
            name="Prompt",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Prompt to send to all models"
        ),
        PortDef(
            id="system_prompt",
            name="System Prompt",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Optional system prompt"
        ),
    ],
    output_ports=[
        PortDef(
            id="results",
            name="Results",
            port_type="output",
            data_type=DataType.JSON,
            description="Comparison results from all models"
        ),
        PortDef(
            id="fastest",
            name="Fastest Response",
            port_type="output",
            data_type=DataType.TEXT,
            description="Response from fastest model"
        ),
        PortDef(
            id="cheapest",
            name="Cheapest Response",
            port_type="output",
            data_type=DataType.TEXT,
            description="Response from cheapest model"
        ),
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Summary statistics"
        ),
    ],
    config_schema={
        "models": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "temperature": {"type": "number"},
                },
                "required": ["provider", "model"],
            },
            "default": [
                {"provider": "openai", "model": "gpt-4o"},
                {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
            ],
            "description": "Models to compare"
        },
        "timeout_seconds": {
            "type": "integer",
            "default": 60,
            "description": "Timeout per model in seconds"
        },
    },
)
async def model_comparison(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Execute model comparison across multiple LLMs.

    Args:
        inputs: Includes prompt, system_prompt, models config
        state: Current workflow state
        llm_config: Default LLM config (used if no models specified)

    Returns:
        Comparison results with all model responses and metrics
    """
    prompt = inputs.get("prompt", "")
    system_prompt = inputs.get("system_prompt")
    models_config = inputs.get("models", [])
    timeout = inputs.get("timeout_seconds", 60)

    if not prompt:
        return {
            "results": [],
            "fastest": "",
            "cheapest": "",
            "summary": {},
            "error": "No prompt provided"
        }

    # Build model specs
    model_specs = []
    for m in models_config:
        model_specs.append(ModelSpec(
            provider=m.get("provider", "openai"),
            model=m.get("model", "gpt-4o"),
            temperature=m.get("temperature", 0.7),
        ))

    # If no models specified, use default config
    if not model_specs:
        model_specs = [
            ModelSpec(provider=llm_config.provider, model=llm_config.model),
        ]

    request = ComparisonRequest(
        prompt=prompt,
        models=model_specs,
        system_prompt=system_prompt,
        timeout_seconds=timeout,
    )

    engine = get_comparison_engine()
    result = await engine.compare(request)

    # Extract fastest and cheapest responses
    fastest_response = ""
    cheapest_response = ""
    for r in result.results:
        model_name = f"{r.provider}/{r.model}"
        if model_name == result.fastest_model:
            fastest_response = r.response
        if model_name == result.cheapest_model:
            cheapest_response = r.response

    summary = {
        "models_compared": len(result.models_compared),
        "successful": len([r for r in result.results if not r.error]),
        "fastest_model": result.fastest_model,
        "cheapest_model": result.cheapest_model,
        "total_cost_usd": result.total_cost_usd,
        "avg_latency_ms": result.total_latency_ms / len(result.results) if result.results else 0,
    }

    return {
        "results": result.to_dict(),
        "fastest": fastest_response,
        "cheapest": cheapest_response,
        "summary": summary,
    }
