"""A substitution the user did not choose must be visible (2026-09-05).

Daniel: "if it's sensitive content, that's not a failure — that's a thing to
surface, so the user can try a different model (or you can try the large model
by default)."

That ruling bends the never-silently-substitute rule, and visibility is the
entire price of the exemption. A fallback nobody can see is the original
defect wearing a helpful face: the run returns an answer from a model the user
never picked, and nothing in the record says so. These tests hold the price.

Two conditions, deliberately not alike: Apple declining the MATERIAL (colonial
legal records describing violence trip this legitimately) is a judgement about
the document, and a broken macOS model asset is the operating system failing.
The user's next move differs, so the label and the sentence differ.
"""

from __future__ import annotations

import pytest

from fichero_server.llm import (
    AppleSystemModelMissingError,
    GuardrailViolationError,
    LLMConfig,
    UnsupportedLocaleError,
    _record_model_fallback,
    collect_model_fallbacks,
    fallback_condition_for,
    model_fallback_summary,
)

APPLE = LLMConfig(provider="apple", model="apple-intelligence")
SONNET = LLMConfig(provider="anthropic", model="claude-sonnet-latest")


# =============================================================================
# The two conditions are distinguishable
# =============================================================================


def test_a_content_refusal_is_labelled_as_policy_not_breakage():
    assert fallback_condition_for(GuardrailViolationError("declined")) == "content_policy"


@pytest.mark.parametrize(
    "error",
    [AppleSystemModelMissingError("asset gone"), UnsupportedLocaleError("no es-419")],
    ids=["broken-os-asset", "unsupported-locale"],
)
def test_infrastructure_conditions_are_labelled_as_unavailable(error):
    assert fallback_condition_for(error) == "system_unavailable"


def test_an_unrelated_error_is_neither():
    assert fallback_condition_for(RuntimeError("boom")) == "other"


def test_a_content_refusal_does_not_read_as_a_document_defect():
    """The message a person sees must not blame the archive."""
    with collect_model_fallbacks() as bucket:
        _record_model_fallback(
            from_config=APPLE,
            to_config=SONNET,
            error=GuardrailViolationError("declined"),
            kind="structured",
        )
    reason = bucket[0]["reason"]
    assert "declined this content" in reason
    assert "not an error in the document" in reason


# =============================================================================
# The substitution is RECORDED, and names both models
# =============================================================================


def test_the_record_names_the_model_that_was_asked_and_the_one_that_answered():
    with collect_model_fallbacks() as bucket:
        _record_model_fallback(
            from_config=APPLE, to_config=SONNET,
            error=GuardrailViolationError("declined"), kind="structured",
        )

    entry = bucket[0]
    assert entry["from_provider"] == "apple"
    assert entry["from_model"] == "apple-intelligence"
    assert entry["to_provider"] == "anthropic"
    assert entry["to_model"] == "claude-sonnet-latest"
    assert entry["kind"] == "structured"


def test_the_summary_is_a_sentence_naming_both_models():
    """This is the line that reaches the run's execution log."""
    with collect_model_fallbacks() as bucket:
        _record_model_fallback(
            from_config=APPLE, to_config=SONNET,
            error=GuardrailViolationError("declined"), kind="structured",
        )
    summary = model_fallback_summary(bucket)
    assert summary is not None
    assert "apple" in summary
    assert "anthropic/claude-sonnet-latest" in summary
    assert "→ ran on" in summary


def test_no_fallback_means_no_line_at_all():
    """An absent line beats a line announcing that nothing happened."""
    assert model_fallback_summary([]) is None


def test_several_substitutions_are_all_named():
    """A chain can substitute more than once; none may be dropped."""
    other = LLMConfig(provider="openai", model="gpt-5")
    with collect_model_fallbacks() as bucket:
        _record_model_fallback(
            from_config=APPLE, to_config=SONNET,
            error=GuardrailViolationError("declined"), kind="structured",
        )
        _record_model_fallback(
            from_config=APPLE, to_config=other,
            error=AppleSystemModelMissingError("asset gone"), kind="chat",
        )
    summary = model_fallback_summary(bucket)
    assert len(bucket) == 2
    assert "claude-sonnet-latest" in summary
    assert "gpt-5" in summary


def test_collection_is_scoped_and_does_not_leak_between_runs():
    """One run's substitution must never appear in another run's record."""
    with collect_model_fallbacks() as first:
        _record_model_fallback(
            from_config=APPLE, to_config=SONNET,
            error=GuardrailViolationError("declined"), kind="chat",
        )
    with collect_model_fallbacks() as second:
        pass

    assert len(first) == 1
    assert second == []


def test_recording_outside_a_collector_is_harmless():
    """A call made with no run in scope logs and returns — it must not raise:
    an accounting concern may never fail the work it is accounting for."""
    _record_model_fallback(
        from_config=APPLE, to_config=SONNET,
        error=GuardrailViolationError("declined"), kind="chat",
    )
