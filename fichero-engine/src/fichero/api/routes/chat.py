"""
Chat Routes

RAG-style chat using LangChain for semantic search and LLM generation.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.api.auth import action_context
from fichero.api.change_stream import emit_change
from fichero.api.routes.claims import _descendant_doc_ids
from fichero.db import Database
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.app_db import get_app_db, AppDatabase
from fichero.models import (
    Conversation,
    DocType,
    Document,
    Model as ModelModel,
    Provider as ProviderModel,
)
from fichero.api.routes.documents import WorkspaceCuratedItem, WorkspacePatchRequest
from fichero.keychain import has_api_key
from fichero.llm import LLMConfig, get_langchain_model
from fichero.node_aliases import DanglingAliasError, is_alias, resolve_alias
from fichero.providers import get_provider_info
from fichero.prompts import compose_system_prompt
from fichero.retrieval.graph_rag import GraphAwareRetriever

logger = logging.getLogger(__name__)


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else now."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else datetime.now().isoformat()
    )


def _read_file_content(path: str | None, max_chars: int = 5000) -> str | None:
    """Read text content from file path.

    Falls back to direct file read when page_content is not available.
    Supports text files like .md, .txt, etc.
    """
    if not path:
        return None

    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None

        # Only read text-like files
        text_extensions = {
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".html",
            ".csv",
        }
        if p.suffix.lower() not in text_extensions:
            return None

        content = p.read_text(encoding="utf-8", errors="ignore")
        return content[:max_chars] if len(content) > max_chars else content
    except Exception as e:
        logger.debug(f"Could not read file {path}: {e}")
        return None


router = APIRouter()


# Request/Response models


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str  # "user" or "assistant"
    content: str


class DocumentSource(BaseModel):
    """Source document reference in a response."""

    document_id: str
    document_name: str
    excerpt: str
    relevance_score: float


class ChatRequest(BaseModel):
    """Request model for chat."""

    message: str = Field(..., min_length=1, max_length=32000)
    conversation_id: Optional[str] = None
    document_ids: Optional[list[str]] = None  # Scope to specific documents
    include_sources: bool = True
    max_sources: int = Field(default=5, ge=1, le=50)
    graph_hops: int = Field(default=1, ge=0, le=3)
    max_kg_claims: int = Field(default=12, ge=0, le=100)
    provider: Optional[str] = None  # e.g., "openai", "anthropic", "ollama"
    model: Optional[str] = None  # e.g., "gpt-4o-mini", "claude-3-haiku"

    model_config = ConfigDict(extra="allow")


class ChatResponse(BaseModel):
    """Response model for chat."""

    message: str
    sources: list[DocumentSource]
    conversation_id: str
    model_used: str = (
        ""  # Which model actually handled the request (empty if not known)
    )
    kg_claims_used: int = 0
    kg_entities_used: int = 0
    document_count: int = 0
    context_count: int = 0


class ProviderInfo(BaseModel):
    """Information about an LLM provider."""

    id: str
    name: str
    models: list[str]
    available: bool  # Whether API key is configured
    supports_vision: bool = False  # Whether provider supports vision/image input


class ChatProviderListResponse(BaseModel):
    """Envelope for a list of chat providers."""

    items: list[ProviderInfo]
    count: int


class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str
    folder_path: str
    sort_order: int


class ChatConversationListResponse(BaseModel):
    """Envelope for a list of chat conversations.

    Elements are plain dicts (the endpoint shapes the payload inline). Typed as
    ``list[dict]`` (not ``list[Any]``) so the generated Swift client exposes
    each item as an object container the conversation decoder can read.
    """

    items: list[dict[str, Any]]
    count: int


class ConversationDeletedResponse(BaseModel):
    status: str


class ConversationReorderResponse(BaseModel):
    status: str
    count: int
    folder_path: str


class ConversationHistory(BaseModel):
    """Conversation with message history."""

    id: str
    title: str
    messages: list[ChatMessage]
    created_at: str
    updated_at: str
    folder_path: str = "/"
    sort_order: int = 0


class AgentWorkspaceSaveRequest(BaseModel):
    """Optional title for an explicit, on-demand conversation workspace save."""

    title: str | None = Field(default=None, min_length=1)


class AgentWorkspaceMembershipPatch(BaseModel):
    """Add or remove the curated source, entity, claim, and note references."""

    add: list[WorkspaceCuratedItem] = Field(default_factory=list)
    remove_ids: list[str] = Field(default_factory=list)


class AgentWorkspace(BaseModel):
    """A persisted agent session represented by a normal workspace node."""

    id: str
    title: str
    provider: str | None = None
    model: str | None = None
    message_history_ref: str
    messages: list[ChatMessage]
    members: list[WorkspaceCuratedItem]
    scoped_document_ids: list[str]
    created_at: str
    updated_at: str


class AgentWorkspaceListResponse(BaseModel):
    items: list[AgentWorkspace]
    count: int


class AgentWorkspaceDeletedResponse(BaseModel):
    status: str
    id: str


_AGENT_WORKSPACE_KIND = "agent"


def _workspace_metadata(document: Document) -> dict[str, Any]:
    return document.metadata if isinstance(document.metadata, dict) else {}


def _is_agent_workspace(document: Document) -> bool:
    return (
        document.doc_type == DocType.folder
        and document.node_kind == "workspace"
        and document.deleted_at is None
        and _workspace_metadata(document).get("workspace_kind") == _AGENT_WORKSPACE_KIND
    )


def _agent_workspace_or_404(db: Database, workspace_id: str) -> Document:
    workspace = db.get(Document, workspace_id)
    if not workspace or not _is_agent_workspace(workspace):
        raise HTTPException(status_code=404, detail="Agent workspace not found")
    return workspace


def _agent_workspace_response(db: Database, workspace: Document) -> AgentWorkspace:
    metadata = _workspace_metadata(workspace)
    conversation_id = str(metadata.get("message_history_ref") or "")
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=409, detail="Workspace conversation is missing")
    members = [
        WorkspaceCuratedItem.model_validate(item)
        for item in workspace.curated_items
        if isinstance(item, dict)
    ]
    return AgentWorkspace(
        id=workspace.id,
        title=workspace.name,
        provider=metadata.get("provider"),
        model=metadata.get("model"),
        message_history_ref=conversation_id,
        messages=[ChatMessage.model_validate(message) for message in conversation.messages],
        members=members,
        scoped_document_ids=list(metadata.get("scoped_document_ids") or []),
        created_at=_safe_isoformat(workspace.created_at),
        updated_at=_safe_isoformat(workspace.updated_at),
    )


def _conversation_scoped_members(conversation: Conversation) -> list[WorkspaceCuratedItem]:
    document_ids = list(conversation.document_ids)
    if conversation.scope_document_id and conversation.scope_document_id not in document_ids:
        document_ids.append(conversation.scope_document_id)
    return [
        WorkspaceCuratedItem(
            id=f"source:{document_id}",
            target_type="document",
            target_id=document_id,
            role="scoped_source",
        )
        for document_id in document_ids
    ]


# Note: Providers and models now come from the database (configured via Providers UI)


def _get_langchain_llm(db: Database, provider: str = None, model: str = None):
    """Get LangChain LLM instance for the specified provider/model.

    Uses the unified llm.py interface which supports all providers via LiteLLM.
    """
    # Get first configured provider/model if not specified
    if not provider or not model:
        configured_providers = db.query(ProviderModel, enabled=True)
        if configured_providers:
            first_provider = configured_providers[0]
            provider = provider or first_provider.provider_type.value
            # Get first model for this provider
            models = db.query(ModelModel, provider_id=first_provider.id, enabled=True)
            if models:
                model = model or models[0].model_id
            else:
                # Use provider default
                info = get_provider_info(provider)
                model = model or (info.default_model if info else "gpt-4o-mini")
        else:
            # Fallback defaults
            provider = provider or "openai"
            model = model or "gpt-4o-mini"

    # Get provider info for API base
    provider_db = db.query(ProviderModel, provider_type=provider)
    api_base = provider_db[0].api_base if provider_db else None

    return get_langchain_model(
        LLMConfig(
            provider=provider,
            model=model,
            temperature=0.7,
            max_tokens=2048,
            api_base=api_base,
        )
    )


def _build_rag_user_prompt(query: str, context_docs: list[dict]) -> str:
    """Build the user message for a RAG chat turn."""
    context_parts = []
    for i, doc in enumerate(context_docs, 1):
        name = doc.get("name", "Unknown")
        content = doc.get("content", "")[:1000]  # Limit content length
        context_parts.append(f"[Document {i}: {name}]\n{content}")

    context = "\n\n".join(context_parts)

    return f"""DOCUMENTS:
{context}

