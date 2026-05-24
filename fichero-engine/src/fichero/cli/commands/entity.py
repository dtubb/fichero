"""CLI commands for entity operations."""

import typer
from typing import Optional
from fichero.cli.client import FicheroClient, DEFAULT_BASE_URL

app = typer.Typer(name="entity", help="Manage knowledge entities.")

@app.command("list")
def list_entities(
    host: str = typer.Option(DEFAULT_BASE_URL, "--host", help="Fichero backend host"),
    limit: int = typer.Option(50, "--limit", help="Maximum number of entities to return"),
    entity_type: Optional[str] = typer.Option(None, "--type", help="Filter by entity type"),
    query: Optional[str] = typer.Option(None, "--query", help="Search entities by name or alias"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List knowledge entities with optional filtering."""
    client = FicheroClient(base_url=host)
    try:
        entities = client.list_entities(
            limit=limit,
            entity_type=entity_type,
            query=query,
        )
        if json_output:
            import json
            typer.echo(json.dumps([e.model_dump() for e in entities], indent=2))
        else:
            typer.echo(f"Found {len(entities)} entities:")
            for entity in entities:
                typer.echo(f"  {entity.id}: {entity.canonical_name} ({entity.entity_type})")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command("claims")
def list_entity_claims(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    host: str = typer.Option(DEFAULT_BASE_URL, "--host", help="Fichero backend host"),
    limit: int = typer.Option(200, "--limit", help="Maximum number of claims to return"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List claims for a specific entity."""
    client = FicheroClient(base_url=host)
    try:
        response = client.get_entity_claims(entity_id=entity_id, limit=limit)
        if json_output:
            import json
            typer.echo(json.dumps(response.model_dump(), indent=2))
        else:
            typer.echo(f"Entity {entity_id} claims ({response.count}):")
            for claim in response.items:
                typer.echo(f"  {claim.id}: {claim.text[:100]}...")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command("digest")
def entity_digest(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    host: str = typer.Option(DEFAULT_BASE_URL, "--host", help="Fichero backend host"),
    format_type: str = typer.Option("markdown", "--format", help="Output format: markdown, text, json"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON (overrides format)"),
):
    """Show a structured digest of an entity."""
    client = FicheroClient(base_url=host)
    try:
        response = client.get_entity_drill_down(entity_id=entity_id)
        if json_output:
            import json
            typer.echo(json.dumps(response.model_dump(), indent=2))
        elif format_type == "markdown":
            typer.echo(f"# Entity Digest: {response.entity.canonical_name}")
            typer.echo(f"\n**Type:** {response.entity.entity_type}")
            typer.echo(f"\n**Description:** {response.entity.description or 'No description'}")
            typer.echo(f"\n**Aliases:** {', '.join(response.entity.aliases or [])}")

            if response.documents:
                typer.echo(f"\n## Documents ({len(response.documents)})")
                for doc in response.documents[:5]:
                    typer.echo(f"- {doc.document_name} ({doc.claim_count} claims)")

            if response.co_occurring:
                typer.echo(f"\n## Related Entities ({len(response.co_occurring)})")
                for co in response.co_occurring[:5]:
                    typer.echo(f"- {co.name} ({co.kind})")

            if response.claim_excerpts:
                typer.echo(f"\n## Representative Claims ({len(response.claim_excerpts)})")
                for excerpt in response.claim_excerpts[:3]:
                    typer.echo(f"- {excerpt}")
        elif format_type == "text":
            typer.echo(f"Entity: {response.entity.canonical_name}")
            typer.echo(f"Type: {response.entity.entity_type}")
            typer.echo(f"Description: {response.entity.description or 'No description'}")
            typer.echo(f"Aliases: {', '.join(response.entity.aliases or [])}")

            if response.documents:
                typer.echo(f"Documents ({len(response.documents)}):")
                for doc in response.documents[:5]:
                    typer.echo(f"  {doc.document_name} ({doc.claim_count} claims)")

            if response.co_occurring:
                typer.echo(f"Related Entities ({len(response.co_occurring)}):")
                for co in response.co_occurring[:5]:
                    typer.echo(f"  {co.name} ({co.kind})")

            if response.claim_excerpts:
                typer.echo(f"Representative Claims ({len(response.claim_excerpts)}):")
                for excerpt in response.claim_excerpts[:3]:
                    typer.echo(f"  {excerpt}")
        else:
            import json
            typer.echo(json.dumps(response.model_dump(), indent=2))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@app.command("biography")
def entity_biography(
    entity_id: str = typer.Argument(..., help="Entity ID"),
    host: str = typer.Option(DEFAULT_BASE_URL, "--host", help="Fichero backend host"),
    format_type: str = typer.Option("markdown", "--format", help="Output format: markdown, text, json"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON (overrides format)"),
):
    """Show a detailed biography/overview of an entity."""
    client = FicheroClient(base_url=host)
    try:
        entity = client.get_entity(entity_id=entity_id)
        documents = client.entity_documents(entity_id=entity_id)
        co_occurrence = client.entity_co_occurrence(entity_id=entity_id)

        if json_output:
            import json
            typer.echo(json.dumps({
                "entity": entity.model_dump(),
                "documents": [d.model_dump() for d in documents],
                "co_occurrence": [c.model_dump() for c in co_occurrence],
            }, indent=2))
        elif format_type == "markdown":
            typer.echo(f"# {entity.canonical_name}")
            typer.echo(f"\n**Type**: {entity.entity_type}")
            typer.echo(f"\n**Description**: {entity.description or 'No description'}")
            typer.echo(f"\n**Aliases**: {', '.join(entity.aliases or [])}")

            if documents:
                typer.echo(f"\n## Associated Documents ({len(documents)})")
                for doc in documents[:5]:
                    typer.echo(f"- [{doc.document_name}]({doc.document_id or ''}) ({doc.claim_count} claims)")

            if co_occurrence:
                typer.echo(f"\n## Related Entities ({len(co_occurrence)})")
                for co in co_occurrence[:5]:
                    typer.echo(f"- {co.name} ({co.kind}) ({co.shared_claims} shared claims)")
        elif format_type == "text":
            typer.echo(f"Name: {entity.canonical_name}")
            typer.echo(f"Type: {entity.entity_type}")
            typer.echo(f"Description: {entity.description or 'No description'}")
            typer.echo(f"Aliases: {', '.join(entity.aliases or [])}")

            if documents:
                typer.echo(f"\nAssociated Documents ({len(documents)}):")
                for doc in documents[:5]:
                    typer.echo(f"  {doc.document_name} ({doc.claim_count} claims)")

            if co_occurrence:
                typer.echo(f"\nRelated Entities ({len(co_occurrence)}):")
                for co in co_occurrence[:5]:
                    typer.echo(f"  {co.name} ({co.kind}) ({co.shared_claims} shared claims)")
        else:
            import json
            typer.echo(json.dumps({
                "entity": entity.model_dump(),
                "documents": [d.model_dump() for d in documents],
                "co_occurrence": [c.model_dump() for c in co_occurrence],
            }, indent=2))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
