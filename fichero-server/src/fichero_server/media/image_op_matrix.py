"""The image-operation matrix, read live (`image.ops.matrix-is-complete`, #6363): which chain operations lack one of the engine's
doors. The chain vocabulary is `_OPERATION_MODELS` plus `_PARAMETERLESS_OPERATIONS`; the doors are the audited `image.<op>` action,
the workflow node and the Prepare Images operation id. A test names what is not yet, so a new operation cannot slip past."""
from __future__ import annotations

#: chain name -> the node that runs it, where the node is not `<name>_images`.
NODE_OF = {"straighten": "deskew_images", "flip_horizontal": "flip_images", "flip_vertical": "flip_images"}
#: chain name -> the Prepare Images operation id that runs it, where the id is not the name with hyphens.
PREPARE_OF = {"contrast": "clarity", "flip_horizontal": "flip", "flip_vertical": "flip", "deskew": "straighten"}


def missing_doors() -> dict[str, set[str]]:
    """`{"action": ..., "node": ..., "prepare": ...}`: the chain operations with no action, no node and no Prepare operation."""
    from fichero_server.actions.registry import registry
    from fichero_server.api.routes.ingest import image_editing
    from fichero_server.recipes import prepare_operations
    from fichero_server.workflows.registry import get_tool_def

    import fichero_server.workflows.tools.enhance_step_nodes  # noqa: F401  (registers the step nodes)

    names = image_editing._OPERATION_MODELS.keys() | image_editing._PARAMETERLESS_OPERATIONS
    return {
        "action": {n for n in names if f"image.{n}" not in registry.names()},
        "node": {n for n in names if get_tool_def(NODE_OF.get(n, f"{n}_images")) is None},
        "prepare": {n for n in names if PREPARE_OF.get(n, n.replace("_", "-")) not in prepare_operations.IDS},
    }
