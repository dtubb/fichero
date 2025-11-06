"""
Step Management CLI Commands

Commands for viewing and editing workflow step outputs
"""

import typer
import asyncio
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel
from typing import Optional

from .base import BaseLibraryCommands

console = Console()


class StepCommands(BaseLibraryCommands):
    """Step viewing and editing commands"""

    def __init__(self, app_initializer=None, base_commands=None):
        """Initialize step commands - optionally share base instance"""
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

    def view_step(
        self,
        item_id: str = typer.Argument(..., help="Item ID"),
        step_index: int = typer.Option(..., "--step", "-s", help="Step index (0-based)"),
        show_content: bool = typer.Option(True, "--content/--no-content", help="Show file content"),
        output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file")
    ):
        """
        View a specific processing step's data

        Example:
            fichero library view-step abc123 --step 2
            fichero library view-step abc123 --step 0 --output step0.json
        """
        async def _view():
            try:
                # Get step editor
                step_editor = self._get_step_editor()

                # Get step data
                console.print(f"[blue]Loading step {step_index} for item {item_id}...[/blue]")
                step_data = await step_editor.get_step_data(item_id, step_index)

                if not step_data:
                    console.print(f"[red]Step not found or error loading step data[/red]")
                    raise typer.Exit(1)

                # Display step information
                self._display_step_info(step_data, show_content)

                # Save to file if requested
                if output_file:
                    output_path = Path(output_file)
                    step_dict = step_data.to_dict()
                    output_path.write_text(json.dumps(step_dict, indent=2, ensure_ascii=False))
                    console.print(f"[green]Step data saved to {output_path}[/green]")

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1)

        asyncio.run(_view())

    def edit_step_text(
        self,
        item_id: str = typer.Argument(..., help="Item ID"),
        step_index: int = typer.Option(..., "--step", "-s", help="Step index (0-based)"),
        input_file: str = typer.Option(..., "--file", "-f", help="Text file with new content")
    ):
        """
        Edit text content for a step

        Example:
            fichero library edit-step-text abc123 --step 2 --file edited.txt
        """
        async def _edit():
            try:
                # Get step editor
                step_editor = self._get_step_editor()

                # Read new content
                new_text = Path(input_file).read_text(encoding='utf-8')

                console.print(f"[blue]Saving edited text for step {step_index}...[/blue]")
                success = await step_editor.save_step_text(item_id, step_index, new_text)

                if success:
                    console.print(f"[green]Successfully saved text edits[/green]")
                else:
                    console.print(f"[red]Failed to save text edits[/red]")
                    raise typer.Exit(1)

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1)

        asyncio.run(_edit())

    def edit_step_json(
        self,
        item_id: str = typer.Argument(..., help="Item ID"),
        step_index: int = typer.Option(..., "--step", "-s", help="Step index (0-based)"),
        input_file: str = typer.Option(..., "--file", "-f", help="JSON file with new content")
    ):
        """
        Edit JSON content for a step

        Example:
            fichero library edit-step-json abc123 --step 3 --file edited.json
        """
        async def _edit():
            try:
                # Get step editor
                step_editor = self._get_step_editor()

                # Read new content
                new_json = json.loads(Path(input_file).read_text(encoding='utf-8'))

                console.print(f"[blue]Saving edited JSON for step {step_index}...[/blue]")
                success = await step_editor.save_step_json(item_id, step_index, new_json)

                if success:
                    console.print(f"[green]Successfully saved JSON edits[/green]")
                else:
                    console.print(f"[red]Failed to save JSON edits[/red]")
                    raise typer.Exit(1)

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1)

        asyncio.run(_edit())

    def list_steps(
        self,
        item_id: str = typer.Argument(..., help="Item ID")
    ):
        """
        List all processing steps for an item

        Example:
            fichero library list-steps abc123
        """
        async def _list():
            try:
                # Get output data
                output_data = await self.library_manager.get_item_output_data(item_id)

                if not output_data or not output_data.get('processing_steps'):
                    console.print(f"[yellow]No processing steps found for item {item_id}[/yellow]")
                    return

                # Create table
                table = Table(title=f"Processing Steps for {item_id}")
                table.add_column("Index", style="cyan", justify="right")
                table.add_column("Step Name", style="magenta")
                table.add_column("File Type", style="green")
                table.add_column("File Path", style="blue")

                for i, step in enumerate(output_data['processing_steps']):
                    table.add_row(
                        str(i),
                        step.step_name,
                        step.file_type,
                        str(step.file_path)
                    )

                console.print(table)

            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1)

        asyncio.run(_list())

    def _get_step_editor(self):
        """Get or create step editor instance"""
        if not hasattr(self.library_manager, 'step_editor'):
            from fichero.library.step_editor import StepEditor
            self.library_manager.step_editor = StepEditor(self.library_manager)
        return self.library_manager.step_editor

    def _display_step_info(self, step_data, show_content: bool = True):
        """Display step information using the renderer system"""
        from fichero.library.renderers import RendererRegistry

        # Create render context
        render_context = self._get_step_editor().create_render_context(
            step_data,
            show_metadata=True,
            show_content=show_content,
            interactive=False  # CLI mode
        )

        # Get appropriate renderer
        renderer = RendererRegistry.get_renderer_for_step(
            tool_name=step_data.tool_name,
            file_type=step_data.file_type,
            file_path=step_data.file_path
        )

        # Render in CLI mode
        output = renderer.render_cli(render_context)

        if output.is_error:
            console.print(f"[red]Error rendering step: {output.error}[/red]")
            return

        # Display rendered output
        if output.text:
            console.print(output.text)

    def register_commands(self, app):
        """Register step viewing and editing commands"""

        @app.command(name="view-step", help="View a specific processing step's data")
        def view_step(
            item_id: str = typer.Argument(..., help="Item ID"),
            step_index: int = typer.Option(..., "--step", "-s", help="Step index (0-based)"),
            show_content: bool = typer.Option(True, "--content/--no-content", help="Show file content"),
            output_file: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file")
        ):
            """View a specific processing step's data"""
            self.view_step(item_id, step_index, show_content, output_file)

        @app.command(name="edit-step-text", help="Edit text content for a step")
        def edit_step_text(
            item_id: str = typer.Argument(..., help="Item ID"),
            step_index: int = typer.Option(..., "--step", "-s", help="Step index (0-based)"),
            input_file: str = typer.Option(..., "--file", "-f", help="Text file with new content")
        ):
            """Edit text content for a step"""
            self.edit_step_text(item_id, step_index, input_file)

        @app.command(name="edit-step-json", help="Edit JSON content for a step")
        def edit_step_json(
            item_id: str = typer.Argument(..., help="Item ID"),
            step_index: int = typer.Option(..., "--step", "-s", help="Step index (0-based)"),
            input_file: str = typer.Option(..., "--file", "-f", help="JSON file with new content")
        ):
            """Edit JSON content for a step"""
            self.edit_step_json(item_id, step_index, input_file)

        @app.command(name="list-steps", help="List all processing steps for an item")
        def list_steps(
            item_id: str = typer.Argument(..., help="Item ID")
        ):
            """List all processing steps for an item"""
            self.list_steps(item_id)
