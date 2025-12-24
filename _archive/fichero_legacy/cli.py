"""
Fichero CLI

Simple command-line interface for document ingestion and search.

Usage:
    fichero ingest <path>           # Ingest file or folder
    fichero search <query>          # Semantic search documents
    fichero find <pattern>          # Find by name pattern (supports wildcards)
    fichero list                    # List documents with filters
    fichero stats                   # Show library stats
    fichero reindex                 # Rebuild search index
    fichero query <question>        # RAG query (requires OPENAI_API_KEY)
    fichero serve                   # Start FastAPI REST API server
"""

import os
import re
from pathlib import Path
from typing import Optional, List
from fnmatch import fnmatch

import typer

app = typer.Typer(
    name="fichero",
    help="Document ingestion and search",
    add_completion=False,
    no_args_is_help=True,
)


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or folder to ingest"),
    copy: bool = typer.Option(False, "--copy", "-c", help="Copy files into library"),
    extract: bool = typer.Option(True, "--extract/--no-extract", help="Extract text content"),
    index: bool = typer.Option(True, "--index/--no-index", help="Create search embeddings"),
):
    """Ingest files into the library."""
    from fichero.ingest import ingest_file, ingest_folder, IngestMode

    if not path.exists():
        typer.echo(f"Error: {path} not found", err=True)
        raise typer.Exit(1)

    mode = IngestMode.COPY if copy else IngestMode.LINK

    def on_progress(current: int, total: int):
        typer.echo(f"  [{current}/{total}]", nl=False)
        if current == total:
            typer.echo()

    try:
        if path.is_file():
            doc = ingest_file(
                path,
                mode=mode,
                extract_text=extract,
                auto_embed=index,
            )
            typer.echo(f"Ingested: {doc.name}")
        else:
            docs = ingest_folder(
                path,
                mode=mode,
                extract_text=extract,
                auto_embed=index,
                on_progress=on_progress,
            )
            typer.echo(f"Ingested {len(docs)} files from {path.name}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    doc_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type: collection, folder, group, file"),
    file_type: Optional[str] = typer.Option(None, "--file-type", "-f", help="Filter by file type: image, pdf, text, word"),
    exclude: Optional[str] = typer.Option(None, "--exclude", "-x", help="Exclude results containing these words (comma-separated)"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum similarity score (0-1)"),
):
    """Semantic search documents by content."""
    from fichero.db import db

    # Get more results to allow for filtering
    fetch_limit = limit * 3 if (doc_type or file_type or exclude) else limit
    results = db.search(query, limit=fetch_limit, min_score=min_score)

    if not results:
        typer.echo("No results found")
        return

    # Apply filters
    filtered = []
    exclude_words = [w.strip().lower() for w in exclude.split(",")] if exclude else []

    for r in results:
        # Type filter
        if doc_type and r.metadata.get('doc_type') != doc_type:
            continue
        if file_type and r.metadata.get('file_type') != file_type:
            continue

        # Exclude filter
        if exclude_words:
            name = (r.metadata.get('name') or '').lower()
            content = (r.content_preview or '').lower()
            text = f"{name} {content}"
            if any(word in text for word in exclude_words):
                continue

        filtered.append(r)
        if len(filtered) >= limit:
            break

    if not filtered:
        typer.echo("No results found (after filtering)")
        return

    typer.echo(f"Found {len(filtered)} results:\n")

    for i, r in enumerate(filtered, 1):
        name = r.metadata.get('name') or r.document_id[:12]
        dt = r.metadata.get('doc_type', '')
        type_str = f" [{dt}]" if dt else ""

        typer.echo(f"{i}. [{r.score:.3f}]{type_str} {name}")
        if r.content_preview:
            preview = r.content_preview[:120].replace('\n', ' ').strip()
            typer.echo(f"   {preview}...")
        typer.echo()


