"""The annotation list's items must be TYPED, not bare dicts.

The generated clients build their model from this `$ref`; a bare
`list[dict]` would give them nothing to build and the typing would be lost
at the boundary.

Since #4990 the ref names `AnnotationRead`, not `Annotation`: the list
carries the stored annotation PLUS where its anchor points now. So the test
also pins that the read shape is a strict superset of the row's — a client
that had every `Annotation` field still has every one of them.
"""

from fichero_server.api.routes.document.annotations import (
    AnnotationListResponse,
    AnnotationRead,
)
from fichero_server.models.knowledge import Annotation


def test_annotation_list_schema_has_typed_items():
    items = AnnotationListResponse.model_json_schema()["properties"]["items"]
    ref = items["items"]["$ref"]
    assert ref.endswith("/AnnotationRead"), ref


def test_the_read_shape_keeps_every_field_the_row_has():
    """The point of the ref being typed is that a client can build the
    model. Renaming the shape must not quietly drop a field."""
    missing = set(Annotation.model_fields) - set(AnnotationRead.model_fields)
    assert not missing, f"AnnotationRead lost {sorted(missing)}"


def test_the_read_shape_adds_only_where_the_anchor_points_now():
    """And gains nothing else, so the ref's meaning stays "an annotation"."""
    added = set(AnnotationRead.model_fields) - set(Annotation.model_fields)
    assert added == {"resolved_anchor"}, sorted(added)


def test_the_resolved_anchor_is_optional_so_an_old_client_is_unaffected():
    field = AnnotationRead.model_fields["resolved_anchor"]
    assert not field.is_required()
    assert field.default is None
