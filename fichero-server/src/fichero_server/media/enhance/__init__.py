"""The enhancement steps: ONE engine function per step, reached by every door (`image.enhance.three-doors-one-function`, #6194).

Each module `<step>.py` has `Params` (a Pydantic model: the editor's request body and the workflow node's config are
built from it) and `run(image, params) -> (image, account)`. The doors are the workflow node, the editor operation and the
rendition writer; none of them has its own copy of a step's pixels. Steps in the engine today: page-crop, deskew, rotate,
split, contrast. Nothing here imports from `fichero_archive` or reads an `assets/<stage>/` folder
(`image.enhance.old-conventions-left-behind`; the guardrail is `tests/unit/media/test_enhance_three_doors.py`).
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

#: step name (as the account and a rendition's `steps[].step` spell it) -> module name
_MODULES = {"page-crop": "page_crop", "deskew": "deskew", "rotate": "rotate", "split": "split", "contrast": "contrast"}


@dataclass(frozen=True)
class StepSpec:
    name: str
    params: type[BaseModel]
    run: Callable[..., tuple[Any, dict[str, Any]]]


def _load() -> dict[str, StepSpec]:
    out = {}
    for name, module_name in _MODULES.items():
        module = importlib.import_module(f"{__name__}.{module_name}")
        out[name] = StepSpec(name, module.Params, module.run)
    return out


def __getattr__(attr: str) -> Any:
    if attr == "STEPS":  # built on first use: the step modules import their own readers lazily
        steps = _load()
        globals()["STEPS"] = steps
        return steps
    raise AttributeError(attr)


def node_config(params: type[BaseModel], *, only: tuple[str, ...] | None = None) -> dict[str, dict[str, Any]]:
    """A workflow node's `config_schema` entries built from the params model, so the node and the editor request cannot drift.
    Each field becomes `{type, default, description, enum?, minimum?, maximum?}`."""
    properties = params.model_json_schema().get("properties", {})
    out: dict[str, dict[str, Any]] = {}
    for key, prop in properties.items():
        if only is not None and key not in only:
            continue
        # an optional field (`X | None`) is an `anyOf` of its type and null: the node shows the type, the null is its default
        branches = [b for b in prop.get("anyOf", []) if b.get("type") != "null"]
        flat = {**(branches[0] if len(branches) == 1 else {}), **{k: v for k, v in prop.items() if k != "anyOf"}}
        entry = {k: flat[k] for k in ("type", "enum", "default", "minimum", "maximum", "description") if k in flat}
        out[key] = entry
    return out
