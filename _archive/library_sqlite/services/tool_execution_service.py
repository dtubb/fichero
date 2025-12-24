"""
ToolExecutionService - Unified tool execution via library backend

Replaces the broken ToolExecutor. Follows crop's proven pattern:
- Uses current step as input (not last step!)
- Resolves paths via library backend
- Creates proper output folder structure
- Updates manifest files
- Saves to library database
"""

import logging
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionResult:
    """Result of tool execution via ToolExecutionService"""
    success: bool
    tool_name: str
    output_path: Optional[Path] = None
    manifest_path: Optional[Path] = None
    output_folder: Optional[Path] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class ToolExecutionService:
    """
    Unified service for executing tools via library backend.

    Follows crop's pattern:
    1. Get source from library backend (uses current step!)
    2. Execute tool
    3. Create proper output structure
    4. Update manifest file
    5. Save to library database

    All UI components (Adjust View, Tools Menu, Process button) use this service.
    """

    def __init__(self, library_manager):
        """
        Initialize tool execution service.

        Args:
            library_manager: LibraryManager instance for backend integration
        """
        self.library_manager = library_manager
        self.logger = logging.getLogger(__name__)

    async def execute_tool(
        self,
        item_id: str,
        tool_name: str,
        source_step_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> ToolExecutionResult:
        """
        Execute a tool on a specific step.

        This is the main entry point. All tool execution goes through here.

        Args:
            item_id: Item to process
            tool_name: Tool to run (e.g., 'crop', 'enhance', 'rotate')
            source_step_name: Step to use as input (e.g., 'crop', 'prepare_images')
            parameters: Tool-specific parameters (optional)

        Returns:
            ToolExecutionResult with success/failure and output paths

        Example:
            >>> result = await service.execute_tool(
            ...     item_id='abc-123',
            ...     tool_name='enhance',
            ...     source_step_name='crop',  # Use crop output as input
            ...     parameters={'method': 'auto'}
            ... )
            >>> if result.success:
            ...     print(f"Output: {result.output_path}")
        """
        start_time = datetime.now()
        self.logger.info(
            f"Executing tool '{tool_name}' on item {item_id}, "
            f"using source step '{source_step_name}'"
        )

        try:
            # 1. Get tool from registry
            tool = ToolRegistry.get_tool(tool_name)
            if not tool:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    error=f"Tool '{tool_name}' not found in registry. "
                          f"Available tools: {', '.join(ToolRegistry.list_tools())}"
                )

            # 2. Merge with default parameters
            params = tool.get_default_parameters()
            if parameters:
                params.update(parameters)

            # 3. Validate parameters
            is_valid, error = tool.validate_parameters(params)
            if not is_valid:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    error=f"Invalid parameters: {error}"
                )

            # 4. Get source data from library backend
            source_data = await self._get_source_data(item_id, source_step_name)
            if not source_data:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    error=f"Source step '{source_step_name}' not found for item {item_id}"
                )

            # 5. Resolve source path using library backend
            source_path = self._resolve_source_path(source_data)
            if not source_path or not source_path.exists():
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    error=f"Source file not found: {source_path}"
                )

            self.logger.info(f"Resolved source path: {source_path}")

            # 6. Create output structure (following Director's convention)
            output_folder, manifest_file = self._create_output_structure(
                item_id=item_id,
                tool=tool,
                source_filename=source_path.name
            )

            # 7. Determine output path
            output_filename = self._get_output_filename(
                source_path=source_path,
                tool=tool,
                parameters=params
            )
            output_path = output_folder / output_filename

            # 8. Execute the tool
            self.logger.info(f"Executing {tool_name}: {source_path} → {output_path}")
            tool_result = await tool.process(
                source_path=source_path,
                output_path=output_path,
                parameters=params
            )

            if not tool_result.success:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    error=tool_result.error or "Tool execution failed"
                )

            # 9. Create/update manifest file
            await self._update_manifest(
                manifest_file=manifest_file,
                tool=tool,
                source_path=source_path,
                output_path=output_path,
                parameters=params,
                tool_result=tool_result
            )

            # 10. Save to library database
            await self._save_to_library(
                item_id=item_id,
                tool=tool,
                output_folder=output_folder,
                manifest_file=manifest_file,
                parameters=params,
                tool_result=tool_result
            )

            # 11. Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()

            self.logger.info(
                f"✅ Tool '{tool_name}' completed successfully in {execution_time:.2f}s"
            )

            return ToolExecutionResult(
                success=True,
                tool_name=tool_name,
                output_path=output_path,
                manifest_path=manifest_file,
                output_folder=output_folder,
                execution_time=execution_time,
                metadata=tool_result.metadata
            )

        except Exception as e:
            self.logger.error(f"Tool execution failed: {e}", exc_info=True)
            execution_time = (datetime.now() - start_time).total_seconds()
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name,
                error=str(e),
                execution_time=execution_time
            )

    async def _get_source_data(self, item_id: str, step_name: str) -> Optional[Dict[str, Any]]:
        """
        Get source step data from library backend.

        Uses LibraryManager.get_step_data() which enriches manifests with source paths.

        Args:
            item_id: Item ID
            step_name: Step name (e.g., 'crop', 'prepare_images')

        Returns:
            Step data dictionary or None if not found
        """
        try:
            step_data = await self.library_manager.get_step_data(
                item_id=item_id,
                step_name=step_name
            )
            return step_data
        except Exception as e:
            self.logger.error(f"Failed to get source data: {e}")
            return None

    def _resolve_source_path(self, source_data: Dict[str, Any]) -> Optional[Path]:
        """
        Resolve source file path from step data.

        Library backend adds 'source_image_path' to manifest entries.
        This method extracts that path.

        Args:
            source_data: Step data from library backend

        Returns:
            Path to source file or None
        """
        # Get manifest data
        manifest_data = source_data.get('manifest_data')
        if not manifest_data:
            self.logger.warning("No manifest_data in source_data")
            return None

        # Get first manifest entry (for single-file tools)
        # TODO: Handle multi-file tools
        if isinstance(manifest_data, list) and manifest_data:
            manifest_entry = manifest_data[0]
        elif isinstance(manifest_data, dict):
            manifest_entry = manifest_data
        else:
            self.logger.warning(f"Unexpected manifest_data format: {type(manifest_data)}")
            return None

        # Get source_image_path (added by library backend)
        source_path = manifest_entry.get('source_image_path')
        if source_path:
            return Path(source_path)

        # Fallback: try to construct from file_path
        file_path = manifest_entry.get('file_path') or manifest_entry.get('path')
        if file_path:
            return Path(file_path)

        self.logger.warning("Could not resolve source path from manifest entry")
        return None

    def _create_output_structure(
        self,
        item_id: str,
        tool,
        source_filename: str
    ) -> tuple[Path, Path]:
        """
        Create output folder structure following Director's convention.

        Structure:
            library/collections/{collection_id}/outputs/
            └── YYYY-MM-DD_HH-MM-SS/
                └── Interactive_{tool_name}/
                    └── {item_name}/
                        └── assets/
                            └── {tool_folder}/
                                ├── {output_files}
                                └── {tool}_manifest.jsonl

        Args:
            item_id: Item ID
            tool: StandardTool instance
            source_filename: Source filename (for naming)

        Returns:
            Tuple of (output_folder, manifest_file)
        """
        # Get library database path
        db_path = Path(self.library_manager.storage.db_path)
        library_base = db_path.parent

        # Get item info for naming
        try:
            # Synchronous call - library_manager methods may not be async
            import asyncio
            if asyncio.iscoroutinefunction(self.library_manager.get_item):
                loop = asyncio.get_event_loop()
                item = loop.run_until_complete(self.library_manager.get_item(item_id))
            else:
                item = self.library_manager.get_item(item_id)
            item_name = item.name if item else item_id[:8]
        except Exception as e:
            self.logger.warning(f"Could not get item name: {e}")
            item_name = item_id[:8]

        # Create timestamped execution folder
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        workflow_name = f"Interactive_{tool.get_tool_name()}"

        # Build path
        output_base = library_base / "outputs" / timestamp / workflow_name / item_name
        assets_folder = output_base / "assets"
        tool_folder = assets_folder / tool.get_manifest_folder()

        # Create directories
        tool_folder.mkdir(parents=True, exist_ok=True)

        # Manifest file path
        manifest_file = tool_folder / f"{tool.get_tool_name()}_manifest.jsonl"

        self.logger.info(f"Created output structure: {tool_folder}")

        return tool_folder, manifest_file

    def _get_output_filename(
        self,
        source_path: Path,
        tool,
        parameters: Dict[str, Any]
    ) -> str:
        """
        Determine output filename based on tool and parameters.

        Args:
            source_path: Source file path
            tool: StandardTool instance
            parameters: Tool parameters

        Returns:
            Output filename
        """
        # Get output format from tool
        output_format = tool.get_output_format(parameters)

        # Use source filename with new extension
        stem = source_path.stem
        return f"{stem}.{output_format}"

    async def _update_manifest(
        self,
        manifest_file: Path,
        tool,
        source_path: Path,
        output_path: Path,
        parameters: Dict[str, Any],
        tool_result
    ):
        """
        Create or update manifest file with tool execution record.

        Follows JSONL format (one JSON object per line).

        Args:
            manifest_file: Path to manifest file
            tool: StandardTool instance
            source_path: Source file that was processed
            output_path: Output file that was created
            parameters: Parameters used
            tool_result: ToolResult from tool execution
        """
        try:
            # Create manifest entry using tool's method
            manifest_entry = tool.create_manifest_entry(
                source_path=source_path,
                output_path=output_path,
                parameters=parameters,
                result=tool_result
            )

            # Add execution metadata
            manifest_entry['execution_metadata'] = {
                'timestamp': datetime.now().isoformat(),
                'execution_mode': 'interactive',
                'service': 'ToolExecutionService'
            }

            # Write to manifest file (append mode)
            with open(manifest_file, 'a') as f:
                f.write(json.dumps(manifest_entry) + '\n')

            self.logger.info(f"Updated manifest: {manifest_file}")

        except Exception as e:
            self.logger.error(f"Failed to update manifest: {e}", exc_info=True)
            # Don't fail the whole operation if manifest update fails

    async def _save_to_library(
        self,
        item_id: str,
        tool,
        output_folder: Path,
        manifest_file: Path,
        parameters: Dict[str, Any],
        tool_result
    ):
        """
        Save tool execution to library database.

        Uses LibraryManager.add_processing_result() (same as Director uses).

        Args:
            item_id: Item ID
            tool: StandardTool instance
            output_folder: Output folder path
            manifest_file: Manifest file path
            parameters: Parameters used
            tool_result: ToolResult from tool execution

        Raises:
            RuntimeError: If saving to library database fails
        """
        try:
            # Get output base (parent of assets folder)
            output_base = output_folder.parent.parent

            self.logger.info(f"💾 Saving to library database:")
            self.logger.info(f"   - Item ID: {item_id}")
            self.logger.info(f"   - Workflow: Interactive_{tool.get_tool_name()}")
            self.logger.info(f"   - Status: success")
            self.logger.info(f"   - Output path: {output_base}")

            # Call library manager to save
            result_id = await self.library_manager.add_processing_result(
                item_id=item_id,
                workflow=f"Interactive_{tool.get_tool_name()}",
                status="success",
                output_paths=[str(output_base)],
                metadata={
                    'steps': [{
                        'step_name': tool.get_tool_name(),
                        'status': 'completed',
                        'manifest_path': str(manifest_file),
                        'manifest_folder': tool.get_manifest_folder(),
                        'tool_parameters': parameters,
                        'execution_mode': 'interactive',
                        'timestamp': datetime.now().isoformat(),
                    }],
                    'execution_service': 'ToolExecutionService',
                    'tool_metadata': tool_result.metadata
                }
            )

            if result_id:
                self.logger.info(f"✅ Successfully saved to library database (result_id: {result_id})")
            else:
                # add_processing_result returned None, which means it failed
                raise RuntimeError("add_processing_result() returned None (save failed)")

        except Exception as e:
            self.logger.error(f"❌ Failed to save to library database: {e}", exc_info=True)
            self.logger.error(f"   Context: item={item_id}, tool={tool.get_tool_name()}, output={output_base}")
            # Re-raise so caller knows the operation failed
            raise RuntimeError(f"Failed to save processing result to library: {e}") from e

    def get_available_tools(self) -> list[str]:
        """
        Get list of available tools.

        Returns:
            List of tool names
        """
        return ToolRegistry.list_tools()

    def is_tool_available(self, tool_name: str) -> bool:
        """
        Check if a tool is available.

        Args:
            tool_name: Tool identifier

        Returns:
            True if tool is registered
        """
        return ToolRegistry.is_registered(tool_name)

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a tool.

        Args:
            tool_name: Tool identifier

        Returns:
            Tool info dictionary or None if not found
        """
        tool = ToolRegistry.get_tool(tool_name)
        if not tool:
            return None

        return {
            'name': tool.get_tool_name(),
            'manifest_folder': tool.get_manifest_folder(),
            'supports_batch': tool.supports_batch_processing(),
            'supported_formats': tool.get_supported_input_formats(),
            'default_parameters': tool.get_default_parameters()
        }
