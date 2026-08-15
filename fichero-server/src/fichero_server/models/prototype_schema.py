"""Typed attribute declarations on document prototypes (datasets Stage 1).

A prototype's ``attributes`` dict (``ClassificationValue`` with
``dimension == document_prototype``) historically holds PLAIN default values
(``container_kind: "folder"``). Structured data needs typed columns, so a
declared attribute is a DICT value carrying a ``type``::

    {"weather": {"type": "select", "options": ["fair", "rain"], "default": ""}}
    {"date":    {"type": "date", "role": "date", "required": true}}

Plain (non-dict) values remain legacy untyped defaults — the builtin seeds
keep working unchanged, and the existing root→leaf shallow merge in
``node_prototypes.resolve_prototype_attributes`` composes both shapes: a
child prototype overrides an attribute by redeclaring it.

Roles (``title``, ``date``, ``geo``, ``media``, ``subtitle``) tell a renderer
which attribute to point at — the timeline renders against the ``date`` role,
cards caption from ``title`` (spec §3.1/§7.2).

Prefer-raise: an unknown type or role in a declaration is a loud
``ValueError`` at prototype save time, never a silently ignored column.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Spec §7.2 — the closed attribute-type vocabulary. The three ``*_ref``
#: types are what prevent a parallel, weaker relation system beside the KG.
ATTRIBUTE_TYPES = frozenset({
    "text", "long_text", "number", "date", "select", "multi_select",
    "checkbox", "rating", "url", "geo", "media",
    "document_ref", "entity_ref", "claim_ref",
})

#: Spec §3.1 — roles a renderer keys on.
ATTRIBUTE_ROLES = frozenset({"title", "date", "geo", "media", "subtitle"})


class AttributeDecl(BaseModel):
    """One declared, typed prototype attribute."""

    model_config = ConfigDict(extra="forbid")

    type: str
    role: str | None = None
    default: Any = None
    options: list[str] = Field(default_factory=list)
    required: bool = False

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in ATTRIBUTE_TYPES:
            raise ValueError(
                f"Unknown attribute type {value!r}; expected one of "
                f"{sorted(ATTRIBUTE_TYPES)}"
            )
        return value

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str | None) -> str | None:
        if value is not None and value not in ATTRIBUTE_ROLES:
            raise ValueError(
                f"Unknown attribute role {value!r}; expected one of "
                f"{sorted(ATTRIBUTE_ROLES)}"
            )
        return value


def is_declaration(value: Any) -> bool:
    """True when an attributes-dict value is a typed declaration."""
    return isinstance(value, dict) and "type" in value


def attribute_declarations(attributes: dict[str, Any]) -> dict[str, AttributeDecl]:
    """Normalize an (effective) attributes dict into typed declarations.

    Typed dict values validate as :class:`AttributeDecl`; legacy plain values
    become untyped ``text`` declarations whose default is the value itself,
    so every attribute renders as a column even on pre-Stage-1 prototypes.

    Raises:
        ValueError: a declaration carries an unknown type or role. Loud on
            purpose — a silently dropped column is how extraction QA lies.
    """
    declarations: dict[str, AttributeDecl] = {}
    for name, value in attributes.items():
        if is_declaration(value):
            try:
                declarations[name] = AttributeDecl.model_validate(value)
            except Exception as exc:
                raise ValueError(f"Attribute {name!r}: {exc}") from exc
        else:
            declarations[name] = AttributeDecl(type="text", default=value)
    return declarations


def validate_prototype_attributes(attributes: dict[str, Any]) -> None:
    """Validate a prototype's attributes dict at save time (loud, not lossy)."""
    attribute_declarations(attributes)