USER QUESTION: {query}
"""


def _build_chat_system_prompt(has_context: bool) -> str:
    extra = (
        "Answer questions about documents in a personal archive. Use the "
        "provided document excerpts when they exist. If the documents do not "
        "contain enough information, say so plainly. Cite the document labels "
        "you rely on."
        if has_context
        else
        "Answer the user's question concisely. If no supporting documents are "
        "available, say you are answering from the user's prompt alone."
    )
    return compose_system_prompt(role="chat", extra=extra)


def _requested_scope_document_id(request: ChatRequest) -> str | None:
    """Compatibility bridge for node-backed scope refs on chat requests."""
    value = getattr(request, "scope_document_id", None)
    return value if isinstance(value, str) and value else None


def _resolve_scope_node(db: Database, scope_document_id: str) -> Document:
    """Resolve a chat scope node, following aliases and raising on misses."""
    scope = db.get(Document, scope_document_id)
    if scope is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chat scope node not found: {scope_document_id}",
        )
    if not is_alias(scope):
        return scope
    try:
        return resolve_alias(db, scope)
    except DanglingAliasError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _effective_scope(
    db: Database,
    request: ChatRequest,
    conv: Conversation,
) -> tuple[list[str] | None, str | None]:
    """Resolve retrieval doc ids plus the stored scope node reference."""
    requested_scope = _requested_scope_document_id(request)
    if requested_scope:
        resolved = _resolve_scope_node(db, requested_scope)
        return sorted(_descendant_doc_ids(db, resolved.id)), requested_scope
    if request.document_ids is not None:
        scope_id = request.document_ids[0] if len(request.document_ids) == 1 else None
        return request.document_ids, scope_id
    if conv.scope_document_id:
        resolved = _resolve_scope_node(db, conv.scope_document_id)
        return sorted(_descendant_doc_ids(db, resolved.id)), conv.scope_document_id
    if conv.document_ids:
        return conv.document_ids, None
    return None, None


# Maximum number of prior conversation turns to include in the LLM prompt (#3238).
# Each turn is one human + one assistant message. Conservative default: keep the
# last 10 turns (20 messages). Older turns are dropped to stay within context.
MAX_HISTORY_TURNS = 10


def _build_history_messages(
    messages: list[dict],
    max_turns: int = MAX_HISTORY_TURNS,
) -> list:
    """Convert stored conversation messages into LangChain message objects.

    Takes the most recent ``max_turns`` turns (one turn = one human + one
    assistant pair) from the stored history and returns them as alternating
    HumanMessage/AIMessage objects. Older turns are dropped to stay within
    the context budget — the system prompt and current user query are always
    included regardless.

    The stored ``conv.messages`` list contains dicts with ``role`` and ``content``.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    if not messages:
        return []

    # Take only human+assistant pairs (skip system/tool messages).
    # Each "turn" is one human followed by one assistant.
    pairs: list[tuple[dict, dict]] = []
    i = 0
    while i < len(messages) - 1:
        if messages[i].get("role") == "user" and messages[i + 1].get("role") == "assistant":
            pairs.append((messages[i], messages[i + 1]))
            i += 2
        else:
            i += 1

    # Keep only the most recent max_turns pairs.
    recent_pairs = pairs[-max_turns:]

    result: list = []
    for human_msg, assistant_msg in recent_pairs:
        result.append(HumanMessage(content=human_msg.get("content", "")))
        result.append(AIMessage(content=assistant_msg.get("content", "")))

    return result


