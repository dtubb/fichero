"""
Enhanced Library Commands for Fichero CLI
Includes processing step navigation and output viewing
"""

import asyncio
import json
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from unittest.mock import Mock
import typer
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich.syntax import Syntax
from rich.progress import Progress, track

from fichero.library.processing_navigator import ProcessingNavigator, ProcessingOutput
from fichero.library.director_bridge import LibraryDirectorBridge
from fichero.director.director_service import FicheroDirector

console = Console()

class LibraryCommands:
    """Enhanced library commands with processing navigation"""
    
    def __init__(self, app_initializer):
        """Initialize enhanced library commands"""
        self.app_initializer = app_initializer
        self.app = typer.Typer(name="library", help="Enhanced library management with processing navigation")
        self._register_commands()
        
        # Initialize library manager directly for CLI
        from fichero.library.library_manager import LibraryManager
        from fichero.library.storage import LibraryStorage
        from pathlib import Path
        
        # For CLI, use a default library path
        library_path = Path.home() / ".fichero" / "library"
        library_path.mkdir(parents=True, exist_ok=True)
        
        db_path = library_path / "library.db"
        storage = LibraryStorage(db_path)
        
        # Create a mock app object for the library manager
        mock_app = Mock()
        mock_app.paths = Mock()
        mock_app.paths.data = library_path
        
        self.library_manager = LibraryManager(mock_app)
        
        # Initialize director bridge
        self.director = FicheroDirector()
        self.bridge = LibraryDirectorBridge(self.director)
    
    def _register_commands(self):
        """Register all enhanced library commands"""
        
        @self.app.command(name="list", help="List all collections with processing status")
        def list_collections():
            """List all collections with their processing status"""
            asyncio.run(self._list_collections())
        
        @self.app.command(name="add", help="Add a new collection to the library")
        def add_collection(
            name: str = typer.Argument(..., help="Name of the new collection"),
            collection_type: str = typer.Option("local", "--type", "-t", help="Type of the collection"),
            source_path: Optional[Path] = typer.Option(None, "--source", "-s", help="Source path for external/local collections"),
            description: str = typer.Option("", "--description", "-d", help="Description of the collection"),
            metadata: Optional[str] = typer.Option(None, "--metadata", "-m", help="JSON string of additional metadata")
        ):
            """Add a new collection to the library"""
            asyncio.run(self._add_collection(name, collection_type, source_path, description, metadata))
        
        @self.app.command(name="delete", help="Delete a collection from the library")
        def delete_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to delete")
        ):
            """Delete a collection from the library"""
            asyncio.run(self._delete_collection(collection_id))
        
        @self.app.command(name="rename", help="Rename a collection")
        def rename_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to rename"),
            new_name: str = typer.Argument(..., help="New name for the collection")
        ):
            """Rename a collection"""
            asyncio.run(self._rename_collection(collection_id, new_name))
        
        @self.app.command(name="import", help="Import a collection from a path")
        def import_collection(
            path: Path = typer.Argument(..., help="Path to import collection from"),
            name: Optional[str] = typer.Option(None, "--name", "-n", help="Name for the imported collection")
        ):
            """Import a collection from a path"""
            asyncio.run(self._import_collection(path, name))
        
        @self.app.command(name="export", help="Export a collection to a path")
        def export_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to export"),
            path: Path = typer.Argument(..., help="Path to export collection to")
        ):
            """Export a collection to a path"""
            asyncio.run(self._export_collection(collection_id, path))
        
        @self.app.command(name="preview", help="Preview collection contents and processing status")
        def preview_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to preview")
        ):
            """Preview collection contents and processing status"""
            asyncio.run(self._preview_collection(collection_id))
        
        @self.app.command(name="reorder", help="Reorder collections")
        def reorder_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to reorder"),
            position: int = typer.Argument(..., help="New position for the collection")
        ):
            """Reorder collections"""
            asyncio.run(self._reorder_collection(collection_id, position))
        
        # New enhanced commands
        @self.app.command(name="steps", help="List processing steps for a collection")
        def list_processing_steps(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            show_files: bool = typer.Option(False, "--files", "-f", help="Show files in each step")
        ):
            """List processing steps for a collection"""
            asyncio.run(self._list_processing_steps(collection_id, show_files))
        
        @self.app.command(name="step", help="View details of a specific processing step")
        def view_processing_step(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            step_name: str = typer.Argument(..., help="Name of the processing step"),
            show_manifest: bool = typer.Option(False, "--manifest", "-m", help="Show manifest information"),
            show_progress: bool = typer.Option(False, "--progress", "-p", help="Show progress information")
        ):
            """View details of a specific processing step"""
            asyncio.run(self._view_processing_step(collection_id, step_name, show_manifest, show_progress))
        
        @self.app.command(name="search", help="Search across all processing steps")
        def search_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            query: str = typer.Argument(..., help="Search query"),
            file_types: Optional[str] = typer.Option(None, "--types", "-t", help="Comma-separated file types to search")
        ):
            """Search across all processing steps"""
            asyncio.run(self._search_collection(collection_id, query, file_types))
        
        @self.app.command(name="view", help="View content of a specific file")
        def view_file(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            step_name: str = typer.Argument(..., help="Name of the processing step"),
            file_name: str = typer.Argument(..., help="Name of the file to view"),
            max_lines: int = typer.Option(20, "--lines", "-l", help="Maximum lines to show")
        ):
            """View content of a specific file"""
            asyncio.run(self._view_file(collection_id, step_name, file_name, max_lines))
        
        @self.app.command(name="process", help="Process a collection through the director")
        def process_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to process"),
            steps: Optional[str] = typer.Option(None, "--steps", "-s", help="Comma-separated list of steps to process"),
            level: Optional[int] = typer.Option(None, "--level", "-l", help="Process specific level of hierarchy")
        ):
            """Process a collection through the director"""
            asyncio.run(self._process_collection(collection_id, steps, level))
        
        @self.app.command(name="status", help="Get processing status of a collection")
        def get_processing_status(
            collection_id: str = typer.Argument(..., help="ID of the collection")
        ):
            """Get processing status of a collection"""
            asyncio.run(self._get_processing_status(collection_id))
        
        @self.app.command(name="structure", help="Preview collection structure")
        def preview_structure(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum depth to show")
        ):
            """Preview collection structure"""
            asyncio.run(self._preview_structure(collection_id, max_depth))
    
    async def _list_collections(self):
        """List all collections with processing status"""
        try:
            # Use our own library manager
            library_manager = self.library_manager
            
            # Get all collections
            collections = await library_manager.get_all_collections()
            
            if not collections:
                console.print("[yellow]No collections found in library[/yellow]")
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
                    navigator = ProcessingNavigator(collection_path)
                    summary = navigator.get_processing_summary()
                    processing_steps = f"{len(summary['available_steps'])}/{len(summary['steps'])}"
                else:
                    processing_steps = "N/A"
                
                description = collection.metadata.get('description', 'N/A')
                table.add_row(
                    str(collection.id),
                    collection.name,
                    collection.type,
                    str(len(await library_manager.get_collection_items(collection.id))),
                    collection.created_at.strftime("%Y-%m-%d"),
                    description,
                    processing_steps
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Failed to list collections: {e}[/red]")
    
    async def _list_processing_steps(self, collection_id: str, show_files: bool):
        """List processing steps for a collection"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Create navigator
            navigator = ProcessingNavigator(collection_path)
            available_steps = navigator.get_available_steps()
            
            if not available_steps:
                console.print("[yellow]No processing steps found in collection[/yellow]")
                return
            
            # Create table
            table = Table(title=f"Processing Steps for {collection.name}")
            table.add_column("Step", style="cyan", no_wrap=True)
            table.add_column("Description", style="white")
            table.add_column("Files", justify="right", style="yellow")
            table.add_column("File Types", style="green")
            table.add_column("Status", style="red")
            
            for step in available_steps:
                outputs = navigator.get_step_outputs(step.name)
                file_count = len(outputs)
                file_types = ", ".join(step.file_types)
                status = "✅ Complete" if file_count > 0 else "⏳ Pending"
                
                table.add_row(
                    step.name,
                    step.description,
                    str(file_count),
                    file_types,
                    status
                )
            
            console.print(table)
            
            if show_files:
                console.print("\n[bold]Files in each step:[/bold]")
                for step in available_steps:
                    outputs = navigator.get_step_outputs(step.name)
                    if outputs:
                        console.print(f"\n[cyan]{step.name}:[/cyan]")
                        for output in outputs[:10]:  # Show first 10 files
                            console.print(f"  • {output.name} ({output.file_type})")
                        if len(outputs) > 10:
                            console.print(f"  ... and {len(outputs) - 10} more files")
            
        except Exception as e:
            console.print(f"[red]Failed to list processing steps: {e}[/red]")
    
    async def _view_processing_step(self, collection_id: str, step_name: str, show_manifest: bool, show_progress: bool):
        """View details of a specific processing step"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Create navigator
            navigator = ProcessingNavigator(collection_path)
            
            if step_name not in navigator.steps:
                console.print(f"[red]Unknown processing step: {step_name}[/red]")
                console.print(f"Available steps: {', '.join(navigator.steps.keys())}")
                return
            
            step = navigator.steps[step_name]
            outputs = navigator.get_step_outputs(step_name)
            
            # Show step information
            console.print(f"\n[bold cyan]Processing Step: {step_name}[/bold cyan]")
            console.print(f"Description: {step.description}")
            console.print(f"Path: {collection_path / step.path}")
            console.print(f"File Types: {', '.join(step.file_types)}")
            console.print(f"Files: {len(outputs)}")
            
            if outputs:
                console.print(f"\n[bold]Files in {step_name}:[/bold]")
                table = Table()
                table.add_column("Name", style="cyan")
                table.add_column("Type", style="green")
                table.add_column("Size", justify="right", style="yellow")
                table.add_column("Modified", style="blue")
                
                for output in outputs:
                    size_str = self._format_file_size(output.size)
                    modified_str = output.modified.strftime("%Y-%m-%d %H:%M")
                    table.add_row(output.name, output.file_type, size_str, modified_str)
                
                console.print(table)
            
            # Show manifest if requested
            if show_manifest:
                manifest = navigator.get_step_manifest(step_name)
                if manifest:
                    console.print(f"\n[bold]Manifest ({manifest['count']} entries):[/bold]")
                    console.print(f"File: {manifest['file']}")
                    # Show first few entries
                    for i, entry in enumerate(manifest['entries'][:5]):
                        console.print(f"  {i+1}. {json.dumps(entry, indent=2)}")
                    if len(manifest['entries']) > 5:
                        console.print(f"  ... and {len(manifest['entries']) - 5} more entries")
                else:
                    console.print("[yellow]No manifest file found[/yellow]")
            
            # Show progress if requested
            if show_progress:
                progress = navigator.get_step_progress(step_name)
                if progress:
                    console.print(f"\n[bold]Progress ({progress['count']} entries):[/bold]")
                    console.print(f"File: {progress['file']}")
                    # Show first few entries
                    for i, entry in enumerate(progress['entries'][:5]):
                        console.print(f"  {i+1}. {json.dumps(entry, indent=2)}")
                    if len(progress['entries']) > 5:
                        console.print(f"  ... and {len(progress['entries']) - 5} more entries")
                else:
                    console.print("[yellow]No progress file found[/yellow]")
            
        except Exception as e:
            console.print(f"[red]Failed to view processing step: {e}[/red]")
    
    async def _search_collection(self, collection_id: str, query: str, file_types: Optional[str]):
        """Search across all processing steps"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Create navigator
            navigator = ProcessingNavigator(collection_path)
            
            # Parse file types
            types_list = None
            if file_types:
                types_list = [t.strip() for t in file_types.split(',')]
            
            # Search
            results = navigator.search_across_steps(query, types_list)
            
            if not results:
                console.print(f"[yellow]No files found matching '{query}'[/yellow]")
                return
            
            console.print(f"\n[bold]Search Results for '{query}' ({len(results)} files):[/bold]")
            
            table = Table()
            table.add_column("Step", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("Type", style="green")
            table.add_column("Size", justify="right", style="yellow")
            table.add_column("Path", style="white")
            
            for result in results:
                size_str = self._format_file_size(result.size)
                table.add_row(
                    result.step,
                    result.name,
                    result.file_type,
                    size_str,
                    str(result.path)
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Failed to search collection: {e}[/red]")
    
    async def _view_file(self, collection_id: str, step_name: str, file_name: str, max_lines: int):
        """View content of a specific file"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Create navigator
            navigator = ProcessingNavigator(collection_path)
            outputs = navigator.get_step_outputs(step_name)
            
            # Find the file
            target_file = None
            for output in outputs:
                if output.name == file_name:
                    target_file = output
                    break
            
            if not target_file:
                console.print(f"[red]File '{file_name}' not found in step '{step_name}'[/red]")
                return
            
            # Get content preview
            content = navigator.get_file_content_preview(target_file, max_lines)
            
            if content is None:
                console.print(f"[yellow]Cannot preview file type: {target_file.file_type}[/yellow]")
                return
            
            # Display content
            console.print(f"\n[bold]File: {file_name}[/bold]")
            console.print(f"Step: {step_name}")
            console.print(f"Type: {target_file.file_type}")
            console.print(f"Size: {self._format_file_size(target_file.size)}")
            console.print(f"Modified: {target_file.modified.strftime('%Y-%m-%d %H:%M')}")
            
            # Show content with syntax highlighting
            if target_file.file_type in ['.json', '.jsonl']:
                syntax = Syntax(content, "json", theme="monokai", line_numbers=True)
            elif target_file.file_type == '.txt':
                syntax = Syntax(content, "text", theme="monokai", line_numbers=True)
            else:
                syntax = Syntax(content, "text", theme="monokai", line_numbers=True)
            
            console.print(syntax)
            
        except Exception as e:
            console.print(f"[red]Failed to view file: {e}[/red]")
    
    async def _process_collection(self, collection_id: str, steps: Optional[str], level: Optional[int]):
        """Process a collection through the director"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Parse steps
            steps_list = None
            if steps:
                steps_list = [s.strip() for s in steps.split(',')]
            
            # Process collection
            if level is not None:
                console.print(f"[blue]Processing collection at level {level}...[/blue]")
                result = await self.bridge.process_collection_level(collection_path, level)
            else:
                console.print(f"[blue]Processing collection...[/blue]")
                result = await self.bridge.process_collection(collection_path, steps_list)
            
            if result["success"]:
                console.print("[green]✅ Collection processed successfully![/green]")
                console.print(f"Processed steps: {result.get('processed_steps', 'N/A')}")
            else:
                console.print(f"[red]❌ Processing failed: {result.get('error', 'Unknown error')}[/red]")
            
        except Exception as e:
            console.print(f"[red]Failed to process collection: {e}[/red]")
    
    async def _get_processing_status(self, collection_id: str):
        """Get processing status of a collection"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Get status
            status = await self.bridge.get_collection_processing_status(collection_path)
            
            console.print(f"\n[bold]Processing Status for {collection.name}[/bold]")
            console.print(f"Collection Path: {status['collection_path']}")
            console.print(f"Total Files: {status['total_files']}")
            console.print(f"Available Steps: {len(status['available_steps'])}")
            
            # Show steps status
            table = Table(title="Processing Steps Status")
            table.add_column("Step", style="cyan")
            table.add_column("Status", style="red")
            table.add_column("Files", justify="right", style="yellow")
            table.add_column("Description", style="white")
            
            for step_name, step_status in status['steps_status'].items():
                status_icon = "✅" if step_status['status'] == 'completed' else "⏳"
                table.add_row(
                    step_name,
                    f"{status_icon} {step_status['status']}",
                    str(step_status['file_count']),
                    step_status['description']
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Failed to get processing status: {e}[/red]")
    
    async def _preview_structure(self, collection_id: str, max_depth: int):
        """Preview collection structure"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Get structure
            structure = await self.bridge.preview_collection_structure(collection_path, max_depth)
            
            console.print(f"\n[bold]Collection Structure for {collection.name}[/bold]")
            console.print(f"Max Depth: {max_depth}")
            
            # Build tree
            tree = Tree(f"[bold]{collection_path.name}[/bold]")
            self._build_tree_display(tree, structure['structure'], max_depth)
            console.print(tree)
            
        except Exception as e:
            console.print(f"[red]Failed to preview structure: {e}[/red]")
    
    def _build_tree_display(self, tree: Tree, structure: Dict[str, Any], max_depth: int, current_depth: int = 0):
        """Build tree display for structure"""
        if current_depth >= max_depth:
            return
        
        if structure['type'] == 'file':
            size_str = self._format_file_size(structure['size'])
            tree.add(f"📄 {structure['name']} ({size_str})")
        elif structure['type'] == 'directory':
            branch = tree.add(f"📁 {structure['name']}")
            for child in structure.get('children', []):
                self._build_tree_display(branch, child, max_depth, current_depth + 1)
        elif structure['type'] == 'truncated':
            tree.add(f"... (truncated at depth {current_depth})")
    
    def _format_file_size(self, size: int) -> str:
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    async def _get_collection_by_id(self, collection_id: str):
        """Get collection by ID"""
        try:
            library_manager = self.library_manager
            collections = await library_manager.get_all_collections()
            
            for collection in collections:
                if str(collection.id) == collection_id:
                    return collection
            
            console.print(f"[red]Collection with ID '{collection_id}' not found[/red]")
            return None
            
        except Exception as e:
            console.print(f"[red]Failed to get collection: {e}[/red]")
            return None
    
    # Real library operations
    async def _add_collection(self, name: str, collection_type: str, source_path: Optional[Path], description: str, metadata: Optional[str]):
        """Add a new collection to the library"""
        try:
            # Parse metadata if provided
            parsed_metadata = {}
            if metadata:
                try:
                    parsed_metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    console.print("[red]Invalid JSON metadata format[/red]")
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
                console.print(f"[green]✅ Collection '{name}' added successfully with ID: {collection_id}[/green]")
            else:
                console.print(f"[red]❌ Failed to add collection '{name}'[/red]")
                
        except Exception as e:
            console.print(f"[red]Failed to add collection: {e}[/red]")
    
    async def _delete_collection(self, collection_id: str):
        """Delete a collection"""
        try:
            # Get collection first to confirm it exists
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Delete from library manager
            success = await self.library_manager.delete_collection(collection_id)
            
            if success:
                console.print(f"[green]✅ Collection '{collection.name}' deleted successfully[/green]")
            else:
                console.print(f"[red]❌ Failed to delete collection[/red]")
                
        except Exception as e:
            console.print(f"[red]Failed to delete collection: {e}[/red]")
    
    async def _rename_collection(self, collection_id: str, new_name: str):
        """Rename a collection"""
        try:
            # Get collection first to confirm it exists
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Update collection name
            success = await self.library_manager.update_collection(collection_id, name=new_name)
            
            if success:
                console.print(f"[green]✅ Collection renamed to '{new_name}' successfully[/green]")
            else:
                console.print(f"[red]❌ Failed to rename collection[/red]")
                
        except Exception as e:
            console.print(f"[red]Failed to rename collection: {e}[/red]")
    
    async def _import_collection(self, path: Path, name: Optional[str]):
        """Import a collection from zip file"""
        try:
            # Check if path exists
            if not path.exists():
                console.print(f"[red]❌ Path does not exist: {path}[/red]")
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
            console.print(f"[red]❌ Failed to import collection: {e}[/red]")
    
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
                    console.print(f"[red]❌ No directories found in zip file[/red]")
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
                    console.print(f"[green]✅ Collection '{collection_name}' imported successfully from zip file[/green]")
                    console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
                else:
                    console.print(f"[red]❌ Failed to add collection to library[/red]")
                    
        except zipfile.BadZipFile:
            console.print(f"[red]❌ Invalid zip file: {zip_path}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Error importing from zip: {e}[/red]")
    
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
                console.print(f"[green]✅ Collection '{collection_name}' imported successfully from directory[/green]")
                console.print(f"[blue]📁 Collection ID: {collection_id}[/blue]")
            else:
                console.print(f"[red]❌ Failed to add collection to library[/red]")
                
        except Exception as e:
            console.print(f"[red]❌ Error importing from directory: {e}[/red]")
    
    async def _export_collection(self, collection_id: str, path: Path):
        """Export a collection to zip file"""
        try:
            # Get collection first to confirm it exists
            collection = await self._get_collection_by_id(collection_id)
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
            console.print(f"[red]❌ Failed to export collection: {e}[/red]")
    
    async def _export_to_zip(self, collection, output_path: Path):
        """Export collection to zip file"""
        try:
            import tempfile
            import shutil
            
            # Get collection source path
            source_path = Path(collection.source_path) if collection.source_path else Path(collection.local_path)
            
            if not source_path.exists():
                console.print(f"[red]❌ Collection source path does not exist: {source_path}[/red]")
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
            
            console.print(f"[green]✅ Collection '{collection.name}' exported successfully[/green]")
            console.print(f"[blue]📦 Export path: {output_path}[/blue]")
            console.print(f"[blue]📊 File size: {size_mb:.1f} MB[/blue]")
            
        except Exception as e:
            console.print(f"[red]❌ Error creating zip file: {e}[/red]")
    
    async def _preview_collection(self, collection_id: str):
        """Preview collection contents and processing status"""
        try:
            # Get collection
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            console.print(f"\n[bold]Collection Preview: {collection.name}[/bold]")
            console.print(f"ID: {collection.id}")
            console.print(f"Type: {collection.type}")
            console.print(f"Source Path: {collection.source_path}")
            console.print(f"Local Path: {collection.local_path}")
            console.print(f"Created: {collection.created_at}")
            console.print(f"Updated: {collection.updated_at}")
            
            if collection.metadata:
                console.print(f"\n[bold]Metadata:[/bold]")
                for key, value in collection.metadata.items():
                    console.print(f"  {key}: {value}")
            
            # Check if local path exists and show processing steps
            if collection.local_path:
                local_path = Path(collection.local_path)
                if local_path.exists():
                    console.print(f"\n[bold]Local Path Status:[/bold] ✅ Exists")
                    console.print(f"Path: {local_path}")
                    
                    # Try to get processing steps
                    try:
                        navigator = ProcessingNavigator(local_path)
                        available_steps = navigator.get_available_steps()
                        console.print(f"\n[bold]Processing Steps:[/bold] {len(available_steps)} available")
                        
                        for step in available_steps:
                            outputs = navigator.get_step_outputs(step.name)
                            console.print(f"  {step.name}: {len(outputs)} files")
                            
                    except Exception as e:
                        console.print(f"[red]Error reading processing steps: {e}[/red]")
                else:
                    console.print(f"\n[bold]Local Path Status:[/bold] ❌ Does not exist")
                    console.print(f"Path: {local_path}")
            else:
                console.print(f"\n[bold]Local Path Status:[/bold] ❌ Not set")
                
        except Exception as e:
            console.print(f"[red]Failed to preview collection: {e}[/red]")
    
    async def _reorder_collection(self, collection_id: str, position: int):
        """Reorder collection"""
        try:
            # Get collection first to confirm it exists
            collection = await self._get_collection_by_id(collection_id)
            if not collection:
                return
            
            # Update collection position
            success = await self.library_manager.update_collection(collection_id, position=position)
            
            if success:
                console.print(f"[green]✅ Collection '{collection.name}' moved to position {position}[/green]")
            else:
                console.print(f"[red]❌ Failed to reorder collection[/red]")
                
        except Exception as e:
            console.print(f"[red]Failed to reorder collection: {e}[/red]")
