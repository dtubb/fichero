"""Unit tests for extract_all's systemic-error classifier (#1060).

extract_all must fail-fast when a workflow run is systemically broken
(e.g. no $large configured → every Apple-Intelligence fallback re-raises
the same error on every page) instead of grinding through all pages and
returning an empty "successful" catalogue. Genuinely-partial failures (a
minority of sparse pages) must still warn-and-continue.
"""

from __future__ import annotations

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
