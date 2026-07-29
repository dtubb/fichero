"""Tests for chat/conversation management routes.

Chat routes manage RAG conversations stored per-library. The LLM call path
is out of scope here — tests focus on conversation CRUD (list, get, update,
delete, reorder) and the providers list. Chat routes live at /api/chat/...
"""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from fichero_server.models import Conversation, DocType, Document
from fichero_server.models.node_aliases import make_alias


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conv(
    conv_id: str = "conv-1",
    title: str = "My Chat",
    *,
    scope_document_id: str | None = None,
) -> Conversation:
    return Conversation(
        id=conv_id,
        title=title,
        messages=[],
        scope_document_id=scope_document_id,
    )


class _FakeLLM:
    def __init__(self):
        self.messages = []

    def invoke(self, messages):
        self.messages = messages

        class _Response:
            content = "Ada Lovelace appears in the archive."

        return _Response()

    async def ainvoke(self, messages):
        self.messages = messages

        class _Response:
            content = "Ada Lovelace appears in the archive."

        return _Response()


class _FakeRetrievalPayload:
    def __init__(self):
        self.context_docs = []
        self.sources = []
        self.kg_claims_used = 0
        self.kg_entities_used = 0


# ---------------------------------------------------------------------------
# GET /api/chat/conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_empty_list(self, client):
        r = client.get("/api/chat/conversations")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_conversations(self, client, db):
        db.save(_make_conv("c-1", "First Chat"))
        db.save(_make_conv("c-2", "Second Chat"))

        r = client.get("/api/chat/conversations")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------


