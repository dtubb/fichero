"""
Handwriting Tool (Paleography)

Specialized transcription of historical handwriting with script-specific guidance.
Handles diacritics, abbreviations, era-specific letter forms, and damaged text.
Inherits from vision_base.py - optimized for historical document reading.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    process_vision,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="handwriting",
    update_page_content=True,
    trigger_embedding=True,
    supports_apple_vision=False,
    metadata_field="handwriting",
)

HANDWRITING_CONFIG = {
    "script": {
        "type": "string",
        "enum": [
            "latin_modern",
            "latin_colonial",
            "latin_medieval",
            "secretary_hand",
            "copperplate",
            "gothic",
            "arabic",
            "hebrew",
            "cyrillic",
            "cjk",
            "devanagari",
            "greek",
            "mixed",
            "unknown",
        ],
        "default": "unknown",
        "description": "Script type",
    },
    "era": {
        "type": "string",
        "enum": [
            "medieval",
            "renaissance",
            "colonial",
            "18th_century",
            "19th_century",
            "early_20th_century",
            "modern",
            "unknown",
        ],
        "default": "unknown",
        "description": "Historical era",
    },
    "language": {
        "type": "string",
        "default": "auto",
        "description": "Document language",
    },
    "handle_diacritics": {
        "type": "boolean",
        "default": True,
        "description": "Preserve diacritics",
    },
}


# =============================================================================
# Script-Specific Guidance
# =============================================================================

SCRIPT_GUIDANCE = {
    "latin_modern": """Modern Latin script (post-1900):
- Standard letterforms with minor personal variations
- Watch for hastily written letters that blur together""",
    "latin_colonial": """Colonial-era Latin script (Spanish/Portuguese/French colonial, 16th-19th century):
- Long 's' (ſ) common in earlier documents
- Abbreviations: q̃ (que), qⁿ (quien), dho (dicho), ntro (nuestro)
- Diacritics: tilde (~) over vowels for nasalization, cedilla (ç)
- Connected letterforms, especially in rapid writing
- Numbers often written with roman numerals
- Watch for: ñ vs n with tilde, doubled letters, archaic spellings""",
    "latin_medieval": """Medieval Latin script:
- Highly abbreviated text (suspensions, contractions, nomina sacra)
- Common abbreviations: ꝑ (per/par), ꝓ (pro), ꝙ (quod), ꝫ (et/con)
- Ligatures: æ, œ, ct, st
- Insular and continental letterform variants
- Rubrication and decorated initials""",
    "secretary_hand": """Secretary hand (English, 15th-17th century):
- Distinctive letter forms: e (looks like reversed 3), r (2-stroke), s (long/short forms)
- Heavy use of abbreviations and superscript letters
- Connected writing with looped ascenders/descenders
- Common confusions: c/t, n/u, m/in, h/b""",
    "copperplate": """Copperplate/roundhand script (18th-19th century):
- Elegant slanted writing with thick/thin strokes
- Clearly formed letters but decorative flourishes
- Capital letters often heavily ornamented
- Watch for: flourished initial letters obscuring the actual letter""",
    "gothic": """Gothic/Blackletter script:
- Angular letterforms with minimal curves
- Many letters look similar (i, m, n, u appear as vertical strokes)
- Heavy use of abbreviation marks
- Distinction between textura, rotunda, and bastarda forms""",
    "arabic": """Arabic script:
- Right-to-left reading direction
- Letters change form based on position (initial, medial, final, isolated)
- Diacritical dots distinguish many letters (ب ت ث)
- Vowel marks (harakat) may be partially or fully omitted
- Common ligatures and calligraphic variations
- Watch for: missing dots, ambiguous letter forms without context""",
    "hebrew": """Hebrew script:
- Right-to-left reading direction
- No standard cursive connections between letters
- Vowel points (nikkud) may be absent
- Similar-looking letters: ב/כ, ד/ר, ו/ז, ח/ה
- Final forms for some letters (ך, ם, ן, ף, ץ)""",
    "cyrillic": """Cyrillic script:
- Similar to Latin with additional characters
- Pre-reform Russian includes: ъ (hard sign), ѣ (yat), і, ѳ
- Handwritten forms differ significantly from printed
- Watch for: cursive forms where т looks like m, д looks like g""",
    "cjk": """CJK (Chinese/Japanese/Korean) characters:
- Complex multi-stroke characters
- Stroke order and direction matters for identification
- Cursive/running script may significantly alter character appearance
- Historical forms may differ from modern standard""",
    "devanagari": """Devanagari script:
