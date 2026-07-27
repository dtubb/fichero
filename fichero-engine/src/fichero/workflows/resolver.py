"""
Input Resolver

Resolves input mappings from path syntax to actual values.
Handles $.nodes.x.y, $.inputs.z, $.files, literals, etc.

Path Syntax:
    Basic paths:
        $.nodes.{id}.{key}       - Output from node
        $.inputs.{key}           - Workflow input
        $.files                  - All input files
        $.files[n]               - Specific file
        $.config.{key}           - Workflow config

    Array operations:
        $.nodes.x.items[*]       - All items in array
        $.nodes.x.items[*].text  - Extract 'text' from each item
        $.nodes.x.items[-1]      - Last item

    Transforms (pipe syntax):
        $.nodes.x.items[*].text | join("\\n")   - Join array with newlines
        $.nodes.x.text | upper                   - Uppercase
        $.nodes.x.text | lower                   - Lowercase
        $.nodes.x.text | trim                    - Strip whitespace
        $.nodes.x.count | str                    - Convert to string
        $.nodes.x.items | len                    - Array length
        $.nodes.x.items | first                  - First item
        $.nodes.x.items | last                   - Last item
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fichero.workflows.safe_condition import safe_eval_expression
from fichero.workflows.types import State

logger = logging.getLogger(__name__)

# Path patterns
NODE_PATH = re.compile(r"^\$\.nodes\.([^.]+)\.(.+)$")  # $.nodes.{id}.{key}
INPUT_PATH = re.compile(r"^\$\.inputs\.(.+)$")  # $.inputs.{key}
FILES_PATH = re.compile(
    r"^\$\.files(?:\[(-?\d+|\*)\])?$"
)  # $.files, $.files[n], $.files[*]
CONFIG_PATH = re.compile(r"^\$\.config\.(.+)$")  # $.config.{key}
STATE_PATH = re.compile(r"^\$\.state\.(.+)$")  # $.state.{key} (raw state access)
TRANSFORM_SPLIT = re.compile(r"\s*\|\s*")  # Split on pipe for transforms


def resolve_inputs(
    input_mappings: dict[str, Any],
    state: State,
    workflow_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve all input mappings to actual values.

    Args:
        input_mappings: Dict of param_name -> path_or_literal
        state: Current workflow state
        workflow_config: Workflow-level configuration

    Returns:
        Dict of param_name -> resolved_value
    """
    resolved = {}

    for param, source in input_mappings.items():
        try:
            resolved[param] = resolve_value(source, state, workflow_config)
        except Exception as e:
            logger.warning("Failed to resolve %s=%s: %s", param, source, e)
            resolved[param] = None

    return resolved


def resolve_value(
    source: Any,
    state: State,
    workflow_config: dict[str, Any] | None = None,
) -> Any:
    """Resolve a single value from its source specification.

    Args:
        source: Path string ($.nodes.x.y) or literal value
        state: Current workflow state
        workflow_config: Workflow-level configuration

    Returns:
        Resolved value
    """
    if isinstance(source, list):
        return [resolve_value(value, state, workflow_config) for value in source]

    # Literal values (not strings, or strings not starting with $)
    if not isinstance(source, str):
        return source

    if not source.startswith("$"):
        return source

    # Check for transforms (pipe syntax): $.path | transform
    parts = TRANSFORM_SPLIT.split(source)
    path = parts[0]
    transforms = parts[1:] if len(parts) > 1 else []

    # Resolve the base path
    value = _resolve_path(path, state, workflow_config)

    # Apply transforms
    for transform in transforms:
        value = _apply_transform(value, transform)

    return value


def _resolve_path(
    path: str,
    state: State,
    workflow_config: dict[str, Any] | None = None,
) -> Any:
    """Resolve a path without transforms."""

    # $.nodes.{node_id}.{rest}
    match = NODE_PATH.match(path)
    if match:
        node_id, rest = match.groups()
        node_output = state.get("outputs", {}).get(node_id, {})
        return _get_nested(node_output, rest)

    # $.inputs.{key}
    match = INPUT_PATH.match(path)
    if match:
        key = match.group(1)
        return _get_nested(state.get("inputs", {}), key)

    # $.files, $.files[n], $.files[*]
    match = FILES_PATH.match(path)
    if match:
        index = match.group(1)
        files = state.get("input_files", [])
        if index is None:
            return files
        elif index == "*":
            return files  # All files
        else:
            idx = int(index)
            if idx < 0:
                idx = len(files) + idx  # Negative indexing
            return files[idx] if 0 <= idx < len(files) else None

    # $.config.{key}
    match = CONFIG_PATH.match(path)
    if match:
        key = match.group(1)
        return _get_nested(workflow_config or {}, key)

    # $.state.{key} - direct state access
    match = STATE_PATH.match(path)
    if match:
        key = match.group(1)
        return _get_nested(dict(state), key)

    logger.warning("Unknown path pattern: %s", path)
    return None


