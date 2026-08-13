"""Effective attributes surface (datasets Stage 1, engine slice 2).

The resolver's promises at the API boundary: inheritance merged root→leaf,
node values overlaying prototype defaults, and 422 — never partial data —
when the chain cannot be resolved.
"""

from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import (
    ClassificationDimension,
    ClassificationValue,
)

_ENTRY = ClassificationValue(
    dimension=ClassificationDimension.document_prototype,
    key="entry",
    label="Entry",
    attributes={"date": {"type": "date", "role": "date"}, "source": "unknown"},
)
_DIARY_ENTRY = ClassificationValue(
    dimension=ClassificationDimension.document_prototype,
    key="diary_entry",
    label="Diary Entry",
    parent_key="entry",
    attributes={"weather": {"type": "select", "options": ["fair", "rain"]}},
)


def _route_prototypes(mock_db):
    def query_side(cls, **filters):
        if cls is ClassificationValue:
            key = filters.get("key")
            return [p for p in (_ENTRY, _DIARY_ENTRY) if p.key == key]
        return []

    mock_db.query.side_effect = query_side


class TestEffectiveAttributes:
    def test_no_prototype_returns_own_values_only(self, client, mock_db):
        doc = Document(
            id="d1", name="loose", doc_type=DocType.file,
            attributes={"note": "hand-set"},
        )
        mock_db.get_committed.side_effect = lambda _c, i: doc if i == "d1" else None

        response = client.get("/api/documents/d1/effective-attributes")
        assert response.status_code == 200
        data = response.json()
        assert data["prototype_key"] is None
        assert data["declarations"] == {}
        assert data["values"] == {"note": "hand-set"}

    def test_inherited_declarations_and_value_overlay(self, client, mock_db):
        doc = Document(
            id="d2", name="jan1", doc_type=DocType.file,
            prototype_key="diary_entry",
            attributes={"weather": "rain"},
        )
        mock_db.get_committed.side_effect = lambda _c, i: doc if i == "d2" else None
        _route_prototypes(mock_db)

        response = client.get("/api/documents/d2/effective-attributes")
        assert response.status_code == 200
        data = response.json()
        # Parent chain merged: child's weather + parent's date and legacy source.
        assert set(data["declarations"]) == {"date", "weather", "source"}
        assert data["declarations"]["date"]["role"] == "date"
        assert data["declarations"]["source"]["type"] == "text"  # legacy plain
        # Node's own value overlays the default; untouched defaults remain.
        assert data["values"]["weather"] == "rain"
        assert data["values"]["source"] == "unknown"
        assert data["values"]["date"] is None

    def test_unresolvable_prototype_is_422_not_partial(self, client, mock_db):
        doc = Document(
            id="d3", name="orphan", doc_type=DocType.file,
            prototype_key="missing_proto",
        )
        mock_db.get_committed.side_effect = lambda _c, i: doc if i == "d3" else None
        mock_db.query.side_effect = lambda cls, **f: []

        response = client.get("/api/documents/d3/effective-attributes")
        assert response.status_code == 422
        assert "missing_proto" in response.json()["detail"]


class TestResolvedPrototypeEndpoint:
    def test_resolved_merges_parent_chain(self, client, mock_db):
        _route_prototypes(mock_db)
        response = client.get("/api/classifications/resolved/diary_entry")
        assert response.status_code == 200
        data = response.json()
        assert set(data["declarations"]) == {"date", "weather", "source"}
        assert data["defaults"]["source"] == "unknown"

    def test_unknown_key_is_422(self, client, mock_db):
        mock_db.query.side_effect = lambda cls, **f: []
        response = client.get("/api/classifications/resolved/nope")
        assert response.status_code == 422
