#!/usr/bin/env python3
"""
Validate that Python Pydantic models and Swift types are in sync.

This script compares field definitions between:
- Python: fichero-server/src/fichero_server/workflows/types.py
- Swift: fichero/fichero/Models/WorkflowTypes.swift

Run this before launching the backend to catch model drift early.
"""

import ast
import re
import sys
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FieldInfo:
    name: str
    type_hint: str
    optional: bool = False
    has_default: bool = False


@dataclass
class ModelInfo:
    name: str
    fields: dict[str, FieldInfo]


# Mapping from Python field names to Swift field names (snake_case to camelCase)
PYTHON_TO_SWIFT_FIELD = {
    "input_ports": "inputPorts",
    "output_ports": "outputPorts",
    "input_mappings": "inputMappings",
    "output_schema": "outputSchema",
    "position_x": "positionX",
    "position_y": "positionY",
    "provider_name": "providerName",
    "model_name": "modelName",
    "uses_llm": "usesLLM",
    "port_type": "portType",
    "data_type": "dataType",
    "display_name": "displayName",
    "config_schema": "configSchema",
    "default_output_schema": "defaultOutputSchema",
    "default_prompt": "defaultPrompt",
    "supports_batch": "supportsBatch",
    "supports_streaming": "supportsStreaming",
    "supports_structured_output": "supportsStructuredOutput",
    "sort_order": "sortOrder",
    "source_path": "sourcePath",
    "port_id": "portId",
    "json_schema": "jsonSchema",
    "timeout_seconds": "timeoutSeconds",
    "max_retries": "maxRetries",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "folder_path": "folderPath",
    # EdgeDef uses source/target in Python, but Swift uses sourceNodeId/targetNodeId for UI
    "source": "sourceNodeId",
    "target": "targetNodeId",
    "source_port": "sourcePortId",
    "target_port": "targetPortId",
    # PortDef uses 'default' in Python, Swift uses 'defaultValue' to avoid keyword
    "default": "defaultValue",
}

# Models to compare (Python name -> Swift name)
MODELS_TO_CHECK = {
    "NodeDef": "WorkflowNode",
    "EdgeDef": "WorkflowEdge",
    "WorkflowDef": "WorkflowDefinition",
    "PortDef": "PortInfo",
    "ToolDef": "ToolInfo",
    "InputMapping": "InputMapping",
    "OutputSchema": "OutputSchema",
}

# Fields to ignore (internal implementation details)
IGNORED_FIELDS = {
    "NodeDef": {"prompt_builder"},  # Runtime-only, not serialized
    "ToolDef": {"prompt_builder"},  # Runtime-only, not serialized
    "WorkflowDef": {},
    "EdgeDef": {},
    "PortDef": {},
    "InputMapping": {},
    "OutputSchema": {},
}


def parse_python_models(python_file: Path) -> dict[str, ModelInfo]:
    """Parse Pydantic model definitions from Python file."""
    with open(python_file) as f:
        source = f.read()

    tree = ast.parse(source)
    models = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it's a Pydantic model (inherits from BaseModel)
            is_pydantic = any(
                (isinstance(base, ast.Name) and base.id == "BaseModel") or
                (isinstance(base, ast.Attribute) and base.attr == "BaseModel")
                for base in node.bases
            )

            if not is_pydantic:
                continue

            fields = {}
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    if field_name.startswith("_"):
                        continue

                    # Get type annotation as string
                    type_hint = ast.unparse(item.annotation) if item.annotation else "Any"

                    # Check if optional (has None in union or has default)
                    optional = "None" in type_hint or "| None" in type_hint
                    has_default = item.value is not None

                    fields[field_name] = FieldInfo(
                        name=field_name,
                        type_hint=type_hint,
                        optional=optional or has_default,
                        has_default=has_default,
                    )

            if fields:
                models[node.name] = ModelInfo(name=node.name, fields=fields)

    return models


