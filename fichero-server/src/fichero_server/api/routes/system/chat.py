"""
Chat Routes

RAG-style chat using LangChain for semantic search and LLM generation.
"""

import asyncio
import json
import logging
import os
from fichero_server.core.timeutil import utc_now
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.change_stream import emit_change
from fichero_server.api.routes.claim.claims import _descendant_doc_ids
from fichero_server.db import Database
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db.app import get_app_db, AppDatabase
from fichero_server.models import (
    Conversation,
    DocType,
    Document,
    Model as ModelModel,
    Provider as ProviderModel,
)
from fichero_server.api.routes.document.documents import (
    WorkspaceCuratedItem,
    WorkspacePatchRequest,
    patch_workspace_items_impl,
)
from fichero_server.models.knowledge import KnowledgeClaim
from fichero_server.security.keychain import has_api_key
# NOTE: fichero_server.llm is imported inside _build_model below, not here (#3950).
# It pulls langchain_core -> transformers, which the engine must not pay for
# just to register this router at startup.
from fichero_server.models.node_aliases import DanglingAliasError, is_alias, resolve_alias
from fichero_server.llm.providers import get_provider_info
from fichero_server.llm.prompts import compose_system_prompt
from fichero_server.retrieval.graph_rag import GraphAwareRetriever

logger = logging.getLogger(__name__)


def _safe_isoformat(value) -> str:
    """Return ISO string when value behaves like datetime, else now."""
    return (
        value.isoformat() if hasattr(value, "isoformat") else utc_now().isoformat()
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


# Passthrough wrappers, NOT deferred imports at the call sites (#3950).
#
# These names are part of this module's TEST SURFACE — tests patch
# `fichero_server.api.routes.system.chat.<name>`. Two things must both hold:
#   1. the name exists as a module attribute, or mock.patch raises
#      AttributeError ("module has no attribute ...");
#   2. the call site resolves it as a module GLOBAL, so the patch takes effect.
# A function-local import at the call site satisfies NEITHER: it removes the
# attribute AND binds a local that shadows any patch — letting a test pass
# while silently exercising the real implementation. A module-level __getattr__
# (PEP 562) fixes (1) but not (2), because LOAD_GLOBAL inside this module never
# consults it. The wrapper satisfies both and still keeps fichero_server.llm
# (langchain_core) off the engine startup path.


def get_langchain_model(*args, **kwargs):
    """Passthrough to fichero_server.llm.get_langchain_model; imports it on first call (#3950)."""
    from fichero_server.llm import get_langchain_model as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


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


class ToolCall(BaseModel):
    """One audited tool call the chat agent made during a turn (#1847 / #3).

    Field names mirror the Swift ``ToolCall`` product spine
    (``fichero/fichero/Models/ToolCall.swift``) in snake_case so the existing
    ``ToolCallCard`` UI lights up with zero Swift work. The agent loop is the
    DEFAULT chat path (#2067); the array is empty when the turn needed no tools,
    when the model cannot bind tools, or when ``FICHERO_CHAT_TOOLS=0`` forces
    single-shot RAG. This slice is READS-ONLY: a dispatched read
    carries ``is_mutation=False`` + an ``audit_id``; a refused mutating call is
    recorded with ``status='error'`` + ``is_mutation=True`` and never invoked.
    """

    id: str
    workspace_id: str | None = None
    message_id: str | None = None
    task_id: str | None = None
    action_name: str
    params: dict[str, Any] | None = None
    actor: str
    audit_id: str | None = None
    is_mutation: bool | None = None
    status: str = "ok"  # pending | running | ok | error (Swift ToolCall.Status)


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
    tool_calls: list[ToolCall] = Field(
        default_factory=list
    )  # audited calls from the default agent loop; [] when no tools ran (#2067)


class ProviderModelInfo(BaseModel):
    """Per-model capability for one configured model (#4187).

    ``supports_vision`` is NOT ``"vision" in capabilities``. Capability
    enforcement (``_model_has_capability`` in ``fichero_server.llm``) is TRI-STATE:
    a model with NO saved capabilities returns ``None``, meaning "unknown —
    fall back to the provider's capability", and only an explicit mismatch
    rejects the run. Collapsing that to a membership test would hide every
    model whose capabilities were never populated — which is most of them on
    an existing install — so the fallback is resolved HERE, server-side, and
    clients consume the resulting bool.
    """

    model_id: str
    capabilities: list[str] = []
    supports_vision: bool = False


class ProviderInfo(BaseModel):
    """Information about an LLM provider."""

    id: str
    name: str
    models: list[str]
    available: bool  # Whether API key is configured
    supports_vision: bool = False  # Whether provider supports vision/image input
    # Per-model capability, so a vision node's picker can exclude text-only
    # models (#4187). `models` stays the plain id list for existing clients.
    model_details: list[ProviderModelInfo] = []


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


class WorkspaceSourceActionParams(BaseModel):
    workspace_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)


