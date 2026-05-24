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
        response = client.get_entities(
            limit=limit,
            entity_type=entity_type,
            q=query,
        )
        if json_output:
            import json
            typer.echo(json.dumps(response, indent=2))
        else:
            typer.echo(f"Found {response['count']} entities:")
            for entity in response['items']:
                typer.echo(f"  {entity['id']}: {entity['canonical_name']} ({entity['entity_type']})")
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
            typer.echo(json.dumps(response, indent=2))
        else:
            typer.echo(f"Entity {entity_id} claims:")
            for claim in response['items']:
                typer.echo(f"  {claim['id']}: {claim['text'][:100]}...")
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
            typer.echo(json.dumps(response, indent=2))
        elif format_type == "markdown":
            # Simple markdown formatting
            typer.echo(f"# Entity Digest: {response['entity']['canonical_name']}")
            typer.echo(f"\n**Type:** {response['entity']['entity_type']}")
            typer.echo(f"\n**Description:** {response['entity'].get('description', 'No description')}")
            typer.echo(f"\n**Aliases:** {', '.join(response['entity'].get('aliases', []))}")
            
            if response['documents']:
                typer.echo(f"\n## Documents ({len(response['documents'])})")
                for doc in response['documents'][:5]:  # Show first 5
                    typer.echo(f"- {doc['document_name']} ({doc['claim_count']} claims)")
                    
            if response['co_occurring']:
                typer.echo(f"\n## Related Entities ({len(response['co_occurring'])})")
                for entity in response['co_occurring'][:5]:  # Show first 5
                    typer.echo(f"- {entity['name']} ({entity['kind']})")
                    
            if response['claim_excerpts']:
                typer.echo(f"\n## Representative Claims ({len(response['claim_excerpts'])})")
                for excerpt in response['claim_excerpts'][:3]:  # Show first 3
                    typer.echo(f"- {excerpt}")
        elif format_type == "text":
            # Simple text formatting
            typer.echo(f"Entity: {response['entity']['canonical_name']}")
            typer.echo(f"Type: {response['entity']['entity_type']}")
            typer.echo(f"Description: {response['entity'].get('description', 'No description')}")
            typer.echo(f"Aliases: {', '.join(response['entity'].get('aliases', []))}")
            
            if response['documents']:
                typer.echo(f"Documents ({len(response['documents'])}):")
                for doc in response['documents'][:5]:
                    typer.echo(f"  {doc['document_name']} ({doc['claim_count']} claims)")
                    
            if response['co_occurring']:
                typer.echo(f"Related Entities ({len(response['co_occurring'])}):")
                for entity in response['co_occurring'][:5]:
                    typer.echo(f"  {entity['name']} ({entity['kind']})")
                    
            if response['claim_excerpts']:
                typer.echo(f"Representative Claims ({len(response['claim_excerpts'])}):")
                for excerpt in response['claim_excerpts'][:3]:
                    typer.echo(f"  {excerpt}")
        else:
            import json
            typer.echo(json.dumps(response, indent=2))
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
        # Get entity details
        entity = client.get_entity(entity_id=entity_id)
        
        # Get entity documents
        documents = client.get_entity_documents(entity_id=entity_id)
        
        # Get co-occurrence data
        co_occurrence = client.get_entity_co_occurrence(entity_id=entity_id)
        
        if json_output:
            import json
            response = {
                "entity": entity,
                "documents": documents,
                "co_occurrence": co_occurrence
            }
            typer.echo(json.dumps(response, indent=2))
        elif format_type == "markdown":
            # Markdown formatted biography
            typer.echo(f"# {entity['canonical_name']}")
            typer.echo(f"\n**Type**: {entity['entity_type']}")
            typer.echo(f"\n**Description**: {entity.get('description', 'No description')}")
            typer.echo(f"\n**Aliases**: {', '.join(entity.get('aliases', []))}")
            
            if documents.get('items'):
                typer.echo(f"\n## Associated Documents ({len(documents['items'])})")
                for doc in documents['items'][:5]:
                    typer.echo(f"- [{doc['document_name']}]({doc.get('document_id', '')}) ({doc['claim_count']} claims)")
                    
            if co_occurrence.get('items'):
                typer.echo(f"\n## Related Entities ({len(co_occurrence['items'])})")
                for entity in co_occurrence['items'][:5]:
                    typer.echo(f"- {entity['name']} ({entity['kind']}) ({entity['shared_claims']} shared claims)")
        elif format_type == "text":
            # Text formatted biography
            typer.echo(f"Name: {entity['canonical_name']}")
            typer.echo(f"Type: {entity['entity_type']}")
            typer.echo(f"Description: {entity.get('description', 'No description')}")
            typer.echo(f"Aliases: {', '.join(entity.get('aliases', []))}")
            
            if documents.get('items'):
                typer.echo(f"\nAssociated Documents ({len(documents['items'])}):")
                for doc in documents['items'][:5]:
                    typer.echo(f"  {doc['document_name']} ({doc['claim_count']} claims)")
                    
            if co_occurrence.get('items'):
                typer.echo(f"\nRelated Entities ({len(co_occurrence['items'])}):")
                for entity in co_occurrence['items'][:5]:
                    typer.echo(f"  {entity['name']} ({entity['kind']}) ({entity['shared_claims']} shared claims)")
        else:
            import json
            response = {
                "entity": entity,
                "documents": documents,
                "co_occurrence": co_occurrence
            }
            typer.echo(json.dumps(response, indent=2))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