def _apply_transform(value: Any, transform: str) -> Any:
    """Apply a transform function to a value.

    Supported transforms:
        join("sep")  - Join array with separator
        upper        - Uppercase string
        lower        - Lowercase string
        trim         - Strip whitespace
        str          - Convert to string
        int          - Convert to int
        float        - Convert to float
        len          - Length of array/string
        first        - First item of array
        last         - Last item of array
        keys         - Dict keys
        values       - Dict values
        flatten      - Flatten nested arrays
        unique       - Unique values
        sort         - Sort array
        reverse      - Reverse array
    """
    transform = transform.strip()

    # join("sep") or join('sep')
    join_match = re.match(r'join\(["\'](.*)["\']\)', transform)
    if join_match:
        sep = join_match.group(1)
        if isinstance(value, list):
            return sep.join(str(v) for v in value if v is not None)
        return value

    # Simple transforms
    if transform == "upper":
        return str(value).upper() if value else value
    elif transform == "lower":
        return str(value).lower() if value else value
    elif transform == "trim":
        return str(value).strip() if value else value
    elif transform == "str":
        return str(value) if value is not None else ""
    elif transform == "int":
        return int(value) if value else 0
    elif transform == "float":
        return float(value) if value else 0.0
    elif transform == "len":
        return len(value) if value else 0
    elif transform == "first":
        if isinstance(value, list) and len(value) > 0:
            return value[0]
        return None
    elif transform == "last":
        if isinstance(value, list) and len(value) > 0:
            return value[-1]
        return None
    elif transform == "keys":
        if isinstance(value, dict):
            return list(value.keys())
        return []
    elif transform == "values":
        if isinstance(value, dict):
            return list(value.values())
        return []
    elif transform == "flatten":
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, list):
                    result.extend(item)
                else:
                    result.append(item)
            return result
        return value
    elif transform == "unique":
        if isinstance(value, list):
            seen = set()
            result = []
            for item in value:
                key = str(item)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return result
        return value
    elif transform == "sort":
        if isinstance(value, list):
            return sorted(value, key=lambda x: str(x) if x else "")
        return value
    elif transform == "reverse":
        if isinstance(value, list):
            return list(reversed(value))
        elif isinstance(value, str):
            return value[::-1]
        return value

    # JSON transforms
    elif transform == "json":
        # Parse JSON string to dict/list
        return _parse_json(value)
    elif transform == "json_repair":
        # Parse and repair malformed JSON
        return _parse_json(value, repair=True)
    elif transform == "json_extract":
        # Extract JSON from text (finds first {...} or [...])
        return _extract_json(value)

    else:
        logger.warning("Unknown transform: %s", transform)
        return value


