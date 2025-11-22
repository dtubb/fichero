"""
Bulk Metadata Operations Commands

Commands for bulk operations on metadata: export, import, update, delete, versioning.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .base import BaseLibraryCommands


class BulkMetadataCommands(BaseLibraryCommands):
    """Bulk metadata operations"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize bulk metadata commands - optionally share base instance"""
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
        """Register bulk metadata commands"""

        @app.command(name="bulk-export-metadata", help="Export all metadata for a collection to JSON")
        def bulk_export_metadata(
            collection_id: str = typer.Argument(..., help="Collection ID"),
            output_file: str = typer.Argument(..., help="Output JSON file path"),
            schema_type: Optional[List[str]] = typer.Option(None, "--schema", "-s", help="Filter by schema type"),
            source_label: Optional[List[str]] = typer.Option(None, "--source", "-l", help="Filter by source label"),
            include_versions: bool = typer.Option(False, "--versions", help="Include all versions (not just latest)"),
            pretty: bool = typer.Option(True, "--pretty/--compact", help="Pretty-print JSON")
        ):
            """
            Export all metadata for a collection to JSON file

            Output format:
                {
                    "collection_id": "...",
                    "exported_at": "...",
                    "items": [
                        {
                            "item_id": "...",
                            "metadata": {
                                "schema_type": "transcription",
                                "source_label": "ai_qwen",
                                "version": 1,
                                "data": {...}
                            }
                        }
                    ]
                }

            Examples:
                # Export all metadata
                fichero library bulk-export-metadata <collection_id> export.json

                # Export only transcriptions
                fichero library bulk-export-metadata <collection_id> transcriptions.json --schema transcription

                # Export with version history
                fichero library bulk-export-metadata <collection_id> full.json --versions
            """
            asyncio.run(self._bulk_export_metadata(
                collection_id, output_file, schema_type, source_label,
                include_versions, pretty
            ))

        @app.command(name="bulk-import-metadata", help="Import metadata from JSON file")
        def bulk_import_metadata(
            input_file: str = typer.Argument(..., help="Input JSON file path"),
            collection_id: Optional[str] = typer.Option(None, "--collection", "-c", help="Target collection (overrides file)"),
            dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be imported without importing"),
            skip_existing: bool = typer.Option(False, "--skip-existing", help="Skip items that already have metadata"),
            increment_versions: bool = typer.Option(True, "--increment-versions/--keep-versions", help="Auto-increment versions")
        ):
            """
            Import metadata from JSON file (exported via bulk-export-metadata)

            Examples:
                # Import metadata
                fichero library bulk-import-metadata export.json

                # Dry run to preview
                fichero library bulk-import-metadata export.json --dry-run

                # Import to different collection
                fichero library bulk-import-metadata export.json --collection <new_id>

                # Skip items that already have metadata
                fichero library bulk-import-metadata export.json --skip-existing
            """
            asyncio.run(self._bulk_import_metadata(
                input_file, collection_id, dry_run, skip_existing, increment_versions
            ))

        @app.command(name="bulk-update-source", help="Update source label for metadata in bulk")
        def bulk_update_source(
            collection_id: str = typer.Argument(..., help="Collection ID"),
            old_source: str = typer.Argument(..., help="Current source label to replace"),
            new_source: str = typer.Argument(..., help="New source label"),
            schema_type: Optional[List[str]] = typer.Option(None, "--schema", "-s", help="Filter by schema type"),
            dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be updated"),
            force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")
        ):
            """
            Update source labels for metadata in bulk

            Useful for:
                - Renaming AI model labels (e.g., ai_qwen -> ai_qwen_v2)
                - Marking corrected metadata (e.g., ai_gpt -> human_corrected)

            Examples:
                # Rename source label
                fichero library bulk-update-source <collection_id> ai_qwen ai_qwen_v2

                # Mark transcriptions as human-corrected
                fichero library bulk-update-source <collection_id> ai_gpt human_corrected --schema transcription
            """
            asyncio.run(self._bulk_update_source(
                collection_id, old_source, new_source, schema_type, dry_run, force
            ))

        @app.command(name="bulk-delete-metadata", help="Delete metadata in bulk")
        def bulk_delete_metadata(
            collection_id: str = typer.Argument(..., help="Collection ID"),
            schema_type: Optional[List[str]] = typer.Option(None, "--schema", "-s", help="Filter by schema type"),
            source_label: Optional[List[str]] = typer.Option(None, "--source", "-l", help="Filter by source label"),
            version: Optional[int] = typer.Option(None, "--version", "-v", help="Delete specific version only"),
            dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted"),
            force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")
        ):
            """
            Delete metadata in bulk with filters

            WARNING: This is destructive. Use --dry-run first.

            Examples:
                # Delete all transcriptions from specific source
                fichero library bulk-delete-metadata <collection_id> --schema transcription --source ai_qwen --dry-run

                # Delete specific version
                fichero library bulk-delete-metadata <collection_id> --version 1 --dry-run

                # Delete everything (dangerous!)
                fichero library bulk-delete-metadata <collection_id> --force
            """
            asyncio.run(self._bulk_delete_metadata(
                collection_id, schema_type, source_label, version, dry_run, force
            ))

        @app.command(name="bulk-reindex", help="Rebuild search index for collection")
        def bulk_reindex(
            collection_id: Optional[str] = typer.Option(None, "--collection", "-c", help="Collection ID (omit for all)"),
            force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")
        ):
            """
            Rebuild search index for metadata

            This will:
                - Clear existing search index entries
                - Re-index all searchable metadata (transcriptions, catalogues, translations)
                - Update search statistics

            Examples:
                # Reindex specific collection
                fichero library bulk-reindex --collection <collection_id>

                # Reindex entire library
                fichero library bulk-reindex --force
            """
            asyncio.run(self._bulk_reindex(collection_id, force))

        @app.command(name="bulk-validate", help="Validate all metadata against schemas")
        def bulk_validate(
            collection_id: str = typer.Argument(..., help="Collection ID"),
            schema_type: Optional[List[str]] = typer.Option(None, "--schema", "-s", help="Filter by schema type"),
            fix_errors: bool = typer.Option(False, "--fix", help="Attempt to fix validation errors"),
            json_output: bool = typer.Option(False, "--json", help="Output as JSON")
        ):
            """
            Validate all metadata against schema definitions

            Checks for:
                - Missing required fields
                - Invalid field types
                - Out-of-range values
                - Pattern mismatches

            Examples:
                # Validate all metadata
                fichero library bulk-validate <collection_id>

                # Validate specific schema
                fichero library bulk-validate <collection_id> --schema transcription

                # Validate and attempt fixes
                fichero library bulk-validate <collection_id> --fix
            """
            asyncio.run(self._bulk_validate(collection_id, schema_type, fix_errors, json_output))

        @app.command(name="bulk-merge-versions", help="Merge metadata versions with conflict resolution")
        def bulk_merge_versions(
            collection_id: str = typer.Argument(..., help="Collection ID"),
            schema_type: str = typer.Argument(..., help="Schema type to merge"),
            strategy: str = typer.Option("newest", "--strategy", help="Merge strategy (newest, highest_confidence, manual)"),
            dry_run: bool = typer.Option(False, "--dry-run", help="Show merge preview")
        ):
            """
            Merge multiple versions of metadata into single version

            Strategies:
                - newest: Use most recent version
                - highest_confidence: Use version with highest confidence score
                - manual: Interactive resolution (not yet implemented)

            Examples:
                # Merge transcription versions, keeping newest
                fichero library bulk-merge-versions <collection_id> transcription --strategy newest

                # Preview merge
                fichero library bulk-merge-versions <collection_id> catalogue --dry-run
            """
            asyncio.run(self._bulk_merge_versions(collection_id, schema_type, strategy, dry_run))

    async def _bulk_export_metadata(
        self,
        collection_id: str,
        output_file: str,
        schema_types: Optional[List[str]],
        source_labels: Optional[List[str]],
        include_versions: bool,
        pretty: bool
    ):
        """Export all metadata for a collection"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            self.console.print(f"[blue]Exporting metadata from collection '{collection.name}'...[/blue]")

            # Get all items
            items = await self.library_manager.get_collection_items(collection_id)
            if not items:
                self.console.print("[yellow]No items found in collection[/yellow]")
                return

            export_data = {
                "collection_id": collection_id,
                "collection_name": collection.name,
                "exported_at": asyncio.get_event_loop().time(),
                "filters": {
                    "schema_types": schema_types,
                    "source_labels": source_labels,
                    "include_versions": include_versions
                },
                "items": []
            }

            items_with_metadata = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Exporting...", total=len(items))

                for item in items:
                    # Get metadata from storage using new schema
                    metadata_list = self.library_manager.storage.get_metadata_by_collection(
                        collection_id,
                        schema_type=None  # Get all types, we'll filter later
                    )

                    # Filter by item
                    item_metadata = [m for m in metadata_list if m.item_id == str(item.id)]

                    # Apply filters
                    if schema_types:
                        item_metadata = [m for m in item_metadata if m.schema_type in schema_types]
                    if source_labels:
                        item_metadata = [m for m in item_metadata if m.source_label in source_labels]

                    if item_metadata:
                        items_with_metadata += 1

                        # Group by schema_type, source_label, version
                        grouped = {}
                        for meta in item_metadata:
                            key = (meta.schema_type, meta.source_label, meta.version)
                            if key not in grouped:
                                grouped[key] = []
                            grouped[key].append(meta)

                        # Build metadata structure
                        metadata_entries = []
                        for (schema, source, version), entries in grouped.items():
                            # Reconstruct metadata dict from individual entries
                            data = {}
                            for entry in entries:
                                # Handle custom_fields if present
                                if entry.custom_fields:
                                    data.update(entry.custom_fields)
                                data[entry.key] = entry.value

                            metadata_entries.append({
                                "schema_type": schema,
                                "source_label": source,
                                "version": version,
                                "schema_version": entries[0].schema_version if entries else 1,
                                "data": data,
                                "created_at": entries[0].created_at.isoformat() if entries and entries[0].created_at else None
                            })

                        export_data["items"].append({
                            "item_id": str(item.id),
                            "item_name": item.name,
                            "metadata": metadata_entries
                        })

                    progress.advance(task)

            # Write to file
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w') as f:
                if pretty:
                    json.dump(export_data, f, indent=2)
                else:
                    json.dump(export_data, f)

            self.console.print(
                f"[green]✅ Exported metadata for {items_with_metadata}/{len(items)} item(s) to {output_file}[/green]"
            )

        except Exception as e:
            self.console.print(f"[red]Failed to export metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _bulk_import_metadata(
        self,
        input_file: str,
        collection_id: Optional[str],
        dry_run: bool,
        skip_existing: bool,
        increment_versions: bool
    ):
        """Import metadata from JSON file"""
        try:
            # Read input file
            input_path = Path(input_file)
            if not input_path.exists():
                self.console.print(f"[red]File not found: {input_file}[/red]")
                return

            with open(input_path, 'r') as f:
                import_data = json.load(f)

            # Use collection from file or override
            target_collection_id = collection_id or import_data.get("collection_id")
            if not target_collection_id:
                self.console.print("[red]No collection ID specified[/red]")
                return

            # Verify collection exists
            collection = await self.get_collection_by_id(target_collection_id)
            if not collection:
                return

            items_data = import_data.get("items", [])
            if not items_data:
                self.console.print("[yellow]No items found in import file[/yellow]")
                return

            if dry_run:
                self.console.print(f"[blue]Dry run: Would import metadata for {len(items_data)} items[/blue]\n")

            imported_count = 0
            skipped_count = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console
            ) as progress:
                task = progress.add_task("Importing..." if not dry_run else "Previewing...", total=len(items_data))

                for item_data in items_data:
                    item_id = item_data.get("item_id")
                    metadata_entries = item_data.get("metadata", [])

                    # Check if item exists
                    item = await self.library_manager.get_item(item_id)
                    if not item:
                        self.console.print(f"[yellow]⚠️  Item not found: {item_id}, skipping[/yellow]")
                        skipped_count += 1
                        progress.advance(task)
                        continue

                    # Check for existing metadata if skip_existing
                    if skip_existing:
                        existing = self.library_manager.storage.get_metadata_by_collection(
                            target_collection_id
                        )
                        if any(m.item_id == item_id for m in existing):
                            skipped_count += 1
                            progress.advance(task)
                            continue

                    # Import each metadata entry
                    for meta_entry in metadata_entries:
                        schema_type = meta_entry.get("schema_type")
                        source_label = meta_entry.get("source_label")
                        version = meta_entry.get("version", 1)
                        data = meta_entry.get("data", {})

                        if increment_versions:
                            # Get latest version for this schema/source
                            latest = self.library_manager.storage.get_metadata_by_collection(
                                target_collection_id,
                                schema_type=schema_type
                            )
                            latest_for_item = [m for m in latest if m.item_id == item_id and m.source_label == source_label]
                            if latest_for_item:
                                max_version = max(m.version for m in latest_for_item)
                                version = max_version + 1

                        if dry_run:
                            self.console.print(
                                f"[dim]Would import {schema_type} v{version} from {source_label} for {item.name}[/dim]"
                            )
                        else:
                            # Create ExtractedMetadata objects
                            from fichero.library.models import ExtractedMetadata
                            from datetime import datetime

                            # Store each field
                            for key, value in data.items():
                                metadata = ExtractedMetadata(
                                    processing_output_id=f"bulk-import-{item_id}",
                                    collection_id=target_collection_id,
                                    item_id=item_id,
                                    schema_type=schema_type,
                                    source_label=source_label,
                                    version=version,
                                    key=key,
                                    value=str(value),
                                    created_at=datetime.now()
                                )
                                self.library_manager.storage.add_extracted_metadata(metadata)

                    imported_count += 1
                    progress.advance(task)

            if dry_run:
                self.console.print(
                    f"\n[blue]Dry run complete. Would import {imported_count} items, skip {skipped_count}.[/blue]"
                )
            else:
                self.console.print(
                    f"[green]✅ Imported metadata for {imported_count} items (skipped {skipped_count})[/green]"
                )

        except Exception as e:
            self.console.print(f"[red]Failed to import metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _bulk_update_source(
        self,
        collection_id: str,
        old_source: str,
        new_source: str,
        schema_types: Optional[List[str]],
        dry_run: bool,
        force: bool
    ):
        """Update source labels in bulk"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Get metadata
            all_metadata = self.library_manager.storage.get_metadata_by_collection(collection_id)

            # Filter
            to_update = [m for m in all_metadata if m.source_label == old_source]
            if schema_types:
                to_update = [m for m in to_update if m.schema_type in schema_types]

            if not to_update:
                self.console.print(f"[yellow]No metadata found with source '{old_source}'[/yellow]")
                return

            self.console.print(f"[yellow]Found {len(to_update)} metadata entries to update[/yellow]")

            if not force and not dry_run:
                response = typer.confirm(f"Update source from '{old_source}' to '{new_source}'?")
                if not response:
                    self.console.print("[blue]Update cancelled[/blue]")
                    return

            if dry_run:
                self.console.print(f"[blue]Dry run: Would update {len(to_update)} entries[/blue]")
                # Show sample
                for meta in to_update[:5]:
                    self.console.print(f"  {meta.schema_type}.{meta.key} v{meta.version}")
                if len(to_update) > 5:
                    self.console.print(f"  ... and {len(to_update) - 5} more")
            else:
                updated = 0
                for meta in to_update:
                    meta.source_label = new_source
                    # Update in database
                    if self.library_manager.storage.update_extracted_metadata(meta):
                        updated += 1

                self.console.print(f"[green]✅ Updated {updated} metadata entries[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to update source labels: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _bulk_delete_metadata(
        self,
        collection_id: str,
        schema_types: Optional[List[str]],
        source_labels: Optional[List[str]],
        version: Optional[int],
        dry_run: bool,
        force: bool
    ):
        """Delete metadata in bulk"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Get metadata
            all_metadata = self.library_manager.storage.get_metadata_by_collection(collection_id)

            # Apply filters
            to_delete = all_metadata
            if schema_types:
                to_delete = [m for m in to_delete if m.schema_type in schema_types]
            if source_labels:
                to_delete = [m for m in to_delete if m.source_label in source_labels]
            if version is not None:
                to_delete = [m for m in to_delete if m.version == version]

            if not to_delete:
                self.console.print("[yellow]No metadata found matching filters[/yellow]")
                return

            self.console.print(f"[red]⚠️  Found {len(to_delete)} metadata entries to delete[/red]")

            if not force and not dry_run:
                response = typer.confirm("This is destructive. Continue?")
                if not response:
                    self.console.print("[blue]Delete cancelled[/blue]")
                    return

            if dry_run:
                self.console.print(f"[blue]Dry run: Would delete {len(to_delete)} entries[/blue]")
                # Show sample
                for meta in to_delete[:5]:
                    self.console.print(f"  {meta.schema_type}.{meta.key} ({meta.source_label} v{meta.version})")
                if len(to_delete) > 5:
                    self.console.print(f"  ... and {len(to_delete) - 5} more")
            else:
                deleted = 0
                for meta in to_delete:
                    if self.library_manager.storage.delete_extracted_metadata(meta.id):
                        deleted += 1

                self.console.print(f"[green]✅ Deleted {deleted} metadata entries[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to delete metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _bulk_reindex(self, collection_id: Optional[str], force: bool):
        """Rebuild search index"""
        try:
            scope = f"collection {collection_id}" if collection_id else "entire library"

            if not force:
                response = typer.confirm(f"Rebuild search index for {scope}?")
                if not response:
                    self.console.print("[blue]Reindex cancelled[/blue]")
                    return

            self.console.print(f"[blue]Rebuilding search index for {scope}...[/blue]")

            success = self.library_manager.rebuild_search_index(collection_id)

            if success:
                stats = self.library_manager.get_search_stats()
                self.console.print(
                    f"[green]✅ Reindexed {stats.get('total_documents', 0)} documents[/green]"
                )
            else:
                self.console.print("[red]❌ Failed to rebuild index[/red]")

        except Exception as e:
            self.console.print(f"[red]Failed to reindex: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _bulk_validate(
        self,
        collection_id: str,
        schema_types: Optional[List[str]],
        fix_errors: bool,
        json_output: bool
    ):
        """Validate all metadata against schemas"""
        try:
            from fichero.library.metadata_validator import validate_metadata

            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Get all metadata
            all_metadata = self.library_manager.storage.get_metadata_by_collection(collection_id)

            # Filter
            if schema_types:
                all_metadata = [m for m in all_metadata if m.schema_type in schema_types]

            if not all_metadata:
                self.console.print("[yellow]No metadata found[/yellow]")
                return

            self.console.print(f"[blue]Validating {len(all_metadata)} metadata entries...[/blue]")

            errors = []
            warnings = []
            valid_count = 0

            # Group by item/schema/source/version for validation
            grouped = {}
            for meta in all_metadata:
                key = (meta.item_id, meta.schema_type, meta.source_label, meta.version)
                if key not in grouped:
                    grouped[key] = {}
                grouped[key][meta.key] = meta.value

            for (item_id, schema_type, source_label, version), data in grouped.items():
                result = validate_metadata(schema_type, data)

                if result.is_valid:
                    valid_count += 1
                else:
                    for error in result.errors:
                        errors.append({
                            "item_id": item_id,
                            "schema_type": schema_type,
                            "source_label": source_label,
                            "version": version,
                            "error": error
                        })

                for warning in result.warnings:
                    warnings.append({
                        "item_id": item_id,
                        "schema_type": schema_type,
                        "source_label": source_label,
                        "version": version,
                        "warning": warning
                    })

            # Output results
            if json_output:
                output = {
                    "total": len(grouped),
                    "valid": valid_count,
                    "errors": errors,
                    "warnings": warnings
                }
                self.console.print(json.dumps(output, indent=2))
            else:
                self.console.print(f"\n[bold cyan]Validation Results:[/bold cyan]")
                self.console.print(f"Total: {len(grouped)}")
                self.console.print(f"Valid: [green]{valid_count}[/green]")
                self.console.print(f"Errors: [red]{len(errors)}[/red]")
                self.console.print(f"Warnings: [yellow]{len(warnings)}[/yellow]\n")

                if errors:
                    table = Table(title="Validation Errors")
                    table.add_column("Item ID", style="cyan")
                    table.add_column("Schema", style="magenta")
                    table.add_column("Source", style="green")
                    table.add_column("Error", style="red")

                    for error in errors[:20]:  # Show first 20
                        table.add_row(
                            error["item_id"][:8],
                            error["schema_type"],
                            error["source_label"],
                            error["error"]
                        )

                    self.console.print(table)

                    if len(errors) > 20:
                        self.console.print(f"[dim]... and {len(errors) - 20} more errors[/dim]")

        except Exception as e:
            self.console.print(f"[red]Failed to validate metadata: {e}[/red]")
            import traceback
            traceback.print_exc()

    async def _bulk_merge_versions(
        self,
        collection_id: str,
        schema_type: str,
        strategy: str,
        dry_run: bool
    ):
        """Merge metadata versions"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            self.console.print(
                f"[blue]Merging {schema_type} versions using '{strategy}' strategy...[/blue]"
            )

            # Get all metadata for this schema
            all_metadata = self.library_manager.storage.get_metadata_by_collection(
                collection_id,
                schema_type=schema_type
            )

            if not all_metadata:
                self.console.print(f"[yellow]No {schema_type} metadata found[/yellow]")
                return

            # Group by item and source
            grouped = {}
            for meta in all_metadata:
                key = (meta.item_id, meta.source_label)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(meta)

            # Find items with multiple versions
            multi_version_items = {k: v for k, v in grouped.items() if len(set(m.version for m in v)) > 1}

            if not multi_version_items:
                self.console.print(f"[yellow]No items found with multiple versions[/yellow]")
                return

            self.console.print(f"Found {len(multi_version_items)} items with multiple versions")

            merged_count = 0

            for (item_id, source_label), versions in multi_version_items.items():
                # Apply merge strategy
                if strategy == "newest":
                    # Keep latest created_at
                    winner = max(versions, key=lambda m: m.created_at)
                elif strategy == "highest_confidence":
                    # Keep highest confidence (if available)
                    with_confidence = [m for m in versions if m.confidence is not None]
                    if with_confidence:
                        winner = max(with_confidence, key=lambda m: m.confidence)
                    else:
                        winner = max(versions, key=lambda m: m.created_at)
                else:
                    self.console.print(f"[red]Unknown strategy: {strategy}[/red]")
                    return

                if dry_run:
                    self.console.print(
                        f"[dim]Would keep version {winner.version} for item {item_id} ({source_label})[/dim]"
                    )
                else:
                    # Delete other versions
                    for meta in versions:
                        if meta.id != winner.id:
                            self.library_manager.storage.delete_extracted_metadata(meta.id)

                    merged_count += 1

            if dry_run:
                self.console.print(f"\n[blue]Dry run complete. Would merge {len(multi_version_items)} items.[/blue]")
            else:
                self.console.print(f"[green]✅ Merged versions for {merged_count} items[/green]")

        except Exception as e:
            self.console.print(f"[red]Failed to merge versions: {e}[/red]")
            import traceback
            traceback.print_exc()
