"""
Classify Script Tool

Classifies a document's script/handwriting type:
  typescript   — typewritten, printed, or digital text
  manuscript   — modern handwriting (20th–21st century)
  htr          — historical handwriting (pre-20th century)
  paleography  — archaic script with non-standard letterforms (pre-18th century)

Returns:
  script_type        — one of the four types above
  confidence         — 0.0–1.0 model confidence
  needs_human_selection — True when confidence < 0.6 (explicit human-in-the-loop signal)
  notes              — brief explanation from the model

Used by the Transcribe (Auto-Detect) workflow to route to the right profile.
"""

from __future__ import annotations

import json
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

SCRIPT_TYPES = ["typescript", "manuscript", "htr", "paleography"]

CONFIDENCE_THRESHOLD = 0.6

TOOL_CONFIG = VisionToolConfig(
    artifact_type="script_classification",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="script_type",
)

CLASSIFY_SCRIPT_CONFIG = {
    "confidence_threshold": {
        "type": "number",
        "default": CONFIDENCE_THRESHOLD,
        "description": (
            "Confidence below which needs_human_selection is True "
            "(0.0–1.0, default 0.6)"
        ),
    },
}

_PROMPT = """Examine this document image and classify its script/handwriting type.

Choose EXACTLY ONE type from:
- typescript   : typewritten, printed, or born-digital text (no handwriting)
- manuscript   : modern handwriting, 20th–21st century (cursive or print)
- htr          : historical handwriting, 16th–19th century (legible but archaic letterforms)
- paleography  : archaic script with non-standard letterforms, heavy abbreviation, or
                 specialist scribal conventions (pre-18th century or highly specialised)

Return a JSON object with exactly these fields:
{
  "script_type": "<one of the four types>",
  "confidence": <float 0.0–1.0>,
  "notes": "<one sentence explaining the classification>"
}

Be conservative: if the image is ambiguous between htr and paleography, pick the harder
category (paleography) and lower your confidence. Only mark typescript when there is
clearly no handwriting. Do not add any text outside the JSON object."""


@register_tool(
    name="classify_script",
    parallelism="elementwise",
    display_name="Classify Script Type",
    description="Detect whether a document is typescript, manuscript, HTR, or paleography",
    category="vision",
    icon="doc.text.magnifyingglass",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, CLASSIFY_SCRIPT_CONFIG),
    config_defaults={
        "vision_mode": "llm",
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "save_to_db": True,
    },
    default_prompt=_PROMPT,
    sort_order=5,
)
async def classify_script(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Classify the script type of document images."""
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    threshold = float(inputs.get("confidence_threshold", CONFIDENCE_THRESHOLD))

    raw = await process_vision(
        files=files,
        documents=documents,
        prompt=_PROMPT,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode=inputs.get("vision_mode", "llm"),
        language=inputs.get("language", "en"),
        max_image_dimension=inputs.get("max_image_dimension", 2048),
        force_ocr=True,
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format="json",
        output_options={},
        reference_values=None,
        match_mode="prefer",
        context=inputs.get("context"),
        input_metadata=inputs.get("metadata"),
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=False,
        metadata_field="script_type",
    )

    # Parse and enrich results per document
    results = raw.get("results") or []
    enriched: list[dict] = []

    for item in results:
        text = (item.get("text") or "").strip()
        parsed: dict = {}
        try:
            # Strip markdown fences if present
            content = text
            if content.startswith("```"):
                lines = content.splitlines()
                content = "\n".join(
                    ln for ln in lines
                    if not ln.strip().startswith("```")
                ).strip()
            parsed = json.loads(content)
        except Exception:
            logger.warning(
                "classify_script: could not parse JSON from model output for %s",
                item.get("file")
                or item.get("document_id")
                or item.get("artifact_id")
                or "<unknown>",
            )

        script_type = parsed.get("script_type", "")
        if script_type not in SCRIPT_TYPES:
            script_type = "manuscript"  # safe fallback
        confidence = float(parsed.get("confidence", 0.0))
        notes = parsed.get("notes", "")
        needs_human = confidence < threshold

        enriched.append({
            **{
                key: item[key]
                for key in ("file", "document_id", "artifact_id")
                if key in item
            },
            "script_type": script_type,
            "confidence": confidence,
            "needs_human_selection": needs_human,
            "notes": notes,
        })

    # Determine top-level script_type: uniform batches keep their type;
    # mixed batches surface "mixed" so the router can handle them explicitly
    # rather than silently collapsing multiple types to one. #2237
    distinct_types = {item["script_type"] for item in enriched} if enriched else set()
    if len(distinct_types) == 1:
        # Uniform batch — use that type and its maximum confidence
        top_type = next(iter(distinct_types))
        top_confidence = max(item["confidence"] for item in enriched)
    elif len(distinct_types) > 1:
        # Mixed batch — surface "mixed" so downstream routing does not silently
        # apply one branch to all items. Confidence is the max across the batch.
        top_type = "mixed"
        top_confidence = max(item["confidence"] for item in enriched)
    else:
        # Empty batch
        top_type = "manuscript"
        top_confidence = 0.0

    needs_human_selection = top_confidence < threshold or top_type == "mixed"

    if needs_human_selection:
        logger.info(
            "classify_script: script_type=%r confidence=%.2f — needs_human_selection=True",
            top_type, top_confidence,
        )

    return {
        **raw,
        "script_type": top_type,
        "confidence": top_confidence,
        "needs_human_selection": needs_human_selection,
        "results": enriched,
        "value": {
            "script_type": top_type,
            "confidence": top_confidence,
            "needs_human_selection": needs_human_selection,
            "profiles": enriched,
        },
    }
