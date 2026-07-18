"""Coverage for built-in workflow registry definitions."""

from fichero.workflows.registry_builtins import _register_builtin_tools


def test_builtin_registry_populates_core_source_transform_and_sink_tools():
    definitions = {}
    _register_builtin_tools(definitions)

    assert {"files", "collection", "search"} <= definitions.keys()
    assert {"transcribe", "analyze", "enhance"} <= definitions.keys()
    assert {"save_to_library", "export"} <= definitions.keys()
    assert definitions["files"].input_ports == []
    assert definitions["export"].output_ports == []
    assert definitions["search"].config_schema["properties"]["limit"]["default"] == 100