- Headline (shirorekha) connecting characters
- Vowel marks (matras) above, below, and around consonants
- Conjunct consonants (half-forms)
- Historical variations in letterforms""",
    "greek": """Greek script:
- Both capital and minuscule forms
- Diacritical marks: acute (´), grave (`), circumflex (ˆ), rough/smooth breathing
- Historical forms differ from modern
- Watch for: ligatures in older manuscripts""",
}

ERA_GUIDANCE = {
    "medieval": "Documents from 5th-15th century. Expect heavy abbreviation, Latin text, parchment damage, faded ink.",
    "renaissance": "Documents from 14th-17th century. Transitional scripts, early printing influence, humanist hands.",
    "colonial": "Documents from 16th-19th century colonial administrations. Legal and administrative language, mixed scripts.",
    "18th_century": "18th century documents. Copperplate influence, standardizing spelling, legal formulae.",
    "19th_century": "19th century documents. More standardized but varied personal hands, early typewriting mixed with handwriting.",
    "early_20th_century": "Early 20th century. Relatively modern letterforms, but ink and paper degradation common.",
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(script: str, era: str, language: str, handle_diacritics: bool) -> str:
    """Build the paleography transcription prompt."""
    script_text = SCRIPT_GUIDANCE.get(script, "")
    era_text = ERA_GUIDANCE.get(era, "")

    language_text = ""
    if language and language != "auto":
        language_text = f"\nThe document language is: {language}"

    diacritics_text = ""
    if handle_diacritics:
        diacritics_text = """

DIACRITICS AND SPECIAL CHARACTERS:
- Preserve ALL diacritical marks exactly as written (accents, tildes, cedillas, umlauts, etc.)
- Distinguish between decorative flourishes and meaningful diacritics
- If a diacritic is ambiguous, include it with a note [?]
- Use proper Unicode characters for special marks
- Common marks: acute (á), grave (à), circumflex (â), tilde (ñ/ã), umlaut (ü), cedilla (ç)"""

    damage_text = """

DAMAGED OR UNCLEAR TEXT:
- Use [...] for completely illegible passages
- Use [word?] for uncertain readings
- Use [---] for deliberately struck-through text
- Note torn, stained, or faded areas that affect readability"""

    abbreviation_text = ""
    if script in ("latin_colonial", "latin_medieval", "secretary_hand", "gothic"):
        abbreviation_text = """

ABBREVIATIONS:
- Expand abbreviations in parentheses: e.g., "dho (dicho)", "q̃ (que)"
- Keep the abbreviated form first, expansion in parentheses
- If expansion is uncertain, mark with [?]"""

    return f"""Transcribe this historical handwritten document.

{f"SCRIPT TYPE: {script}" if script != "unknown" else "Identify the script type and adapt your reading accordingly."}
{f"ERA: {era_text}" if era_text else ""}
{language_text}

{f"SCRIPT-SPECIFIC GUIDANCE:{chr(10)}{script_text}" if script_text else ""}
{diacritics_text}
{abbreviation_text}
{damage_text}

TRANSCRIPTION RULES:
- Transcribe exactly what is written, preserving original spelling
- Maintain line breaks where clearly intended
- Preserve capitalization as written
- Include marginalia or interlinear additions in {{curly braces}}
- Note any page numbers, folio markers, or archival references

Output the transcription as plain text, preserving the document structure."""


def build_handwriting_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    script = config.get("script", "unknown")
    era = config.get("era", "unknown")
    language = config.get("language", "auto")
    handle_diacritics = config.get("handle_diacritics", True)
    return _build_prompt(script, era, language, handle_diacritics)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="handwriting",
    display_name="Handwriting",
    description="Historical handwriting transcription",
    category="vision",
    icon="pencil.and.scribble",
    color="brown",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, HANDWRITING_CONFIG),
    default_prompt=_build_prompt("unknown", "unknown", "auto", True),
    prompt_builder=build_handwriting_prompt,
    sort_order=27,
)
async def handwriting(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Transcribe historical handwriting with paleography guidance."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    script = inputs.get("script", "unknown")
    era = inputs.get("era", "unknown")
    language = inputs.get("language", "auto")
    handle_diacritics = inputs.get("handle_diacritics", True)

    prompt = inputs.get("prompt") or _build_prompt(
        script, era, language, handle_diacritics
    )

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="llm",
        force_ocr=True,
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", "text"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
    )
