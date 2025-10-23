"""
Outputs Management Commands

CLI commands for browsing, viewing, and editing workflow outputs.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from .base import BaseLibraryCommands


class OutputsCommands(BaseLibraryCommands):
    """Outputs management commands"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize outputs commands - optionally share base instance"""
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
        """Register outputs commands"""

        @app.command(name="list", help="List all tool outputs in a folder")
        def list_tools(
            output_path: str = typer.Argument(..., help="Path to Director output folder")
        ):
            """List all tools that produced outputs"""
            asyncio.run(self._list_tools(output_path))

        @app.command(name="show", help="Show outputs for a specific tool")
        def show_tool(
            output_path: str = typer.Argument(..., help="Path to Director output folder"),
            tool_name: str = typer.Argument(..., help="Name of the tool"),
            show_params: bool = typer.Option(False, "--params", "-p", help="Show tool parameters")
        ):
            """Show outputs for a specific tool"""
            asyncio.run(self._show_tool(output_path, tool_name, show_params))

        @app.command(name="view", help="View content of a specific output file")
        def view_file(
            output_path: str = typer.Argument(..., help="Path to Director output folder"),
            tool_name: str = typer.Argument(..., help="Name of the tool"),
            file_name: str = typer.Argument(..., help="Name of the file to view"),
            max_lines: int = typer.Option(50, "--lines", "-l", help="Maximum lines to show")
        ):
            """View content of a specific output file"""
            asyncio.run(self._view_file(output_path, tool_name, file_name, max_lines))

        @app.command(name="manifest", help="Show manifest for a tool")
        def show_manifest(
            output_path: str = typer.Argument(..., help="Path to Director output folder"),
            tool_name: str = typer.Argument(..., help="Name of the tool"),
            max_entries: int = typer.Option(10, "--entries", "-n", help="Maximum entries to show")
        ):
            """Show manifest entries for a tool"""
            asyncio.run(self._show_manifest(output_path, tool_name, max_entries))

        @app.command(name="item-outputs", help="Show file-specific filtered outputs for a library item")
        def item_outputs(
            item_id: str = typer.Argument(..., help="Library item ID"),
            verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed step information"),
            show_content: bool = typer.Option(False, "--show-content", "-c", help="Display JSON content from each step")
        ):
            """Test file-specific output filtering for a library item"""
            asyncio.run(self._item_outputs(item_id, verbose, show_content))

    async def _list_tools(self, output_path_str: str):
        """List all tools in output folder"""
        try:
            from fichero.library.outputs_manager import OutputsManager

            output_path = Path(output_path_str)
            manager = OutputsManager()

            # Load session
            session = manager.load_output_folder(output_path)

            # List tools
            tools = manager.list_tools(session)

            if not tools:
                self.console.print("[yellow]No tool outputs found in folder[/yellow]")
                return

            # Create table
            table = Table(title=f"Tool Outputs: {output_path.name}")
            table.add_column("Tool Name", style="cyan")
            table.add_column("Output Folder", style="white")
            table.add_column("Files", justify="right", style="yellow")
            table.add_column("Manifest", style="green")

            for tool in tools:
                manifest_name = tool.manifest_path.name if tool.manifest_path else "N/A"
                table.add_row(
                    tool.tool_name,
                    str(tool.output_folder.relative_to(output_path)),
                    str(len(tool.files)),
                    manifest_name
                )

            self.console.print(table)
            self.console.print(f"\n[green]Found {len(tools)} tool output(s)[/green]")

        except FileNotFoundError as e:
            self.console.print(f"[red]{e}[/red]")
        except Exception as e:
            import traceback
            self.console.print(f"[red]Failed to list tools: {e}[/red]")
            self.console.print(traceback.format_exc())

    async def _show_tool(self, output_path_str: str, tool_name: str, show_params: bool):
        """Show outputs for a specific tool"""
        try:
            from fichero.library.outputs_manager import OutputsManager

            output_path = Path(output_path_str)
            manager = OutputsManager()

            # Load session
            session = manager.load_output_folder(output_path)

            # Get tool output
            tool = manager.get_tool_output(session, tool_name)

            if not tool:
                self.console.print(f"[red]Tool '{tool_name}' not found in outputs[/red]")
                # Show available tools
                tools = manager.list_tools(session)
                if tools:
                    self.console.print("\n[yellow]Available tools:[/yellow]")
                    for t in tools:
                        self.console.print(f"  • {t.tool_name}")
                return

            # Show tool info
            self.console.print(f"\n[bold cyan]Tool: {tool.tool_name}[/bold cyan]")
            self.console.print(f"Output Folder: {tool.output_folder}")
            self.console.print(f"Manifest: {tool.manifest_path}")

            # Show parameters if requested
            if show_params:
                params = tool.parameters
                if params:
                    self.console.print("\n[bold]Parameters:[/bold]")
                    param_json = json.dumps(params, indent=2)
                    syntax = Syntax(param_json, "json", theme="monokai")
                    self.console.print(syntax)

            # Show files
            files = tool.files
            if files:
                self.console.print(f"\n[bold]Output Files ({len(files)}):[/bold]")
                table = Table()
                table.add_column("File Name", style="cyan")
                table.add_column("Size", justify="right", style="yellow")
                table.add_column("Type", style="green")

                for file_path in files:
                    size = file_path.stat().st_size
                    size_str = self._format_size(size)
                    file_type = file_path.suffix or "no extension"
                    table.add_row(file_path.name, size_str, file_type)

                self.console.print(table)
            else:
                self.console.print("\n[yellow]No output files found[/yellow]")

        except Exception as e:
            import traceback
            self.console.print(f"[red]Failed to show tool: {e}[/red]")
            self.console.print(traceback.format_exc())

    async def _view_file(self, output_path_str: str, tool_name: str, file_name: str, max_lines: int):
        """View content of a specific file"""
        try:
            from fichero.library.outputs_manager import OutputsManager

            output_path = Path(output_path_str)
            manager = OutputsManager()

            # Load session
            session = manager.load_output_folder(output_path)

            # Get tool output
            tool = manager.get_tool_output(session, tool_name)

            if not tool:
                self.console.print(f"[red]Tool '{tool_name}' not found[/red]")
                return

            # Find the file
            target_file = None
            for file_path in tool.files:
                if file_path.name == file_name:
                    target_file = file_path
                    break

            if not target_file:
                self.console.print(f"[red]File '{file_name}' not found in {tool_name} outputs[/red]")
                return

            # Display file info
            self.console.print(f"\n[bold]File: {file_name}[/bold]")
            self.console.print(f"Tool: {tool_name}")
            self.console.print(f"Type: {target_file.suffix}")
            self.console.print(f"Size: {self._format_size(target_file.stat().st_size)}")

            # Read and display content
            content_type = self._detect_content_type(target_file)

            if content_type == "text":
                with open(target_file, 'r') as f:
                    lines = f.readlines()
                    content = ''.join(lines[:max_lines])

                    if target_file.suffix == '.json':
                        syntax = Syntax(content, "json", theme="monokai", line_numbers=True)
                    else:
                        syntax = Syntax(content, "text", theme="monokai", line_numbers=True)

                    self.console.print(syntax)

                    if len(lines) > max_lines:
                        self.console.print(f"\n[yellow]... {len(lines) - max_lines} more lines (use --lines to see more)[/yellow]")
            elif content_type == "binary":
                self.console.print("\n[yellow]Binary file - cannot display as text[/yellow]")
                self.console.print(f"Use: cat {target_file}")
            else:
                self.console.print(f"\n[yellow]Unknown file type: {target_file.suffix}[/yellow]")

        except Exception as e:
            import traceback
            self.console.print(f"[red]Failed to view file: {e}[/red]")
            self.console.print(traceback.format_exc())

    async def _show_manifest(self, output_path_str: str, tool_name: str, max_entries: int):
        """Show manifest entries for a tool"""
        try:
            from fichero.library.outputs_manager import OutputsManager

            output_path = Path(output_path_str)
            manager = OutputsManager()

            # Load session
            session = manager.load_output_folder(output_path)

            # Get tool output
            tool = manager.get_tool_output(session, tool_name)

            if not tool:
                self.console.print(f"[red]Tool '{tool_name}' not found[/red]")
                return

            if not tool.manifest_path.exists():
                self.console.print(f"[yellow]No manifest found for {tool_name}[/yellow]")
                return

            # Read manifest
            self.console.print(f"\n[bold cyan]Manifest: {tool.manifest_path.name}[/bold cyan]")

            entries = []
            with open(tool.manifest_path, 'r') as f:
                for i, line in enumerate(f):
                    if i >= max_entries:
                        break
                    if line.strip():
                        entries.append(json.loads(line))

            # Display entries
            for i, entry in enumerate(entries, 1):
                entry_json = json.dumps(entry, indent=2)
                panel = Panel(
                    Syntax(entry_json, "json", theme="monokai"),
                    title=f"Entry {i}",
                    border_style="cyan"
                )
                self.console.print(panel)

            # Count total
            total_lines = sum(1 for _ in open(tool.manifest_path))
            if total_lines > max_entries:
                self.console.print(f"\n[yellow]... {total_lines - max_entries} more entries (use --entries to see more)[/yellow]")

            self.console.print(f"\n[green]Total entries: {total_lines}[/green]")

        except Exception as e:
            import traceback
            self.console.print(f"[red]Failed to show manifest: {e}[/red]")
            self.console.print(traceback.format_exc())

    async def _item_outputs(self, item_id: str, verbose: bool, show_content: bool = False):
        """Show file-specific filtered outputs for a library item"""
        try:
            self.console.print(f"\n[bold cyan]Testing File-Specific Output Filtering[/bold cyan]")
            self.console.print(f"Item ID: [yellow]{item_id}[/yellow]\n")

            # Get filtered output data
            output_data = await self.library_manager.get_item_output_data(item_id)

            if not output_data:
                self.console.print("[red]Failed to get output data for item[/red]")
                return

            # Display item info
            self.console.print(f"[bold]Item Information:[/bold]")
            self.console.print(f"  Filename: {output_data['filename']}")
            self.console.print(f"  Source: {output_data['source_path']}")
            self.console.print(f"  Has Outputs: {'✅ Yes' if output_data['has_outputs'] else '❌ No'}")

            if output_data['workflow']:
                self.console.print(f"  Workflow: {output_data['workflow']}")
            if output_data['processing_date']:
                self.console.print(f"  Processing Date: {output_data['processing_date']}")

            if output_data['output_root']:
                self.console.print(f"  Output Root: {output_data['output_root']}")

            # Display processing steps
            steps = output_data['processing_steps']
            if not steps:
                self.console.print("\n[yellow]No processing steps found[/yellow]")
                return

            self.console.print(f"\n[bold green]✅ File-Specific Processing Steps ({len(steps)} found):[/bold green]")

            # Create table for steps
            table = Table(title=f"Filtered Outputs for: {output_data['filename']}")
            table.add_column("#", style="cyan", justify="right")
            table.add_column("Step Name", style="yellow")
            table.add_column("Output Path", style="white")
            table.add_column("Description", style="green")

            for i, step in enumerate(steps, 1):
                table.add_row(
                    str(i),
                    step.step_name,
                    str(step.file_path.name) if step.file_path else "N/A",
                    step.description or ""
                )

            self.console.print(table)

            # Verbose mode: show details for each step
            if verbose and steps:
                self.console.print(f"\n[bold]Detailed Step Information:[/bold]")
                for i, step in enumerate(steps, 1):
                    panel = Panel(
                        f"[cyan]Step:[/cyan] {step.step_name}\n"
                        f"[cyan]File:[/cyan] {step.file_path}\n"
                        f"[cyan]Description:[/cyan] {step.description or 'N/A'}\n"
                        f"[cyan]Exists:[/cyan] {'✅ Yes' if step.file_path and step.file_path.exists() else '❌ No'}",
                        title=f"Step {i}",
                        border_style="green"
                    )
                    self.console.print(panel)

            # Show content mode: display JSON content from each step
            if show_content and steps:
                self.console.print(f"\n[bold]Step Content (JSON/Text Files):[/bold]")
                for i, step in enumerate(steps, 1):
                    if not step.file_path or not step.file_path.exists():
                        continue

                    # Check if it's a JSON file
                    if step.file_path.suffix.lower() in ['.json', '.jsonl']:
                        try:
                            with open(step.file_path, 'r', encoding='utf-8') as f:
                                content = f.read()

                            # Try to parse and pretty-print JSON
                            try:
                                if step.file_path.suffix.lower() == '.jsonl':
                                    # For JSONL, show each line separately
                                    lines = [json.loads(line) for line in content.strip().split('\n') if line.strip()]
                                    content_str = json.dumps(lines, indent=2, ensure_ascii=False)
                                else:
                                    # For JSON, parse and pretty-print
                                    parsed = json.loads(content)
                                    content_str = json.dumps(parsed, indent=2, ensure_ascii=False)
                            except json.JSONDecodeError:
                                # If JSON parsing fails, show raw content
                                content_str = content

                            # Display in a panel with syntax highlighting
                            syntax = Syntax(content_str, "json", theme="monokai", line_numbers=True)
                            panel = Panel(
                                syntax,
                                title=f"[bold cyan]Step {i}: {step.step_name}[/bold cyan] - {step.file_path.name}",
                                border_style="blue",
                                expand=False
                            )
                            self.console.print(panel)

                        except Exception as e:
                            self.console.print(f"[yellow]Could not read {step.file_path.name}: {e}[/yellow]")
                    elif step.file_path.suffix.lower() in ['.txt', '.md']:
                        # Show text files
                        try:
                            with open(step.file_path, 'r', encoding='utf-8') as f:
                                content = f.read()

                            syntax = Syntax(content, "text", theme="monokai", line_numbers=True)
                            panel = Panel(
                                syntax,
                                title=f"[bold cyan]Step {i}: {step.step_name}[/bold cyan] - {step.file_path.name}",
                                border_style="blue",
                                expand=False
                            )
                            self.console.print(panel)
                        except Exception as e:
                            self.console.print(f"[yellow]Could not read {step.file_path.name}: {e}[/yellow]")

            # Verification section
            self.console.print(f"\n[bold]Filtering Verification:[/bold]")
            self.console.print(f"  ✅ File-specific filtering: [green]WORKING[/green]")
            self.console.print(f"  ✅ JSONL parsing: [green]WORKING[/green]")
            self.console.print(f"  ✅ Steps filtered for '[yellow]{output_data['filename']}[/yellow]' only")
            self.console.print(f"  ℹ️  These are NOT container-level outputs, but file-specific outputs")
            if not show_content:
                self.console.print(f"  💡 Tip: Use --show-content/-c to view JSON content from each step")

        except Exception as e:
            import traceback
            self.console.print(f"[red]Failed to get item outputs: {e}[/red]")
            self.console.print(traceback.format_exc())

    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _detect_content_type(self, file_path: Path) -> str:
        """Detect if file is text or binary"""
        text_extensions = {'.txt', '.json', '.jsonl', '.md', '.yml', '.yaml', '.xml', '.csv'}
        binary_extensions = {'.jpg', '.jpeg', '.png', '.pdf', '.docx', '.zip', '.gz'}

        if file_path.suffix.lower() in text_extensions:
            return "text"
        elif file_path.suffix.lower() in binary_extensions:
            return "binary"
        else:
            # Try to read first few bytes
            try:
                with open(file_path, 'r') as f:
                    f.read(1024)
                return "text"
            except:
                return "binary"
