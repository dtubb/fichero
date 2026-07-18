"""
Models Routes

API endpoints for browsing and selecting LLM models.
Proxies Hugging Face Hub API with caching for model discovery.
"""

import logging
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from fichero.api.routes.auth_accounts import _require_authenticated_or_bootstrap

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(_require_authenticated_or_bootstrap)])

# Simple in-memory cache for HF API responses
_cache: dict[str, tuple[datetime, list]] = {}
CACHE_TTL = timedelta(minutes=15)


# =============================================================================
# Response Models
# =============================================================================


class HFModelInfo(BaseModel):
    """Hugging Face model information."""

    id: str  # e.g., "meta-llama/Llama-3.1-8B-Instruct"
    downloads: int
    likes: int
    pipeline_tag: Optional[str]  # Task type
    library_name: Optional[str]  # Primary library (transformers, gguf, etc.)
    created_at: Optional[str]
    tags: list[str] = []


class HFTaskCategory(BaseModel):
    """Hugging Face task/pipeline category."""

    id: str  # e.g., "text-generation"
    label: str  # e.g., "Text Generation"


class HFTaskListResponse(BaseModel):
    """Envelope for a list of Hugging Face task categories."""

    items: list[HFTaskCategory]
    count: int


class ModelSearchResponse(BaseModel):
    """Paginated model search results."""

    models: list[HFModelInfo]
    total: int
    has_more: bool


# =============================================================================
# Helper Functions
# =============================================================================


def _get_cache(key: str) -> Optional[list]:
    """Get cached response if not expired."""
    if key in _cache:
        cached_at, data = _cache[key]
        if datetime.now() - cached_at < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _set_cache(key: str, data: list) -> None:
    """Cache response."""
    _cache[key] = (datetime.now(), data)


async def _fetch_hf_models(
    task: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "downloads",
    limit: int = 20,
    offset: int = 0,
    library: Optional[str] = None,
) -> list[dict]:
    """Fetch models from Hugging Face Hub API."""
    params = {
        "sort": sort,
        "limit": limit,
        "skip": offset,
    }
    if task:
        params["pipeline_tag"] = task
    if search:
        params["search"] = search
    if library:
        params["library"] = library

    cache_key = f"hf_models:{task}:{search}:{sort}:{limit}:{offset}:{library}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    import httpx  # lazy (#3985): keep off the engine boot path

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://huggingface.co/api/models",
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            _set_cache(cache_key, data)
            return data
        except httpx.HTTPError as e:
            logger.error(f"HuggingFace API error: {e}")
            raise HTTPException(
                status_code=502, detail=f"HuggingFace API error: {str(e)}"
            )


async def _fetch_hf_tasks() -> list[dict]:
    """Fetch available task categories from Hugging Face."""
    cache_key = "hf_tasks"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    import httpx  # lazy (#3985): keep off the engine boot path

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://huggingface.co/api/models-tags-by-type",
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            tasks = data.get("pipeline_tag", [])
            _set_cache(cache_key, tasks)
            return tasks
        except httpx.HTTPError as e:
            logger.error(f"HuggingFace API error: {e}")
            raise HTTPException(
                status_code=502, detail=f"HuggingFace API error: {str(e)}"
            )


# =============================================================================
# Routes
# =============================================================================


@router.get("/huggingface/tasks", response_model=HFTaskListResponse)
async def list_hf_tasks() -> HFTaskListResponse:
    """List available Hugging Face task categories for filtering."""
    tasks = await _fetch_hf_tasks()
    items = [
        HFTaskCategory(id=t["id"], label=t.get("label", t["id"])) for t in tasks
    ]
    return HFTaskListResponse(items=items, count=len(items))


@router.get("/huggingface")
async def search_hf_models(
    task: Optional[str] = Query(
        None, description="Filter by task (e.g., text-generation)"
    ),
    search: Optional[str] = Query(None, description="Search query"),
    sort: str = Query(
        "downloads", description="Sort by: downloads, likes, trending, lastModified"
    ),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    library: Optional[str] = Query(
        None, description="Filter by library (e.g., transformers, gguf)"
    ),
) -> ModelSearchResponse:
    """
    Search Hugging Face models.

    Popular tasks:
    - text-generation: LLMs for chat/completion
    - image-to-text: Vision models (OCR, captioning)
    - text-to-image: Image generation (Stable Diffusion, etc.)
    - feature-extraction: Embedding models
    - automatic-speech-recognition: Whisper, etc.
    """
    models_data = await _fetch_hf_models(
        task=task,
        search=search,
        sort=sort,
        limit=limit + 1,  # Fetch one extra to check has_more
        offset=offset,
        library=library,
    )

    has_more = len(models_data) > limit
    models_data = models_data[:limit]

    models = [
        HFModelInfo(
            id=m.get("modelId") or m.get("id", ""),
            downloads=m.get("downloads", 0),
            likes=m.get("likes", 0),
            pipeline_tag=m.get("pipeline_tag"),
            library_name=m.get("library_name"),
            created_at=m.get("createdAt"),
            tags=m.get("tags", []),
        )
        for m in models_data
    ]

    return ModelSearchResponse(
        models=models,
        total=len(models),  # HF API doesn't return total count
        has_more=has_more,
    )


@router.get("/huggingface/{model_id:path}")
async def get_hf_model(model_id: str) -> HFModelInfo:
    """Get details for a specific Hugging Face model."""
    cache_key = f"hf_model:{model_id}"
    cached = _get_cache(cache_key)

    if cached is None:
        import httpx  # lazy (#3985): keep off the engine boot path

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"https://huggingface.co/api/models/{model_id}",
                    timeout=30.0,
                )
                response.raise_for_status()
                cached = [response.json()]
                _set_cache(cache_key, cached)
            except httpx.HTTPError as e:
                logger.error(f"HuggingFace API error: {e}")
                raise HTTPException(
                    status_code=502, detail=f"HuggingFace API error: {str(e)}"
                )

    m = cached[0]
    return HFModelInfo(
        id=m.get("modelId") or m.get("id", ""),
        downloads=m.get("downloads", 0),
        likes=m.get("likes", 0),
        pipeline_tag=m.get("pipeline_tag"),
        library_name=m.get("library_name"),
        created_at=m.get("createdAt"),
        tags=m.get("tags", []),
    )
