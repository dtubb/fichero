"""Regression: spaCy NER provider/model must be configurable on extraction nodes (#1333)."""

from __future__ import annotations

import fichero_server.workflows.tools  # noqa: F401
from fichero_server.workflows.registry import TOOL_DEFS


def _assert_has_ner_config(tool_name: str) -> None:
    schema = TOOL_DEFS[tool_name].config_schema
    assert "ner_provider" in schema
    assert "ner_model" in schema
    assert schema["ner_provider"].get("default") == "spacy"


def test_extract_all_exposes_ner_provider_and_model() -> None:
    _assert_has_ner_config("extract_all")


def test_section_extractors_expose_ner_provider_and_model() -> None:
    for tool_name in (
        "people_extract",
        "places_extract",
        "organizations_extract",
        "events_extract",
    ):
        _assert_has_ner_config(tool_name)
