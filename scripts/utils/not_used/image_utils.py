from PIL import Image, ExifTags
import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def get_image_orientation(image_path: Path) -> tuple[str, int, dict]:
    """Get the true orientation of an image using EXIF data and required rotation angle."""
    details = {
        "exif_orientation": None,
        "original_dimensions": None,
        "rotation_applied": None,
        "reason": None
    }
    
    try:
        image = Image.open(image_path)
        width, height = image.size
        details["original_dimensions"] = {"width": width, "height": height}
        
        # Check for EXIF orientation tag
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == 'Orientation':
                try:
                    exif = dict(image._getexif().items())
                    if orientation in exif:
                        exif_orientation = exif[orientation]
                        details["exif_orientation"] = exif_orientation
                        
                        if exif_orientation in [5, 6, 7, 8]:  # Vertical orientations
                            if exif_orientation == 6:  # 90° CW
                                details["rotation_applied"] = 270
                                details["reason"] = "EXIF orientation 6 (90° CW) requires 270° rotation to correct"
                                return "vertical", 270, details
                            elif exif_orientation == 8:  # 90° CCW
                                details["rotation_applied"] = 90
                                details["reason"] = "EXIF orientation 8 (90° CCW) requires 90° rotation to correct"
                                return "vertical", 90, details
                            elif exif_orientation == 5:  # Mirrored and rotated 90° CCW
                                details["rotation_applied"] = 270
                                details["reason"] = "EXIF orientation 5 (Mirrored 90° CCW) requires 270° rotation to correct"
                                return "vertical", 270, details
                            elif exif_orientation == 7:  # Mirrored and rotated 90° CW
                                details["rotation_applied"] = 90
                                details["reason"] = "EXIF orientation 7 (Mirrored 90° CW) requires 90° rotation to correct"
                                return "vertical", 90, details
                except (AttributeError, KeyError, IndexError) as e:
                    details["reason"] = f"No valid EXIF data found: {str(e)}"
        
        # Fallback to dimension check if no EXIF data
        if height > width:
            details["reason"] = "No EXIF data, using dimensions (height > width) to determine vertical orientation"
            return "vertical", 0, details
        else:
            details["reason"] = "No EXIF data, using dimensions (width >= height) to determine horizontal orientation"
            return "horizontal", 0, details
    except Exception as e:
        details["reason"] = f"Error checking orientation: {str(e)}"
        return "unknown", 0, details

def prepare_image_for_model(
    image: Image.Image,
    target_size: int = 640,
    divisible_by: int = 32
) -> Tuple[np.ndarray, float, Tuple[int, int], Tuple[int, int]]:
    """Prepare image for model input with proper scaling and dimensions."""
    # Convert to numpy array
    img_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    orig_height, orig_width = img_array.shape[:2]
    
    # Calculate target size maintaining aspect ratio
    scale = min(target_size / orig_width, target_size / orig_height)
    model_width = int(orig_width * scale)
    model_height = int(orig_height * scale)
    
    # Ensure dimensions are divisible by specified value
    model_width = ((model_width + divisible_by - 1) // divisible_by) * divisible_by
    model_height = ((model_height + divisible_by - 1) // divisible_by) * divisible_by
    
    # Resize image
    model_img = cv2.resize(img_array, (model_width, model_height), 
                         interpolation=cv2.INTER_LINEAR)
    
    return model_img, scale, (orig_width, orig_height), (model_width, model_height)

def save_image_with_metadata(
    image: Image.Image,
    output_path: Path,
    original_image: Optional[Image.Image] = None,
    quality: int = 95
) -> None:
    """Save image with preserved metadata and proper format."""
    # Convert to RGB if needed
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Try to preserve EXIF data
    if original_image and hasattr(original_image, '_getexif'):
        try:
            exif = original_image._getexif()
            if exif is not None:
                image.info['exif'] = exif
        except Exception as e:
            logger.warning(f"Could not preserve EXIF data: {e}")
    
    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save image
    image.save(output_path, 'JPEG', quality=quality)

def get_relative_path(file_path: Path) -> Path:
    """Get relative path from documents/ onwards."""
    parts = file_path.parts
    if 'documents' in parts:
        return Path(*parts[parts.index('documents')+1:])
    return file_path 