class TestChatWithSources:
    def test_chat_continuation_caps_prompt_history_to_recent_turns(
        self, client, db, monkeypatch
    ):
        conv = _make_conv("conv-history-cap", "Long History")
        conv.messages = []
        for i in range(12):
            conv.messages.extend(
                [
                    {"role": "user", "content": f"Q{i}"},
                    {"role": "assistant", "content": f"A{i}"},
                ]
            )
        db.save(conv)

        class _FakeRetriever:
            def retrieve(self, **_kwargs):
                return _FakeRetrievalPayload()

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _FakeRetriever(),
        )

        response = client.post(
            "/api/chat",
            json={
                "conversation_id": conv.id,
                "message": "Newest question",
            },
        )

        assert response.status_code == 200
        assert len(fake_llm.messages) == 22
        assert fake_llm.messages[1].content == "Q2"
        assert fake_llm.messages[2].content == "A2"
        assert fake_llm.messages[-2].content == "A11"
        assert fake_llm.messages[-1].content == "Question: Newest question"
        assert all(msg.content != "Q0" for msg in fake_llm.messages[1:-1])
        assert all(msg.content != "A0" for msg in fake_llm.messages[1:-1])
        assert all(msg.content != "Q1" for msg in fake_llm.messages[1:-1])
        assert all(msg.content != "A1" for msg in fake_llm.messages[1:-1])

    def test_chat_continuation_skips_malformed_stored_history(
        self, client, db, monkeypatch
    ):
        conv = _make_conv("conv-history-malformed", "Malformed History")
        conv.messages = [
            {"role": "system", "content": "ignore me"},
            {"role": "user", "content": "Q0"},
            {"role": "assistant", "content": "A0"},
            {"role": "assistant", "content": "orphan assistant"},
            {"role": "user", "content": "orphan user"},
        ]
        db.save(conv)

        class _FakeRetriever:
            def retrieve(self, **_kwargs):
                return _FakeRetrievalPayload()

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _FakeRetriever(),
        )

        response = client.post(
            "/api/chat",
            json={
                "conversation_id": conv.id,
                "message": "Continue safely",
            },
        )

        assert response.status_code == 200
        assert [msg.content for msg in fake_llm.messages[1:-1]] == ["Q0", "A0"]
        assert fake_llm.messages[-1].content == "Question: Continue safely"

    def test_chat_scoped_to_document_returns_sources(
        self, client, db, monkeypatch
    ):
        doc = Document(
            id="doc-chat-source",
            name="Lovelace notes",
            page_content="Ada Lovelace wrote notes on the Analytical Engine.",
        )
        db.save(doc)

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )

        r = client.post(
            "/api/chat",
            json={
                "message": "Who wrote notes on the Analytical Engine?",
                "document_ids": [doc.id],
                "include_sources": True,
                "provider": "openai",
                "model": "gpt-4o-mini",
            },
        )

        assert r.status_code == 200
        data = r.json()
        assert data["message"] == "Ada Lovelace appears in the archive."
        assert data["sources"] == [
            {
                "document_id": doc.id,
                "document_name": "Lovelace notes",
                "excerpt": "Ada Lovelace wrote notes on the Analytical Engine.",
                "relevance_score": 1.0,
            }
        ]
        assert data["model_used"] == "openai/gpt-4o-mini"
        assert data["kg_claims_used"] == 0
        assert data["kg_entities_used"] == 0
        assert data["document_count"] == 1
        assert data["context_count"] == 1
        assert len(fake_llm.messages) == 2
        assert isinstance(fake_llm.messages[0], SystemMessage)
        assert isinstance(fake_llm.messages[1], HumanMessage)
        assert "[Document 1: Lovelace notes]" in fake_llm.messages[1].content
        assert "transparent, local instrument" in fake_llm.messages[0].content
        assert "Never pretend to be human" in fake_llm.messages[0].content
        assert db.get(Conversation, data["conversation_id"]) is not None

    def test_chat_scope_node_round_trips_and_includes_contained_docs(
        self, client, db, monkeypatch
    ):
        folder = Document(id="chat-folder", name="Scope Folder", doc_type=DocType.folder)
        child = Document(
            id="chat-child",
            name="Contained Doc",
            parent_id=folder.id,
            page_content="Contained archive evidence.",
        )
        db.save(folder)
        db.save(child)

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )

        response = client.post(
            "/api/chat",
            json={
                "message": "What evidence is in scope?",
                "scope_document_id": folder.id,
                "include_sources": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        conv = db.get(Conversation, payload["conversation_id"])
        assert conv is not None
        assert conv.scope_document_id == folder.id
        assert conv.document_ids == [folder.id]
        assert payload["sources"] == [
            {
                "document_id": child.id,
                "document_name": "Contained Doc",
                "excerpt": "Contained archive evidence.",
                "relevance_score": 1.0,
            }
        ]

    def test_chat_conversation_scope_alias_resolves_to_target_node(
        self, client, db, monkeypatch
    ):
        folder = Document(id="chat-folder-alias-target", name="Target", doc_type=DocType.folder)
        child = Document(
            id="chat-folder-alias-child",
            name="Alias Child",
            parent_id=folder.id,
            page_content="Alias-routed evidence.",
        )
        alias = make_alias(folder, parent_id=None, name="Alias Scope")
        conv = _make_conv("conv-alias-scope", scope_document_id=alias.id)
        db.save(folder)
        db.save(child)
        db.save(alias)
        db.save(conv)

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )

        response = client.post(
            "/api/chat",
            json={"message": "Use alias scope", "conversation_id": conv.id},
        )

        assert response.status_code == 200
        assert response.json()["sources"][0]["document_id"] == child.id
        assert db.get(Conversation, conv.id).scope_document_id == alias.id

    def test_chat_conversation_scope_missing_node_prefers_raise(
        self, client, db, monkeypatch
    ):
        conv = _make_conv("conv-missing-scope", scope_document_id="missing-node")
        db.save(conv)

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )

        response = client.post(
            "/api/chat",
            json={"message": "Use missing scope", "conversation_id": conv.id},
        )

        assert response.status_code == 404
        assert "Chat scope node not found: missing-node" in response.json()["detail"]

    def test_chat_passes_graph_knobs_to_retriever(self, client, monkeypatch):
        captured: dict = {}

        class _FakeRetriever:
            def retrieve(self, **kwargs):
                captured.update(kwargs)
                return _FakeRetrievalPayload()

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _FakeRetriever(),
        )

        r = client.post(
            "/api/chat",
            json={
                "message": "Test graph knobs",
                "include_sources": False,
                "graph_hops": 2,
                "max_kg_claims": 9,
            },
        )
        assert r.status_code == 200
        assert captured["graph_hops"] == 2
        assert captured["max_kg_claims"] == 9

    def test_chat_returns_kg_usage_from_retriever(self, client, monkeypatch):
        class _FakeRetriever:
            def retrieve(self, **_kwargs):
                p = _FakeRetrievalPayload()
                p.kg_claims_used = 4
                p.kg_entities_used = 3
                return p

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _FakeRetriever(),
        )

        r = client.post("/api/chat", json={"message": "Use KG"})
        assert r.status_code == 200
        data = r.json()
        assert data["kg_claims_used"] == 4
        assert data["kg_entities_used"] == 3
        assert data["document_count"] == 0
        assert data["context_count"] == 0

    def test_chat_logs_retrieval_diagnostics(self, client, monkeypatch, caplog):
        class _FakeRetriever:
            def retrieve(self, **_kwargs):
                p = _FakeRetrievalPayload()
                p.kg_claims_used = 2
                p.kg_entities_used = 1
                return p

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _FakeRetriever(),
        )

        with caplog.at_level("INFO"):
            r = client.post("/api/chat", json={"message": "Use KG"})
        assert r.status_code == 200
        assert "chat_retrieval" in caplog.text

    def test_chat_retrieval_failure_returns_502_and_skips_llm(self, client, monkeypatch):
        class _BrokenRetriever:
            def retrieve(self, **_kwargs):
                raise RuntimeError("index offline")

        llm_called = False

        class _ShouldNotRunLLM:
            async def ainvoke(self, _messages):
                nonlocal llm_called
                llm_called = True
                return type("_Response", (), {"content": "nope"})()

        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: _ShouldNotRunLLM(),
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _BrokenRetriever(),
        )

        response = client.post("/api/chat", json={"message": "Use retrieval"})

        assert response.status_code == 502
        assert response.json()["detail"] == "Search unavailable — cannot ground the answer"
        assert llm_called is False

    def test_chat_emits_conversation_change_with_actor_context(
        self, client, db, monkeypatch
    ):
        emitted: list[dict] = []
        fake_llm = _FakeLLM()

        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.emit_change",
            lambda library_path, **kwargs: emitted.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        create_response = client.post(
            "/api/chat",
            headers={"X-Fichero-Origin-Window": "chat-window-1"},
            json={"message": "Start a new conversation"},
        )

        assert create_response.status_code == 200
        created_conversation_id = create_response.json()["conversation_id"]
        assert emitted[-1]["type"] == "conversation.created"
        assert emitted[-1]["metadata"] == {"conversation_id": created_conversation_id}
        assert emitted[-1]["origin_window"] == "chat-window-1"
        assert emitted[-1]["origin_user"] == emitted[-1]["actor"]
        assert emitted[-1]["actor"]

        update_response = client.post(
            "/api/chat",
            json={
                "conversation_id": created_conversation_id,
                "message": "Continue the conversation",
            },
        )

        assert update_response.status_code == 200
        assert emitted[-1]["type"] == "conversation.updated"
        assert emitted[-1]["metadata"] == {"conversation_id": created_conversation_id}

    def test_chat_rejects_out_of_range_graph_hops(self, client):
        r = client.post(
            "/api/chat",
            json={
                "message": "Test invalid graph hops",
                "graph_hops": 99,
            },
        )
        assert r.status_code == 422

    def test_chat_rejects_empty_message_with_400(self, client):
        response = client.post("/api/chat", json={"message": "   "})

        assert response.status_code == 400
        assert response.json()["detail"] == "Message cannot be empty"

    def test_chat_rejects_missing_required_message_field(self, client):
        response = client.post("/api/chat", json={"include_sources": True})

        assert response.status_code == 422

    def test_chat_surfaces_retrieval_sources_when_present(self, client, monkeypatch):
        class _FakeRetriever:
            def retrieve(self, **_kwargs):
                payload = _FakeRetrievalPayload()
                payload.context_docs = [
                    {
                        "kind": "document",
                        "id": "doc-1",
                        "name": "Archive note",
                        "content": "Ada kept detailed archival notes.",
                    }
                ]
                payload.sources = [
                    {
                        "document_id": "doc-1",
                        "document_name": "Archive note",
                        "excerpt": "Ada kept detailed archival notes.",
                        "relevance_score": 0.91,
                    }
                ]
                return payload

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero_server.api.routes.chat.GraphAwareRetriever",
            lambda *_args, **_kwargs: _FakeRetriever(),
        )

        response = client.post(
            "/api/chat",
            json={"message": "What do the notes say?", "include_sources": True},
        )

        assert response.status_code == 200
        assert response.json()["sources"] == [
            {
                "document_id": "doc-1",
                "document_name": "Archive note",
                "excerpt": "Ada kept detailed archival notes.",
                "relevance_score": 0.91,
            }
        ]

    def test_chat_provider_error_prefers_raise_over_silent_fallback(
        self, client, monkeypatch
    ):
        class _BrokenLLM:
            def invoke(self, _messages):
                raise RuntimeError("provider misconfigured")

            async def ainvoke(self, _messages):
                raise RuntimeError("provider misconfigured")

        monkeypatch.setattr(
            "fichero_server.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: _BrokenLLM(),
        )

        with pytest.raises(RuntimeError, match="provider misconfigured"):
            client.post(
                "/api/chat",
                json={
                    "message": "hello",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                },
            )


