"""The on-device tier's schemas must stay inside the converter's subset.

`_pydantic_to_apple_schema` RAISES on enums, unions, recursion, `format`
keywords and free-form mappings. That is the right behaviour — but it fires at
run time, on a user's Mac, in the middle of a paid-for extraction run. These
tests move the failure to here: add a `StrEnum` or a `date` field to a
consumer model and this file goes red before the model ever ships.

Also pinned: the free-form-mapping hole found on 2026-09-04. `dict[str, T]`
has no DynamicGenerationSchema equivalent, and it used to convert to an object
with ZERO properties — so the decoder could emit nothing but `{}` and the
field was structurally guaranteed to come back empty, forever, with no error
anywhere. Silence is the one outcome this converter's contract forbids.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

import pytest
from pydantic import BaseModel, Field

from fichero_server.llm import _pydantic_to_apple_schema
from fichero_server.llm.apple_guided_schemas import (
    APPLE_GUIDED_SCHEMAS,
    DATE_PRECISIONS,
    SUBJECT_KINDS,
    PlaceNormalization,
    SubjectNaming,
    TemporalScope,
)


# =============================================================================
# Every shipped consumer schema is Apple-eligible
# =============================================================================


def test_the_population_is_real():
    assert len(APPLE_GUIDED_SCHEMAS) >= 3


@pytest.mark.parametrize(
    "model", APPLE_GUIDED_SCHEMAS, ids=lambda m: m.__name__
)
def test_every_consumer_schema_converts(model):
    """The contract, per model: it must survive the converter untouched."""
    tree = _pydantic_to_apple_schema(model)
    assert tree["type"] == "object"
    assert tree["properties"], f"{model.__name__} converted to an empty object"


@pytest.mark.parametrize(
    "model", APPLE_GUIDED_SCHEMAS, ids=lambda m: m.__name__
)
def test_every_field_has_a_default(model):
    """One missing value must not fail a whole page (#1113).

    Required strings once turned a single absent field into 66 'field
    required' errors and zero claims for the page.
    """
    for name, field in model.model_fields.items():
        assert not field.is_required(), f"{model.__name__}.{name} is required"


@pytest.mark.parametrize(
    "model", APPLE_GUIDED_SCHEMAS, ids=lambda m: m.__name__
)
def test_every_field_describes_itself(model):
    """The description IS the instruction: the schema rides in the prompt as
    well as the grammar on Apple (#1633/#1634), so an undescribed field is a
    field the model has to guess at."""
    for name, field in model.model_fields.items():
        assert field.description, f"{model.__name__}.{name} has no description"


def test_classification_values_live_in_the_description_not_an_enum():
    """An enum anywhere makes the model Apple-INELIGIBLE, and the failure is
    an exception rather than a fallback — so allowed values are prose."""
    kind = SubjectNaming.model_fields["kind"]
    assert kind.annotation is str
    for value in SUBJECT_KINDS:
        assert value in kind.description

    precision = TemporalScope.model_fields["precision"]
    assert precision.annotation is str
    for value in DATE_PRECISIONS:
        assert value in precision.description


def test_dates_are_strings_so_the_document_can_be_quoted_as_written():
    """A `date` field would add a JSON-Schema format keyword (ineligible) AND
    force a day onto 'la fiesta de San Juan de 1573'."""
    assert TemporalScope.model_fields["start"].annotation is str
    assert TemporalScope.model_fields["as_written"].annotation is str


def test_empty_is_a_valid_answer_everywhere():
    """A claim about an undated, place-less fact must still validate."""
    assert SubjectNaming().subject == ""
    assert TemporalScope().precision == "unknown"
    assert PlaceNormalization().name == ""


def test_place_normalization_does_not_invent_coordinates():
    """A plausible invented latitude is worse in an archive than none."""
    assert "latitude" not in PlaceNormalization.model_fields
    assert "longitude" not in PlaceNormalization.model_fields


# =============================================================================
# The converter's refusals — each one a shape that would fail silently or late
# =============================================================================


def test_a_free_form_mapping_is_refused_not_silently_emptied():
    """The 2026-09-04 finding: dict[str, list[str]] converted to an object
    with no properties, so the grammar could only ever produce {}."""

    class WithMapping(BaseModel):
        extra: dict[str, list[str]] = Field(default_factory=dict)

    with pytest.raises(ValueError) as caught:
        _pydantic_to_apple_schema(WithMapping)
    message = str(caught.value)
    assert "free-form mapping" in message
    assert "only ever emit {}" in message, "the refusal must say WHY"


def test_an_enum_is_refused():
    class Kind(StrEnum):
        person = "person"

    class WithEnum(BaseModel):
        kind: Kind = Kind.person

    with pytest.raises(ValueError):
        _pydantic_to_apple_schema(WithEnum)


def test_a_format_keyword_is_refused():
    class WithDate(BaseModel):
        when: date | None = None

    with pytest.raises(ValueError):
        _pydantic_to_apple_schema(WithDate)


def test_a_plain_nested_model_still_converts():
    """The guard must not have swallowed ordinary nesting."""

    class Inner(BaseModel):
        name: str = ""

    class Outer(BaseModel):
        items: list[Inner] = Field(default_factory=list)

    tree = _pydantic_to_apple_schema(Outer)
    assert tree["properties"][0]["schema"]["type"] == "array"
