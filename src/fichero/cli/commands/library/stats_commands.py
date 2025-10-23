"""
Library Statistics and Utility Commands

Commands for library statistics, scanning, and utility operations.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from .base import BaseLibraryCommands


class StatsCommands(BaseLibraryCommands):
    """Library statistics and utility operations"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize stats commands - optionally share base instance"""
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
        """Register stats and utility commands"""
        
        @app.command(name="stats", help="Show library statistics")
        def show_stats():
            """Show library statistics"""
            asyncio.run(self._show_stats())
        
        @app.command(name="scan", help="Scan external collections for availability")
        def scan_external():
            """Scan external collections for availability"""
            asyncio.run(self._scan_external())
        
        @app.command(name="update", help="Update collection metadata")
        def update_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to update"),
            metadata: str = typer.Option(None, "--metadata", "-m", help="JSON metadata to update"),
            description: str = typer.Option(None, "--description", "-d", help="New description")
        ):
            """Update collection metadata"""
            asyncio.run(self._update_collection(collection_id, metadata, description))
        
        @app.command(name="add-result", help="Add processing result to an item")
        def add_processing_result(
            item_id: str = typer.Argument(..., help="ID of the item"),
            workflow: str = typer.Argument(..., help="Workflow name"),
            status: str = typer.Argument(..., help="Status: success, failed, partial"),
            output_paths: str = typer.Option(None, "--outputs", "-o", help="Comma-separated output paths"),
            logs_path: str = typer.Option(None, "--logs", "-l", help="Path to logs")
        ):
            """Add processing result to an item"""
            asyncio.run(self._add_processing_result(item_id, workflow, status, output_paths, logs_path))
    
    async def _show_stats(self):
        """Show library statistics"""
        try:
            # Get library stats
            stats = await self.library_manager.get_library_stats()
            
            # Create stats table
            table = Table(title="Library Statistics")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_column("Description", style="yellow")
            
            # Collections
            table.add_row("Total Collections", str(stats.get('total_collections', 0)), "Number of collections in library")
            table.add_row("Local Collections", str(stats.get('local_collections', 0)), "Collections stored locally")
            table.add_row("External Collections", str(stats.get('external_collections', 0)), "Collections referencing external paths")
            table.add_row("URL Collections", str(stats.get('url_collections', 0)), "Collections referencing URLs")
            
            # Items
            table.add_row("Total Items", str(stats.get('total_items', 0)), "Number of items across all collections")
            table.add_row("File Items", str(stats.get('file_items', 0)), "Individual file items")
            table.add_row("Folder Items", str(stats.get('folder_items', 0)), "Folder items")
            table.add_row("URL Items", str(stats.get('url_items', 0)), "URL items")
            
            # Processing
            table.add_row("Processing Results", str(stats.get('total_results', 0)), "Total processing results")
            table.add_row("Successful Results", str(stats.get('successful_results', 0)), "Successfully processed items")
            table.add_row("Failed Results", str(stats.get('failed_results', 0)), "Failed processing results")
            table.add_row("Partial Results", str(stats.get('partial_results', 0)), "Partially processed items")
            
            # Storage
            table.add_row("Library Size", stats.get('library_size', 'N/A'), "Total size of library data")
            table.add_row("Database Size", stats.get('database_size', 'N/A'), "Size of SQLite database")
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to show stats: {e}[/red]")
    
    async def _scan_external(self):
        """Scan external collections for availability"""
        try:
            # Scan external collections
            scan_results = await self.library_manager.scan_external_collections()
            
            if not scan_results:
                self.console.print("[yellow]No external collections found[/yellow]")
                return
            
            # Create scan results table
            table = Table(title="External Collection Availability Scan")
            table.add_column("Collection ID", style="cyan", no_wrap=True)
            table.add_column("Path", style="blue")
            table.add_column("Status", style="red")
            table.add_column("Last Seen", style="yellow")
            
            for collection_id, status in scan_results.items():
                # Get collection name
                collection = await self.get_collection_by_id(collection_id)
                collection_name = collection.name if collection else "Unknown"
                
                # Determine status icon
                if status == "available":
                    status_icon = "✅ Available"
                elif status == "unmounted":
                    status_icon = "❌ Unmounted"
                else:
                    status_icon = "⚠️ Error"
                
                table.add_row(
                    collection_id,
                    collection_name,
                    status_icon,
                    "N/A"  # Last seen not available in current implementation
                )
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to scan external collections: {e}[/red]")
    
    async def _update_collection(self, collection_id: str, metadata: Optional[str], description: Optional[str]):
        """Update collection metadata"""
        try:
            # Get collection first
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Prepare updates
            updates = {}
            
            # Update description
            if description:
                if 'metadata' not in collection.metadata:
                    collection.metadata = {}
                collection.metadata['description'] = description
                updates['metadata'] = collection.metadata
            
            # Update metadata
            if metadata:
                try:
                    parsed_metadata = json.loads(metadata)
                    if 'metadata' not in collection.metadata:
                        collection.metadata = {}
                    collection.metadata.update(parsed_metadata)
                    updates['metadata'] = collection.metadata
                except json.JSONDecodeError:
                    self.console.print("[red]Invalid JSON metadata format[/red]")
                    return
            
            # Update collection
            if updates:
                success = await self.library_manager.update_collection(collection_id, **updates)
                if success:
                    self.console.print(f"[green]✅ Collection '{collection.name}' updated successfully[/green]")
                else:
                    self.console.print(f"[red]❌ Failed to update collection[/red]")
            else:
                self.console.print("[yellow]No updates specified[/yellow]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to update collection: {e}[/red]")
    
    async def _add_processing_result(self, item_id: str, workflow: str, status: str, output_paths: Optional[str], logs_path: Optional[str]):
        """Add processing result to an item"""
        try:
            # Validate status
            valid_statuses = ["success", "failed", "partial"]
            if status not in valid_statuses:
                self.console.print(f"[red]Invalid status. Choose from: {', '.join(valid_statuses)}[/red]")
                return
            
            # Parse output paths
            output_paths_list = None
            if output_paths:
                output_paths_list = [path.strip() for path in output_paths.split(',')]
            
            # Add processing result
            result_id = await self.library_manager.add_processing_result(
                item_id=item_id,
                workflow=workflow,
                status=status,
                output_paths=output_paths_list,
                logs_path=logs_path
            )
            
            if result_id:
                self.console.print(f"[green]✅ Processing result added successfully with ID: {result_id}[/green]")
            else:
                self.console.print(f"[red]❌ Failed to add processing result[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to add processing result: {e}[/red]")