@router.post("")
async def chat(
    request: ChatRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ChatResponse:
    """
    Send a message and get a response with RAG.

    1. Searches for relevant documents
    2. Builds context from top results
    3. Calls LLM with context + query
    4. Returns response with source citations
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Get or create conversation
    created = not request.conversation_id
    if request.conversation_id:
        conv = db.get(Conversation, request.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        # Create new conversation
        conv = Conversation(
            title=request.message[:50] + "..."
            if len(request.message) > 50
            else request.message,
            messages=[],
            provider=request.provider,
            model=request.model,
            document_ids=request.document_ids or [],
            folder_path="/",
            sort_order=0,
        )

    effective_document_ids, scope_document_id = _effective_scope(db, request, conv)
    conv.scope_document_id = scope_document_id
    conv.document_ids = (
        [scope_document_id]
        if scope_document_id is not None
        else list(effective_document_ids or [])
    )

    # Add user message
    conv.messages.append({"role": "user", "content": request.message})
    conv.updated_at = datetime.now()

    # Search for relevant docs + KG neighborhood context
    sources = []
    context_docs = []
    document_count = 0
    context_count = 0
    kg_claims_used = 0
    kg_entities_used = 0

    try:
        retrieval = await asyncio.to_thread(
            GraphAwareRetriever(db, file_reader=_read_file_content).retrieve,
            query=request.message,
            max_sources=request.max_sources,
            include_sources=request.include_sources,
            document_ids=effective_document_ids,
            graph_hops=request.graph_hops,
            max_kg_claims=request.max_kg_claims,
        )
        context_docs = retrieval.context_docs
        sources = [DocumentSource(**row) for row in retrieval.sources]
        kg_claims_used = retrieval.kg_claims_used
        kg_entities_used = retrieval.kg_entities_used
        context_count = len(context_docs)
        document_count = sum(
            1 for item in context_docs if item.get("kind") == "document"
        )
        logger.info(
            "chat_retrieval query_len=%d max_sources=%d graph_hops=%d "
            "max_kg_claims=%d document_count=%d context_count=%d "
            "kg_claims_used=%d kg_entities_used=%d",
            len(request.message or ""),
            request.max_sources,
            request.graph_hops,
            request.max_kg_claims,
            document_count,
            context_count,
            kg_claims_used,
            kg_entities_used,
        )
    except Exception as exc:
        logger.warning("Search failed; refusing ungrounded answer: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Search unavailable — cannot ground the answer",
        ) from exc

    # Generate response with LangChain LLM.
    # Pass through request values - _get_langchain_llm handles None by looking up configured providers.
    llm = _get_langchain_llm(db, provider=request.provider, model=request.model)
    provider = request.provider or "auto"
    model = request.model or "auto"
    model_used = f"{provider}/{model}"

    if context_docs:
        user_prompt = _build_rag_user_prompt(request.message, context_docs)
    else:
        user_prompt = f"Question: {request.message}"

    # Build conversation history from prior turns (amnesia fix, #3238).
    # Reserve ~50% of context for RAG docs; cap history at N turns.
    history_messages = _build_history_messages(
        conv.messages,
        max_turns=MAX_HISTORY_TURNS,
    )
    messages = [
        SystemMessage(content=_build_chat_system_prompt(bool(context_docs))),
        *history_messages,
        HumanMessage(content=user_prompt),
    ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Add assistant message
    conv.messages.append({"role": "assistant", "content": response_text})
    conv.updated_at = datetime.now()

    # Save conversation to database
    db.save(conv)
    emit_change(
        ctx.library_path or "",
        type="conversation.created" if created else "conversation.updated",
        actor=ctx.actor,
        metadata={"conversation_id": conv.id},
        origin_window=ctx.origin_window,
        origin_user=ctx.actor,
    )

    return ChatResponse(
        message=response_text,
        sources=sources,
        conversation_id=conv.id,
        model_used=model_used,
        kg_claims_used=kg_claims_used,
        kg_entities_used=kg_entities_used,
        document_count=document_count,
        context_count=context_count,
    )


@router.get("/conversations", response_model=ChatConversationListResponse)
async def list_conversations(
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
) -> ChatConversationListResponse:
    """List all conversations, optionally filtered by folder."""
    # Query conversations from database
    convs = db.query(Conversation, folder_path=folder_path)

    result = []
    for conv in convs:
        result.append(
            {
                "id": conv.id,
                "title": conv.title,
                "message_count": len(conv.messages),
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "folder_path": conv.folder_path,
                "sort_order": conv.sort_order,
            }
        )

    # Sort by sort_order, then by updated_at descending
    result.sort(key=lambda x: (x["sort_order"], x["updated_at"]), reverse=False)

    return ChatConversationListResponse(items=result, count=len(result))


@router.post(
    "/conversations/{conversation_id}/workspace", response_model=AgentWorkspace
)
async def save_conversation_as_workspace(
    conversation_id: str,
    request: AgentWorkspaceSaveRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AgentWorkspace:
    """Explicitly save a non-empty chat session as an undoable workspace node."""
    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not conversation.messages:
        raise HTTPException(status_code=422, detail="Cannot save an empty conversation")

    existing = next(
        (
            document
            for document in db.query(Document)
            if _is_agent_workspace(document)
            and _workspace_metadata(document).get("message_history_ref") == conversation.id
        ),
        None,
    )
    if existing:
        return _agent_workspace_response(db, existing)

    scoped_members = _conversation_scoped_members(conversation)
    result = registry.invoke(
        db,
        "document.create",
        {
            "name": request.title or conversation.title,
            "doc_type": DocType.folder.value,
            "node_kind": "workspace",
            "metadata": {
                "workspace_kind": _AGENT_WORKSPACE_KIND,
                "message_history_ref": conversation.id,
                "provider": conversation.provider,
                "model": conversation.model,
                "scoped_document_ids": [member.target_id for member in scoped_members],
            },
        },
        ctx,
    )
    workspace = Document.model_validate(result.result)
    registry.invoke(
        db,
        "document.patch_workspace",
        {
            "doc_id": workspace.id,
            "patch": WorkspacePatchRequest(add=scoped_members).model_dump(mode="json"),
        },
        ctx,
    )
    return _agent_workspace_response(db, _agent_workspace_or_404(db, workspace.id))


@router.get("/workspaces", response_model=AgentWorkspaceListResponse)
async def list_agent_workspaces(
    db: Database = Depends(get_library_database),
) -> AgentWorkspaceListResponse:
    """List explicit agent-session workspace nodes in the current library."""
    items = [
        _agent_workspace_response(db, workspace)
        for workspace in db.query(Document)
        if _is_agent_workspace(workspace)
    ]
    items.sort(key=lambda workspace: workspace.updated_at, reverse=True)
    return AgentWorkspaceListResponse(items=items, count=len(items))


@router.get("/workspaces/{workspace_id}", response_model=AgentWorkspace)
async def get_agent_workspace(
    workspace_id: str,
    db: Database = Depends(get_library_database),
) -> AgentWorkspace:
    """Reload a saved session, including its conversation history and members."""
    return _agent_workspace_response(db, _agent_workspace_or_404(db, workspace_id))


@router.patch("/workspaces/{workspace_id}/members", response_model=AgentWorkspace)
async def patch_agent_workspace_members(
    workspace_id: str,
    request: AgentWorkspaceMembershipPatch,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AgentWorkspace:
    """Add or remove source, entity, claim, or note references from a workspace."""
    _agent_workspace_or_404(db, workspace_id)
    registry.invoke(
        db,
        "document.patch_workspace",
        {
            "doc_id": workspace_id,
            "patch": WorkspacePatchRequest(
                add=request.add, remove_ids=request.remove_ids
            ).model_dump(mode="json"),
        },
        ctx,
    )
    return _agent_workspace_response(db, _agent_workspace_or_404(db, workspace_id))


@router.delete("/workspaces/{workspace_id}", response_model=AgentWorkspaceDeletedResponse)
async def delete_agent_workspace(
    workspace_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> AgentWorkspaceDeletedResponse:
    """Soft-delete a workspace node through the existing undoable document action."""
    _agent_workspace_or_404(db, workspace_id)
    registry.invoke(db, "document.delete", {"doc_id": workspace_id}, ctx)
    return AgentWorkspaceDeletedResponse(status="deleted", id=workspace_id)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: Database = Depends(get_library_database),
) -> ConversationHistory:
    """Get a specific conversation with full history."""
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationHistory(
        id=conv.id,
        title=conv.title,
        messages=[ChatMessage(**m) for m in conv.messages],
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        folder_path=conv.folder_path,
        sort_order=conv.sort_order,
    )


class ConversationUpdate(BaseModel):
    """Request to update conversation properties."""

    title: Optional[str] = None
    folder_path: Optional[str] = None

    model_config = ConfigDict(extra="allow")


def update_conversation_impl(
    db: Database, conversation_id: str, request: ConversationUpdate
) -> Conversation:
    """Apply title/folder_path edits to a conversation and persist it.

    Extracted from the ``PUT /conversations/{id}`` route so BOTH the route and
    the ``conversation.update`` action (EPIC #1848) drive the *same* code
    (iterate-not-replace). Raises ``HTTPException(404)`` on an unknown id exactly
    as the route did. Returns the mutated, persisted ``Conversation``.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Update fields
    if request.title is not None:
        conv.title = request.title
    if request.folder_path is not None:
        conv.folder_path = request.folder_path

    conv.updated_at = datetime.now()
    db.save(conv)
    return conv


@router.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    db: Database = Depends(get_library_database_for_write),
) -> ConversationHistory:
    """Update conversation title and/or folder_path."""
    conv = update_conversation_impl(db, conversation_id, request)

    return ConversationHistory(
        id=conv.id,
        title=conv.title,
        messages=[ChatMessage(**m) for m in conv.messages],
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        folder_path=conv.folder_path,
        sort_order=conv.sort_order,
    )


def duplicate_conversation_impl(db: Database, conversation_id: str) -> Conversation:
    """Create and persist a copy of a conversation under a new id.

    Extracted from the ``POST /conversations/{id}/duplicate`` route so BOTH the
    route and the ``conversation.duplicate`` action drive the *same* copy logic
    (iterate-not-replace). Raises ``HTTPException(404)`` on an unknown id.
    Returns the new ``Conversation``.
    """
    original = db.get(Conversation, conversation_id)
    if not original:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Create new conversation with copied properties
    new_conv = Conversation(
        title=f"{original.title} (Copy)",
        messages=original.messages[:],  # Copy the messages
        provider=original.provider,
        model=original.model,
        document_ids=original.document_ids[:],
        scope_document_id=original.scope_document_id,
        folder_path=original.folder_path,
        sort_order=original.sort_order,
    )

    db.save(new_conv)
    return new_conv


@router.post("/conversations/{conversation_id}/duplicate")
async def duplicate_conversation(
    conversation_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> ConversationSummary:
    """Duplicate a conversation with a new ID."""
    new_conv = duplicate_conversation_impl(db, conversation_id)

    return ConversationSummary(
        id=new_conv.id,
        title=new_conv.title,
        message_count=len(new_conv.messages),
        created_at=_safe_isoformat(getattr(new_conv, "created_at", None)),
        updated_at=_safe_isoformat(getattr(new_conv, "updated_at", None)),
        folder_path=new_conv.folder_path,
        sort_order=new_conv.sort_order,
    )


def delete_conversation_impl(db: Database, conversation_id: str) -> Conversation:
    """Delete a conversation, returning the row that was removed.

    Extracted from the ``DELETE /conversations/{id}`` route so BOTH the route
    and the ``conversation.delete`` action drive the *same* code
    (iterate-not-replace). Returning the deleted ``Conversation`` lets the action
    snapshot it as the undo payload. Raises ``HTTPException(404)`` on unknown id.
    """
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Database = Depends(get_library_database_for_write),
) -> ConversationDeletedResponse:
    """Delete a conversation."""
    delete_conversation_impl(db, conversation_id)
    return ConversationDeletedResponse(status="deleted")


@router.post("/conversations/reorder")
async def reorder_conversations(
    conversation_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database_for_write),
) -> ConversationReorderResponse:
    """Reorder conversations within a folder."""
    for index, conversation_id in enumerate(conversation_ids):
        conv = db.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(
                status_code=404, detail=f"Conversation not found: {conversation_id}"
            )

        conv.sort_order = index
        conv.updated_at = datetime.now()
        db.save(conv)

    return ConversationReorderResponse(
        status="reordered",
        count=len(conversation_ids),
        folder_path=folder_path,
    )


