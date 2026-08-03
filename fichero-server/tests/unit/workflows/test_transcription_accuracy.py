"""A character error rate must be exact, labelled, and refusable (#3905).

The properties, each with a test:

1. Identical text is 0.0 under every policy, and a known edit distance gives
   the exact expected rate. Every expected value here is hand-computed in the
   test from the definition — never copied from what the implementation
   returned, which would only prove it is consistent with itself.
2. A number is meaningless without its normalisation policy, so each policy
   moves the rate in the documented direction on text that differs in exactly
   that dimension.
3. Refusals outrank the feature. A gold for a page the run never saw, a run
   that failed, a step that produced nothing, and a length mismatch that says
   "different page" all come back ``comparable=False`` with ``cer=None``.
4. The ensemble's per-tier artifacts are each scored, because "how far off is
   the cheap tier" is the question #3905 actually asks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.workflows.run_comparison import RunComparisonError, RunSide
from fichero_server.workflows.transcription_accuracy import (
    ACCENT_BLIND,
    CER_DEFINITION,
    DIPLOMATIC,
    LAYOUT_INSENSITIVE,
    LENIENT,
    MAX_CER_CHARS,
    POLICIES,
    ReferenceTranscription,
    character_error_rate,
    normalize,
    resolve_policy,
    score_run_against_reference,
    score_texts_under_policies,
    with_expansions,
)

_T0 = datetime(2026, 8, 3, 12, 0, 0, tzinfo=timezone.utc)

GOLD_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures/paleography/dialogo_lengua_page_18.txt"
)


def _artifact(**overrides):
    base = dict(
        id="art-1",
        artifact_type="transcription",
        document_id="doc-1",
        source_document_id=None,
        run_id="thread-1",
        workflow_id="wf-1",
        step_name="t4",
        provider="anthropic",
        model="claude-vision-large",
        sequence=4,
        created_at=_T0,
        content="hola",
        data=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run(**overrides) -> RunSide:
    base = dict(
        thread_id="thread-1",
        workflow_id="wf-1",
        workflow_name="Transcribe Paleography (Ensemble + Deep Review)",
        status="completed",
        steps=(),
        artifacts=(_artifact(),),
        error=None,
        resolved_scope={"resolved_ids": ["doc-1"]},
        duration_ms=1000,
    )
    base.update(overrides)
    return RunSide(**base)


def _reference(**overrides) -> ReferenceTranscription:
    base = dict(
        document_id="doc-1",
        text="hola",
        source="DILE, page-aligned transcription, rows 143-147 (CC-BY-SA 4.0)",
        document_name="dialogo_lengua_page_18.pdf",
    )
    base.update(overrides)
    return ReferenceTranscription(**base)


# ---------------------------------------------------------------------------
# The rate: exact, hand-computed values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("policy_name", sorted(POLICIES))
def test_identical_text_scores_zero_under_every_policy(policy_name: str) -> None:
    score = character_error_rate(
        "enel tþo q́ el eʃcriuio, yental caʃo",
        "enel tþo q́ el eʃcriuio, yental caʃo",
        policy=policy_name,
    )
    assert score.cer == 0.0
    assert score.distance == 0
    assert score.policy == policy_name


def test_one_substitution_over_six_characters() -> None:
    # "abcdef" -> "abcdxf": one substitution, e -> x. Reference is 6 chars.
    # CER = 1 / 6.
    score = character_error_rate("abcdef", "abcdxf", policy=DIPLOMATIC)
    assert score.distance == 1
    assert score.reference_chars == 6
    assert score.cer == pytest.approx(1 / 6)


def test_one_deletion_over_four_characters() -> None:
    # "hola" -> "hla": the o is dropped. One deletion, reference 4 chars.
    score = character_error_rate("hola", "hla", policy=DIPLOMATIC)
    assert score.distance == 1
    assert score.cer == pytest.approx(0.25)


def test_one_insertion_over_four_characters() -> None:
    # "hola" -> "holaa": one insertion. Normalised by the REFERENCE length (4),
    # not by the longer string (5) — 0.25, not 0.2. This test is the one that
    # pins the choice of denominator.
    score = character_error_rate("hola", "holaa", policy=DIPLOMATIC)
    assert score.distance == 1
    assert score.reference_chars == 4
    assert score.hypothesis_chars == 5
    assert score.cer == pytest.approx(0.25)


def test_five_substitutions_over_ten_characters() -> None:
    # The archive's own example. "Ospina Oca" against "Ocampo Oca", aligned:
    #   O s p i n a _ O c a
    #   O c a m p o _ O c a
    # The O, the space and the trailing "Oca" match; the five characters
    # between them all differ. Five substitutions over a ten-character
    # reference, CER = 0.5. Note how badly eyeballing this misleads — the two
    # surnames look like a near-miss and are half the page wrong.
    score = character_error_rate("Ospina Oca", "Ocampo Oca", policy=DIPLOMATIC)
    assert score.distance == 5
    assert score.reference_chars == 10
    assert score.cer == pytest.approx(0.5)


def test_a_deletion_and_an_insertion_together() -> None:
    # "abcdef" -> "bcdefx": "bcdef" aligns, the leading a is deleted and a
    # trailing x is inserted. Two edits over a six-character reference.
    score = character_error_rate("abcdef", "bcdefx", policy=DIPLOMATIC)
    assert score.distance == 2
    assert score.cer == pytest.approx(2 / 6)


def test_rate_exceeds_one_and_is_not_clamped() -> None:
    # A one-character reference against five characters: four insertions.
    # 4 / 1 = 4.0. Clamping to 1.0 would hide a run that emitted commentary
    # instead of a transcription.
    score = character_error_rate("a", "abcde", policy=DIPLOMATIC)
    assert score.distance == 4
    assert score.cer == pytest.approx(4.0)


def test_every_score_carries_its_definition_and_policy() -> None:
    score = character_error_rate("hola", "hola")
    assert score.definition == CER_DEFINITION
    assert "NORMALISED REFERENCE" in score.definition
    assert score.policy == LAYOUT_INSENSITIVE.name
    assert score.policy_description
    assert score.policy_flags["collapse_whitespace"] is True


def test_default_policy_is_layout_insensitive() -> None:
    assert resolve_policy(None) is LAYOUT_INSENSITIVE


def test_unknown_policy_is_refused_not_defaulted() -> None:
    with pytest.raises(RunComparisonError, match="unknown normalisation policy"):
        character_error_rate("hola", "hola", policy="loose-ish")


# ---------------------------------------------------------------------------
# Normalisation policies move the number in the documented direction
# ---------------------------------------------------------------------------


def test_nfc_is_always_applied_so_encoding_is_not_an_error() -> None:
    # "é" precomposed (U+00E9) against "e" + combining acute (U+0301). Same
    # reading, different bytes. Under the STRICTEST policy this must still be
    # zero: it is an encoding difference, not a transcription error.
    score = character_error_rate("café", "café", policy=DIPLOMATIC)
    assert score.distance == 0
    assert score.cer == 0.0


def test_line_wrapping_counts_under_diplomatic_and_not_under_default() -> None:
    reference = "el eʃcriuio\nyental caʃo"
    hypothesis = "el eʃcriuio yental caʃo"
    strict = character_error_rate(reference, hypothesis, policy=DIPLOMATIC)
    default = character_error_rate(reference, hypothesis, policy=LAYOUT_INSENSITIVE)
    # One newline substituted for one space.
    assert strict.distance == 1
    assert strict.cer > 0
    assert default.cer == 0.0


def test_case_and_punctuation_count_until_lenient() -> None:
    reference = "Ospina, dixo."
    hypothesis = "ospina dixo"
    default = character_error_rate(reference, hypothesis, policy=LAYOUT_INSENSITIVE)
    lenient = character_error_rate(reference, hypothesis, policy=LENIENT)
    # O->o, plus the comma and full stop deleted: three edits over 13 chars.
    assert default.distance == 3
    assert default.cer == pytest.approx(3 / 13)
    assert lenient.cer == 0.0


def test_accents_count_until_accent_blind() -> None:
    reference = "aconteçio deʃpues dela paβion"
    hypothesis = "acontecio despues dela paβion"
    lenient = character_error_rate(reference, hypothesis, policy=LENIENT)
    blind = character_error_rate(reference, hypothesis, policy=ACCENT_BLIND)
    # ç -> c and ʃ -> s. The cedilla is a combining mark and vanishes under
    # accent-blind; the long s is a LETTER and stays an error under both,
    # which is the point — dropping accents must not silently drop letters.
    assert lenient.cer > blind.cer > 0
    assert blind.distance == 1


def test_each_policy_is_looser_than_the_last_on_text_that_differs_in_all() -> None:
    reference = "Él dixo:\n«Ospina»"
    hypothesis = "el dixo Ospina"
    rates = [
        s.cer
        for s in score_texts_under_policies(
            reference,
            hypothesis,
            [DIPLOMATIC, LAYOUT_INSENSITIVE, LENIENT, ACCENT_BLIND],
        )
    ]
    assert rates == sorted(rates, reverse=True), rates
    assert rates[0] > rates[-1]
    assert rates[-1] == 0.0


def test_expansions_are_opt_in_and_named_in_the_policy() -> None:
    # The brevigraph q́ (q + combining acute) expands to "que" in this hand.
    # No shipped policy does this by default, because an expansion table is an
    # editorial claim about a specific scribe.
    reference = "por q́ el dize"
    hypothesis = "por que el dize"
    default = character_error_rate(reference, hypothesis, policy=LAYOUT_INSENSITIVE)
    assert default.cer > 0
    assert default.policy_flags["expansion_count"] == 0

    policy = with_expansions(LAYOUT_INSENSITIVE, {"q́": "que"})
    expanded = character_error_rate(reference, hypothesis, policy=policy)
    assert expanded.cer == 0.0
    assert "expansions(1)" in expanded.policy
    assert expanded.policy_flags["expansion_count"] == 1


def test_normalize_leaves_long_s_alone() -> None:
    # ʃ is a letterform, not a diacritic. Nothing folds it, including the
    # loosest policy — a transcription that modernises it has made a choice a
    # historian may want counted.
    for policy in POLICIES.values():
        assert "ʃ" in normalize("eʃcriuio", policy)


# ---------------------------------------------------------------------------
# Denominator and size refusals
# ---------------------------------------------------------------------------


def test_empty_reference_is_refused_not_scored_as_zero() -> None:
    with pytest.raises(RunComparisonError, match="no denominator"):
        character_error_rate("   \n  ", "anything", policy=LAYOUT_INSENSITIVE)


def test_text_beyond_the_exact_limit_is_refused() -> None:
    long_text = "a" * (MAX_CER_CHARS + 1)
    with pytest.raises(RunComparisonError, match="too long for an exact"):
        character_error_rate(long_text, long_text, policy=DIPLOMATIC)


# ---------------------------------------------------------------------------
# Scoring a run: what gets refused
# ---------------------------------------------------------------------------


def test_scores_a_completed_run_against_the_gold() -> None:
    result = score_run_against_reference(
        _reference(text="hola mundo"),
        _run(artifacts=(_artifact(content="hola mvndo"),)),
    )
    assert result.comparable is True
    assert result.incomparable_reason is None
    assert result.cer == pytest.approx(1 / 10)
    assert result.primary_step_name == "t4"
    assert result.policy == LAYOUT_INSENSITIVE.name
    assert result.reference_source.startswith("DILE")


def test_failed_run_is_refused_not_scored() -> None:
    result = score_run_against_reference(
        _reference(),
        _run(status="failed", error="vision provider timed out"),
    )
    assert result.comparable is False
    assert result.cer is None
    assert "failed" in result.incomparable_reason
    assert "vision provider timed out" in result.incomparable_reason


def test_running_run_is_refused() -> None:
    result = score_run_against_reference(_reference(), _run(status="running"))
    assert result.comparable is False
    assert result.cer is None
    assert "still running" in result.incomparable_reason


def test_gold_for_a_page_the_run_never_resolved_is_refused() -> None:
    # The honesty rule: a rate against a page the run did not transcribe would
    # be a confident number about nothing.
    result = score_run_against_reference(
        _reference(document_id="doc-99"),
        _run(resolved_scope={"resolved_ids": ["doc-1", "doc-2"]}),
    )
    assert result.comparable is False
    assert result.cer is None
    assert "doc-99" in result.incomparable_reason
    assert "never resolved that document" in result.incomparable_reason


def test_a_page_child_is_covered_even_though_scope_names_the_parent() -> None:
    # The case that matters in practice and the one a scope-first check gets
    # wrong: the user selects a PDF, the ensemble splits it and writes the
    # transcription against the PAGE child, so resolved_scope lists the parent
    # and never the page. The artifact is direct evidence the page was
    # transcribed and outranks the scope, or the whole feature refuses every
    # real run.
    result = score_run_against_reference(
        _reference(document_id="page-1", text="hola"),
        _run(
            resolved_scope={"resolved_ids": ["parent-doc"]},
            artifacts=(_artifact(document_id="page-1", content="hola"),),
        ),
    )
    assert result.comparable is True
    assert result.cer == 0.0


def test_run_with_no_transcription_for_the_page_is_refused() -> None:
    result = score_run_against_reference(
        _reference(),
        _run(
            resolved_scope=None,
            artifacts=(_artifact(artifact_type="entities", data={"people": []}),),
        ),
    )
    assert result.comparable is False
    assert result.cer is None
    assert "no transcription for document doc-1" in result.incomparable_reason
    assert "no transcription artifacts at all" in result.incomparable_reason


def test_run_that_transcribed_other_pages_says_which() -> None:
    result = score_run_against_reference(
        _reference(document_id="doc-1"),
        _run(
            resolved_scope=None,
            artifacts=(_artifact(id="art-2", document_id="doc-7"),),
        ),
    )
    assert result.comparable is False
    assert "doc-7" in result.incomparable_reason
    assert "1 other document" in result.incomparable_reason


def test_empty_artifact_is_refused_rather_than_scored_one_point_zero() -> None:
    result = score_run_against_reference(
        _reference(text="hola mundo"),
        _run(artifacts=(_artifact(content="   "),)),
    )
    assert result.comparable is False
    assert result.cer is None
    assert "no text" in result.incomparable_reason


def test_grossly_mismatched_lengths_are_refused_as_a_different_page() -> None:
    # One page of gold against a run that transcribed a whole volume.
    result = score_run_against_reference(
        _reference(text="hola mundo"),
        _run(artifacts=(_artifact(content="hola mundo " * 60),)),
    )
    assert result.comparable is False
    assert result.cer is None
    assert "not plausibly the same page" in result.incomparable_reason


def test_unrecorded_scope_does_not_by_itself_block_scoring() -> None:
    # #4384 predates resolved_scope. Unknown is not the same claim as
    # mismatched; the artifact lookup still has to find the page.
    result = score_run_against_reference(
        _reference(text="hola"),
        _run(resolved_scope=None, artifacts=(_artifact(content="hola"),)),
    )
    assert result.comparable is True
    assert result.cer == 0.0


def test_reference_without_a_source_is_rejected_outright() -> None:
    with pytest.raises(RunComparisonError, match="no source"):
        score_run_against_reference(_reference(source="  "), _run())


def test_reference_without_a_document_is_rejected_outright() -> None:
    with pytest.raises(RunComparisonError, match="names no document"):
        score_run_against_reference(_reference(document_id=""), _run())


# ---------------------------------------------------------------------------
# Per-tier calibration and the diff
# ---------------------------------------------------------------------------


def test_every_tier_is_scored_separately_with_its_provider_and_model() -> None:
    run = _run(
        artifacts=(
            _artifact(
                id="art-small",
                step_name="t1a",
                sequence=1,
                provider="mlx",
                model="qwen2-vl-2b",
                content="ola mund",
            ),
            _artifact(
                id="art-final",
                step_name="t4",
                sequence=4,
                provider="anthropic",
                model="claude-vision-large",
                content="hola mundo",
            ),
        )
    )
    result = score_run_against_reference(_reference(text="hola mundo"), run)

    assert [s.artifact.step_name for s in result.scored] == ["t1a", "t4"]
    small, final = result.scored
    assert small.artifact.model == "qwen2-vl-2b"
    # "hola mundo" -> "ola mund": drop the leading h and the trailing o.
    # Two edits over ten reference characters.
    assert small.score.distance == 2
    assert small.score.cer == pytest.approx(0.2)
    assert final.score.cer == 0.0
    # The headline rate is the run's FINAL reading, not its cheapest draft.
    assert result.cer == 0.0
    assert result.primary_artifact_id == "art-final"


def test_one_bad_tier_does_not_make_the_run_incomparable() -> None:
    run = _run(
        artifacts=(
            _artifact(id="art-small", step_name="t1a", sequence=1, content=""),
            _artifact(id="art-final", step_name="t4", sequence=4, content="hola"),
        )
    )
    result = score_run_against_reference(_reference(text="hola"), run)
    assert result.scored[0].comparable is False
    assert result.scored[0].score is None
    assert result.comparable is True
    assert result.cer == 0.0


def test_the_result_names_which_line_disagrees_not_only_a_rate() -> None:
    result = score_run_against_reference(
        _reference(text="linea uno\nfirmado Ospina\nlinea tres"),
        _run(
            artifacts=(
                _artifact(content="linea uno\nfirmado Ocampo\nlinea tres"),
            )
        ),
    )
    assert result.comparable is True
    diff = result.scored[0].text_diff
    assert diff is not None
    assert diff.differences[0].left_lines == ["firmado Ospina"]
    assert diff.differences[0].right_lines == ["firmado Ocampo"]
    assert diff.differences[0].left_start_line == 2


# ---------------------------------------------------------------------------
# The one real gold text in the repository
# ---------------------------------------------------------------------------


def test_real_gold_fixture_scores_zero_against_itself() -> None:
    gold = GOLD_FIXTURE.read_text(encoding="utf-8")
    assert gold.strip(), "the DILE page-18 fixture must not be empty"
    score = character_error_rate(gold, gold, policy=DIPLOMATIC)
    assert score.cer == 0.0
    assert score.reference_chars <= MAX_CER_CHARS


def test_real_gold_fixture_policies_are_ordered_on_a_modernised_reading() -> None:
    # A plausible wrong reading of the real page: the long s modernised, the
    # brevigraph expanded, the accents dropped.
    gold = GOLD_FIXTURE.read_text(encoding="utf-8")
    modernised = (
        gold.replace("ʃ", "s").replace("q́", "que").replace("ç", "c")
    )
    diplomatic = character_error_rate(gold, modernised, policy=DIPLOMATIC)
    blind = character_error_rate(gold, modernised, policy=ACCENT_BLIND)
    assert diplomatic.cer > 0
    # Accent-blind absorbs the cedilla; the long s and the expansion remain
    # errors, so the number drops but does not vanish.
    assert 0 < blind.cer < diplomatic.cer
