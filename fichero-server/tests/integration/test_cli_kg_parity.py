"""CLI smoke tests for SwiftUI KG/inspector operation parity."""

from __future__ import annotations

import json
from contextlib import contextmanager

from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_server.api.routes.document_inspector import DocumentKnowledgeGraphResponse
from fichero_server.api.routes.workflow_execution.schemas import ExecuteAcceptedResponse
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.models import Artifact


runner = CliRunner()


class FakeParityClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def document_knowledge_graph(
        self, doc_id: str, *, include_children: bool = False
    ) -> DocumentKnowledgeGraphResponse:
        self.calls.append(("document_knowledge_graph", doc_id, include_children))
        return DocumentKnowledgeGraphResponse(
            document_id=doc_id,
            include_children=include_children,
            groups=[],
            claims=[],
            entity_count=0,
            claim_count=0,
            catalogue=[],
        )

    def list_entities(
        self, *, query: str | None = None, entity_type: str | None = None, limit: int = 50
    ) -> list[KnowledgeEntity]:
        self.calls.append(("list_entities", query, entity_type, limit))
        return [
            KnowledgeEntity(
                id="entity-1",
                canonical_name="Bogotá",
                entity_type=entity_type or "location",
            )
        ]

    def list_claims(
        self, *, source_document_id: str | None = None, limit: int = 50, **_: object
    ) -> list[KnowledgeClaim]:
        self.calls.append(("list_claims", source_document_id, limit))
        return [
            KnowledgeClaim(
                id="claim-1",
                text="Bogotá appears in the source.",
                source_document_id=source_document_id,
            )
        ]

    def citations_at_doc(self, doc_id: str) -> list[KnowledgeEntity]:
        self.calls.append(("citations_at_doc", doc_id))
        return [
            KnowledgeEntity(
                id="citation-1",
                canonical_name="Smith-2024",
                entity_type="citation",
            )
        ]

    def list_artifacts(
        self, doc_id: str, *, artifact_type: str | None = None, limit: int = 50
    ) -> list[Artifact]:
        self.calls.append(("list_artifacts", doc_id, artifact_type, limit))
        return [
            Artifact(
                id="artifact-1",
                document_id=doc_id,
                artifact_type=artifact_type or "transcription",
                content="hello",
            )
        ]

    def split_chapters(self, doc_id: str) -> ExecuteAcceptedResponse:
        self.calls.append(("split_chapters", doc_id))
        return ExecuteAcceptedResponse(
            thread_id="thread-1",
            workflow_id="split-chapters",
            workflow_name="Split Chapters",
            status="accepted",
            stream_url="/api/workflow-execution/stream/thread-1",
        )


def _install_fake_client(monkeypatch):
    fake = FakeParityClient()

    @contextmanager
    def fake_client(_ctx):
        yield fake

    monkeypatch.setattr(cli, "_client", fake_client)
    return fake


def _json_for(args: list[str]) -> object:
    result = runner.invoke(cli.app, ["--json", *args])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_cli_kg_parity_commands_emit_stable_json(monkeypatch):
    fake = _install_fake_client(monkeypatch)

    docs_kg = _json_for(["docs", "kg", "doc-1", "--include-children"])
    assert docs_kg["document_id"] == "doc-1"
    assert docs_kg["include_children"] is True

    entities = _json_for(["kg", "entities", "--type", "location", "--limit", "7"])
    assert entities[0]["canonical_name"] == "Bogotá"

    claims = _json_for(["kg", "claims", "--doc", "doc-1"])
    assert claims[0]["source_document_id"] == "doc-1"

    citations = _json_for(["kg", "citations", "doc-1"])
    assert citations[0]["entity_type"] == "citation"

    artifacts = _json_for(["artifacts", "list", "doc-1"])
    assert artifacts[0]["document_id"] == "doc-1"

    split = _json_for(["docs", "split-chapters", "doc-1"])
    assert split["workflow_name"] == "Split Chapters"

    assert ("document_knowledge_graph", "doc-1", True) in fake.calls
    assert ("list_entities", None, "location", 7) in fake.calls
    assert ("list_claims", "doc-1", 50) in fake.calls
    assert ("citations_at_doc", "doc-1") in fake.calls
    assert ("list_artifacts", "doc-1", None, 50) in fake.calls
    assert ("split_chapters", "doc-1") in fake.calls
