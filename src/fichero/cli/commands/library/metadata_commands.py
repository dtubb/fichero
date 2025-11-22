"""
Metadata Management Commands - DEPRECATED

**DEPRECATED**: These commands use the old metadata_api system.
Use the new commands instead:
    - For search: fichero library search, search-facets, search-stats
    - For bulk ops: fichero library bulk-export-metadata, bulk-import-metadata, etc.

These commands are kept for backward compatibility only and will be removed.
They log deprecation warnings when used.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from .base import BaseLibraryCommands

logger = logging.getLogger(__name__)


class MetadataCommands(BaseLibraryCommands):
    """Metadata query and management operations"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize metadata commands - optionally share base instance"""
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
        """Register metadata management commands"""

        @app.command(name="metadata-query", help="Query items by metadata filters")
        def metadata_query(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            filter: List[str] = typer.Option(None, "--filter", "-f", help="Metadata filter (e.g., 'crop.method=yolo' or 'crop.confidence>=0.85')"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
            show_metadata: bool = typer.Option(False, "--show-metadata", "-m", help="Show metadata for matching items")
        ):
            """Query items by metadata filters

            Examples:
                fichero library metadata-query <collection_id> --filter "crop.method=yolo"
                fichero library metadata-query <collection_id> --filter "crop.confidence>=0.85" --filter "rotate.angle>=-1"
            """
            asyncio.run(self._metadata_query(collection_id, filter, json_output, show_metadata))

        @app.command(name="metadata-show", help="Show all metadata for an item")
        def metadata_show(
            item_id: str = typer.Argument(..., help="ID of the item"),
            step: Optional[str] = typer.Option(None, "--step", "-s", help="Show metadata for specific step only"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
            version: Optional[int] = typer.Option(None, "--version", "-v", help="Show specific version of metadata")
        ):
            """Show all metadata for an item

            Examples:
                fichero library metadata-show <item_id>
                fichero library metadata-show <item_id> --step crop
                fichero library metadata-show <item_id> --step crop --version 2
            """
            asyncio.run(self._metadata_show(item_id, step, json_output, version))

        @app.command(name="metadata-export", help="Export metadata to JSON file")
        def metadata_export(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            output_file: str = typer.Argument(..., help="Output JSON file path"),
            step: Optional[str] = typer.Option(None, "--step", "-s", help="Export metadata for specific step only"),
            pretty: bool = typer.Option(True, "--pretty/--compact", help="Pretty-print JSON")
        ):
            """Export metadata to JSON file

            Examples:
                fichero library metadata-export <collection_id> metadata.json
                fichero library metadata-export <collection_id> crop_metadata.json --step crop
            """
            asyncio.run(self._metadata_export(collection_id, output_file, step, pretty))

        @app.command(name="metadata-stats", help="Show statistics about stored metadata")
        def metadata_stats(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON")
        ):
            """Show statistics about stored metadata

            Examples:
                fichero library metadata-stats <collection_id>
                fichero library metadata-stats <collection_id> --json
            """
            asyncio.run(self._metadata_stats(collection_id, json_output))

        @app.command(name="metadata-import", help="Import JSONL manifest into library metadata")
        def metadata_import(
            item_id: str = typer.Argument(..., help="ID of the item"),
            manifest_path: str = typer.Argument(..., help="Path to JSONL manifest file"),
            step: Optional[str] = typer.Option(None, "--step", "-s", help="Import as specific step (if not in manifest)"),
            dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be imported without importing")
        ):
            """Import JSONL manifest into library metadata

            Examples:
                fichero library metadata-import <item_id> manifest.jsonl
                fichero library metadata-import <item_id> crop_results.jsonl --step crop
            """
            asyncio.run(self._metadata_import(item_id, manifest_path, step, dry_run))

        @app.command(name="metadata-history", help="Show version history for item metadata")
        def metadata_history(
            item_id: str = typer.Argument(..., help="ID of the item"),
            step: str = typer.Argument(..., help="Processing step name"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON")
        ):
            """Show version history for item metadata

            Examples:
                fichero library metadata-history <item_id> crop
                fichero library metadata-history <item_id> rotate --json
            """
            asyncio.run(self._metadata_history(item_id, step, json_output))

    async def _metadata_query(self, collection_id: str, filters: Optional[List[str]], json_output: bool, show_metadata: bool):
        """Query items by metadata filters"""
        logger.warning("DEPRECATED: metadata-query command uses old metadata_api. Use 'fichero library search' instead.")
        self.console.print("[yellow]⚠️  DEPRECATED: Use 'fichero library search' instead of metadata-query[/yellow]\n")
        try:
            # Get collection first
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Parse filters
            if not filters:
                self.console.print("[yellow]⚠️  No filters provided. Use --filter to specify metadata filters.[/yellow]")
                return

            parsed_filters = self._parse_filters(filters)
            if not parsed_filters:
                return

            # Query items using metadata API
            metadata_api = self.library_manager.metadata_api
            matching_item_ids = metadata_api.query_items_by_metadata(collection_id, parsed_filters)

            if not matching_item_ids:
                self.console.print(f"[yellow]No items found matching filters[/yellow]")
                return

            # Get item details
            items = []
            for item_id in matching_item_ids:
                item = await self.library_manager.get_item(item_id)
                if item:
                    items.append(item)

            # Output results
            if json_output:
                output = {
                    "collection_id": collection_id,
                    "filters": filters,
                    "matching_items": [
                        {
                            "id": str(item.id),
                            "name": item.name,
                            "type": item.type,
                            "status": item.status,
                            "source_path": item.source_path
                        }
                        for item in items
                    ]
                }
                self.console.print(json.dumps(output, indent=2))
            else:
                # Create table
                table = Table(title=f"Items Matching Filters in '{collection.name}'")
                table.add_column("ID", style="cyan", no_wrap=True)
                table.add_column("Name", style="magenta")
                table.add_column("Type", style="green")
                table.add_column("Status", style="yellow")

                for item in items:
                    table.add_row(
                        str(item.id),
                        item.name,
                        item.type,
                        item.status
                    )

                self.console.print(table)
                self.console.print(f"\n[green]Found {len(items)} item(s) matching filters[/green]")

                # Show metadata if requested
                if show_metadata:
                    self.console.print("\n[bold cyan]Metadata for matching items:[/bold cyan]")
                    for item in items:
                        self.console.print(f"\n[bold]{item.name}[/bold] ({item.id}):")
                        metadata = metadata_api.get_all_step_metadata(str(item.id))
                        if metadata:
                            syntax = Syntax(json.dumps(metadata, indent=2), "json", theme="monokai")
                            self.console.print(syntax)
                        else:
                            self.console.print("  [dim]No metadata found[/dim]")

        except Exception as e:
            self.console.print(f"[red]Failed to query metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _metadata_show(self, item_id: str, step: Optional[str], json_output: bool, version: Optional[int]):
        """Show all metadata for an item"""
        logger.warning("DEPRECATED: metadata-show command uses old metadata_api.")
        self.console.print("[yellow]⚠️  DEPRECATED: This command uses the old metadata system[/yellow]\n")
        try:
            # Get item first
            item = await self.library_manager.get_item(item_id)
            if not item:
                self.console.print(f"[red]Item not found: {item_id}[/red]")
                return

            metadata_api = self.library_manager.metadata_api

            # Get metadata
            if step:
                # Show specific step
                metadata = metadata_api.get_step_metadata(item_id, step, version=version)
                if not metadata:
                    self.console.print(f"[yellow]No metadata found for step '{step}'[/yellow]")
                    return

                output_data = {step: metadata}
            else:
                # Show all steps
                metadata = metadata_api.get_all_step_metadata(item_id)
                if not metadata:
                    self.console.print(f"[yellow]No metadata found for item {item_id}[/yellow]")
                    return

                output_data = metadata

            # Output results
            if json_output:
                output = {
                    "item_id": item_id,
                    "item_name": item.name,
                    "version": version if version else "latest",
                    "metadata": output_data
                }
                self.console.print(json.dumps(output, indent=2))
            else:
                version_str = f" (version {version})" if version else " (latest)"
                self.console.print(f"\n[bold cyan]Metadata for '{item.name}'{version_str}:[/bold cyan]\n")
                syntax = Syntax(json.dumps(output_data, indent=2), "json", theme="monokai")
                self.console.print(syntax)

        except Exception as e:
            self.console.print(f"[red]Failed to show metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _metadata_export(self, collection_id: str, output_file: str, step: Optional[str], pretty: bool):
        """Export metadata to JSON file"""
        logger.warning("DEPRECATED: metadata-export command uses old metadata_api. Use 'bulk-export-metadata' instead.")
        self.console.print("[yellow]⚠️  DEPRECATED: Use 'fichero library bulk-export-metadata' instead[/yellow]\n")
        try:
            # Get collection first
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Get all items
            items = await self.library_manager.get_collection_items(collection_id)
            if not items:
                self.console.print(f"[yellow]No items found in collection[/yellow]")
                return

            metadata_api = self.library_manager.metadata_api

            # Collect metadata
            export_data = {
                "collection_id": collection_id,
                "collection_name": collection.name,
                "export_timestamp": asyncio.get_event_loop().time(),
                "items": []
            }

            items_with_metadata = 0
            for item in items:
                if step:
                    metadata = metadata_api.get_step_metadata(str(item.id), step)
                    if metadata:
                        item_data = {
                            "item_id": str(item.id),
                            "item_name": item.name,
                            "metadata": {step: metadata}
                        }
                        export_data["items"].append(item_data)
                        items_with_metadata += 1
                else:
                    metadata = metadata_api.get_all_step_metadata(str(item.id))
                    if metadata:
                        item_data = {
                            "item_id": str(item.id),
                            "item_name": item.name,
                            "metadata": metadata
                        }
                        export_data["items"].append(item_data)
                        items_with_metadata += 1

            # Write to file
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                if pretty:
                    json.dump(export_data, f, indent=2)
                else:
                    json.dump(export_data, f)

            self.console.print(f"[green]✅ Exported metadata for {items_with_metadata} item(s) to {output_file}[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to export metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _metadata_stats(self, collection_id: str, json_output: bool):
        """Show statistics about stored metadata"""
        logger.warning("DEPRECATED: metadata-stats command uses old metadata_api.")
        self.console.print("[yellow]⚠️  DEPRECATED: This command uses the old metadata system[/yellow]\n")
        try:
            # Get collection first
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Get all items
            items = await self.library_manager.get_collection_items(collection_id)
            if not items:
                self.console.print(f"[yellow]No items found in collection[/yellow]")
                return

            metadata_api = self.library_manager.metadata_api

            # Collect statistics
            total_items = len(items)
            items_with_metadata = 0
            step_counts = {}
            field_counts = {}

            for item in items:
                metadata = metadata_api.get_all_step_metadata(str(item.id))
                if metadata:
                    items_with_metadata += 1
                    for step_name, step_metadata in metadata.items():
                        step_counts[step_name] = step_counts.get(step_name, 0) + 1
                        for field_name in step_metadata.keys():
                            full_key = f"{step_name}.{field_name}"
                            field_counts[full_key] = field_counts.get(full_key, 0) + 1

            # Output results
            if json_output:
                output = {
                    "collection_id": collection_id,
                    "collection_name": collection.name,
                    "total_items": total_items,
                    "items_with_metadata": items_with_metadata,
                    "coverage_percentage": round((items_with_metadata / total_items * 100) if total_items > 0 else 0, 2),
                    "steps": step_counts,
                    "fields": field_counts
                }
                self.console.print(json.dumps(output, indent=2))
            else:
                # Display statistics
                self.console.print(f"\n[bold cyan]Metadata Statistics for '{collection.name}':[/bold cyan]\n")
                self.console.print(f"Total Items: {total_items}")
                self.console.print(f"Items with Metadata: {items_with_metadata}")
                coverage = (items_with_metadata / total_items * 100) if total_items > 0 else 0
                self.console.print(f"Coverage: {coverage:.1f}%\n")

                if step_counts:
                    # Step counts table
                    step_table = Table(title="Metadata by Processing Step")
                    step_table.add_column("Step", style="cyan")
                    step_table.add_column("Items", style="magenta", justify="right")
                    step_table.add_column("Coverage", style="green", justify="right")

                    for step_name, count in sorted(step_counts.items()):
                        step_coverage = (count / total_items * 100) if total_items > 0 else 0
                        step_table.add_row(
                            step_name,
                            str(count),
                            f"{step_coverage:.1f}%"
                        )

                    self.console.print(step_table)

                    # Field counts table (top 10)
                    if field_counts:
                        self.console.print()
                        field_table = Table(title="Top Metadata Fields")
                        field_table.add_column("Field", style="cyan")
                        field_table.add_column("Count", style="magenta", justify="right")

                        sorted_fields = sorted(field_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                        for field_name, count in sorted_fields:
                            field_table.add_row(field_name, str(count))

                        self.console.print(field_table)
                else:
                    self.console.print("[yellow]No metadata found in collection[/yellow]")

        except Exception as e:
            self.console.print(f"[red]Failed to generate metadata stats: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _metadata_import(self, item_id: str, manifest_path: str, step: Optional[str], dry_run: bool):
        """Import JSONL manifest into library metadata"""
        logger.warning("DEPRECATED: metadata-import command uses old metadata_api. Use 'bulk-import-metadata' instead.")
        self.console.print("[yellow]⚠️  DEPRECATED: Use 'fichero library bulk-import-metadata' instead[/yellow]\n")
        try:
            # Get item first
            item = await self.library_manager.get_item(item_id)
            if not item:
                self.console.print(f"[red]Item not found: {item_id}[/red]")
                return

            # Read manifest file
            manifest_file = Path(manifest_path)
            if not manifest_file.exists():
                self.console.print(f"[red]Manifest file not found: {manifest_path}[/red]")
                return

            metadata_api = self.library_manager.metadata_api

            # Parse JSONL manifest
            entries_imported = 0
            with open(manifest_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        entry = json.loads(line.strip())

                        # Extract step name
                        entry_step = step or entry.get('step_name')
                        if not entry_step:
                            self.console.print(f"[yellow]⚠️  Line {line_num}: No step name found, skipping[/yellow]")
                            continue

                        # Extract metadata
                        entry_metadata = entry.get('metadata', {})
                        if not entry_metadata:
                            # Try using the entire entry as metadata (excluding known keys)
                            entry_metadata = {k: v for k, v in entry.items() if k not in ['step_name', 'item_id']}

                        if dry_run:
                            self.console.print(f"[blue]Would import {entry_step}: {list(entry_metadata.keys())}[/blue]")
                        else:
                            # Import metadata
                            success = metadata_api.save_step_metadata(
                                item_id=item_id,
                                step_name=entry_step,
                                metadata=entry_metadata,
                                version=1
                            )

                            if success:
                                entries_imported += 1
                            else:
                                self.console.print(f"[yellow]⚠️  Line {line_num}: Failed to import metadata[/yellow]")

                    except json.JSONDecodeError as e:
                        self.console.print(f"[yellow]⚠️  Line {line_num}: Invalid JSON - {e}[/yellow]")
                    except Exception as e:
                        self.console.print(f"[yellow]⚠️  Line {line_num}: Error - {e}[/yellow]")

            if dry_run:
                self.console.print(f"\n[blue]Dry run complete. Would import {entries_imported} entries.[/blue]")
            else:
                self.console.print(f"[green]✅ Imported {entries_imported} metadata entries for item '{item.name}'[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to import metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _metadata_history(self, item_id: str, step: str, json_output: bool):
        """Show version history for item metadata"""
        logger.warning("DEPRECATED: metadata-history command uses old metadata_api.")
        self.console.print("[yellow]⚠️  DEPRECATED: This command uses the old metadata system[/yellow]\n")
        try:
            # Get item first
            item = await self.library_manager.get_item(item_id)
            if not item:
                self.console.print(f"[red]Item not found: {item_id}[/red]")
                return

            metadata_api = self.library_manager.metadata_api

            # Get history
            history = metadata_api.get_metadata_history(item_id, step)
            if not history:
                self.console.print(f"[yellow]No version history found for {step} on item {item_id}[/yellow]")
                return

            # Output results
            if json_output:
                output = {
                    "item_id": item_id,
                    "item_name": item.name,
                    "step": step,
                    "history": history
                }
                self.console.print(json.dumps(output, indent=2, default=str))
            else:
                self.console.print(f"\n[bold cyan]Version History for '{step}' on '{item.name}':[/bold cyan]\n")

                # Create table
                table = Table()
                table.add_column("Version", style="cyan", justify="right")
                table.add_column("Changed At", style="magenta")
                table.add_column("Changed By", style="green")
                table.add_column("Reason", style="yellow")
                table.add_column("Fields", style="blue")

                for version_data in history:
                    metadata_snapshot = version_data.get('metadata', {})
                    field_list = ', '.join(metadata_snapshot.keys()) if metadata_snapshot else "N/A"

                    table.add_row(
                        str(version_data.get('version', '?')),
                        version_data.get('changed_at', 'N/A'),
                        version_data.get('changed_by', 'N/A'),
                        version_data.get('change_reason', 'N/A'),
                        field_list
                    )

                self.console.print(table)
                self.console.print(f"\n[green]Found {len(history)} version(s)[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to show metadata history: {e}[/red]")
            import traceback
            traceback.print_exc()

    def _parse_filters(self, filters: List[str]) -> dict:
        """Parse filter strings into query format

        Supports:
        - Simple equality: "step.field=value"
        - Comparison: "step.field>=value", "step.field<value"
        """
        parsed = {}

        for filter_str in filters:
            try:
                # Check for comparison operators
                if ">=" in filter_str:
                    key, value = filter_str.split(">=", 1)
                    parsed[key.strip()] = {"$gte": self._parse_value(value.strip())}
                elif "<=" in filter_str:
                    key, value = filter_str.split("<=", 1)
                    parsed[key.strip()] = {"$lte": self._parse_value(value.strip())}
                elif ">" in filter_str:
                    key, value = filter_str.split(">", 1)
                    parsed[key.strip()] = {"$gt": self._parse_value(value.strip())}
                elif "<" in filter_str:
                    key, value = filter_str.split("<", 1)
                    parsed[key.strip()] = {"$lt": self._parse_value(value.strip())}
                elif "!=" in filter_str:
                    key, value = filter_str.split("!=", 1)
                    parsed[key.strip()] = {"$ne": self._parse_value(value.strip())}
                elif "=" in filter_str:
                    key, value = filter_str.split("=", 1)
                    parsed[key.strip()] = self._parse_value(value.strip())
                else:
                    self.console.print(f"[yellow]⚠️  Invalid filter format: {filter_str}[/yellow]")
                    continue

            except Exception as e:
                self.console.print(f"[yellow]⚠️  Failed to parse filter '{filter_str}': {e}[/yellow]")
                continue

        return parsed

    def _parse_value(self, value_str: str):
        """Parse a value string into appropriate type"""
        # Try to parse as number
        try:
            if '.' in value_str:
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            # Try to parse as boolean
            if value_str.lower() == 'true':
                return True
            elif value_str.lower() == 'false':
                return False
            # Return as string
            return value_str
