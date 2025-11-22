"""
CropTool - StandardTool implementation for crop functionality

Wraps the existing crop.process_image() function to work with ToolExecutionService.
This provides a unified interface for tool execution following the StandardTool pattern.
"""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from fichero.tools.base_tool import StandardTool, ToolResult
from fichero.library.services import ToolRegistry

# Import crop functionality
from fichero.tools.crop import (
    process_image,
    ContourSettings,
    DEFAULT_CONTOUR_SETTINGS
)


@ToolRegistry.register
class CropTool(StandardTool):
    """
    Crop tool implementation using StandardTool interface.

    Uses YOLO and contour detection to automatically crop documents from images.
    Falls back to original image if detection fails.

    Supports multiple output formats: jpg, png, jxl
    """

    def get_tool_name(self) -> str:
        """Returns 'crop' to match existing manifest structure"""
        return "crop"

    def get_manifest_folder(self) -> str:
        """Returns 'cropped' for output folder structure"""
        return "cropped"

    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate crop tool parameters.

        Valid parameters:
        - output_format: str ('jpg', 'png', 'jxl') - default 'jpg'
        - contour_settings: dict - contour detection settings
        - box: dict - manual crop box {x1, y1, x2, y2} (optional)

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

        # If manual crop box provided, validate coordinates
        if 'box' in parameters:
            box = parameters['box']
            if not isinstance(box, dict):
                return (False, "box must be a dictionary with keys: x1, y1, x2, y2")

            required_keys = ['x1', 'y1', 'x2', 'y2']
            if not all(k in box for k in required_keys):
                return (False, f"box must contain all keys: {required_keys}")

            # Validate coordinates are numeric
            try:
                coords = [float(box[k]) for k in required_keys]
                # Validate box is non-empty
                if coords[2] <= coords[0] or coords[3] <= coords[1]:
                    return (False, "box must have x2 > x1 and y2 > y1")
            except (ValueError, TypeError):
                return (False, "box coordinates must be numeric")

        return (True, None)

    async def process(
        self,
        source_path: Path,
        output_path: Path,
        parameters: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute crop on a source image.

        Uses existing crop.process_image() function for the actual processing.

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

            # Build contour settings from parameters
            contour_settings = DEFAULT_CONTOUR_SETTINGS
            if 'contour_settings' in parameters:
                cs_params = parameters['contour_settings']
                contour_settings = ContourSettings(
                    threshold_method=cs_params.get('threshold_method', 'auto'),
                    threshold_value=cs_params.get('threshold_value', 150),
                    blur_kernel=cs_params.get('blur_kernel', 0),
                    edge_detection=cs_params.get('edge_detection', False),
                    min_contour_area=cs_params.get('min_contour_area', 0.5),
                    max_contour_area=cs_params.get('max_contour_area', 0.99),
                    min_aspect_ratio=cs_params.get('min_aspect_ratio', 0.5),
                    max_aspect_ratio=cs_params.get('max_aspect_ratio', 2.0),
                    padding=cs_params.get('padding', 10)
                )

            # Call existing crop.process_image function
            # NOTE: We're NOT passing library_manager/item_id here because
            # ToolExecutionService handles database persistence via add_processing_result()
            result_dict = process_image(
                file_path=source_path,
                out_path=output_path,
                output_format=output_format,
                contour_settings=contour_settings,
                library_manager=None,  # ToolExecutionService handles library integration
                item_id=None
            )

            # Check if process_image succeeded
            if result_dict.get('success') is False:
                return ToolResult(
                    success=False,
                    error=result_dict.get('error', 'Crop processing failed')
                )

            # Extract metadata from result
            crop_details = result_dict.get('details', {})

            return ToolResult(
                success=True,
                output_path=output_path,
                metadata={
                    'method': crop_details.get('method'),
                    'confidence': crop_details.get('confidence'),
                    'box': crop_details.get('box'),
                    'original_size': crop_details.get('original_size'),
                    'cropped_size': crop_details.get('cropped_size'),
                    'rotation': crop_details.get('rotation'),
                    'attempts': crop_details.get('attempts', []),
                    'output_format': crop_details.get('output_format', output_format)
                }
            )

        except Exception as e:
            self.logger.error(f"Crop processing failed: {e}", exc_info=True)
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
        Create JSONL manifest entry for crop execution.

        Follows existing crop manifest format for compatibility.

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

        # Build manifest entry following crop's format
        manifest_entry = {
            'path': output_path.name,
            'source': source_path.name,
            'type': 'file',
            'details': {
                'method': metadata.get('method', 'unknown'),
                'confidence': metadata.get('confidence'),
                'box': metadata.get('box'),
                'original_size': metadata.get('original_size'),
                'cropped_size': metadata.get('cropped_size'),
                'rotation': metadata.get('rotation'),
                'attempts': metadata.get('attempts', []),
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

        # Add manual box if provided in parameters
        if 'box' in parameters:
            manifest_entry['details']['manual_box'] = parameters['box']

        return manifest_entry

    def get_default_parameters(self) -> Dict[str, Any]:
        """
        Get default parameters for crop tool.

        Returns:
            Dictionary with default parameters
        """
        return {
            'output_format': 'jpg',
            'contour_settings': None  # Use DEFAULT_CONTOUR_SETTINGS
        }

    def supports_batch_processing(self) -> bool:
        """Crop tool supports batch processing"""
        return True

    def get_supported_input_formats(self) -> list[str]:
        """
        Get supported input formats for crop.

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
