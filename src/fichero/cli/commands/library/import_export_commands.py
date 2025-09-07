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
        """Import collection from zip file"""
        try:
            # Create temporary extraction directory
            import tempfile
            import shutil
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Extract zip file
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                # Find the main collection directory (usually the first directory)
                extracted_dirs = [d for d in temp_path.iterdir() if d.is_dir()]
                if not extracted_dirs:
                    self.console.print(f"[red]❌ No directories found in zip file[/red]")
                    return
                
                # Use the first directory as the collection source
                source_dir = extracted_dirs[0]
                
                # Add collection to library
                collection_id = await self.library_manager.add_collection(
                    name=collection_name,
                    collection_type="local",
                    source_path=str(source_dir),
                    description=f"Imported from {zip_path.name}"
                )
                
                if collection_id:
                    self.console.print(f"[green]✅ Collection '{collection_name}' imported successfully from zip file[/green]")
                    self.console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
                else:
                    self.console.print(f"[red]❌ Failed to add collection to library[/red]")
                    
        except zipfile.BadZipFile:
            self.console.print(f"[red]❌ Invalid zip file: {zip_path}[/red]")
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
        """Export a collection to zip file"""
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
            
            # Export collection to zip
            await self._export_to_zip(collection, path)
            
        except Exception as e:
            self.console.print(f"[red]❌ Failed to export collection: {e}[/red]")
    
    async def _export_to_zip(self, collection, output_path: Path):
        """Export collection to zip file"""
        try:
            import tempfile
            import shutil
            
            # Get collection source path
            source_path = Path(collection.source_path) if collection.source_path else Path(collection.local_path)
            
            if not source_path.exists():
                self.console.print(f"[red]❌ Collection source path does not exist: {source_path}[/red]")
                return
            
            # Create zip file
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Walk through the directory and add files to zip
                for file_path in source_path.rglob('*'):
                    if file_path.is_file():
                        # Calculate relative path from source directory
                        arcname = file_path.relative_to(source_path)
                        zipf.write(file_path, arcname)
            
            # Get file size for display
            file_size = output_path.stat().st_size
            size_mb = file_size / (1024 * 1024)
            
            self.console.print(f"[green]✅ Collection '{collection.name}' exported successfully[/green]")
            self.console.print(f"[blue]📦 Export path: {output_path}[/blue]")
            self.console.print(f"[blue]📊 File size: {size_mb:.1f} MB[/blue]")
            
        except Exception as e:
            self.console.print(f"[red]❌ Error creating zip file: {e}[/red]")
