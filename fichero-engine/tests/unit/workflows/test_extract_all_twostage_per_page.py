from __future__ import annotations

import pytest

from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.llm import LLMConfig
from fichero.models import DocType, Document
from fichero.workflows.tools import extract_all as extract_all_module


@pytest.mark.asyncio
async def test_two_stage_writes_kg_rows_to_page_docs_not_folder(db, test_package, monkeypatch):
    folder = Document(name="Folder", path="/tmp/folder", doc_type=DocType.folder)
    page1 = Document(name="p1", path="/tmp/folder/p1.png", doc_type=DocType.page)
    page2 = Document(name="p2", path="/tmp/folder/p2.png", doc_type=DocType.page)
    db.save(folder)
    db.save(page1)
    db.save(page2)

    async def fake_stage1(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._EntitiesOnly:
            raise AssertionError(f"unexpected schema: {schema!r}")
        return extract_all_module._EntitiesOnly(
            people=[extract_all_module._EntityOnly(name="Ada", entity_type="person")],
            places=[],
            organizations=[],
            dates=[],
            events=[],
        )

    async def fake_claims_for_entity(*args, **kwargs):
        return [
            {
                "verb": "signed",
                "object": "the ledger",
                "source_text": "Ada signed the ledger",
            }
        ]

    monkeypatch.setattr(
        "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_stage1,
    )
    monkeypatch.setattr(
        "fichero.workflows.tools.extract_all._extract_claims_for_entity",
        fake_claims_for_entity,
    )

    state = {
        "library_path": str(test_package),
        "selected_doc_ids": [folder.id],
    }
    llm_config = LLMConfig(provider="openai", model="gpt-4o-mini")

    await extract_all_module._run_two_stage(
        text="Ada signed the ledger.",
        recovered_records=[
            {"doc_id": page1.id, "text": "Ada signed the ledger."},
            {"doc_id": page2.id, "text": "Ada signed the ledger again."},
        ],
        state=state,
        llm_config=llm_config,
        output_language="English",
        inputs={"persist_kg": True},
    )

    entities = db.query(KnowledgeEntity, entity_type=EntityType.person)
    assert entities, "expected person KnowledgeEntity rows to be persisted"

    folder_claims = db.query(KnowledgeClaim, source_document_id=folder.id)
    page1_claims = db.query(KnowledgeClaim, source_document_id=page1.id)
    page2_claims = db.query(KnowledgeClaim, source_document_id=page2.id)

    assert len(folder_claims) == 0, "claims should be attached to page docs"
    assert len(page1_claims) > 0
    assert len(page2_claims) > 0


# ---------------------------------------------------------------------------
# Regression: Apple _EntitiesOnly grammar must stay permissive (#1272 revert).
#
# #1272 made every _EntitiesOnly field + _EntityOnly.entity_type required so the
# Apple grammar would refuse a `{}` decode. But an all-required nested grammar
# is unsatisfiable for on-device FoundationModels, collapsing the constrained
# decoder to empty on EVERY chunk. The fix: keep the fields optional (permissive
# grammar) and detect a genuinely-empty Stage 1 result via a soft-fail helper.
# ---------------------------------------------------------------------------


class TestEntitiesOnlyGrammarPermissive:
    def test_entities_only_fields_optional(self):
        """All 5 _EntitiesOnly category fields default to [] so the Apple
        grammar marks them optional (not required) — instantiation with no
        args must succeed."""
        entities = extract_all_module._EntitiesOnly()
        assert entities.people == []
        assert entities.places == []
        assert entities.organizations == []
        assert entities.dates == []
        assert entities.events == []

    def test_entities_only_not_in_json_schema_required(self):
        """The five category fields must NOT appear in the Pydantic JSON-schema
        `required` list — that's the signal _pydantic_to_apple_schema uses to
        mark a property `optional` in the Apple grammar tree."""
        required = set(
            extract_all_module._EntitiesOnly.model_json_schema().get("required", [])
        )
        assert required == set(), f"expected no required fields, got {required}"

    def test_entity_only_entity_type_optional(self):
        """_EntityOnly.entity_type must be optional with a sensible default so
        each element of the nested grammar is also permissive."""
        ent = extract_all_module._EntityOnly(name="Dr. Guerrero")
        assert ent.entity_type == "other"
        required = set(
            extract_all_module._EntityOnly.model_json_schema().get("required", [])
        )
        # name stays required; entity_type must NOT be required.
        assert "entity_type" not in required
        assert "name" in required

    def test_apple_schema_marks_entities_only_fields_optional(self):
        """End-to-end: the Apple grammar tree produced from _EntitiesOnly marks
        every category property `optional`, so fm-bridge permits an empty
        decode instead of collapsing."""
        from fichero.llm import _pydantic_to_apple_schema

        schema = _pydantic_to_apple_schema(extract_all_module._EntitiesOnly)
        props = {p["name"]: p for p in schema["properties"]}
        for field in ("people", "places", "organizations", "dates", "events"):
            assert props[field].get("optional") is True, (
                f"{field} must be optional in the Apple grammar"
            )

    def test_empty_stage1_result_detected_as_soft_failure(self):
        """An all-empty Stage 1 decode is a valid permissive-grammar result and
        must be detected explicitly (soft failure), not raise."""
        empty = extract_all_module._EntitiesOnly()
        assert extract_all_module._entities_only_is_empty(empty) is True

    def test_non_empty_stage1_result_not_flagged_empty(self):
        """A Stage 1 result WITH entities (the real Marshall-page case) must not
        be flagged empty."""
        result = extract_all_module._EntitiesOnly(
            people=[
                extract_all_module._EntityOnly(name="Dr. Guerrero", entity_type="person"),
                extract_all_module._EntityOnly(name="Dr. Cordoba", entity_type="person"),
            ],
            places=[extract_all_module._EntityOnly(name="Condoto", entity_type="place")],
        )
        assert extract_all_module._entities_only_is_empty(result) is False