def _parse_json(value: Any, repair: bool = False) -> Any:
    """Parse JSON string, optionally repairing common issues.

    Common issues repaired:
    - Trailing commas
    - Single quotes instead of double
    - Unquoted keys
    - Missing quotes around strings
    - JavaScript-style comments
    """

    if not isinstance(value, str):
        return value

    text = value.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if not repair:
            logger.warning("JSON parse failed: %s...", text[:100])
            return value

    # Attempt repairs
    repaired = text

    # Remove JavaScript-style comments
    repaired = re.sub(r"//.*?$", "", repaired, flags=re.MULTILINE)
    repaired = re.sub(r"/\*.*?\*/", "", repaired, flags=re.DOTALL)

    # Replace single quotes with double quotes (careful with nested quotes)
    # Only do this if there are no double quotes at all
    if '"' not in repaired and "'" in repaired:
        repaired = repaired.replace("'", '"')

    # Remove trailing commas before } or ]
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    # Try again
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Try to fix unquoted keys: {key: value} -> {"key": value}
    repaired = re.sub(r"(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        logger.warning("JSON repair failed: %s", e)
        return value


def _extract_json(value: Any) -> Any:
    """Extract JSON from text containing other content.

    Useful when LLM returns JSON wrapped in explanation text.
    Finds the first complete {...} or [...] block.
    """

    if not isinstance(value, str):
        return value

    # Try to find JSON object {...}
    obj_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", value, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            pass

    # Try to find JSON array [...]
    arr_match = re.search(r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]", value, re.DOTALL)
    if arr_match:
        try:
            return json.loads(arr_match.group())
        except json.JSONDecodeError:
            pass

    # Try code block extraction ```json ... ```
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", value)
    if code_match:
        return _parse_json(code_match.group(1), repair=True)

    logger.warning("Could not extract JSON from: %s...", value[:100])
    return value


def _get_nested(obj: dict | list, path: str) -> Any:
    """Get a nested value from a dict/list using dot notation.

    Supports:
    - obj.key.subkey
    - obj.key[0].subkey
    - obj[0][1]
    - obj.items[*].text  -> Extract 'text' from each item
    - obj[-1]            -> Negative indexing
    """
    current = obj
    parts = _parse_path(path)

    for i, part in enumerate(parts):
        if current is None:
            return None

        if part == "*":
            # Wildcard: extract from all items
            if isinstance(current, list):
                # Get remaining path after [*]
                remaining_parts = parts[i + 1 :]
                if remaining_parts:
                    # Extract nested value from each item
                    remaining_path = _parts_to_path(remaining_parts)
                    return [_get_nested(item, remaining_path) for item in current]
                else:
                    return current
            else:
                return None

        elif isinstance(part, int):
            # List index (supports negative)
            if isinstance(current, list):
                if part < 0:
                    part = len(current) + part
                if 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            else:
                return None
        else:
            # Dict key
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                # If we have a list but need a dict key, extract from all items
                current = [
                    item.get(part) if isinstance(item, dict) else None
                    for item in current
                ]
            else:
                return None

    return current


def _parts_to_path(parts: list[str | int]) -> str:
    """Convert parsed path parts back to a string."""
    result = []
    for part in parts:
        if isinstance(part, int):
            result.append(f"[{part}]")
        elif part == "*":
            result.append("[*]")
        else:
            if result:
                result.append(f".{part}")
            else:
                result.append(part)
    return "".join(result)


def _parse_path(path: str) -> list[str | int]:
    """Parse a path into parts, handling both dots and brackets.

    Examples:
        "foo.bar" -> ["foo", "bar"]
        "foo[0].bar" -> ["foo", 0, "bar"]
        "foo.bar[2][3]" -> ["foo", "bar", 2, 3]
        "foo[*].bar" -> ["foo", "*", "bar"]
        "foo[-1]" -> ["foo", -1]
    """
    parts = []
    current = ""

    i = 0
    while i < len(path):
        char = path[i]

        if char == ".":
            if current:
                parts.append(current)
                current = ""
        elif char == "[":
            if current:
                parts.append(current)
                current = ""
            # Find closing bracket
            end = path.index("]", i)
            index_str = path[i + 1 : end]
            if index_str == "*":
                parts.append("*")  # Wildcard
            else:
                parts.append(int(index_str))  # Supports negative
            i = end
        else:
            current += char

        i += 1

    if current:
        parts.append(current)

    return parts


def evaluate_condition(
    condition: str,
    state: State,
    workflow_config: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a conditional expression.

    Supports:
    - $.nodes.x.y == "value"
    - $.nodes.x.count > 10
    - $.inputs.flag == true

    Args:
        condition: Condition string with paths and operators
        state: Current workflow state
        workflow_config: Workflow-level configuration

    Returns:
        Boolean result
    """

    # Replace paths with resolved values
    def replace_path(match: re.Match) -> str:
        path = match.group(0)
        value = resolve_value(path, state, workflow_config)

        # Convert to valid Python literal
        if value is None:
            return "None"
        elif isinstance(value, bool):
            return "True" if value else "False"
        elif isinstance(value, str):
            return repr(value)
        else:
            return str(value)

    # Find all $. paths and replace them
    resolved_condition = re.sub(r"\$\.[a-zA-Z0-9_.\[\]]+", replace_path, condition)

    # Handle common comparisons
    resolved_condition = resolved_condition.replace(" true", " True")
    resolved_condition = resolved_condition.replace(" false", " False")

    try:
        result = safe_eval_expression(resolved_condition)
        return bool(result)
    except Exception as e:
        logger.warning(
            "Condition evaluation failed: %s -> %s: %s",
            condition,
            resolved_condition,
            e,
        )
        return False
