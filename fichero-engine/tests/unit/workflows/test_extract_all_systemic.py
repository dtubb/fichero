"""Unit tests for extract_all's systemic-error classifier (#1060).

extract_all must fail-fast when a workflow run is systemically broken
(e.g. no $large configured → every Apple-Intelligence fallback re-raises
the same error on every page) instead of grinding through all pages and
returning an empty "successful" catalogue. Genuinely-partial failures (a
minority of sparse pages) must still warn-and-continue.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from types import SimpleNamespace

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools.extract_all import (
    _annotate_pronoun_source,
    _classify_systemic_error,
)


class TestClassifySystemicError:
    def test_no_errors_is_not_systemic(self):
        assert _classify_systemic_error([], 10) is None

    def test_zero_chunks_is_not_systemic(self):
        assert _classify_systemic_error(["boom"], 0) is None

    def test_all_chunks_failed_is_systemic(self):
        errors = ["sparse page, empty result"] * 12
        cause = _classify_systemic_error(errors, 12)
        assert cause is not None

    def test_single_transient_failure_is_not_systemic(self):
        errors = ["temporary decode hiccup"]
        assert _classify_systemic_error(errors, 1) is None

    def test_two_transient_failures_still_not_systemic(self):
        errors = ["temporary decode hiccup", "provider returned malformed json"]
        assert _classify_systemic_error(errors, 2) is None

    def test_high_fraction_failed_is_systemic(self):
        # 13/15 failed — not literally all, but well past the threshold.
        errors = ["guardrail refusal"] * 13
        cause = _classify_systemic_error(errors, 15)
        assert cause == "guardrail refusal"

    def test_repetitive_identical_error_is_systemic(self):
        # The $large-unconfigured pattern: every page re-raises the same
        # error. 12/15 identical → repetitive even though 3 pages were
        # error-free.
        errors = ["AppleUnavailableError: guardrail violation"] * 12
        cause = _classify_systemic_error(errors, 15)
        assert cause == "AppleUnavailableError: guardrail violation"

    def test_infra_signature_systemic_at_half(self):
        # An explicit infra signature (401) trips systemic once half the
        # chunks failed, even below the high-fraction threshold.
        errors = ["HTTP 401 Unauthorized", "sparse", "sparse", "sparse"]
        cause = _classify_systemic_error(errors, 8)
        assert cause == "HTTP 401 Unauthorized"

    def test_quota_signature_detected(self):
        errors = ["provider quota exceeded"] * 9
        cause = _classify_systemic_error(errors, 10)
        assert "quota" in cause.lower()

    def test_auth_signature_detected_on_first_failed_chunk(self):
        errors = ["HTTP 401 Unauthorized"]
        cause = _classify_systemic_error(errors, 1)
        assert cause == "HTTP 401 Unauthorized"

    def test_large_not_configured_signature_detected(self):
        errors = ["$large fallback not configured"] * 6
        cause = _classify_systemic_error(errors, 7)
        assert cause is not None

    def test_minority_isolated_failures_not_systemic(self):
        # 2/15 distinct, non-infra failures — the normal sparse-page case.
        # Must stay warn-and-continue.
        errors = ["empty pydantic from sparse page", "page had no text layer"]
        assert _classify_systemic_error(errors, 15) is None

    def test_below_half_with_infra_keyword_still_not_systemic(self):
        # One infra-looking error but only 1/15 chunks failed — a single
        # transient blip, not a systemic break.
        errors = ["connection reset"]
        assert _classify_systemic_error(errors, 15) is None


class TestAnnotatePronounSource:
    def test_he_gets_bracketed(self):
        result = _annotate_pronoun_source(
            "He had met his wife in Manizales.", "Aon Alfonso"
        )
        assert result == "[Aon Alfonso] He had met his wife in Manizales."

    def test_she_gets_bracketed(self):
        result = _annotate_pronoun_source("She wrote the letter.", "María")
        assert result == "[María] She wrote the letter."

    def test_they_gets_bracketed(self):
        result = _annotate_pronoun_source("They left at dawn.", "Los mineros")
        assert result == "[Los mineros] They left at dawn."

    def test_non_pronoun_unchanged(self):
        result = _annotate_pronoun_source(
            "Don Alfonso visited Manizales.", "Don Alfonso"
        )
        assert result == "Don Alfonso visited Manizales."

    def test_already_bracketed_not_doubled(self):
        # If the LLM already resolved it, no double annotation.
        result = _annotate_pronoun_source(
            "[Aon Alfonso] He arrived.", "Aon Alfonso"
        )
        # "[" is not a pronoun word — no change.
        assert result == "[Aon Alfonso] He arrived."

    def test_empty_source_text_unchanged(self):
        assert _annotate_pronoun_source("", "Entity") == ""

    def test_empty_entity_name_unchanged(self):
        assert _annotate_pronoun_source("He left.", "") == "He left."

    def test_pronoun_with_trailing_punctuation_stripped(self):
        # "Him," at start — comma should not block detection.
        result = _annotate_pronoun_source("Him, they found in the square.", "Juan")
        assert result == "[Juan] Him, they found in the square."

    def test_capitalization_insensitive(self):
        result = _annotate_pronoun_source("HE departed at noon.", "General Vargas")
        assert result == "[General Vargas] HE departed at noon."


async def _count_loop_ticks_until(done: asyncio.Event) -> int:
    ticks = 0
    while not done.is_set():
        ticks += 1
        await asyncio.sleep(0.001)
    return ticks


class TestExtractAllCooperativeScheduling:
    @pytest.mark.asyncio
    async def test_text_recovery_runs_off_event_loop(self, monkeypatch):
        """Large-PDF recovery can parse/query hundreds of pages.

        It must not run before the first await in extract_all, or the
        server loop cannot answer health checks while recovery is busy.
        """
        module = importlib.import_module("fichero.workflows.tools.extract_all")

        def slow_recovery(_inputs, _state):
            time.sleep(0.05)
            return "", []

        monkeypatch.setattr(module, "_recover_text_and_records", slow_recovery)

        done = asyncio.Event()
        ticker = asyncio.create_task(_count_loop_ticks_until(done))
        result = await module.extract_all(
            {},
            {},
            LLMConfig(provider="test", model="test"),
        )
        done.set()
        ticks = await ticker

        assert result["error"] == "No text input"
        assert ticks > 0

    @pytest.mark.asyncio
    async def test_per_page_persistence_yields_between_pages(self, monkeypatch):
        module = importlib.import_module("fichero.workflows.tools.extract_all")

        page_count = 30
        records = [
            {"doc_id": f"page-{i}", "text": f"Page {i} names Ana."}
            for i in range(page_count)
        ]
        text = "\n\n---\n\n".join(record["text"] for record in records)

        async def fake_chat_structured(**_kwargs):
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

        container = SimpleNamespace(id="doc-1", updated_at=None)
        fake_db = SimpleNamespace(
            query=lambda *_args, **_kwargs: [],
            save=lambda *_args, **_kwargs: None,
        )
        write_calls = 0

        def slow_write(*_args, **_kwargs):
            nonlocal write_calls
            write_calls += 1
            time.sleep(0.002)
            # _write_kg_rows now returns (entity_ids, claim_ids); the caller
            # unpacks it to feed per-document change-stream emits.
            return [], []

        # _extract_one (oneshot) calls chat_structured_with_fallback after #1284 fix.
        monkeypatch.setattr(module, "chat_structured_with_fallback", fake_chat_structured)
        monkeypatch.setattr(module, "_write_kg_rows", slow_write)
        monkeypatch.setattr(module, "_resolve_write_target", lambda *_: container)
        monkeypatch.setattr(module.db_manager, "get_database", lambda *_: fake_db)

        progress_events = []

        async def progress_callback(event_type, data):
            progress_events.append((event_type, data))

        done = asyncio.Event()
        ticker = asyncio.create_task(_count_loop_ticks_until(done))
        result = await module.extract_all(
            {
                "text": text,
                "records": records,
                "extraction_mode": "oneshot",
                "__progress_callback": progress_callback,
            },
            {
                "library_path": "/tmp/fichero-test-library",
                "selected_doc_ids": ["doc-1"],
                "task_id": "task-1",
            },
            LLMConfig(provider="test", model="test"),
        )
        done.set()
        ticks = await ticker

        assert write_calls == page_count
        assert result["value"]["people"]
        assert ticks > 0
        event_types = [event_type for event_type, _ in progress_events]
        assert "file_start" in event_types
        assert "file_complete" in event_types
        assert any(
            "Extract All chunk" in data["file_path"]
            for _, data in progress_events
        )
        assert any("KG write page" in data["file_path"] for _, data in progress_events)


class TestExtractAllOutputLanguageOverride:
    @pytest.mark.asyncio
    async def test_primary_language_setting_overrides_auto_detection(self, monkeypatch):
        module = importlib.import_module("fichero.workflows.tools.extract_all")

        async def fake_run_two_stage(
            _text,
            _records,
            _state,
            _llm_config,
            output_language,
            _inputs,
            _progress_callback,
        ):
            return {"output_language": output_language}

        class _FakeAppDB:
            def get_setting(self, key: str):
                if key == "default_primary_language":
                    return "Spanish"
                return None

        monkeypatch.setattr(module, "_run_two_stage", fake_run_two_stage)
        monkeypatch.setattr("fichero.db.app.get_app_db", lambda: _FakeAppDB())

        result = await module.extract_all(
            {
                "text": (
                    "Marshall wrote in English about Popayán and Andagoya, "
                    "but the diary passage itself is ordinary English prose."
                ),
                "records": [],
                "output_language": "auto",
                "extraction_mode": "twostage",
            },
            {},
            LLMConfig(provider="test", model="test"),
        )

        assert result["output_language"] == "Spanish"


class TestExtractAllProviderDefaults:
    @pytest.mark.asyncio
    async def test_direct_cloud_providers_default_to_twostage(self, monkeypatch):
        module = importlib.import_module("fichero.workflows.tools.extract_all")

        async def fake_run_two_stage(
            _text,
            _records,
            _state,
            _llm_config,
            _output_language,
            _inputs,
            _progress_callback,
        ):
            return {"mode": "twostage", "provider": _llm_config.provider}

        async def fail_oneshot(*_args, **_kwargs):
            raise AssertionError("oneshot path should not be the default here")

        monkeypatch.setattr(module, "_run_two_stage", fake_run_two_stage)
        monkeypatch.setattr(module, "chat_structured_with_fallback", fail_oneshot)

        for provider, model in (
            ("openai", "gpt-4o-mini"),
            ("openrouter", "openai/gpt-4o-mini"),
        ):
            result = await module.extract_all(
                {"text": "Marshall met Peña in San Pablo."},
                {},
                LLMConfig(provider=provider, model=model),
            )

            assert result == {"mode": "twostage", "provider": provider}


class TestExtractAllGuardrailFallback:
    """#1284 — guardrail/unsupported_language chunks must engage $large fallback.

    The oneshot _extract_one previously called chat_structured directly, so
    AppleUnavailableError subclasses (GuardrailViolationError, UnsupportedLocaleError)
    counted as chunk failures and accumulated in chunk_errors, eventually
    triggering the systemic-abort gate and returning an empty catalogue.

    After the fix, _extract_one calls chat_structured_with_fallback, which
    handles AppleUnavailableError internally and retries on $large.
    """

    @pytest.mark.asyncio
    async def test_oneshot_routes_through_fallback_wrapper(self, monkeypatch):
        """Verify that the oneshot path calls chat_structured_with_fallback,
        not bare chat_structured — so guardrail/locale errors are handled."""
        from fichero.llm import GuardrailViolationError

        module = importlib.import_module("fichero.workflows.tools.extract_all")

        fallback_calls = []

        async def fake_chat_structured_with_fallback(**kwargs):
            fallback_calls.append(kwargs)
            return module._Extraction(
                people=[
                    module._Person(
                        name="Beatriz",
                        verb="lived in",
                        object="Cali",
                        source_text="Beatriz lived in Cali.",
                    )
                ]
            )

        async def bare_chat_structured_raises(**kwargs):
            raise GuardrailViolationError("guardrail refused")

        container = SimpleNamespace(id="doc-1", updated_at=None)
        fake_db = SimpleNamespace(
            query=lambda *_args, **_kwargs: [],
            save=lambda *_args, **_kwargs: None,
        )

        monkeypatch.setattr(
            module, "chat_structured_with_fallback", fake_chat_structured_with_fallback
        )
        monkeypatch.setattr(module, "chat_structured", bare_chat_structured_raises)
        monkeypatch.setattr(module, "_resolve_write_target", lambda *_: container)
        monkeypatch.setattr(module, "_write_kg_rows", lambda *_args, **_kw: None)
        monkeypatch.setattr(module.db_manager, "get_database", lambda *_: fake_db)

        result = await module.extract_all(
            {"text": "Beatriz lived in Cali.", "extraction_mode": "oneshot"},
            {
                "library_path": "/tmp/fichero-test",
                "selected_doc_ids": ["doc-1"],
            },
            LLMConfig(provider="apple", model="apple"),
        )

        # fallback wrapper was called (not bare chat_structured)
        assert fallback_calls, "chat_structured_with_fallback was never called"
        # result has entities — chunk did NOT fail
        assert result["value"].get("people"), "expected people entities in result"
        # no systemic error set
        assert "error" not in result
