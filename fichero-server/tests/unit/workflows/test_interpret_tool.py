"""The interpret tool — the hermeneutic layer's FIRST writer (2026-08-12).

The layer had models, tables, CRUD, and a predicate vocabulary with no
producer. interpret applies a framework to text via structured output and
persists Interpretation rows: canonicalized predicates, act fallback,
document linkage. Elementwise, so it chains after transcribe.
"""

from unittest.mock import patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.models.hermeneutics import (
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
)
from fichero_server.workflows.tools.interpret import (
    _InterpretationBatch,
    _InterpretationDraft,
    interpret,
)


@pytest.fixture
def framework(db):
    fw = InterpretiveFramework(
        name="Subaltern reading",
        framework_type="theoretical",
        description="Reads records against the archive's grain.",
    )
    db.save(fw)
    return fw


def _state(test_package):
    return {"library_path": str(test_package), "task_id": "t-1"}


class TestInterpretPersists:
    @pytest.mark.asyncio
    async def test_interpretations_persist_with_canonical_predicates(
        self, db, test_package, framework
    ):
        batch = _InterpretationBatch(
            interpretations=[
                _InterpretationDraft(
                    interpretation_text="The ledger centers the creditor's voice.",
                    act="critiquing",
                    predicate="contests reading",
                    key_insights=["debt structured the record"],
                    confidence=0.8,
                ),
                _InterpretationDraft(
                    interpretation_text="Read as an artifact of notarial power.",
                    act="NOT-AN-ACT",
                    predicate="reads as",
                ),
            ]
        )
        with patch(
            "fichero_server.llm.chat_structured", return_value=batch
        ):
            result = await interpret(
                inputs={
                    "text": "Cobro por $608 pesos contra Nicanor Córdoba…",
                    "documents": [{"id": "doc-1"}],
                    "framework_id": framework.id,
                },
                state=_state(test_package),
                llm_config=LLMConfig(provider="mock", model="m"),
            )

        assert result.get("error") is None
        assert result["count"] == 2
        rows = db.all(Interpretation)
        assert len(rows) == 2
        by_text = {r.interpretation_text: r for r in rows}
        first = by_text["The ledger centers the creditor's voice."]
        assert first.predicate_canonical == "contests_reading"
        assert first.act == InterpretiveActType.critiquing
        assert first.document_id == "doc-1"
        assert first.created_by == "model"
        # Unknown act falls back to `applying` rather than dying mid-run.
        second = by_text["Read as an artifact of notarial power."]
        assert second.act == InterpretiveActType.applying
        assert second.predicate_canonical == "reads_as"

    @pytest.mark.asyncio
    async def test_missing_framework_is_a_loud_error(self, db, test_package):
        result = await interpret(
            inputs={"text": "some text", "framework_id": "nope"},
            state=_state(test_package),
            llm_config=LLMConfig(provider="mock", model="m"),
        )
        assert "Framework not found" in result["error"]

    @pytest.mark.asyncio
    async def test_no_framework_configured_refuses(self, db, test_package):
        result = await interpret(
            inputs={"text": "some text"},
            state=_state(test_package),
            llm_config=LLMConfig(provider="mock", model="m"),
        )
        assert "No framework_id" in result["error"]

    @pytest.mark.asyncio
    async def test_no_text_refuses(self, db, test_package, framework):
        result = await interpret(
            inputs={"framework_id": framework.id},
            state=_state(test_package),
            llm_config=LLMConfig(provider="mock", model="m"),
        )
        assert result["error"] == "No text provided"
