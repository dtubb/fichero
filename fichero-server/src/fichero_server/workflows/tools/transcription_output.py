"""Sanitize + validate model output before it is stored as a transcription (#4496).

The paleography ensemble stored the model's *commentary* in artifacts whose
``artifact_type`` is ``transcription``: 4,518 characters beginning
``Step-by-step reasoning:`` on a page whose gold transcription is under a
thousand. Every node reported ``✓ Completed`` with ``error: None``, and the
measured CER for the final pass was 5.41 — five pages of something that is not
the page.

Three things had to be true at once for that to happen, and this module
addresses the last two:

1. ``build_thinking_preamble`` prepended "Show your reasoning, then provide
   your answer" to the same prompt that then said "output ONLY the
   transcription". The framework asked for the commentary the tool forbade.
   Fixed at the source in ``llm_prompting.py`` by delimiting the reasoning.

2. **Nothing stripped it.** The only stripper, ``parse_thinking_response``,
   matches ``<think>``/``<answer>`` — one tag family, which Gemini does not
   emit. ``strip_reasoning`` below matches the shapes models actually produce.

3. **Nothing refused it.** A node that returns commentary must fail, not
   store. ``sanitize_transcription`` raises, and because it is wired as
   ``process_vision(postprocess_text=...)`` — the seam #4329 built for exactly
   this — the raise fails that file loudly and saves no artifact.

The prompt is not the enforcement. The prompt already forbade commentary and
was ignored; prompts are requests. The enforcement is here, in code that
inspects the output.

Design note on the two halves. ``strip_reasoning`` is deliberately generous:
delimited reasoning is unambiguous and recoverable, so remove it and keep the
transcription. ``commentary_reason`` is deliberately tight: it fires the
refusal, and a false refusal fails a real run over a real page. Every pattern
in it was observed in a stored artifact or is a fixed assistant idiom that no
transcription of a manuscript opens with.
"""

from __future__ import annotations

import re


# =============================================================================
# Delimited reasoning — recoverable, so strip it
# =============================================================================

# Tag families that actually appear in the wild. `parse_thinking_response`
# knew only the first one, which is why the ensemble output survived intact.
_REASONING_TAGS = ("think", "thinking", "thought", "reasoning", "scratchpad", "analysis")

_TAG_BLOCK_RES = tuple(
    re.compile(rf"<{tag}\b[^>]*>.*?</{tag}\s*>", re.DOTALL | re.IGNORECASE)
    for tag in _REASONING_TAGS
)

