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


# =============================================================================
# The fallback walks the SAME ladder resolution does (team-lead, 2026-09-05)
#
# I argued this case could not arise: if the bar's choice reaches every step,
# a step only runs Apple when Apple was chosen. Wrong on two paths — a preset
# that declares accepts_model_override == false keeps its pinned Apple node
# while the run carries a cloud choice, and a step whose capability
# disqualifies the run's choice resolves its own tier, which can be Apple. In
# both, a refusal happens while the user HAS named a model.
# =============================================================================


def test_the_runs_choice_is_preferred_over_a_configured_tier():
    from fichero_server.llm import (
        _run_choice_fallback_config,
        clear_run_model_choice,
        set_run_model_choice,
    )

    token = set_run_model_choice("anthropic", "claude-sonnet-latest")
    try:
        target = _run_choice_fallback_config(APPLE)
    finally:
        clear_run_model_choice(token)

    assert target is not None
    assert target.provider == "anthropic"
    assert target.model == "claude-sonnet-latest"


def test_no_run_choice_means_the_tier_walk_is_untouched():
    from fichero_server.llm import _run_choice_fallback_config

    assert _run_choice_fallback_config(APPLE) is None


def test_the_run_choice_is_not_a_retry_into_the_model_that_just_failed():
    """A 'fallback' to the failing model is a retry into the same refusal."""
    from fichero_server.llm import (
        _run_choice_fallback_config,
        clear_run_model_choice,
        set_run_model_choice,
    )

    token = set_run_model_choice("apple", "apple-intelligence")
    try:
        assert _run_choice_fallback_config(APPLE) is None
    finally:
        clear_run_model_choice(token)


def test_a_choice_that_cannot_do_the_work_is_not_a_rescue():
    """apple-vision is a recognition route: it returns the page's own text and
    ignores the prompt, so it can no more rescue a text step than serve one."""
    from fichero_server.llm import (
        _run_choice_fallback_config,
        clear_run_model_choice,
        set_run_model_choice,
    )

    token = set_run_model_choice("apple", "apple-vision")
    try:
        assert _run_choice_fallback_config(APPLE) is None
    finally:
        clear_run_model_choice(token)


def test_the_choice_does_not_outlive_its_run():
    """One run's choice must never steer another run's fallback."""
    from fichero_server.llm import (
        clear_run_model_choice,
        run_model_choice,
        set_run_model_choice,
    )

    token = set_run_model_choice("anthropic", "claude-sonnet-latest")
    assert run_model_choice() == ("anthropic", "claude-sonnet-latest")
    clear_run_model_choice(token)
    assert run_model_choice() is None


def test_an_empty_choice_is_no_choice():
    from fichero_server.llm import (
        clear_run_model_choice,
        run_model_choice,
        set_run_model_choice,
    )

    token = set_run_model_choice("", "  ")
    try:
        assert run_model_choice() is None
    finally:
        clear_run_model_choice(token)