class WorkspaceClaimActionParams(BaseModel):
    workspace_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)


class WorkspaceNoteActionParams(BaseModel):
    workspace_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


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

    # LLMConfig only — get_langchain_model resolves to the module-level
    # passthrough above, which tests patch. A local import of it here would
    # shadow that patch (#3950).
    from fichero_server.llm import LLMConfig  # noqa: PLC0415

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


# ---------------------------------------------------------------------------
# Chat-tools agent loop (#1847 / #3 / #2067) — DEFAULT-ON, READS-ONLY
# ---------------------------------------------------------------------------
#
# Wires the `fichero_server.actions.chat_tools` generator + dispatcher into the
# live chat handler. The loop is the DEFAULT chat path (#2067 — the Research
# surface chats with the library through audited tools); FICHERO_CHAT_TOOLS=0
# is the kill switch back to the single-shot RAG path. This slice only exposes
# and dispatches actions flagged `read_only=True`; a mutating tool call is
# refused (recorded, never invoked) pending a write-policy review (EPIC #1848).
# A model/provider that cannot bind tools degrades gracefully to single-shot
# inside `_run_chat_tools_loop` rather than failing the turn.

_CHAT_TOOLS_FALSY = {"0", "false", "no", "off"}

# Bound the agent loop so a misbehaving model cannot spin forever.
MAX_CHAT_TOOL_ITERATIONS = 4


def _chat_tools_enabled() -> bool:
    """Whether the read-only chat-tools agent loop is enabled (default ON).

    ``FICHERO_CHAT_TOOLS=0`` (or false/no/off) disables the loop and restores
    the single-shot RAG path unchanged.
    """
    return (
        os.environ.get("FICHERO_CHAT_TOOLS", "").strip().lower()
        not in _CHAT_TOOLS_FALSY
    )


