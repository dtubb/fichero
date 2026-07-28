"""Deterministic KG paragraph rendering with citation markers.

This module keeps the composition logic in one place so routes and other
surfaces can render KnowledgeClaim rows the same way.
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence

from pydantic import BaseModel, Field

from fichero.knowledge._common import order_statement_parts, render_statement
from fichero.models.knowledge import KnowledgeClaim

_SUPERSCRIPT_TRANSLATION = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


class ParagraphStyle(str, Enum):
    """Supported paragraph render styles."""

    narrative = "narrative"
    list = "list"
    footnoted = "footnoted"


class ParagraphMarker(BaseModel):
    """Marker offsets in the rendered text."""

    marker_index: int
    start: int
    end: int
    token: str


class ParagraphCitation(BaseModel):
    """Source metadata for one rendered citation marker."""

    marker_index: int
    claim_id: str
    source_document_id: str
    source_page_label: str | None = None
    source_excerpt: str | None = None
    source_bbox: list[float] | None = None
    source_char_start: int | None = None
    source_char_end: int | None = None


class ParagraphRenderResponse(BaseModel):
    """Response body for KG paragraph rendering."""

    style: ParagraphStyle
    text: str
    citations: list[ParagraphCitation] = Field(default_factory=list)
    markers: list[ParagraphMarker] = Field(default_factory=list)


class ParagraphRenderRequest(BaseModel):
    """Request body for KG paragraph rendering."""

    claim_ids: list[str] = Field(min_length=1)
    style: ParagraphStyle = ParagraphStyle.narrative


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _normalize(value: str | None) -> str:
    return _collapse_whitespace(value or "").casefold()


def _sentence_end(text: str) -> str:
    stripped = text.rstrip()
    if not stripped:
        return ""
    if stripped.endswith((".", "!", "?")):
        return stripped
    return f"{stripped}."


def _combine_phrases(phrases: list[str]) -> str:
    cleaned = [_collapse_whitespace(phrase).rstrip(".") for phrase in phrases if phrase]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _claim_subject(claim: KnowledgeClaim) -> str | None:
    subject = claim.subject_canonical or claim.svo_subject
    if subject:
        return _collapse_whitespace(subject)
    return None


def _claim_verb(claim: KnowledgeClaim) -> str | None:
    verb = claim.predicate_verb or claim.svo_verb
    if verb:
        return _collapse_whitespace(verb)
    return None


def _claim_object(claim: KnowledgeClaim) -> str | None:
    obj = claim.object_phrase or claim.svo_object
    if obj:
        return _collapse_whitespace(obj)
    return None


def _claim_sentence(claim: KnowledgeClaim) -> str:
    subject = _claim_subject(claim)
    verb = _claim_verb(claim)
    obj = _claim_object(claim)
    # Two or more roles present makes a sentence; a lone role does not, so it
    # falls through to the claim's own text below. The previous four explicit
    # branches (S V O / V O / S V / S O) are exactly that rule (#4172).
    parts = order_statement_parts(subject, verb, obj)
    if len(parts) >= 2:
        return _sentence_end(" ".join(parts))

    text = _collapse_whitespace(claim.text)
    if text:
        return _sentence_end(text)

    if subject:
        return _sentence_end(subject)
    if verb:
        return _sentence_end(verb)
    if obj:
        return _sentence_end(obj)
    return ""


def _is_mergeable_pair(left: KnowledgeClaim, right: KnowledgeClaim) -> bool:
    left_subject = _claim_subject(left)
    right_subject = _claim_subject(right)
    left_verb = _claim_verb(left)
    right_verb = _claim_verb(right)
    left_object = _claim_object(left)
    right_object = _claim_object(right)
    return bool(
        left_subject
        and right_subject
        and left_verb
        and right_verb
        and left_object
        and right_object
        and _normalize(left_subject) == _normalize(right_subject)
        and _normalize(left_verb) == _normalize(right_verb)
    )


def _group_claims(claims: Sequence[KnowledgeClaim]) -> list[list[KnowledgeClaim]]:
    groups: list[list[KnowledgeClaim]] = []
    i = 0
    while i < len(claims):
        claim = claims[i]
        if i + 1 >= len(claims) or not _is_mergeable_pair(claim, claims[i + 1]):
            groups.append([claim])
            i += 1
            continue

        subject = _claim_subject(claim)
        verb = _claim_verb(claim)
        group = [claim]
        i += 1
        while i < len(claims) and _is_mergeable_pair(claim, claims[i]):
            next_claim = claims[i]
            if (
                _normalize(_claim_subject(next_claim)) == _normalize(subject)
                and _normalize(_claim_verb(next_claim)) == _normalize(verb)
            ):
                group.append(next_claim)
                i += 1
                continue
            break
        groups.append(group)
    return groups


def _superscript_number(value: int) -> str:
    return str(value).translate(_SUPERSCRIPT_TRANSLATION)


def _marker_token(index: int, style: ParagraphStyle) -> str:
    if style == ParagraphStyle.narrative:
        return _superscript_number(index)
    return f"[{index}]"


class _TextBuilder:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0

    def append(self, text: str) -> tuple[int, int]:
        start = self.length
        self.parts.append(text)
        self.length += len(text)
        return start, self.length

    def build(self) -> str:
        return "".join(self.parts)


def _citation_for_claim(marker_index: int, claim: KnowledgeClaim) -> ParagraphCitation:
    return ParagraphCitation(
        marker_index=marker_index,
        claim_id=claim.id,
        source_document_id=claim.source_document_id,
        source_page_label=claim.source_page_label,
        source_excerpt=claim.source_excerpt or claim.text,
        source_bbox=claim.source_bbox,
        source_char_start=claim.source_char_start,
        source_char_end=claim.source_char_end,
    )


def _render_sentence(
    builder: _TextBuilder,
    sentence: str,
    citation_indices: list[int],
    style: ParagraphStyle,
) -> list[ParagraphMarker]:
    markers: list[ParagraphMarker] = []
    text = _sentence_end(sentence)
    builder.append(text)
    if citation_indices:
        builder.append(" ")
        for pos, citation_index in enumerate(citation_indices):
            if pos:
                builder.append(" ")
            token = _marker_token(citation_index, style)
            start, end = builder.append(token)
            markers.append(
                ParagraphMarker(
                    marker_index=citation_index,
                    start=start,
                    end=end,
                    token=token,
                )
            )
    return markers


def _render_claim_list_item(
    builder: _TextBuilder,
    claim: KnowledgeClaim,
    marker_index: int,
) -> ParagraphMarker:
    token = _marker_token(marker_index, ParagraphStyle.list)
    sentence = _claim_sentence(claim)
    prefix = f"- {sentence} "
    start, _ = builder.append(f"{prefix}{token}")
    builder.append("\n")
    builder.append(
        f"  source: {claim.source_document_id}"
        f"{f' p. {claim.source_page_label}' if claim.source_page_label else ''}"
    )
    if claim.source_excerpt:
        builder.append(f"\n  excerpt: {claim.source_excerpt}")
    builder.append("\n")
    return ParagraphMarker(
        marker_index=marker_index,
        start=start + len(prefix),
        end=start + len(prefix) + len(token),
        token=token,
    )


def render_paragraph_claims(
    claims: Sequence[KnowledgeClaim],
    *,
    style: ParagraphStyle = ParagraphStyle.narrative,
) -> ParagraphRenderResponse:
    """Render claims into deterministic prose plus citation metadata."""

    builder = _TextBuilder()
    citations: list[ParagraphCitation] = []
    markers: list[ParagraphMarker] = []
    rendered_marker_index = 1

    if style == ParagraphStyle.list:
        for index, claim in enumerate(claims):
            if index:
                builder.append("\n")
            citation = _citation_for_claim(rendered_marker_index, claim)
            citations.append(citation)
            markers.append(_render_claim_list_item(builder, claim, rendered_marker_index))
            rendered_marker_index += 1
        return ParagraphRenderResponse(
            style=style,
            text=builder.build().rstrip("\n"),
            citations=citations,
            markers=markers,
        )

    for group_index, group in enumerate(_group_claims(claims)):
        if group_index:
            builder.append(" ")

        if len(group) > 1 and _is_mergeable_pair(group[0], group[1]):
            subject = _claim_subject(group[0]) or ""
            verb = _claim_verb(group[0]) or ""
            objects = [_claim_object(claim) or "" for claim in group]
            # Same ordering helper as the single-claim path, with the merged
            # object phrase standing in for one object (#4172).
            sentence = render_statement(subject, verb, _combine_phrases(objects))
        else:
            sentence = _claim_sentence(group[0])

        citation_indices: list[int] = []
        for claim in group:
            citation = _citation_for_claim(rendered_marker_index, claim)
            citations.append(citation)
            citation_indices.append(rendered_marker_index)
            rendered_marker_index += 1

        markers.extend(_render_sentence(builder, sentence, citation_indices, style))

    text = builder.build()
    if style == ParagraphStyle.footnoted and citations:
        builder.append("\n\nFootnotes:\n")
        for citation in citations:
            builder.append(
                f"{citation.marker_index}. {citation.source_document_id}"
                f"{f' p. {citation.source_page_label}' if citation.source_page_label else ''}"
            )
            if citation.source_excerpt:
                builder.append(f" — {citation.source_excerpt}")
            builder.append("\n")
        text = builder.build().rstrip("\n")

    return ParagraphRenderResponse(
        style=style,
        text=text,
        citations=citations,
        markers=markers,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
