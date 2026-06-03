"""Versioned workflow-tool system prompt profiles.

This module is the backend source of truth for default tool alignment
profiles. Task prompts remain tool-specific and editable; these profiles
capture the stable role, constraints, and output expectations that should
travel with a tool invocation.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from fichero.workflows.types import ToolPromptProfile

PROMPT_PROFILE_SOURCE = "fichero.workflows.prompt_profiles"
PROMPT_PROFILE_VERSION = 1


_PROFILES: dict[str, ToolPromptProfile] = {
    "transcribe.strict_fidelity.v1": ToolPromptProfile(
        id="transcribe.strict_fidelity",
        version=PROMPT_PROFILE_VERSION,
        role="Faithful transcription engine for archival source images.",
        constraints=[
            "Transcribe only visible text from the supplied source.",
            "Do not invent, normalize, summarize, translate, or explain content.",
            "Preserve spelling, punctuation, line breaks, layout, and diacritics when visible.",
            "Mark uncertainty explicitly instead of guessing.",
        ],
        output_expectations=[
            "Return only the transcription or the configured structured transcription object.",
            "Use [ILLEGIBLE] for unreadable spans and [UNCERTAIN] for low-confidence readings.",
            "Use [sin texto] when no text is legible.",
        ],
        source=PROMPT_PROFILE_SOURCE,
    ),
    "extract_entities.schema_constrained.v1": ToolPromptProfile(
        id="extract_entities.schema_constrained",
        version=PROMPT_PROFILE_VERSION,
        role="Schema-constrained extractor over provided source text.",
        constraints=[
            "Extract only entities supported by the source text.",
            "Do not infer missing names, dates, places, relationships, or categories.",
            "Keep uncertain values out unless the source text explicitly supports them.",
        ],
        output_expectations=[
            "Return valid JSON matching the requested extraction schema.",
            "Use empty arrays for requested entity types that are not present.",
            "Do not include prose outside the JSON response.",
        ],
        source=PROMPT_PROFILE_SOURCE,
    ),
    "catalogue.conservative_metadata.v1": ToolPromptProfile(
        id="catalogue.conservative_metadata",
        version=PROMPT_PROFILE_VERSION,
        role="Conservative archival catalogue synthesizer.",
        constraints=[
            "Ground catalogue metadata in transcript text or prior extracted claims.",
            "Represent uncertainty plainly; do not fill gaps with plausible-sounding details.",
            "Prefer omission over unsupported facts.",
        ],
        output_expectations=[
            "Produce catalogue prose or structured sections in the requested language.",
            "Keep names, places, dates, and events tied to source evidence.",
            "Avoid confident claims when source evidence is ambiguous.",
        ],
        source=PROMPT_PROFILE_SOURCE,
    ),
}

_TOOL_DEFAULTS = {
    "transcribe": "transcribe.strict_fidelity.v1",
    "extract_entities": "extract_entities.schema_constrained.v1",
    "extract_all": "extract_entities.schema_constrained.v1",
    "catalogue": "catalogue.conservative_metadata.v1",
}


def prompt_override_enabled() -> bool:
    """Return whether user-supplied system prompt overrides are enabled."""
    value = os.environ.get("FICHERO_WORKFLOW_TOOL_PROMPT_OVERRIDES", "")
    return value.strip().lower() in {"1", "true", "yes", "on", "dev"}


def get_prompt_profile(profile_key: str | None) -> ToolPromptProfile | None:
    """Return a copy of a profile by key."""
    if not profile_key:
        return None
    profile = _PROFILES.get(profile_key)
    return deepcopy(profile) if profile else None


def default_prompt_profile_for_tool(tool_name: str) -> ToolPromptProfile | None:
    """Return the default prompt profile for a workflow tool."""
    return get_prompt_profile(_TOOL_DEFAULTS.get(tool_name))


def resolve_system_prompt(tool_name: str, inputs: dict[str, Any]) -> str | None:
    """Resolve the system prompt for a tool invocation.

    User overrides are deliberately gated until the profile UI and release
    QA have validated arbitrary prompt edits.
    """
    override = str(inputs.get("system_prompt_override") or "").strip()
    if override and prompt_override_enabled():
        return override

    profile_key = inputs.get("system_prompt_profile")
    profile = get_prompt_profile(profile_key)
    if profile is None:
        profile = default_prompt_profile_for_tool(tool_name)
    return profile.render_system_prompt() if profile else None

