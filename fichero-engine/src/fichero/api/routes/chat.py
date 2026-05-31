"""
Chat Routes

RAG-style chat using LangChain for semantic search and LLM generation.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero.db import Database
from fichero.api.main import get_library_database
from fichero.app_db import get_app_db, AppDatabase
from fichero.models import (
    Conversation,
    DocType,
    Document,
    Model as ModelModel,
    Provider as ProviderModel,
)
from fichero.keychain import has_api_key
from fichero.providers import get_provider_info
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

    message: str
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


# Note: Providers and models now come from the database (configured via Providers UI)


def _get_langchain_llm(db: Database, provider: str = None, model: str = None):
    """Get LangChain LLM instance for the specified provider/model.

    Uses the unified llm.py interface which supports all providers via LiteLLM.
    """
    from fichero.llm import get_api_key

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

    # Use LiteLLM via langchain
    from langchain_community.chat_models import ChatLiteLLM

    # Build model name in LiteLLM format
    if provider in ("ollama", "lmstudio"):
        model_name = f"ollama/{model}"
    elif provider == "huggingface":
        model_name = f"huggingface/{model}"
    else:
        model_name = f"{provider}/{model}"

    # Get API key from keychain
    api_key = get_api_key(provider)

    return ChatLiteLLM(
        model=model_name,
        api_key=api_key,
        temperature=0.7,
        max_tokens=2048,
        api_base=api_base,
    )


def _build_rag_prompt(query: str, context_docs: list[dict]) -> str:
    """Build a RAG prompt with retrieved context."""
    context_parts = []
    for i, doc in enumerate(context_docs, 1):
        name = doc.get("name", "Unknown")
        content = doc.get("content", "")[:1000]  # Limit content length
        context_parts.append(f"[Document {i}: {name}]\n{content}")

    context = "\n\n".join(context_parts)

    prompt = f"""You are a helpful assistant that answers questions about documents in a personal archive.
Use the following document excerpts to answer the user's question. If the documents don't contain relevant information, say so.
Always cite which document(s) you're drawing information from.

DOCUMENTS:
{context}

USER QUESTION: {query}

Provide a helpful, accurate answer based on the documents above. Be concise but thorough."""

    return prompt


@router.post("")
async def chat(
    request: ChatRequest,
    db: Database = Depends(get_library_database),
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

    # Add user message
    conv.messages.append({"role": "user", "content": request.message})
    conv.updated_at = datetime.now()

    # Search for relevant docs + KG neighborhood context
    sources = []
    context_docs = []
    kg_claims_used = 0
    kg_entities_used = 0

    try:
        retrieval = GraphAwareRetriever(db, file_reader=_read_file_content).retrieve(
            query=request.message,
            max_sources=request.max_sources,
            include_sources=request.include_sources,
            document_ids=request.document_ids,
            graph_hops=request.graph_hops,
            max_kg_claims=request.max_kg_claims,
        )
        context_docs = retrieval.context_docs
        sources = [DocumentSource(**row) for row in retrieval.sources]
        kg_claims_used = retrieval.kg_claims_used
        kg_entities_used = retrieval.kg_entities_used
    except Exception as e:
        logger.warning(f"Search failed, proceeding without context: {e}")

    # Generate response with LangChain LLM
    # Pass through request values - _get_langchain_llm handles None by looking up configured providers
    try:
        llm = _get_langchain_llm(db, provider=request.provider, model=request.model)
        # Build model_used string for response
        provider = request.provider or "auto"
        model = request.model or "auto"
        model_used = f"{provider}/{model}"

        if context_docs:
            prompt = _build_rag_prompt(request.message, context_docs)
        else:
            # No context - just answer directly
            prompt = f"You are a helpful assistant. Answer the user's question concisely.\n\nQuestion: {request.message}"

        response = llm.invoke(prompt)
        response_text = response.content

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        response_text = f"I apologize, but I encountered an error while processing your request. Please try again. (Error: {str(e)[:100]})"
        model_used = "error"

    # Add assistant message
    conv.messages.append({"role": "assistant", "content": response_text})
    conv.updated_at = datetime.now()

    # Save conversation to database
    db.save(conv)

    return ChatResponse(
        message=response_text,
        sources=sources,
        conversation_id=conv.id,
        model_used=model_used,
        kg_claims_used=kg_claims_used,
        kg_entities_used=kg_entities_used,
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


@router.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    db: Database = Depends(get_library_database),
) -> ConversationHistory:
    """Update conversation title and/or folder_path."""
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

    return ConversationHistory(
        id=conv.id,
        title=conv.title,
        messages=[ChatMessage(**m) for m in conv.messages],
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        folder_path=conv.folder_path,
        sort_order=conv.sort_order,
    )


@router.post("/conversations/{conversation_id}/duplicate")
async def duplicate_conversation(
    conversation_id: str,
    db: Database = Depends(get_library_database),
) -> ConversationSummary:
    """Duplicate a conversation with a new ID."""
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
        folder_path=original.folder_path,
        sort_order=original.sort_order,
    )

    db.save(new_conv)

    return ConversationSummary(
        id=new_conv.id,
        title=new_conv.title,
        message_count=len(new_conv.messages),
        created_at=_safe_isoformat(getattr(new_conv, "created_at", None)),
        updated_at=_safe_isoformat(getattr(new_conv, "updated_at", None)),
        folder_path=new_conv.folder_path,
        sort_order=new_conv.sort_order,
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Database = Depends(get_library_database),
) -> ConversationDeletedResponse:
    """Delete a conversation."""
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    return ConversationDeletedResponse(status="deleted")


@router.post("/conversations/reorder")
async def reorder_conversations(
    conversation_ids: list[str],
    folder_path: str = "/",
    db: Database = Depends(get_library_database),
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
    db: Database = Depends(get_library_database),
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
