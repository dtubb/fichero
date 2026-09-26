"""#5072: a verb that changes what an entity IS writes the rule that makes the next import respect
it, in the SAME audited action. Every test here runs the full round trip through the real verb:

    run the verb -> the rule row exists -> re-import -> the correction held

Asserting only the last step would not fail when no verb writes a rule; asserting only the middle
step would prove a row was written and nothing about whether it works. (Two older tests, in
`test_entity_writer.py` and `test_merge_dedup_curation_survival.py`, saved the durable state by hand
and so could not fail on this gap; they now run their verb.)
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request

import fichero_server.api.routes.entity.entities  # noqa: F401  (registers entity.*)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.system.actions_registry import undo_action
from fichero_server.models.knowledge import (
    EntityResolutionRule,
    EntityResolutionRuleType,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)

SECTION = {"name": "people", "entity_type": EntityType.person}
LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _undo(db, audit_id: str):
    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
            "server": ("testserver", 443),
            "path": f"/api/actions/audit/{audit_id}/undo",
            "query_string": b"",
        }
    )
    return asyncio.run(
        undo_action(audit_id, request=request, db=db, x_fichero_library_path=LIB, x_fichero_origin_window=None)
    )


def _import(db, name: str, *, doc: str = "a", verb: str = "attended", obj: str = "a hearing") -> None:
    from fichero_server.workflows.tools.extractors import _write_kg_rows

    _write_kg_rows(
        db,
        section=SECTION,
        items=[{"name": name, "verb": verb, "object": obj}],
        container_id=doc,
        page_label="1",
        source_excerpt=f"{name} {verb} {obj}.",
    )


def _live(db) -> list[tuple[str, str]]:
    return sorted(
        (e.canonical_name, e.entity_type.value)
        for e in db.query(KnowledgeEntity)
        if e.merged_into_id is None
    )


def _entity(db, name: str) -> KnowledgeEntity:
    return next(e for e in db.query(KnowledgeEntity) if e.canonical_name == name)


def _rules(db, rule_type=None) -> list[EntityResolutionRule]:
    return [r for r in db.query(EntityResolutionRule) if rule_type is None or r.rule_type == rule_type]


class TestDeleteWritesASuppressRule:
    def test_the_deleted_entity_does_not_come_back_on_the_next_import(self, db):
        _import(db, "Zed Quill")
        registry.invoke(db, "entity.delete", {"entity_id": _entity(db, "Zed Quill").id}, _ctx())

        # the middle step: the rule exists, and says what it is for
        (rule,) = _rules(db, EntityResolutionRuleType.suppress)
        assert rule.match_canonical_name == "Zed Quill"
        assert rule.match_entity_type == EntityType.person
        assert rule.created_by == "ui"
        assert _live(db) == []

        # the last step: the correction held
        _import(db, "Zed Quill", doc="b")
        assert _live(db) == []
        # (the first import's claim stays, with its link cleared, by the delete's own contract)
        assert [c for c in db.query(KnowledgeClaim) if c.source_document_id == "b"] == []

    def test_an_alias_of_the_deleted_entity_is_suppressed_too(self, db):
        _import(db, "Zed Quill")
        entity = _entity(db, "Zed Quill")
        entity.aliases = ["Z. Quill"]
        db.save(entity)
        registry.invoke(db, "entity.delete", {"entity_id": entity.id}, _ctx())

        assert {r.match_canonical_name for r in _rules(db, EntityResolutionRuleType.suppress)} == {
            "Zed Quill",
            "Z. Quill",
        }
        _import(db, "Z. Quill", doc="b")
        assert _live(db) == []

    def test_the_rule_is_scoped_to_the_deleted_entitys_type(self, db):
        """Deleting a person "Zed Quill" must not suppress a place of the same name."""
        _import(db, "Zed Quill")
        registry.invoke(db, "entity.delete", {"entity_id": _entity(db, "Zed Quill").id}, _ctx())
        from fichero_server.workflows.tools.extractors import _write_kg_rows

        _write_kg_rows(
            db,
            section={"name": "places", "entity_type": EntityType.location},
            items=[{"name": "Zed Quill", "verb": "lies", "object": "north"}],
            container_id="b",
            page_label="1",
            source_excerpt="Zed Quill lies north.",
        )
        assert _live(db) == [("Zed Quill", "location")]

    def test_cascade_delete_writes_the_rule_too(self, db):
        _import(db, "Zed Quill")
        registry.invoke(
            db,
            "entity.delete",
            {"entity_id": _entity(db, "Zed Quill").id, "cascade_claims": True},
            _ctx(),
        )
        assert len(_rules(db, EntityResolutionRuleType.suppress)) == 1
        _import(db, "Zed Quill", doc="b")
        assert _live(db) == []

    def test_undo_removes_the_rule_so_the_restored_entity_is_not_suppressed(self, db):
        _import(db, "Zed Quill")
        forward = registry.invoke(
            db, "entity.delete", {"entity_id": _entity(db, "Zed Quill").id}, _ctx()
        )
        assert len(_rules(db)) == 1

        _undo(db, forward.audit_id)

        assert _rules(db) == []
        assert _live(db) == [("Zed Quill", "person")]
        _import(db, "Zed Quill", doc="b")
        assert _live(db) == [("Zed Quill", "person")], "a duplicate, or the mention was suppressed"

    def test_undoing_a_create_does_not_suppress_the_name(self, db):
        """The delete that is the INVERSE of a create is an undo, not a correction."""
        forward = registry.invoke(
            db,
            "entity.create",
            {"canonical_name": "Zed Quill", "entity_type": "person"},
            _ctx(),
        )
        _undo(db, forward.audit_id)
        assert _rules(db) == []
        _import(db, "Zed Quill", doc="b")
        assert _live(db) == [("Zed Quill", "person")]

    def test_a_rule_that_cannot_be_written_fails_the_verb_and_changes_nothing(self, db, monkeypatch):
        _import(db, "Zed Quill")
        entity = _entity(db, "Zed Quill")
        claims_before = [c.model_dump(mode="json") for c in db.query(KnowledgeClaim)]

        real_save = type(db).save

        def failing_save(self, obj, *args, **kwargs):
            if isinstance(obj, EntityResolutionRule):
                raise RuntimeError("rule store unavailable")
            return real_save(self, obj, *args, **kwargs)

        monkeypatch.setattr(type(db), "save", failing_save)
        with pytest.raises(RuntimeError, match="rule store unavailable"):
            registry.invoke(db, "entity.delete", {"entity_id": entity.id}, _ctx())
        monkeypatch.undo()

        assert db.get(KnowledgeEntity, entity.id) is not None, "the entity was deleted without its rule"
        assert _rules(db) == []
        assert [c.model_dump(mode="json") for c in db.query(KnowledgeClaim)] == claims_before


class TestReclassifyWritesAReclassifyRule:
    @staticmethod
    def _reclassify(db, name: str, to: str = "location"):
        entity = _entity(db, name)
        return registry.invoke(
            db,
            "entity.update",
            {"entity_id": entity.id, "canonical_name": entity.canonical_name, "entity_type": to},
            _ctx(),
        )

    def test_the_next_import_lands_on_the_corrected_type_not_beside_it(self, db):
        _import(db, "Quibdo Creek")
        self._reclassify(db, "Quibdo Creek")

        (rule,) = _rules(db, EntityResolutionRuleType.reclassify)
        assert rule.match_canonical_name == "Quibdo Creek"
        assert rule.match_entity_type == EntityType.person
        assert rule.target_entity_type == EntityType.location

        _import(db, "Quibdo Creek", doc="b")
        assert _live(db) == [("Quibdo Creek", "location")], "two rows for one thing at two types"

    def test_a_change_that_is_not_a_type_change_writes_no_rule(self, db):
        _import(db, "Quibdo Creek")
        entity = _entity(db, "Quibdo Creek")
        registry.invoke(
            db,
            "entity.update",
            {"entity_id": entity.id, "canonical_name": "Quibdo Creek", "entity_type": "person", "description": "a stream"},
            _ctx(),
        )
        assert _rules(db) == []

    def test_reclassifying_back_supersedes_the_rule_instead_of_forming_a_cycle(self, db):
        """A -> B -> A must not leave two opposite rules: the resolver answers a cycle by
        SUPPRESSING the mention, which would drop every later import of the name."""
        _import(db, "Quibdo Creek")
        self._reclassify(db, "Quibdo Creek", to="location")
        self._reclassify(db, "Quibdo Creek", to="person")

        rules = _rules(db, EntityResolutionRuleType.reclassify)
        assert [(r.match_entity_type, r.target_entity_type) for r in rules] == [
            (EntityType.location, EntityType.person)
        ]
        _import(db, "Quibdo Creek", doc="b")
        assert _live(db) == [("Quibdo Creek", "person")], "the name was suppressed or duplicated"

    def test_undo_restores_the_type_and_removes_the_rule(self, db):
        _import(db, "Quibdo Creek")
        forward = self._reclassify(db, "Quibdo Creek")
        assert len(_rules(db)) == 1

        _undo(db, forward.audit_id)

        assert _rules(db) == []
        assert _live(db) == [("Quibdo Creek", "person")]
        _import(db, "Quibdo Creek", doc="b")
        assert _live(db) == [("Quibdo Creek", "person")]

    def test_undoing_the_second_reclassify_restores_the_rule_it_superseded(self, db):
        _import(db, "Quibdo Creek")
        self._reclassify(db, "Quibdo Creek", to="location")
        back = self._reclassify(db, "Quibdo Creek", to="person")

        _undo(db, back.audit_id)

        rules = _rules(db, EntityResolutionRuleType.reclassify)
        assert [(r.match_entity_type, r.target_entity_type) for r in rules] == [
            (EntityType.person, EntityType.location)
        ]
        assert _live(db) == [("Quibdo Creek", "location")]

    def test_a_rule_that_cannot_be_written_fails_the_verb_and_the_type_is_unchanged(self, db, monkeypatch):
        _import(db, "Quibdo Creek")
        entity = _entity(db, "Quibdo Creek")
        real_save = type(db).save

        def failing_save(self, obj, *args, **kwargs):
            if isinstance(obj, EntityResolutionRule):
                raise RuntimeError("rule store unavailable")
            return real_save(self, obj, *args, **kwargs)

        monkeypatch.setattr(type(db), "save", failing_save)
        with pytest.raises(RuntimeError, match="rule store unavailable"):
            registry.invoke(
                db,
                "entity.update",
                {"entity_id": entity.id, "canonical_name": "Quibdo Creek", "entity_type": "location"},
                _ctx(),
            )
        monkeypatch.undo()

        assert db.get(KnowledgeEntity, entity.id).entity_type == EntityType.person
        assert _rules(db) == []


class TestRenameWritesAnAliasRule:
    """#5073: renaming to a DIFFERENT name keeps the old name resolvable."""

    @staticmethod
    def _rename(db, old: str, new: str, **extra):
        entity = _entity(db, old)
        return registry.invoke(
            db,
            "entity.update",
            {
                "entity_id": entity.id,
                "canonical_name": new,
                "entity_type": extra.pop("entity_type", entity.entity_type.value),
                **extra,
            },
            _ctx(),
        )

    def test_the_old_name_no_longer_mints_a_duplicate(self, db):
        _import(db, "the Major")
        self._rename(db, "the Major", "John Marshall")

        (rule,) = _rules(db, EntityResolutionRuleType.alias)
        assert rule.match_canonical_name == "the Major"
        assert rule.target_canonical_name == "John Marshall"
        assert rule.match_entity_type == EntityType.person

        _import(db, "the Major", doc="b")
        assert _live(db) == [("John Marshall", "person")], "the old name minted a duplicate"
        renamed = _entity(db, "John Marshall")
        (new_claim,) = [c for c in db.query(KnowledgeClaim) if c.source_document_id == "b"]
        assert new_claim.subject_entity_id == renamed.id

    def test_a_case_only_rename_writes_no_rule(self, db):
        _import(db, "the major")
        self._rename(db, "the major", "The Major")
        assert _rules(db) == []

    def test_renaming_back_supersedes_the_rule_instead_of_forming_a_cycle(self, db):
        _import(db, "the Major")
        self._rename(db, "the Major", "John Marshall")
        self._rename(db, "John Marshall", "the Major")

        rules = _rules(db, EntityResolutionRuleType.alias)
        assert [(r.match_canonical_name, r.target_canonical_name) for r in rules] == [
            ("John Marshall", "the Major")
        ]
        _import(db, "the Major", doc="b")
        assert _live(db) == [("the Major", "person")]

    def test_a_rename_and_a_type_change_in_one_update_both_hold(self, db):
        """The resolver applies the reclassify rule and then looks the name up AGAIN at the new
        type; the alias rule must still match there."""
        _import(db, "Quibdo Creek")
        self._rename(db, "Quibdo Creek", "Rio Quibdo", entity_type="location")

        _import(db, "Quibdo Creek", doc="b")
        assert _live(db) == [("Rio Quibdo", "location")]

    def test_undo_removes_the_rule_and_the_old_name_is_the_name_again(self, db):
        _import(db, "the Major")
        forward = self._rename(db, "the Major", "John Marshall")
        _undo(db, forward.audit_id)

        assert _rules(db) == []
        assert _live(db) == [("the Major", "person")]
        _import(db, "the Major", doc="b")
        assert _live(db) == [("the Major", "person")]

    def test_a_rule_that_cannot_be_written_fails_the_rename_and_the_name_is_unchanged(self, db, monkeypatch):
        _import(db, "the Major")
        entity = _entity(db, "the Major")
        real_save = type(db).save

        def failing_save(self, obj, *args, **kwargs):
            if isinstance(obj, EntityResolutionRule):
                raise RuntimeError("rule store unavailable")
            return real_save(self, obj, *args, **kwargs)

        monkeypatch.setattr(type(db), "save", failing_save)
        with pytest.raises(RuntimeError, match="rule store unavailable"):
            self._rename(db, "the Major", "John Marshall")
        monkeypatch.undo()

        assert db.get(KnowledgeEntity, entity.id).canonical_name == "the Major"
        assert _rules(db) == []

