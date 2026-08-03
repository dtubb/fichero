"""Score a transcription against a human-verified reference (#3905).

#4341 answers "where do two runs disagree". That is agreement, not accuracy:
two runs can agree perfectly and both be wrong. #3905 asks the other question —
how far is this transcription from what a paleographer actually read — and it
needs two things #4341 does not have.

**A gold transcription is not a run.** It has no thread id, no steps, no
duration, no resolved scope. Manufacturing a ``RunSide`` for it with
``status="completed"`` would fabricate exactly the claim that #4341's refusal
machinery exists to protect, so this module compares a *text* against a run
instead of pretending the text is one. Everything else is reused:
``summarise_side``, ``incomparable_reason``, ``artifact_ref``, ``order_key``
and ``diff_text`` all come from ``run_comparison``, so there is one definition
of "this side cannot be trusted" and one line-level diff, not two that drift.

**CER did not exist in this codebase.** The paleography fixture asserted a
``difflib`` similarity *ratio* with an unlabelled case-fold. A ratio is not a
character error rate, and ``difflib`` does not compute a minimal edit distance
at all. This module computes a real one.

What a number here must always carry
------------------------------------

CER is reported inconsistently in the literature — normalised by reference
length or by the longer string, computed on raw text or on aggressively folded
text — so a bare number is not a measurement. Every score returned here names
its definition (``CER_DEFINITION``) and its normalisation policy, and there is
no code path that emits a float without them.

Normalisation is a JUDGEMENT, not a detail. For Spanish colonial paleography,
accents, abbreviation brevigraphs and letter case are precisely what a
transcription gets wrong; folding them away does not "clean up" the number, it
answers a different question. So the policy is a parameter with four named
settings, and the honest default (``layout-insensitive``) folds only the one
thing that is not a reading of the hand: how the text was wrapped into lines.

What gets refused rather than scored
------------------------------------

A confident 0.03 against the wrong page is worse than no number. These all
return ``comparable=False`` with a named reason and ``cer=None``:

* the run did not complete (same reason strings as #4341);
* the run resolved a document set that does not include the page the reference
  is for — the gold does not cover what was transcribed;
* the run produced no transcription artifact for that page;
* the artifact is empty — a step that produced nothing scores 1.0 on the
  arithmetic, and 1.0 reads as "transcribed it, got everything wrong";
* reference and hypothesis differ in length so grossly that they are not
  plausibly the same page (a one-page gold against a whole-book run);
* either side is longer than the exact algorithm can handle — an approximation
  presented as a CER is the plausible-looking wrong output this refuses to be.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from fichero_server.llm.multilingual import levenshtein_distance
from fichero_server.workflows.run_comparison import (
    ArtifactRef,
    RunComparisonError,
    RunSide,
    SideSummary,
    TextDiff,
    artifact_ref,
    diff_text,
    incomparable_reason,
    order_key,
    summarise_side,
)

#: Artifact type holding transcribed page text. Matches the contract enforced
#: by ``scripts/check_artifact_type_contract.py``.
TRANSCRIPTION_ARTIFACT_TYPE = "transcription"

#: Exactly what the float means. Attached to every score, because "CER 0.04"
#: with no definition cannot be compared against anyone else's 0.04.
CER_DEFINITION = (
    "CER = Levenshtein distance in CHARACTERS (unit cost for each insertion, "
    "deletion and substitution) between the normalised reference and the "
    "normalised hypothesis, divided by the length in characters of the "
    "NORMALISED REFERENCE. Not divided by the longer of the two, and not by "
    "the unnormalised text. Unbounded above: a hypothesis longer than the "
    "reference can score above 1.0, and is deliberately not clamped, because "
    "a clamp would hide a run that emitted a page of commentary."
)

#: The exact distance is O(reference x hypothesis) in pure Python. A manuscript
#: page transcription runs 1-3k characters; well past that the honest move is
#: to refuse rather than to return a heuristic wearing a CER's name.
MAX_CER_CHARS = 5000

#: Beyond this ratio between normalised lengths the two texts are not
#: plausibly transcriptions of the same page — the usual cause is a one-page
#: gold scored against a run over a whole volume.
DEFAULT_MAX_LENGTH_RATIO = 5.0


# ---------------------------------------------------------------------------
# Normalisation policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizationPolicy:
    """What a CER computed under this policy does and does not count.

    Applied to BOTH sides, in this fixed order:

    1. Unicode NFC. Always, under every policy, and not optional: ``é`` typed
       as one code point and ``é`` typed as ``e`` + combining acute are the
       same reading, and counting them as an error would measure the encoding
       rather than the transcription.
    2. Line endings normalised to ``\\n``. Also always: CRLF is a file format,
       not a reading.
    3. ``expansions``, longest key first, on both sides.
    4. ``fold_case``
    5. ``strip_accents``
    6. ``strip_punctuation``
    7. ``collapse_whitespace``
    """

    name: str
    description: str
    collapse_whitespace: bool = False
    fold_case: bool = False
    strip_accents: bool = False
    strip_punctuation: bool = False
    #: Abbreviation expansions applied to both sides, e.g. ``(("q́", "que"),)``.
    #: Empty under every shipped policy. An expansion table is an editorial
    #: claim about a specific hand; one applied silently by default would be an
    #: unattributed edit to a historian's gold text, so the caller supplies it
    #: and ``expansions_applied`` reports whether it fired.
    expansions: tuple[tuple[str, str], ...] = ()

    def flags(self) -> dict[str, Any]:
        return {
            "collapse_whitespace": self.collapse_whitespace,
            "fold_case": self.fold_case,
            "strip_accents": self.strip_accents,
            "strip_punctuation": self.strip_punctuation,
            "expansion_count": len(self.expansions),
        }


DIPLOMATIC = NormalizationPolicy(
    name="diplomatic",
    description=(
        "Strictest. NFC and line endings only. Case, accents, punctuation, "
        "spacing and every brevigraph count as read. Use this to report what "
        "the model actually produced."
    ),
)

LAYOUT_INSENSITIVE = NormalizationPolicy(
    name="layout-insensitive",
    description=(
        "Default. Runs of whitespace, including line breaks, collapse to one "
        "space. Where the model chose to wrap a line is a rendering decision, "
        "not a reading of the hand; case, accents and punctuation still count "
        "because in this material they ARE the reading."
    ),
    collapse_whitespace=True,
)

LENIENT = NormalizationPolicy(
    name="lenient",
    description=(
        "Layout-insensitive plus case folding and punctuation removal. "
        "Answers 'did it get the letters', accepting modernised pointing. "
        "Will flatter a transcription that mangles the pointing."
    ),
    collapse_whitespace=True,
    fold_case=True,
    strip_punctuation=True,
)

ACCENT_BLIND = NormalizationPolicy(
    name="accent-blind",
    description=(
        "Lenient plus accent and combining-mark removal. Loosest shipped "
        "policy. Its use is subtraction: the gap between this and lenient is "
        "how much of the error is purely diacritics."
    ),
    collapse_whitespace=True,
    fold_case=True,
    strip_accents=True,
    strip_punctuation=True,
)

POLICIES: dict[str, NormalizationPolicy] = {
    p.name: p for p in (DIPLOMATIC, LAYOUT_INSENSITIVE, LENIENT, ACCENT_BLIND)
}

DEFAULT_POLICY_NAME = LAYOUT_INSENSITIVE.name


def resolve_policy(
    policy: NormalizationPolicy | str | None,
) -> NormalizationPolicy:
    """A policy object from a name, refusing unknown names rather than
    silently falling back to the default — a caller who asked for
    ``diplomatic`` and got ``layout-insensitive`` would be told a wrong number.
    """
    if policy is None:
        return LAYOUT_INSENSITIVE
    if isinstance(policy, NormalizationPolicy):
        return policy
    try:
        return POLICIES[policy]
    except KeyError:
        known = ", ".join(sorted(POLICIES))
        raise RunComparisonError(
            f"unknown normalisation policy {policy!r}; known policies: {known}"
        ) from None


def with_expansions(
    policy: NormalizationPolicy | str | None,
    expansions: Mapping[str, str],
) -> NormalizationPolicy:
    """A copy of ``policy`` carrying an abbreviation table, named so the
    reported policy says the table was in play."""
    base = resolve_policy(policy)
    if not expansions:
        return base
    ordered = tuple(
        sorted(expansions.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    )
    return NormalizationPolicy(
        name=f"{base.name}+expansions({len(ordered)})",
        description=(
            f"{base.description} Plus {len(ordered)} caller-supplied "
            "abbreviation expansion(s), applied to both sides."
        ),
        collapse_whitespace=base.collapse_whitespace,
        fold_case=base.fold_case,
        strip_accents=base.strip_accents,
        strip_punctuation=base.strip_punctuation,
        expansions=ordered,
    )


def normalize(text: str, policy: NormalizationPolicy) -> str:
    """Apply ``policy`` in the documented order."""
    out = unicodedata.normalize("NFC", text or "")
    out = out.replace("\r\n", "\n").replace("\r", "\n")

    for source, target in policy.expansions:
        if source:
            out = out.replace(source, target)

    if policy.fold_case:
        out = out.casefold()

    if policy.strip_accents:
        decomposed = unicodedata.normalize("NFD", out)
        out = unicodedata.normalize(
            "NFC",
            "".join(ch for ch in decomposed if not unicodedata.combining(ch)),
        )

    if policy.strip_punctuation:
        out = "".join(
            ch for ch in out if not unicodedata.category(ch).startswith("P")
        )

    if policy.collapse_whitespace:
        out = " ".join(out.split())

    return out


# ---------------------------------------------------------------------------
# The rate itself
# ---------------------------------------------------------------------------


@dataclass
class CerScore:
    """A character error rate that carries what produced it."""

    policy: str
    policy_description: str
    policy_flags: dict[str, Any]
    distance: int
    reference_chars: int
    hypothesis_chars: int
    cer: float
    definition: str = CER_DEFINITION


def character_error_rate(
    reference: str,
    hypothesis: str,
    *,
    policy: NormalizationPolicy | str | None = None,
) -> CerScore:
    """CER of ``hypothesis`` against ``reference`` under ``policy``.

    Raises ``RunComparisonError`` rather than returning a number when the
    reference normalises to nothing (there is no denominator, and 0/0 is not
    "perfect") or when either side exceeds ``MAX_CER_CHARS``.
    """
    resolved = resolve_policy(policy)
    ref = normalize(reference, resolved)
    hyp = normalize(hypothesis, resolved)

    if not ref:
        raise RunComparisonError(
            f"reference is empty after {resolved.name} normalisation; CER has "
            "no denominator, and 0 errors over 0 characters is not a score"
        )
    if len(ref) > MAX_CER_CHARS or len(hyp) > MAX_CER_CHARS:
        raise RunComparisonError(
            f"text too long for an exact character error rate: reference "
            f"{len(ref)} chars, hypothesis {len(hyp)} chars, limit "
            f"{MAX_CER_CHARS}. Refusing rather than returning an "
            "approximation labelled as CER; score page by page instead"
        )

    distance = levenshtein_distance(ref, hyp)
    return CerScore(
        policy=resolved.name,
        policy_description=resolved.description,
        policy_flags=resolved.flags(),
        distance=distance,
        reference_chars=len(ref),
        hypothesis_chars=len(hyp),
        cer=distance / len(ref),
    )


# ---------------------------------------------------------------------------
# Scoring a run
# ---------------------------------------------------------------------------


@dataclass
class ReferenceTranscription:
    """A human-verified reading of one page, and where it came from."""

    document_id: str
    text: str
    #: Provenance. Required and non-empty: a gold text with no attribution is
    #: an anonymous opinion, and every number derived from it inherits that.
    source: str
    document_name: str | None = None


@dataclass
class ScoredTranscription:
    """One transcription artifact measured against the reference."""

    artifact: ArtifactRef
    comparable: bool
    incomparable_reason: str | None = None
    score: CerScore | None = None
    text_diff: TextDiff | None = None


@dataclass
class ReferenceComparison:
    """How close a run came to a paleographer's reading of one page."""

    run: SideSummary
    reference_document_id: str
    reference_document_name: str | None
    reference_source: str
    policy: str
    policy_description: str
    comparable: bool
    incomparable_reason: str | None = None
    #: The headline rate: the run's FINAL transcription of the page. None
    #: whenever it could not be measured, so an absent number can never be
    #: read as a good one.
    cer: float | None = None
    primary_artifact_id: str | None = None
    primary_step_name: str | None = None
    #: Every transcription artifact for the page, each scored separately. The
    #: ensemble writes one per tier and each artifact row carries its provider
    #: and model, so this list IS the cheap-tier calibration #3905 asks for.
    scored: list[ScoredTranscription] = field(default_factory=list)
    definition: str = CER_DEFINITION


