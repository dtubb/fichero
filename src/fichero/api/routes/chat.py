"""
Chat Routes

RAG-style chat using LangChain for semantic search and LLM generation.
"""

import logging
import os
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fichero.db import db
from fichero.models import Document, Provider as ProviderModel, Model as ModelModel
from fichero.keychain import has_api_key
from fichero.providers import PROVIDERS as PROVIDER_CATALOG, get_provider_info

logger = logging.getLogger(__name__)


def _read_file_content(path: str | None, max_chars: int = 5000) -> str | None:
    """Read text content from file path.

    Falls back to direct file read when page_content is not available.
    Supports text files like .md, .txt, etc.
    """
    if not path:
        return None

    try:
        from pathlib import Path
        p = Path(path)
        if not p.exists() or not p.is_file():
            return None

        # Only read text-like files
        text_extensions = {'.md', '.txt', '.json', '.yaml', '.yml', '.xml', '.html', '.csv'}
        if p.suffix.lower() not in text_extensions:
            return None

        content = p.read_text(encoding='utf-8', errors='ignore')
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
    document_ids: Optional[List[str]] = None  # Scope to specific documents
    include_sources: bool = True
    max_sources: int = 5
    provider: Optional[str] = None  # e.g., "openai", "anthropic", "ollama"
    model: Optional[str] = None  # e.g., "gpt-4o-mini", "claude-3-haiku"


class ChatResponse(BaseModel):
    """Response model for chat."""
    message: str
    sources: List[DocumentSource]
    conversation_id: str
    model_used: Optional[str] = None  # Which model actually handled the request


class ProviderInfo(BaseModel):
    """Information about an LLM provider."""
    id: str
    name: str
    models: List[str]
    available: bool  # Whether API key is configured


class ConversationHistory(BaseModel):
    """Conversation with message history."""
    id: str
    title: str
    messages: List[ChatMessage]
    created_at: str
    updated_at: str


# In-memory conversation store (would be database in production)
_conversations: dict[str, dict] = {}

# Note: Providers and models now come from the database (configured via Providers UI)


def _get_langchain_llm(provider: str = None, model: str = None):
    """Get LangChain LLM instance for the specified provider/model.

    Uses the unified llm.py interface which supports all providers via LiteLLM.
    """
    from fichero.llm import LLMConfig, get_api_key

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


