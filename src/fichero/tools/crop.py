import typer
from PIL import Image
from pathlib import Path
import numpy as np
import cv2
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import os
import json
import yaml

from PIL import ExifTags

# Import utilities with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.files import ensure_dirs
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # Fall back to relative imports (when run standalone)
    from utils.batch import BatchProcessor
    from utils.processor import process_file
    from utils.segment_handler import SegmentHandler
    from utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from utils.files import ensure_dirs
    from utils.tool_logger import get_tool_logger

# Configure tool_logger
tool_logger = get_tool_logger('crop')

# Load YOLO model
try:
    from ultralytics import YOLO
    yolo_model = None  # Will be initialized with the path from command line
    tool_logger.info("YOLO model will be loaded with provided path")
except Exception as e:
    tool_logger.error(f"Failed to import YOLO: {e}")
    raise

def get_image_orientation(image_path: Path) -> tuple[str, int, dict]:
    """Get the true orientation of an image using EXIF data and required rotation angle.
    Returns (orientation, rotation_angle, details) where:
    - orientation is "vertical" or "horizontal"
    - rotation_angle is the degrees needed to correct the image
    - details is a dict with EXIF and processing information"""
    details = {
        "exif_orientation": None,
        "original_dimensions": None,
        "rotation_applied": None,
        "reason": None
    }
    
    try:
        # Use load_image to handle various formats
        image, metadata = load_image(image_path)
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
                        
                        # EXIF orientation values and their meanings:
                        # 1: Normal (0°)
                        # 2: Mirrored (0°)
                        # 3: Upside down (180°)
                        # 4: Mirrored upside down (180°)
                        # 5: Mirrored and rotated 90° CCW (90°)
                        # 6: Rotated 90° CW (270°)
                        # 7: Mirrored and rotated 90° CW (270°)
                        # 8: Rotated 90° CCW (90°)
                        
                        if exif_orientation in [5, 6, 7, 8]:  # Vertical orientations
                            # Calculate required rotation angle
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