@app.command()
def find(
    pattern: str = typer.Argument(..., help="Name pattern (supports * and ? wildcards)"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    doc_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type: collection, folder, group, file"),
    file_type: Optional[str] = typer.Option(None, "--file-type", "-f", help="Filter by file type: image, pdf, text, word"),
    sort: str = typer.Option("name", "--sort", "-s", help="Sort by: name, date, type"),
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Reverse sort order"),
):
    """Find documents by name pattern (wildcards: * matches any, ? matches one char)."""
    from fichero.db import db
    from fichero.models import Document

    all_docs = db.all(Document)

    # Filter by pattern
    matches = []
    for doc in all_docs:
        if fnmatch(doc.name.lower(), pattern.lower()):
            # Apply type filters
            if doc_type and doc.doc_type.value != doc_type:
                continue
            if file_type and (not doc.file_type or doc.file_type.value != file_type):
                continue
            matches.append(doc)

    if not matches:
        typer.echo(f"No documents matching '{pattern}'")
        return

    # Sort
    if sort == "name":
        matches.sort(key=lambda d: d.name.lower(), reverse=reverse)
    elif sort == "date":
        matches.sort(key=lambda d: d.created_at, reverse=not reverse)  # newest first by default
    elif sort == "type":
        matches.sort(key=lambda d: (d.doc_type.value, d.name.lower()), reverse=reverse)

    # Limit
    total = len(matches)
    matches = matches[:limit]

    typer.echo(f"Found {total} documents matching '{pattern}'")
    if total > limit:
        typer.echo(f"(showing first {limit})\n")
    else:
        typer.echo()

    for doc in matches:
        ft = f" ({doc.file_type.value})" if doc.file_type else ""
        typer.echo(f"  [{doc.doc_type.value}]{ft} {doc.name}")


@app.command(name="list")
def list_docs(
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    doc_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type: collection, folder, group, file"),
    file_type: Optional[str] = typer.Option(None, "--file-type", "-f", help="Filter by file type: image, pdf, text, word"),
    has_content: Optional[bool] = typer.Option(None, "--has-content/--no-content", help="Filter by text content presence"),
    indexed: Optional[bool] = typer.Option(None, "--indexed/--not-indexed", help="Filter by index status"),
    sort: str = typer.Option("date", "--sort", "-s", help="Sort by: name, date, type"),
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Reverse sort order"),
    contains: Optional[str] = typer.Option(None, "--contains", "-c", help="Filter: name or content contains text"),
):
    """List documents with filtering and sorting."""
    from fichero.db import db
    from fichero.models import Document

    all_docs = db.all(Document)

    # Get indexed doc IDs for filtering
    indexed_ids = set()
    if indexed is not None:
        embed_stats = db.embedding_stats()
        # This is a simplification - in real implementation would query LanceDB
        indexed_ids = set(r.get("id") for r in db.lance.open_table("embeddings").to_pandas().to_dict("records")) if "embeddings" in db.lance.table_names() else set()

    # Filter
    matches = []
    for doc in all_docs:
        # Type filters
        if doc_type and doc.doc_type.value != doc_type:
            continue
        if file_type and (not doc.file_type or doc.file_type.value != file_type):
            continue

        # Content filter
        if has_content is True and (not doc.page_content or len(doc.page_content) < 10):
            continue
        if has_content is False and doc.page_content and len(doc.page_content) >= 10:
            continue

        # Index filter
        if indexed is True and doc.id not in indexed_ids:
            continue
        if indexed is False and doc.id in indexed_ids:
            continue

        # Contains filter
        if contains:
            search_text = f"{doc.name} {doc.page_content or ''}".lower()
            if contains.lower() not in search_text:
                continue

        matches.append(doc)

    if not matches:
        typer.echo("No documents found matching filters")
        return

    # Sort
    if sort == "name":
        matches.sort(key=lambda d: d.name.lower(), reverse=reverse)
    elif sort == "date":
        matches.sort(key=lambda d: d.created_at, reverse=not reverse)
    elif sort == "type":
        matches.sort(key=lambda d: (d.doc_type.value, d.name.lower()), reverse=reverse)

    # Limit
    total = len(matches)
    matches = matches[:limit]

    typer.echo(f"Total: {total} documents")
    if total > limit:
        typer.echo(f"(showing first {limit})\n")
    else:
        typer.echo()

    for doc in matches:
        ft = f" ({doc.file_type.value})" if doc.file_type else ""
        content_marker = "●" if doc.page_content and len(doc.page_content) >= 10 else "○"
        typer.echo(f"  {content_marker} [{doc.doc_type.value}]{ft} {doc.name}")


@app.command()
def stats():
    """Show library statistics."""
    from fichero.db import db
    from fichero.models import Document

    doc_count = db.count(Document)
    embed_stats = db.embedding_stats()

    typer.echo(f"Documents: {doc_count}")
    typer.echo(f"Indexed:   {embed_stats.get('indexed_count', 0)}")


@app.command()
def reindex():
    """Rebuild search index for all documents."""
    from fichero.db import db

    def on_progress(indexed: int, total: int):
        typer.echo(f"  [{indexed}/{total}]", nl=False)
        if indexed == total:
            typer.echo()

    typer.echo("Reindexing...")
    count = db.reindex_all(on_progress=on_progress)
    typer.echo(f"Indexed {count} documents")


@app.command()
def extract_text(
    doc_id: str = typer.Argument(None, help="Document ID to extract (or 'all' for all documents)"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-extract even if text already exists"),
):
    """Extract/re-extract text content from documents.

    This populates the page_content field for search and chat.

    Examples:
        fichero extract-text all          # Extract text for all documents
        fichero extract-text all --force  # Re-extract even if already done
        fichero extract-text abc123       # Extract for specific document
    """
    from fichero.db import db
    from fichero.models import Document, DocType
    from fichero.ingest import _extract_text_content
    from pathlib import Path

    if doc_id == "all" or doc_id is None:
        # Process all documents
        docs = list(db.all(Document))
        typer.echo(f"Processing {len(docs)} documents...")

        extracted = 0
        skipped = 0
        failed = 0

        for doc in docs:
            # Skip if already has content and not forcing
            if doc.page_content and not force:
                skipped += 1
                continue

            # Skip folders and collections
            if doc.doc_type in (DocType.folder, DocType.collection):
                skipped += 1
                continue

            if not doc.path:
                skipped += 1
                continue

            path = Path(doc.path)
            if not path.exists():
                typer.echo(f"  Skipping {doc.name}: file not found")
                skipped += 1
                continue

            try:
                _extract_text_content(doc, path)
                if doc.page_content:
                    db.save(doc)
                    extracted += 1
                    typer.echo(f"  ✓ {doc.name} ({len(doc.page_content)} chars)")
                else:
                    skipped += 1
            except Exception as e:
                typer.echo(f"  ✗ {doc.name}: {e}")
                failed += 1

        typer.echo(f"\nDone: {extracted} extracted, {skipped} skipped, {failed} failed")
    else:
        # Process single document
        doc = db.get(Document, doc_id)
        if not doc:
            typer.echo(f"Document not found: {doc_id}", err=True)
            raise typer.Exit(1)

        if not doc.path:
            typer.echo(f"Document has no file path", err=True)
            raise typer.Exit(1)

        path = Path(doc.path)
        if not path.exists():
            typer.echo(f"File not found: {path}", err=True)
            raise typer.Exit(1)

        _extract_text_content(doc, path)
        if doc.page_content:
            db.save(doc)
            typer.echo(f"Extracted {len(doc.page_content)} characters from {doc.name}")
        else:
            typer.echo(f"No text extracted from {doc.name}")


@app.command()
def serve(
    port: int = typer.Option(8765, "--port", "-p", help="Port to bind to"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
):
    """Start the FastAPI REST API server."""
    import uvicorn

    typer.echo(f"Starting Fichero API at http://{host}:{port}")
    typer.echo("Press Ctrl+C to stop\n")

    uvicorn.run(
        "fichero.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command()
def query(
    question: str = typer.Argument(..., help="Question to ask"),
    context_limit: int = typer.Option(5, "--context", "-c", help="Number of documents for context"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model to use"),
):
    """Ask a question using RAG (retrieval-augmented generation)."""
    from fichero.db import db

    # Find relevant documents
    typer.echo("Searching for relevant documents...")
    results = db.search(question, limit=context_limit)

    if not results:
        typer.echo("No relevant documents found. Try ingesting some files first.")
        raise typer.Exit(1)

    typer.echo(f"Found {len(results)} relevant documents\n")

    # Build context from search results
    context_parts = []
    for i, r in enumerate(results, 1):
        context_parts.append(f"[Document {i}]:\n{r.content_preview}")

    context = "\n\n".join(context_parts)

    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        typer.echo("Error: OPENAI_API_KEY environment variable not set", err=True)
        raise typer.Exit(1)

    # Call LLM
    typer.echo("Generating answer...\n")

    try:
        from openai import OpenAI
        client = OpenAI()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that answers questions based on the provided documents. "
                        "Use only the information from the documents. If the answer isn't in the documents, say so."
                    )
                },
                {
                    "role": "user",
                    "content": f"Documents:\n{context}\n\nQuestion: {question}"
                }
            ],
            temperature=0.3,
        )

        answer = response.choices[0].message.content
        typer.echo(f"Answer:\n{answer}\n")

        # Show sources
        typer.echo("Sources:")
        for i, r in enumerate(results, 1):
            name = r.metadata.get("name") or r.document_id[:8]
            typer.echo(f"  {i}. [{r.score:.2f}] {name}")

    except ImportError:
        typer.echo("Error: openai package not installed", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error calling LLM: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
