"""
PrepareImagesRenderer - Renderer for prepare_images tool output

Extends FolderRenderer since prepare_images creates a folder of prepared images.
Shows gallery view of all prepared images with parameters used.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import FolderRenderer

logger = logging.getLogger(__name__)


class PrepareImagesRenderer(FolderRenderer):
    """
    Renderer for prepare_images tool output.

    Extends FolderRenderer since prepare_images creates a folder of images:
    - Displays gallery view of all prepared images
    - Provides editable JSON with preparation parameters
    - Can re-run preparation with new parameters

    Example manifest entry:
        {
            "path": "prepared/",
            "type": "folder",
            "resize_mode": "fit",
            "target_size": [1200, 1600],
            "quality": 95,
            "format": "jpg",
            "dpi": 300,
            "processed_count": 50
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render prepared images gallery with interactive viewer.

        Shows thumbnails of all prepared images with ability to click and view full size.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML
        """
        # Use parent FolderRenderer for gallery display
        # It will show thumbnails of all images in the folder
        return super().render_html(context)

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """
        Render preparation info for CLI.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with text
        """
        text_parts = []

        # Title
        text_parts.append(f"Step {context.step_index}: {context.step_name}")
        text_parts.append("=" * 60)
        text_parts.append("")

        # Folder info
        text_parts.append(f"Folder: {context.file_path}")
        text_parts.append(f"Type: {context.file_type}")
        text_parts.append("")

        # Preparation info from manifest
        if context.manifest_entry:
            prep_data = self._extract_preparation_data(context.manifest_entry)

            text_parts.append("Preparation Parameters:")
            text_parts.append(f"  Resize Mode: {prep_data.get('resize_mode', 'fit')}")

            target_size = prep_data.get('target_size', [1200, 1600])
            text_parts.append(f"  Target Size: {target_size[0]}x{target_size[1]}")

            text_parts.append(f"  Quality: {prep_data.get('quality', 95)}")
            text_parts.append(f"  Format: {prep_data.get('format', 'jpg')}")
            text_parts.append(f"  DPI: {prep_data.get('dpi', 300)}")

            if 'processed_count' in prep_data:
                text_parts.append(f"  Processed: {prep_data['processed_count']} images")

            text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Prepared images: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Get editable JSON for preparation parameters.

        Returns resize_mode, target_size, quality, format, dpi from manifest entry.

        Args:
            context: Rendering context

        Returns:
            Dictionary with editable parameters or None
        """
        if not context.manifest_entry:
            logger.warning("No manifest entry in context, cannot extract preparation data")
            return None

        prep_data = self._extract_preparation_data(context.manifest_entry)

        if not prep_data:
            logger.warning("No preparation data found in manifest entry")
            return None

        return prep_data

    def _extract_preparation_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract preparation-specific data from manifest entry.

        Args:
            manifest_entry: Manifest entry dictionary

        Returns:
            Dictionary with resize_mode, target_size, quality, format, dpi
        """
        prep_data = {}

        # Resize mode (default 'fit')
        prep_data['resize_mode'] = manifest_entry.get('resize_mode', 'fit')

        # Target size (default [1200, 1600])
        prep_data['target_size'] = manifest_entry.get('target_size', [1200, 1600])

        # Quality (default 95)
        prep_data['quality'] = manifest_entry.get('quality', 95)

        # Format (default 'jpg')
        prep_data['format'] = manifest_entry.get('format', 'jpg')

        # DPI (default 300)
        prep_data['dpi'] = manifest_entry.get('dpi', 300)

        # Processed count (optional)
        if 'processed_count' in manifest_entry:
            prep_data['processed_count'] = manifest_entry['processed_count']

        return prep_data

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate edited preparation JSON.

        Checks:
        - resize_mode is valid ('fit', 'fill', 'exact')
        - target_size is [width, height] with positive integers
        - quality is 1-100
        - format is valid ('jpg', 'png', 'tiff')
        - dpi is positive integer

        Args:
            json_data: Edited JSON data

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check resize_mode
        if 'resize_mode' in json_data:
            resize_mode = json_data['resize_mode']
            valid_modes = ['fit', 'fill', 'exact']

            if resize_mode not in valid_modes:
                return False, f"resize_mode must be one of {valid_modes}, got '{resize_mode}'"

        # Check target_size
        if 'target_size' in json_data:
            target_size = json_data['target_size']

            if not isinstance(target_size, list) or len(target_size) != 2:
                return False, f"target_size must be [width, height], got {target_size}"

            width, height = target_size

            if not isinstance(width, int) or not isinstance(height, int):
                return False, f"target_size values must be integers, got {target_size}"

            if width <= 0 or height <= 0:
                return False, f"target_size values must be positive, got {target_size}"

        # Check quality
        if 'quality' in json_data:
            quality = json_data['quality']

            if not isinstance(quality, int):
                return False, f"quality must be integer, got {type(quality).__name__}"

            if not 1 <= quality <= 100:
                return False, f"quality must be 1-100, got {quality}"

        # Check format
        if 'format' in json_data:
            format_val = json_data['format']
            valid_formats = ['jpg', 'png', 'tiff']

            if format_val not in valid_formats:
                return False, f"format must be one of {valid_formats}, got '{format_val}'"

        # Check DPI
        if 'dpi' in json_data:
            dpi = json_data['dpi']

            if not isinstance(dpi, int):
                return False, f"dpi must be integer, got {type(dpi).__name__}"

            if dpi <= 0:
                return False, f"dpi must be positive, got {dpi}"

        return True, None

    def apply_json_edits(
        self,
        context: RenderContext,
        json_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Apply edited preparation parameters and re-run tool.

        This is a placeholder for now. Full implementation would:
        1. Get source images from original step
        2. Call prepare_images tool with new parameters
        3. Update manifest with new data
        4. Return success/failure

        Args:
            context: Rendering context
            json_data: Edited JSON data

        Returns:
            Tuple of (success, error_message)
        """
        # Validate first
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        # TODO: Implement re-preparation
        # For now, just log and return success
        logger.info(f"Would re-prepare images with parameters: {json.dumps(json_data, indent=2)}")
        logger.warning("apply_json_edits not fully implemented yet - changes not saved")

        return False, "Image preparation re-processing not implemented yet (placeholder)"
