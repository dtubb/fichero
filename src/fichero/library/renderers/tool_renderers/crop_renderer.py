"""
CropRenderer - Renderer for crop tool output

Extends ImageRenderer to provide crop-specific JSON editing capabilities.
Displays cropped images with interactive viewer and allows editing crop parameters.
"""

import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from ..base_renderer import RenderContext, RenderedOutput
from ..type_renderers import ImageRenderer

logger = logging.getLogger(__name__)


class CropRenderer(ImageRenderer):
    """
    Renderer for crop tool output.

    Extends ImageRenderer with crop-specific JSON editing:
    - Displays cropped image with interactive viewer
    - Provides editable JSON with crop box, padding, method
    - Can re-run crop with new parameters

    Example manifest entry:
        {
            "path": "cropped/file.jpg",
            "type": "file",
            "crop_box": {"x": 100, "y": 50, "width": 800, "height": 600},
            "padding": 30,
            "method": "contour",
            "template": "auto"
        }
    """

    def render_html(self, context: RenderContext) -> RenderedOutput:
        """
        Render cropped image with interactive crop editor.

        If viewing the cropped output with manifest data, show interactive
        crop editor that allows adjusting the crop box.

        Args:
            context: Rendering context

        Returns:
            RenderedOutput with HTML
        """
        # Use image editor with crop box if we have manifest data
        if context.interactive and context.show_content and context.manifest_entry:
            details = context.manifest_entry.get('details', {})
            crop_box = details.get('box')

            if crop_box:
                # We have crop data - show image editor with crop visualization
                from ..html_templates_image_editor import get_image_editor

                # Get the source image path (original, not cropped)
                source_file = context.manifest_entry.get('source', '')
                logger.info(f"[CropRenderer] source_file from manifest: {source_file}")

                if source_file:
                    # Source is relative to item directory
                    # context.file_path is like: .../item.tif/assets/cropped/file.jpg
                    # Source is like: EAP1740_NP_T19_1700_001_01.tif
                    item_dir = context.file_path.parent.parent.parent

                    # Try multiple possible source locations
                    possible_source_paths = [
                        item_dir / 'assets' / 'original' / source_file,  # Prepared images
                        item_dir / 'documents' / source_file,  # Original documents
                        item_dir / source_file,  # Root level
                    ]

                    source_path = None
                    for path in possible_source_paths:
                        logger.info(f"[CropRenderer] Checking: {path}")
                        if path.exists():
                            source_path = path
                            logger.info(f"[CropRenderer] Found source at: {source_path}")
                            break

                    if not source_path:
                        logger.warning(f"[CropRenderer] Source image not found in any location:")
                        logger.warning(f"[CropRenderer] Tried: {[str(p) for p in possible_source_paths]}")
                        # List what's actually in these directories
                        for try_dir in [item_dir / 'assets' / 'original', item_dir / 'documents', item_dir]:
                            if try_dir.exists() and try_dir.is_dir():
                                files = list(try_dir.iterdir())[:10]  # First 10 files
                                logger.info(f"[CropRenderer] Files in {try_dir}: {[f.name for f in files]}")

                    if source_path:
                        # Use rubber-band crop viewer for interactive editing
                        from ..html_templates_crop import get_rubberband_crop_viewer

                        html = get_rubberband_crop_viewer(
                            image_path=source_path,
                            crop_box=crop_box,
                            title=f"Crop Editor: {context.step_name}",
                            use_base64=True,
                            item_id=context.item_id,
                            step_index=context.step_index
                        )
                        return RenderedOutput(
                            html=html,
                            title=context.step_name,
                            description=f'Interactive crop editor: {context.file_path.name}'
                        )

        # Fallback: use parent ImageRenderer for standard display
        return super().render_html(context)

    def render_cli(self, context: RenderContext) -> RenderedOutput:
        """
        Render crop info for CLI.

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

        # File info
        text_parts.append(f"File: {context.file_path}")
        text_parts.append(f"Type: {context.file_type}")
        text_parts.append("")

        # Crop info from manifest
        if context.manifest_entry:
            crop_data = self._extract_crop_data(context.manifest_entry)

            if crop_data.get('crop_box'):
                box = crop_data['crop_box']
                text_parts.append("Crop Box:")
                text_parts.append(f"  x: {box.get('x', 'N/A')}")
                text_parts.append(f"  y: {box.get('y', 'N/A')}")
                text_parts.append(f"  width: {box.get('width', 'N/A')}")
                text_parts.append(f"  height: {box.get('height', 'N/A')}")
                text_parts.append("")

            if 'padding' in crop_data:
                text_parts.append(f"Padding: {crop_data['padding']}")
                text_parts.append("")

            if 'method' in crop_data:
                text_parts.append(f"Method: {crop_data['method']}")
                text_parts.append("")

        return RenderedOutput(
            text='\n'.join(text_parts),
            title=context.step_name,
            description=f"Cropped image: {context.file_path.name}"
        )

    def get_editable_json(self, context: RenderContext) -> Optional[Dict[str, Any]]:
        """
        Get editable JSON for crop parameters.

        Returns crop box, padding, method, and template from manifest entry.

        Args:
            context: Rendering context

        Returns:
            Dictionary with editable crop parameters or None
        """
        if not context.manifest_entry:
            logger.warning("No manifest entry in context, cannot extract crop data")
            return None

        crop_data = self._extract_crop_data(context.manifest_entry)

        if not crop_data:
            logger.warning("No crop data found in manifest entry")
            return None

        return crop_data

    def _extract_crop_data(self, manifest_entry: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract crop-specific data from manifest entry.

        Returns the entire manifest entry as-is for editing.
        This allows users to see and edit all fields without custom extraction logic.

        Args:
            manifest_entry: Manifest entry dictionary

        Returns:
            The complete manifest entry for editing
        """
        # Just return the entire manifest - no need to extract specific fields
        # The user can see and edit everything
        return manifest_entry

    def validate_json(self, json_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate edited crop JSON.

        Checks:
        - details.box exists and has x1, y1, x2, y2 (new format)
        - Values are positive integers
        - Box coordinates are sane (x2 > x1, y2 > y1)

        Args:
            json_data: Edited JSON data with 'details.box' containing {x1, y1, x2, y2}

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check details exists
        if 'details' not in json_data:
            return False, "Missing 'details' field"

        details = json_data['details']

        # Check box exists
        if 'box' not in details:
            return False, "Missing 'box' in details"

        box = details['box']

        # Check box has required fields (x1, y1, x2, y2 format)
        required_fields = ['x1', 'y1', 'x2', 'y2']
        for field in required_fields:
            if field not in box:
                return False, f"Missing '{field}' in box"

            # Check type and value
            value = box[field]
            if not isinstance(value, (int, float)):
                return False, f"box.{field} must be a number, got {type(value).__name__}"

            if value < 0:
                return False, f"box.{field} must be non-negative, got {value}"

        # Check box is sane (x2 > x1, y2 > y1)
        if box['x2'] <= box['x1']:
            return False, f"box.x2 ({box['x2']}) must be greater than box.x1 ({box['x1']})"

        if box['y2'] <= box['y1']:
            return False, f"box.y2 ({box['y2']}) must be greater than box.y1 ({box['y1']})"

        return True, None

    async def apply_json_edits(
        self,
        context: RenderContext,
        json_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Apply edited crop parameters by manually cropping the image.

        Loads the original image, crops it using the new box coordinates,
        and saves it to replace the existing cropped image.

        Args:
            context: Rendering context
            json_data: Edited JSON data with 'details.box' containing x1, y1, x2, y2

        Returns:
            Tuple of (success, error_message)
        """
        # Validate first
        is_valid, error = self.validate_json(json_data)
        if not is_valid:
            return False, error

        try:
            from PIL import Image

            # Get the crop box from json_data
            details = json_data.get('details', {})
            box = details.get('box', {})

            if not box:
                return False, "No crop box found in JSON data"

            x1 = int(box.get('x1', 0))
            y1 = int(box.get('y1', 0))
            x2 = int(box.get('x2', 0))
            y2 = int(box.get('y2', 0))

            # Get source image path
            source_file = json_data.get('source', '')
            if not source_file:
                return False, "No source file found in JSON data"

            # Build path to original image
            item_dir = context.file_path.parent.parent.parent
            source_path = item_dir / 'assets' / 'original' / source_file

            if not source_path.exists():
                return False, f"Source image not found: {source_path}"

            # Load original image
            logger.info(f"Loading original image from: {source_path}")
            img = Image.open(source_path)

            # Crop the image
            logger.info(f"Cropping to box: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
            cropped_img = img.crop((x1, y1, x2, y2))

            # Save cropped image (overwrite existing)
            output_path = context.file_path
            logger.info(f"Saving cropped image to: {output_path}")

            # Determine format from file extension
            ext = output_path.suffix.lower()
            if ext in ['.jpg', '.jpeg']:
                cropped_img.save(output_path, 'JPEG', quality=95)
            elif ext == '.png':
                cropped_img.save(output_path, 'PNG')
            elif ext == '.tif' or ext == '.tiff':
                cropped_img.save(output_path, 'TIFF')
            else:
                cropped_img.save(output_path)

            # Update manifest file
            manifest_dir_name = "cropped"
            manifest_file = item_dir / "assets" / manifest_dir_name / "crop_manifest.jsonl"

            if manifest_file.exists():
                # Read existing manifest
                with open(manifest_file, 'r') as f:
                    lines = f.readlines()

                # Find and update the line for this file
                updated = False
                for i, line in enumerate(lines):
                    entry = json.loads(line)
                    # Match by source file
                    if entry.get('source') == source_file:
                        # Update the details
                        entry['details']['box'] = box
                        entry['details']['cropped_size'] = [x2 - x1, y2 - y1]
                        entry['details']['method'] = 'manual'
                        lines[i] = json.dumps(entry) + '\n'
                        updated = True
                        break

                if updated:
                    # Write back to manifest
                    with open(manifest_file, 'w') as f:
                        f.writelines(lines)
                    logger.info(f"Updated manifest file: {manifest_file}")
                else:
                    logger.warning(f"Could not find entry in manifest for source: {source_file}")

            # Save to library backend if we have library_manager in context
            if hasattr(context, 'library_manager') and context.library_manager:
                try:
                    await self._update_library_database(context, box, source_file)
                except Exception as db_error:
                    logger.error(f"Failed to update library database: {db_error}")
                    # Continue anyway - manifest was updated

            logger.info("Manual crop applied successfully")
            return True, None

        except Exception as e:
            logger.error(f"Error applying manual crop: {e}")
            return False, f"Error applying crop: {str(e)}"

    async def _update_library_database(self, context: RenderContext, box: dict, source_file: str):
        """
        Update library database after manual crop edit.

        Args:
            context: Rendering context with library_manager
            box: Crop box coordinates {x1, y1, x2, y2}
            source_file: Source filename
        """
        from datetime import datetime

        library_manager = context.library_manager

        # Get library manager from parent if not available directly
        if not library_manager and hasattr(context, 'item_id'):
            # Try to get library_manager from global context
            # This is a fallback - ideally it's passed in context
            logger.warning("library_manager not in context, attempting to use metadata API directly")
            return

        # Use metadata API to save crop metadata
        try:
            metadata_api = library_manager.metadata_api

            # Prepare metadata for library storage
            metadata_for_library = {
                # Step results
                "method": "manual",
                "box": box,
                "cropped_size": [box['x2'] - box['x1'], box['y2'] - box['y1']],

                # Mark as manually edited
                "manually_edited": True,
                "edited_at": datetime.now().isoformat()
            }

            # Save to library database
            success = metadata_api.save_step_metadata(
                item_id=context.item_id,
                step_name="crop",
                metadata=metadata_for_library,
                version=None  # Auto-increment version
            )

            if success:
                logger.info(f"✅ Saved crop metadata to library for item {context.item_id}")
            else:
                logger.error(f"❌ Failed to save crop metadata to library for item {context.item_id}")

        except Exception as e:
            logger.error(f"Error saving metadata to library: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't fail the whole operation
