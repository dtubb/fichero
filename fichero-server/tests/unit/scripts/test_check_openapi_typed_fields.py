from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_openapi_typed_fields.py"
_SPEC = importlib.util.spec_from_file_location("check_openapi_typed_fields", _SCRIPT)
assert _SPEC and _SPEC.loader
check_openapi_typed_fields = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check_openapi_typed_fields
_SPEC.loader.exec_module(check_openapi_typed_fields)  # type: ignore[attr-defined]


def _schema_properties() -> dict[str, set[str]]:
    return {
        "ConversationUpdate": {"title", "folder_path"},
        "SavedSearchUpdate": {"query", "filters", "folder_path"},
        "WorkflowRequest": {"name", "inputs"},
    }


def test_scan_source_flags_declared_fields_in_direct_schema_additional_properties():
    offenders = check_openapi_typed_fields.scan_source(
        """
let request = Components.Schemas.ConversationUpdate(
    additionalProperties: OpenAPIObjectContainer(value: [
        "title": title,
        "folder_path": folderPath,
        "custom": customValue,
    ])
)
""",
        "fichero/fichero/Services/ConversationServiceGenerated.swift",
        _schema_properties(),
    )

    assert {(offender.schema, offender.key) for offender in offenders} == {
        ("ConversationUpdate", "folder_path"),
        ("ConversationUpdate", "title"),
    }


def test_scan_source_flags_declared_fields_in_nearby_payload_variable():
    offenders = check_openapi_typed_fields.scan_source(
        """
let payload = OpenAPIObjectContainer(value: [
    "query": query,
    "folder_path": folderPath,
    "unknown": value,
])
let request = Components.Schemas.SavedSearchUpdate(additionalProperties: payload)
""",
        "fichero/fichero/Services/SearchServiceGenerated.swift",
        _schema_properties(),
    )

    assert {(offender.schema, offender.key) for offender in offenders} == {
        ("SavedSearchUpdate", "folder_path"),
        ("SavedSearchUpdate", "query"),
    }


def test_scan_source_flags_shorthand_init_when_type_annotation_names_schema():
    offenders = check_openapi_typed_fields.scan_source(
        """
let request: Components.Schemas.ConversationUpdate = .init(
    additionalProperties: [
        "title": title
    ]
)
""",
        "fichero/fichero/Services/ConversationServiceGenerated.swift",
        _schema_properties(),
    )

    assert [(offender.schema, offender.key) for offender in offenders] == [
        ("ConversationUpdate", "title")
    ]


def test_scan_source_allows_dynamic_map_schemas_even_when_keys_overlap_parent_fields():
    offenders = check_openapi_typed_fields.scan_source(
        """
let filtersPayload = Components.Schemas.SavedSearchUpdate.FiltersPayload(
    additionalProperties: OpenAPIObjectContainer(value: [
        "query": query,
        "folder_path": folderPath,
    ])
)
let inputsPayload = Components.Schemas.WorkflowRequest.InputsPayload(
    additionalProperties: OpenAPIObjectContainer(value: [
        "name": "dynamic input"
    ])
)
""",
        "fichero/fichero/Services/SearchServiceGenerated.swift",
        _schema_properties(),
    )

    assert offenders == []


def test_scan_source_allows_unknown_dynamic_keys_on_typed_schema():
    offenders = check_openapi_typed_fields.scan_source(
        """
let request = Components.Schemas.ConversationUpdate(
    additionalProperties: OpenAPIObjectContainer(value: [
        "plugin_value": value
    ])
)
""",
        "fichero/fichero/Services/ConversationServiceGenerated.swift",
        _schema_properties(),
    )

    assert offenders == []


def test_main_returns_nonzero_and_prints_offender_location(monkeypatch, capsys, tmp_path):
    schema_path = tmp_path / "fichero-server" / "tests" / "contracts" / "openapi.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(
        json.dumps(
            {
                "components": {
                    "schemas": {
                        "ConversationUpdate": {
                            "properties": {
                                "title": {"type": "string"},
                                "folder_path": {"type": "string"},
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    service = tmp_path / "fichero" / "fichero" / "Services" / "ConversationServiceGenerated.swift"
    service.parent.mkdir(parents=True)
    service.write_text(
        """
let request = Components.Schemas.ConversationUpdate(
    additionalProperties: OpenAPIObjectContainer(value: [
        "title": title
    ])
)
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_openapi_typed_fields, "ROOT", tmp_path)
    monkeypatch.setattr(check_openapi_typed_fields, "OPENAPI_SCHEMA", schema_path)
    monkeypatch.setattr(check_openapi_typed_fields, "SWIFT_SERVICES", service.parent)
    monkeypatch.setattr(
        check_openapi_typed_fields.sys,
        "argv",
        ["check_openapi_typed_fields.py"],
    )

    assert check_openapi_typed_fields.main() == 1
    output = capsys.readouterr().out
    assert "OpenAPI typed-field guardrail" in output
    assert "fichero/fichero/Services/ConversationServiceGenerated.swift:2" in output
    assert "declared field 'title'" in output


def test_main_returns_zero_when_current_code_is_clean(monkeypatch):
    monkeypatch.setattr(check_openapi_typed_fields, "scan", lambda: [])
    monkeypatch.setattr(
        check_openapi_typed_fields.sys,
        "argv",
        ["check_openapi_typed_fields.py"],
    )

    assert check_openapi_typed_fields.main() == 0
