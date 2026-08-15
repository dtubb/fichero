"""Typed prototype attribute declarations (datasets Stage 1).

The contract: typed dict values validate against a CLOSED type/role
vocabulary and fail LOUDLY; legacy plain values keep working as untyped
text defaults so pre-Stage-1 prototypes (the builtin seeds) are untouched.
"""

import pytest

from fichero_server.models.prototype_schema import (
    ATTRIBUTE_ROLES,
    ATTRIBUTE_TYPES,
    AttributeDecl,
    attribute_declarations,
    is_declaration,
    validate_prototype_attributes,
)


class TestDeclarations:
    def test_typed_declaration_parses(self):
        decls = attribute_declarations(
            {"date": {"type": "date", "role": "date", "required": True}}
        )
        assert decls["date"].type == "date"
        assert decls["date"].role == "date"
        assert decls["date"].required is True

    def test_legacy_plain_value_becomes_untyped_text_default(self):
        decls = attribute_declarations({"container_kind": "folder"})
        assert decls["container_kind"].type == "text"
        assert decls["container_kind"].default == "folder"
        assert decls["container_kind"].role is None

    def test_mixed_legacy_and_typed_coexist(self):
        decls = attribute_declarations({
            "supports_children": True,
            "weather": {"type": "select", "options": ["fair", "rain"]},
        })
        assert decls["supports_children"].default is True
        assert decls["weather"].options == ["fair", "rain"]

    def test_unknown_type_raises_with_attribute_name(self):
        with pytest.raises(ValueError, match="weather"):
            attribute_declarations({"weather": {"type": "climate"}})

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError, match="role"):
            attribute_declarations({"t": {"type": "text", "role": "headline"}})

    def test_extra_keys_in_declaration_are_rejected(self):
        # extra="forbid": a typo'd key must not silently vanish.
        with pytest.raises(ValueError, match="t"):
            attribute_declarations({"t": {"type": "text", "defualt": "x"}})

    def test_validate_is_the_same_contract(self):
        validate_prototype_attributes({"ok": {"type": "number"}})
        with pytest.raises(ValueError):
            validate_prototype_attributes({"bad": {"type": "nope"}})

    def test_is_declaration_discriminates(self):
        assert is_declaration({"type": "text"})
        assert not is_declaration("folder")
        assert not is_declaration({"no_type_key": 1})

    def test_ref_types_exist(self):
        # The three *_ref types are what prevent a parallel relation system.
        assert {"document_ref", "entity_ref", "claim_ref"} <= ATTRIBUTE_TYPES

    def test_renderer_roles_pinned(self):
        assert ATTRIBUTE_ROLES == {"title", "date", "geo", "media", "subtitle"}


class TestBuiltinSeedsStillValid:
    def test_builtin_seed_attributes_pass_validation(self):
        from fichero_server.db import _BUILTIN_DOCUMENT_PROTOTYPE_SEEDS

        assert _BUILTIN_DOCUMENT_PROTOTYPE_SEEDS, "seeds must exist to prove anything"
        for seed in _BUILTIN_DOCUMENT_PROTOTYPE_SEEDS:
            decls = attribute_declarations(dict(seed.get("attributes", {})))
            assert all(d.type == "text" for d in decls.values()), (
                "builtin seeds are legacy plain defaults — they must normalize "
                "as untyped text, not silently gain types"
            )


class TestRouteValidation:
    def test_prototype_dimension_rejects_bad_schema_with_422(self):
        from fastapi import HTTPException

        from fichero_server.api.routes.document.classifications import (
            _validate_prototype_schema,
        )
        from fichero_server.models.knowledge import ClassificationDimension

        with pytest.raises(HTTPException) as exc:
            _validate_prototype_schema(
                ClassificationDimension.document_prototype,
                {"weather": {"type": "climate"}},
            )
        assert exc.value.status_code == 422

        # Non-prototype dimensions carry free-form attributes — untouched.
        _validate_prototype_schema(
            ClassificationDimension.entity_type,
            {"weather": {"type": "climate"}},
        )
