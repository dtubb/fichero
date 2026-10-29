"""Typed prototype attribute declarations (datasets Stage 1).

The contract: typed dict values validate against a CLOSED type/role
vocabulary and fail LOUDLY; legacy plain values keep working as untyped
text defaults so pre-Stage-1 prototypes (the builtin seeds) are untouched.
"""

import pytest

from fichero_server.models.prototype_schema import (
    ATTRIBUTE_ROLES,
    ATTRIBUTE_TYPES,
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


class TestDeclarationsGainTemplateFields:
    """proto.template.labels-per-language-and-order, proto.kind.declared-defaults-for-beneath
    (attributes-and-prototypes.md Step 1.1)."""

    def test_new_fields_parse(self):
        decl = attribute_declarations({"tema": {
            "type": "multi_select", "order": 4,
            "labels": {"es": "Tema", "en": "Subject"},
            "help": {"es": "Elija términos"},
            "options": ["a", "b"],
            "option_labels": {"es": {"a": "Uno"}, "en": {"a": "One"}},
            "inherits": True, "join": "|", "name_order": "surname_first",
            "format": "d/Mes/aaaa", "source": "folder.name",
        }})["tema"]
        assert decl.order == 4 and decl.inherits and decl.join == "|"
        assert decl.labels["en"] == "Subject" and decl.help["es"]
        assert decl.option_labels["en"]["a"] == "One"
        assert decl.name_order == "surname_first" and decl.source == "folder.name"

    def test_unknown_source_and_name_order_raise(self):
        with pytest.raises(ValueError, match="source"):
            attribute_declarations({"x": {"type": "text", "source": "nope"}})
        with pytest.raises(ValueError, match="name_order"):
            attribute_declarations({"x": {"type": "text", "name_order": "backwards"}})

    def test_old_single_label_reads_as_metadata_language(self):
        decl = attribute_declarations({"x": {"type": "text", "label": "Título"}})["x"]
        assert decl.heading("x", "es") == "Título"
        assert decl.heading("x", "en") == "Título"  # no other label: the old one, never the key

    def test_heading_prefers_language_then_never_the_key(self):
        decl = attribute_declarations({"x": {"type": "text", "labels": {"es": "Título", "en": "Title"}}})["x"]
        assert decl.heading("x", "en") == "Title"
        assert decl.heading("x", "fr") in {"Título", "Title"}
        bare = attribute_declarations({"x": {"type": "text"}})["x"]
        assert bare.heading("x", "en") == "x"  # nothing declared: only then the key

    def test_ordered_keys_follow_order_then_key(self):
        from fichero_server.models.prototype_schema import ordered_field_keys

        attrs = {
            "b": {"type": "text"}, "a": {"type": "text"},
            "z": {"type": "text", "order": 1}, "y": {"type": "text", "order": 2},
            "subfolders": "eap_digital_folder",
        }
        assert ordered_field_keys(attrs) == ["z", "y", "a", "b"]  # level defaults are not fields

    def test_level_defaults_are_prototype_keys(self):
        from fichero_server.models.prototype_schema import level_defaults

        attrs = {"subfolders": "eap_digital_folder", "pages": "eap_page", "title": {"type": "text"}}
        assert level_defaults(attrs) == {"subfolders": "eap_digital_folder", "pages": "eap_page"}
        with pytest.raises(ValueError, match="subfolders"):
            validate_prototype_attributes({"subfolders": 3})


class TestLevelDefaultsAreChecked:
    """proto.kind.declared-defaults-for-beneath: unknown key or cycle refused with words."""

    @staticmethod
    def _db(tmp_path):
        from fichero_server.db import Database

        return Database(tmp_path / "t.duckdb")

    @staticmethod
    def _proto(db, key, attributes, parent_key=None):
        from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue

        db.save(ClassificationValue(dimension=ClassificationDimension.document_prototype, key=key,
                                    label=key, parent_key=parent_key, attributes=attributes))

    def test_unknown_prototype_key_is_refused_in_words(self, tmp_path):
        from fichero_server.models.node_prototypes import check_level_defaults

        db = self._db(tmp_path)
        try:
            with pytest.raises(ValueError, match="subfolders.*nope"):
                check_level_defaults(db, "box", {"subfolders": "nope"})
        finally:
            db.close()

    def test_cycle_through_levels_is_refused(self, tmp_path):
        from fichero_server.models.node_prototypes import check_level_defaults

        db = self._db(tmp_path)
        try:
            self._proto(db, "a", {"pages": "b"})
            self._proto(db, "b", {"subfolders": "a"})
            with pytest.raises(ValueError, match="cycle"):
                check_level_defaults(db, "b", {"subfolders": "a"})
            check_level_defaults(db, "c", {"pages": "a"})  # a known key, no cycle: fine
        finally:
            db.close()

    def test_save_route_refuses_unknown_key_with_422(self, tmp_path):
        from fastapi import HTTPException

        from fichero_server.api.routes.document.classifications import _validate_prototype_schema
        from fichero_server.models.knowledge import ClassificationDimension

        db = self._db(tmp_path)
        try:
            with pytest.raises(HTTPException) as exc:
                _validate_prototype_schema(ClassificationDimension.document_prototype,
                                           {"pages": "ghost"}, db=db, key="box")
            assert exc.value.status_code == 422
        finally:
            db.close()