# ---------------------------------------------------------------------------
# GET /api/chat/conversations/{id}
# ---------------------------------------------------------------------------


class TestGetConversation:
    def test_get_existing(self, client, db):
        conv = _make_conv("c-get", "Test conversation")
        db.save(conv)

        r = client.get("/api/chat/conversations/c-get")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "c-get"
        assert data["title"] == "Test conversation"
        assert "messages" in data

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/chat/conversations/no-such-conv")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/chat/conversations/{id}
# ---------------------------------------------------------------------------


class TestUpdateConversation:
    def test_update_title(self, client, db):
        conv = _make_conv("c-upd", "Old Title")
        db.save(conv)

        r = client.put("/api/chat/conversations/c-upd", json={"title": "New Title"})
        assert r.status_code == 200
        assert r.json()["title"] == "New Title"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/chat/conversations/no-such", json={"title": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/chat/conversations/{id}
# ---------------------------------------------------------------------------


class TestDeleteConversation:
    def test_delete_existing(self, client, db):
        conv = _make_conv("c-del", "To Delete")
        db.save(conv)

        r = client.delete("/api/chat/conversations/c-del")
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/chat/conversations/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Agent workspace nodes (#3547)
# ---------------------------------------------------------------------------


class TestAgentWorkspaceNodes:
    def test_save_list_reload_and_soft_delete_round_trip(self, client, db):
        conversation = _make_conv("workspace-conversation", "Letter investigation")
        conversation.provider = "openai"
        conversation.model = "gpt-4o-mini"
        conversation.document_ids = ["source-a"]
        conversation.messages = [
            {"role": "user", "content": "What does this letter say?"},
            {"role": "assistant", "content": "It concerns the 1844 petition."},
        ]
        db.save(conversation)

        saved = client.post(
            f"/api/chat/conversations/{conversation.id}/workspace",
            json={"title": "Petition workspace"},
        )
        assert saved.status_code == 200
        workspace = saved.json()
        assert workspace["title"] == "Petition workspace"
        assert workspace["model"] == "gpt-4o-mini"
        assert workspace["message_history_ref"] == conversation.id
        assert workspace["members"][0]["id"] == "source:source-a"
        assert workspace["members"][0]["target_type"] == "document"
        assert workspace["members"][0]["target_id"] == "source-a"
        assert workspace["members"][0]["role"] == "scoped_source"
        assert workspace["members"][0]["added_at"]

        listed = client.get("/api/chat/workspaces")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [workspace["id"]]

        reloaded = client.get(f"/api/chat/workspaces/{workspace['id']}")
        assert reloaded.status_code == 200
        assert reloaded.json()["messages"] == conversation.messages

        deleted = client.delete(f"/api/chat/workspaces/{workspace['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted", "id": workspace["id"]}
        assert db.get(Document, workspace["id"]).deleted_at is not None
        assert db.get(Conversation, conversation.id) is not None

    def test_membership_add_and_remove(self, client, db):
        conversation = _make_conv("workspace-members", "Members")
        conversation.messages = [{"role": "user", "content": "Find relevant claims."}]
        db.save(conversation)
        workspace_id = client.post(
            f"/api/chat/conversations/{conversation.id}/workspace", json={}
        ).json()["id"]

        added = client.patch(
            f"/api/chat/workspaces/{workspace_id}/members",
            json={
                "add": [
                    {
                        "id": "entity:rosario",
                        "target_type": "entity",
                        "target_id": "rosario",
                        "role": "surfaced_entity",
                    },
                    {
                        "id": "claim:petition",
                        "target_type": "claim",
                        "target_id": "petition",
                        "role": "surfaced_claim",
                    },
                    {
                        "id": "note:question",
                        "target_type": "note",
                        "target_id": "question",
                        "notes": "Check the date against the ledger.",
                    },
                ]
            },
        )
        assert added.status_code == 200
        assert {item["id"] for item in added.json()["members"]} == {
            "entity:rosario",
            "claim:petition",
            "note:question",
        }

        removed = client.patch(
            f"/api/chat/workspaces/{workspace_id}/members",
            json={"remove_ids": ["claim:petition"]},
        )
        assert removed.status_code == 200
        assert {item["id"] for item in removed.json()["members"]} == {
            "entity:rosario",
            "note:question",
        }

    def test_empty_conversation_cannot_be_saved(self, client, db):
        conversation = _make_conv("workspace-empty", "Empty")
        db.save(conversation)

        response = client.post(
            f"/api/chat/conversations/{conversation.id}/workspace", json={}
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "Cannot save an empty conversation"


# ---------------------------------------------------------------------------
# POST /api/chat/conversations/reorder
# ---------------------------------------------------------------------------


class TestReorderConversations:
    def test_reorder_updates_sort_order(self, client, db):
        c1 = _make_conv("r-1", "Conv 1")
        c2 = _make_conv("r-2", "Conv 2")
        db.save(c1)
        db.save(c2)

        r = client.post("/api/chat/conversations/reorder", json=["r-2", "r-1"])
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2

    def test_reorder_missing_conv_returns_404(self, client):
        r = client.post("/api/chat/conversations/reorder", json=["no-such-conv"])
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# _get_langchain_llm — model factory fix (#2490)
# ---------------------------------------------------------------------------


class TestGetLangchainLlm:
    """_get_langchain_llm must route through llm.get_langchain_model (not ChatLiteLLM)."""

    def test_no_chatllm_import_error(self, monkeypatch):
        """The function must not attempt to import the removed ChatLiteLLM."""
        from unittest.mock import MagicMock

        from unittest.mock import AsyncMock
        fake_model = MagicMock()
        fake_model.invoke.return_value = MagicMock(content="ok")
        fake_model.ainvoke = AsyncMock(return_value=MagicMock(content="ok"))

        captured_config = {}

        def fake_get_langchain_model(config):
            captured_config["provider"] = config.provider
            captured_config["model"] = config.model
            captured_config["temperature"] = config.temperature
            captured_config["max_tokens"] = config.max_tokens
            return fake_model

        fake_db = MagicMock()
        fake_db.query.return_value = []  # no configured providers → fallback defaults

        monkeypatch.setattr(
            "fichero_server.api.routes.chat.get_langchain_model",
            fake_get_langchain_model,
        )

        from fichero_server.api.routes.chat import _get_langchain_llm

        result = _get_langchain_llm(fake_db, provider="openai", model="gpt-4o-mini")

        assert result is fake_model
        assert captured_config["provider"] == "openai"
        assert captured_config["model"] == "gpt-4o-mini"
        assert captured_config["temperature"] == 0.7
        assert captured_config["max_tokens"] == 2048

    def test_chat_endpoint_uses_central_factory(self, client, monkeypatch):
        """POST /api/chat succeeds when get_langchain_model returns a stub."""
        from unittest.mock import MagicMock

        from unittest.mock import AsyncMock
        fake_model = MagicMock()
        # The default agent loop (#2067) binds tools and inspects tool_calls on
        # the response — make bind_tools return the same stub and give the
        # response an empty tool_calls list so the loop terminates.
        stub_response = MagicMock(content="Hello from stub", tool_calls=[])
        fake_model.invoke.return_value = stub_response
        fake_model.ainvoke = AsyncMock(return_value=stub_response)
        fake_model.bind_tools.return_value = fake_model

        monkeypatch.setattr(
            "fichero_server.api.routes.chat.get_langchain_model",
            lambda _config: fake_model,
        )

        r = client.post(
            "/api/chat",
            json={"message": "test", "provider": "openai", "model": "gpt-4o-mini"},
        )
        assert r.status_code == 200
        assert r.json()["message"] == "Hello from stub"
