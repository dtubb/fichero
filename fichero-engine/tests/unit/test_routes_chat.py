"""Tests for chat/conversation management routes.

Chat routes manage RAG conversations stored per-library. The LLM call path
is out of scope here — tests focus on conversation CRUD (list, get, update,
delete, reorder) and the providers list. Chat routes live at /api/chat/...
"""

from fichero.models import Conversation, Document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conv(conv_id: str = "conv-1", title: str = "My Chat") -> Conversation:
    return Conversation(id=conv_id, title=title, messages=[])


class _FakeLLM:
    def __init__(self):
        self.prompt = ""

    def invoke(self, prompt: str):
        self.prompt = prompt

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
            "fichero.api.routes.chat._get_langchain_llm",
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
        assert "[Document 1: Lovelace notes]" in fake_llm.prompt
        assert db.get(Conversation, data["conversation_id"]) is not None

    def test_chat_passes_graph_knobs_to_retriever(self, client, monkeypatch):
        captured: dict = {}

        class _FakeRetriever:
            def retrieve(self, **kwargs):
                captured.update(kwargs)
                return _FakeRetrievalPayload()

        fake_llm = _FakeLLM()
        monkeypatch.setattr(
            "fichero.api.routes.chat._get_langchain_llm",
            lambda *_args, **_kwargs: fake_llm,
        )
        monkeypatch.setattr(
            "fichero.api.routes.chat.GraphAwareRetriever",
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

    def test_chat_rejects_out_of_range_graph_hops(self, client):
        r = client.post(
            "/api/chat",
            json={
                "message": "Test invalid graph hops",
                "graph_hops": 99,
            },
        )
        assert r.status_code == 422


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