def get_app_database() -> AppDatabase:
    """FastAPI dependency to get the app-wide database."""
    return get_app_db()


@router.get("/providers", response_model=ChatProviderListResponse)
async def list_providers(
    app_db: AppDatabase = Depends(get_app_database),
) -> ChatProviderListResponse:
    """List available LLM providers and their models from user configuration.

    Providers are stored app-wide (not per-library), so we query the app database.
    """
    result = []

    # Get configured providers from app-wide database
    configured_providers = app_db.list_providers()
    # Filter to enabled only
    configured_providers = [p for p in configured_providers if p.enabled]

    for provider in configured_providers:
        provider_type = provider.provider_type.value

        # Get models for this provider from app database
        models = app_db.list_models(provider.id)
        # Filter to enabled only
        models = [m for m in models if m.enabled]
        model_ids = [m.model_id for m in models]

        # If no models configured, use default from catalog
        if not model_ids:
            catalog_info = get_provider_info(provider_type)
            if catalog_info and catalog_info.default_model:
                model_ids = [catalog_info.default_model]

        # Check availability - local providers are always available
        # Cloud providers need API key
        catalog_info = get_provider_info(provider_type)
        is_local = catalog_info.is_local if catalog_info else False

        if is_local:
            available = True
        else:
            available = has_api_key(provider_type)

        # Get vision support from catalog
        supports_vision = catalog_info.supports_vision if catalog_info else False

        result.append(
            ProviderInfo(
                id=provider_type,
                name=provider.name,
                models=model_ids,
                available=available,
                supports_vision=supports_vision,
            )
        )

    return ChatProviderListResponse(items=result, count=len(result))


