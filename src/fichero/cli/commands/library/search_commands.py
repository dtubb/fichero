"""
Search Commands

Full-text search commands using FTS5 for searching transcriptions, catalogue data,
and other indexed metadata across the library.
"""

import asyncio
import json
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from .base import BaseLibraryCommands


class SearchCommands(BaseLibraryCommands):
    """Full-text search operations"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize search commands - optionally share base instance"""
        if base_commands:
            # Use shared base instance (library_manager, director, etc.)
            self.library_manager = base_commands.library_manager
            self.director = base_commands.director
            self.bridge = base_commands.bridge
            self.console = base_commands.console
            self.app_initializer = app_initializer
        else:
            # Create own instances (standalone mode)
            super().__init__(app_initializer)

    def register_commands(self, app):
        """Register search commands"""

        @app.command(name="search", help="Search library content with full-text search")
        def search(
            query: str = typer.Argument(..., help="Search query (supports FTS5 syntax)"),
            collection_id: Optional[str] = typer.Option(None, "--collection", "-c", help="Filter by collection ID"),
            schema_type: Optional[List[str]] = typer.Option(None, "--schema", "-s", help="Filter by schema type (transcription, catalogue, etc.)"),
            source_label: Optional[List[str]] = typer.Option(None, "--source", "-l", help="Filter by source label (ai_qwen, human_corrected, etc.)"),
            language: Optional[str] = typer.Option(None, "--language", help="Filter by language"),
            confidence_min: Optional[float] = typer.Option(None, "--confidence-min", help="Minimum confidence score (0.0-1.0)"),
            limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of results"),
            offset: int = typer.Option(0, "--offset", help="Offset for pagination"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
            no_snippets: bool = typer.Option(False, "--no-snippets", help="Disable snippet generation")
        ):
            """
            Search library content using full-text search with BM25 ranking

            Query Syntax:
                - Simple: "document text"
                - Phrase: "\"exact phrase\""
                - Boolean: "term1 AND term2", "term1 OR term2"
                - Exclude: "term1 NOT term2"
                - Prefix: "archiv*"

            Examples:
                # Search all transcriptions
                fichero library search "letter from John" --schema transcription

                # Search with confidence filter
                fichero library search "colonial archive" --confidence-min 0.8

                # Search specific collection and source
                fichero library search "1931" --collection <id> --source ai_qwen

                # Multi-language search
                fichero library search "documento" --language es

                # Boolean search
                fichero library search "archivo AND colonial NOT duplicado"
            """
            asyncio.run(self._search(
                query, collection_id, schema_type, source_label,
                language, confidence_min, limit, offset,
                json_output, not no_snippets
            ))

        @app.command(name="search-facets", help="Get facet counts for search results")
        def search_facets(
            query: str = typer.Argument(..., help="Search query"),
            collection_id: Optional[str] = typer.Option(None, "--collection", "-c", help="Filter by collection ID"),
            facet: List[str] = typer.Option(
                ["schema_type", "source_label"],
                "--facet", "-f",
                help="Facet fields (schema_type, source_label, collection_id)"
            ),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON")
        ):
            """
            Get facet counts for search results

            Useful for understanding the distribution of search results across
            different dimensions (schema types, sources, collections).

            Examples:
                fichero library search-facets "archive" --facet schema_type --facet source_label
                fichero library search-facets "colonial" --collection <id>
            """
            asyncio.run(self._search_facets(query, collection_id, facet, json_output))

        @app.command(name="search-stats", help="Show search index statistics")
        def search_stats(
            json_output: bool = typer.Option(False, "--json", help="Output as JSON")
        ):
            """
            Show statistics about the search index

            Displays:
                - Total indexed documents
                - Documents by schema type
                - Documents by source label
                - Index size

            Examples:
                fichero library search-stats
                fichero library search-stats --json
            """
            asyncio.run(self._search_stats(json_output))

        @app.command(name="rebuild-index", help="Rebuild search index")
        def rebuild_index(
            collection_id: Optional[str] = typer.Option(None, "--collection", "-c", help="Rebuild index for specific collection only"),
            force: bool = typer.Option(False, "--force", "-f", help="Force rebuild without confirmation")
        ):
            """
            Rebuild the search index from scratch

            This can be useful if:
                - Search results seem incorrect or incomplete
                - After bulk imports or migrations
                - After database corruption

            Examples:
                fichero library rebuild-index
                fichero library rebuild-index --collection <id>
                fichero library rebuild-index --force
            """
            asyncio.run(self._rebuild_index(collection_id, force))

        @app.command(name="suggest", help="Get query completion suggestions")
        def suggest(
            prefix: str = typer.Argument(..., help="Query prefix to complete"),
            limit: int = typer.Option(10, "--limit", "-n", help="Maximum suggestions"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON")
        ):
            """
            Get query completion suggestions based on indexed content

            Useful for building autocomplete interfaces or exploring indexed terms.

            Examples:
                fichero library suggest "archiv"
                fichero library suggest "doc" --limit 20
            """
            asyncio.run(self._suggest(prefix, limit, json_output))

    async def _search(
        self,
        query: str,
        collection_id: Optional[str],
        schema_types: Optional[List[str]],
        source_labels: Optional[List[str]],
        language: Optional[str],
        confidence_min: Optional[float],
        limit: int,
        offset: int,
        json_output: bool,
        include_snippets: bool
    ):
        """Execute search and display results"""
        try:
            # Build metadata filters
            metadata_filters = {}
            if language:
                metadata_filters["language"] = language
            if confidence_min is not None:
                metadata_filters["confidence"] = f">={confidence_min}"

            # Execute search
            collection_ids = [collection_id] if collection_id else None

            response = self.library_manager.search(
                query=query,
                collection_ids=collection_ids,
                schema_types=schema_types,
                source_labels=source_labels,
                metadata_filters=metadata_filters if metadata_filters else None,
                limit=limit,
                offset=offset,
                include_snippets=include_snippets
            )

            if json_output:
                # JSON output
                output = {
                    "query": response.query,
                    "total_count": response.total_count,
                    "took_ms": response.took_ms,
                    "results": [
                        {
                            "metadata_id": r.metadata_id,
                            "collection_id": r.collection_id,
                            "item_id": r.item_id,
                            "schema_type": r.schema_type,
                            "source_label": r.source_label,
                            "version": r.version,
                            "rank": r.rank,
                            "snippet": r.snippet
                        }
                        for r in response.results
                    ]
                }
                self.console.print(json.dumps(output, indent=2))
            else:
                # Rich console output
                if not response.results:
                    self.console.print(f"[yellow]No results found for query: {query}[/yellow]")
                    return

                # Header
                self.console.print(
                    f"\n[bold cyan]Search Results[/bold cyan] "
                    f"({response.total_count} total, showing {len(response.results)}, "
                    f"took {response.took_ms:.1f}ms)\n"
                )

                # Results
                for i, result in enumerate(response.results, start=offset + 1):
                    # Get item details
                    item = None
                    if result.item_id:
                        item = await self.library_manager.get_item(result.item_id)

                    item_name = item.name if item else result.item_id or "Unknown"

                    # Result panel
                    title = f"[bold]{i}. {item_name}[/bold]"

                    content_lines = [
                        f"[cyan]Schema:[/cyan] {result.schema_type}",
                        f"[cyan]Source:[/cyan] {result.source_label} (v{result.version})",
                        f"[cyan]Collection:[/cyan] {result.collection_id}",
                        f"[cyan]Rank:[/cyan] {result.rank:.4f}",
                    ]

                    if result.snippet:
                        content_lines.append(f"\n[dim]{result.snippet}[/dim]")

                    panel = Panel(
                        "\n".join(content_lines),
                        title=title,
                        border_style="blue",
                        expand=False
                    )
                    self.console.print(panel)

                # Pagination hint
                if response.total_count > offset + len(response.results):
                    next_offset = offset + limit
                    self.console.print(
                        f"\n[dim]Showing results {offset + 1}-{offset + len(response.results)} of {response.total_count}. "
                        f"Use --offset {next_offset} to see more.[/dim]\n"
                    )

        except Exception as e:
            self.console.print(f"[red]Search failed: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _search_facets(
        self,
        query: str,
        collection_id: Optional[str],
        facet_fields: List[str],
        json_output: bool
    ):
        """Get facet counts for search results"""
        try:
            collection_ids = [collection_id] if collection_id else None

            facets = self.library_manager.search_service.search_facets(
                query=query,
                collection_ids=collection_ids,
                facet_fields=facet_fields
            )

            if json_output:
                self.console.print(json.dumps(facets, indent=2))
            else:
                self.console.print(f"\n[bold cyan]Search Facets for query: {query}[/bold cyan]\n")

                for facet_field, counts in facets.items():
                    if not counts:
                        continue

                    table = Table(title=f"{facet_field}")
                    table.add_column("Value", style="cyan")
                    table.add_column("Count", style="magenta", justify="right")

                    for value, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
                        table.add_row(value, str(count))

                    self.console.print(table)
                    self.console.print()

        except Exception as e:
            self.console.print(f"[red]Failed to get facets: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _search_stats(self, json_output: bool):
        """Show search index statistics"""
        try:
            stats = self.library_manager.get_search_stats()

            if json_output:
                self.console.print(json.dumps(stats, indent=2))
            else:
                self.console.print("\n[bold cyan]Search Index Statistics[/bold cyan]\n")

                self.console.print(f"Total Indexed Documents: [bold]{stats.get('total_documents', 0)}[/bold]")
                self.console.print(f"Index Size: [bold]{stats.get('index_size_mb', 0):.2f} MB[/bold]")
                self.console.print()

                # By schema type
                if stats.get('by_schema_type'):
                    table = Table(title="Documents by Schema Type")
                    table.add_column("Schema Type", style="cyan")
                    table.add_column("Count", style="magenta", justify="right")

                    for schema, count in sorted(stats['by_schema_type'].items(), key=lambda x: x[1], reverse=True):
                        table.add_row(schema, str(count))

                    self.console.print(table)
                    self.console.print()

                # By source label
                if stats.get('by_source_label'):
                    table = Table(title="Documents by Source Label")
                    table.add_column("Source Label", style="cyan")
                    table.add_column("Count", style="magenta", justify="right")

                    for source, count in sorted(stats['by_source_label'].items(), key=lambda x: x[1], reverse=True):
                        table.add_row(source, str(count))

                    self.console.print(table)

        except Exception as e:
            self.console.print(f"[red]Failed to get search stats: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _rebuild_index(self, collection_id: Optional[str], force: bool):
        """Rebuild search index"""
        try:
            scope = f"collection {collection_id}" if collection_id else "entire library"

            if not force:
                self.console.print(f"[yellow]⚠️  This will rebuild the search index for {scope}.[/yellow]")
                response = typer.confirm("Continue?")
                if not response:
                    self.console.print("[blue]Index rebuild cancelled.[/blue]")
                    return

            self.console.print(f"[blue]Rebuilding search index for {scope}...[/blue]")

            success = self.library_manager.rebuild_search_index(collection_id)

            if success:
                self.console.print(f"[green]✅ Search index rebuilt successfully for {scope}[/green]")

                # Show new stats
                stats = self.library_manager.get_search_stats()
                self.console.print(f"[dim]Indexed {stats.get('total_documents', 0)} documents[/dim]")
            else:
                self.console.print(f"[red]❌ Failed to rebuild search index[/red]")

        except Exception as e:
            self.console.print(f"[red]Failed to rebuild index: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _suggest(self, prefix: str, limit: int, json_output: bool):
        """Get query completion suggestions"""
        try:
            suggestions = self.library_manager.search_service.suggest_completions(prefix, limit)

            if json_output:
                output = {
                    "prefix": prefix,
                    "suggestions": suggestions
                }
                self.console.print(json.dumps(output, indent=2))
            else:
                if not suggestions:
                    self.console.print(f"[yellow]No suggestions found for prefix: {prefix}[/yellow]")
                    return

                self.console.print(f"\n[bold cyan]Suggestions for '{prefix}':[/bold cyan]\n")

                for suggestion in suggestions:
                    self.console.print(f"  • {suggestion}")

                self.console.print(f"\n[dim]Showing {len(suggestions)} suggestion(s)[/dim]\n")

        except Exception as e:
            self.console.print(f"[red]Failed to get suggestions: {e}[/red]")
            import traceback
            traceback.print_exc()
