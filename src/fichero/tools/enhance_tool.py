"""
EnhanceTool - StandardTool implementation for enhance functionality

Wraps the existing enhance.process_image() function to work with ToolExecutionService.
This provides a unified interface for tool execution following the StandardTool pattern.
"""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from fichero.tools.base_tool import StandardTool, ToolResult
from fichero.library.services import ToolRegistry

# Import enhance functionality
from fichero.tools.enhance import process_image


@ToolRegistry.register
class EnhanceTool(StandardTool):
    """
    Enhance tool implementation using StandardTool interface.

    Applies automatic image enhancement: contrast adjustment, sharpening,
    brightness normalization, and yellowing removal for aged documents.

    Supports multiple output formats: jpg, png, jxl
    """

    def get_tool_name(self) -> str:
        """Returns 'enhance' to match existing manifest structure"""
        return "enhance"

    def get_manifest_folder(self) -> str:
        """Returns 'enhanced' for output folder structure"""
        return "enhanced"

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate enhance tool parameters.

        Valid parameters:
        - output_format: str ('jpg', 'png', 'jxl') - default 'jpg'

        Args:
            parameters: Parameter dictionary

        Returns:
            (True, None) if valid, (False, error_message) if invalid
        """
        # Validate output_format if present
        output_format = parameters.get('output_format', 'jpg')
        valid_formats = ['jpg', 'jpeg', 'png', 'jxl']
        if output_format.lower() not in valid_formats:
            return (False, f"output_format must be one of {valid_formats}, got '{output_format}'")

        return (True, None)

    async def process(
        self,
        source_path: Path,
        output_path: Path,
        parameters: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute enhance on a source image.

        Uses existing enhance.process_image() function for the actual processing.

        Args:
            source_path: Path to input image
            output_path: Path for output image
            parameters: Processing parameters

        Returns:
            ToolResult with success status and metadata
        """
        try:
            # Extract parameters
            output_format = parameters.get('output_format', 'jpg')

            # Call existing enhance.process_image function
            result_dict = process_image(
                file_path=source_path,
                out_path=output_path,
                output_format=output_format
            )

            # Check if process_image succeeded
            if result_dict.get('success') is False:
                return ToolResult(
                    success=False,
                    error=result_dict.get('error', 'Enhance processing failed')
                )

            # Extract metadata from result
            enhance_details = result_dict.get('details', {})

            return ToolResult(
                success=True,
                output_path=output_path,
                metadata={
                    'original_size': enhance_details.get('original_size'),
                    'enhanced_size': enhance_details.get('enhanced_size'),
                    'enhancement_params': enhance_details.get('enhancement_params'),
                    'output_format': enhance_details.get('output_format', output_format)
                }
            )

        except Exception as e:
            self.logger.error(f"Enhance processing failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )

    def create_manifest_entry(
        self,
        source_path: Path,
        output_path: Path,
        parameters: Dict[str, Any],
        result: ToolResult
    ) -> Dict[str, Any]:
        """
        Create JSONL manifest entry for enhance execution.

        Follows existing enhance manifest format for compatibility.

        Args:
            source_path: Source file that was processed
            output_path: Output file that was created
            parameters: Parameters used
            result: ToolResult from process()

        Returns:
            Dictionary for JSONL manifest line
        """
        # Extract metadata from result
        metadata = result.metadata or {}

        # Build manifest entry following enhance's format
        manifest_entry = {
            'path': output_path.name,
            'source': source_path.name,
            'type': 'file',
            'details': {
                'original_size': metadata.get('original_size'),
                'enhanced_size': metadata.get('enhanced_size'),
                'enhancement_params': metadata.get('enhancement_params', {}),
                'output_format': metadata.get('output_format', 'jpg'),
                'parameters': {
                    'output_format': parameters.get('output_format', 'jpg')
                }
            },
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'tool_version': '1.0',
                'execution_mode': 'interactive'
            }
        }

        return manifest_entry

    def get_default_parameters(self) -> Dict[str, Any]:
        """
        Get default parameters for enhance tool.

        Returns:
            Dictionary with default parameters
        """
        return {
            'output_format': 'jpg'
        }

    def supports_batch_processing(self) -> bool:
        """Enhance tool supports batch processing"""
        return True

    def get_supported_input_formats(self) -> list[str]:
        """
        Get supported input formats for enhance.

        Returns:
            List of supported image formats
        """
        return ['jpg', 'jpeg', 'png', 'tif', 'tiff', 'jxl', 'heif', 'heic']

    def get_output_format(self, parameters: Dict[str, Any]) -> str:
        """
        Get output format based on parameters.

        Args:
            parameters: Tool parameters

        Returns:
            Output format extension
        """
        return parameters.get('output_format', 'jpg')
