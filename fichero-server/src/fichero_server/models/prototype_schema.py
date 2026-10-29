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


#: The computed-column vocabulary (attributes-and-prototypes.md §3): read-only, no stored value.
COMPUTED_SOURCES = frozenset({
    "folder.name", "folder.first_file", "folder.last_file", "folder.page_count",
    "folder.path", "description", "problems", "cataloguer",
})

#: Keys that name a prototype for the nodes beneath (§1); they are not fields/columns.
LEVEL_KEYS = ("subfolders", "pages", "regions", "lines", "entries")

NAME_ORDERS = frozenset({"as_written", "surname_first"})


class AttributeDecl(BaseModel):
    """One declared, typed prototype attribute."""

    model_config = ConfigDict(extra="forbid")

    type: str
    role: str | None = None
    default: Any = None
    options: list[str] = Field(default_factory=list)
    required: bool = False
    #: The question a model is asked and a person reads (`structured.schema.question-wording`, #5636);
    #: None asks it from the label (`question`).
    ask: str | None = None
    #: The column heading; None shows the attribute's key.
    label: str | None = None
    #: A few worded answers, put in the extraction prompt (and later the training set).
    examples: list[str] = Field(default_factory=list)
    #: Column position; declarations without one follow in key order (§3).
    order: int | None = None
    #: Heading per language; the old single ``label`` stands for the project's metadata language.
    labels: dict[str, str] = Field(default_factory=dict)
    #: The instruction line under the heading, per language.
    help: dict[str, str] = Field(default_factory=dict)
    #: ``{language: {option: label}}`` for select / multi_select.
    option_labels: dict[str, dict[str, str]] = Field(default_factory=dict)
    #: The nearest ancestor's effective value shows when the node holds none (§2).
    inherits: bool = False
    #: String between list values ("; " or "|").
    join: str | None = None
    #: People: as written, or "Apellido, Nombre".
    name_order: str | None = None
    #: Date format such as ``d/Mes/aaaa``.
    format: str | None = None
    #: A computed column's source (no stored value).
    source: str | None = None
    #: Month names per language for the ``Mes`` of a date ``format`` (declaration data, not code).
    months: dict[str, list[str]] = Field(default_factory=dict)
    #: A child prototype hides a column it inherits without removing the parent's declaration.
    hidden: bool = False

    def heading(self, key: str, language: str | None = None) -> str:
        """The column heading: the language's label, else any label, else the old label, else the key."""
        if language and self.labels.get(language):
            return self.labels[language]
        if self.label:
            return self.label
        for text in self.labels.values():
            if text:
                return text
        return key

    def question(self, key: str) -> str:
        """The field's question: its own wording, else one made from its label (or key)."""
        if self.ask and self.ask.strip():
            return self.ask.strip()
        name = (self.label or key.replace("_", " ")).strip()
        return f"What is the {name[:1].lower() + name[1:]}?"

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in ATTRIBUTE_TYPES:
            raise ValueError(
                f"Unknown attribute type {value!r}; expected one of "
                f"{sorted(ATTRIBUTE_TYPES)}"
            )
        return value

    @field_validator("source")
    @classmethod
    def _known_source(cls, value: str | None) -> str | None:
        if value is not None and value not in COMPUTED_SOURCES:
            raise ValueError(f"Unknown column source {value!r}; expected one of {sorted(COMPUTED_SOURCES)}")
        return value

    @field_validator("name_order")
    @classmethod
    def _known_name_order(cls, value: str | None) -> str | None:
        if value is not None and value not in NAME_ORDERS:
            raise ValueError(f"Unknown name_order {value!r}; expected one of {sorted(NAME_ORDERS)}")
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
        if name in LEVEL_KEYS and isinstance(value, str):
            continue  # a prototype key for the nodes beneath, not a field
        if is_declaration(value):
            try:
                declarations[name] = AttributeDecl.model_validate(value)
            except Exception as exc:
                raise ValueError(f"Attribute {name!r}: {exc}") from exc
        else:
            declarations[name] = AttributeDecl(type="text", default=value)
    return declarations


def level_defaults(attributes: dict[str, Any]) -> dict[str, str]:
    """The prototype keys a prototype names for the nodes beneath (``subfolders``, ``pages`` ...)."""
    return {k: attributes[k] for k in LEVEL_KEYS if isinstance(attributes.get(k), str) and attributes[k]}


def ordered_field_keys(attributes: dict[str, Any]) -> list[str]:
    """Field keys in template order: declared ``order`` first, then the rest by key (§3)."""
    decls = attribute_declarations(attributes)
    return sorted(decls, key=lambda k: (decls[k].order is None, decls[k].order or 0, k))


def validate_prototype_attributes(attributes: dict[str, Any]) -> None:
    """Validate a prototype's attributes dict at save time (loud, not lossy)."""
    for key in LEVEL_KEYS:
        value = attributes.get(key)
        if key != "entries" and value is not None and not isinstance(value, str):
            raise ValueError(f"Attribute {key!r} must name a prototype key, not {value!r}")
    attribute_declarations(attributes)
