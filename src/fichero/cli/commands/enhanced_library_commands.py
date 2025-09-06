"""
Enhanced Library Commands for Fichero CLI
Includes processing step navigation and output viewing
"""

import asyncio
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich.syntax import Syntax

from fichero.library.processing_navigator import ProcessingNavigator, ProcessingOutput
from fichero.library.director_bridge import LibraryDirectorBridge
from fichero.director.director_service import FicheroDirector

console = Console()

class EnhancedLibraryCommands:
    """Enhanced library commands with processing navigation"""
    
    def __init__(self, app_initializer):
        """Initialize enhanced library commands"""
        self.app_initializer = app_initializer
        self.app = typer.Typer(name="library", help="Enhanced library management with processing navigation")
        self._register_commands()
        
        # Initialize director bridge
        self.director = FicheroDirector()
        self.bridge = LibraryDirectorBridge(self.director)
    
    def _register_commands(self):
        """Register all enhanced library commands"""
        
        @self.app.command(name="list", help="List all collections with processing status")
        async def list_collections():
            """List all collections with their processing status"""
            await self._list_collections()
        
        @self.app.command(name="add", help="Add a new collection to the library")
        async def add_collection(
            name: str = typer.Argument(..., help="Name of the new collection"),
            collection_type: str = typer.Option("local", "--type", "-t", help="Type of the collection"),
            source_path: Optional[Path] = typer.Option(None, "--source", "-s", help="Source path for external/local collections"),
            description: str = typer.Option("", "--description", "-d", help="Description of the collection"),
            metadata: Optional[str] = typer.Option(None, "--metadata", "-m", help="JSON string of additional metadata")
        ):
            """Add a new collection to the library"""
            await self._add_collection(name, collection_type, source_path, description, metadata)
        
        @self.app.command(name="delete", help="Delete a collection from the library")
        async def delete_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to delete")
        ):
            """Delete a collection from the library"""
            await self._delete_collection(collection_id)
        
        @self.app.command(name="rename", help="Rename a collection")
        async def rename_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to rename"),
            new_name: str = typer.Argument(..., help="New name for the collection")
        ):
            """Rename a collection"""
            await self._rename_collection(collection_id, new_name)
        
        @self.app.command(name="import", help="Import a collection from a path")
        async def import_collection(
            path: Path = typer.Argument(..., help="Path to import collection from"),
            name: Optional[str] = typer.Option(None, "--name", "-n", help="Name for the imported collection")
        ):
            """Import a collection from a path"""
            await self._import_collection(path, name)
        
        @self.app.command(name="export", help="Export a collection to a path")
        async def export_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to export"),
            path: Path = typer.Argument(..., help="Path to export collection to")
        ):
            """Export a collection to a path"""
            await self._export_collection(collection_id, path)
        
        @self.app.command(name="preview", help="Preview collection contents and processing status")
        async def preview_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to preview")
        ):
            """Preview collection contents and processing status"""
            await self._preview_collection(collection_id)
        
        @self.app.command(name="reorder", help="Reorder collections")
        async def reorder_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to reorder"),
            position: int = typer.Argument(..., help="New position for the collection")
        ):
            """Reorder collections"""
            await self._reorder_collection(collection_id, position)
        
        # New enhanced commands
        @self.app.command(name="steps", help="List processing steps for a collection")
        async def list_processing_steps(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            show_files: bool = typer.Option(False, "--files", "-f", help="Show files in each step")
        ):
            """List processing steps for a collection"""
            await self._list_processing_steps(collection_id, show_files)
        
        @self.app.command(name="step", help="View details of a specific processing step")
        async def view_processing_step(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            step_name: str = typer.Argument(..., help="Name of the processing step"),
            show_manifest: bool = typer.Option(False, "--manifest", "-m", help="Show manifest information"),
            show_progress: bool = typer.Option(False, "--progress", "-p", help="Show progress information")
        ):
            """View details of a specific processing step"""
            await self._view_processing_step(collection_id, step_name, show_manifest, show_progress)
        
        @self.app.command(name="search", help="Search across all processing steps")
        async def search_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            query: str = typer.Argument(..., help="Search query"),
            file_types: Optional[str] = typer.Option(None, "--types", "-t", help="Comma-separated file types to search")
        ):
            """Search across all processing steps"""
            await self._search_collection(collection_id, query, file_types)
        
        @self.app.command(name="view", help="View content of a specific file")
        async def view_file(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            step_name: str = typer.Argument(..., help="Name of the processing step"),
            file_name: str = typer.Argument(..., help="Name of the file to view"),
            max_lines: int = typer.Option(20, "--lines", "-l", help="Maximum lines to show")
        ):
            """View content of a specific file"""
            await self._view_file(collection_id, step_name, file_name, max_lines)
        
        @self.app.command(name="process", help="Process a collection through the director")
        async def process_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to process"),
            steps: Optional[str] = typer.Option(None, "--steps", "-s", help="Comma-separated list of steps to process"),
            level: Optional[int] = typer.Option(None, "--level", "-l", help="Process specific level of hierarchy")
        ):
            """Process a collection through the director"""
            await self._process_collection(collection_id, steps, level)
        
        @self.app.command(name="status", help="Get processing status of a collection")
        async def get_processing_status(
            collection_id: str = typer.Argument(..., help="ID of the collection")
        ):
            """Get processing status of a collection"""
            await self._get_processing_status(collection_id)
        
        @self.app.command(name="structure", help="Preview collection structure")
        async def preview_structure(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum depth to show")
        ):
            """Preview collection structure"""
            await self._preview_structure(collection_id, max_depth)
    
    async def _list_collections(self):
        """List all collections with processing status"""
        try:
            # Get library manager from app initializer
            library_manager = self.app_initializer.library_manager
            
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
            library_manager = self.app_initializer.library_manager
            collections = await library_manager.get_all_collections()
            
            for collection in collections:
                if str(collection.id) == collection_id:
                    return collection
            
            console.print(f"[red]Collection with ID '{collection_id}' not found[/red]")
            return None
            
        except Exception as e:
            console.print(f"[red]Failed to get collection: {e}[/red]")
            return None
    
    # Placeholder methods for basic library operations
    async def _add_collection(self, name: str, collection_type: str, source_path: Optional[Path], description: str, metadata: Optional[str]):
        """Add a new collection (placeholder)"""
        console.print(f"[yellow]Add collection command not yet implemented[/yellow]")
    
    async def _delete_collection(self, collection_id: str):
        """Delete a collection (placeholder)"""
        console.print(f"[yellow]Delete collection command not yet implemented[/yellow]")
    
    async def _rename_collection(self, collection_id: str, new_name: str):
        """Rename a collection (placeholder)"""
        console.print(f"[yellow]Rename collection command not yet implemented[/yellow]")
    
    async def _import_collection(self, path: Path, name: Optional[str]):
        """Import a collection (placeholder)"""
        console.print(f"[yellow]Import collection command not yet implemented[/yellow]")
    
    async def _export_collection(self, collection_id: str, path: Path):
        """Export a collection (placeholder)"""
        console.print(f"[yellow]Export collection command not yet implemented[/yellow]")
    
    async def _preview_collection(self, collection_id: str):
        """Preview collection (placeholder)"""
        console.print(f"[yellow]Preview collection command not yet implemented[/yellow]")
    
    async def _reorder_collection(self, collection_id: str, position: int):
        """Reorder collection (placeholder)"""
        console.print(f"[yellow]Reorder collection command not yet implemented[/yellow]")