# An unclosed opening tag — the model started reasoning and the response was
# cut off, or it never closed the block. Everything from the tag on is
# reasoning; there is no transcription after it to keep.
_UNCLOSED_TAG_RES = tuple(
    re.compile(rf"<{tag}\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)
    for tag in _REASONING_TAGS
)

# Explicit answer wrapper: if present it names the transcription exactly.
_ANSWER_RE = re.compile(
    r"<(answer|final|transcription|output)\b[^>]*>(.*?)</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)

# A fence wrapping the WHOLE output. Models add one despite instructions; the
# same shape convert.py strips for the same reason (#4329).
_WHOLE_FENCE_RE = re.compile(r"\A```[a-zA-Z0-9_+-]*\s*\n(.*?)\n?```\s*\Z", re.DOTALL)


def strip_reasoning(text: str) -> str:
    """Remove delimited reasoning, returning the transcription it wrapped.

    Handles, in order: an explicit ``<answer>``-style wrapper (which names the
    transcription outright), every reasoning tag family in ``_REASONING_TAGS``
    both closed and unclosed, and a code fence around the whole output.

    Undelimited commentary is NOT stripped here — there is no reliable
    boundary between "reasoning prose" and "transcription prose", and guessing
    one would silently truncate a real transcription. That case is refused by
    ``sanitize_transcription`` instead.
    """
    out = (text or "").strip()
    if not out:
        return out

    answer = _ANSWER_RE.search(out)
    if answer:
        out = answer.group(2).strip()
    else:
        for rx in _TAG_BLOCK_RES:
            out = rx.sub("", out)
        out = out.strip()
        for rx in _UNCLOSED_TAG_RES:
            out = rx.sub("", out)
        out = out.strip()

    fenced = _WHOLE_FENCE_RE.match(out)
    if fenced:
        out = fenced.group(1).strip()

    return out


# =============================================================================
# Undelimited commentary — unrecoverable, so refuse it
# =============================================================================

# Each entry is (name, regex). Names appear in the raised message so a red run
# says WHICH shape it saw, not just "bad output".
#
# Anchored to the start of the output: this is about what the model opened
# with, and a transcription that opens with an assistant idiom is not a
# transcription. Matching mid-text would fire on manuscripts that legitimately
# contain phrases like "here is" in their own prose.
_COMMENTARY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Observed verbatim in stored ensemble output.
    ("step-by-step-reasoning", re.compile(r"\A\**\s*step[-\s]?by[-\s]?step\b", re.I)),
    ("reasoning-header", re.compile(r"\A\**\s*(reasoning|analysis|thinking|thought process)\b\s*\**\s*:", re.I)),
    ("reasoning-heading", re.compile(r"\A#{1,6}\s*\**\s*(reasoning|analysis|thinking|step|approach|observations?|notes?)\b", re.I)),
    ("transcription-plan", re.compile(r"\A\s*to transcribe\b", re.I)),
    # Fixed assistant idioms. No transcription of a page opens with these.
    ("first-person-plan", re.compile(r"\A\s*(i will|i'll|i am going to|let me|first,?\s+(i|let)|i can see|i notice)\b", re.I)),
    ("answer-preamble", re.compile(r"\A\s*(here is|here's|below is|the following is)\b[^\n]{0,120}?\b(transcription|text|reading)\b", re.I)),
    ("assistant-filler", re.compile(r"\A\s*(okay|ok|sure|certainly|of course|understood|got it|alright)\b\s*[,.!—-]", re.I)),
    # Vision-model description-instead-of-transcription, and refusals.
    ("image-description", re.compile(r"\A\s*(this|the)\s+(image|photo|photograph|scan|picture)\b[^\n]{0,60}?\b(is|shows|appears|contains|depicts)\b", re.I)),
    ("refusal", re.compile(r"\A\s*(i'm sorry|i am sorry|i cannot|i can't|unfortunately,? i)\b", re.I)),
    # A reasoning tag that survived stripping (malformed nesting, stray close).
    ("unstripped-reasoning-tag", re.compile(r"\A\s*</?(?:think|thinking|thought|reasoning|scratchpad)\b", re.I)),
)


def commentary_reason(text: str) -> str | None:
    """Name the commentary shape this output opens with, or None if it reads
    like a transcription.

    Tight by construction — this is what turns a run red.
    """
    head = (text or "").lstrip()
    if not head:
        return None
    for name, rx in _COMMENTARY_PATTERNS:
        if rx.search(head):
            return name
    return None


class TranscriptionCommentaryError(ValueError):
    """A transcription step returned commentary instead of a transcription."""


def sanitize_transcription(text: str) -> str:
    """Strip delimited reasoning; refuse output that is still commentary.

    Wired as ``process_vision(postprocess_text=...)``, so the raise fails that
    file loudly and no artifact is written — the run goes red instead of green
    with 4,518 characters of reasoning stored as a transcription (#4496).

    Empty input is returned untouched: ``process_vision`` has its own
    empty-response retry and its own loud empty failure, and duplicating that
    judgement here would report the wrong cause.
    """
    if not (text or "").strip():
        return text

    out = strip_reasoning(text)

    if not out.strip():
        raise TranscriptionCommentaryError(
            "Transcription step returned only reasoning — nothing remained "
            "after stripping the delimited reasoning block. Refusing to save "
            "an empty transcription artifact."
        )

    reason = commentary_reason(out)
    if reason is not None:
        preview = " ".join(out.strip()[:160].split())
        raise TranscriptionCommentaryError(
            f"Transcription step returned commentary, not a transcription "
            f"({reason}). Refusing to save it as a transcription artifact. "
            f"Output began: {preview!r}. "
            f"If this node sets thinking_mode, the reasoning belongs inside "
            f"<think>...</think> so it can be stripped."
        )

    return out
