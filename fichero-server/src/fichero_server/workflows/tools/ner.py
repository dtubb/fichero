"""Workflow tool exposing provider-selectable NER."""

from __future__ import annotations

from typing import Any

from fichero_server.kg.ner import ExtractedEntity
from fichero_server.llm import LLMConfig
from fichero_server.workflows.ner.providers import get_ner_provider
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State


NER_INPUT_PORTS = [
    PortDef(
        id="text",
        name="Text",
        port_type="input",
        data_type=DataType.TEXT,
        required=True,
        description="Text to analyse for named entities",
    )
]

NER_OUTPUT_PORTS = [
    PortDef(
        id="entities",
        name="Entities",
        port_type="output",
        data_type=DataType.JSON,
        description="Normalised extracted entities",
    )
]

NER_CONFIG_SCHEMA = {
    "provider": {
        "type": "string",
        "default": "llm",
        "description": "NER backend: llm, spacy, or transformers",
    },
    "model": {
        "type": "string",
        "default": "",
        "description": "Backend model name",
    },
    "language": {
        "type": "string",
        "default": "auto",
        "description": "Optional language hint",
    },
}


def _serialise_entities(entities: list[ExtractedEntity]) -> list[dict[str, Any]]:
    return [entity.model_dump(mode="json") for entity in entities]


@register_tool(
    name="ner",
    display_name="Named Entity Recognition",
    description="Extract named entities with a selectable backend provider",
    category="llm",
    icon="person.3",
    color="purple",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=False,
    input_ports=NER_INPUT_PORTS,
    output_ports=NER_OUTPUT_PORTS,
    config_schema=NER_CONFIG_SCHEMA,
    sort_order=34,
)
async def ner(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    text = inputs.get("text", "")
    if not text:
        return {
            "entities": [],
            "text": "",
            "value": [],
            "cached": False,
            "error": "No text provided",
        }

    provider_name = inputs.get("provider") or "llm"
    model_name = inputs.get("model") or None
    provider = get_ner_provider(provider_name, model_name)
    language = inputs.get("language")
    if language and str(language).lower() == "auto":
        language = None

    entities = await provider.extract(
        text,
        language=language,
        state=state,
        llm_config=llm_config,
        inputs=inputs,
    )
    serialised = _serialise_entities(entities)
    return {
        "entities": serialised,
        "text": "",
        "value": serialised,
        "texts": [],
        "values": [serialised],
        "results": [],
        "artifacts": [],
        "cached": False,
    }