def _run_reason(run: RunSide) -> str | None:
    return incomparable_reason("Scored", run)


def _no_coverage_reason(reference: ReferenceTranscription, run: RunSide) -> str:
    """Why this run cannot be said to have transcribed the reference's page.

    Called only once the artifact lookup has already come up empty. That
    ordering matters: the ensemble transcribes PAGE children while
    ``resolved_scope`` records the parent document the user selected, so a
    scope that does not list the page is routine and proves nothing. A
    transcription artifact for the page is direct evidence of coverage and
    outranks the scope; the scope is only useful here for saying WHY there is
    none.
    """
    scope = run.resolved_scope
    ids = scope.get("resolved_ids") if isinstance(scope, dict) else None
    base = (
        f"Run {run.thread_id} produced no transcription for document "
        f"{reference.document_id}"
    )
    if isinstance(ids, list) and str(reference.document_id) not in {
        str(i) for i in ids
    }:
        return (
            f"{base}; it never resolved that document either (it resolved "
            f"{len(ids)}, none of them this page). A rate against a page the "
            "run did not transcribe would describe nothing."
        )
    elsewhere = sorted(
        {
            str(getattr(a, "document_id", "") or "")
            for a in run.artifacts
            if str(getattr(a, "artifact_type", "") or "")
            == TRANSCRIPTION_ARTIFACT_TYPE
        }
    )
    if elsewhere:
        return (
            f"{base}; it transcribed {len(elsewhere)} other document(s): "
            + ", ".join(elsewhere)
            + "."
        )
    return f"{base}; it produced no transcription artifacts at all."


