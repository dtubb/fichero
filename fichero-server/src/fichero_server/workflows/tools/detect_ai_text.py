"""Detect AI-generated text likelihood (heuristic local classifier).

This is a local-first fallback for #753. It does not depend on external
model files and provides a stable workflow-tool surface so higher-fidelity
backends can be swapped in later without changing workflow graphs.
"""

from __future__ import annotations

import re
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

_INPUT_PORTS = [
    PortDef(
        id="text",
        name="Text",
        port_type="input",
        data_type=DataType.TEXT,
        required=True,
        description="Text to classify",
    )
]

_OUTPUT_PORTS = [
    PortDef(
        id="analysis",
        name="Analysis",
        port_type="output",
        data_type=DataType.JSON,
        description="AI-text likelihood report",
    )
]

_CONFIG_SCHEMA = {
    "threshold": {
        "type": "number",
        "default": 0.55,
        "description": "Score threshold above which text is flagged as likely AI",
    },
}


def _score_text(text: str) -> tuple[float, dict[str, Any]]:
    words = re.findall(r"\b\w+\b", text)
    n_words = len(words)
    n_chars = len(text)
    if n_words == 0:
        return 0.0, {"word_count": 0, "char_count": n_chars}

    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    n_sent = max(len(sentences), 1)
    avg_sentence_words = n_words / n_sent

    unique_ratio = len({w.lower() for w in words}) / n_words
    repeated_bigrams = 0
    seen_bigrams: set[tuple[str, str]] = set()
    for i in range(len(words) - 1):
        bg = (words[i].lower(), words[i + 1].lower())
        if bg in seen_bigrams:
            repeated_bigrams += 1
        seen_bigrams.add(bg)

    punctuation_density = sum(ch in ",;:-()[]" for ch in text) / max(n_chars, 1)

    score = 0.0
    if avg_sentence_words > 22:
        score += 0.2
    if unique_ratio < 0.55:
        score += 0.25
    if repeated_bigrams >= 3:
        score += 0.2
    if punctuation_density > 0.06:
        score += 0.1
    if n_words > 250:
        score += 0.1
    if "as an ai" in text.lower() or "in conclusion" in text.lower():
        score += 0.2

    return min(score, 1.0), {
        "word_count": n_words,
        "sentence_count": n_sent,
        "avg_sentence_words": round(avg_sentence_words, 2),
        "unique_ratio": round(unique_ratio, 3),
        "repeated_bigrams": repeated_bigrams,
        "punctuation_density": round(punctuation_density, 4),
    }


@register_tool(
    name="detect_ai_text",
    display_name="Detect AI Text",
    description="Estimate likelihood that text is AI-generated",
    category="llm",
    icon="sparkles",
    color="orange",
    uses_llm=False,
    supports_batch=False,
    supports_structured_output=False,
    input_ports=_INPUT_PORTS,
    output_ports=_OUTPUT_PORTS,
    config_schema=_CONFIG_SCHEMA,
    sort_order=37,
)
async def detect_ai_text(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    del state, llm_config
    text = str(inputs.get("text") or "")
    threshold = float(inputs.get("threshold", 0.55))

    score, features = _score_text(text)
    verdict = "likely_ai" if score >= threshold else "likely_human"

    payload = {
        "score": round(score, 3),
        "threshold": threshold,
        "verdict": verdict,
        "features": features,
        "model": "heuristic-v1",
    }

    return {
        "analysis": payload,
        "text": "",
        "value": payload,
        "cached": False,
    }
