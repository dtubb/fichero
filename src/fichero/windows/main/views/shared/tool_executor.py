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

        Routes to specific tool execution methods via dynamic dispatch.
        """
        self.logger.info(f"Running {tool_name} on {input_path}")

        try:
            # Dynamic method dispatch for all 20 tools
            method_name = f"_run_{tool_name}"
            if not hasattr(self, method_name):
                self.logger.warning(f"Tool {tool_name} not yet implemented in ToolExecutor")
                return False

            method = getattr(self, method_name)
            return await method(input_path, output_folder, parameters)

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

        # Run in thread pool to avoid blocking UI (CRITICAL-5: Use asyncio.to_thread)
        result = await asyncio.to_thread(
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

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
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

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            process_image,
            input_path,
            output_path,
            'jpg'
        )

        return result.get('success', False) if result else False

    async def _run_split(self, input_path: Path, output_folder: Path,
                        parameters: Dict[str, Any]) -> bool:
        """Run split tool"""
        from fichero.tools.split import process_image

        output_path = output_folder / input_path.name
        output_format = parameters.get('output_format', 'jpg')
        disable_splitting = parameters.get('disable_splitting', False)

        result = await asyncio.to_thread(
            process_image,
            input_path,
            output_path,
            output_format,
            disable_splitting
        )

        # CRITICAL-6: Fix return value structure (split returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_remove_background(self, input_path: Path, output_folder: Path,
                                    parameters: Dict[str, Any]) -> bool:
        """Run remove_background tool"""
        from fichero.tools.remove_background import process_image

        output_path = output_folder / input_path.name
        output_format = parameters.get('output_format', 'png')
        # MAJOR-3: Fix parameter values ('ai' and 'opencv', not 'rembg')
        method = parameters.get('method', 'opencv')
        ai_model = parameters.get('ai_model', 'u2net')

        result = await asyncio.to_thread(
            process_image,
            input_path,
            output_path,
            output_format,
            method,
            ai_model
        )

        # CRITICAL-6: Fix return value structure (remove_background returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_prepare_images(self, input_path: Path, output_folder: Path,
                                 parameters: Dict[str, Any]) -> bool:
        """Run prepare_images tool"""
        from fichero.tools.prepare_images import process_image

        output_path = output_folder / input_path.name
        output_format = parameters.get('output_format', 'jpg')
        # MAJOR-2: Fix default compression_quality (95 → 85)
        compression_quality = parameters.get('compression_quality', 85)

        result = await asyncio.to_thread(
            process_image,
            input_path,
            output_path,
            output_format,
            compression_quality
        )

        # CRITICAL-6: Fix return value structure (prepare_images returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_segment(self, input_path: Path, output_folder: Path,
                          parameters: Dict[str, Any]) -> bool:
        """Run segment tool"""
        from fichero.tools.segment import process_image

        output_path = output_folder / input_path.name

        result = await asyncio.to_thread(
            process_image,
            input_path,
            output_path
        )

        # CRITICAL-6: Fix return value structure (segment returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_convert_to_svg(self, input_path: Path, output_folder: Path,
                                 parameters: Dict[str, Any]) -> bool:
        """
        Run convert_to_svg tool

        CRITICAL-1: This tool requires both image and transcription data.
        For single-item execution, transcription_folder and transcription_manifest
        must be provided in parameters.
        """
        from fichero.tools.convert_to_svg import convert_to_svg_batch
        import tempfile
        import json
        import os

        # CRITICAL-1: Check for required transcription parameters
        transcription_folder = parameters.get('transcription_folder')
        transcription_manifest = parameters.get('transcription_manifest')

        if not transcription_folder or not transcription_manifest:
            self.logger.error("convert_to_svg requires transcription_folder and transcription_manifest parameters")
            return False

        # Create temporary manifest for single item
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            manifest_entry = {'source': str(input_path), 'outputs': [str(input_path)]}
            f.write(json.dumps(manifest_entry) + '\n')
            temp_manifest = f.name

        try:
            # CRITICAL-1: Fix function signature - add transcription parameters
            # CRITICAL-5: Use asyncio.to_thread
            result = await asyncio.to_thread(
                convert_to_svg_batch,
                input_path.parent,              # source_folder
                Path(temp_manifest),            # source_manifest
                Path(transcription_folder),     # transcription_folder (ADDED)
                Path(transcription_manifest),   # transcription_manifest (ADDED)
                output_folder,                  # output_folder
                # Optional parameters
                None,  # metadata_manifest
                None,  # visual_descriptions_manifest
                None,  # api_key_cli
                parameters.get('skip_processing', False)
            )
            # CRITICAL-6: Fix return value structure (returns success/failed counts)
            return result.get('success', 0) > 0
        finally:
            # CRITICAL-7: Proper cleanup error handling
            try:
                if os.path.exists(temp_manifest):
                    Path(temp_manifest).unlink()
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp manifest: {e}")

    async def _run_transcribe_lmstudio(self, input_path: Path, output_folder: Path,
                                      parameters: Dict[str, Any]) -> bool:
        """Run transcribe_lmstudio tool"""
        from fichero.tools.transcribe_lmstudio import transcribe_batch
        import tempfile
        import json
        import os

        # Create temporary manifest for single item
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            manifest_entry = {'source': str(input_path), 'outputs': [str(input_path)]}
            f.write(json.dumps(manifest_entry) + '\n')
            temp_manifest = f.name

        try:
            # CRITICAL-2: Remove invalid 'prompt' parameter
            # CRITICAL-5: Use asyncio.to_thread
            result = await asyncio.to_thread(
                transcribe_batch,
                input_path.parent,
                Path(temp_manifest),
                output_folder,
                parameters.get('api_url', 'http://localhost:1234'),
                parameters.get('model_name', 'llava-1.5-7b-hf')
                # REMOVED: prompt parameter doesn't exist in function signature
            )
            # CRITICAL-6: Fix return value structure (returns success/failed counts)
            return result.get('success', 0) > 0
        finally:
            # CRITICAL-7: Proper cleanup error handling
            try:
                if os.path.exists(temp_manifest):
                    Path(temp_manifest).unlink()
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp manifest: {e}")

    async def _run_describe(self, input_path: Path, output_folder: Path,
                           parameters: Dict[str, Any]) -> bool:
        """Run describe tool"""
        from fichero.tools.describe_images import describe_batch
        import tempfile
        import json
        import os

        # Create temporary manifest for single item
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            manifest_entry = {'source': str(input_path), 'outputs': [str(input_path)]}
            f.write(json.dumps(manifest_entry) + '\n')
            temp_manifest = f.name

        try:
            # CRITICAL-5: Use asyncio.to_thread
            result = await asyncio.to_thread(
                describe_batch,
                input_path.parent,
                Path(temp_manifest),
                output_folder,
                parameters.get('llm', 'qwen-max')
            )
            # CRITICAL-6: Fix return value structure (returns success/failed counts)
            return result.get('success', 0) > 0
        finally:
            # CRITICAL-7: Proper cleanup error handling
            try:
                if os.path.exists(temp_manifest):
                    Path(temp_manifest).unlink()
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp manifest: {e}")

    async def _run_llm_process(self, input_path: Path, output_folder: Path,
                              parameters: Dict[str, Any]) -> bool:
        """Run llm_process tool"""
        from fichero.tools.llm_process import process_documents_batch
        import tempfile
        import json
        import os

        # Create temporary manifest for single item
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            manifest_entry = {'source': str(input_path), 'outputs': [str(input_path)]}
            f.write(json.dumps(manifest_entry) + '\n')
            temp_manifest = f.name

        try:
            # MAJOR-1: Add folder_mode parameter
            # CRITICAL-5: Use asyncio.to_thread
            result = await asyncio.to_thread(
                process_documents_batch,
                input_path.parent,
                Path(temp_manifest),
                output_folder,
                parameters.get('prompt_config', 'catalogue_generic'),
                parameters.get('llm', 'qwen-max'),
                parameters.get('max_tokens', 8000),
                parameters.get('folder_mode', False)
            )
            # CRITICAL-6: Fix return value structure (returns success/failed counts)
            return result.get('success', 0) > 0
        finally:
            # CRITICAL-7: Proper cleanup error handling
            try:
                if os.path.exists(temp_manifest):
                    Path(temp_manifest).unlink()
            except Exception as e:
                self.logger.warning(f"Failed to cleanup temp manifest: {e}")

    async def _run_analyze_document_groups(self, input_path: Path, output_folder: Path,
                                          parameters: Dict[str, Any]) -> bool:
        """
        Run analyze_document_groups tool

        Note: This tool operates on folders, not individual files.
        Using input_path.parent to get the folder containing the file.
        """
        from fichero.tools.analyze_document_groups import analyze_document_groups_batch

        # MAJOR-5: This tool operates on folders, not files
        # Use the parent folder of the input file
        source_folder = input_path.parent

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            analyze_document_groups_batch,
            source_folder,
            output_folder,
            parameters.get('llm', 'qwen-max'),
            parameters.get('fps', 3)
        )

        # CRITICAL-6: Fix return value structure
        return result.get('success', False)

    async def _run_convert_to_word(self, input_path: Path, output_folder: Path,
                                  parameters: Dict[str, Any]) -> bool:
        """Run convert_to_word tool"""
        from fichero.tools.convert_to_word import process_document, SpreadManager
        import tempfile

        # CRITICAL-4: SpreadManager requires temp_dir parameter
        # MAJOR-7: Use context manager for temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            spread_manager = SpreadManager(temp_dir=Path(temp_dir))
            transcription_folder = parameters.get('transcription_folder', None)

            # CRITICAL-5: Use asyncio.to_thread
            result = await asyncio.to_thread(
                process_document,
                str(input_path),
                output_folder,
                spread_manager,
                transcription_folder
            )

            # CRITICAL-6: Return value structure (convert_to_word returns 'outputs')
            return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_json_to_word(self, input_path: Path, output_folder: Path,
                               parameters: Dict[str, Any]) -> bool:
        """Run json_to_word tool"""
        from fichero.tools.json_to_word import process_document

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            process_document,
            str(input_path),
            output_folder
        )

        # CRITICAL-6: Return value structure (json_to_word returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_json_to_excel(self, input_path: Path, output_folder: Path,
                                parameters: Dict[str, Any]) -> bool:
        """Run json_to_excel tool"""
        from fichero.tools.json_to_excel import json_to_excel

        output_file = output_folder / f"{input_path.stem}.xlsx"

        # CRITICAL-3: Remove invalid 'flatten' parameter
        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            json_to_excel,
            input_path.parent,
            output_file
            # REMOVED: flatten parameter doesn't exist in function signature
        )

        # Return based on file existence
        return output_file.exists()

    async def _run_recombine(self, input_path: Path, output_folder: Path,
                            parameters: Dict[str, Any]) -> bool:
        """Run recombine tool"""
        from fichero.tools.recombine_segments import process_document

        # Get required mappings from parameters
        bg_mapping = parameters.get('bg_mapping', {})
        segments_mapping = parameters.get('segments_mapping', {})
        input_folder = parameters.get('input_folder', input_path.parent)

        # MAJOR-7: Validate complex dict parameters
        if not isinstance(bg_mapping, dict):
            self.logger.error("bg_mapping must be a dictionary")
            return False
        if not isinstance(segments_mapping, dict):
            self.logger.error("segments_mapping must be a dictionary")
            return False

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            process_document,
            str(input_path),
            output_folder,
            bg_mapping,
            segments_mapping,
            input_folder
        )

        # CRITICAL-6: Return value structure (recombine returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_fuzzy_clean(self, input_path: Path, output_folder: Path,
                              parameters: Dict[str, Any]) -> bool:
        """Run fuzzy_clean tool"""
        from fichero.tools.fuzzy_clean import process_document

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            process_document,
            str(input_path),
            output_folder
        )

        # CRITICAL-6: Return value structure (fuzzy_clean returns 'outputs')
        return 'outputs' in result and len(result.get('outputs', [])) > 0

    async def _run_extract_library_metadata(self, input_path: Path, output_folder: Path,
                                           parameters: Dict[str, Any]) -> bool:
        """Run extract_library_metadata tool"""
        from fichero.tools.extract_library_metadata import extract_metadata_batch

        collection_id = parameters.get('collection_id')
        # MAJOR-6: Default to library_manager database path if not provided
        library_db_path = parameters.get('library_db_path') or self.library_manager.storage.db_path

        # MAJOR-8: Specific error message for missing collection_id
        if not collection_id:
            self.logger.error("extract_library_metadata requires collection_id parameter")
            return False

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            extract_metadata_batch,
            collection_id,
            output_folder,
            library_db_path
        )

        # CRITICAL-6: Return value structure
        return result.get('success', False)

    async def _run_build_documents_manifest(self, input_path: Path, output_folder: Path,
                                           parameters: Dict[str, Any]) -> bool:
        """Run build_documents_manifest tool"""
        from fichero.tools.build_documents_manifest import build_documents_manifest_batch

        # CRITICAL-5: Use asyncio.to_thread
        result = await asyncio.to_thread(
            build_documents_manifest_batch,
            input_path,
            output_folder
        )

        # CRITICAL-6: Return value structure
        return result.get('success', False)

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