def _transcriptions(run: RunSide, document_id: str) -> list[Any]:
    found = [
        a
        for a in run.artifacts
        if str(getattr(a, "document_id", "") or "") == document_id
        and str(getattr(a, "artifact_type", "") or "") == TRANSCRIPTION_ARTIFACT_TYPE
    ]
    found.sort(key=order_key)
    return found


def _score_one(
    artifact: Any,
    reference: ReferenceTranscription,
    policy: NormalizationPolicy,
    document_names: dict[str, str],
    max_length_ratio: float,
) -> ScoredTranscription:
    ref = artifact_ref(artifact, document_names)
    content = getattr(artifact, "content", None) or ""

    if not content.strip():
        return ScoredTranscription(
            artifact=ref,
            comparable=False,
            incomparable_reason=(
                f"Artifact {ref.artifact_id} holds no text. An empty "
                "transcription scores 1.0 arithmetically, which reads as "
                "'read the page and got every character wrong' rather than "
                "'this step produced nothing'."
            ),
        )

    normalised_ref = normalize(reference.text, policy)
    normalised_hyp = normalize(content, policy)
    if normalised_ref and normalised_hyp:
        longer = max(len(normalised_ref), len(normalised_hyp))
        shorter = min(len(normalised_ref), len(normalised_hyp))
        if longer > shorter * max_length_ratio:
            return ScoredTranscription(
                artifact=ref,
                comparable=False,
                incomparable_reason=(
                    f"Reference is {len(normalised_ref)} characters and "
                    f"artifact {ref.artifact_id} is {len(normalised_hyp)} "
                    f"under the {policy.name} policy — a ratio past "
                    f"{max_length_ratio:g}:1. These are not plausibly the "
                    "same page, so no rate is reported."
                ),
            )

    try:
        score = character_error_rate(reference.text, content, policy=policy)
    except RunComparisonError as exc:
        return ScoredTranscription(
            artifact=ref, comparable=False, incomparable_reason=str(exc)
        )

    # The rate says how far off; the diff says which line to go and look at.
    # #4341's point exactly, and the reason this is not just a float.
    diff = diff_text(reference.text, content)
    return ScoredTranscription(
        artifact=ref,
        comparable=True,
        score=score,
        text_diff=diff if diff.difference_count else None,
    )