def parse_swift_models(swift_files: list[Path]) -> dict[str, ModelInfo]:
    """Parse struct definitions from one or more Swift files."""
    models = {}
    for swift_file in swift_files:
        with open(swift_file) as f:
            source = f.read()

        # Find all struct declarations and their starting positions
        struct_starts = []
        for match in re.finditer(r"struct\s+(\w+)\s*:", source):
            struct_starts.append((match.start(), match.group(1)))

        for i, (start_pos, struct_name) in enumerate(struct_starts):
            # Find the opening brace
            brace_pos = source.find("{", start_pos)
            if brace_pos == -1:
                continue

            # Find matching closing brace by counting braces
            depth = 1
            pos = brace_pos + 1
            while pos < len(source) and depth > 0:
                if source[pos] == "{":
                    depth += 1
                elif source[pos] == "}":
                    depth -= 1
                pos += 1

            struct_body = source[brace_pos + 1 : pos - 1]
            fields = {}

            # Match property declarations (let/var name: Type)
            # Be careful to stop at = or newline, and handle array types with []
            prop_pattern = r"(?:let|var)\s+(\w+)\s*:\s*([^\n={}]+?)(?:\s*=|\s*$|\n)"

            for prop_match in re.finditer(prop_pattern, struct_body):
                field_name = prop_match.group(1)
                type_hint = prop_match.group(2).strip()

                # Skip computed properties (those with { get or { return)
                if field_name.startswith("_"):
                    continue

                # Skip if this looks like a computed property
                next_content = struct_body[prop_match.end():prop_match.end() + 50]
                if re.match(r"\s*\{", next_content) and "return" not in type_hint:
                    continue

                optional = type_hint.endswith("?")

                fields[field_name] = FieldInfo(
                    name=field_name,
                    type_hint=type_hint,
                    optional=optional,
                    has_default=False,  # We don't parse Swift defaults
                )

            if fields:
                models[struct_name] = ModelInfo(name=struct_name, fields=fields)

    return models


def convert_python_field_to_swift(field_name: str) -> str:
    """Convert Python snake_case field name to Swift camelCase."""
    if field_name in PYTHON_TO_SWIFT_FIELD:
        return PYTHON_TO_SWIFT_FIELD[field_name]

    # Default conversion: snake_case to camelCase
    parts = field_name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def validate_models(python_file: Path, swift_files: list[Path]) -> list[str]:
    """Compare Python and Swift models, return list of issues."""
    issues = []

    python_models = parse_python_models(python_file)
    swift_models = parse_swift_models(swift_files)

    for python_name, swift_name in MODELS_TO_CHECK.items():
        if python_name not in python_models:
            issues.append(f"Python model '{python_name}' not found in {python_file.name}")
            continue

        if swift_name not in swift_models:
            issues.append(f"Swift struct '{swift_name}' not found in parsed Swift model files")
            continue

        python_model = python_models[python_name]
        swift_model = swift_models[swift_name]
        ignored = IGNORED_FIELDS.get(python_name, set())

        # Check for missing fields in Swift
        for py_field_name, py_field in python_model.fields.items():
            if py_field_name in ignored:
                continue

            swift_field_name = convert_python_field_to_swift(py_field_name)

            if swift_field_name not in swift_model.fields:
                issues.append(
                    f"Missing field in Swift {swift_name}: "
                    f"'{swift_field_name}' (Python: {python_name}.{py_field_name})"
                )

        # Check for extra fields in Swift (might be intentional, so just warn)
        python_field_names_swift = {
            convert_python_field_to_swift(name)
            for name in python_model.fields.keys()
            if name not in ignored
        }

        for swift_field_name in swift_model.fields.keys():
            if swift_field_name not in python_field_names_swift:
                # Check if it's a known Swift-only field
                if swift_field_name in {"id"}:  # id might be computed
                    continue
                # This is informational, not an error
                # issues.append(f"Extra field in Swift {swift_name}: '{swift_field_name}' (not in Python)")

    return issues


def main():
    """Main entry point."""
    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    python_file = project_root / "src" / "fichero" / "workflows" / "types.py"
    swift_model_files = [
        project_root.parent / "fichero" / "fichero" / "Models" / "WorkflowTypes.swift",
        project_root.parent / "fichero" / "fichero" / "Models" / "WorkflowSupportTypes.swift",
        project_root.parent / "fichero" / "fichero" / "Models" / "WorkflowToolTypes.swift",
    ]

    if not python_file.exists():
        print(f"Error: Python file not found: {python_file}")
        sys.exit(1)

    missing_swift_files = [path for path in swift_model_files if not path.exists()]
    if missing_swift_files:
        for path in missing_swift_files:
            print(f"Error: Swift file not found: {path}")
        sys.exit(1)

    def format_path(path: Path) -> str:
        """Prefer repo-relative display; fall back to absolute path."""
        for base in (project_root, project_root.parent):
            try:
                return str(path.relative_to(base))
            except ValueError:
                continue
        return str(path)

    print("Validating Python/Swift model sync...")
    print(f"  Python: {format_path(python_file)}")
    print("  Swift files:")
    for swift_file in swift_model_files:
        print(f"    - {format_path(swift_file)}")
    print()

    issues = validate_models(python_file, swift_model_files)

    if issues:
        print("❌ Model sync issues found:")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("To fix, either:")
        print("  1. Add missing fields to Swift types in WorkflowTypes.swift")
        print("  2. Update conversion functions in WorkflowServiceGenerated.swift")
        print("  3. Run ./scripts/sync_openapi_schema.sh to regenerate OpenAPI spec")
        sys.exit(1)
    else:
        print("✅ All models are in sync!")
        sys.exit(0)


if __name__ == "__main__":
    main()
