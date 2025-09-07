"""
Collection CRUD Commands

Basic collection management: add, delete, rename, reorder, preview
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from .base import BaseLibraryCommands


class CollectionCommands(BaseLibraryCommands):
    """Collection CRUD operations"""
    
    def register_commands(self, app):
        """Register collection CRUD commands"""
        
        @app.command(name="list", help="List all collections with processing status")
        def list_collections():
            """List all collections with their processing status"""
            asyncio.run(self._list_collections())
        
        @app.command(name="add", help="Add a new collection to the library")
        def add_collection(
            name: str = typer.Argument(..., help="Name of the new collection"),
            collection_type: str = typer.Option("local", "--type", "-t", help="Type of the collection: local, external, url, hybrid"),
            source_path: Optional[Path] = typer.Option(None, "--source", "-s", help="Source path for external/local collections"),
            description: str = typer.Option("", "--description", "-d", help="Description of the collection"),
            metadata: Optional[str] = typer.Option(None, "--metadata", "-m", help="JSON string of additional metadata")
        ):
            """Add a new collection to the library"""
            asyncio.run(self._add_collection(name, collection_type, source_path, description, metadata))
        
        @app.command(name="delete", help="Delete a collection from the library")
        def delete_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to delete")
        ):
            """Delete a collection from the library"""
            asyncio.run(self._delete_collection(collection_id))
        
        @app.command(name="rename", help="Rename a collection")
        def rename_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to rename"),
            new_name: str = typer.Argument(..., help="New name for the collection")
        ):
            """Rename a collection"""
            asyncio.run(self._rename_collection(collection_id, new_name))
        
        @app.command(name="preview", help="Preview collection contents and processing status")
        def preview_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to preview")
        ):
            """Preview collection contents and processing status"""
            asyncio.run(self._preview_collection(collection_id))
        
        @app.command(name="reorder", help="Reorder collections")
        def reorder_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to reorder"),
            position: int = typer.Argument(..., help="New position for the collection")
        ):
            """Reorder collections"""
            asyncio.run(self._reorder_collection(collection_id, position))
    
    async def _list_collections(self):
        """List all collections with processing status"""
        try:
            # Get all collections
            collections = await self.library_manager.get_all_collections()
            
            if not collections:
                self.console.print("[yellow]No collections found in library[/yellow]")
                return
            
            # Create table with processing status
            table = Table(title="Library Collections with Processing Status")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="magenta")
            table.add_column("Type", style="green")
            table.add_column("Items", justify="right", style="yellow")
            table.add_column("Created", style="blue")
            table.add_column("Description", style="white")
            table.add_column("Processing Steps", style="red")
            
            for collection in collections:
                # Get processing status
                collection_path = Path(collection.local_path) if collection.local_path else None
                if collection_path and collection_path.exists():
                    navigator = self.get_navigator_for_collection(collection)
                    if navigator:
                        summary = navigator.get_processing_summary()
                        processing_steps = f"{len(summary['available_steps'])}/{len(summary['steps'])}"
                    else:
                        processing_steps = "N/A"
                else:
                    processing_steps = "N/A"
                
                description = collection.metadata.get('description', 'N/A')
                table.add_row(
                    str(collection.id),
                    collection.name,
                    collection.type,
                    str(len(await self.library_manager.get_collection_items(collection.id))),
                    collection.created_at.strftime("%Y-%m-%d"),
                    description,
                    processing_steps
                )
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to list collections: {e}[/red]")
    
    async def _add_collection(self, name: str, collection_type: str, source_path: Optional[Path], description: str, metadata: Optional[str]):
        """Add a new collection to the library"""
        try:
            # Parse metadata if provided
            parsed_metadata = {}
            if metadata:
                try:
                    parsed_metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    self.console.print("[red]Invalid JSON metadata format[/red]")
                    return
            
            # Add description to metadata
            if description:
                parsed_metadata['description'] = description
            
            # Convert source_path to string if it's a Path
            source_path_str = str(source_path) if source_path else None
            
            # Add collection
            collection_id = await self.library_manager.add_collection(
                name=name,
                collection_type=collection_type,
                source_path=source_path_str,
                description="",  # Empty string since Collection doesn't have description field
                metadata=parsed_metadata
            )
            
            if collection_id:
                self.console.print(f"[green]✅ Collection '{name}' added successfully with ID: {collection_id}[/green]")
            else:
                self.console.print(f"[red]❌ Failed to add collection '{name}'[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to add collection: {e}[/red]")
    
    async def _delete_collection(self, collection_id: str):
        """Delete a collection"""
        try:
            # Get collection first to confirm it exists
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Delete from library manager
            success = await self.library_manager.delete_collection(collection_id)
            
            if success:
                self.console.print(f"[green]✅ Collection '{collection.name}' deleted successfully[/green]")
            else:
                self.console.print(f"[red]❌ Failed to delete collection[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to delete collection: {e}[/red]")
    
    async def _rename_collection(self, collection_id: str, new_name: str):
        """Rename a collection"""
        try:
            # Get collection first to confirm it exists
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Update collection name
            success = await self.library_manager.update_collection(collection_id, name=new_name)
            
            if success:
                self.console.print(f"[green]✅ Collection renamed to '{new_name}' successfully[/green]")
            else:
                self.console.print(f"[red]❌ Failed to rename collection[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to rename collection: {e}[/red]")
    
    async def _preview_collection(self, collection_id: str):
        """Preview collection contents and processing status"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            self.console.print(f"\n[bold]Collection Preview: {collection.name}[/bold]")
            self.console.print(f"ID: {collection.id}")
            self.console.print(f"Type: {collection.type}")
            self.console.print(f"Source Path: {collection.source_path}")
            self.console.print(f"Local Path: {collection.local_path}")
            self.console.print(f"Created: {collection.created_at}")
            self.console.print(f"Updated: {collection.updated_at}")
            
            if collection.metadata:
                self.console.print(f"\n[bold]Metadata:[/bold]")
                for key, value in collection.metadata.items():
                    self.console.print(f"  {key}: {value}")
            
            # Check if local path exists and show processing steps
            if collection.local_path:
                local_path = Path(collection.local_path)
                if local_path.exists():
                    self.console.print(f"\n[bold]Local Path Status:[/bold] ✅ Exists")
                    self.console.print(f"Path: {local_path}")
                    
                    # Try to get processing steps
                    try:
                        navigator = self.get_navigator_for_collection(collection)
                        if navigator:
                            available_steps = navigator.get_available_steps()
                            self.console.print(f"\n[bold]Processing Steps:[/bold] {len(available_steps)} available")
                            
                            for step in available_steps:
                                outputs = navigator.get_step_outputs(step.name)
                                self.console.print(f"  {step.name}: {len(outputs)} files")
                                
                    except Exception as e:
                        self.console.print(f"[red]Error reading processing steps: {e}[/red]")
                else:
                    self.console.print(f"\n[bold]Local Path Status:[/bold] ❌ Does not exist")
                    self.console.print(f"Path: {local_path}")
            else:
                self.console.print(f"\n[bold]Local Path Status:[/bold] ❌ Not set")
                
        except Exception as e:
            self.console.print(f"[red]Failed to preview collection: {e}[/red]")
    
    async def _reorder_collection(self, collection_id: str, position: int):
        """Reorder collection"""
        try:
            # Get collection first to confirm it exists
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Update collection position
            success = await self.library_manager.update_collection(collection_id, position=position)
            
            if success:
                self.console.print(f"[green]✅ Collection '{collection.name}' moved to position {position}[/green]")
            else:
                self.console.print(f"[red]❌ Failed to reorder collection[/red]")
                
        except Exception as e:
            self.console.print(f"[red]Failed to reorder collection: {e}[/red]")