def score_run_against_reference(
    reference: ReferenceTranscription,
    run: RunSide,
    *,
    policy: NormalizationPolicy | str | None = None,
    document_names: dict[str, str] | None = None,
    max_length_ratio: float = DEFAULT_MAX_LENGTH_RATIO,
) -> ReferenceComparison:
    """Measure a run's transcription of one page against a verified reading.

    Refuses rather than answers wrongly, in #4341's shape: ``comparable`` is
    False with a reason naming the cause, and ``cer`` is None — never 0.0 and
    never omitted such that a default reads as success.
    """
    if not reference.document_id:
        raise RunComparisonError(
            "the reference names no document; a transcription can only be "
            "scored against the page it is a reading of"
        )
    if not (reference.source or "").strip():
        raise RunComparisonError(
            "the reference carries no source; an unattributed gold text "
            "cannot stand behind a published error rate"
        )
    if not (reference.text or "").strip():
        raise RunComparisonError(
            f"the reference for document {reference.document_id} is empty"
        )

    resolved = resolve_policy(policy)
    names = dict(document_names or {})
    summary = summarise_side(run)

    def refuse(why: str) -> ReferenceComparison:
        return ReferenceComparison(
            run=summary,
            reference_document_id=reference.document_id,
            reference_document_name=reference.document_name
            or names.get(reference.document_id),
            reference_source=reference.source,
            policy=resolved.name,
            policy_description=resolved.description,
            comparable=False,
            incomparable_reason=why,
        )

    blocked = _run_reason(run)
    if blocked:
        return refuse(blocked)

    artifacts = _transcriptions(run, reference.document_id)
    if not artifacts:
        return refuse(_no_coverage_reason(reference, run))

    scored = [
        _score_one(a, reference, resolved, names, max_length_ratio)
        for a in artifacts
    ]
    # The last artifact by (sequence, created_at) is the run's final reading —
    # the ensemble's consensus pass rather than one of its drafts. The earlier
    # ones stay in `scored` with their provider and model, which is how a
    # cheap tier gets measured against the same gold in the same call.
    primary = scored[-1]

    return ReferenceComparison(
        run=summary,
        reference_document_id=reference.document_id,
        reference_document_name=reference.document_name
        or names.get(reference.document_id),
        reference_source=reference.source,
        policy=resolved.name,
        policy_description=resolved.description,
        comparable=primary.comparable,
        incomparable_reason=primary.incomparable_reason,
        cer=primary.score.cer if primary.score else None,
        primary_artifact_id=primary.artifact.artifact_id,
        primary_step_name=primary.artifact.step_name,
        scored=scored,
    )


def score_texts_under_policies(
    reference: str,
    hypothesis: str,
    policies: Sequence[NormalizationPolicy | str],
) -> list[CerScore]:
    """The same pair under several policies, for reporting the spread.

    A single number invites "the CER is 0.08"; four of them make it obvious
    that the answer depends on what you agreed to stop counting.
    """
    return [
        character_error_rate(reference, hypothesis, policy=p) for p in policies
    ]