def crop_with_yolo(image_path: Path, output_folder: Path, conf_threshold: float = 0.35) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
    """Crop image using YOLOv8 model
    Returns tuple of (cropped_image, crop_info) where crop_info contains box coordinates and confidence"""
    try:
        # Get true orientation and required rotation
        true_orientation, rotation_angle, orientation_details = get_image_orientation(image_path)
        
        # Load image using the format utility
        original_pil, metadata = load_image(image_path)
        orig_width, orig_height = original_pil.size
        
        # Apply rotation if needed
        if rotation_angle > 0:
            original_pil = original_pil.rotate(rotation_angle, expand=True)
            # Update dimensions after rotation
            orig_width, orig_height = original_pil.size
        
        # Convert to numpy array for YOLO
        original_img = cv2.cvtColor(np.array(original_pil), cv2.COLOR_RGB2BGR)
        
        # Resize image for model prediction while maintaining aspect ratio and stride requirement
        model_size = 640
        scale = min(model_size / orig_width, model_size / orig_height)
        model_width = int(orig_width * scale)
        model_height = int(orig_height * scale)
        
        # Ensure dimensions are multiples of 32 (YOLO stride requirement)
        model_width = ((model_width + 31) // 32) * 32
        model_height = ((model_height + 31) // 32) * 32
        
        model_img = cv2.resize(original_img, (model_width, model_height))
        
        # Run prediction with optimized settings
        results = yolo_model.predict(
            source=model_img,
            conf=conf_threshold,
            imgsz=(model_width, model_height),
            iou=0.45,
            verbose=False
        )[0]
        
        if not results.boxes:
            tool_logger.warning("No detections found")
            return None
            
        # Get the best detection (highest confidence)
        box = max(results.boxes.data, key=lambda x: x[4])
        x1, y1, x2, y2, conf = map(float, box[:5])
        
        # Scale coordinates back to original image size
        x1 = int(x1 / scale)
        y1 = int(y1 / scale)
        x2 = int(x2 / scale)
        y2 = int(y2 / scale)
        
        # Apply padding only on left and bottom
        padding = 30
        x1 = max(0, x1 - padding)  # Add padding to left
        y1 = max(0, y1 - padding)  # Add padding to top
        x2 = min(orig_width, x2)   # No padding on right
        y2 = min(orig_height, y2 + padding)  # Add padding to bottom
        
        # Crop original image at full resolution
        cropped = original_img[y1:y2, x1:x2]
        
        # Convert to PIL Image and preserve EXIF
        result = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
        
        # Try to preserve EXIF data from original image
        try:
            if hasattr(original_pil, '_getexif'):
                exif = original_pil._getexif()
                if exif is not None:
                    result.info['exif'] = exif
        except Exception as e:
            tool_logger.warning(f"Could not preserve EXIF data: {e}")
        
        # Create crop info dictionary
        crop_info = {
            "box": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2
            },
            "confidence": float(conf),
            "method": "yolo",
            "padding": padding,
            "original_size": [orig_width, orig_height],
            "cropped_size": [x2 - x1, y2 - y1],
            "orientation": orientation_details
        }
            
        return result, crop_info
    except Exception as e:
        tool_logger.error(f"YOLO cropping failed: {e}")
        return None

def detect_with_contours(image_path: Path) -> Optional[Image.Image]:
    """Try to detect document using contour detection"""
    try:
        # Load image using the format utility
        image, metadata = load_image(image_path)
        img_array = np.array(image)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Apply threshold
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
            
        # Get the largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Add padding
        padding = 30
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(img_array.shape[1] - x, w + padding)
        h = min(img_array.shape[0] - y, h + padding)
        
        # Crop the image
        cropped = img_array[y:y+h, x:x+w]
        
        # Convert to PIL Image
        return Image.fromarray(cropped)
    except Exception as e:
        tool_logger.warning(f"Contour detection failed: {e}")
        return None

def process_image(file_path: Path, out_path: Path, output_format: str = 'jpg') -> dict:
    """Process a single image file"""
    # Use SegmentHandler for path handling
    rel_path = SegmentHandler.get_relative_path(file_path)
    
    # Verify file exists
    if not file_path.exists():
        tool_logger.error(f"File does not exist: {file_path}")
        return {"success": False, "error": "File not found"}
    
    try:
        # Load image using the format utility
        image, metadata = load_image(file_path)
    except Exception as e:
        tool_logger.error(f"Failed to load image {file_path.name}: {e}")
        return {"success": False, "error": f"Failed to load image: {e}"}
    
    attempts = []
    
    # Try YOLO with original confidence threshold
    result = crop_with_yolo(file_path, out_path.parent, conf_threshold=0.35)
    attempts.append({
        "method": "yolo",
        "confidence": 0.35,
        "success": bool(result)
    })
    
    # If YOLO fails, try with lower confidence
    if not result:
        result = crop_with_yolo(file_path, out_path.parent, conf_threshold=0.15)
        attempts.append({
            "method": "yolo",
            "confidence": 0.15,
            "success": bool(result)
        })
    
    # If YOLO still fails, try contour detection
    if not result:
        result = detect_with_contours(file_path)
        attempts.append({
            "method": "contour",
            "success": bool(result)
        })
        if result:
            # For contour detection, create a simplified crop info
            crop_info = {
                "method": "contour",
                "original_size": list(image.size),
                "cropped_size": list(result.size)
            }
            result = (result, crop_info)
    
    # If all detection methods fail, use original image
    if not result:
        tool_logger.warning(f"Using original image as fallback for {file_path.name}")
        crop_info = {
            "method": "original",
            "original_size": list(image.size),
            "cropped_size": list(image.size)
        }
        result = (image, crop_info)
        attempts.append({
            "method": "original",
            "success": True
        })
    
    # Get the processed image and crop info
    processed_image, crop_info = result
    
    # Ensure output directory exists
    ensure_dirs(out_path)
    
    # Save the result using the format utility with the specified output format
    final_path, actual_format = save_image(processed_image, out_path, output_format)
    
    # Add attempts, format info, and metadata to the crop info
    crop_info["attempts"] = attempts
    crop_info["output_format"] = actual_format  # Store the actual format used
    crop_info["input_metadata"] = metadata
    
    # Get the relative path for the output file
    output_rel_path = SegmentHandler.get_relative_path(final_path)
    
    return {
        "outputs": [str(output_rel_path)],  # Use the new output path
        "source": str(rel_path),
        "details": crop_info
    }

def process_document(file_path: str, output_folder: Path, output_format: str = 'jpg') -> dict:
    """Process a single document file"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        return process_image(Path(f), o, output_format)
    
    # Get supported extensions and create file_types dict
    file_types = {ext: process_fn for ext in get_supported_extensions_list()}
    
    return process_file(
        file_path=str(file_path),
        output_folder=output_folder,
        process_fn=process_fn,
        file_types=file_types
    )

# Importable batch function - NO CLI dependencies
def crop_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    model_path: Path,
    output_format: str = "jpg",
    **kwargs
) -> dict:
    """
    Crop document pages to remove borders - importable function
    
    Returns:
        Processing statistics dictionary
    """
    global yolo_model
    yolo_model = YOLO(str(model_path))
    
    processor = BatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="crop",
        base_folder=source_folder,
        processor_fn=lambda f, o: process_document(f, o, output_format)
    )
    return processor.process()

# CLI wrapper for typer
def crop(
    source_folder: Path = typer.Argument(..., help="Source folder containing documents"),
    source_manifest: Path = typer.Argument(..., help="Manifest file"),
    output_folder: Path = typer.Argument(..., help="Output folder for cropped images"),
    model_path: Path = typer.Option(..., "--model-path", help="Path to YOLOv8 model file"),
    output_format: str = typer.Option("jpg", "--format", "-f", 
                                     help="Output format: png, jxl, or jpg",
                                     callback=validate_format)
):
    """Crop document pages to remove borders"""
    return crop_batch(source_folder, source_manifest, output_folder, model_path, output_format)

if __name__ == "__main__":
    typer.run(crop)