def _build_rag_prompt(query: str, context_docs: List[dict]) -> str:
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
async def chat(request: ChatRequest) -> ChatResponse:
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
    conv_id = request.conversation_id or datetime.now().strftime("%Y%m%d%H%M%S%f")
    if conv_id not in _conversations:
        _conversations[conv_id] = {
            "id": conv_id,
            "title": request.message[:50] + "..." if len(request.message) > 50 else request.message,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    conv = _conversations[conv_id]

    # Add user message
    conv["messages"].append({"role": "user", "content": request.message})
    conv["updated_at"] = datetime.now().isoformat()

    # Search for relevant documents
    sources = []
    context_docs = []

    try:
        # If specific documents are requested, use those
        if request.document_ids:
            for doc_id in request.document_ids[:request.max_sources]:
                doc = db.get(Document, doc_id)
                if doc and doc.page_content:
                    context_docs.append({
                        "id": doc.id,
                        "name": doc.name,
                        "content": doc.page_content,
                    })
                    if request.include_sources:
                        sources.append(DocumentSource(
                            document_id=doc.id,
                            document_name=doc.name,
                            excerpt=doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                            relevance_score=1.0,
                        ))
        else:
            # Enhanced search for relevant documents
            search_results, _, _ = db.search(
                query=request.message,
                limit=request.max_sources,
                min_score=0.0,
                search_type="hybrid",  # Use hybrid search for better results
            )

            for result in search_results:
                doc = db.get(Document, result.document_id)
                if doc:
                    # Use page_content if available, otherwise read from file
                    content = doc.page_content or _read_file_content(doc.path)
                    if content:
                        context_docs.append({
                            "id": doc.id,
                            "name": doc.name,
                            "content": content,
                        })
                        if request.include_sources:
                            sources.append(DocumentSource(
                                document_id=result.document_id,
                                document_name=doc.name,
                                excerpt=content[:200] + "..." if len(content) > 200 else content,
                                relevance_score=result.score,
                            ))
    except Exception as e:
        logger.warning(f"Search failed, proceeding without context: {e}")

    # Generate response with LangChain LLM
    # Pass through request values - _get_langchain_llm handles None by looking up configured providers
    try:
        llm = _get_langchain_llm(provider=request.provider, model=request.model)
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

    # Add assistant message
    conv["messages"].append({"role": "assistant", "content": response_text})

    return ChatResponse(
        message=response_text,
        sources=sources,
        conversation_id=conv_id,
        model_used=model_used,
    )


@router.get("/conversations")
async def list_conversations(
    folder_path: str = "/"
) -> List[dict]:
    """List all conversations, optionally filtered by folder."""
    # For now, return in-memory conversations
    # In the future, this could query from the database
    result = []
    for conv in _conversations.values():
        result.append({
            "id": conv["id"],
            "title": conv["title"],
            "message_count": len(conv["messages"]),
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            # For now, assume all conversations are in root folder
            "folder_path": "/",
            "sort_order": 0
        })
    return result


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> ConversationHistory:
    """Get a specific conversation with full history."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv = _conversations[conversation_id]
    return ConversationHistory(
        id=conv["id"],
        title=conv["title"],
        messages=[ChatMessage(**m) for m in conv["messages"]],
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
    )


@router.post("/conversations/{conversation_id}/duplicate")
async def duplicate_conversation(conversation_id: str) -> dict:
    """Duplicate a conversation with a new ID."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    original_conv = _conversations[conversation_id]

    # Create a new conversation with a new ID and modified title
    new_conv_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    new_title = f"{original_conv['title']} (Copy)"

    new_conv = {
        "id": new_conv_id,
        "title": new_title,
        "messages": original_conv["messages"][:],  # Copy the messages
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    _conversations[new_conv_id] = new_conv

    return {
        "id": new_conv_id,
        "title": new_title,
        "message_count": len(new_conv["messages"]),
        "created_at": new_conv["created_at"],
        "updated_at": new_conv["updated_at"],
        "folder_path": "/",
        "sort_order": 0
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if conversation_id not in _conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    del _conversations[conversation_id]
    return {"status": "deleted"}


@router.post("/conversations/reorder")
async def reorder_conversations(conversation_ids: list[str], folder_path: str = "/") -> dict:
    """Reorder conversations within a folder."""
    # For now, since conversations are in-memory, we'll just return a success status
    # In a real implementation with database persistence, we'd update the sort_order field
    return {"status": "reordered", "count": len(conversation_ids), "folder_path": folder_path}


@router.get("/providers")
async def list_providers() -> List[ProviderInfo]:
    """List available LLM providers and their models from user configuration."""
    result = []

    # Get configured providers from database
    configured_providers = db.query(ProviderModel, enabled=True)

    for provider in configured_providers:
        provider_type = provider.provider_type.value

        # Get models for this provider
        models = db.query(ModelModel, provider_id=provider.id, enabled=True)
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

        result.append(ProviderInfo(
            id=provider_type,
            name=provider.name,
            models=model_ids,
            available=available,
        ))

    return result


# Text extraction endpoint
class ExtractTextRequest(BaseModel):
    """Request to extract text from documents."""
    document_ids: Optional[List[str]] = None  # None means all documents
    force: bool = False  # Re-extract even if text already exists


class ExtractTextResponse(BaseModel):
    """Response from text extraction."""
    extracted: int
    skipped: int
    failed: int
    errors: List[str]


@router.post("/extract-text")
async def extract_text(request: ExtractTextRequest) -> ExtractTextResponse:
    """
    Extract text content from documents.

    This populates the page_content field for search and chat.
    Can be used to re-extract text for documents imported before text extraction was working.
    """
    from pathlib import Path
    from fichero.models import DocType
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
