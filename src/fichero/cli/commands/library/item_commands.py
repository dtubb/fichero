"""
Item Management Commands

Commands for managing individual items within collections.
"""

import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from .base import BaseLibraryCommands


class ItemCommands(BaseLibraryCommands):
    """Item management operations"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize item commands - optionally share base instance"""
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
        """Register item management commands"""
        
        @app.command(name="items", help="List items in a collection")
        def list_items(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            show_details: bool = typer.Option(False, "--details", "-d", help="Show detailed item information")
        ):
            """List items in a collection"""
            asyncio.run(self._list_items(collection_id, show_details))
        
        @app.command(name="add-item", help="Add an item to a collection")
        def add_item(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            item_type: str = typer.Argument(..., help="Type of item: file, folder, url, camera, audio"),
            source: str = typer.Argument(..., help="Source path or URL"),
            name: str = typer.Option(None, "--name", "-n", help="Name for the item"),
            operation: str = typer.Option("link", "--operation", "-o", help="Operation: link, copy, move")
        ):
            """Add an item to a collection"""
            asyncio.run(self._add_item(collection_id, item_type, source, name, operation))
        
        @app.command(name="remove-item", help="Remove an item from a collection")
        def remove_item(
            item_id: str = typer.Argument(..., help="ID of the item to remove")
        ):
            """Remove an item from a collection"""
            asyncio.run(self._remove_item(item_id))
        
        @app.command(name="update-item", help="Update item status or metadata")
        def update_item(
            item_id: str = typer.Argument(..., help="ID of the item to update"),
            status: str = typer.Option(None, "--status", "-s", help="New status: pending, processing, completed, error"),
            metadata: str = typer.Option(None, "--metadata", "-m", help="JSON metadata to update")
        ):
            """Update item status or metadata"""
            asyncio.run(self._update_item(item_id, status, metadata))
        
        @app.command(name="history", help="Show processing history for an item")
        def show_history(
            item_id: str = typer.Argument(..., help="ID of the item"),
            show_details: bool = typer.Option(False, "--details", "-d", help="Show detailed history")
        ):
            """Show processing history for an item"""
            asyncio.run(self._show_history(item_id, show_details))
    
    async def _list_items(self, collection_id: str, show_details: bool):
        """List items in a collection"""
        try:
            # Get collection first
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Get items
            items = await self.library_manager.get_collection_items(collection_id)
            
            if not items:
                self.console.print(f"[yellow]No items found in collection '{collection.name}'[/yellow]")
                return
            
            # Create table
            table = Table(title=f"Items in Collection: {collection.name}")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="magenta")
            table.add_column("Type", style="green")
            table.add_column("Status", style="red")
            table.add_column("Source", style="blue")
            
            if show_details:
                table.add_column("Created", style="yellow")
                table.add_column("Updated", style="yellow")
                table.add_column("Storage", style="cyan")
            
            for item in items:
                if show_details:
                    table.add_row(
                        str(item.id),
                        item.name,
                        item.type,
                        item.status,
                        item.source_path or "N/A",
                        item.created_at.strftime("%Y-%m-%d %H:%M"),
                        item.updated_at.strftime("%Y-%m-%d %H:%M"),
                        item.storage_type
                    )
                else:
                    table.add_row(
                        str(item.id),
                        item.name,
                        item.type,
                        item.status,
                        item.source_path or "N/A"
                    )
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to list items: {e}[/red]")
    
    async def _add_item(self, collection_id: str, item_type: str, source: str, name: Optional[str], operation: str):
        """Add an item to a collection"""
        try:
            # Validate item type
            valid_types = ["file", "folder", "url", "camera", "audio"]
            if item_type not in valid_types:
                self.console.print(f"[red]Invalid item type. Choose from: {', '.join(valid_types)}[/red]")
                return
            
            # Validate operation
            valid_operations = ["link", "copy", "move"]
            if operation not in valid_operations:
                self.console.print(f"[red]Invalid operation. Choose from: {', '.join(valid_operations)}[/red]")
                return
            
            # Determine item name
            if not name:
                name = Path(source).name if source else f"Item_{item_type}"
            
            # Add item
            item_id = await self.library_manager.add_item_to_collection(
                collection_id=collection_id,
                item_type=item_type,
                source=source,
                name=name,
                operation=operation
            )
            
            if item_id:
                self.console.print(f"[green]✅ Item '{name}' added successfully with ID: {item_id}[/green]")
            else:
                self.console.print(f"[red]❌ Failed to add item '{name}'[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to add item: {e}[/red]")
    
    async def _remove_item(self, item_id: str):
        """Remove an item from collection"""
        try:
            # Note: This would need to be implemented in LibraryManager
            # For now, just show that it's not implemented
            self.console.print(f"[yellow]⚠️ Remove item functionality not yet implemented[/yellow]")
            self.console.print(f"[blue]Item ID: {item_id}[/blue]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to remove item: {e}[/red]")
    
    async def _update_item(self, item_id: str, status: Optional[str], metadata: Optional[str]):
        """Update item status or metadata"""
        try:
            # Update status if provided
            if status:
                success = await self.library_manager.update_item_status(item_id, status)
                if success:
                    self.console.print(f"[green]✅ Item status updated to '{status}'[/green]")
                else:
                    self.console.print(f"[red]❌ Failed to update item status[/red]")
            
            # Update metadata if provided
            if metadata:
                # Note: This would need to be implemented in LibraryManager
                self.console.print(f"[yellow]⚠️ Metadata update not yet implemented[/yellow]")
                self.console.print(f"[blue]Metadata: {metadata}[/blue]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to update item: {e}[/red]")
    
    async def _show_history(self, item_id: str, show_details: bool):
        """Show processing history for an item"""
        try:
            # Get processing history
            history = await self.library_manager.get_processing_history(item_id)
            
            if not history:
                self.console.print(f"[yellow]No processing history found for item {item_id}[/yellow]")
                return
            
            # Create table
            table = Table(title=f"Processing History for Item {item_id}")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Workflow", style="magenta")
            table.add_column("Status", style="red")
            table.add_column("Started", style="blue")
            table.add_column("Completed", style="blue")
            
            if show_details:
                table.add_column("Backend", style="green")
                table.add_column("Time", style="yellow")
                table.add_column("Outputs", style="cyan")
            
            for result in history:
                if show_details:
                    table.add_row(
                        str(result.id),
                        result.workflow,
                        result.status,
                        result.started_at.strftime("%Y-%m-%d %H:%M") if result.started_at else "N/A",
                        result.completed_at.strftime("%Y-%m-%d %H:%M") if result.completed_at else "N/A",
                        result.llm_backend or "N/A",
                        f"{result.processing_time:.2f}s" if result.processing_time else "N/A",
                        str(len(result.output_paths))
                    )
                else:
                    table.add_row(
                        str(result.id),
                        result.workflow,
                        result.status,
                        result.started_at.strftime("%Y-%m-%d %H:%M") if result.started_at else "N/A",
                        result.completed_at.strftime("%Y-%m-%d %H:%M") if result.completed_at else "N/A"
                    )
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to show history: {e}[/red]")
