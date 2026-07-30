"""
Model Comparison Engine

Runs the same prompt against multiple LLM models in parallel,
tracking cost, latency, and response quality for comparison.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, TYPE_CHECKING
from fichero_server.core.timeutil import utc_now


from pydantic import BaseModel, Field

# NOTE: fichero_server.llm is imported at CALL time, not here (#3950). It pulls
# langchain_core (~450 modules beyond the fastapi floor). api/routes/
# model_comparison.py imports this module at engine startup just to register
# the model_comparison tool and expose estimate_cost — neither of which needs
# a chat model. TYPE_CHECKING covers the annotations, which are already
# strings thanks to `from __future__ import annotations` above.
if TYPE_CHECKING:  # pragma: no cover - import-time typing only
    from fichero_server.llm import LLMConfig
from fichero_server.models import Artifact
# NOTE: fichero_server.workflows.runtime is imported at CALL time, not here (#3950).
# It pulls builder -> langgraph + every tool. This module is imported by
# api/routes/model_comparison.py at app startup purely to register the
# model_comparison tool and expose estimate_cost; compiling a graph is
# something a comparison does when it RUNS. See the use site below.
from fichero_server.workflows.registry import get_tool_def, register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


# Passthrough wrappers (#3950).
#
# Deferring these imports must not remove them as MODULE ATTRIBUTES: tests
# patch `fichero_server.workflows.model_comparison.<name>`, which needs (1) the
# attribute to exist for mock.patch to find, and (2) the call site to resolve
# it as a module GLOBAL so the patch takes effect. A function-local import
# satisfies neither and would let those tests pass while silently calling the
# real LLM.


def chat_workflow(*args, **kwargs):
    """Passthrough to fichero_server.llm.chat_workflow; imports it on first call (#3950)."""
    from fichero_server.llm import chat_workflow as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def vision(*args, **kwargs):
    """Passthrough to fichero_server.llm.vision; imports it on first call (#3950)."""
    from fichero_server.llm import vision as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def create_compiled_app(*args, **kwargs):
    """Passthrough to fichero_server.workflows.runtime.create_compiled_app; imports it on first call (#3950)."""
    from fichero_server.workflows.runtime import create_compiled_app as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


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
    structured_decode_success: bool | None = None
    structured_decode_error: str | None = None
    guardrail_fallback_used: bool = False
    fallback_provider: str | None = None
    fallback_model: str | None = None
    raw_response: Any | None = None
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())

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
            "structured_decode_success": self.structured_decode_success,
            "structured_decode_error": self.structured_decode_error,
            "guardrail_fallback_used": self.guardrail_fallback_used,
            "fallback_provider": self.fallback_provider,
            "fallback_model": self.fallback_model,
            "raw_response": self.raw_response,
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
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())

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
    system_prompt: str | None = Field(
        default=None, description="Optional system prompt"
    )
    timeout_seconds: int = Field(default=120, description="Timeout per model")
    include_cost_tracking: bool = Field(default=True, description="Track costs")
    expect_json: bool = Field(
        default=False,
        description="Mark structured_decode_success by parsing each response as JSON",
    )
    response_schema: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON schema requested by the UI for structured output",
    )


# =============================================================================
# Cost Estimation
# =============================================================================

