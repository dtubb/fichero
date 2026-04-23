"""
Catalogue Tool

Generates a structured archival catalogue entry for a folder of documents,
producing a rich nine-section output matching the reference format in the
Archivo Judicial de Medellín catalogue.docx exemplars.

Contract:
- Expects aggregated `text` input (from upstream Transcribe → implicit aggregate).
- Reads `state.selected_doc_ids` to determine the container (folder) on which
  to save the final artifact. If the selection is a single folder doc, save
  there. If it's a list of file docs sharing a parent, save on the parent.
- Produces one Artifact on the container doc with type="catalogue", containing:
    - content: markdown rendering of the nine sections (human-readable)
    - data:    parsed JSON matching the nine-section schema
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
)
from fichero.llm import LLMConfig, chat
from fichero.db import db_manager
from fichero.models import Document, DocType, Artifact

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="catalogue",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field=None,
)

CATALOGUE_CONFIG = {
    "output_language": {
        "type": "string",
        "default": "Spanish",
        "description": "Output language for catalogue narrative fields",
        "x-group": "primary",
    },
}

CATALOGUE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Aggregated transcription text from upstream step",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt (ported from legacy Catalogue (English).jsonl)
# =============================================================================

_CATALOGUE_SCHEMA = """{
  "resumen": "string — narrative summary, 150-300 words in {output_language}",
  "palabras_clave": ["keyword1", "keyword2", "..."],
  "personas_clave": [
    {"nombre": "...", "contexto": "role and importance in {output_language}"}
  ],
  "fechas": [
    {"fecha": "as written", "fecha_normalizada": "YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD", "contexto": "..."}
  ],
  "referencias_legales": [
    {"nombre": "...", "contexto": "..."}
  ],
  "rios": [
    {"nombre": "...", "ortografias_alternativas": ["..."], "contexto": "..."}
  ],
  "eventos_clave": [
    {"evento": "...", "contexto": "..."}
  ],
  "minas": [
    {"nombre": "...", "contexto": "..."}
  ],
  "propiedades": [
    {"nombre": "...", "contexto": "..."}
  ]
}"""


def _build_prompt(output_language: str) -> str:
    """Build the catalogue prompt.

    Produces a rich nine-section archival catalogue entry from aggregated
    transcriptions. Schema matches the reference .docx format used for the
    Archivo Judicial de Medellín catalogue.
    """
    schema = _CATALOGUE_SCHEMA.replace("{output_language}", output_language)
    return f"""You are cataloguing a collection of archival documents. You receive
the aggregated transcriptions (possibly across many pages or files).

Produce a structured catalogue entry in {output_language} with these sections:

1. **Resumen** — a 150-300 word narrative summary of what the collection contains:
   the subject, dates, key actors, central events, outcomes. Write in paragraph
   form, not bullets.

2. **Palabras Clave** — 10-20 descriptive keywords capturing themes, subjects,
   locations, time periods, legal concepts. Return as an array of short strings.

3. **Personas Clave** — 5-15 most important people. For each: canonical name,
   role/importance in the case.

4. **Fechas** — every significant date mentioned. For each: the date as written
   in the original (with ambiguity if any), normalized to YYYY-MM-DD (or
   YYYY-MM-DD/YYYY-MM-DD for ranges, YYYY-MM for month-only), short context.

5. **Referencias Legales** — every law, article, decree, statute cited. Name +
   context of how it's invoked.

6. **Rios** — every river, waterway, tributary mentioned. Canonical name,
   alternative spellings found in the documents, context.

7. **Eventos Clave** — significant events (incidents, decisions, hearings,
   meetings, deaths, financial transactions). Event description + context.

8. **Minas** — every mine, mining company, mining claim mentioned. Name + context.

9. **Propiedades** — every property, estate, parcel, building mentioned beyond
   rivers and mines. Name + context.

Rules:
- Include ALL occurrences. Do not include page numbers in outputs.
- Preserve exact spelling of names but capitalize properly. Group alternative
  spellings under the canonical (most complete) form.
- Only include facts supported by the text. Do not speculate.
- Write all prose ({output_language}). Keep dates in ISO format.
- Omit a section only if the text contains zero examples of it.

Return ONLY valid JSON matching this schema. No prose outside the JSON:

{schema}
"""


def build_catalogue_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    output_language = config.get("output_language", "Spanish")
    return _build_prompt(output_language)


# =============================================================================
# Rendering helpers
# =============================================================================


def _render_markdown(data: dict[str, Any]) -> str:
    """Render the nine-section JSON as a human-readable markdown document.

    Mirrors the structure of the reference .docx so researchers see something
    familiar. Sections with no content are skipped.
    """
    lines: list[str] = []

    if resumen := data.get("resumen"):
        lines.append("## Resumen\n")
        lines.append(str(resumen))
        lines.append("")

    if keywords := data.get("palabras_clave"):
        lines.append("## Palabras Clave\n")
        if isinstance(keywords, list):
            lines.append("; ".join(str(k) for k in keywords))
        else:
            lines.append(str(keywords))
        lines.append("")

    def _table(section_key: str, title: str, columns: list[tuple[str, str]]) -> None:
        items = data.get(section_key) or []
        if not items:
            return
        lines.append(f"## {title}\n")
        lines.append("| " + " | ".join(c[1] for c in columns) + " |")
        lines.append("|" + "|".join(["---"] * len(columns)) + "|")
        for item in items:
            if not isinstance(item, dict):
                continue
            row = []
            for key, _ in columns:
                val = item.get(key, "")
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                row.append(str(val).replace("|", "\\|").replace("\n", " "))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    _table("personas_clave", "Personas Clave", [("nombre", "Nombre"), ("contexto", "Contexto")])
    _table(
        "fechas",
        "Fechas",
        [("fecha", "Fecha"), ("fecha_normalizada", "Fecha Normalizada"), ("contexto", "Contexto")],
    )
    _table(
        "referencias_legales",
        "Referencias Legales",
        [("nombre", "Nombre"), ("contexto", "Contexto")],
    )
    _table(
        "rios",
        "Ríos",
        [
            ("nombre", "Nombre"),
            ("ortografias_alternativas", "Ortografías Alternativas"),
            ("contexto", "Contexto"),
        ],
    )
    _table("eventos_clave", "Eventos Clave", [("evento", "Evento"), ("contexto", "Contexto")])
    _table("minas", "Minas", [("nombre", "Nombre"), ("contexto", "Contexto")])
    _table("propiedades", "Propiedades", [("nombre", "Nombre"), ("contexto", "Contexto")])

    return "\n".join(lines).strip()


def _resolve_container_doc(
    selected_doc_ids: list[str], library_path: str
) -> Document | None:
    """Determine which document should receive the catalogue artifact.

    Priority:
    1. If exactly one doc is a folder/group, use it.
    2. If all docs share a common parent_id, use that parent.
    3. Otherwise, use the first folder found among the selection or its parents.
    """
    if not selected_doc_ids or not library_path:
        return None

    db = db_manager.get_database(library_path)
    docs = [db.get(Document, did) for did in selected_doc_ids]
    docs = [d for d in docs if d is not None]
    if not docs:
        return None

    folders = [d for d in docs if d.doc_type == DocType.folder]
    if len(folders) == 1:
        return folders[0]

    parent_ids = {d.parent_id for d in docs if d.parent_id}
    if len(parent_ids) == 1:
        parent_id = next(iter(parent_ids))
        if parent := db.get(Document, parent_id):
            return parent

    # Fallback: return the first folder in selection, else the first doc's parent
    if folders:
        return folders[0]
    if docs[0].parent_id:
        return db.get(Document, docs[0].parent_id)
    return docs[0]


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="catalogue",
    display_name="Catalogue",
    description="Generate nine-section archival catalogue entry for a folder",
    category="llm",
    icon="books.vertical",
    color="brown",
    uses_llm=True,
    supports_batch=False,
    supports_structured_output=True,
    input_ports=CATALOGUE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, CATALOGUE_CONFIG),
    default_prompt=_build_prompt("Spanish"),
    prompt_builder=build_catalogue_prompt,
    sort_order=9,
)
async def catalogue(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate nine-section catalogue for the container of processed files.

    Runs a single LLM call with the aggregated transcription text. Saves the
    result as a catalogue Artifact on the container document (folder).
    """
    text = inputs.get("text", "")
    if not text:
        logger.warning("Catalogue: no text input; nothing to catalogue")
        return {
            "text": "",
            "value": None,
            "error": "No aggregated text provided to catalogue tool",
        }

    output_language = inputs.get("output_language", "Spanish")
    prompt = inputs.get("prompt") or _build_prompt(output_language)

    full_prompt = f"{prompt}\n\n---\nSource transcriptions:\n\n{text}"

    logger.info(f"Catalogue: running on {len(text)} chars in {output_language}")

    try:
        response = await chat(
            [{"role": "user", "content": full_prompt}],
            config=llm_config,
        )
    except Exception as exc:
        logger.error(f"Catalogue LLM call failed: {exc}")
        return {"text": "", "value": None, "error": str(exc)}

    # Parse structured JSON. Models sometimes wrap in ```json fences.
    raw = response.strip()
    if raw.startswith("```"):
        # Strip the first fence line and any trailing fence
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    data: dict[str, Any] | None = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(f"Catalogue: JSON parse failed ({exc}); saving raw text")

    markdown = _render_markdown(data) if data else response

    # Save artifact on the container document.
    library_path = state.get("library_path", "")
    selected_doc_ids = state.get("selected_doc_ids") or []
    artifact_id: str | None = None

    container = _resolve_container_doc(selected_doc_ids, library_path)
    if container and library_path:
        try:
            db = db_manager.get_database(library_path)
            artifact = Artifact(
                document_id=container.id,
                artifact_type="catalogue",
                content=markdown,
                data=data,
                provider=getattr(llm_config, "provider", None),
                model=getattr(llm_config, "model", None),
                run_id=state.get("task_id"),
            )
            db.save(artifact)
            artifact_id = artifact.id
            logger.info(
                f"Catalogue: saved artifact {artifact_id} on container {container.id} ({container.name})"
            )
        except Exception as exc:
            logger.error(f"Catalogue: failed to save artifact: {exc}")
    else:
        logger.warning(
            "Catalogue: no container doc resolved (selected_doc_ids=%s); artifact not saved",
            selected_doc_ids,
        )

    return {
        "text": markdown,
        "value": data,
        "results": [{"data": data, "markdown": markdown}],
        "artifacts": [artifact_id] if artifact_id else [],
        "container_id": container.id if container else None,
    }