# Text extraction endpoint
class ExtractTextRequest(BaseModel):
    """Request to extract text from documents."""

    document_ids: Optional[list[str]] = None  # None means all documents
    force: bool = False  # Re-extract even if text already exists

    model_config = ConfigDict(extra="allow")


class ExtractTextResponse(BaseModel):
    """Response from text extraction."""

    extracted: int
    skipped: int
    failed: int
    errors: list[str]


@router.post("/extract-text")
async def extract_text(
    request: ExtractTextRequest,
    db: Database = Depends(get_library_database_for_write),
) -> ExtractTextResponse:
    """
    Extract text content from documents.

    This populates the page_content field for search and chat.
    Can be used to re-extract text for documents imported before text extraction was working.
    """
    from fichero.ingest import _extract_text_content

    extracted = 0
    skipped = 0
    failed = 0
    errors = []

    # Get documents to process
    if request.document_ids:
        docs = [db.get(Document, doc_id) for doc_id in request.document_ids]
        docs = [d for d in docs if d is not None]
    else:
        docs = list(db.all(Document))

    for doc in docs:
        # Skip if already has content and not forcing
        if doc.page_content and not request.force:
            skipped += 1
            continue

        # Skip folders
        if doc.doc_type == DocType.folder:
            skipped += 1
            continue

        if not doc.path:
            skipped += 1
            continue

        path = Path(doc.path)
        if not path.exists():
            skipped += 1
            continue

        try:
            _extract_text_content(doc, path)
            if doc.page_content:
                db.save(doc)
                extracted += 1
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            errors.append(f"{doc.name}: {str(e)[:100]}")

    return ExtractTextResponse(
        extracted=extracted,
        skipped=skipped,
        failed=failed,
        errors=errors[:10],  # Limit error list
    )


