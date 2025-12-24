"""
Seed default data for Fichero.

Populates the database with default:
- Providers (OpenAI, Qwen, LM Studio)
- Models (GPT-4o, Qwen VL Max, etc.)
- Tools (Transcribe, Segment, etc.)
- Saved searches (All, Recent, Images)

Run on first app start or to reset defaults.

Usage:
    from fichero.seed import seed_defaults
    seed_defaults()  # Only seeds if tables are empty
    seed_defaults(force=True)  # Re-seeds everything
"""

from fichero.db import db
from fichero.models import (
    Provider,
    ProviderType,
    Model,
    Tool,
    SavedSearch,
    Workflow,
)


def seed_defaults(force: bool = False) -> dict[str, int]:
    """Seed default data into database.

    Args:
        force: If True, re-seed even if data exists

    Returns:
        Dict with counts of seeded items per type
    """
    counts = {}

    counts["providers"] = _seed_providers(force)
    counts["models"] = _seed_models(force)
    counts["tools"] = _seed_tools(force)
    counts["searches"] = _seed_searches(force)
    counts["workflows"] = _seed_workflows(force)

    return counts


# =============================================================================
# Providers
# =============================================================================

DEFAULT_PROVIDERS = [
    Provider(
        id="openai",
        name="OpenAI",
        provider_type=ProviderType.openai,
        sort_order=0,
    ),
    Provider(
        id="qwen",
        name="Qwen",
        provider_type=ProviderType.dashscope,
        sort_order=1,
    ),
    Provider(
        id="lmstudio",
        name="LM Studio",
        provider_type=ProviderType.lmstudio,
        api_base="http://localhost:1234/v1",
        sort_order=2,
    ),
    Provider(
        id="ollama",
        name="Ollama",
        provider_type=ProviderType.ollama,
        api_base="http://localhost:11434",
        sort_order=3,
    ),
]


def _seed_providers(force: bool) -> int:
    if not force and db.count(Provider) > 0:
        return 0

    count = 0
    for provider in DEFAULT_PROVIDERS:
        db.save(provider)
        count += 1
    return count


# =============================================================================
# Models
# =============================================================================

DEFAULT_MODELS = [
    # OpenAI
    Model(
        id="gpt-4o",
        provider_id="openai",
        name="GPT-4o",
        model_id="gpt-4o",
        capabilities=["vision", "chat", "transcription"],
        is_default=True,
        sort_order=0,
        input_cost=2.5,
        output_cost=10.0,
    ),
    Model(
        id="gpt-4o-mini",
        provider_id="openai",
        name="GPT-4o Mini",
        model_id="gpt-4o-mini",
        capabilities=["vision", "chat"],
        sort_order=1,
        input_cost=0.15,
        output_cost=0.6,
    ),
    # Qwen
    Model(
        id="qwen-vl-max",
        provider_id="qwen",
        name="Qwen VL Max",
        model_id="qwen-vl-max",
        capabilities=["vision", "transcription"],
        is_default=True,
        sort_order=0,
    ),
    Model(
        id="qwen-vl-ocr",
        provider_id="qwen",
        name="Qwen VL OCR",
        model_id="qwen-vl-ocr",
        capabilities=["ocr"],
        sort_order=1,
    ),
    # LM Studio
    Model(
        id="lmstudio-local",
        provider_id="lmstudio",
        name="Local Model",
        model_id="local-model",
        capabilities=["chat"],
        is_default=True,
        sort_order=0,
    ),
    # Ollama
    Model(
        id="ollama-llava",
        provider_id="ollama",
        name="LLaVA",
        model_id="llava",
        capabilities=["vision", "chat"],
        is_default=True,
        sort_order=0,
    ),
]


def _seed_models(force: bool) -> int:
    if not force and db.count(Model) > 0:
        return 0

    count = 0
    for model in DEFAULT_MODELS:
        db.save(model)
        count += 1
    return count


# =============================================================================
# Tools
# =============================================================================

DEFAULT_TOOLS = [
    Tool(
        id="transcribe",
        name="Transcribe",
        description="Extract text from images using OCR",
        icon="text.viewfinder",
        module_path="fichero.tools.transcribe",
        sort_order=0,
    ),
    Tool(
        id="segment",
        name="Segment",
        description="Split images into regions",
        icon="scissors",
        module_path="fichero.tools.segment",
        sort_order=1,
    ),
    Tool(
        id="enhance",
        name="Enhance",
        description="Improve image quality",
        icon="wand.and.stars",
        module_path="fichero.tools.enhance",
        sort_order=2,
    ),
    Tool(
        id="describe",
        name="Describe",
        description="Generate image descriptions",
        icon="text.bubble",
        module_path="fichero.tools.describe_images",
        sort_order=3,
    ),
    Tool(
        id="convert_word",
        name="Convert to Word",
        description="Export to Word document",
        icon="doc.richtext",
        module_path="fichero.tools.convert_to_word",
        sort_order=4,
    ),
    Tool(
        id="extract_metadata",
        name="Extract Metadata",
        description="Extract file metadata",
        icon="info.circle",
        module_path="fichero.tools.extract_library_metadata",
        sort_order=5,
    ),
]


def _seed_tools(force: bool) -> int:
    if not force and db.count(Tool) > 0:
        return 0

    count = 0
    for tool in DEFAULT_TOOLS:
        db.save(tool)
        count += 1
    return count


# =============================================================================
# Saved Searches
# =============================================================================

DEFAULT_SEARCHES = [
    SavedSearch(
        id="all",
        name="All Documents",
        icon="doc.on.doc",
        query={},
        sort_order=0,
    ),
    SavedSearch(
        id="recent",
        name="Recent",
        icon="clock",
        query={"days": 7},
        sort_order=1,
    ),
    SavedSearch(
        id="images",
        name="Images",
        icon="photo.stack",
        query={"file_type": "image"},
        sort_order=2,
    ),
    SavedSearch(
        id="unprocessed",
        name="Unprocessed",
        icon="exclamationmark.circle",
        query={"status": "pending"},
        sort_order=3,
    ),
]


def _seed_searches(force: bool) -> int:
    if not force and db.count(SavedSearch) > 0:
        return 0

    count = 0
    for search in DEFAULT_SEARCHES:
        db.save(search)
        count += 1
    return count


# =============================================================================
# Workflows
# =============================================================================

DEFAULT_WORKFLOWS = [
    Workflow(
        id="transcribe-ocr",
        name="Transcribe (OCR)",
        description="Extract text from images",
        steps=[
            {"name": "transcribe", "tool": "transcribe", "provider": "qwen"}
        ],
    ),
    Workflow(
        id="full-analysis",
        name="Full Analysis",
        description="OCR, entities, and summary",
        steps=[
            {"name": "transcribe", "tool": "transcribe", "provider": "qwen"},
            {"name": "describe", "tool": "describe", "provider": "openai"},
        ],
    ),
]


def _seed_workflows(force: bool) -> int:
    if not force and db.count(Workflow) > 0:
        return 0

    count = 0
    for wf in DEFAULT_WORKFLOWS:
        db.save(wf)
        count += 1
    return count


# =============================================================================
# CLI entry point
# =============================================================================

if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv
    counts = seed_defaults(force=force)

    print("Seeded defaults:")
    for name, count in counts.items():
        print(f"  {name}: {count}")
