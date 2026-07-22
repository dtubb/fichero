"""Geo-extraction tool (#2266).

Pulls place names out of a document's text with an LLM, then geocodes each
to lat/lon via ``fichero.media.geo`` so the result can drive the 2D world-map and
3D globe representations (#2264). Modelled on ``entities.py`` — the only
net-new step is the geocode pass over the extracted place list.

The geocoded points are returned on the ``geo`` output port AND stitched into
the document's ``metadata['geo_points']`` so the list-doc-geo endpoint (and the
existing ``_metadata_has_geo`` map-lens detector) can find them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
    process_text,
    parse_output,
)
from fichero.llm import LLMConfig
from fichero.media import geo

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="geo",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="geo_points",
)

GEO_CONFIG = {
    "online_geocoding": {
        "type": "boolean",
        "default": False,
        "description": "Fall through to Nominatim for places the offline gazetteer misses",
    },
}

GEO_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to extract place names from",
        )
    ],
    BASE_INPUT_PORTS,
)

GEO_OUTPUT_PORTS = merge_ports(
    [
        PortDef(
            id="geo",
            name="Geo Points",
            port_type="output",
            data_type=DataType.JSON,
            description="Geocoded place points (lat/lon)",
        )
    ],
    BASE_OUTPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================

def _build_geo_prompt() -> str:
    return """Extract every geographic place mentioned in the following text:
cities, towns, regions, countries, and named geographic features.

Return only valid JSON — a flat array of distinct place-name strings, no other
text. Use the most specific, canonical spelling for each place.
Example:
["Popayán", "Quito", "Madrid"]"""


def build_geo_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    return _build_geo_prompt()


def _coerce_place_names(value: Any) -> list[str]:
    """Pull a flat list of place-name strings out of whatever the LLM returned."""
    if isinstance(value, str):
        value = parse_output(value, "json") or []
    names: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("place") or item.get("value")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    elif isinstance(value, dict):
        # Tolerate {"places": [...]} / {"locations": [...]} shapes.
        for key in ("places", "locations", "geo"):
            if isinstance(value.get(key), list):
                return _coerce_place_names(value[key])
    return names


# =============================================================================
# Tool Registration
# =============================================================================

@register_tool(
    name="extract_geo",
    display_name="Extract Geo",
    description="Extract place names from text and geocode them to lat/lon",
    category="llm",
    icon="map",
    color="green",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=GEO_INPUT_PORTS,
    output_ports=GEO_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, GEO_CONFIG),
    default_prompt=_build_geo_prompt(),
    prompt_builder=build_geo_prompt,
    sort_order=34,
)
async def extract_geo(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract place names from text, then geocode them to points."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")
    online = bool(inputs.get("online_geocoding", False))

    if not text:
        return {
            "geo": [],
            "text": "",
            "value": [],
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No text provided",
        }

    prompt = inputs.get("prompt") or _build_geo_prompt()

    result = await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format="json",
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "geo_points",
    )

    names = _coerce_place_names(result.get("value"))
    points = geo.geocode_places(names, online=online)

    geo_points = [
        {
            "place_name": name,
            "lat": point.lat,
            "lon": point.lon,
            "precision_m": point.precision_m,
        }
        for name, point in points.items()
    ]
    unresolved = [n for n in names if n not in points]
    if unresolved:
        logger.info("extract_geo: %d place(s) did not geocode: %s", len(unresolved), unresolved)

    return {
        "geo": geo_points,
        "text": json.dumps(geo_points),
        "value": geo_points,
        "texts": result.get("texts", []),
        "values": [geo_points],
        "results": result.get("results", []),
        "artifacts": result.get("artifacts", []),
        "places": names,
        "unresolved": unresolved,
        "error": result.get("error"),
    }
