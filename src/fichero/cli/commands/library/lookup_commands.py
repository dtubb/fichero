"""
Lookup Commands for Library CLI

Commands for looking up collections and items by ID or name.
"""

import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from .base import BaseLibraryCommands

console = Console()

class LookupCommands(BaseLibraryCommands):
    """Lookup operations for collections and items"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize lookup commands - optionally share base instance"""
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
        """Register lookup commands"""
        
        @app.command(name="get-collection", help="Get collection by ID")
        def get_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to get")
        ):
            """Get collection by ID"""
            asyncio.run(self._get_collection(collection_id))
        
        @app.command(name="get-collection-by-name", help="Get collection by name")
        def get_collection_by_name(
            name: str = typer.Argument(..., help="Name of the collection to get")
        ):
            """Get collection by name"""
            asyncio.run(self._get_collection_by_name(name))
        
        @app.command(name="get-item", help="Get item by ID")
        def get_item(
            item_id: str = typer.Argument(..., help="ID of the item to get")
        ):
            """Get item by ID"""
            asyncio.run(self._get_item(item_id))
        
        @app.command(name="search-items", help="Search items across all collections")
        def search_items(
            query: str = typer.Argument(..., help="Search query"),
            item_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by item type"),
            status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status")
        ):
            """Search items across all collections"""
            asyncio.run(self._search_items(query, item_type, status))
    
    async def _get_collection(self, collection_id: str):
        """Get collection by ID"""
        try:
            collection = await self.library_manager.get_collection(collection_id)
            if not collection:
                console.print(f"[red]Collection with ID '{collection_id}' not found[/red]")
                return
            
            # Display collection details
            console.print(f"\n[bold]Collection Details[/bold]")
            console.print(f"ID: {collection.id}")
            console.print(f"Name: {collection.name}")
            console.print(f"Type: {collection.type}")
            console.print(f"Source Path: {collection.source_path}")
            console.print(f"Local Path: {collection.local_path}")
            console.print(f"Created: {collection.created_at}")
            console.print(f"Updated: {collection.updated_at}")
            
            if collection.metadata:
                console.print(f"\n[bold]Metadata:[/bold]")
                for key, value in collection.metadata.items():
                    console.print(f"  {key}: {value}")
            
        except Exception as e:
            console.print(f"[red]Failed to get collection: {e}[/red]")
    
    async def _get_collection_by_name(self, name: str):
        """Get collection by name"""
        try:
            collection = await self.library_manager.get_collection_by_name(name)
            if not collection:
                console.print(f"[red]Collection with name '{name}' not found[/red]")
                return
            
            # Display collection details
            console.print(f"\n[bold]Collection Details[/bold]")
            console.print(f"ID: {collection.id}")
            console.print(f"Name: {collection.name}")
            console.print(f"Type: {collection.type}")
            console.print(f"Source Path: {collection.source_path}")
            console.print(f"Local Path: {collection.local_path}")
            console.print(f"Created: {collection.created_at}")
            console.print(f"Updated: {collection.updated_at}")
            
            if collection.metadata:
                console.print(f"\n[bold]Metadata:[/bold]")
                for key, value in collection.metadata.items():
                    console.print(f"  {key}: {value}")
            
        except Exception as e:
            console.print(f"[red]Failed to get collection by name: {e}[/red]")
    
    async def _get_item(self, item_id: str):
        """Get item by ID"""
        try:
            # Search through all collections to find the item
            collections = await self.library_manager.get_all_collections()
            item = None
            collection = None
            
            for coll in collections:
                items = await self.library_manager.get_collection_items(coll.id)
                for itm in items:
                    if str(itm.id) == item_id:
                        item = itm
                        collection = coll
                        break
                if item:
                    break
            
            if not item:
                console.print(f"[red]Item with ID '{item_id}' not found[/red]")
                return
            
            # Display item details
            console.print(f"\n[bold]Item Details[/bold]")
            console.print(f"ID: {item.id}")
            console.print(f"Name: {item.name}")
            console.print(f"Type: {item.type}")
            console.print(f"Collection: {collection.name} ({collection.id})")
            console.print(f"Source Path: {item.source_path}")
            console.print(f"Local Path: {item.local_path}")
            console.print(f"Storage Type: {item.storage_type}")
            console.print(f"Status: {item.status}")
            console.print(f"Created: {item.created_at}")
            console.print(f"Updated: {item.updated_at}")
            
            if item.metadata:
                console.print(f"\n[bold]Metadata:[/bold]")
                for key, value in item.metadata.items():
                    console.print(f"  {key}: {value}")
            
        except Exception as e:
            console.print(f"[red]Failed to get item: {e}[/red]")
    
    async def _search_items(self, query: str, item_type: Optional[str], status: Optional[str]):
        """Search items across all collections"""
        try:
            collections = await self.library_manager.get_all_collections()
            results = []
            
            for collection in collections:
                items = await self.library_manager.get_collection_items(collection.id)
                for item in items:
                    # Check if item matches search criteria
                    matches = False
                    
                    # Text search
                    if query.lower() in item.name.lower():
                        matches = True
                    
                    # Type filter
                    if item_type and item.type != item_type:
                        matches = False
                    
                    # Status filter
                    if status and item.status != status:
                        matches = False
                    
                    if matches:
                        results.append((collection, item))
            
            if not results:
                console.print(f"[yellow]No items found matching '{query}'[/yellow]")
                return
            
            # Display results
            console.print(f"\n[bold]Search Results for '{query}' ({len(results)} items):[/bold]")
            
            table = Table()
            table.add_column("Collection", style="cyan")
            table.add_column("Item Name", style="magenta")
            table.add_column("Type", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Storage", style="blue")
            
            for collection, item in results:
                table.add_row(
                    collection.name,
                    item.name,
                    item.type,
                    item.status,
                    item.storage_type
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Failed to search items: {e}[/red]")
