"""Coverage for document-inspector knowledge-graph helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

from fichero.api.routes import document_inspector as inspector
from fichero.knowledge_models import KnowledgeEntity
from fichero.models import Artifact


def test_resolve_canonical_follows_merge_chain_and_stops_cycles():
    first = KnowledgeEntity(id="first", canonical_name="First", merged_into_id="second")
    second = KnowledgeEntity(id="second", canonical_name="Second", merged_into_id="third")
    third = KnowledgeEntity(id="third", canonical_name="Third")
    cycle = KnowledgeEntity(id="cycle", canonical_name="Cycle", merged_into_id="cycle")

    class DB:
        def get(self, _model, key):
            return {item.id: item for item in (first, second, third, cycle)}.get(key)

    db = DB()
    assert inspector._resolve_canonical(db, "first") is third
    assert inspector._resolve_canonical(db, "cycle") is cycle
    assert inspector._resolve_canonical(db, "missing") is None


def test_catalogue_artifacts_filter_and_order_by_type_then_newest():
    now = datetime.now()
    rows = [
        Artifact(document_id="doc", artifact_type="transcription", created_at=now),
        Artifact(document_id="doc", artifact_type="catalogue.keywords", created_at=now),
        Artifact(document_id="doc", artifact_type="catalogue.narrative", created_at=now - timedelta(days=1)),
        Artifact(document_id="doc", artifact_type="catalogue", created_at=now),
    ]

    class DB:
        def query(self, _model, **filters):
            assert filters == {"document_id": "doc"}
            return rows

    assert inspector._is_catalogue_artifact("catalogue.timeline")
    assert not inspector._is_catalogue_artifact("summary")
    result = inspector._catalogue_artifacts(DB(), "doc")

    assert [item.artifact_type for item in result] == [
        "catalogue",
        "catalogue.narrative",
        "catalogue.keywords",
    ]
