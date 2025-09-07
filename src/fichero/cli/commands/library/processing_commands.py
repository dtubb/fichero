"""
Processing Navigation Commands

Commands for navigating and viewing processing steps and outputs.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree

from .base import BaseLibraryCommands
from .utils import format_file_size, build_tree_display


class ProcessingCommands(BaseLibraryCommands):
    """Processing navigation and viewing commands"""
    
    def register_commands(self, app):
        """Register processing navigation commands"""
        
        @app.command(name="steps", help="List processing steps for a collection")
        def list_processing_steps(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            show_files: bool = typer.Option(False, "--files", "-f", help="Show files in each step")
        ):
            """List processing steps for a collection"""
            asyncio.run(self._list_processing_steps(collection_id, show_files))
        
        @app.command(name="step", help="View details of a specific processing step")
        def view_processing_step(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            step_name: str = typer.Argument(..., help="Name of the processing step"),
            show_manifest: bool = typer.Option(False, "--manifest", "-m", help="Show manifest information"),
            show_progress: bool = typer.Option(False, "--progress", "-p", help="Show progress information")
        ):
            """View details of a specific processing step"""
            asyncio.run(self._view_processing_step(collection_id, step_name, show_manifest, show_progress))
        
        @app.command(name="search", help="Search across all processing steps")
        def search_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            query: str = typer.Argument(..., help="Search query"),
            file_types: Optional[str] = typer.Option(None, "--types", "-t", help="Comma-separated file types to search")
        ):
            """Search across all processing steps"""
            asyncio.run(self._search_collection(collection_id, query, file_types))
        
        @app.command(name="view", help="View content of a specific file")
        def view_file(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            step_name: str = typer.Argument(..., help="Name of the processing step"),
            file_name: str = typer.Argument(..., help="Name of the file to view"),
            max_lines: int = typer.Option(20, "--lines", "-l", help="Maximum lines to show")
        ):
            """View content of a specific file"""
            asyncio.run(self._view_file(collection_id, step_name, file_name, max_lines))
        
        @app.command(name="process", help="Process a collection through the director")
        def process_collection(
            collection_id: str = typer.Argument(..., help="ID of the collection to process"),
            steps: Optional[str] = typer.Option(None, "--steps", "-s", help="Comma-separated list of steps to process"),
            level: Optional[int] = typer.Option(None, "--level", "-l", help="Process specific level of hierarchy")
        ):
            """Process a collection through the director"""
            asyncio.run(self._process_collection(collection_id, steps, level))
        
        @app.command(name="status", help="Get processing status of a collection")
        def get_processing_status(
            collection_id: str = typer.Argument(..., help="ID of the collection")
        ):
            """Get processing status of a collection"""
            asyncio.run(self._get_processing_status(collection_id))
        
        @app.command(name="structure", help="Preview collection structure")
        def preview_structure(
            collection_id: str = typer.Argument(..., help="ID of the collection"),
            max_depth: int = typer.Option(3, "--depth", "-d", help="Maximum depth to show")
        ):
            """Preview collection structure"""
            asyncio.run(self._preview_structure(collection_id, max_depth))
    
    async def _list_processing_steps(self, collection_id: str, show_files: bool):
        """List processing steps for a collection"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            navigator = self.get_navigator_for_collection(collection)
            if not navigator:
                return
            
            available_steps = navigator.get_available_steps()
            
            if not available_steps:
                self.console.print("[yellow]No processing steps found in collection[/yellow]")
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
            
            self.console.print(table)
            
            if show_files:
                self.console.print("\n[bold]Files in each step:[/bold]")
                for step in available_steps:
                    outputs = navigator.get_step_outputs(step.name)
                    if outputs:
                        self.console.print(f"\n[cyan]{step.name}:[/cyan]")
                        for output in outputs[:10]:  # Show first 10 files
                            self.console.print(f"  • {output.name} ({output.file_type})")
                        if len(outputs) > 10:
                            self.console.print(f"  ... and {len(outputs) - 10} more files")
            
        except Exception as e:
            self.console.print(f"[red]Failed to list processing steps: {e}[/red]")
    
    async def _view_processing_step(self, collection_id: str, step_name: str, show_manifest: bool, show_progress: bool):
        """View details of a specific processing step"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            navigator = self.get_navigator_for_collection(collection)
            if not navigator:
                return
            
            if step_name not in navigator.steps:
                self.console.print(f"[red]Unknown processing step: {step_name}[/red]")
                self.console.print(f"Available steps: {', '.join(navigator.steps.keys())}")
                return
            
            step = navigator.steps[step_name]
            outputs = navigator.get_step_outputs(step_name)
            
            # Show step information
            self.console.print(f"\n[bold cyan]Processing Step: {step_name}[/bold cyan]")
            self.console.print(f"Description: {step.description}")
            self.console.print(f"Path: {Path(collection.local_path) / step.path}")
            self.console.print(f"File Types: {', '.join(step.file_types)}")
            self.console.print(f"Files: {len(outputs)}")
            
            if outputs:
                self.console.print(f"\n[bold]Files in {step_name}:[/bold]")
                table = Table()
                table.add_column("Name", style="cyan")
                table.add_column("Type", style="green")
                table.add_column("Size", justify="right", style="yellow")
                table.add_column("Modified", style="blue")
                
                for output in outputs:
                    size_str = format_file_size(output.size)
                    modified_str = output.modified.strftime("%Y-%m-%d %H:%M")
                    table.add_row(output.name, output.file_type, size_str, modified_str)
                
                self.console.print(table)
            
            # Show manifest if requested
            if show_manifest:
                manifest = navigator.get_step_manifest(step_name)
                if manifest:
                    self.console.print(f"\n[bold]Manifest ({manifest['count']} entries):[/bold]")
                    self.console.print(f"File: {manifest['file']}")
                    # Show first few entries
                    for i, entry in enumerate(manifest['entries'][:5]):
                        self.console.print(f"  {i+1}. {json.dumps(entry, indent=2)}")
                    if len(manifest['entries']) > 5:
                        self.console.print(f"  ... and {len(manifest['entries']) - 5} more entries")
                else:
                    self.console.print("[yellow]No manifest file found[/yellow]")
            
            # Show progress if requested
            if show_progress:
                progress = navigator.get_step_progress(step_name)
                if progress:
                    self.console.print(f"\n[bold]Progress ({progress['count']} entries):[/bold]")
                    self.console.print(f"File: {progress['file']}")
                    # Show first few entries
                    for i, entry in enumerate(progress['entries'][:5]):
                        self.console.print(f"  {i+1}. {json.dumps(entry, indent=2)}")
                    if len(progress['entries']) > 5:
                        self.console.print(f"  ... and {len(progress['entries']) - 5} more entries")
                else:
                    self.console.print("[yellow]No progress file found[/yellow]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to view processing step: {e}[/red]")
    
    async def _search_collection(self, collection_id: str, query: str, file_types: Optional[str]):
        """Search across all processing steps"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            navigator = self.get_navigator_for_collection(collection)
            if not navigator:
                return
            
            # Parse file types
            types_list = None
            if file_types:
                types_list = [t.strip() for t in file_types.split(',')]
            
            # Search
            results = navigator.search_across_steps(query, types_list)
            
            if not results:
                self.console.print(f"[yellow]No files found matching '{query}'[/yellow]")
                return
            
            self.console.print(f"\n[bold]Search Results for '{query}' ({len(results)} files):[/bold]")
            
            table = Table()
            table.add_column("Step", style="cyan")
            table.add_column("Name", style="magenta")
            table.add_column("Type", style="green")
            table.add_column("Size", justify="right", style="yellow")
            table.add_column("Path", style="white")
            
            for result in results:
                size_str = format_file_size(result.size)
                table.add_row(
                    result.step,
                    result.name,
                    result.file_type,
                    size_str,
                    str(result.path)
                )
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to search collection: {e}[/red]")
    
    async def _view_file(self, collection_id: str, step_name: str, file_name: str, max_lines: int):
        """View content of a specific file"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            navigator = self.get_navigator_for_collection(collection)
            if not navigator:
                return
            
            outputs = navigator.get_step_outputs(step_name)
            
            # Find the file
            target_file = None
            for output in outputs:
                if output.name == file_name:
                    target_file = output
                    break
            
            if not target_file:
                self.console.print(f"[red]File '{file_name}' not found in step '{step_name}'[/red]")
                return
            
            # Get content preview
            content = navigator.get_file_content_preview(target_file, max_lines)
            
            if content is None:
                self.console.print(f"[yellow]Cannot preview file type: {target_file.file_type}[/yellow]")
                return
            
            # Display content
            self.console.print(f"\n[bold]File: {file_name}[/bold]")
            self.console.print(f"Step: {step_name}")
            self.console.print(f"Type: {target_file.file_type}")
            self.console.print(f"Size: {format_file_size(target_file.size)}")
            self.console.print(f"Modified: {target_file.modified.strftime('%Y-%m-%d %H:%M')}")
            
            # Show content with syntax highlighting
            if target_file.file_type in ['.json', '.jsonl']:
                syntax = Syntax(content, "json", theme="monokai", line_numbers=True)
            elif target_file.file_type == '.txt':
                syntax = Syntax(content, "text", theme="monokai", line_numbers=True)
            else:
                syntax = Syntax(content, "text", theme="monokai", line_numbers=True)
            
            self.console.print(syntax)
            
        except Exception as e:
            self.console.print(f"[red]Failed to view file: {e}[/red]")
    
    async def _process_collection(self, collection_id: str, steps: Optional[str], level: Optional[int]):
        """Process a collection through the director"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                self.console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Parse steps
            steps_list = None
            if steps:
                steps_list = [s.strip() for s in steps.split(',')]
            
            # Process collection
            if level is not None:
                self.console.print(f"[blue]Processing collection at level {level}...[/blue]")
                result = await self.bridge.process_collection_level(collection_path, level)
            else:
                self.console.print(f"[blue]Processing collection...[/blue]")
                result = await self.bridge.process_collection(collection_path, steps_list)
            
            if result["success"]:
                self.console.print("[green]✅ Collection processed successfully![/green]")
                self.console.print(f"Processed steps: {result.get('processed_steps', 'N/A')}")
            else:
                self.console.print(f"[red]❌ Processing failed: {result.get('error', 'Unknown error')}[/red]")
            
        except Exception as e:
            self.console.print(f"[red]Failed to process collection: {e}[/red]")
    
    async def _get_processing_status(self, collection_id: str):
        """Get processing status of a collection"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                self.console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Get status
            status = await self.bridge.get_collection_processing_status(collection_path)
            
            self.console.print(f"\n[bold]Processing Status for {collection.name}[/bold]")
            self.console.print(f"Collection Path: {status['collection_path']}")
            self.console.print(f"Total Files: {status['total_files']}")
            self.console.print(f"Available Steps: {len(status['available_steps'])}")
            
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
            
            self.console.print(table)
            
        except Exception as e:
            self.console.print(f"[red]Failed to get processing status: {e}[/red]")
    
    async def _preview_structure(self, collection_id: str, max_depth: int):
        """Preview collection structure"""
        try:
            # Get collection
            collection = await self.get_collection_by_id(collection_id)
            if not collection:
                return
            
            collection_path = Path(collection.local_path) if collection.local_path else None
            if not collection_path or not collection_path.exists():
                self.console.print(f"[red]Collection path not found: {collection_path}[/red]")
                return
            
            # Get structure
            structure = await self.bridge.preview_collection_structure(collection_path, max_depth)
            
            self.console.print(f"\n[bold]Collection Structure for {collection.name}[/bold]")
            self.console.print(f"Max Depth: {max_depth}")
            
            # Build tree
            tree = Tree(f"[bold]{collection_path.name}[/bold]")
            build_tree_display(tree, structure['structure'], max_depth)
            self.console.print(tree)
            
        except Exception as e:
            self.console.print(f"[red]Failed to preview structure: {e}[/red]")
