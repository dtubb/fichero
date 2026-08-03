"""#4496 — a transcription node must not store the model's commentary.

The paleography ensemble stored 4,518 characters beginning "Step-by-step
reasoning:" in an artifact typed `transcription`, on every node, green, with
`error: None`. The measured CER for the final pass was 5.41 — the output was
five times the length of the page's gold transcription and unrelated to it.

Per #4487: a stripper nobody has watched strip is a guess. Every shape
`strip_reasoning` claims to handle has a fixture proving it FIRES, and every
pattern that turns a run red has one proving it raises. The false-positive
tests matter equally — a refusal that fires on a real transcription of a real
page is worse than the bug, because it refuses work that succeeded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fichero_server.workflows.tools.llm_prompting import (
    THINKING_MODES,
    build_thinking_preamble,
)
from fichero_server.workflows.tools.transcription_output import (
    TranscriptionCommentaryError,
    commentary_reason,
    sanitize_transcription,
    strip_reasoning,
)

# A real fragment, taken from a stored artifact in ICANH-Andagoya-Gemini.
REAL_TRANSCRIPTION = (
    "[Script: itálica; century: 19th (1867); language: Spanish]\n"
    "[Sello: ESTADOS UU. DE COLOMBIA • SOBERANO DEL CAUCA]\n"
    "En la Ciudad de Nóvita a veintiuno de Enero del\n"
    "año de mil ochocientos cincuenta i nueve, compareció ante\n"
    "mí Adolfo Hurtado, notario público"
)


# =============================================================================
# strip_reasoning — one fixture per shape, each proving the strip FIRES
# =============================================================================


@pytest.mark.parametrize(
    "shape,raw",
    [
        ("think", f"<think>The hand is itálica.</think>\n{REAL_TRANSCRIPTION}"),
        ("thinking", f"<thinking>Let me look.</thinking>\n{REAL_TRANSCRIPTION}"),
        ("thought", f"<thought>rn vs m here.</thought>\n{REAL_TRANSCRIPTION}"),
        ("reasoning", f"<reasoning>Comparing drafts.</reasoning>\n{REAL_TRANSCRIPTION}"),
        ("scratchpad", f"<scratchpad>notes</scratchpad>\n{REAL_TRANSCRIPTION}"),
        ("analysis", f"<analysis>19th century.</analysis>\n{REAL_TRANSCRIPTION}"),
        ("uppercase tag", f"<THINK>Reasoning here.</THINK>\n{REAL_TRANSCRIPTION}"),
        ("tag with attrs", f'<think type="deep">why</think>\n{REAL_TRANSCRIPTION}'),
        ("multiline block", f"<think>\nline one\nline two\n</think>\n{REAL_TRANSCRIPTION}"),
        ("trailing block", f"{REAL_TRANSCRIPTION}\n<think>afterthought</think>"),
        ("two blocks", f"<think>a</think>{REAL_TRANSCRIPTION}<think>b</think>"),
    ],
)
def test_strip_reasoning_removes_each_delimited_shape(shape, raw):
    """Every tag family in _REASONING_TAGS is actually stripped."""
    out = strip_reasoning(raw)
    assert out == REAL_TRANSCRIPTION, f"{shape} was not stripped: {out!r}"


def test_strip_reasoning_prefers_an_explicit_answer_wrapper():
    raw = f"<think>reasoning</think><answer>{REAL_TRANSCRIPTION}</answer>"
    assert strip_reasoning(raw) == REAL_TRANSCRIPTION


@pytest.mark.parametrize("tag", ["answer", "final", "transcription", "output"])
def test_strip_reasoning_unwraps_each_answer_tag(tag):
    raw = f"Some preamble.\n<{tag}>{REAL_TRANSCRIPTION}</{tag}>"
    assert strip_reasoning(raw) == REAL_TRANSCRIPTION


def test_strip_reasoning_drops_an_unclosed_reasoning_block():
    """A truncated response: the model opened <think> and never closed it.

    Everything after the tag is reasoning. Keeping it would store commentary;
    keeping nothing is correct, and sanitize_transcription then refuses the
    empty result rather than saving it.
    """
    assert strip_reasoning("<think>I will start by looking at the ductus") == ""


def test_strip_reasoning_removes_a_whole_output_code_fence():
    raw = f"```\n{REAL_TRANSCRIPTION}\n```"
    assert strip_reasoning(raw) == REAL_TRANSCRIPTION


def test_strip_reasoning_removes_a_language_tagged_fence():
    raw = f"```text\n{REAL_TRANSCRIPTION}\n```"
    assert strip_reasoning(raw) == REAL_TRANSCRIPTION


def test_strip_reasoning_leaves_a_clean_transcription_byte_identical():
    """The no-op case. A stripper that rewrites good output is a corrupter."""
    assert strip_reasoning(REAL_TRANSCRIPTION) == REAL_TRANSCRIPTION


def test_strip_reasoning_keeps_an_interior_fence():
    """A fence around PART of the output is content, not a wrapper."""
    raw = f"{REAL_TRANSCRIPTION}\n```\ntabla\n```\nmás texto"
    assert strip_reasoning(raw) == raw


# =============================================================================
# commentary_reason — the refusal. Each pattern proven to fire, by name.
# =============================================================================


@pytest.mark.parametrize(
    "expected_reason,raw",
    [
        # Observed verbatim in the #3905 ensemble run.
        ("step-by-step-reasoning", "Step-by-step reasoning:\nThe manuscript appears"),
        ("step-by-step-reasoning", "**Step-by-step reasoning:** the hand is"),
        ("reasoning-header", "Reasoning: the script is procesal"),
        ("reasoning-header", "**Analysis:**\nthe page is blotted"),
        ("reasoning-heading", "### Reasoning\nThe hand is procesal"),
        ("reasoning-heading", "## Approach\nFirst compare the drafts"),
        ("transcription-plan", "To transcribe this document, I will first examine"),
        # Fixed assistant idioms.
        ("first-person-plan", "I will begin by identifying the script family."),
        ("first-person-plan", "I'll start with the marginalia."),
        ("first-person-plan", "Let me work through this page."),
        ("first-person-plan", "I can see a stamp in the upper left."),
        ("answer-preamble", "Here is the transcription of the manuscript:\nEn la"),
        ("answer-preamble", "Below is the corrected text:\nEn la Ciudad"),
        ("assistant-filler", "Okay, let's look at this page."),
        ("assistant-filler", "Certainly! En la Ciudad de Nóvita"),
        # Description instead of transcription, and refusals.
        ("image-description", "This image shows a 19th-century notarial document"),
        ("image-description", "The scan appears to be a Spanish legal record"),
        ("refusal", "I'm sorry, I cannot read this handwriting."),
        ("refusal", "I cannot transcribe this document."),
        ("unstripped-reasoning-tag", "</think>\nEn la Ciudad"),
    ],
)
def test_commentary_reason_names_each_shape(expected_reason, raw):
    assert commentary_reason(raw) == expected_reason


@pytest.mark.parametrize(
    "why,raw",
    [
        ("gemini ensemble output", REAL_TRANSCRIPTION),
        ("script classification line", "[Script: cortesana; hand size: small]\nEn la Ciudad"),
        ("explicit no-text token", "[sin texto]"),
        ("uncertainty markers", "[ilegible] de la mina [uncertain] Oeste"),
        ("apple vision garbage is still transcription-shaped",
         "Partida N= 28. Fililo de la mina\nOeste, hasta el punto de partidos."),
        ("multipage prefix", "--- Page 1 ---\n\n[Script: itálica]\nderecho de rejistro"),
        ("english diary page", "SUNDAY, JANUARY 7, 1923\nPay Day.\nMail arrived at noon."),
        ("all-caps header", "MEMORANDA\nNo. | Date | Subject"),
        ("marginalia convention", "[M.N.] Ojo\nEn la Ciudad de Nóvita"),
        ("a page that merely contains 'here is'",
         "En la Ciudad de Nóvita, here is recorded the sale"),
        ("a document about an image", "This is a true copy of the original deed."),
        ("first word 'first'", "First Baptist Church of Novita, 1859"),
    ],
)
def test_commentary_reason_stays_silent_on_real_transcriptions(why, raw):
    """False positives fail real runs over real pages. This is the tight half."""
    assert commentary_reason(raw) is None, f"false positive on {why}: {raw!r}"


# =============================================================================
# sanitize_transcription — strip, then refuse
# =============================================================================


def test_sanitize_raises_on_the_exact_shape_that_shipped():
    """The #4496 artifact: reasoning stored as `artifact_type=transcription`."""
    raw = (
        "Step-by-step reasoning:\n"
        "1. The script is itálica, 19th century.\n"
        "2. The first line reads ambiguously; rn vs m.\n"
        "3. I will prefer the reading consistent with the notarial formula.\n"
    )
    with pytest.raises(TranscriptionCommentaryError) as exc:
        sanitize_transcription(raw)
    message = str(exc.value)
    assert "step-by-step-reasoning" in message
    assert "Step-by-step reasoning" in message, "the message must quote what it saw"


