"""
Import/Export Commands

Collection import and export functionality.
"""

import asyncio
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
import typer

from .base import BaseLibraryCommands


class ImportExportCommands(BaseLibraryCommands):
    """Import and export collection commands"""
    
    def register_commands(self, app):
        """Register import/export commands"""
        
        @app.command(name="import", help="Import a collection from a path")
        def import_collection(
            path: Path = typer.Argument(..., help="Path to import collection from"),
            name: Optional[str] = typer.Option(None, "--name", "-n", help="Name for the imported collection")
        ):
            """Import a collection from a path"""
            asyncio.run(self._import_collection(path, name))
        
        @app.command(name="export", help="Export a collection to a path")
        def export_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to export"),
            path: Path = typer.Argument(..., help="Path to export collection to")
        ):
            """Export a collection to a path"""
            asyncio.run(self._export_collection(collection_id, path))
    
    async def _import_collection(self, path: Path, name: Optional[str]):
        """Import a collection from zip file"""
        try:
            # Check if path exists
            if not path.exists():
                self.console.print(f"[red]❌ Path does not exist: {path}[/red]")
                return
            
            # Determine collection name
            collection_name = name or path.stem
            
            # Check if it's a zip file
            if path.suffix.lower() == '.zip':
                # Import from zip file
                await self._import_from_zip(path, collection_name)
            else:
                # Import from directory (existing functionality)
                await self._import_from_directory(path, collection_name)
                
        except Exception as e:
            self.console.print(f"[red]❌ Failed to import collection: {e}[/red]")
    
    async def _import_from_zip(self, zip_path: Path, collection_name: str):
        """Import collection from export zip file with all files and metadata"""
        try:
            self.console.print(f"[blue]📦 Importing collection from {zip_path.name}...[/blue]")

            # Import using library manager
            collection_id = await self.library_manager.import_collection(zip_path, collection_name)

            if collection_id:
                self.console.print(f"[green]✅ Collection '{collection_name}' imported successfully[/green]")
                self.console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
            else:
                self.console.print(f"[red]❌ Failed to import collection from zip file[/red]")

        except Exception as e:
            self.console.print(f"[red]❌ Error importing from zip: {e}[/red]")
    
    async def _import_from_directory(self, dir_path: Path, collection_name: str):
        """Import collection from directory (existing functionality)"""
        try:
            # Add collection to library
            collection_id = await self.library_manager.add_collection(
                name=collection_name,
                collection_type="local", 
                source_path=str(dir_path),
                description=f"Imported from directory"
            )
            
            if collection_id:
                self.console.print(f"[green]✅ Collection '{collection_name}' imported successfully from directory[/green]")
                self.console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
            else:
                self.console.print(f"[red]❌ Failed to add collection to library[/red]")
                
        except Exception as e:
            self.console.print(f"[red]❌ Error importing from directory: {e}[/red]")
    
    async def _export_collection(self, collection_id: str, path: Path):
        """Export a collection to zip file with all files and metadata"""
        try:
            # Get collection first to confirm it exists
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return

            # Ensure the output path has .zip extension
            if not path.suffix.lower() == '.zip':
                path = path.with_suffix('.zip')

            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)

            # Export collection using library manager
            self.console.print(f"[blue]📦 Exporting collection '{collection.name}'...[/blue]")

            success = await self.library_manager.export_collection(collection_id, path)

            if success:
                file_size = path.stat().st_size
                size_mb = file_size / (1024 * 1024)

                self.console.print(f"[green]✅ Collection exported successfully[/green]")
                self.console.print(f"[blue]📦 Export path: {path}[/blue]")
                self.console.print(f"[blue]📊 File size: {size_mb:.1f} MB[/blue]")
            else:
                self.console.print(f"[red]❌ Export failed[/red]")

        except Exception as e:
            self.console.print(f"[red]❌ Failed to export collection: {e}[/red]")
