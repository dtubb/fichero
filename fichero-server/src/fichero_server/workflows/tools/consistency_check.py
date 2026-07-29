"""Deterministic transcription consistency checks."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

_FIGURE = r"[\d.,]+"
_WORD_NUMBER = re.compile(
    r"\b(?:cero|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|die[cs]is[ée]is|die[cs]isiete|die[cs]iocho|die[cs]inueve|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|doscientos?|trescientos?|cuatrocientos?|quinientos?|seiscientos?|setecientos?|ochocientos?|novecientos?|mil|y)(?:\s+(?:cero|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|die[cs]is[ée]is|die[cs]isiete|die[cs]iocho|die[cs]inueve|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|doscientos?|trescientos?|cuatrocientos?|quinientos?|seiscientos?|setecientos?|ochocientos?|novecientos?|mil|y))*\b",
    re.IGNORECASE,
)
_NAMES = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)\b")
_NUMBER_WORDS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300,
    "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500, "quinientas": 500,
    "seiscientos": 600, "seiscientas": 600, "setecientos": 700, "setecientas": 700,
    "ochocientos": 800, "ochocientas": 800, "novecientos": 900, "novecientas": 900,
}


def _figure(value: str) -> int:
    return int(value.replace(".", "").replace(",", ""))


def _word_number(value: str) -> int | None:
    total = current = 0
    for word in unicodedata.normalize("NFKD", value.lower()).encode("ascii", "ignore").decode().split():
        if word == "y":
            continue
        if word.startswith("veinti"):
            current += 20 + _NUMBER_WORDS.get(word[6:], 0)
        elif word == "mil":
            total += max(1, current) * 1000
            current = 0
        elif word in _NUMBER_WORDS:
            current += _NUMBER_WORDS[word]
        else:
            return None
    return total + current


def _normalise_name(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()


def find_inconsistencies(text: str, *, check_formula_completeness: bool = False) -> list[dict[str, str]]:
    """Return deterministic numeric, name, and optional formula warnings."""
    flags: list[dict[str, str]] = []
    for match in re.finditer(rf"({_FIGURE})\s*[x×]\s*({_FIGURE})\s*=\s*({_FIGURE})", text):
        left, right, stated = map(_figure, match.groups())
        if left * right != stated:
            flags.append({"type": "numeral", "message": f"{match.group(0)}: expected {left * right}"})
    for match in re.finditer(rf"({_WORD_NUMBER.pattern})\s*(?:por|x|×)\s*({_FIGURE})\s*=\s*({_FIGURE})", text, re.IGNORECASE):
        word_value = _word_number(match.group(1))
        factor, stated = _figure(match.group(2)), _figure(match.group(3))
        if word_value is not None and word_value * factor != stated:
            flags.append({"type": "numeral", "message": f"{match.group(0)}: expected {word_value * factor}"})

    names = list(dict.fromkeys(_NAMES.findall(text)))
    for index, name in enumerate(names):
        first, *surname = name.split()
        for other in names[index + 1:]:
            other_first, *other_surname = other.split()
            if _normalise_name(first) == _normalise_name(other_first) and surname != other_surname:
                if SequenceMatcher(None, _normalise_name(" ".join(surname)), _normalise_name(" ".join(other_surname))).ratio() >= 0.75:
                    flags.append({"type": "name", "message": f"Possible inconsistent name spelling: {name} / {other}"})

    if check_formula_completeness:
        lowered = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
        for marker in ("ante mi", "otorga", "doy fe"):
            if marker not in lowered:
                flags.append({"type": "formula", "message": f"Missing notarial formula marker: {marker}"})
    return flags


@register_tool(
    name="consistency-check", display_name="Consistency Check",
    description="Flag deterministic numeral, name, and formula inconsistencies.",
    category="transform", icon="checklist", color="orange", uses_llm=False, supports_batch=True,
    input_ports=[
        PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT, required=False),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False),
    ],
    output_ports=[PortDef(id="inconsistencies", name="Inconsistencies", port_type="output", data_type=DataType.JSON)],
    config_schema={"check_formula_completeness": {"type": "boolean", "default": False}}, sort_order=28,
)
async def consistency_check(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    """Check transcription text without invoking an LLM."""
    text = str(inputs.get("text") or state.get("text") or "")
    flags = find_inconsistencies(text, check_formula_completeness=bool(inputs.get("check_formula_completeness")))
    return {"inconsistencies": flags, "count": len(flags), "error": None}