def test_sanitize_strips_delimited_reasoning_and_returns_the_transcription():
    """The recoverable case: reasoning was delimited, so the run stays green."""
    raw = f"<think>Comparing the three drafts.</think>\n{REAL_TRANSCRIPTION}"
    assert sanitize_transcription(raw) == REAL_TRANSCRIPTION


def test_sanitize_raises_when_stripping_leaves_nothing():
    with pytest.raises(TranscriptionCommentaryError, match="only reasoning"):
        sanitize_transcription("<think>I will look at the ductus</think>")


def test_sanitize_raises_when_commentary_follows_a_stripped_block():
    """Stripping is not a licence to keep whatever survives."""
    raw = "<think>plan</think>\nHere is the transcription:\n\nEn la Ciudad"
    with pytest.raises(TranscriptionCommentaryError, match="answer-preamble"):
        sanitize_transcription(raw)


def test_sanitize_passes_a_clean_transcription_through_unchanged():
    assert sanitize_transcription(REAL_TRANSCRIPTION) == REAL_TRANSCRIPTION


@pytest.mark.parametrize("empty", ["", "   ", "\n\n"])
def test_sanitize_leaves_empty_output_to_the_existing_empty_handling(empty):
    """process_vision already retries and then fails loudly on empty (#837).

    Raising here would report the wrong cause for the same failure.
    """
    assert sanitize_transcription(empty) == empty


