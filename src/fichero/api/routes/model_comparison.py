"""
Model Comparison API Routes

Endpoints for comparing responses across multiple LLM models.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fichero.workflows.model_comparison import (
    ModelComparisonEngine,
    ComparisonRequest,
    ModelSpec,
    get_comparison_engine,
    MODEL_PRICING,
)

router = APIRouter(prefix="/model-comparison", tags=["model-comparison"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CompareRequest(BaseModel):
    """Request to compare models."""
    prompt: str = Field(..., description="Prompt to send to all models")
    models: list[dict] = Field(
        default=[
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
        ],
        description="Models to compare"
    )
    system_prompt: str | None = Field(default=None, description="Optional system prompt")
    timeout_seconds: int = Field(default=60, description="Timeout per model")


class ModelInfo(BaseModel):
    """Information about a model."""
    provider: str
    model: str
    input_price_per_million: float
    output_price_per_million: float


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/compare")
async def compare_models(request: CompareRequest):
    """Compare responses from multiple models.

    Runs the same prompt against all specified models in parallel
    and returns comparison results with timing and cost metrics.
    """
    model_specs = [
        ModelSpec(
            provider=m.get("provider", "openai"),
            model=m.get("model", "gpt-4o"),
            temperature=m.get("temperature", 0.7),
        )
        for m in request.models
    ]

    comparison_request = ComparisonRequest(
        prompt=request.prompt,
        models=model_specs,
        system_prompt=request.system_prompt,
        timeout_seconds=request.timeout_seconds,
    )

    engine = get_comparison_engine()
    result = await engine.compare(comparison_request)

    return result.to_dict()


@router.get("/history")
async def get_comparison_history(limit: int = 10):
    """Get recent comparison history."""
    engine = get_comparison_engine()
    return {"history": engine.get_history(limit)}


@router.get("/comparison/{comparison_id}")
async def get_comparison(comparison_id: str):
    """Get a specific comparison by ID."""
    engine = get_comparison_engine()
    result = engine.get_comparison(comparison_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return result.to_dict()


@router.get("/models")
async def list_available_models():
    """List available models with pricing information."""
    models = []
    for model_name, (input_price, output_price) in MODEL_PRICING.items():
        # Infer provider from model name
        if model_name.startswith("gpt"):
            provider = "openai"
        elif model_name.startswith("claude"):
            provider = "anthropic"
        elif model_name.startswith("gemini"):
            provider = "google"
        elif model_name.startswith("mistral"):
            provider = "mistral"
        else:
            provider = "local"

        models.append({
            "provider": provider,
            "model": model_name,
            "input_price_per_million": input_price,
            "output_price_per_million": output_price,
        })

    return {"models": models}


@router.post("/estimate-cost")
async def estimate_comparison_cost(request: CompareRequest):
    """Estimate the cost of running a comparison.

    Uses approximate token counts to estimate costs before running.
    """
    from fichero.workflows.model_comparison import estimate_cost

    # Estimate input tokens (rough: ~4 chars per token)
    estimated_input_tokens = len(request.prompt) // 4
    if request.system_prompt:
        estimated_input_tokens += len(request.system_prompt) // 4

    # Estimate output tokens (assume ~500 tokens average response)
    estimated_output_tokens = 500

    estimates = []
    total_estimated_cost = 0.0

    for m in request.models:
        model_name = m.get("model", "gpt-4o")
        cost = estimate_cost(model_name, estimated_input_tokens, estimated_output_tokens)
        estimates.append({
            "provider": m.get("provider", "openai"),
            "model": model_name,
            "estimated_cost_usd": cost,
        })
        total_estimated_cost += cost

    return {
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_output_tokens": estimated_output_tokens,
        "model_estimates": estimates,
        "total_estimated_cost_usd": total_estimated_cost,
    }


@router.get("/presets")
async def get_comparison_presets():
    """Get preset model combinations for common comparison scenarios."""
    return {
        "presets": [
            {
                "name": "Speed Test",
                "description": "Compare response speed across providers",
                "models": [
                    {"provider": "openai", "model": "gpt-4o-mini"},
                    {"provider": "anthropic", "model": "claude-3-5-haiku-20241022"},
                    {"provider": "google", "model": "gemini-1.5-flash"},
                ],
            },
            {
                "name": "Quality Test",
                "description": "Compare quality across top-tier models",
                "models": [
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                    {"provider": "google", "model": "gemini-1.5-pro"},
                ],
            },
            {
                "name": "Budget Test",
                "description": "Compare cost-effective models",
                "models": [
                    {"provider": "openai", "model": "gpt-3.5-turbo"},
                    {"provider": "anthropic", "model": "claude-3-haiku-20240307"},
                    {"provider": "google", "model": "gemini-1.5-flash"},
                ],
            },
            {
                "name": "Claude Family",
                "description": "Compare different Claude models",
                "models": [
                    {"provider": "anthropic", "model": "claude-3-5-sonnet-20241022"},
                    {"provider": "anthropic", "model": "claude-3-5-haiku-20241022"},
                    {"provider": "anthropic", "model": "claude-3-opus-20240229"},
                ],
            },
            {
                "name": "GPT Family",
                "description": "Compare different GPT models",
                "models": [
                    {"provider": "openai", "model": "gpt-4o"},
                    {"provider": "openai", "model": "gpt-4o-mini"},
                    {"provider": "openai", "model": "gpt-4-turbo"},
                ],
            },
        ]
    }
