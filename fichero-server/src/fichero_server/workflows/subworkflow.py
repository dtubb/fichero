"""Typed sub-workflow contracts and runtime helpers.

This module keeps the first sub-workflow slice intentionally small: references
are literal ids/names, contracts are Pydantic-validated, and tests can inject
child workflows through ``state["sub_workflows"]`` without touching the DB.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from typing import Any

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, field_validator

from fichero_server.llm import LLMConfig
from fichero_server.workflows.resolver import resolve_value
from fichero_server.workflows.types import DataType, PortDef, State, WorkflowDef

logger = logging.getLogger(__name__)


class SubWorkflowContractEntry(BaseModel):
    """Declared input/output exposed by a sub-workflow node."""

    id: str = Field(..., min_length=1)
    data_type: DataType = DataType.ANY
    required: bool = True
    description: str = ""
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("id")
    @classmethod
    def reject_dotted_ids(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("contract id cannot be empty")
        if "." in value:
            raise ValueError("contract id cannot contain dots")
        return value


class SubWorkflowConfig(BaseModel):
    """Typed config for the ``sub_workflow`` primitive."""

    workflow_ref: str = Field(..., min_length=1)
    workflow_version: str | None = None
    input_contract: list[SubWorkflowContractEntry] = Field(default_factory=list)
    output_contract: list[SubWorkflowContractEntry] = Field(default_factory=list)
    output_mapping: dict[str, str] = Field(default_factory=dict)
    max_depth: int = Field(default=4, ge=1, le=16)
    allow_partial: bool = False

    @field_validator("workflow_ref")
    @classmethod
    def workflow_ref_must_be_literal(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("workflow_ref cannot be empty")
        if value.startswith("$") or "{" in value or "}" in value:
            raise ValueError("workflow_ref must be a literal workflow id or template name")
        return value

    @field_validator("output_mapping")
    @classmethod
    def mapping_values_must_be_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for key, path in value.items():
            if not isinstance(path, str) or not path.startswith("$."):
                raise ValueError(f"output_mapping.{key} must be a workflow path")
        return value


WorkflowResolver = Callable[[str], WorkflowDef | None]


def contract_ports(
    entries: list[SubWorkflowContractEntry],
    *,
    port_type: str,
) -> list[PortDef]:
    """Convert declared contract entries into visual/runtime ports."""

    return [
        PortDef(
            id=entry.id,
            name=entry.id.replace("_", " ").title(),
            port_type=port_type,  # type: ignore[arg-type]
            data_type=entry.data_type,
            required=entry.required,
            description=entry.description,
        )
        for entry in entries
    ]


def parse_sub_workflow_config(config: Mapping[str, Any]) -> SubWorkflowConfig:
    """Parse a node config or merged tool input into a typed sub-workflow config."""

    return SubWorkflowConfig.model_validate(dict(config))


def _resolve_from_library_db(workflow_ref: str, library_path: str) -> WorkflowDef | None:
    """Resolve a child workflow from the library's workflow store (#4324).

    A user who edits a seeded sub-workflow component (e.g. tweaks the Spanish
    Script child passes' prompts) edits the DB row — the shipped JSON is only
    the install-time template. Resolution order within the DB: exact id, then
    name match preferring the seeded (is_system/is_template) row, so a user's
    same-named duplicate never hijacks a preset reference.
    """
    from fichero_server.db import db_manager
    from fichero_server.models import Workflow
    from fichero_server.workflows.runtime import to_workflow_def

    db = db_manager.get_database(library_path)
    stored = db.get(Workflow, workflow_ref)
    if stored is None:
        matches = [w for w in db.all(Workflow) if w.name == workflow_ref]
        flagged = [
            w
            for w in matches
            if getattr(w, "is_system", False) or getattr(w, "is_template", False)
        ]
        candidates = flagged or matches
        stored = candidates[0] if candidates else None
    if stored is None or not (getattr(stored, "nodes", None) or []):
        return None
    return to_workflow_def(stored)


def _resolve_from_global_defaults(workflow_ref: str) -> WorkflowDef | None:
    """Resolve a child ref against the global library's DEFAULT rows (#4450).

    Mirrors ``_resolve_from_library_db``'s id-then-name order, but only
    ``is_system`` rows qualify — a user workflow in the global library is a
    global-library workflow, not a default, and must not leak into other
    libraries' runs.
    """
    from fichero_server.workflows.default_workflows import (
        list_global_default_workflows,
        resolve_default_workflow,
    )
    from fichero_server.workflows.runtime import to_workflow_def

    stored = resolve_default_workflow(workflow_ref)
    if stored is None:
        matches = [
            w for w in list_global_default_workflows() if w.name == workflow_ref
        ]
        stored = matches[0] if matches else None
    if stored is None or not (getattr(stored, "nodes", None) or []):
        return None
    return to_workflow_def(stored)


def resolve_sub_workflow_ref(workflow_ref: str, state: State | None = None) -> WorkflowDef | None:
    """Resolve a child workflow: injected state, then DB, then shipped presets.

    The DB step (#4324) makes user edits to a sub-workflow component take
    effect when the parent runs; shipped JSON remains the fallback so a
    library without the seeded row (or with it deleted) still resolves.
    """

    injected = (state or {}).get("sub_workflows")  # type: ignore[typeddict-item]
    if isinstance(injected, Mapping):
        candidate = injected.get(workflow_ref)
        if isinstance(candidate, WorkflowDef):
            return candidate
        if isinstance(candidate, Mapping):
            return WorkflowDef.model_validate(candidate)

    library_path = str((state or {}).get("library_path") or "")
    if library_path:
        try:
            resolved = _resolve_from_library_db(workflow_ref, library_path)
            if resolved is not None:
                return resolved
        except Exception as exc:
            logger.warning(
                "Sub-workflow DB resolution failed for %r (%s); "
                "falling back to shipped presets",
                workflow_ref,
                exc,
            )

    # #4450 parity: default components live as rows in the GLOBAL library,
    # and a user's edit to one (tweaked prompts on the Spanish Script child
    # passes, say) edits that row. Skipping straight to the shipped JSON here
    # meant the parent used the EDITED component in the global library and
    # the PRISTINE one everywhere else — the same workflow silently behaving
    # differently per library. Resolve the global row before the JSON.
    try:
        resolved = _resolve_from_global_defaults(workflow_ref)
        if resolved is not None:
            return resolved
    except Exception as exc:
        logger.warning(
            "Sub-workflow global-default resolution failed for %r (%s); "
            "falling back to shipped presets",
            workflow_ref,
            exc,
        )

    try:
        from fichero_server.workflows.default_workflows import _load_preset_files

        for preset in _load_preset_files():
            if workflow_ref in {str(preset.get("id", "")), str(preset.get("name", ""))}:
                return WorkflowDef.model_validate(preset)
    except Exception:
        return None
    return None


def _value_matches_data_type(value: Any, data_type: DataType) -> bool:
    if data_type == DataType.ANY:
        return True
    if data_type == DataType.TEXT:
        return isinstance(value, str)
    if data_type == DataType.FILE:
        return isinstance(value, str)
    if data_type == DataType.FILES:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if data_type == DataType.JSON:
        return isinstance(value, dict)
    if data_type == DataType.ARRAY:
        return isinstance(value, list)
    if data_type == DataType.IMAGE:
        return isinstance(value, str)
    if data_type == DataType.NUMBER:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if data_type == DataType.BOOLEAN:
        return isinstance(value, bool)
    return True


def validate_contract_value(
    *,
    label: str,
    entry: SubWorkflowContractEntry,
    value: Any,
) -> None:
    """Validate one runtime input/output value against a contract entry."""

    if value is None:
        if entry.required:
            raise ValueError(f"Missing required {label} '{entry.id}'")
        return
    if not _value_matches_data_type(value, entry.data_type):
        raise ValueError(
            f"Invalid {label} '{entry.id}': expected {entry.data_type.value}, "
            f"got {type(value).__name__}"
        )
    if entry.json_schema:
        try:
            jsonschema.validate(value, entry.json_schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(
                f"Invalid {label} '{entry.id}': does not match schema: {exc.message}"
            ) from exc


def validate_sub_workflow_node_config(config: Mapping[str, Any]) -> list[str]:
    """Return typed validation errors for one sub-workflow node config."""

    try:
        parsed = parse_sub_workflow_config(config)
    except Exception as exc:
        return [str(exc)]

    output_ids = {entry.id for entry in parsed.output_contract}
    mapping_ids = set(parsed.output_mapping)
    missing_mappings = sorted(
        entry.id
        for entry in parsed.output_contract
        if entry.required and entry.id not in parsed.output_mapping
    )
    unknown_mappings = sorted(mapping_ids - output_ids)
    errors: list[str] = []
    if missing_mappings:
        errors.append(
            "output_mapping missing required contract output(s): "
            + ", ".join(missing_mappings)
        )
    if unknown_mappings:
        errors.append(
            "output_mapping references undeclared output(s): "
            + ", ".join(unknown_mappings)
        )
    return errors


def validate_sub_workflow_references(
    workflow: WorkflowDef,
    *,
    workflow_resolver: WorkflowResolver | None = None,
) -> list[str]:
    """Validate sub-workflow configs and reject direct/transitive cycles."""

    errors: list[str] = []
    root_keys = {workflow.id, workflow.name}
    resolver = workflow_resolver or (lambda ref: resolve_sub_workflow_ref(ref))

    def refs_for(current: WorkflowDef) -> list[tuple[str, str]]:
        refs: list[tuple[str, str]] = []
        for node in current.nodes:
            if node.tool != "sub_workflow":
                continue
            node_label = node.label or node.id or node.tool
            node_errors = validate_sub_workflow_node_config(node.config)
            errors.extend(
                f"Node '{node_label}' ({node.tool}): {error}"
                for error in node_errors
            )
            try:
                parsed = parse_sub_workflow_config(node.config)
            except Exception:
                continue
            refs.append((node_label, parsed.workflow_ref))
        return refs

    def visit(current: WorkflowDef, path: list[str]) -> None:
        for node_label, ref in refs_for(current):
            if ref in root_keys or ref in path:
                cycle = " -> ".join([*path, ref])
                errors.append(
                    f"Node '{node_label}' (sub_workflow): workflow reference cycle detected: {cycle}"
                )
                continue
            child = resolver(ref)
            if child is None:
                continue
            visit(child, [*path, ref])

    visit(workflow, [workflow.id or workflow.name])
    return errors


async def sub_workflow(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Execute a child workflow behind declared input/output contracts."""

    config = parse_sub_workflow_config(inputs)
    parent_node_id = str(inputs.get("__node_id") or "sub_workflow")
    parent_task_id = state.get("task_id", "")
    parent_workflow_id = state.get("workflow_id", "")
    depth = int(state.get("sub_workflow_depth", 0) or 0)
    if depth >= config.max_depth:
        raise RuntimeError(
            f"Sub-workflow '{config.workflow_ref}' exceeded max_depth={config.max_depth}"
        )

    child_inputs: dict[str, Any] = {}
    for entry in config.input_contract:
        value = inputs.get(entry.id)
        validate_contract_value(label="input", entry=entry, value=value)
        if value is not None:
            child_inputs[entry.id] = value

    child = resolve_sub_workflow_ref(config.workflow_ref, state)
    if child is None:
        raise RuntimeError(f"Sub-workflow '{config.workflow_ref}' could not be resolved")

    child_task_id = f"{parent_task_id or 'run'}:{parent_node_id}:{uuid.uuid4().hex[:8]}"
    parent_lineage = str(state.get("lineage_path", "") or parent_task_id or parent_workflow_id)
    lineage_path = "/".join(
        part for part in [parent_lineage, parent_node_id, child_task_id] if part
    )
    child_state = dict(state)
    child_state.update(
        {
            "task_id": child_task_id,
            "workflow_id": child.id,
            "parent_task_id": parent_task_id,
            "parent_workflow_id": parent_workflow_id,
            "parent_node_id": parent_node_id,
            "lineage_path": lineage_path,
            "sub_workflow_depth": depth + 1,
            "inputs": child_inputs,
            "outputs": {},
            "completed_nodes": [],
            "error": None,
        }
    )

    try:
        from fichero_server.workflows.builder import build_graph

        final_state = await build_graph(child, skip_cache=True).ainvoke(child_state)
    except Exception as exc:
        raise RuntimeError(
            f"Sub-workflow '{child.name}' failed under parent node "
            f"'{parent_node_id}': {exc}"
        ) from exc

    mapped: dict[str, Any] = {}
    for entry in config.output_contract:
        path = config.output_mapping.get(entry.id)
        value = resolve_value(path, final_state) if path else None
        validate_contract_value(label="output", entry=entry, value=value)
        if value is not None or entry.required or not config.allow_partial:
            mapped[entry.id] = value

    mapped["_run"] = {
        "child_task_id": child_task_id,
        "child_workflow_id": child.id,
        "parent_task_id": parent_task_id,
        "parent_workflow_id": parent_workflow_id,
        "parent_node_id": parent_node_id,
        "lineage_path": lineage_path,
    }
    return mapped