def test_sanitize_is_wired_into_both_transcription_tools():
    """The validator only protects the archive if the tools actually call it.

    A sanitizer that exists but is not passed as `postprocess_text` is exactly
    the `parse_thinking_response` situation again: a stripper nobody runs.
    """
    from fichero_server.workflows.tools import transcribe, transcribe_review

    for module in (transcribe, transcribe_review):
        source = Path(module.__file__).read_text()
        assert "postprocess_text=sanitize_transcription" in source, (
            f"{module.__name__} does not pass sanitize_transcription to "
            f"process_vision — commentary would be stored, not refused"
        )


# =============================================================================
# The preamble that asked for the commentary in the first place
# =============================================================================


@pytest.mark.parametrize("mode", ["short", "medium", "long"])
def test_thinking_preamble_demands_delimited_reasoning(mode):
    """The root cause: the preamble asked for undelimited "show your reasoning"
    and was prepended to a prompt forbidding commentary."""
    preamble = build_thinking_preamble(mode)
    assert "<think>" in preamble and "</think>" in preamble
    assert "nothing else" in preamble


def test_thinking_preamble_off_is_empty():
    assert build_thinking_preamble("off") == ""


def test_thinking_preamble_rejects_a_mode_outside_the_enum():
    """The ensemble asked for `thinking_mode: "high"` on its two review nodes.

    `high` is not in the enum, so it silently produced NO preamble — the nodes
    declaring the deepest thinking got none at all. A config value that does
    nothing must not read as one that works.
    """
    with pytest.raises(ValueError, match="high"):
        build_thinking_preamble("high")


def test_a_preamble_plus_prompt_round_trip_is_strippable():
    """End to end: what the framework asks for, a model complies with, and the
    sanitizer recovers — without the transcription being touched."""
    build_thinking_preamble("medium")  # what the model was told
    model_output = f"<think>Three drafts disagree on line 4.</think>\n{REAL_TRANSCRIPTION}"
    assert sanitize_transcription(model_output) == REAL_TRANSCRIPTION


# =============================================================================
# The preset that requested it
# =============================================================================


PRESET_DIR = (
    Path(__file__).resolve().parents[3]
    / "src" / "fichero_server" / "resources" / "default_workflows"
)


def _node_configs(preset_path: Path):
    data = json.loads(preset_path.read_text())
    for node in data.get("nodes") or []:
        yield preset_path.name, node.get("id"), node.get("config") or {}


def test_no_shipped_preset_requests_a_thinking_mode_outside_the_enum():
    """Guardrail for the `high` class of defect across every preset.

    build_thinking_preamble now raises on an unknown mode, so a preset shipping
    one would fail at RUN time on a real page. Catching it here means it fails
    at TEST time instead.
    """
    offenders = [
        f"{name}:{node_id} thinking_mode={config['thinking_mode']!r}"
        for path in sorted(PRESET_DIR.glob("*.json"))
        for name, node_id, config in _node_configs(path)
        if "thinking_mode" in config and config["thinking_mode"] not in THINKING_MODES
    ]
    assert not offenders, (
        "presets requesting a thinking_mode outside "
        f"{THINKING_MODES}: {offenders}"
    )


def test_paleography_ensemble_asks_no_node_for_an_apparatus():
    """t3 asked for "a diplomatic transcription followed by a concise apparatus
    of unresolved readings" — commentary, appended, stored in the artifact and
    fed to t4 as its prior transcription.

    The output validator is anchored to the START of the text and would NOT
    catch a trailing apparatus. This is the half that has to be fixed in the
    preset, and this test is what keeps it fixed.
    """
    preset = PRESET_DIR / "transcribe_paleography_ensemble.json"
    for _, node_id, config in _node_configs(preset):
        prompt = (config.get("prompt") or "").lower()
        assert "apparatus" not in prompt, (
            f"node {node_id} asks for an apparatus appended to the "
            f"transcription; that text is stored as the transcription"
        )