async def _run_chat_tools_loop(
    llm: Any,
    messages: list,
    *,
    db: Database,
    ctx: ActionContext,
) -> tuple[str, list[ToolCall]]:
    """Run the bounded, read-only chat-tools agent loop.

    Binds the SAFE (``read_only=True``) subset of registry actions as tools,
    then loops: ask the model; if it emits tool calls, run each read-only one
    through the audited ``dispatch_tool_call`` choke point and refuse any
    mutating one; feed results back; repeat until the model returns a final
    text answer or the iteration cap is hit.

    Returns ``(final_text, tool_calls)`` — ``tool_calls`` records every call the
    model made (dispatched reads and refused mutations) for the ``ToolCallCard``
    UI. Any tool call that fails to resolve or dispatch is recorded as an error
    tool_call rather than aborting the whole chat turn.
    """
    from langchain_core.messages import ToolMessage  # noqa: PLC0415

    from fichero_server.actions.chat_tools import (  # noqa: PLC0415
        action_tools,
        dispatch_tool_call,
        is_read_only_action,
        resolve_action_name,
    )
    from fichero_server.actions.registry import ActionNotFoundError  # noqa: PLC0415

    tools = action_tools(read_only=True)
    try:
        bound = llm.bind_tools(tools) if tools else llm
    except (AttributeError, NotImplementedError, ValueError) as exc:
        # Now that the loop is the default (#2067), a model/provider without
        # tool-calling support must degrade to the single-shot RAG answer, not
        # fail the whole turn. The degradation is visible: tool_calls is [].
        logger.warning(
            "chat tools unavailable for this model (%s); falling back to "
            "single-shot RAG",
            exc,
        )
        response = await llm.ainvoke(list(messages))
        return getattr(response, "content", ""), []

    convo = list(messages)
    tool_calls: list[ToolCall] = []
    response = None
    actor = ctx.actor or "chat"

    for _ in range(MAX_CHAT_TOOL_ITERATIONS):
        response = await bound.ainvoke(convo)
        calls = getattr(response, "tool_calls", None) or []
        if not calls:
            break

        convo.append(response)
        for call in calls:
            raw_name = call.get("name") or ""
            args = call.get("args") or {}
            call_id = call.get("id") or uuid4().hex

            # Unknown tool — record an error, tell the model, keep going.
            try:
                canonical = resolve_action_name(raw_name)
            except ActionNotFoundError:
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        action_name=raw_name,
                        params=args,
                        actor=actor,
                        is_mutation=None,
                        status="error",
                    )
                )
                convo.append(
                    ToolMessage(
                        content=f"unknown tool: {raw_name}", tool_call_id=call_id
                    )
                )
                continue

            # READS-ONLY gate: refuse (do NOT invoke) any mutating action.
            if not is_read_only_action(canonical):
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        action_name=canonical,
                        params=args,
                        actor=actor,
                        is_mutation=True,
                        status="error",
                    )
                )
                convo.append(
                    ToolMessage(
                        content=(
                            f"denied: '{canonical}' mutates state; chat tools are "
                            "read-only in this build"
                        ),
                        tool_call_id=call_id,
                    )
                )
                continue

            # Safe read — dispatch through the audited choke point.
            try:
                result = dispatch_tool_call(
                    db,
                    canonical,
                    args,
                    actor=actor,
                    origin_window=ctx.origin_window,
                    run_id=ctx.run_id,
                    library_path=ctx.library_path,
                )
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        action_name=canonical,
                        params=args,
                        actor=actor,
                        audit_id=result.audit_id,
                        is_mutation=False,
                        status="ok",
                    )
                )
                convo.append(
                    ToolMessage(
                        content=json.dumps(result.result, default=str),
                        tool_call_id=call_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - never abort the whole turn
                logger.warning("chat tool dispatch failed: %s -> %s", canonical, exc)
                tool_calls.append(
                    ToolCall(
                        id=call_id,
                        action_name=canonical,
                        params=args,
                        actor=actor,
                        is_mutation=False,
                        status="error",
                    )
                )
                convo.append(
                    ToolMessage(
                        content=f"tool error: {exc}", tool_call_id=call_id
                    )
                )

    text = getattr(response, "content", "") if response is not None else ""
    return text, tool_calls


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
    conv.updated_at = utc_now()

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
    # Lazy import (#3976): langchain_core is only needed when a chat actually
    # runs, not at engine startup. Importing it at module scope pulled ~24
    # langchain_core modules onto the boot path — the single biggest slice of
    # the engine bind. Mirrors the existing _build_model/_build_history_messages
    # deferral (#3950).
    from langchain_core.messages import HumanMessage, SystemMessage
    messages = [
        SystemMessage(content=_build_chat_system_prompt(bool(context_docs))),
        *history_messages,
        HumanMessage(content=user_prompt),
    ]

    # Default single-shot RAG (byte-for-byte unchanged) unless the read-only
    # chat-tools agent loop is explicitly enabled via FICHERO_CHAT_TOOLS (#1847).
    tool_calls: list[ToolCall] = []
    if _chat_tools_enabled():
        response_text, tool_calls = await _run_chat_tools_loop(
            llm, messages, db=db, ctx=ctx
        )
    else:
        response = await llm.ainvoke(messages)
        response_text = response.content

    # Add assistant message
    conv.messages.append({"role": "assistant", "content": response_text})
    conv.updated_at = utc_now()

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
        tool_calls=tool_calls,
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


class ConversationCreateRequest(BaseModel):
    """Create an empty conversation without requiring an LLM turn (#4308).

    Before this endpoint a conversation only came into existence as a side
    effect of a successful ``POST /api/chat`` LLM round-trip — so "New Chat"
    silently created nothing when no provider was configured or the model
    errored, and the sidebar showed nothing. Creation is now a plain, audited
    persistence operation; the first real message continues the returned
    conversation id.
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    folder_path: str = "/"
    provider: Optional[str] = None
    model: Optional[str] = None


@router.post("/conversations", response_model=ConversationHistory)
async def create_conversation(
    request: ConversationCreateRequest,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ConversationHistory:
    """Create an empty conversation through the audited ``conversation.create``
    action (#4308) — no LLM required, appears in the sidebar immediately."""
    result = registry.invoke(
        db,
        "conversation.create",
        {
            "title": request.title or "New Chat",
            "folder_path": request.folder_path,
            "provider": request.provider,
            "model": request.model,
        },
        ctx,
    )
    conv = Conversation(**result.result)
    return ConversationHistory(
        id=conv.id,
        title=conv.title,
        messages=[],
        created_at=_safe_isoformat(conv.created_at),
        updated_at=_safe_isoformat(conv.updated_at),
        folder_path=conv.folder_path,
        sort_order=conv.sort_order,
    )


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

    conv.updated_at = utc_now()
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
        conv.updated_at = utc_now()
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

        capabilities_by_model = {
            m.model_id: [str(cap).strip().lower() for cap in (m.capabilities or [])]
            for m in models
        }
        model_details = []
        for model_id in model_ids:
            # A synthesized catalog default (no configured row) has no saved
            # capabilities, so it inherits the provider's vision support.
            capabilities = capabilities_by_model.get(model_id, [])
            model_details.append(
                ProviderModelInfo(
                    model_id=model_id,
                    capabilities=capabilities,
                    supports_vision=(
                        "vision" in capabilities if capabilities else supports_vision
                    ),
                )
            )

        result.append(
            ProviderInfo(
                id=provider_type,
                name=provider.name,
                models=model_ids,
                available=available,
                supports_vision=supports_vision,
                model_details=model_details,
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
    from fichero_server.importers.ingest import _extract_text_content

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


class ConversationCreateParams(BaseModel):
    """``conversation.create`` — start an empty conversation, no LLM turn (#4308)."""

    title: str = Field(default="New Chat", min_length=1, max_length=200)
    folder_path: str = "/"
    provider: Optional[str] = None
    model: Optional[str] = None


@action(
    "conversation.create",
    ConversationCreateParams,
    domains=["conversation"],
    undoable=True,
    invert=_invert_create,
)
def _action_create_conversation(
    db: Database, params: ConversationCreateParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    conv = Conversation(
        title=params.title,
        messages=[],
        provider=params.provider,
        model=params.model,
        document_ids=[],
        folder_path=params.folder_path,
        sort_order=0,
    )
    db.save(conv)
    after = _snap_conversation(conv)
    spec = ChangeSpec(
        domains=["conversation"],
        target_ids=[conv.id],
        before=None,
        after=after,
        emit_type="conversation.created",
    )
    return after, spec


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


def _invert_workspace_membership(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before:
        return None
    return ("document.restore", {"documents": [before]})


def _mutate_agent_workspace(
    db: Database, workspace_id: str, patch: WorkspacePatchRequest
) -> tuple[dict, ChangeSpec]:
    workspace = _agent_workspace_or_404(db, workspace_id)
    updated, before = patch_workspace_items_impl(db, workspace.id, patch)
    return (
        {"workspace_id": updated.id, "items": updated.curated_items},
        ChangeSpec(
            domains=["document"],
            target_ids=[updated.id],
            before=before,
            after=updated.model_dump(mode="json"),
            emit_type="document.updated",
            document_ids=[updated.id],
        ),
    )


@action(
    "workspace.add_source",
    WorkspaceSourceActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_workspace_membership,
)
def _action_workspace_add_source(
    db: Database, params: WorkspaceSourceActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    if db.get(Document, params.document_id) is None:
        raise HTTPException(status_code=404, detail="Source document not found")
    return _mutate_agent_workspace(
        db,
        params.workspace_id,
        WorkspacePatchRequest(
            add=[
                WorkspaceCuratedItem(
                    id=f"source:{params.document_id}",
                    target_type="document",
                    target_id=params.document_id,
                    role="agent_source",
                )
            ]
        ),
    )


@action(
    "workspace.remove_source",
    WorkspaceSourceActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_workspace_membership,
)
def _action_workspace_remove_source(
    db: Database, params: WorkspaceSourceActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    workspace = _agent_workspace_or_404(db, params.workspace_id)
    item_id = f"source:{params.document_id}"
    if not any(item.get("id") == item_id for item in workspace.curated_items):
        raise HTTPException(status_code=404, detail="Workspace source not found")
    return _mutate_agent_workspace(
        db, params.workspace_id, WorkspacePatchRequest(remove_ids=[item_id])
    )


@action(
    "workspace.surface_claim",
    WorkspaceClaimActionParams,
    domains=["document", "claim"],
    undoable=True,
    invert=_invert_workspace_membership,
)
def _action_workspace_surface_claim(
    db: Database, params: WorkspaceClaimActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    if db.get(KnowledgeClaim, params.claim_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge claim not found")
    result, spec = _mutate_agent_workspace(
        db,
        params.workspace_id,
        WorkspacePatchRequest(
            add=[
                WorkspaceCuratedItem(
                    id=f"claim:{params.claim_id}",
                    target_type="claim",
                    target_id=params.claim_id,
                    role="surfaced_claim",
                )
            ]
        ),
    )
    spec.claim_ids = [params.claim_id]
    return result, spec


@action(
    "workspace.add_note",
    WorkspaceNoteActionParams,
    domains=["document"],
    undoable=True,
    invert=_invert_workspace_membership,
)
def _action_workspace_add_note(
    db: Database, params: WorkspaceNoteActionParams, ctx: ActionContext
) -> tuple[dict, ChangeSpec]:
    item_id = f"note:{uuid4().hex}"
    result, spec = _mutate_agent_workspace(
        db,
        params.workspace_id,
        WorkspacePatchRequest(
            add=[
                WorkspaceCuratedItem(
                    id=item_id,
                    target_type="note",
                    target_id=item_id,
                    role="agent_note",
                    notes=params.text,
                )
            ]
        ),
    )
    result["item_id"] = item_id
    return result, spec