# ---------------------------------------------------------------------------
# Action layer registration (EPIC #1848 / sweep #2014) — conversation domain
# ---------------------------------------------------------------------------
#
# Every conversation mutation (update / duplicate / delete) becomes a
# registered, audited action that WRAPS the proven ``*_impl`` above — the typed
# routes stay green and untouched; the action is the additional uniform path
# that chat tools / App Intents / tests drive via POST /api/actions/invoke.
# ``before``/``after`` snapshots ARE the undo payload.
#
# Undo design (mirrors the workflow sibling): ``db.save`` is an upsert by id, so
# a single ``conversation.restore`` (full-snapshot upsert) inverts BOTH a delete
# (re-inserts the row, same id) and an edit (overwrites with the prior snapshot).
# ``restore`` records whether the row pre-existed, so its OWN inverse is
# ``conversation.delete`` (after a recreate) or ``conversation.restore`` (after
# an overwrite) — keeping every delete<->restore and edit<->restore redo chain
# sane. ``conversation.duplicate`` creates a brand-new row (no prior state to
# reverse to) and is left NOT undoable per the sweep scope.

def _snap_conversation(conv: Conversation) -> dict:
    """JSON-able snapshot of a Conversation row (the undo payload)."""
    return conv.model_dump(mode="json")