# Models that run on-device or against a local server: always free. Everything
# else prices through the litellm registry (llm/model_types.py, #4325) instead
# of the retired hand-rolled "as of 2024" table.
_FREE_LOCAL_MODELS = {
    "apple",
    "apple-intelligence",
    "apple-vision",
    "apple-speech",
    "mock",
    "local",
    "local-model",
    "llama3.2",
    "llama3.1",
    "mistral",
    "codellama",
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate cost for a model run via the litellm-backed registry (#4325).

    On-device / local-server models are free; unknown models return None
    (pricing unavailable) rather than a stale guess.
    """
    name = (model or "").strip()
    if name.lower() in _FREE_LOCAL_MODELS:
        return 0.0

    from fichero_server.llm.model_types import estimate_cost as _registry_estimate

    return _registry_estimate(name, input_tokens, output_tokens)


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
        comparison_id = str(uuid.uuid4())[:8]

        logger.info(
            f"Starting comparison {comparison_id} with {len(request.models)} models"
        )

        # Run all models in parallel
        tasks = [
            self._run_model(
                spec,
                request.prompt,
                request.system_prompt,
                request.timeout_seconds,
                expect_json=request.expect_json or request.response_schema is not None,
            )
            for spec in request.models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        model_results: list[ModelResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                spec = request.models[i]
                model_results.append(
                    ModelResult(
                        provider=spec.provider,
                        model=spec.model,
                        response="",
                        latency_ms=0,
                        error=str(result),
                    )
                )
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
        *,
        expect_json: bool = False,
    ) -> ModelResult:
        """Run a single model and collect metrics."""
        start_time = time.time()

        try:
            response, fallback = await self._invoke_model_with_optional_fallback(
                spec, prompt, system_prompt, timeout_seconds
            )

            latency_ms = (time.time() - start_time) * 1000

            # Extract token counts if available
            input_tokens = 0
            output_tokens = 0

            if hasattr(response, "response_metadata"):
                metadata = response.response_metadata
                if "usage" in metadata:
                    usage = metadata["usage"]
                    input_tokens = usage.get(
                        "input_tokens", usage.get("prompt_tokens", 0)
                    )
                    output_tokens = usage.get(
                        "output_tokens", usage.get("completion_tokens", 0)
                    )
                elif "token_usage" in metadata:
                    usage = metadata["token_usage"]
                    input_tokens = usage.get(
                        "input_tokens", usage.get("prompt_tokens", 0)
                    )
                    output_tokens = usage.get(
                        "output_tokens", usage.get("completion_tokens", 0)
                    )

            # Estimate tokens if not available
            if input_tokens == 0:
                # Rough estimate: ~4 chars per token
                input_tokens = len(prompt) // 4
            if output_tokens == 0:
                output_tokens = len(response.content) // 4

            cost = estimate_cost(spec.model, input_tokens, output_tokens) or 0.0
            structured_success = None
            structured_error = None
            raw_response = None
            if expect_json:
                try:
                    raw_response = json.loads(response.content)
                    structured_success = True
                except (TypeError, json.JSONDecodeError) as exc:
                    structured_success = False
                    structured_error = str(exc)

            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response=response.content,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                structured_decode_success=structured_success,
                structured_decode_error=structured_error,
                guardrail_fallback_used=fallback is not None,
                fallback_provider=fallback.provider if fallback else None,
                fallback_model=fallback.model if fallback else None,
                raw_response=raw_response,
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

    async def _invoke_model_with_optional_fallback(
        self,
        spec: ModelSpec,
        prompt: str,
        system_prompt: str | None,
        timeout_seconds: int,
    ) -> tuple[Any, ModelSpec | None]:
        """Invoke a model and record when Apple guardrail fallback is used."""
        # Imported here rather than at module scope: pulls langchain_core (#3950).
        # AppleUnavailableError is caught below — an `except` clause is a global
        # lookup, so the name must be bound in this scope before the try.
        from fichero_server.llm import AppleUnavailableError, resolve_model_alias  # noqa: PLC0415

        try:
            return await self._invoke_model(spec, prompt, system_prompt, timeout_seconds), None
        except AppleUnavailableError:
            provider, model = resolve_model_alias("$large", "")
            if provider == spec.provider and model == spec.model:
                raise
            fallback_spec = ModelSpec(
                provider=provider,
                model=model,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
            )
            return (
                await self._invoke_model(
                    fallback_spec, prompt, system_prompt, timeout_seconds
                ),
                fallback_spec,
            )

    async def _invoke_model(
        self,
        spec: ModelSpec,
        prompt: str,
        system_prompt: str | None,
        timeout_seconds: int,
    ) -> Any:
        # LLMConfig only — chat_workflow is a module-level passthrough below,
        # because tests patch it; a local import here would shadow the patch.
        from fichero_server.llm import LLMConfig  # noqa: PLC0415

        config = LLMConfig(
            provider=spec.provider,
            model=spec.model,
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
        )
        messages = [{"role": "user", "content": prompt}]
        content = await asyncio.wait_for(
            chat_workflow(messages, config, system=system_prompt),
            timeout=timeout_seconds,
        )
        return SimpleNamespace(content=content, response_metadata={})

    def get_history(self, limit: int = 10) -> list[dict]:
        """Get recent comparison history."""
        return [c.to_dict() for c in self.comparison_history[-limit:]]

    def get_comparison(self, comparison_id: str) -> ComparisonResult | None:
        """Get a specific comparison by ID."""
        for c in self.comparison_history:
            if c.comparison_id == comparison_id:
                return c
        return None

    async def compare_vision(
        self,
        images: list[str],
        prompt: str,
        models: list[ModelSpec],
        detail: str = "auto",
        timeout_seconds: int = 120,
    ) -> ComparisonResult:
        """Compare vision models on the same image(s).

        Args:
            images: List of image URLs or base64 data URIs
            prompt: Prompt to send with images
            models: Models to compare (must support vision)
            detail: Image detail level (auto, low, high)
            timeout_seconds: Timeout per model

        Returns:
            ComparisonResult with all model responses
        """
        comparison_id = str(uuid.uuid4())[:8]

        logger.info(
            f"Starting vision comparison {comparison_id} with {len(models)} models, {len(images)} images"
        )

        tasks = [
            self._run_vision_model(spec, images, prompt, detail, timeout_seconds)
            for spec in models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        model_results: list[ModelResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                spec = models[i]
                model_results.append(
                    ModelResult(
                        provider=spec.provider,
                        model=spec.model,
                        response="",
                        latency_ms=0,
                        error=str(result),
                    )
                )
            else:
                model_results.append(result)

        # Calculate stats
        successful_results = [r for r in model_results if not r.error]
        fastest_model = None
        cheapest_model = None

        if successful_results:
            fastest = min(successful_results, key=lambda r: r.latency_ms)
            fastest_model = f"{fastest.provider}/{fastest.model}"
            cheapest = min(successful_results, key=lambda r: r.cost_usd)
            cheapest_model = f"{cheapest.provider}/{cheapest.model}"

        comparison = ComparisonResult(
            prompt=f"[Vision: {len(images)} images] {prompt}",
            models_compared=[f"{s.provider}/{s.model}" for s in models],
            results=model_results,
            fastest_model=fastest_model,
            cheapest_model=cheapest_model,
            total_cost_usd=sum(r.cost_usd for r in model_results),
            total_latency_ms=sum(r.latency_ms for r in model_results),
            comparison_id=comparison_id,
        )

        self.comparison_history.append(comparison)
        return comparison

    async def _run_vision_model(
        self,
        spec: ModelSpec,
        images: list[str],
        prompt: str,
        detail: str,
        timeout_seconds: int,
    ) -> ModelResult:
        """Run a single vision model."""
        # LLMConfig only — `vision` is a module-level passthrough below,
        # because tests patch it; a local import here would shadow the patch.
        from fichero_server.llm import LLMConfig  # noqa: PLC0415

        start_time = time.time()

        try:
            config = LLMConfig(
                provider=spec.provider,
                model=spec.model,
                temperature=spec.temperature,
            )

            # ``vision`` is an async coroutine that returns a str. It must be
            # awaited directly — wrapping it in ``asyncio.to_thread`` only builds
            # the coroutine object (never awaiting it), so ``response`` came back
            # as a coroutine and every model failed with
            # "object of type 'coroutine' has no len()".
            response = await asyncio.wait_for(
                vision(images, prompt, config),
                timeout=timeout_seconds,
            )

            latency_ms = (time.time() - start_time) * 1000

            if not response:
                return ModelResult(
                    provider=spec.provider,
                    model=spec.model,
                    response="",
                    latency_ms=latency_ms,
                    error="empty response from vision model (#2212)",
                )

            # Estimate tokens (vision is typically more expensive)
            input_tokens = len(prompt) // 4 + (
                len(images) * 1000
            )  # ~1000 tokens per image
            output_tokens = len(response) // 4
            cost = estimate_cost(spec.model, input_tokens, output_tokens) or 0.0

            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response=response,
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
            logger.exception(f"Vision model {spec.provider}/{spec.model} failed: {e}")
            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
            )

    async def compare_tool(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        models: list[ModelSpec],
        tool_config: dict[str, Any] | None = None,
        timeout_seconds: int = 120,
    ) -> ComparisonResult:
        """Compare models running the same workflow tool.

        Args:
            tool_name: Name of the workflow tool (describe, summarize, etc.)
            inputs: Tool inputs (files, text, etc.)
            models: Models to compare
            tool_config: Optional tool configuration overrides
            timeout_seconds: Timeout per model

        Returns:
            ComparisonResult with all model responses
        """
        from fichero_server.workflows.registry import get_tool

        comparison_id = str(uuid.uuid4())[:8]

        logger.info(
            f"Starting tool comparison {comparison_id}: {tool_name} with {len(models)} models"
        )

        # Get the tool function
        tool_func = get_tool(tool_name)
        if tool_func is None:
            raise ValueError(f"Unknown tool: {tool_name}")

        tasks = [
            self._run_tool_with_model(
                tool_func, tool_name, spec, inputs, tool_config, timeout_seconds
            )
            for spec in models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        model_results: list[ModelResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                spec = models[i]
                model_results.append(
                    ModelResult(
                        provider=spec.provider,
                        model=spec.model,
                        response="",
                        latency_ms=0,
                        error=str(result),
                    )
                )
            else:
                model_results.append(result)

        # Calculate stats
        successful_results = [r for r in model_results if not r.error]
        fastest_model = None
        cheapest_model = None

        if successful_results:
            fastest = min(successful_results, key=lambda r: r.latency_ms)
            fastest_model = f"{fastest.provider}/{fastest.model}"
            cheapest = min(successful_results, key=lambda r: r.cost_usd)
            cheapest_model = f"{cheapest.provider}/{cheapest.model}"

        comparison = ComparisonResult(
            prompt=f"[Tool: {tool_name}] {str(inputs)[:100]}",
            models_compared=[f"{s.provider}/{s.model}" for s in models],
            results=model_results,
            fastest_model=fastest_model,
            cheapest_model=cheapest_model,
            total_cost_usd=sum(r.cost_usd for r in model_results),
            total_latency_ms=sum(r.latency_ms for r in model_results),
            comparison_id=comparison_id,
        )

        self.comparison_history.append(comparison)
        return comparison

    async def compare_workflow(
        self,
        workflow,
        inputs: dict[str, Any],
        models: list[ModelSpec],
        *,
        library_path: str,
        timeout_seconds: int = 300,
        db: Any | None = None,
    ) -> ComparisonResult:
        """Run the same workflow once per model override and compare outcomes."""
        comparison_id = str(uuid.uuid4())[:8]

        logger.info(
            "Starting workflow comparison %s for workflow %s with %d models",
            comparison_id,
            getattr(workflow, "id", None) or getattr(workflow, "name", "<unknown>"),
            len(models),
        )

        tasks = [
            self._run_workflow_with_model(
                workflow=workflow,
                inputs=inputs,
                spec=spec,
                library_path=library_path,
                timeout_seconds=timeout_seconds,
                db=db,
            )
            for spec in models
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        model_results: list[ModelResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                spec = models[i]
                model_results.append(
                    ModelResult(
                        provider=spec.provider,
                        model=spec.model,
                        response="",
                        latency_ms=0,
                        error=str(result),
                    )
                )
            else:
                model_results.append(result)

        successful_results = [r for r in model_results if not r.error]
        fastest_model = None
        cheapest_model = None
        if successful_results:
            fastest = min(successful_results, key=lambda r: r.latency_ms)
            fastest_model = f"{fastest.provider}/{fastest.model}"
            cheapest = min(successful_results, key=lambda r: r.cost_usd)
            cheapest_model = f"{cheapest.provider}/{cheapest.model}"

        comparison = ComparisonResult(
            prompt=(
                f"[Workflow: {getattr(workflow, 'name', '') or getattr(workflow, 'id', '')}] "
                f"{json.dumps(inputs, ensure_ascii=False)[:100]}"
            ),
            models_compared=[f"{s.provider}/{s.model}" for s in models],
            results=model_results,
            fastest_model=fastest_model,
            cheapest_model=cheapest_model,
            total_cost_usd=sum(r.cost_usd for r in model_results),
            total_latency_ms=sum(r.latency_ms for r in model_results),
            comparison_id=comparison_id,
        )

        self.comparison_history.append(comparison)
        return comparison

    async def _run_tool_with_model(
        self,
        tool_func,
        tool_name: str,
        spec: ModelSpec,
        inputs: dict[str, Any],
        tool_config: dict[str, Any] | None,
        timeout_seconds: int,
    ) -> ModelResult:
        """Run a workflow tool with a specific model."""
        from fichero_server.workflows.types import State

        # Imported here rather than at module scope: pulls langchain_core (#3950).
        from fichero_server.llm import LLMConfig  # noqa: PLC0415

        start_time = time.time()

        try:
            config = LLMConfig(
                provider=spec.provider,
                model=spec.model,
                temperature=spec.temperature,
            )

            # Merge inputs with tool config
            merged_inputs = {**inputs}
            if tool_config:
                merged_inputs.update(tool_config)

            # Create minimal state
            state = State(
                files=[],
                results={},
                errors={},
                metadata={},
            )

            # Run the tool
            result = await asyncio.wait_for(
                tool_func(merged_inputs, state, config),
                timeout=timeout_seconds,
            )

            latency_ms = (time.time() - start_time) * 1000

            # Extract response - try common output keys
            response = ""
            if isinstance(result, dict):
                for key in ["text", "description", "summary", "result", "output"]:
                    if key in result and result[key]:
                        response = str(result[key])
                        break
                if not response:
                    response = str(result)

            # Estimate cost
            input_tokens = len(str(inputs)) // 4
            output_tokens = len(response) // 4
            cost = estimate_cost(spec.model, input_tokens, output_tokens) or 0.0

            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response=response,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                structured_decode_success=isinstance(result, dict)
                and not bool(result.get("error")),
                structured_decode_error=str(result.get("error"))
                if isinstance(result, dict) and result.get("error")
                else None,
                raw_response=result if isinstance(result, dict) else None,
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
            logger.exception(
                f"Tool {tool_name} with {spec.provider}/{spec.model} failed: {e}"
            )
            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=str(e),
            )

    async def _run_workflow_with_model(
        self,
        *,
        workflow,
        inputs: dict[str, Any],
        spec: ModelSpec,
        library_path: str,
        timeout_seconds: int,
        db: Any | None,
    ) -> ModelResult:
        """Run one workflow variant with a provider/model override."""
        start_time = time.time()

        try:
            workflow_variant = self._workflow_with_model_override(workflow, spec)
            final_state = await self._execute_workflow_variant(
                workflow_variant=workflow_variant,
                inputs=inputs,
                library_path=library_path,
                timeout_seconds=timeout_seconds,
            )
            latency_ms = (time.time() - start_time) * 1000
            response = self._workflow_response_text(final_state, db=db)
            input_tokens, output_tokens = self._workflow_token_estimate(
                workflow_variant=workflow_variant,
                inputs=inputs,
                response=response,
                final_state=final_state,
            )
            cost = estimate_cost(spec.model, input_tokens, output_tokens) or 0.0

            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response=response,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                raw_response=final_state if isinstance(final_state, dict) else None,
            )
        except asyncio.TimeoutError:
            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=f"Timeout after {timeout_seconds}s",
            )
        except Exception as exc:
            logger.exception(
                "Workflow comparison failed for %s/%s: %s",
                spec.provider,
                spec.model,
                exc,
            )
            return ModelResult(
                provider=spec.provider,
                model=spec.model,
                response="",
                latency_ms=(time.time() - start_time) * 1000,
                error=str(exc),
            )

    async def _execute_workflow_variant(
        self,
        *,
        workflow_variant,
        inputs: dict[str, Any],
        library_path: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        # library_path is the .fichero bundle directory (e.g. MyLib.fichero/).
        # create_compiled_app → AsyncDuckDBCheckpointer.from_db_path expects the
        # .duckdb FILE, not the directory — passing the directory raises
        # IOException: Is a directory (#2211).
        from pathlib import Path as _Path  # noqa: PLC0415

        # build_initial_state only — create_compiled_app is a module-level
        # passthrough below, because tests patch it.
        from fichero_server.workflows.runtime import build_initial_state  # noqa: PLC0415

        db_path: str | _Path = library_path
        if library_path:
            p = _Path(library_path)
            if p.is_dir():
                db_path = p / "fichero.duckdb"
        app, _ = create_compiled_app(
            workflow_variant,
            db_path=db_path,
            enable_parallel=False,
            skip_cache=True,
        )
        config = {
            "configurable": {
                "thread_id": f"compare-{uuid.uuid4().hex[:12]}",
                "checkpoint_ns": "",
            }
        }
        initial_state = build_initial_state(inputs, library_path=library_path)
        initial_state["workflow_id"] = workflow_variant.id
        final_state = await asyncio.wait_for(
            app.ainvoke(initial_state, config=config),
            timeout=timeout_seconds,
        )
        if isinstance(final_state, dict) and final_state.get("error"):
            raise RuntimeError(str(final_state["error"]))
        return final_state

    def _workflow_with_model_override(self, workflow, spec: ModelSpec):
        workflow_variant = (
            workflow.model_copy(deep=True)
            if hasattr(workflow, "model_copy")
            else copy.deepcopy(workflow)
        )
        workflow_variant.provider = spec.provider
        workflow_variant.model = spec.model
        for node in workflow_variant.nodes:
            tool_def = get_tool_def(node.tool)
            if not (tool_def and tool_def.uses_llm):
                continue
            node.provider_name = spec.provider
            node.model_name = spec.model
        return workflow_variant

    def _workflow_response_text(
        self,
        final_state: dict[str, Any] | Any,
        *,
        db: Any | None,
    ) -> str:
        if not isinstance(final_state, dict):
            return str(final_state)

        outputs = final_state.get("outputs")
        completed = final_state.get("completed_nodes") or []
        if isinstance(outputs, dict):
            for node_id in reversed(completed):
                text = self._extract_text(outputs.get(node_id))
                if text:
                    return text
            for value in reversed(list(outputs.values())):
                text = self._extract_text(value)
                if text:
                    return text

        artifact_ids = final_state.get("artifacts")
        if db is not None and isinstance(artifact_ids, list):
            for artifact_id in reversed(artifact_ids):
                try:
                    artifact = db.get(Artifact, artifact_id)
                except Exception:
                    artifact = None
                if artifact and artifact.content:
                    return artifact.content

        return self._extract_text(final_state) or ""

    def _workflow_token_estimate(
        self,
        *,
        workflow_variant,
        inputs: dict[str, Any],
        response: str,
        final_state: dict[str, Any] | Any,
    ) -> tuple[int, int]:
        llm_node_count = 0
        for node in getattr(workflow_variant, "nodes", []):
            tool_def = get_tool_def(node.tool)
            if tool_def and tool_def.uses_llm:
                llm_node_count += 1
        llm_node_count = max(llm_node_count, 1)

        input_tokens = max(len(json.dumps(inputs, ensure_ascii=False)) // 4, 1)
        output_tokens = max(len(response) // 4, 1) if response else 0

        if isinstance(final_state, dict):
            outputs = final_state.get("outputs")
            if isinstance(outputs, dict):
                extra_output_tokens = 0
                for value in outputs.values():
                    text = self._extract_text(value)
                    if text:
                        extra_output_tokens += len(text) // 4
                output_tokens = max(output_tokens, extra_output_tokens)

        return input_tokens * llm_node_count, output_tokens

    def _extract_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in (
                "text",
                "content",
                "response",
                "summary",
                "description",
                "result",
                "output",
                "translation",
                "value",
            ):
                text = self._extract_text(value.get(key))
                if text:
                    return text
            return ""
        if isinstance(value, list):
            parts = [self._extract_text(item) for item in value]
            return "\n".join(part for part in parts if part)
        return str(value)


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
            description="Prompt to send to all models",
        ),
        PortDef(
            id="system_prompt",
            name="System Prompt",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Optional system prompt",
        ),
    ],
    output_ports=[
        PortDef(
            id="results",
            name="Results",
            port_type="output",
            data_type=DataType.JSON,
            description="Comparison results from all models",
        ),
        PortDef(
            id="fastest",
            name="Fastest Response",
            port_type="output",
            data_type=DataType.TEXT,
            description="Response from fastest model",
        ),
        PortDef(
            id="cheapest",
            name="Cheapest Response",
            port_type="output",
            data_type=DataType.TEXT,
            description="Response from cheapest model",
        ),
        PortDef(
            id="summary",
            name="Summary",
            port_type="output",
            data_type=DataType.JSON,
            description="Summary statistics",
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
            "default": [],
            "description": (
                "Models to compare. Empty = the workflow's own default "
                "provider/model (tier aliases like $medium resolve through "
                "AI Defaults, #4325)."
            ),
        },
        "timeout_seconds": {
            "type": "integer",
            "default": 60,
            "description": "Timeout per model in seconds",
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
            "error": "No prompt provided",
        }

    # Build model specs. Entries missing provider/model inherit the workflow's
    # own default config instead of a hardcoded vintage model (#4325) — tier
    # aliases ($medium etc.) then resolve through AI Defaults downstream.
    model_specs = []
    for m in models_config:
        model_specs.append(
            ModelSpec(
                provider=m.get("provider") or llm_config.provider,
                model=m.get("model") or llm_config.model,
                temperature=m.get("temperature", 0.7),
            )
        )

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
        "avg_latency_ms": result.total_latency_ms / len(result.results)
        if result.results
        else 0,
    }

    return {
        "results": result.to_dict(),
        "fastest": fastest_response,
        "cheapest": cheapest_response,
        "summary": summary,
    }
