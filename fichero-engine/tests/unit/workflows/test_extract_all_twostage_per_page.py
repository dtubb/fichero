from __future__ import annotations

import asyncio

import pytest

from fichero.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
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


@pytest.mark.asyncio
async def test_two_stage_extracts_entity_claims_concurrently_with_same_output(
    db, test_package, monkeypatch
):
    page = Document(name="p", path="/tmp/p.png", doc_type=DocType.page)
    db.save(page)

    async def fake_stage1(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._EntitiesOnly:
            raise AssertionError(f"unexpected schema: {schema!r}")
        return extract_all_module._EntitiesOnly(
            people=[
                extract_all_module._EntityOnly(name="Ada", entity_type="person"),
                extract_all_module._EntityOnly(name="Bert", entity_type="person"),
                extract_all_module._EntityOnly(name="Cy", entity_type="person"),
            ],
        )

    active = 0
    max_active = 0
    call_order: list[str] = []

    async def fake_claims_for_entity(
        _context, entity_name, _entity_type, _llm_config, _instructions, extraction_sem
    ):
        nonlocal active, max_active
        async with extraction_sem:
            call_order.append(entity_name)
            active += 1
            max_active = max(max_active, active)
            await extract_all_module.asyncio.sleep(0)
            active -= 1
        return [
            {
                "verb": "signed",
                "object": f"{entity_name} ledger",
                "source_text": f"{entity_name} signed the ledger",
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

    result = await extract_all_module._run_two_stage(
        text="Ada signed the ledger. Bert signed the ledger. Cy signed the ledger.",
        recovered_records=[{"doc_id": page.id, "text": "Ada signed the ledger."}],
        state={"library_path": str(test_package), "selected_doc_ids": [page.id]},
        llm_config=LLMConfig(provider="openai", model="gpt-4o-mini"),
        output_language="English",
        inputs={"persist_kg": False},
    )

    assert max_active > 1
    assert call_order == ["Ada", "Bert", "Cy"]
    assert result["value"]["people"] == [
        {
            "name": "Ada",
            "verb": "signed",
            "object": "Ada ledger",
            "source_text": "Ada signed the ledger",
        },
        {
            "name": "Bert",
            "verb": "signed",
            "object": "Bert ledger",
            "source_text": "Bert signed the ledger",
        },
        {
            "name": "Cy",
            "verb": "signed",
            "object": "Cy ledger",
            "source_text": "Cy signed the ledger",
        },
    ]


@pytest.mark.asyncio
async def test_two_stage_preserves_entity_order_when_claim_tasks_finish_out_of_order(
    db, test_package, monkeypatch
):
    page = Document(name="p", path="/tmp/p.png", doc_type=DocType.page)
    db.save(page)

    async def fake_stage1(**kwargs):
        schema = kwargs.get("schema")
        if schema is not extract_all_module._EntitiesOnly:
            raise AssertionError(f"unexpected schema: {schema!r}")
        return extract_all_module._EntitiesOnly(
            people=[
                extract_all_module._EntityOnly(name="Ada", entity_type="person"),
                extract_all_module._EntityOnly(name="Bert", entity_type="person"),
                extract_all_module._EntityOnly(name="Cy", entity_type="person"),
            ],
        )

    completion_order: list[str] = []
    delays = {"Ada": 0.03, "Bert": 0.01, "Cy": 0.0}

    async def fake_claims_for_entity(
        _context, entity_name, _entity_type, _llm_config, _instructions, extraction_sem
    ):
        async with extraction_sem:
            await asyncio.sleep(delays[entity_name])
            completion_order.append(entity_name)
        return [
            {
                "verb": "signed",
                "object": f"{entity_name} ledger",
                "source_text": f"{entity_name} signed the ledger",
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

    result = await extract_all_module._run_two_stage(
        text="Ada signed the ledger. Bert signed the ledger. Cy signed the ledger.",
        recovered_records=[{"doc_id": page.id, "text": "Ada signed the ledger."}],
        state={"library_path": str(test_package), "selected_doc_ids": [page.id]},
        llm_config=LLMConfig(provider="openai", model="gpt-4o-mini"),
        output_language="English",
        inputs={"persist_kg": False},
    )

    assert completion_order == ["Cy", "Bert", "Ada"]
    assert [person["name"] for person in result["value"]["people"]] == [
        "Ada",
        "Bert",
        "Cy",
    ]


@pytest.mark.asyncio
async def test_two_stage_entity_claim_failures_stay_local_to_the_failed_entity(
    db, test_package, monkeypatch
):
    page = Document(name="p", path="/tmp/p.png", doc_type=DocType.page)
    db.save(page)

    async def fake_chat_structured_with_fallback(**kwargs):
        schema = kwargs.get("schema")
        if schema is extract_all_module._EntitiesOnly:
            return extract_all_module._EntitiesOnly(
                people=[
                    extract_all_module._EntityOnly(name="Ada", entity_type="person"),
                    extract_all_module._EntityOnly(name="Bert", entity_type="person"),
                ],
            )
        if schema is extract_all_module._EntityClaims:
            prompt = kwargs.get("prompt", "")
            if "Entity: Bert" in prompt:
                raise RuntimeError("malformed entity claims")
            if "Entity: Ada" in prompt:
                return extract_all_module._EntityClaims(
                    subject="Ada",
                    claims=[
                        extract_all_module._SVOClaim(
                            subject="Ada",
                            verb="signed",
                            object="the ledger",
                            source_text="Ada signed the ledger",
                        )
                    ]
                )
        raise AssertionError(f"unexpected schema/prompt: {schema!r} {kwargs.get('prompt')!r}")

    monkeypatch.setattr(
        "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
        fake_chat_structured_with_fallback,
    )

    result = await extract_all_module._run_two_stage(
        text="Ada signed the ledger. Bert signed the ledger.",
        recovered_records=[{"doc_id": page.id, "text": "Ada signed the ledger. Bert signed the ledger."}],
        state={"library_path": str(test_package), "selected_doc_ids": [page.id]},
        llm_config=LLMConfig(provider="openai", model="gpt-4o-mini"),
        output_language="English",
        inputs={"persist_kg": False},
    )

    assert result["value"]["people"] == [
        {
            "name": "Ada",
            "verb": "signed",
            "object": "the ledger",
            "source_text": "Ada signed the ledger",
        }
    ]
    assert result["cached"] is False


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


# ---------------------------------------------------------------------------
# Regression: Apple Stage 1 must inject the schema into the prompt (#1633/#1634).
#
# With include_schema_in_prompt=False the Apple on-device FoundationModels
# decoder returns a grammar-VALID but ALL-EMPTY _EntitiesOnly object even on
# clean prose, so NER entities were never extracted (and therefore never saved).
# Injecting the schema gives the model the field signal it needs and it extracts
# entities reliably. Other providers describe the shape via system instructions
# and keep the flag False for cloud-prompt token economy.
# ---------------------------------------------------------------------------


class TestEntitySchemaInPrompt:
    def test_apple_provider_injects_schema(self):
        cfg = LLMConfig(provider="apple", model="apple")
        assert extract_all_module._entity_schema_in_prompt(cfg) is True

    def test_apple_provider_case_insensitive(self):
        cfg = LLMConfig(provider="Apple", model="apple")
        assert extract_all_module._entity_schema_in_prompt(cfg) is True

    def test_cloud_provider_does_not_inject_schema(self):
        cfg = LLMConfig(provider="openai", model="gpt-4o")
        assert extract_all_module._entity_schema_in_prompt(cfg) is False

    @pytest.mark.asyncio
    async def test_stage1_passes_include_schema_in_prompt_for_apple(
        self, db, test_package, monkeypatch
    ):
        """The live Stage 1 path must pass include_schema_in_prompt=True when the
        configured provider is Apple, so the on-device decoder populates the
        nested result instead of collapsing to empty."""
        page = Document(name="p", path="/tmp/p.png", doc_type=DocType.page)
        db.save(page)

        captured: dict[str, object] = {}

        async def fake_stage1(**kwargs):
            captured["include_schema_in_prompt"] = kwargs.get(
                "include_schema_in_prompt"
            )
            return extract_all_module._EntitiesOnly(
                people=[extract_all_module._EntityOnly(name="Ada", entity_type="person")],
            )

        async def fake_claims_for_entity(*args, **kwargs):
            return []

        monkeypatch.setattr(
            "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
            fake_stage1,
        )
        monkeypatch.setattr(
            "fichero.workflows.tools.extract_all._extract_claims_for_entity",
            fake_claims_for_entity,
        )

        await extract_all_module._run_two_stage(
            text="Ada signed the ledger.",
            recovered_records=[{"doc_id": page.id, "text": "Ada signed the ledger."}],
            state={"library_path": str(test_package), "selected_doc_ids": [page.id]},
            llm_config=LLMConfig(provider="apple", model="apple"),
            output_language="English",
            inputs={"persist_kg": False},
        )

        assert captured["include_schema_in_prompt"] is True

    @pytest.mark.asyncio
    async def test_stage1_no_schema_in_prompt_for_cloud(
        self, db, test_package, monkeypatch
    ):
        """Cloud providers keep include_schema_in_prompt=False (token economy)."""
        page = Document(name="p", path="/tmp/p.png", doc_type=DocType.page)
        db.save(page)

        captured: dict[str, object] = {}

        async def fake_stage1(**kwargs):
            captured["include_schema_in_prompt"] = kwargs.get(
                "include_schema_in_prompt"
            )
            return extract_all_module._EntitiesOnly(
                people=[extract_all_module._EntityOnly(name="Ada", entity_type="person")],
            )

        async def fake_claims_for_entity(*args, **kwargs):
            return []

        monkeypatch.setattr(
            "fichero.workflows.tools.extract_all.chat_structured_with_fallback",
            fake_stage1,
        )
        monkeypatch.setattr(
            "fichero.workflows.tools.extract_all._extract_claims_for_entity",
            fake_claims_for_entity,
        )

        await extract_all_module._run_two_stage(
            text="Ada signed the ledger.",
            recovered_records=[{"doc_id": page.id, "text": "Ada signed the ledger."}],
            state={"library_path": str(test_package), "selected_doc_ids": [page.id]},
            llm_config=LLMConfig(provider="openai", model="gpt-4o-mini"),
            output_language="English",
            inputs={"persist_kg": False},
        )

        assert captured["include_schema_in_prompt"] is False
