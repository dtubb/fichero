"""Guided-generation schemas for the on-device tier (#4667/#4670 consumers).

The two jobs lane-svo-quality asked for — naming a claim's subject, and
normalizing its date and place — are exactly the shape Apple's constrained
decoder is good at: small, closed, structurally guaranteed output, free and
offline. They are declared HERE, beside the converter, rather than in the
extraction tools, because what makes a schema usable on the on-device tier is
a property of `_pydantic_to_apple_schema`, and a model that drifts out of its
supported subset should fail in this module's tests rather than at run time on
a user's machine.

The converter's limits are the design constraints, not suggestions. It RAISES
on discriminated unions, recursive types, **enums**, `Annotated` with custom
validators, `format` keywords, and free-form mappings. So:

- every classification field is a plain `str` whose ALLOWED VALUES live in its
  description, never a `StrEnum` — the same shape `epistemic_status` and
  `claim_type` already use, mapped back afterwards by the caller;
- every field carries a default, so one missing value cannot fail a whole
  page. That is the #1113 lesson: required strings turned one absent field
  into 66 "field required" errors and zero claims;
- nothing nests deeper than it must, because the on-device context window is
  ~4K and the schema is sent in the prompt as well as in the grammar
  (`_entity_schema_in_prompt`, #1633/#1634 — with the schema omitted the
  decoder returns grammar-valid, ALL-EMPTY objects on clean prose).

Empty is a legitimate answer everywhere here: a claim about an undated fact
must validate. Callers detect emptiness explicitly rather than leaning on the
grammar to refuse it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

#: Values `SubjectNaming.kind` may carry. In the DESCRIPTION, not an enum —
#: an enum makes the whole model Apple-ineligible and the failure is an
#: exception, not a fallback.
SUBJECT_KINDS = ("person", "place", "organization", "event", "other")

#: What `TemporalScope.precision` may say about a normalized date.
DATE_PRECISIONS = ("day", "month", "year", "range", "unknown")


class SubjectNaming(BaseModel):
    """Who or what a candidate triple is actually about.

    The measured failure (lane-svo-quality, 2026-09-04): 9 of 17 real rows had
    a "verb" that was a proper noun, adjective or preposition — the subject
    slot was carrying clause debris. A grammar cannot know Spanish morphology,
    but it can hold the OUTPUT to one short name plus a reason, which is what
    stops a clause dump from being written as a subject in the first place.
    """

    subject: str = Field(
        default="",
        description=(
            "The single person, place, organization or thing the statement is "
            "about, as a short proper name — not a clause, not a sentence. "
            "Empty when the text names no clear subject."
        ),
    )
    kind: str = Field(
        default="other",
        description=(
            "What the subject IS. One of: person, place, organization, event, "
            "other. Use 'other' when unsure rather than guessing."
        ),
    )
    confident: bool = Field(
        default=False,
        description=(
            "True only when the subject is named explicitly in the text. "
            "False when it was inferred from context."
        ),
    )


class TemporalScope(BaseModel):
    """A date as the timeline can actually use it (#4667).

    ISO-shaped strings, NOT a `date` field: a JSON-Schema `format` keyword
    makes the model Apple-ineligible, and the source is historical prose where
    "the feast of San Juan, 1573" is a real and only partly resolvable answer.
    A string that says what it knows beats a date that had to invent a day.
    """

    start: str = Field(
        default="",
        description=(
            "Earliest date the statement covers, as YYYY, YYYY-MM or "
            "YYYY-MM-DD. Empty when the text gives no date."
        ),
    )
    end: str = Field(
        default="",
        description=(
            "Latest date the statement covers, same format. Equal to start "
            "for a single day; empty when there is no range."
        ),
    )
    precision: str = Field(
        default="unknown",
        description=(
            "How precisely the date is known. One of: day, month, year, "
            "range, unknown."
        ),
    )
    as_written: str = Field(
        default="",
        description=(
            "The date exactly as the document words it, copied verbatim — "
            "'la fiesta de San Juan de 1573'. Never normalized, never "
            "translated: this is what the reader can check the reading against."
        ),
    )


class PlaceNormalization(BaseModel):
    """A place name resolved to something comparable across documents (#4670).

    No coordinates: the on-device model does not know them, and a plausible
    invented latitude is worse in an archive than an absent one.
    """

    name: str = Field(
        default="",
        description=(
            "The place in its modern, standard form — 'Cartagena de Indias'. "
            "Empty when the text names no place."
        ),
    )
    as_written: str = Field(
        default="",
        description=(
            "The place exactly as the document words it, copied verbatim, "
            "including archaic spelling."
        ),
    )
    within: str = Field(
        default="",
        description=(
            "The larger place containing it, when the text says so — a "
            "province, viceroyalty or country. Empty when unstated. Do not "
            "supply one from general knowledge."
        ),
    )


#: Every model this module offers to the on-device tier. The contract test
#: converts each one and fails if any drifts out of the supported subset —
#: which is how an enum or a `date` field gets caught here rather than on a
#: user's Mac.
APPLE_GUIDED_SCHEMAS: tuple[type[BaseModel], ...] = (
    SubjectNaming,
    TemporalScope,
    PlaceNormalization,
)
