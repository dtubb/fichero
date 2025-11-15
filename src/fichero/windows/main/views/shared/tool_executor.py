"""
ToolExecutor - Executes processing tools on library items

Connects AdjustView tool buttons to the Director backend.
Handles:
- Finding last completed step as input
- Running tool via Director
- Creating new step with output
- Updating UI
"""
import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of tool execution"""
    success: bool
    tool_name: str
    output_folder: Optional[Path] = None
    output_manifest: Optional[Path] = None
    error_message: str = ""
    step_index: int = -1


class ToolExecutor:
    """
    Executes processing tools on library items.

    Bridges the gap between UI (AdjustView) and backend (Director).
    """

    def __init__(self, library_manager, step_manager):
        """
        Initialize tool executor.

        Args:
            library_manager: LibraryManager instance
            step_manager: StepManager instance
        """
        self.library_manager = library_manager
        self.step_manager = step_manager
        self.logger = logging.getLogger(__name__)

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute a processing tool on the current item.

        Args:
            tool_name: Tool to run (e.g., 'crop', 'rotate')
            parameters: Tool parameters

        Returns:
            ToolResult with success/failure info
        """
        self.logger.info(f"Executing tool: {tool_name} with params {parameters}")

        try:
            # 1. Get current item
            if not self.step_manager.current_item_id:
                return ToolResult(
                    success=False,
                    tool_name=tool_name,
                    error_message="No item selected"
                )

            item_id = self.step_manager.current_item_id

            # 2. Get last completed step as input
            last_step = self._get_last_step()
            if not last_step:
                return ToolResult(
                    success=False,
                    tool_name=tool_name,
                    error_message="No input step found"
                )

            input_path = last_step.file_path
            self.logger.info(f"Input: {input_path}")

            # 3. Determine output path
            output_folder = self._get_output_folder(item_id, tool_name)
            output_folder.mkdir(parents=True, exist_ok=True)

            # 4. Execute the tool
            success = await self._run_tool(
                tool_name=tool_name,
                input_path=input_path,
                output_folder=output_folder,
                parameters=parameters
            )

            if not success:
                return ToolResult(
                    success=False,
                    tool_name=tool_name,
                    error_message=f"Tool {tool_name} failed"
                )

            # 5. Find output file
            output_file = self._find_output_file(output_folder, input_path)
            if not output_file:
                return ToolResult(
                    success=False,
                    tool_name=tool_name,
                    error_message="No output file generated"
                )

            # 6. Create new step
            await self._add_step_to_library(
                item_id=item_id,
                tool_name=tool_name,
                output_path=output_file,
                parameters=parameters
            )

            # 7. Reload steps
            await self.step_manager.load_item(item_id)

            return ToolResult(
                success=True,
                tool_name=tool_name,
                output_folder=output_folder,
                step_index=len(self.step_manager.steps) - 1
            )

        except Exception as e:
            self.logger.error(f"Tool execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                tool_name=tool_name,
                error_message=str(e)
            )

    def _get_last_step(self):
        """Get the most recent completed step"""
        if not self.step_manager.steps:
            return None
        return self.step_manager.steps[-1]

    def _get_output_folder(self, item_id: str, tool_name: str) -> Path:
        """Determine output folder for tool"""
        # Get the library database path
        db_path = Path(self.library_manager.storage.db_path)
        cache_base = db_path.parent / "cache"

        # Store in library cache under item
        item_cache_dir = cache_base / item_id
        item_cache_dir.mkdir(parents=True, exist_ok=True)

        output_dir = item_cache_dir / tool_name
        return output_dir

    async def _run_tool(self, tool_name: str, input_path: Path,
                       output_folder: Path, parameters: Dict[str, Any]) -> bool:
        """
        Actually run the tool.

        For now, this is a simplified version that imports and calls the tool directly.
        TODO: Route through Director for proper workflow management
        """
        self.logger.info(f"Running {tool_name} on {input_path}")

        try:
            if tool_name == 'crop':
                return await self._run_crop(input_path, output_folder, parameters)
            elif tool_name == 'rotate':
                return await self._run_rotate(input_path, output_folder, parameters)
            elif tool_name == 'enhance':
                return await self._run_enhance(input_path, output_folder, parameters)
            else:
                self.logger.warning(f"Tool {tool_name} not yet implemented")
                return False

        except Exception as e:
            self.logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return False

    async def _run_crop(self, input_path: Path, output_folder: Path,
                       parameters: Dict[str, Any]) -> bool:
        """Run crop tool"""
        from fichero.tools.crop import process_image, get_contour_template, ContourSettings

        # Get template from parameters
        template_name = parameters.get('contour_template', 'auto')
        padding = parameters.get('contour_padding', 30)

        # Load template settings
        try:
            template = get_contour_template(template_name)
            if template['settings']:
                # Use template settings
                settings = template['settings']
                # Override padding if specified
                if padding != 30:
                    settings.padding = padding
            else:
                # Custom - use defaults
                settings = ContourSettings(padding=padding)
        except Exception as e:
            self.logger.warning(f"Failed to load template {template_name}: {e}, using defaults")
            settings = ContourSettings(padding=padding)

        # Determine output filename
        output_path = output_folder / input_path.name

        # Run in thread pool to avoid blocking UI
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            process_image,
            input_path,
            output_path,
            'jpg',
            settings
        )

        return result.get('success', False) if result else False

    async def _run_rotate(self, input_path: Path, output_folder: Path,
                         parameters: Dict[str, Any]) -> bool:
        """Run rotate tool"""
        from fichero.tools.rotate import process_image

        output_path = output_folder / input_path.name

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            process_image,
            input_path,
            output_path,
            'jpg'
        )

        return result.get('success', False) if result else False

    async def _run_enhance(self, input_path: Path, output_folder: Path,
                          parameters: Dict[str, Any]) -> bool:
        """Run enhance tool"""
        from fichero.tools.enhance import process_image

        output_path = output_folder / input_path.name

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            process_image,
            input_path,
            output_path,
            'jpg'
        )

        return result.get('success', False) if result else False

    def _find_output_file(self, output_folder: Path, input_path: Path) -> Optional[Path]:
        """Find the output file generated by the tool"""
        # Look for file with same name as input
        expected = output_folder / input_path.name
        if expected.exists():
            return expected

        # Look for any image file
        for ext in ['.jpg', '.png', '.tiff', '.tif']:
            candidate = output_folder / f"{input_path.stem}{ext}"
            if candidate.exists():
                return candidate

        # Look for first file in output folder
        files = list(output_folder.glob('*'))
        if files:
            return files[0]

        return None

    async def _add_step_to_library(self, item_id: str, tool_name: str,
                                   output_path: Path, parameters: Dict[str, Any]):
        """Add the tool output as a new step in the library"""
        # For now, just log - LibraryManager will pick it up when we reload
        self.logger.info(f"Adding step {tool_name} to item {item_id}: {output_path}")

        # TODO: Properly register the step with LibraryManager
        # This might involve calling library_manager.add_processing_output(item_id, tool_name, output_path, parameters)