class ConversationIdParams(BaseModel):
    """Shared params for id-only conversation actions (duplicate / delete)."""

    conversation_id: str


class ConversationUpdateParams(BaseModel):
    """``conversation.update`` params — the target id plus the editable fields.

    Mirrors :class:`ConversationUpdate` (title / folder_path, ``extra="allow"``)
    with the path id folded in so the action is self-contained.
    """

    conversation_id: str
    title: Optional[str] = None
    folder_path: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class ConversationRestoreParams(BaseModel):
    """``conversation.restore`` — re-materialize / overwrite a conversation by
    snapshot (preserving its id)."""

    snapshot: dict


def _invert_to_restore_before(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo an edit/delete by restoring the captured pre-change snapshot."""
    if not before:
        return None
    return ("conversation.restore", {"snapshot": before})


def _invert_create(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Undo a created conversation by deleting the created row."""
    if not after:
        return None
    cid = after.get("id")
    if not cid:
        return None
    return ("conversation.delete", {"conversation_id": cid})


def _invert_restore(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    """Inverse of restore — depends on whether the row pre-existed.

    If ``before`` is None the restore RE-CREATED a missing row (it was undoing a
    delete) -> redo by deleting again. If ``before`` is a snapshot the restore
    OVERWROTE an existing row (undoing an edit) -> redo by restoring that prior
    snapshot, which re-applies the edit. Keeps delete<->restore and
    edit<->restore redo chains correct."""
    if not after:
        return None
    cid = after.get("id")
    if before is None:
        if not cid:
            return None
        return ("conversation.delete", {"conversation_id": cid})
    return ("conversation.restore", {"snapshot": before})


@action(
    "conversation.update",
    ConversationUpdateParams,
    domains=["conversation"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_update_conversation(
    db: Database, params: ConversationUpdateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    existing = db.get(Conversation, params.conversation_id)
    if existing is None:
        raise HTTPException(
            status_code=404, detail="Conversation not found"
        )
    before = _snap_conversation(existing)
    request = ConversationUpdate(
        title=params.title, folder_path=params.folder_path
    )
    conv = update_conversation_impl(db, params.conversation_id, request)
    after = _snap_conversation(conv)
    spec = ChangeSpec(
        domains=["conversation"],
        target_ids=[conv.id],
        before=before,
        after=after,
        emit_type="conversation.updated",
    )
    return after, spec


@action(
    "conversation.duplicate",
    ConversationIdParams,
    domains=["conversation"],
    undoable=True,
    invert=_invert_create,
)
def _action_duplicate_conversation(
    db: Database, params: ConversationIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    new_conv = duplicate_conversation_impl(db, params.conversation_id)
    after = _snap_conversation(new_conv)
    spec = ChangeSpec(
        domains=["conversation"],
        target_ids=[new_conv.id],
        before=None,
        after=after,
        emit_type="conversation.created",
    )
    return after, spec


@action(
    "conversation.delete",
    ConversationIdParams,
    domains=["conversation"],
    undoable=True,
    invert=_invert_to_restore_before,
)
def _action_delete_conversation(
    db: Database, params: ConversationIdParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    deleted = delete_conversation_impl(db, params.conversation_id)
    before = _snap_conversation(deleted)
    spec = ChangeSpec(
        domains=["conversation"],
        target_ids=[params.conversation_id],
        before=before,
        after=None,
        emit_type="conversation.deleted",
    )
    return before, spec


@action(
    "conversation.restore",
    ConversationRestoreParams,
    domains=["conversation"],
    undoable=True,
    invert=_invert_restore,
)
def _action_restore_conversation(
    db: Database, params: ConversationRestoreParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    """Upsert a conversation from its snapshot (preserving id). Records whether
    the row pre-existed so its inverse picks delete (recreate) vs restore
    (edit)."""
    cid = params.snapshot.get("id")
    existing = db.get(Conversation, cid) if cid else None
    before = _snap_conversation(existing) if existing else None
    conv = Conversation(**params.snapshot)
    db.save(conv)
    after = _snap_conversation(conv)
    spec = ChangeSpec(
        domains=["conversation"],
        target_ids=[conv.id],
        before=before,
        after=after,
        emit_type="conversation.updated" if before else "conversation.created",
    )
    return after, spec
