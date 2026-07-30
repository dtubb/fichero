"""Unit tests for the fichero CLI command tree and output formatters.

The FicheroClient is replaced with an in-memory fake so the CLI is exercised
without a live backend.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_cli import FicheroError
from fichero_cli import client as client_module
from fichero_cli.formatters import render
from fichero_server.api.routes.system.activity import ActivityResponse
from fichero_server.api.routes.document.artifacts import ArtifactResponse
from fichero_server.api.routes.document.inspector import DocumentInspectorResponse
from fichero_server.api.routes.entity.entities import (
    EntityAuditResponse,
    EntityCoOccurrence,
    EntityDocumentLink,
    EntityResolutionResponse,
    TopEntityRow,
)
from fichero_server.api.routes.kg_search import KGSearchResponse
from fichero_server.api.routes.ai.provider_models import ProviderResponse
from fichero_server.api.routes.workflow_execution.schemas import (
    ExecuteAcceptedResponse,
    ExecutionStatusResponse,
    ThreadListResponse,
)
from fichero_server.api.routes.workflow_execution.threads import ThreadDeletedResponse
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity, Note
from fichero_server.models import LibraryCreateResponse, Workflow

runner = CliRunner()


class FakeClient:
    """Records construction kwargs and call args; returns canned responses."""

    instances: list["FakeClient"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list[tuple] = []
        FakeClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def close(self):
        pass

    # -- recorded operations --------------------------------------------
    def health(self):
        self.calls.append(("health",))
        return {"status": "ok"}

    def request(self, method, path, *, params=None, json=None, files=None):
        self.calls.append(
            ("request", method, path, {"params": params, "json": json, "files": files})
        )
        return {
            "method": method,
            "path": path,
            "params": params,
            "json": json,
            "has_files": files is not None,
        }

    def request_stream(self, method, path, *, params=None):
        self.calls.append(("request_stream", method, path, {"params": params}))
        return [
            'data: {"type":"tick","thread_id":"t-1"}',
            ": keepalive",
        ]

    def list_documents(self, **kw):
        self.calls.append(("list_documents", kw))
        from fichero_server.models import DocumentListResponse
        # Mirror the real FicheroClient: list_documents() returns list[Document]
        # (it unwraps the {items,count} envelope via _expect_list). Reuse the
        # envelope's validation, then hand back .items so the fake matches the
        # real client's contract.
        return DocumentListResponse(
            items=[{
                "id": "d1",
                "name": "Doc One",
                "path": "/path/to/doc",
                "doc_type": "file",
                "description": "",
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00"
            }],
            count=1
        ).items

    def get_document(self, doc_id):
        self.calls.append(("get_document", doc_id))
        return {"id": doc_id, "title": "Doc One"}

    def import_file(self, path, parent_id=None):
        self.calls.append(("import_file", path, parent_id))
        return {"id": "d99", "filename": str(path)}

    def list_workflows(self):
        # Real FicheroClient.list_workflows() returns list[Workflow]; the fake
        # must match the typed contract or _resolve_workflow's attribute access
        # fails.
        self.calls.append(("list_workflows",))
        return [
            Workflow.model_validate({"id": "wf-1", "name": "Catalogue"}),
            Workflow.model_validate({"id": "wf-2", "name": "Transcribe"}),
            Workflow.model_validate({"id": "wf-3", "name": "Translate"}),
        ]

    def run_workflow(self, workflow_id, inputs=None, **kw):
        self.calls.append(("run_workflow", workflow_id, inputs, kw))
        return ExecuteAcceptedResponse(
            thread_id="t-1",
            workflow_id=workflow_id,
            workflow_name="Catalogue",
            status="accepted",
            stream_url="/api/workflow-execution/stream/t-1",
        )

    def compare_models(self, *, prompt, models, system_prompt=None, timeout_seconds=120):
        self.calls.append(("compare_models", prompt, models, system_prompt, timeout_seconds))
        return {
            "prompt": prompt,
            "models_compared": [f"{item['provider']}/{item['model']}" for item in models],
            "results": [
                {
                    "provider": models[0]["provider"],
                    "model": models[0]["model"],
                    "response": "best model output",
                    "latency_ms": 11.0,
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cost_usd": 0.0100,
                    "error": None,
                    "timestamp": "2026-05-15T00:00:00",
                },
                {
                    "provider": models[-1]["provider"],
                    "model": models[-1]["model"],
                    "response": "cheapest model output",
                    "latency_ms": 19.0,
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cost_usd": 0.0020,
                    "error": None,
                    "timestamp": "2026-05-15T00:00:00",
                },
            ],
            "fastest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "cheapest_model": f"{models[-1]['provider']}/{models[-1]['model']}",
            "total_cost_usd": 0.0120,
            "total_latency_ms": 30.0,
            "comparison_id": "cmp-cli-models",
            "timestamp": "2026-05-15T00:00:00",
        }

    def compare_vision(self, *, images, models, prompt, detail="auto", timeout_seconds=120):
        self.calls.append(("compare_vision", images, models, prompt, detail, timeout_seconds))
        return {
            "prompt": prompt,
            "models_compared": [f"{item['provider']}/{item['model']}" for item in models],
            "results": [
                {
                    "provider": models[0]["provider"],
                    "model": models[0]["model"],
                    "response": "vision output",
                    "latency_ms": 12.0,
                    "input_tokens": 1000,
                    "output_tokens": 20,
                    "cost_usd": 0.0200,
                    "error": None,
                    "timestamp": "2026-05-15T00:00:00",
                }
            ],
            "fastest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "cheapest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "total_cost_usd": 0.0200,
            "total_latency_ms": 12.0,
            "comparison_id": "cmp-cli-vision",
            "timestamp": "2026-05-15T00:00:00",
        }

    def compare_tool(self, *, tool_name, inputs, models, tool_config=None, timeout_seconds=120):
        self.calls.append(("compare_tool", tool_name, inputs, models, tool_config, timeout_seconds))
        return {
            "prompt": f"[Tool: {tool_name}]",
            "models_compared": [f"{item['provider']}/{item['model']}" for item in models],
            "results": [
                {
                    "provider": models[0]["provider"],
                    "model": models[0]["model"],
                    "response": "tool output",
                    "latency_ms": 21.0,
                    "input_tokens": 10,
                    "output_tokens": 15,
                    "cost_usd": 0.0030,
                    "error": None,
                    "timestamp": "2026-05-15T00:00:00",
                }
            ],
            "fastest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "cheapest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "total_cost_usd": 0.0030,
            "total_latency_ms": 21.0,
            "comparison_id": "cmp-cli-tool",
            "timestamp": "2026-05-15T00:00:00",
        }

    def compare_workflow(self, *, workflow_id, doc_id, models, inputs=None, timeout_seconds=300):
        self.calls.append(("compare_workflow", workflow_id, doc_id, models, inputs, timeout_seconds))
        return {
            "prompt": f"[Workflow: {workflow_id}]",
            "models_compared": [f"{item['provider']}/{item['model']}" for item in models],
            "results": [
                {
                    "provider": models[0]["provider"],
                    "model": models[0]["model"],
                    "response": "workflow output",
                    "latency_ms": 55.0,
                    "input_tokens": 20,
                    "output_tokens": 30,
                    "cost_usd": 0.0150,
                    "error": None,
                    "timestamp": "2026-05-15T00:00:00",
                }
            ],
            "fastest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "cheapest_model": f"{models[0]['provider']}/{models[0]['model']}",
            "total_cost_usd": 0.0150,
            "total_latency_ms": 55.0,
            "comparison_id": "cmp-cli-workflow",
            "timestamp": "2026-05-15T00:00:00",
        }

    def translate_document(self, doc_id, *, target_lang="en", source_lang="auto"):
        self.calls.append(("translate_document", doc_id, target_lang, source_lang))
        return ExecuteAcceptedResponse(
            thread_id="t-3",
            workflow_id="wf-3",
            workflow_name="Translate",
            status="accepted",
            stream_url="/api/workflow-execution/stream/t-3",
        )

    def execution_status(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        # The status endpoint is unreliable mid-run (#1088): it reports
        # "completed" whenever a checkpoint has no pending writes. The fake
        # mirrors that flakiness — it always says "completed" so the wait
        # loop is forced to consult the activity log to know the truth.
        return ExecutionStatusResponse(
            thread_id=thread_id,
            workflow_id="wf-1",
            workflow_name="Catalogue",
            status="completed",
            current_state={"final": True},
        )

    def list_activities(self, *, thread_id=None, types=None, limit=100):
        self.calls.append(("list_activities", thread_id, types, limit))
        from fichero_server.models import ActivityListResponse
        # Mimic the executor: emit a workflow_completed event only after
        # the second poll, so the wait loop has to actually wait.
        # Mirror the real FicheroClient: list_activities() returns
        # list[ActivityResponse] (unwrapped from the envelope). Hand back .items.
        polls = [c for c in self.calls if c[0] == "list_activities"]
        if len(polls) < 2:
            return ActivityListResponse(items=[], count=0).items
        activity_data = {
            "id": "act-end",
            "type": "workflow_completed",
            "level": "info",
            "message": "Workflow completed",
            "timestamp": "2024-01-01T00:00:00",
            "thread_id": thread_id,
            "workflow_id": "wf-1",
            "metadata": {},
        }
        return ActivityListResponse(items=[activity_data], count=1).items

    def get_artifact(self, artifact_id):
        self.calls.append(("get_artifact", artifact_id))
        from fichero_server.models import Artifact

        return Artifact.model_validate(
            {
                "id": artifact_id,
                "document_id": "doc-7",
                "artifact_type": "transcription",
                "content": "hello world",
                "version": 2,
                "provider": "openai",
                "model": "gpt-4o",
                "reviewed": False,
            }
        )

    def list_artifacts(self, doc_id, **kw):
        self.calls.append(("list_artifacts", doc_id, kw))
        return {"artifacts": [{"id": "a1", "artifact_type": "transcription"}]}

    def list_entities(self, **kw):
        self.calls.append(("list_entities", kw))
        return [
            KnowledgeEntity(id="e1", canonical_name="Bogotá", entity_type="location")
        ]

    def list_claims(self, **kw):
        self.calls.append(("list_claims", kw))
        return [KnowledgeClaim(id="c1", text="X", source_document_id="d5")]

    def citations_at_doc(self, doc_id: str):
        self.calls.append(("citations_at_doc", doc_id))
        return [{"canonical_name": "Smith-1999", "entity_type": "citation"}]

    def document_inspector(self, doc_id):
        self.calls.append(("document_inspector", doc_id))
        return DocumentInspectorResponse(
            document_id=doc_id,
            document=None,
            source_metadata=None,
            claim_count=1,
            claims=[
                KnowledgeClaim(
                    id="c-other", text="should not appear", source_document_id=doc_id
                )
            ],
            entities=[KnowledgeEntity(id="e1", canonical_name="Bogotá", entity_type="location")],
            annotations=[],
            notes=[],
            citations_outbound=[],
            citations_inbound=[],
            interpretations=[],
            projects=[],
        )

    def kg_search(self, query, **kw):
        self.calls.append(("kg_search", query, kw))
        return KGSearchResponse(query=query, hits=[], counts={})

    def search(self, query, **kw):
        self.calls.append(("search", query, kw))
        return {"results": [{"id": "d1", "title": "Doc One"}]}

    def recent_activity(self, **kw):
        self.calls.append(("recent_activity", kw))
        return [
            ActivityResponse(
                id="act1",
                type="workflow_completed",
                level="info",
                timestamp="2026-05-15T00:00:00Z",
                message="completed",
            )
        ]

    def create_note(self, **kw):
        self.calls.append(("create_note", kw))
        return Note(
            id="note-z1",
            title=kw.get("title"),
            body=kw.get("body", ""),
            kind=kw.get("kind", "zettel"),
            tags=kw.get("tags") or [],
            linked_document_ids=kw.get("linked_document_ids") or [],
        )

    def list_notes(self, **kw):
        self.calls.append(("list_notes", kw))
        return [
            Note(
                id="note-z1",
                title="Field note",
                body="Remember this",
                kind="zettel",
                tags=["field"],
            )
        ]

    def get_note(self, note_id):
        self.calls.append(("get_note", note_id))
        return Note(id=note_id, title="Field note", body="Remember this")


    def create_library(self, path):
        # Real client returns LibraryCreateResponse — keep the typed
        # contract so the CLI's render() goes through the model_dump path.
        self.calls.append(("create_library", path))
        return LibraryCreateResponse(
            path=path, created=True, tables_initialized=True
        )

    # -- extended document methods -----------------------------------------
    def delete_document(self, doc_id):
        self.calls.append(("delete_document", doc_id))
        return None

    def update_document(self, doc_id, **fields):
        self.calls.append(("update_document", doc_id, fields))
        return {"id": doc_id, "name": fields.get("name", "Updated Doc")}

    def document_knowledge_graph(self, doc_id, **kw):
        self.calls.append(("document_knowledge_graph", doc_id, kw))
        from fichero_server.api.routes.document.inspector import DocumentKnowledgeGraphResponse
        return DocumentKnowledgeGraphResponse(
            document_id=doc_id,
            include_children=kw.get("include_children", False),
            groups=[],
            claims=[],
            entity_count=0,
            claim_count=0,
            catalogue=[],
        )

    # -- extended artifact methods -----------------------------------------
    def update_artifact(self, artifact_id, *, content=None, reviewed=None):
        self.calls.append(("update_artifact", artifact_id, content, reviewed))
        return ArtifactResponse(
            id=artifact_id,
            document_id="doc-7",
            artifact_type="transcription",
            content=content or "updated",
            version=3,
            reviewed=reviewed if reviewed is not None else True,
            created_at="2026-05-15T00:00:00",
        )

    def delete_artifact(self, artifact_id):
        self.calls.append(("delete_artifact", artifact_id))
        return None

    # -- claim methods -----------------------------------------------------
    def get_claim(self, claim_id):
        self.calls.append(("get_claim", claim_id))
        return KnowledgeClaim(id=claim_id, text="A claim", source_document_id="d5")

    def update_claim(self, claim_id, **fields):
        self.calls.append(("update_claim", claim_id, fields))
        return KnowledgeClaim(
            id=claim_id,
            text=fields.get("text", "Updated claim"),
            source_document_id="d5",
        )

    def delete_claim(self, claim_id):
        self.calls.append(("delete_claim", claim_id))
        return None

    def review_claim(self, claim_id, *, status):
        self.calls.append(("review_claim", claim_id, status))
        return KnowledgeClaim(id=claim_id, text="A claim", source_document_id="d5")

    # -- entity methods ----------------------------------------------------
    def get_entity(self, entity_id):
        self.calls.append(("get_entity", entity_id))
        return KnowledgeEntity(id=entity_id, canonical_name="Bogotá", entity_type="location")

    def update_entity(self, entity_id, **fields):
        self.calls.append(("update_entity", entity_id, fields))
        return KnowledgeEntity(
            id=entity_id,
            canonical_name=fields.get("canonical_name", "Updated"),
        )

    def delete_entity(self, entity_id):
        self.calls.append(("delete_entity", entity_id))
        return None

    def merge_entities(self, absorbing_id, absorbed_ids, **kw):
        self.calls.append(("merge_entities", absorbing_id, absorbed_ids, kw))
        from datetime import datetime
        from fichero_server.models.knowledge import EntityMergeOperationType
        return EntityAuditResponse(
            id="audit-1",
            operation_type=EntityMergeOperationType.merge,
            source_entity_ids=absorbed_ids,
            target_entity_id=absorbing_id,
            alias_changes={},
            reversal_id=None,
            created_by="cli",
            created_at=datetime(2026, 5, 15),
        )

    def split_entity(self, primary_id, split_off_ids, **kw):
        self.calls.append(("split_entity", primary_id, split_off_ids, kw))
        from datetime import datetime
        from fichero_server.models.knowledge import EntityMergeOperationType
        return EntityAuditResponse(
            id="audit-2",
            operation_type=EntityMergeOperationType.split,
            source_entity_ids=[primary_id],
            target_entity_id=split_off_ids[0] if split_off_ids else primary_id,
            alias_changes={},
            reversal_id=None,
            created_by="cli",
            created_at=datetime(2026, 5, 15),
        )

    def top_entities(self, *, limit=30):
        self.calls.append(("top_entities", limit))
        return [TopEntityRow(entity_id="e1", name="Bogotá", kind="place", claim_count=5)]

    def entity_documents(self, entity_id):
        self.calls.append(("entity_documents", entity_id))
        return [
            EntityDocumentLink(
                document_id="d1",
                document_name="Doc One",
                claim_count=3,
            )
        ]

    def entity_co_occurrence(self, entity_id):
        self.calls.append(("entity_co_occurrence", entity_id))
        return [
            EntityCoOccurrence(
                entity_id="e2",
                name="Colombia",
                kind="place",
                shared_claims=2,
            )
        ]

    def resolve_entity(self, name):
        self.calls.append(("resolve_entity", name))
        return EntityResolutionResponse(
            resolved=True,
            value=name,
            entity_id="e1",
            canonical_name="Bogotá",
            entity_type="location",
            match_type="canonical_name",
        )

    # -- audit methods -----------------------------------------------------
    def list_audits(self, *, limit=50):
        self.calls.append(("list_audits", limit))
        from datetime import datetime
        from fichero_server.models.knowledge import EntityMergeOperationType
        return [
            EntityAuditResponse(
                id="audit-1",
                operation_type=EntityMergeOperationType.merge,
                source_entity_ids=["e2"],
                target_entity_id="e1",
                alias_changes={},
                reversal_id=None,
                created_by="cli",
                created_at=datetime(2026, 5, 15),
            )
        ]

    def undo_audit(self, audit_id):
        self.calls.append(("undo_audit", audit_id))
        from datetime import datetime
        from fichero_server.models.knowledge import EntityMergeOperationType
        return EntityAuditResponse(
            id=audit_id,
            operation_type=EntityMergeOperationType.merge,
            source_entity_ids=["e1"],
            target_entity_id="e2",
            alias_changes={},
            reversal_id=None,
            created_by="cli",
            created_at=datetime(2026, 5, 15),
        )

    # -- workflow thread methods -------------------------------------------
    def list_threads(self, *, limit=100):
        self.calls.append(("list_threads", limit))
        return ThreadListResponse(threads=[])

    def delete_thread(self, thread_id):
        self.calls.append(("delete_thread", thread_id))
        return ThreadDeletedResponse(message=f"Thread deleted: {thread_id}")

    # -- settings methods --------------------------------------------------
    def get_settings(self):
        self.calls.append(("get_settings",))
        return {"text_model": "gpt-4o", "text_provider": "openai"}

    def set_settings(self, **fields):
        self.calls.append(("set_settings", fields))
        return {"status": "ok"}

    # -- provider methods --------------------------------------------------
    def list_providers(self):
        self.calls.append(("list_providers",))
        return [
            ProviderResponse(
                id="prov-1",
                name="My OpenAI",
                provider_type="openai",
                api_base=None,
                enabled=True,
                sort_order=0,
                has_api_key=True,
                created_at="2026-05-15T00:00:00",
            )
        ]

    def get_provider(self, provider_id):
        self.calls.append(("get_provider", provider_id))
        return ProviderResponse(
            id=provider_id,
            name="My OpenAI",
            provider_type="openai",
            api_base=None,
            enabled=True,
            sort_order=0,
            has_api_key=True,
            created_at="2026-05-15T00:00:00",
        )

    def add_provider(self, provider_type, **kw):
        self.calls.append(("add_provider", provider_type, kw))
        return ProviderResponse(
            id="prov-new",
            name=kw.get("name") or provider_type,
            provider_type=provider_type,
            api_base=kw.get("api_base"),
            enabled=True,
            sort_order=0,
            has_api_key=bool(kw.get("api_key")),
            created_at="2026-05-15T00:00:00",
        )

    def delete_provider(self, provider_id):
        self.calls.append(("delete_provider", provider_id))
        return None

    def list_known_libraries(self):
        from fichero_server.models import KnownLibrary, LibraryRegistryResponse
        from datetime import datetime

        self.calls.append(("list_known_libraries",))
        return LibraryRegistryResponse(
            libraries=[
                KnownLibrary(
                    id="lib-1",
                    path="/Users/daniel/Documents/Test.fichero",
                    name="Test Library",
                    added_at=datetime(2026, 5, 15),
                    last_accessed=datetime(2026, 5, 17),
                )
            ],
            count=1,
        )

    def add_known_library(self, path, name=None):
        from fichero_server.models import KnownLibrary
        from datetime import datetime

        self.calls.append(("add_known_library", path, name))
        return KnownLibrary(
            id="lib-new",
            path=path,
            name=name or "New Library",
            added_at=datetime(2026, 5, 15),
            last_accessed=datetime(2026, 5, 17),
        )

    def remove_known_library(self, path):
        self.calls.append(("remove_known_library", path))
        return {"status": "removed", "path": path}

    def update_library_access(self, path):
        from fichero_server.models import KnownLibrary
        from datetime import datetime

        self.calls.append(("update_library_access", path))
        return KnownLibrary(
            id="lib-1",
            path=path,
            name="Test Library",
            added_at=datetime(2026, 5, 15),
            last_accessed=datetime.now(),
        )


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(cli, "FicheroClient", FakeClient)
    # Make `workflow run --wait` polling instant.
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    yield


def _last_client() -> FakeClient:
    return FakeClient.instances[-1]


# -- basic commands --------------------------------------------------------
def test_health_human_output():
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 0
    assert "status: ok" in result.output
    assert _last_client().calls == [("health",)]


def test_health_json_output():
    result = runner.invoke(cli.app, ["--json", "health"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"status": "ok"}


def test_global_options_passed_to_client():
    result = runner.invoke(
        cli.app,
        [
            "--library",
            "/tmp/L.fichero",
            "--base-url",
            "http://x",
            "--token",
            "tk",
            "--as-user",
            "alice",
            "health",
        ],
    )
    assert result.exit_code == 0
    assert _last_client().kwargs == {
        "base_url": "http://x",
        "library_path": "/tmp/L.fichero",
        "token": "tk",
        "as_user": "alice",
    }


def test_generated_ingest_commands_send_request_body_path(tmp_path):
    file_path = tmp_path / "upload.txt"
    file_path.write_text("hello")
    folder_path = tmp_path / "folder"
    folder_path.mkdir()

    file_result = runner.invoke(
        cli.app,
        ["--json", "ingest", "file", "--path", str(file_path)],
    )
    assert file_result.exit_code == 0, file_result.output
    file_call = _last_client().calls[-1]
    assert file_call[:3] == ("request", "POST", "/api/ingest/file")
    assert file_call[3]["json"]["path"] == str(file_path)

    folder_result = runner.invoke(
        cli.app,
        ["--json", "ingest", "folder", "--path", str(folder_path)],
    )
    assert folder_result.exit_code == 0, folder_result.output
    folder_call = _last_client().calls[-1]
    assert folder_call[:3] == ("request", "POST", "/api/ingest/folder")
    assert folder_call[3]["json"]["path"] == str(folder_path)


def test_401_error_suggests_auth_login(monkeypatch):
    class ErrorClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def close(self):
            pass

        def health(self):
            raise FicheroError("GET /api/health -> 401: unauthorized", status_code=401)

    monkeypatch.setattr(cli, "FicheroClient", ErrorClient)
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 1
    assert "Authentication required. Run `fichero auth login`." in result.output


def test_403_error_includes_user_and_library(monkeypatch, tmp_path):
    class ErrorClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def close(self):
            pass

        def health(self):
            raise FicheroError("GET /api/health -> 403: forbidden", status_code=403)

    monkeypatch.setattr(cli, "FicheroClient", ErrorClient)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    client_module._CLI_SESSION_PATH.write_text(
        json.dumps({"session_token": "token", "user": {"username": "alice"}}),
        encoding="utf-8",
    )
    client_module._CLI_SESSION_PATH.chmod(0o600)
    result = runner.invoke(cli.app, ["--library", "/tmp/Lib.fichero", "health"])
    assert result.exit_code == 1
    assert "Access denied for alice on /tmp/Lib.fichero." in result.output


def test_401_error_for_missing_selected_user_session(monkeypatch, tmp_path):
    class ErrorClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def close(self):
            pass

        def health(self):
            raise FicheroError("GET /api/health -> 401: unauthorized", status_code=401)

    monkeypatch.setattr(cli, "FicheroClient", ErrorClient)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    client_module._CLI_SESSION_PATH.write_text(
        json.dumps({"current_user": "alice", "sessions": {}}),
        encoding="utf-8",
    )
    result = runner.invoke(cli.app, ["--as-user", "bob", "health"])
    assert result.exit_code == 1
    assert "No stored session for bob. Run `fichero auth login bob`." in result.output


def test_generated_actions_group_is_exposed():
    result = runner.invoke(cli.app, ["actions", "--help"])
    assert result.exit_code == 0
    assert "list-by-category" in result.output
    assert "record-use" in result.output


def test_generated_document_commands_attach_to_docs_app():
    result = runner.invoke(cli.app, ["docs", "--help"])
    assert result.exit_code == 0
    assert "list-collections" in result.output


def test_plural_document_group_is_not_exposed_when_docs_app_exists():
    result = runner.invoke(cli.app, ["documents", "--help"])
    assert result.exit_code != 0


def test_root_exposes_shell_completion_options():
    # Typer 0.25 stopped listing --install-completion/--show-completion in the
    # rich `--help` panel, so assert the options are WIRED by invoking them:
    # a missing option prints "No such option", a present one reaches shell
    # detection (which fails in the test env, hence a non-zero exit is fine).
    for flag in ("--install-completion", "--show-completion"):
        result = runner.invoke(cli.app, [flag])
        assert "No such option" not in result.output, f"{flag} is not wired"


def test_sergio_import_command_is_exposed():
    # The command exists...
    assert runner.invoke(cli.app, ["import-sergio-corpus", "--help"]).exit_code == 0
    # ...and exposes --spreadsheet-path. Assert the option is WIRED by invoking
    # it (a present option errs "requires an argument"; a missing one errs
    # "No such option") rather than grepping the rich --help table, which wraps
    # the flag across lines at CliRunner's default 80-col width and flakes.
    result = runner.invoke(cli.app, ["import-sergio-corpus", "--spreadsheet-path"])
    assert "No such option" not in result.output


def test_generated_command_forwards_path_params_via_raw_request():
    result = runner.invoke(cli.app, ["actions", "list-by-category", "history"])
    assert result.exit_code == 0
    assert _last_client().calls == [
        (
            "request",
            "GET",
            "/api/actions/category/history",
            {"params": None, "json": None, "files": None},
        )
    ]


def test_generated_json_body_command_uses_typed_request_flags():
    result = runner.invoke(
        cli.app,
        [
            "actions",
            "create",
            "--name",
            "Example",
            "--category",
            "builtin",
            "--tags",
            '["cli"]',
            "--node-template",
            '{"kind":"leaf"}',
        ],
    )
    assert result.exit_code == 0
    assert _last_client().calls == [
        (
            "request",
            "POST",
            "/api/actions",
            {
                "params": None,
                "json": {
                    "name": "Example",
                    "category": "builtin",
                    "tags": ["cli"],
                    "node_template": {"kind": "leaf"},
                },
                "files": None,
            },
        )
    ]


def test_activity_stream_command_supports_json():
    result = runner.invoke(cli.app, ["--json", "activity-stream", "--thread-id", "t-1"])
    assert result.exit_code == 0
    assert _last_client().calls == [
        (
            "request_stream",
            "GET",
            "/api/activity/stream",
            {"params": {
                "types": None,
                "levels": None,
                "workflow_id": None,
                "batch_id": None,
                "thread_id": "t-1",
            }},
        )
    ]
    assert '"thread_id": "t-1"' in result.output
    assert '"type": "tick"' in result.output


def test_workflow_stream_command_reaches_sse_endpoint():
    result = runner.invoke(cli.app, ["workflow", "stream", "t-1"])
    assert result.exit_code == 0
    assert _last_client().calls == [
        ("request_stream", "GET", "/api/workflow-execution/stream/t-1", {"params": None})
    ]
    assert "type: tick" in result.output


def test_docs_list_forwards_filters():
    result = runner.invoke(cli.app, ["docs", "list", "--parent", "p1", "--limit", "3"])
    assert result.exit_code == 0
    _, kw = _last_client().calls[0]
    assert kw["parent_id"] == "p1"
    assert kw["limit"] == 3
    assert "Doc One" in result.output


def test_docs_get_passes_id():
    result = runner.invoke(cli.app, ["docs", "get", "abc"])
    assert result.exit_code == 0
    assert ("get_document", "abc") in _last_client().calls


def test_docs_translate_passes_language_options():
    result = runner.invoke(
        cli.app,
        ["docs", "translate", "doc-7", "--to", "en", "--source", "nl"],
    )
    assert result.exit_code == 0
    assert ("translate_document", "doc-7", "en", "nl") in _last_client().calls


def test_import_passes_path_and_parent():
    result = runner.invoke(cli.app, ["import", "/tmp/file.pdf", "--parent", "f1"])
    assert result.exit_code == 0
    assert ("import_file", "/tmp/file.pdf", "f1") in _last_client().calls


# -- workflow run ----------------------------------------------------------
def test_workflow_run_resolves_name_to_id():
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7"])
    assert result.exit_code == 0
    run_call = next(c for c in _last_client().calls if c[0] == "run_workflow")
    assert run_call[1] == "wf-1"
    assert run_call[2] == {"selected_doc_ids": ["doc-7"]}


def test_workflow_run_unknown_name_errors():
    result = runner.invoke(cli.app, ["workflow", "run", "Nope", "doc-7"])
    assert result.exit_code == 1
    assert "No workflow named 'Nope'" in result.output


def test_workflow_run_wait_polls_until_terminal():
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # The wait loop now polls the activity log (#1088). The fake emits
    # workflow_completed on the second call, so we expect at least two polls.
    polls = [c for c in _last_client().calls if c[0] == "list_activities"]
    assert len(polls) >= 2
    assert "status: completed" in result.output


def test_workflow_run_accepts_id_directly():
    result = runner.invoke(cli.app, ["workflow", "run", "wf-2", "doc-7"])
    assert result.exit_code == 0
    run_call = next(c for c in _last_client().calls if c[0] == "run_workflow")
    assert run_call[1] == "wf-2"


def test_compare_models_command_renders_table():
    result = runner.invoke(
        cli.app,
        ["compare", "models", "--prompt", "hello", "--models", "openai/gpt-4o,google/gemini-2.5-flash"],
    )
    assert result.exit_code == 0
    assert "cmp-cli-models" in result.output
    assert "[fastest]" in result.output
    assert "[cheapest]" in result.output
    call = next(c for c in _last_client().calls if c[0] == "compare_models")
    assert call[1] == "hello"


def test_compare_vision_command_base64_encodes_image(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"png-bytes")
    result = runner.invoke(
        cli.app,
        [
            "compare",
            "vision",
            "--image",
            str(image),
            "--models",
            "openai/gpt-4o",
        ],
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "compare_vision")
    assert call[1][0].startswith("data:image/png;base64,")


def test_compare_tool_command_reads_json_file(tmp_path):
    payload = tmp_path / "inputs.json"
    payload.write_text(json.dumps({"text": "hola"}), encoding="utf-8")
    result = runner.invoke(
        cli.app,
        [
            "compare",
            "tool",
            "--tool",
            "translate",
            "--inputs-json",
            str(payload),
            "--models",
            "openai/gpt-4o",
        ],
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "compare_tool")
    assert call[1] == "translate"
    assert call[2] == {"text": "hola"}


def test_compare_workflow_command_supports_json_output():
    result = runner.invoke(
        cli.app,
        [
            "compare",
            "workflow",
            "--workflow",
            "wf-1",
            "--doc",
            "doc-7",
            "--models",
            "openai/gpt-4o",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["comparison_id"] == "cmp-cli-workflow"
    call = next(c for c in _last_client().calls if c[0] == "compare_workflow")
    assert call[1] == "wf-1"
    assert call[2] == "doc-7"


def test_workflow_run_wait_tolerates_404_status_endpoint(monkeypatch):
    """A 404 from the status endpoint must NOT abort the wait — fast or
    empty runs may finish before any checkpoint is written, so the activity
    log is the real signal. Status 404 is "not ready yet, keep polling".
    """

    def status_404(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("not ready", status_code=404)

    monkeypatch.setattr(FakeClient, "execution_status", status_404)
    # The default fake list_activities emits workflow_completed on its
    # second call, so the loop should still reach a terminal verdict.
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # The activity log must have been polled at least twice (and won the race
    # over the 404'ing status endpoint).
    activity_polls = [c for c in _last_client().calls if c[0] == "list_activities"]
    assert len(activity_polls) >= 2
    assert "status: completed" in result.output


def test_workflow_run_wait_uses_activity_log_not_status(monkeypatch):
    """Regression for #1088: the wait loop must NOT short-circuit on the
    status endpoint reporting "completed" — that's only true between nodes
    when there are no pending writes. The terminal signal is a
    ``workflow_completed`` event in the activity log.
    """
    # Status endpoint perpetually lies that we're done.
    def always_completed(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        return {"thread_id": thread_id, "status": "completed", "current_state": {}}

    activity_calls = {"count": 0}

    def slow_executor(self, *, thread_id=None, types=None, limit=100):
        self.calls.append(("list_activities", thread_id, types, limit))
        activity_calls["count"] += 1
        # Three empty polls before the executor finishes.
        if activity_calls["count"] < 4:
            return []
        return [
            {
                "id": "act-end",
                "type": "workflow_completed",
                "thread_id": thread_id,
                "workflow_id": "wf-1",
            }
        ]

    monkeypatch.setattr(FakeClient, "execution_status", always_completed)
    monkeypatch.setattr(FakeClient, "list_activities", slow_executor)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 0
    # The activity log must have been polled multiple times — proves we
    # didn't trust the status endpoint's premature "completed".
    assert activity_calls["count"] >= 4


def test_workflow_run_wait_propagates_non_404_errors(monkeypatch):
    """A 500 (or any non-404) during polling should bail out, not loop."""

    def boom(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("kaboom", status_code=500)

    monkeypatch.setattr(FakeClient, "execution_status", boom)
    result = runner.invoke(cli.app, ["workflow", "run", "Catalogue", "doc-7", "--wait"])
    assert result.exit_code == 1
    assert "kaboom" in result.output


def test_workflow_run_wait_raises_on_timeout(monkeypatch):
    """If no terminal activity event ever appears, surface a timeout —
    do NOT return silently with empty output, which would mask the failure.

    The wait loop now keys off the activity log (#1088 fix). Simulate an
    executor that never emits ``workflow_completed`` by returning empty
    activity payloads forever, and shrink both poll-budget knobs so the
    test exits quickly.
    """

    def perma_404(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        raise FicheroError("not ready", status_code=404)

    def empty_activities(self, *, thread_id=None, types=None, limit=100):
        self.calls.append(("list_activities", thread_id, types, limit))
        return []

    monkeypatch.setattr(FakeClient, "execution_status", perma_404)
    monkeypatch.setattr(FakeClient, "list_activities", empty_activities)
    # Shrink both budgets so the test is fast — wall-clock dominates with
    # zero timeout, attempt cap is the safety net.
    monkeypatch.setattr(cli, "_POLL_MAX_ATTEMPTS", 3)
    result = runner.invoke(
        cli.app,
        ["workflow", "run", "Catalogue", "doc-7", "--wait", "--timeout", "0"],
    )
    assert result.exit_code == 1
    assert "Timed out" in result.output
    assert "fichero activity" in result.output


# -- workflow run --wait #1079: workflow_id/name on terminal payload --------
def test_workflow_run_wait_resolves_workflow_id_when_status_says_unknown(monkeypatch):
    """Regression for #1079: when the status endpoint reports
    ``workflow_id: unknown`` (which it does for fast runs whose checkpoint
    metadata hasn't been hydrated), the CLI must fall back to the workflow
    id we passed to ``run_workflow``.
    """

    def status_unknown(self, thread_id):
        self.calls.append(("execution_status", thread_id))
        return {
            "thread_id": thread_id,
            "workflow_id": "unknown",
            "workflow_name": "Unknown",
            "status": "completed",
        }

    monkeypatch.setattr(FakeClient, "execution_status", status_unknown)
    result = runner.invoke(
        cli.app, ["--json", "workflow", "run", "Catalogue", "doc-7", "--wait"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    # We resolved "Catalogue" -> wf-1 client-side; that id must replace
    # the placeholder so users can chain to other commands.
    assert payload["workflow_id"] == "wf-1"


# -- artifacts get ---------------------------------------------------------
def test_artifacts_get_prints_header_then_content():
    """`artifacts get <id>` shows provenance fields then a separator then content."""
    result = runner.invoke(cli.app, ["artifacts", "get", "a-99"])
    assert result.exit_code == 0
    out = result.output
    assert "id: a-99" in out
    assert "document_id: doc-7" in out
    assert "artifact_type: transcription" in out
    assert "provider/model: openai/gpt-4o" in out
    assert "version: 2" in out
    # Separator (60 dashes) and the actual content body.
    assert "-" * 60 in out
    assert "hello world" in out
    # Header must come before content — separator is the boundary.
    sep_idx = out.index("-" * 60)
    assert out.index("artifact_type") < sep_idx < out.index("hello world")
    assert ("get_artifact", "a-99") in _last_client().calls


def test_artifacts_get_json_emits_raw_model():
    """The global --json flag should emit the model dump, not the human view."""
    result = runner.invoke(cli.app, ["--json", "artifacts", "get", "a-99"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["id"] == "a-99"
    assert payload["content"] == "hello world"
    assert payload["provider"] == "openai"


def test_artifacts_list_still_works():
    """The new typer-group conversion preserves the per-doc list behaviour."""
    result = runner.invoke(cli.app, ["artifacts", "list", "doc-7"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_artifacts")
    assert call[1] == "doc-7"


def test_import_manifest_prints_artifact_counts(monkeypatch, tmp_path):
    """The manifest importer summary must expose artifact rows.

    Imported transcripts/entities are first-class backend artifacts; hiding
    their counts in CLI output made it look like import skipped them.
    """
    from fichero_server.importers.manifest_import import ImportSummary

    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")
    library = tmp_path / "library.fichero"

    def fake_import_manifest_via_http(**kwargs):
        assert kwargs["manifest_path"] == manifest
        assert kwargs["library_path"] == library
        assert kwargs["client"].kwargs["base_url"] == "http://remote-engine.test"
        return ImportSummary(
            manifest=str(manifest),
            library_path=str(library),
            nodes_seen=6,
            pages_seen=5,
            documents_created=6,
            documents_skipped=0,
            entities_created=12,
            entities_reused=3,
            artifacts_created=5,
            artifacts_skipped=1,
            claims_created=7,
            claims_skipped=2,
        )

    monkeypatch.setattr(
        "fichero_server.importers.manifest_import.import_manifest_via_http",
        fake_import_manifest_via_http,
    )

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            "http://remote-engine.test",
            "import-manifest",
            "--manifest",
            str(manifest),
            "--library",
            str(library),
        ],
    )

    assert result.exit_code == 0
    assert "artifacts_created: 5" in result.output
    assert "artifacts_skipped: 1" in result.output


# -- import --recursive ---------------------------------------------------
def test_import_directory_recursive(tmp_path):
    """A directory PATH should fan out into per-file imports.

    Hidden files (dot-prefixed) and hidden subdirs are skipped at every depth;
    individual successes/failures are reported per-line; a final summary line
    reports totals. Exit code stays zero unless every file failed.
    """
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / ".hidden.txt").write_text("h")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c")
    hidden_dir = tmp_path / ".dotdir"
    hidden_dir.mkdir()
    (hidden_dir / "x.txt").write_text("x")

    result = runner.invoke(cli.app, ["import", str(tmp_path)])
    assert result.exit_code == 0
    out = result.output
    # Three visible files were imported (recursive default for directories);
    # hidden file and hidden-dir contents are skipped.
    assert "imported a.txt -> d99" in out
    assert "imported b.txt -> d99" in out
    assert "imported c.txt -> d99" in out
    assert ".hidden.txt" not in out
    assert "x.txt" not in out
    assert "summary: 3 imported, 0 failed, 3 total" in out


def test_import_directory_no_recursive(tmp_path):
    """``--no-recursive`` keeps the import to top-level files only."""
    (tmp_path / "a.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("c")

    result = runner.invoke(cli.app, ["import", str(tmp_path), "--no-recursive"])
    assert result.exit_code == 0
    assert "imported a.txt" in result.output
    assert "c.txt" not in result.output
    assert "summary: 1 imported, 0 failed, 1 total" in result.output


def test_import_directory_continues_on_failure(monkeypatch, tmp_path):
    """One failure must not abort the batch — log and keep going."""
    (tmp_path / "ok.txt").write_text("o")
    (tmp_path / "bad.txt").write_text("b")

    def selective_import(self, path, parent_id=None):
        self.calls.append(("import_file", path, parent_id))
        if path.endswith("bad.txt"):
            raise FicheroError("boom")
        return {"id": "d-ok", "filename": path}

    monkeypatch.setattr(FakeClient, "import_file", selective_import)
    result = runner.invoke(cli.app, ["import", str(tmp_path)])
    assert result.exit_code == 0  # partial success is still success
    out = result.output
    assert "imported ok.txt -> d-ok" in out
    assert "failed bad.txt: boom" in out
    assert "summary: 1 imported, 1 failed, 2 total" in out


def test_import_single_file_unchanged(tmp_path):
    """Single-file calls keep the original typed-output behaviour for back-
    compat with existing scripts and the JSON contract."""
    target = tmp_path / "one.pdf"
    target.write_text("data")
    result = runner.invoke(cli.app, ["import", str(target), "--parent", "f1"])
    assert result.exit_code == 0
    # The original code path delegates to a single import_file call.
    assert ("import_file", str(target), "f1") in _last_client().calls


# -- kg / search / activity ------------------------------------------------
def test_kg_entities_filters_to_entities_only():
    """`kg entities` is library-wide and emits only the entity list."""
    result = runner.invoke(cli.app, ["--json", "kg", "entities"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]["id"] == "e1"
    assert payload[0]["canonical_name"] == "Bogotá"
    # Sibling fields from the inspector must not leak through.
    assert "should not appear" not in result.output
    assert "a-other" not in result.output


def test_kg_claims_positional_doc_id():
    """`kg claims <doc-id>` passes doc-id as source_document_id."""
    result = runner.invoke(cli.app, ["kg", "claims", "d5"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1]["source_document_id"] == "d5"


def test_kg_entities_lists_library_wide():
    """`kg entities` is a library-wide listing — no doc-id required; it succeeds
    and calls list_entities (entity_type/limit only)."""
    result = runner.invoke(cli.app, ["kg", "entities"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_entities")
    assert "entity_type" in call[1] and "limit" in call[1]


def test_kg_search_passes_query():
    result = runner.invoke(cli.app, ["kg", "search", "land reform"])
    assert result.exit_code == 0
    call = _last_client().calls[0]
    assert call[0] == "kg_search" and call[1] == "land reform"


def test_notes_create_json_output_is_stable():
    result = runner.invoke(
        cli.app,
        [
            "--json",
            "notes",
            "create",
            "Remember this",
            "--title",
            "Field note",
            "--tag",
            "field",
            "--doc",
            "doc-1",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["id"] == "note-z1"
    assert payload["body"] == "Remember this"
    call = _last_client().calls[0]
    assert call[0] == "create_note"
    assert call[1]["linked_document_ids"] == ["doc-1"]


def test_notes_list_and_get_call_client():
    list_result = runner.invoke(cli.app, ["notes", "list", "--kind", "zettel", "--query", "field"])
    assert list_result.exit_code == 0
    assert _last_client().calls[0] == (
        "list_notes",
        {
            "kind": "zettel",
            "tag": None,
            "linked_entity_id": None,
            "linked_claim_id": None,
            "linked_document_id": None,
            "query": "field",
        },
    )

    get_result = runner.invoke(cli.app, ["notes", "get", "note-z1"])
    assert get_result.exit_code == 0
    assert _last_client().calls[0] == ("get_note", "note-z1")



def test_search_command():
    result = runner.invoke(cli.app, ["search", "archive", "--limit", "5"])
    assert result.exit_code == 0
    call = _last_client().calls[0]
    assert call[1] == "archive" and call[2]["limit"] == 5


def test_activity_command():
    result = runner.invoke(cli.app, ["activity"])
    assert result.exit_code == 0
    assert "completed" in result.output


# -- error handling --------------------------------------------------------
def test_client_error_exits_nonzero(monkeypatch):
    def boom(self):
        raise FicheroError("Cannot connect to the Fichero backend")

    monkeypatch.setattr(FakeClient, "health", boom)
    result = runner.invoke(cli.app, ["health"])
    assert result.exit_code == 1


# -- formatters ------------------------------------------------------------
def test_render_json_is_valid():
    out = render({"b": 2, "a": 1}, as_json=True)
    assert json.loads(out) == {"a": 1, "b": 2}


def test_render_list_one_line_per_item():
    out = render([{"id": "d1", "title": "One"}, {"id": "d2", "title": "Two"}])
    assert out.splitlines() == ["- d1  One", "- d2  Two"]


def test_render_unwraps_envelope():
    out = render({"documents": [{"id": "d1", "name": "N"}]})
    assert out.startswith("documents (1):")
    assert "- d1  N" in out


def test_render_empty_list():
    assert render([]) == "(empty)"


def test_render_none():
    assert render(None) == "(no data)"


def test_render_nested_dict():
    out = render({"id": "d1", "meta": {"pages": 3}})
    assert "id: d1" in out
    assert "meta:" in out
    assert "pages: 3" in out


def test_render_top_entity():
    from fichero_cli.formatters import render_top_entity
    from fichero_server.api.routes.entity.entities import TopEntityRow

    # Test with all fields
    entity = TopEntityRow(
        entity_id="e1", name="Bogotá", kind="place", claim_count=5
    )
    out = render_top_entity(entity)
    assert "Bogotá" in out
    assert "place" in out
    assert "5" in out
    # Should not show missing
    assert "(missing)" not in out

    # Test with missing optional kind
    entity2 = TopEntityRow(entity_id="e2", name="Colombia", kind=None, claim_count=10)
    out2 = render_top_entity(entity2)
    assert "Colombia" in out2
    assert "10" in out2


# -- library create / list -------------------------------------------------
def test_library_create_calls_client_with_expanded_path():
    """`library create ~/Foo.fichero` expands ~ before sending to client."""
    result = runner.invoke(cli.app, ["library", "create", "~/Documents/x.fichero"])
    assert result.exit_code == 0, result.output
    call = next(c for c in _last_client().calls if c[0] == "create_library")
    # ~ must be expanded — the backend allowlist works on expanded paths.
    assert not call[1].startswith("~")
    assert call[1].endswith("/Documents/x.fichero")
    assert "created and registered" in result.output.lower()


def test_library_create_json_emits_typed_response():
    result = runner.invoke(
        cli.app, ["--json", "library", "create", "/var/folders/test.fichero"]
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # `library create` now emits a status summary after create + auto-register.
    assert "created and registered" in payload["status"].lower()
    assert "/var/folders/test.fichero" in payload["status"]


def test_library_list_walks_filesystem(tmp_path, monkeypatch):
    """`library list` queries the backend registry for known libraries."""
    result = runner.invoke(cli.app, ["library", "list"])
    assert result.exit_code == 0, result.output
    # FakeClient.list_known_libraries returns "Test Library" at lib-1.
    assert "Test Library" in result.output
    # The backend was called.
    assert ("list_known_libraries",) in _last_client().calls


def test_library_list_json(tmp_path, monkeypatch):
    result = runner.invoke(cli.app, ["--json", "library", "list"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # FakeClient returns a LibraryRegistryResponse; --json emits its items list.
    libraries = payload if isinstance(payload, list) else payload.get("libraries", payload.get("items", []))
    assert len(libraries) >= 1


# -- docs extended ---------------------------------------------------------
def test_docs_delete_requires_confirmation():
    result = runner.invoke(cli.app, ["docs", "delete", "d1"], input="n\n")
    assert result.exit_code != 0
    # When user aborts the confirmation, no client is created at all.
    for fc in FakeClient.instances:
        assert ("delete_document", "d1") not in fc.calls


def test_docs_delete_yes_flag():
    result = runner.invoke(cli.app, ["docs", "delete", "d1", "--yes"])
    assert result.exit_code == 0
    assert ("delete_document", "d1") in _last_client().calls


def test_generated_delete_requires_confirmation():
    result = runner.invoke(cli.app, ["actions", "delete", "act-1"], input="n\n")
    assert result.exit_code != 0
    assert FakeClient.instances == []


def test_generated_commands_use_canonical_resource_trees():
    assert runner.invoke(cli.app, ["library", "--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["canvas", "--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["libraries", "--help"]).exit_code != 0
    assert runner.invoke(cli.app, ["mindpalace", "--help"]).exit_code != 0


def test_docs_update_passes_fields():
    result = runner.invoke(cli.app, ["docs", "update", "d1", "--name", "New Name"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "update_document")
    assert call[1] == "d1"
    assert call[2].get("name") == "New Name"


def test_docs_update_requires_fields():
    result = runner.invoke(cli.app, ["docs", "update", "d1"])
    assert result.exit_code == 1


def test_docs_inspector_calls_client():
    result = runner.invoke(cli.app, ["docs", "inspector", "d1"])
    assert result.exit_code == 0
    assert ("document_inspector", "d1") in _last_client().calls


def test_docs_kg_calls_client():
    result = runner.invoke(cli.app, ["docs", "kg", "d1"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "document_knowledge_graph")
    assert call[1] == "d1"


# -- artifacts extended ----------------------------------------------------
def test_artifacts_update_content():
    result = runner.invoke(
        cli.app, ["artifacts", "update", "a-1", "--content", "new text"]
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "update_artifact")
    assert call[1] == "a-1"
    assert call[2] == "new text"


def test_artifacts_delete_yes_flag():
    result = runner.invoke(cli.app, ["artifacts", "delete", "a-1", "--yes"])
    assert result.exit_code == 0
    assert ("delete_artifact", "a-1") in _last_client().calls


def test_artifacts_delete_requires_confirmation():
    result = runner.invoke(cli.app, ["artifacts", "delete", "a-1"], input="n\n")
    assert result.exit_code != 0


# -- claim -----------------------------------------------------------------
def test_claim_get():
    result = runner.invoke(cli.app, ["claim", "get", "c-1"])
    assert result.exit_code == 0
    assert ("get_claim", "c-1") in _last_client().calls


def test_claim_update_text():
    result = runner.invoke(cli.app, ["claim", "update", "c-1", "--text", "Updated"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "update_claim")
    assert call[2].get("text") == "Updated"


def test_claim_delete_yes():
    result = runner.invoke(cli.app, ["claim", "delete", "c-1", "--yes"])
    assert result.exit_code == 0
    assert ("delete_claim", "c-1") in _last_client().calls


def test_claim_review():
    result = runner.invoke(
        cli.app, ["claim", "review", "c-1", "--status", "approved"]
    )
    assert result.exit_code == 0
    assert ("review_claim", "c-1", "approved") in _last_client().calls


def test_claim_list_with_doc_filter():
    result = runner.invoke(cli.app, ["claim", "list", "--doc", "d5"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1].get("source_document_id") == "d5"


# -- entity ----------------------------------------------------------------
def test_entity_get():
    result = runner.invoke(cli.app, ["entity", "get", "e-1"])
    assert result.exit_code == 0
    assert ("get_entity", "e-1") in _last_client().calls


def test_entity_update_name():
    result = runner.invoke(
        cli.app, ["entity", "update", "e-1", "--name", "Cartagena"]
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "update_entity")
    assert call[2].get("canonical_name") == "Cartagena"


def test_entity_delete_yes():
    result = runner.invoke(cli.app, ["entity", "delete", "e-1", "--yes"])
    assert result.exit_code == 0
    assert ("delete_entity", "e-1") in _last_client().calls


def test_entity_merge():
    result = runner.invoke(cli.app, ["entity", "merge", "e-1", "e-2"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "merge_entities")
    assert call[1] == "e-1"
    assert "e-2" in call[2]


def test_entity_split():
    result = runner.invoke(cli.app, ["entity", "split", "e-1", "e-2"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "split_entity")
    assert call[1] == "e-1"


def test_entity_top():
    result = runner.invoke(cli.app, ["entity", "top", "--limit", "5"])
    assert result.exit_code == 0
    assert ("top_entities", 5) in _last_client().calls
    # Verify formatter shows entity name, not "(missing)"
    assert "Bogotá" in result.output
    assert "(missing)" not in result.output


def test_entity_documents():
    result = runner.invoke(cli.app, ["entity", "documents", "e-1"])
    assert result.exit_code == 0
    assert ("entity_documents", "e-1") in _last_client().calls


def test_entity_co_occurrence():
    result = runner.invoke(cli.app, ["entity", "co-occurrence", "e-1"])
    assert result.exit_code == 0
    assert ("entity_co_occurrence", "e-1") in _last_client().calls


def test_entity_resolve():
    result = runner.invoke(cli.app, ["entity", "resolve", "Bogota"])
    assert result.exit_code == 0
    assert ("resolve_entity", "Bogota") in _last_client().calls


# -- audit -----------------------------------------------------------------
def test_audit_list():
    result = runner.invoke(cli.app, ["audit", "list", "--limit", "10"])
    assert result.exit_code == 0
    assert ("list_audits", 10) in _last_client().calls


def test_audit_undo():
    result = runner.invoke(cli.app, ["audit", "undo", "audit-1"])
    assert result.exit_code == 0
    assert ("undo_audit", "audit-1") in _last_client().calls


# -- workflow threads ------------------------------------------------------
def test_workflow_threads_list():
    result = runner.invoke(cli.app, ["workflow", "threads", "list"])
    assert result.exit_code == 0
    assert ("list_threads", 100) in _last_client().calls


def test_workflow_threads_delete_yes():
    result = runner.invoke(
        cli.app, ["workflow", "threads", "delete", "t-abc", "--yes"]
    )
    assert result.exit_code == 0
    assert ("delete_thread", "t-abc") in _last_client().calls


def test_workflow_status():
    result = runner.invoke(cli.app, ["workflow", "status", "t-1"])
    assert result.exit_code == 0
    assert ("execution_status", "t-1") in _last_client().calls


# -- settings --------------------------------------------------------------
def test_settings_list():
    result = runner.invoke(cli.app, ["settings", "list"])
    assert result.exit_code == 0
    assert ("get_settings",) in _last_client().calls
    assert "text_model" in result.output


def test_settings_get():
    result = runner.invoke(cli.app, ["settings", "get", "text_model"])
    assert result.exit_code == 0
    assert "gpt-4o" in result.output


def test_settings_get_missing_key():
    result = runner.invoke(cli.app, ["settings", "get", "nonexistent_key"])
    assert result.exit_code == 1


def test_settings_set():
    result = runner.invoke(
        cli.app, ["settings", "set", "text_model", "claude-sonnet-4-6"]
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "set_settings")
    assert call[1].get("text_model") == "claude-sonnet-4-6"


# -- providers -------------------------------------------------------------
def test_providers_list():
    result = runner.invoke(cli.app, ["providers", "list"])
    assert result.exit_code == 0
    assert ("list_providers",) in _last_client().calls
    assert "My OpenAI" in result.output


def test_providers_get():
    result = runner.invoke(cli.app, ["providers", "get", "prov-1"])
    assert result.exit_code == 0
    assert ("get_provider", "prov-1") in _last_client().calls


def test_providers_add():
    result = runner.invoke(
        cli.app,
        ["providers", "add", "--type", "anthropic", "--name", "My Anthropic"],
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "add_provider")
    assert call[1] == "anthropic"
    assert call[2].get("name") == "My Anthropic"


def test_providers_delete_yes():
    result = runner.invoke(cli.app, ["providers", "delete", "prov-1", "--yes"])
    assert result.exit_code == 0
    assert ("delete_provider", "prov-1") in _last_client().calls


# -- library lifecycle (registry) ------------------------------------------
def test_library_list():
    result = runner.invoke(cli.app, ["library", "list"])
    assert result.exit_code == 0
    assert ("list_known_libraries",) in _last_client().calls
    assert "Test Library" in result.output or "Test.fichero" in result.output


def test_library_list_empty():
    """When no libraries are registered, display (no libraries)."""
    FakeClient.instances.clear()

    def empty_client(**_kwargs):
        fake = FakeClient()
        fake.kwargs = {}
        fake.calls = []
        return fake

    class EmptyClient(FakeClient):
        def list_known_libraries(self):
            from fichero_server.models import LibraryRegistryResponse

            self.calls.append(("list_known_libraries",))
            return LibraryRegistryResponse(libraries=[], count=0)

    # Monkey-patch for this test
    import fichero_cli.__main__ as cli_module

    old_client_class = cli_module.FicheroClient
    try:
        cli_module.FicheroClient = EmptyClient
        result = runner.invoke(cli_module.app, ["library", "list"])
        assert result.exit_code == 0
        assert "(no libraries)" in result.output
    finally:
        cli_module.FicheroClient = old_client_class


def test_library_add():
    result = runner.invoke(cli.app, ["library", "add", "~/Documents/MyLib.fichero"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "add_known_library")
    assert "MyLib.fichero" in call[1]
    assert "Added:" in result.output


def test_library_remove():
    result = runner.invoke(cli.app, ["library", "remove", "~/Documents/MyLib.fichero"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "remove_known_library")
    assert "MyLib.fichero" in call[1]
    assert "Removed:" in result.output


def test_library_create():
    result = runner.invoke(cli.app, ["library", "create", "~/Documents/NewLib.fichero"])
    assert result.exit_code == 0
    calls = _last_client().calls
    # Should call create_library and then add_known_library
    assert any(c[0] == "create_library" for c in calls)
    assert any(c[0] == "add_known_library" for c in calls)
    assert "Created and registered:" in result.output


def test_library_delete_yes():
    """Delete a library with confirmation."""
    result = runner.invoke(
        cli.app, ["library", "delete", "~/Documents/OldLib.fichero", "--yes"]
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "remove_known_library")
    assert "OldLib.fichero" in call[1]
    assert "Deleted:" in result.output


def test_library_delete_no_confirm():
    """Delete aborts when user declines confirmation."""
    result = runner.invoke(
        cli.app, ["library", "delete", "~/Documents/OldLib.fichero"], input="n\n"
    )
    assert result.exit_code == 1


def test_library_open():
    result = runner.invoke(cli.app, ["library", "open", "~/Documents/MyLib.fichero"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "update_library_access")
    assert "MyLib.fichero" in call[1]
    assert "Activated:" in result.output


def test_library_close():
    """Close is a no-op for now but should not error."""
    result = runner.invoke(cli.app, ["library", "close", "~/Documents/MyLib.fichero"])
    assert result.exit_code == 0
    assert "Closed:" in result.output


def test_library_reset_yes():
    result = runner.invoke(cli.app, ["library", "reset", "--yes"])
    assert result.exit_code == 0
    calls = _last_client().calls
    # Should list all libraries and remove each one
    assert ("list_known_libraries",) in calls
    assert any(c[0] == "remove_known_library" for c in calls)
    assert "Reset complete" in result.output


def test_library_reset_no_confirm():
    """Reset aborts when user declines confirmation."""
    result = runner.invoke(cli.app, ["library", "reset"], input="n\n")
    assert result.exit_code == 1


# -- #1348: consistent --doc/-d flag across kg citations, kg claims, artifacts list -----------


def test_kg_claims_positional_still_works():
    """`kg claims <doc-id>` positional form passes doc-id correctly."""
    result = runner.invoke(cli.app, ["kg", "claims", "d5"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1]["source_document_id"] == "d5"


def test_kg_claims_doc_flag():
    """`kg claims --doc <id>` flag form passes doc-id correctly."""
    result = runner.invoke(cli.app, ["kg", "claims", "--doc", "d5"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1]["source_document_id"] == "d5"


def test_kg_claims_doc_short_flag():
    """`kg claims -d <id>` short flag passes doc-id correctly."""
    result = runner.invoke(cli.app, ["kg", "claims", "-d", "d5"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1]["source_document_id"] == "d5"


def test_kg_claims_flag_overrides_positional():
    """`--doc` overrides the positional arg when both are supplied."""
    result = runner.invoke(cli.app, ["kg", "claims", "positional-id", "--doc", "flag-id"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_claims")
    assert call[1]["source_document_id"] == "flag-id"


def test_kg_claims_requires_doc_id():
    """Bare `kg claims` without a doc ID should exit non-zero."""
    result = runner.invoke(cli.app, ["kg", "claims"])
    assert result.exit_code != 0


def test_kg_claims_rejects_empty_doc_flag():
    result = runner.invoke(cli.app, ["kg", "claims", "--doc", ""])
    assert result.exit_code != 0


def test_kg_citations_positional_still_works():
    """`kg citations <doc-id>` positional form passes doc-id correctly."""
    result = runner.invoke(cli.app, ["kg", "citations", "doc-1"])
    assert result.exit_code == 0
    assert ("citations_at_doc", "doc-1") in _last_client().calls


def test_kg_citations_doc_flag():
    """`kg citations --doc <id>` flag form passes doc-id correctly."""
    result = runner.invoke(cli.app, ["kg", "citations", "--doc", "doc-1"])
    assert result.exit_code == 0
    assert ("citations_at_doc", "doc-1") in _last_client().calls


def test_kg_citations_doc_short_flag():
    """`kg citations -d <id>` short flag passes doc-id correctly."""
    result = runner.invoke(cli.app, ["kg", "citations", "-d", "doc-1"])
    assert result.exit_code == 0
    assert ("citations_at_doc", "doc-1") in _last_client().calls


def test_kg_citations_flag_overrides_positional():
    """`--doc` overrides the positional arg when both are supplied."""
    result = runner.invoke(cli.app, ["kg", "citations", "positional-id", "--doc", "flag-id"])
    assert result.exit_code == 0
    assert ("citations_at_doc", "flag-id") in _last_client().calls


def test_kg_citations_requires_doc_id():
    """Bare `kg citations` without a doc ID should exit non-zero."""
    result = runner.invoke(cli.app, ["kg", "citations"])
    assert result.exit_code != 0


def test_kg_citations_rejects_empty_doc_flag():
    result = runner.invoke(cli.app, ["kg", "citations", "--doc", ""])
    assert result.exit_code != 0


def test_artifacts_list_positional_still_works():
    """`artifacts list <doc-id>` positional form still passes doc-id correctly."""
    result = runner.invoke(cli.app, ["artifacts", "list", "doc-7"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_artifacts")
    assert call[1] == "doc-7"


def test_artifacts_list_doc_flag():
    """`artifacts list --doc <id>` flag form passes doc-id correctly."""
    result = runner.invoke(cli.app, ["artifacts", "list", "--doc", "doc-7"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_artifacts")
    assert call[1] == "doc-7"


def test_artifacts_list_doc_short_flag():
    """`artifacts list -d <id>` short flag passes doc-id correctly."""
    result = runner.invoke(cli.app, ["artifacts", "list", "-d", "doc-7"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_artifacts")
    assert call[1] == "doc-7"


def test_artifacts_list_flag_overrides_positional():
    """`--doc` overrides the positional arg when both are supplied."""
    result = runner.invoke(cli.app, ["artifacts", "list", "positional-id", "--doc", "flag-id"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "list_artifacts")
    assert call[1] == "flag-id"


def test_artifacts_list_requires_doc_id():
    """Bare `artifacts list` without a doc ID should exit non-zero."""
    result = runner.invoke(cli.app, ["artifacts", "list"])
    assert result.exit_code != 0


def test_artifacts_list_rejects_empty_doc_flag():
    result = runner.invoke(cli.app, ["artifacts", "list", "--doc", ""])
    assert result.exit_code != 0


def test_artifacts_list_json_flag():
    """`--json artifacts list <doc-id>` emits valid JSON, not human text."""
    result = runner.invoke(cli.app, ["--json", "artifacts", "list", "doc-7"])
    assert result.exit_code == 0
    # Must be parseable JSON.
    payload = json.loads(result.output)
    # FakeClient.list_artifacts returns {"artifacts": [...]} envelope — just
    # confirm the response is JSON (not a human render_artifact string).
    assert isinstance(payload, (dict, list))


def test_artifacts_list_json_flag_with_doc_option():
    """`--json artifacts list --doc <id>` emits valid JSON."""
    result = runner.invoke(cli.app, ["--json", "artifacts", "list", "--doc", "doc-7"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, (dict, list))
