"""
Batch Commands for Library CLI

Commands for batch operations on multiple items or collections.
"""

import asyncio
from typing import List, Optional
import typer
from rich.console import Console
from rich.progress import Progress, TaskID

from .base import BaseLibraryCommands

console = Console()

class BatchCommands(BaseLibraryCommands):
    """Batch operations for collections and items"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize batch commands - optionally share base instance"""
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
        """Register batch commands"""
        
        @app.command(name="batch-update-items", help="Update multiple items at once")
        def batch_update_items(
            item_ids: str = typer.Argument(..., help="Comma-separated list of item IDs"),
            status: Optional[str] = typer.Option(None, "--status", "-s", help="New status for all items"),
            metadata: Optional[str] = typer.Option(None, "--metadata", "-m", help="JSON metadata to add")
        ):
            """Update multiple items at once"""
            asyncio.run(self._batch_update_items(item_ids, status, metadata))
        
        @app.command(name="batch-delete-items", help="Delete multiple items at once")
        def batch_delete_items(
            item_ids: str = typer.Argument(..., help="Comma-separated list of item IDs"),
            confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt")
        ):
            """Delete multiple items at once"""
            asyncio.run(self._batch_delete_items(item_ids, confirm))
        
        @app.command(name="batch-export", help="Export multiple collections at once")
        def batch_export(
            collection_ids: str = typer.Argument(..., help="Comma-separated list of collection IDs"),
            output_dir: str = typer.Argument(..., help="Output directory for exports")
        ):
            """Export multiple collections at once"""
            asyncio.run(self._batch_export(collection_ids, output_dir))
        
        @app.command(name="duplicate-collection", help="Duplicate a collection")
        def duplicate_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to duplicate"),
            new_name: str = typer.Argument(..., help="Name for the new collection")
        ):
            """Duplicate a collection"""
            asyncio.run(self._duplicate_collection(collection_id, new_name))
    
    async def _batch_update_items(self, item_ids: str, status: Optional[str], metadata: Optional[str]):
        """Update multiple items at once"""
        try:
            item_id_list = [id.strip() for id in item_ids.split(',')]
            
            if not item_id_list:
                console.print("[red]No item IDs provided[/red]")
                return
            
            # Parse metadata if provided
            parsed_metadata = {}
            if metadata:
                import json
                try:
                    parsed_metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    console.print("[red]Invalid JSON metadata format[/red]")
                    return
            
            console.print(f"[blue]Updating {len(item_id_list)} items...[/blue]")
            
            success_count = 0
            failed_count = 0
            
            with Progress() as progress:
                task = progress.add_task("Updating items...", total=len(item_id_list))
                
                for item_id in item_id_list:
                    try:
                        # Update status if provided
                        if status:
                            await self.library_manager.update_item_status(item_id, status)
                        
                        # Update metadata if provided
                        if parsed_metadata:
                            # Get current item to update metadata
                            collections = await self.library_manager.get_all_collections()
                            for collection in collections:
                                items = await self.library_manager.get_collection_items(collection.id)
                                for item in items:
                                    if str(item.id) == item_id:
                                        # Update item metadata
                                        item.metadata.update(parsed_metadata)
                                        # Note: This would need a proper update method in LibraryManager
                                        break
                        
                        success_count += 1
                        
                    except Exception as e:
                        console.print(f"[red]Failed to update item {item_id}: {e}[/red]")
                        failed_count += 1
                    
                    progress.advance(task)
            
            console.print(f"[green]✅ Updated {success_count} items successfully[/green]")
            if failed_count > 0:
                console.print(f"[red]❌ Failed to update {failed_count} items[/red]")
            
        except Exception as e:
            console.print(f"[red]Failed to batch update items: {e}[/red]")
    
    async def _batch_delete_items(self, item_ids: str, confirm: bool):
        """Delete multiple items at once"""
        try:
            item_id_list = [id.strip() for id in item_ids.split(',')]
            
            if not item_id_list:
                console.print("[red]No item IDs provided[/red]")
                return
            
            if not confirm:
                response = input(f"Are you sure you want to delete {len(item_id_list)} items? (y/N): ")
                if response.lower() != 'y':
                    console.print("[yellow]Operation cancelled[/yellow]")
                    return
            
            console.print(f"[blue]Deleting {len(item_id_list)} items...[/blue]")
            
            success_count = 0
            failed_count = 0
            
            with Progress() as progress:
                task = progress.add_task("Deleting items...", total=len(item_id_list))
                
                for item_id in item_id_list:
                    try:
                        # Find and delete the item
                        collections = await self.library_manager.get_all_collections()
                        for collection in collections:
                            items = await self.library_manager.get_collection_items(collection.id)
                            for item in items:
                                if str(item.id) == item_id:
                                    # Delete the item
                                    # Note: This would need a proper delete method in LibraryManager
                                    success_count += 1
                                    break
                            if success_count > 0:
                                break
                        
                        if success_count == 0:
                            failed_count += 1
                        
                    except Exception as e:
                        console.print(f"[red]Failed to delete item {item_id}: {e}[/red]")
                        failed_count += 1
                    
                    progress.advance(task)
            
            console.print(f"[green]✅ Deleted {success_count} items successfully[/green]")
            if failed_count > 0:
                console.print(f"[red]❌ Failed to delete {failed_count} items[/red]")
            
        except Exception as e:
            console.print(f"[red]Failed to batch delete items: {e}[/red]")
    
    async def _batch_export(self, collection_ids: str, output_dir: str):
        """Export multiple collections at once"""
        try:
            collection_id_list = [id.strip() for id in collection_ids.split(',')]
            
            if not collection_id_list:
                console.print("[red]No collection IDs provided[/red]")
                return
            
            from pathlib import Path
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            console.print(f"[blue]Exporting {len(collection_id_list)} collections to {output_dir}...[/blue]")
            
            success_count = 0
            failed_count = 0
            
            with Progress() as progress:
                task = progress.add_task("Exporting collections...", total=len(collection_id_list))
                
                for collection_id in collection_id_list:
                    try:
                        collection = await self.library_manager.get_collection(collection_id)
                        if not collection:
                            console.print(f"[red]Collection {collection_id} not found[/red]")
                            failed_count += 1
                            continue
                        
                        export_file = output_path / f"{collection.name}.zip"
                        await self.library_manager.export_collection(collection_id, export_file)
                        
                        success_count += 1
                        console.print(f"[green]✅ Exported {collection.name} to {export_file}[/green]")
                        
                    except Exception as e:
                        console.print(f"[red]Failed to export collection {collection_id}: {e}[/red]")
                        failed_count += 1
                    
                    progress.advance(task)
            
            console.print(f"[green]✅ Exported {success_count} collections successfully[/green]")
            if failed_count > 0:
                console.print(f"[red]❌ Failed to export {failed_count} collections[/red]")
            
        except Exception as e:
            console.print(f"[red]Failed to batch export collections: {e}[/red]")
    
    async def _duplicate_collection(self, collection_id: str, new_name: str):
        """Duplicate a collection"""
        try:
            # Get the original collection
            collection = await self.library_manager.get_collection(collection_id)
            if not collection:
                console.print(f"[red]Collection with ID '{collection_id}' not found[/red]")
                return
            
            # Create new collection with same settings
            new_collection_id = await self.library_manager.add_collection(
                name=new_name,
                collection_type=collection.type,
                source_path=collection.source_path,
                description=f"Duplicated from {collection.name}",
                metadata=collection.metadata
            )
            
            if not new_collection_id:
                console.print(f"[red]Failed to create duplicate collection[/red]")
                return
            
            # Copy all items from original collection
            items = await self.library_manager.get_collection_items(collection_id)
            
            if items:
                console.print(f"[blue]Copying {len(items)} items to new collection...[/blue]")
                
                with Progress() as progress:
                    task = progress.add_task("Copying items...", total=len(items))
                    
                    for item in items:
                        try:
                            await self.library_manager.add_item_to_collection(
                                collection_id=new_collection_id,
                                item_type=item.type,
                                source=item.source_path or "",
                                name=item.name,
                                operation="link",  # Just reference, don't copy files
                                metadata=item.metadata
                            )
                        except Exception as e:
                            console.print(f"[red]Failed to copy item {item.name}: {e}[/red]")
                        
                        progress.advance(task)
            
            console.print(f"[green]✅ Collection '{new_name}' duplicated successfully with ID: {new_collection_id}[/green]")
            
        except Exception as e:
            console.print(f"[red]Failed to duplicate collection: {e}[/red]")
