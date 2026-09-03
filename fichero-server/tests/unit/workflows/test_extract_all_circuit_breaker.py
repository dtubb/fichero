"""extract_all in-flight circuit breaker + error_kind propagation.

Beta catalogue run, 2026-09-03 (~250 files): extract_all ground through
~894/1,084 items re-raising the SAME structured-call failure on every one.
`_classify_systemic_error` only runs after the batch, so every failing item
still paid for (and waited on) a doomed LLM call. The breaker opens after
N consecutive identical failures, remaining chunks are skipped loudly (never
fabricated), and one success resets the streak so genuinely-partial runs are
untouched. Failures classified by the LLM layer (StructuredCallEmptyError,
mirroring 10872b864's error_kind work) carry their kind onto page errors.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm import LLMConfig, StructuredCallEmptyError
from fichero_server.workflows.tools import extract_all as module


def _records(n: int) -> list[dict]:
    return [
        {"doc_id": f"page-{i}", "text": f"Page {i} names Ana and the ledger."}
        for i in range(n)
    ]


def _wire_oneshot(monkeypatch, fake_chat) -> SimpleNamespace:
    container = SimpleNamespace(id="doc-1", updated_at=None)
    saved_artifacts: list = []
    fake_db = SimpleNamespace(
        query=lambda *_args, **_kwargs: [],
        save=lambda obj, *_a, **_k: saved_artifacts.append(obj),
        path=SimpleNamespace(parent="/tmp"),
    )
    monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", "1")
    monkeypatch.setattr(module, "chat_structured_with_fallback", fake_chat)
    monkeypatch.setattr(module, "_write_kg_rows", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(module, "_resolve_write_target", lambda *_: container)
    monkeypatch.setattr(module.db_manager, "get_database", lambda *_: fake_db)
    monkeypatch.setattr(module, "_load_registry_types", lambda *_a, **_k: [])
    return SimpleNamespace(container=container, saved_artifacts=saved_artifacts)


async def _run_oneshot(n_pages: int) -> dict:
    records = _records(n_pages)
    return await module.extract_all(
        {
            "text": "\n\n".join(r["text"] for r in records),
            "records": records,
            "extraction_mode": "oneshot",
        },
        {
            "library_path": "/tmp/fichero-test-library",
            "selected_doc_ids": ["doc-1"],
            "task_id": "task-1",
        },
        LLMConfig(provider="test", model="test"),
    )


class TestOneshotCircuitBreaker:
    @pytest.mark.asyncio
    async def test_identical_failures_stop_paying_for_llm_calls(self, monkeypatch):
        calls = 0

        async def always_fail(**_kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("provider exploded identically")

        _wire_oneshot(monkeypatch, always_fail)
        result = await _run_oneshot(30)

        # With in-flight capped at 1, the breaker opens at exactly the
        # threshold; the remaining 22 chunks are skipped without an LLM call.
        assert calls == module._CIRCUIT_BREAK_CONSECUTIVE
        # The run is classified systemic and aborts loudly.
        assert "systemic" in (result.get("error") or "")

    @pytest.mark.asyncio
    async def test_skipped_pages_get_loud_error_artifacts_not_fabrication(
        self, monkeypatch
    ):
        async def always_fail(**_kwargs):
            raise RuntimeError("provider exploded identically")

        wired = _wire_oneshot(monkeypatch, always_fail)
        result = await _run_oneshot(30)

        assert not result["value"]  # nothing invented for skipped pages
        error_artifacts = [
            a
            for a in wired.saved_artifacts
            if getattr(a, "artifact_type", "") == "extraction_error"
        ]
        assert len(error_artifacts) == 30
        skip_texts = [a for a in error_artifacts if "circuit breaker open" in a.content]
        # Every skipped page's artifact names the breaker AND the repeated cause.
        assert len(skip_texts) == 30 - module._CIRCUIT_BREAK_CONSECUTIVE
        assert all("provider exploded identically" in a.content for a in skip_texts)

    @pytest.mark.asyncio
    async def test_intermittent_failures_never_open_the_breaker(self, monkeypatch):
        calls = 0

        async def flaky(**_kwargs):
            nonlocal calls
            calls += 1
            if calls % 2 == 0:
                raise RuntimeError("transient hiccup")
            return module._Extraction(
                people=[
                    module._Person(
                        name="Ana",
                        verb="appears on",
                        object="the page",
                        source_text="Ana",
                    )
                ]
            )

        _wire_oneshot(monkeypatch, flaky)
        result = await _run_oneshot(30)

        # Every chunk was attempted — a success resets the identical-failure
        # streak, so a genuinely-partial run is not short-circuited.
        assert calls == 30
        assert result["value"]["people"]

    @pytest.mark.asyncio
    async def test_error_kind_from_classified_failure_reaches_page_errors(
        self, monkeypatch
    ):
        async def truncated(**_kwargs):
            raise StructuredCallEmptyError(
                "structured call returned no parsed result", error_kind="truncated"
            )

        wired = _wire_oneshot(monkeypatch, truncated)
        await _run_oneshot(3)

        error_artifacts = [
            a
            for a in wired.saved_artifacts
            if getattr(a, "artifact_type", "") == "extraction_error"
        ]
        assert error_artifacts
        assert any("error_kind=truncated" in a.content for a in error_artifacts)


class TestTwoStageCircuitBreaker:
    @pytest.mark.asyncio
    async def test_stage1_breaker_opens_and_stage2_is_skipped(self, monkeypatch):
        stage1_calls = 0
        stage2_calls = 0

        async def stage1_always_fails(**_kwargs):
            nonlocal stage1_calls
            stage1_calls += 1
            raise RuntimeError("provider exploded identically")

        async def stage2_counts(*_args, **_kwargs):
            nonlocal stage2_calls
            stage2_calls += 1
            return []

        monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", "1")
        monkeypatch.setattr(
            module, "chat_structured_with_fallback", stage1_always_fails
        )
        monkeypatch.setattr(module, "_extract_claims_for_entity", stage2_counts)
        monkeypatch.setattr(
            module, "_resolve_write_target", lambda *_: SimpleNamespace(id="doc-1")
        )
        monkeypatch.setattr(
            module.db_manager, "get_database", lambda *_: SimpleNamespace()
        )

        records = _records(30)
        result = await module._run_two_stage(
            text="\n\n".join(r["text"] for r in records),
            recovered_records=records,
            state={"library_path": "", "selected_doc_ids": []},
            llm_config=LLMConfig(provider="test", model="test"),
            output_language="English",
            inputs={},
        )

        assert stage1_calls == module._CIRCUIT_BREAK_CONSECUTIVE
        assert stage2_calls == 0
        # Two-stage no longer swallows a systemically-broken Stage 1: the run
        # aborts with the cause instead of returning a clean empty success.
        assert "systemic" in (result.get("error") or "")
        assert "provider exploded identically" in result["error"]

    @pytest.mark.asyncio
    async def test_two_stage_partial_failures_still_continue(self, monkeypatch):
        calls = 0

        async def flaky_stage1(**_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("one transient failure")
            return module._EntitiesOnly(
                people=[module._EntityOnly(name="Ana", entity_type="person")]
            )

        async def stage2(*_args, **_kwargs):
            return [
                {
                    "verb": "signed",
                    "object": "the ledger",
                    "source_text": "Ana signed the ledger",
                }
            ]

        monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", "1")
        monkeypatch.setattr(module, "chat_structured_with_fallback", flaky_stage1)
        monkeypatch.setattr(module, "_extract_claims_for_entity", stage2)
        monkeypatch.setattr(
            module, "_resolve_write_target", lambda *_: SimpleNamespace(id="doc-1")
        )
        monkeypatch.setattr(
            module.db_manager, "get_database", lambda *_: SimpleNamespace()
        )

        records = _records(5)
        result = await module._run_two_stage(
            text="\n\n".join(r["text"] for r in records),
            recovered_records=records,
            state={"library_path": "", "selected_doc_ids": []},
            llm_config=LLMConfig(provider="test", model="test"),
            output_language="English",
            inputs={"persist_kg": False},
        )

        assert calls == 5
        assert not result.get("error")
        assert result["value"]["people"]
