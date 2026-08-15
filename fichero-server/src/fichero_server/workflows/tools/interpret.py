"""Interpret — apply an interpretive framework to text (hermeneutic layer).

The hermeneutic layer (#1124) had models, tables, CRUD, and a predicate
vocabulary — and NOTHING that wrote to it (2026-08-11 semantic-index
audit: "ghost infrastructure"). This tool is its first writer: given a
page's text and a framework, it asks the model for interpretations —
interpretive MOVES, not facts — and persists them as `Interpretation`
rows with canonicalized hermeneutic predicates, linked to the source
document. Elementwise, so it chains after transcribe and streams per page
(FICHERO_STREAM_ELEMENTWISE).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)


class _InterpretationDraft(BaseModel):
    """One interpretive move the model proposes."""

    interpretation_text: str
    act: str = "applying"
    predicate: str = ""
    key_insights: list[str] = Field(default_factory=list)
    tensions: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class _InterpretationBatch(BaseModel):
    interpretations: list[_InterpretationDraft] = Field(default_factory=list)


_SYSTEM_PROMPT = """You are a careful humanities scholar applying an \
interpretive framework to a historical document passage. Produce \
interpretations — interpretive MOVES under the framework, never bare \
facts. For each: the interpretation itself, the interpretive act \
(reading, translating, contextualizing, synthesizing, critiquing, \
applying), a short interpretive predicate (e.g. "centers", "reads as", \
"contests reading", "exposes silenced voices"), key insights, and \
tensions — places the framework strains against the evidence. Ground \
every interpretation in the passage; do not invent content."""


def _build_prompt(framework_name: str, framework_description: str, text: str) -> str:
    return (
        f"Framework: {framework_name}\n"
        f"Framework description: {framework_description}\n\n"
        f"Passage:\n{text}\n\n"
        "Apply the framework to this passage. Return 1-5 interpretations."
    )


@register_tool(
    name="interpret",
    parallelism="elementwise",
    display_name="Interpret",
    description=(
        "Apply an interpretive framework to text and persist the resulting "
        "interpretations (hermeneutic layer)"
    ),
    category="llm",
    icon="text.magnifyingglass",
    color="purple",
    input_ports=[
        PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT),
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
        ),
    ],
    output_ports=[
        PortDef(
            id="interpretations",
            name="Interpretations",
            port_type="output",
            data_type=DataType.JSON,
        ),
        PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT),
    ],
    config_schema={
        "framework_id": {
            "type": "string",
            "title": "Framework",
            "description": "InterpretiveFramework id to apply",
        },
    },
    config_defaults={"framework_id": ""},
    uses_llm=True,
    requires_generative_model=True,
    tested=True,
)
async def interpret(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Apply a framework to text; persist Interpretation rows."""
    from fichero_server.db import db_manager
    from fichero_server.knowledge._common import canonical_hermeneutic_predicate
    from fichero_server.llm import chat_structured
    from fichero_server.models.hermeneutics import (
        Interpretation,
        InterpretiveActType,
        InterpretiveFramework,
    )

    text = inputs.get("text", "")
    documents = inputs.get("documents", []) or []
    framework_id = inputs.get("framework_id", "")
    library_path = state.get("library_path", "")

    if not text:
        return {
            "interpretations": [],
            "text": "",
            "value": None,
            "error": "No text provided",
        }
    if not framework_id:
        return {
            "interpretations": [],
            "text": "",
            "value": None,
            "error": "No framework_id configured — pick a framework to apply",
        }
    if not library_path:
        return {
            "interpretations": [],
            "text": "",
            "value": None,
            "error": "No library_path in state — interpretations must persist",
        }

    db = db_manager.get_database(library_path)
    framework = db.get(InterpretiveFramework, framework_id)
    if framework is None:
        return {
            "interpretations": [],
            "text": "",
            "value": None,
            "error": f"Framework not found: {framework_id}",
        }

    batch = await chat_structured(
        prompt=_build_prompt(framework.name, framework.description, text),
        schema=_InterpretationBatch,
        config=llm_config,
        system=_SYSTEM_PROMPT,
        use_case="interpretation",
    )
    if not isinstance(batch, _InterpretationBatch):
        batch = _InterpretationBatch.model_validate(batch)

    document_id: str | None = None
    if documents and isinstance(documents[0], dict):
        document_id = documents[0].get("id")

    saved: list[dict[str, Any]] = []
    for draft in batch.interpretations:
        if not draft.interpretation_text.strip():
            continue
        try:
            act = InterpretiveActType(draft.act.strip().lower())
        except ValueError:
            act = InterpretiveActType.applying
        row = Interpretation(
            framework_id=framework.id,
            document_id=document_id,
            passage_text=text[:1000],
            interpretation_text=draft.interpretation_text,
            act=act,
            predicate=draft.predicate,
            predicate_canonical=canonical_hermeneutic_predicate(draft.predicate),
            confidence=max(0.0, min(1.0, draft.confidence)),
            key_insights=list(draft.key_insights),
            tensions=list(draft.tensions),
            created_by="model",
        )
        db.save(row)
        saved.append(row.model_dump(mode="json"))

    logger.info(
        "interpret: %d interpretation(s) under framework %s for document %s",
        len(saved), framework.name, document_id or "(none)",
    )
    summary = "\n".join(item["interpretation_text"] for item in saved)
    return {
        "interpretations": saved,
        "text": summary,
        "value": [item["id"] for item in saved],
        "count": len(saved),
    }
