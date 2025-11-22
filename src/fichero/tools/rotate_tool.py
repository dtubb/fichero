"""
RotateTool - StandardTool implementation for rotate functionality

Wraps the existing rotate.process_image() function to work with ToolExecutionService.
This provides a unified interface for tool execution following the StandardTool pattern.
"""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from fichero.tools.base_tool import StandardTool, ToolResult
from fichero.library.services import ToolRegistry

# Import rotate functionality
from fichero.tools.rotate import process_image


@ToolRegistry.register
class RotateTool(StandardTool):
    """
    Rotate tool implementation using StandardTool interface.

    Uses Hough line detection to automatically straighten/rotate images.
    Corrects skewed document scans by detecting text baselines and rotating
    the image to align them horizontally.

    Supports multiple output formats: jpg, png, jxl
    """

    def get_tool_name(self) -> str:
        """Returns 'rotate' to match existing manifest structure"""
        return "rotate"

    def get_manifest_folder(self) -> str:
        """Returns 'rotated' for output folder structure"""
        return "rotated"

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate rotate tool parameters.

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
        Execute rotate on a source image.

        Uses existing rotate.process_image() function for the actual processing.

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

            # Call existing rotate.process_image function
            result_dict = process_image(
                file_path=source_path,
                out_path=output_path,
                output_format=output_format
            )

            # Check if process_image succeeded
            if result_dict.get('success') is False:
                return ToolResult(
                    success=False,
                    error=result_dict.get('error', 'Rotate processing failed')
                )

            # Extract metadata from result
            rotate_details = result_dict.get('details', {})

            return ToolResult(
                success=True,
                output_path=output_path,
                metadata={
                    'original_size': rotate_details.get('original_size'),
                    'rotated_size': rotate_details.get('rotated_size'),
                    'debug': rotate_details.get('debug'),
                    'output_format': rotate_details.get('output_format', output_format)
                }
            )

        except Exception as e:
            self.logger.error(f"Rotate processing failed: {e}", exc_info=True)
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
        Create JSONL manifest entry for rotate execution.

        Follows existing rotate manifest format for compatibility.

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

        # Build manifest entry following rotate's format
        manifest_entry = {
            'path': output_path.name,
            'source': source_path.name,
            'type': 'file',
            'details': {
                'original_size': metadata.get('original_size'),
                'rotated_size': metadata.get('rotated_size'),
                'debug': metadata.get('debug', {}),
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
        Get default parameters for rotate tool.

        Returns:
            Dictionary with default parameters
        """
        return {
            'output_format': 'jpg'
        }

    def supports_batch_processing(self) -> bool:
        """Rotate tool supports batch processing"""
        return True

    def get_supported_input_formats(self) -> list[str]:
        """
        Get supported input formats for rotate.

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
