"""
Document Cropping Processor using YOLO

This script processes scanned document images using YOLOv8 to detect and crop documents.
Key features:
- GPU Acceleration with CUDA and Apple Silicon (MPS) support
- Single worker mode for direct execution
- Automatic device optimization
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

import typer
from PIL import Image
import numpy as np
import cv2
import torch
from ultralytics import YOLO
from datetime import datetime
import logging
from typing import Dict, Any, Optional, Tuple, List
import json
import yaml
import time
import platform
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.live import Live
from PIL import ExifTags

from scripts.utils.step_manifest import StepManifestManager
from scripts.utils.workflow_progress import create_progress_tracker
from scripts.utils.file_manager import FileManager
from scripts.utils.logging_utils import rich_log, setup_logging
from scripts.utils.worker_manager import clear_gpu_memory, get_best_device, get_worker_device

# Initialize global variables
yolo_model = None
device = None
file_manager = None

app = typer.Typer()

def get_best_device():
    """Determine the best available device for model inference."""
    # Check if CPU is forced
    force_cpu = os.environ.get('FICHERO_FORCE_CPU', '0') == '1'
    if force_cpu:
        rich_log("info", "Force CPU mode enabled - using CPU for processing")
        return "cpu"
    
    # Select best device
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        rich_log("info", "Using MPS (Metal Performance Shaders) for GPU acceleration")
        return "mps"
    elif torch.cuda.is_available():
        rich_log("info", "Using CUDA for GPU acceleration")
        return "cuda"
    else:
        rich_log("info", "Using CPU for inference")
        return "cpu"

def init_yolo_model(model_path: str = "models/yolov8s-fichero.pt", worker_id: Optional[int] = None):
    """Initialize YOLO model with proper device optimization."""
    rich_log("info", "=== Initializing YOLO Model ===")
    
    # Check device availability
    rich_log("info", "Checking device availability:")
    rich_log("info", f"CUDA available: {torch.cuda.is_available()}")
    rich_log("info", f"MPS available: {torch.backends.mps.is_available()}")
    rich_log("info", f"MPS built: {torch.backends.mps.is_built()}")
    
    # Get device
    device = get_best_device()
    if worker_id is not None:
        device = get_worker_device(worker_id, device)
    rich_log("info", f"Selected device: {device}")
    
    # Load model with detailed logging
    rich_log("info", f"Loading model from: {model_path}")
    try:
        yolo_model = YOLO(model_path)
        rich_log("info", "Model loaded successfully")
        
        # Move model to device with proper MPS handling
        if device == "mps":
            rich_log("info", "Moving model to MPS device")
            # Enable MPS fallback to CPU if needed
            torch.backends.mps.enable_fallback_to_cpu = True
            yolo_model.to("mps")
            rich_log("info", "MPS configuration complete")
        elif device == "cuda":
            rich_log("info", "Moving model to CUDA device")
            yolo_model.to("cuda")
            rich_log("info", "Enabling half precision")
            yolo_model.model.half()  # Use FP16 for better performance
        else:
            rich_log("info", "Using CPU device")
            yolo_model.to("cpu")
            
        return yolo_model, device
    except Exception as e:
        rich_log("error", f"Failed to load model: {e}")
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
        rich_log("error", f"Error getting image orientation: {e}")
        details["reason"] = f"error: {str(e)}"
        return "unknown", 0, details

def crop_with_yolo(image_path: Path, output_folder: Path, conf_threshold: float = 0.35) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
    """Crop image using YOLOv8 model with optimized settings"""
    try:
        rich_log("info", f"=== Starting YOLO Processing for {image_path} ===")
        
        # Get true orientation and required rotation
        true_orientation, rotation_angle, orientation_details = get_image_orientation(image_path)
        rich_log("info", f"Image orientation: {true_orientation}, Rotation: {rotation_angle}")
        
        # Read original image and convert to PIL
        original_pil = Image.open(image_path)
        orig_width, orig_height = original_pil.size
        rich_log("info", f"Original image size: {orig_width}x{orig_height}")
        
        # Apply rotation if needed
        if rotation_angle > 0:
            original_pil = original_pil.rotate(rotation_angle, expand=True)
            orig_width, orig_height = original_pil.size
            rich_log("info", f"Image size after rotation: {orig_width}x{orig_height}")
        
        # Run prediction with optimized settings
        rich_log("info", "=== Running YOLO Prediction ===")
        with torch.no_grad():  # Disable gradient calculation
            results = list(yolo_model.predict(
                source=original_pil,  # Pass PIL image directly
                conf=conf_threshold,
                imgsz=640,  # Standard YOLO size
                iou=0.45,
                verbose=False
            ))
        
        if not results or not results[0].boxes:
            rich_log("warning", "No detections found")
            return None
            
        # Get the best detection (highest confidence)
        box = max(results[0].boxes.data, key=lambda x: x[4])
        x1, y1, x2, y2, conf = map(float, box[:5])
        rich_log("info", f"Detection: x1={x1:.1f}, y1={y1:.1f}, x2={x2:.1f}, y2={y2:.1f}")
        
        # Apply padding only on left and bottom
        padding = 30
        x1 = max(0, x1 - padding)  # Add padding to left
        y1 = max(0, y1 - padding)  # Add padding to top
        x2 = min(orig_width, x2)   # No padding on right
        y2 = min(orig_height, y2 + padding)  # Add padding to bottom
        rich_log("info", f"After padding: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
        
        # Crop image
        cropped_img = original_pil.crop((x1, y1, x2, y2))
        
        # Try to preserve EXIF data
        try:
            if hasattr(original_pil, '_getexif'):
                exif = original_pil._getexif()
                if exif is not None:
                    cropped_img.info['exif'] = exif
        except Exception as e:
            rich_log("warning", f"Could not preserve EXIF data: {e}")
        
        # Return cropped image and details
        return cropped_img, {
            "confidence": float(conf),
            "original_size": {"width": orig_width, "height": orig_height},
            "crop_box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "orientation": orientation_details
        }
        
    except Exception as e:
        rich_log("error", f"Error in YOLO processing: {e}")
        return None

def detect_with_contours(image_path: Path) -> Optional[Image.Image]:
    """Try to detect document using contour detection"""
    try:
        # Read image
        img = cv2.imread(str(image_path))
        if img is None:
            return None
            
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
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
        w = min(img.shape[1] - x, w + padding)
        h = min(img.shape[0] - y, h + padding)
        
        # Crop the image
        cropped = img[y:y+h, x:x+w]
        
        # Convert to PIL Image
        return Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
    except Exception as e:
        rich_log("warning", f"Contour detection failed: {e}")
        return None

def process_document(file_path: str, output_folder: Path, manifest: StepManifestManager) -> bool:
    """Process a single document file."""
    global file_manager
    
    file_path = Path(file_path)
    output_folder = Path(output_folder)
    
    # Skip directories
    if file_path.is_dir():
        rich_log("info", f"Skipping directory: {file_path}")
        return True
    
    try:
        rich_log("info", f"[CROP] Starting processing: {file_path}")
        
        # Get relative path from project root for input file
        rel_input = str(file_manager.get_relative_path(file_path, base_prefix="documents"))
        
        # Verify file exists and is readable
        if not file_path.exists():
            error_msg = f"File does not exist: {file_path}"
            rich_log("error", error_msg)
            manifest.mark_error(f"documents/{rel_input}", error_msg)
            return False
        
        # Process image
        try:
            image = Image.open(file_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
        except Exception as img_error:
            error_msg = f"Failed to open or convert image: {str(img_error)}"
            rich_log("error", error_msg)
            manifest.mark_error(f"documents/{rel_input}", error_msg)
            return False
        
        attempts = []
        
        # Try YOLO with original confidence threshold
        rich_log("info", f"Attempting YOLO detection with confidence 0.35 for {file_path.name}")
        result = crop_with_yolo(file_path, output_folder, conf_threshold=0.35)
        attempts.append({
            "method": "yolo",
            "confidence": 0.35,
            "success": bool(result)
        })
        
        # If YOLO fails, try with lower confidence
        if not result:
            rich_log("info", f"Attempting YOLO detection with confidence 0.15 for {file_path.name}")
            result = crop_with_yolo(file_path, output_folder, conf_threshold=0.15)
            attempts.append({
                "method": "yolo",
                "confidence": 0.15,
                "success": bool(result)
            })
        
        # If YOLO still fails, try contour detection
        if not result:
            rich_log("info", f"Attempting contour detection for {file_path.name}")
            result = detect_with_contours(file_path)
            attempts.append({
                "method": "contour",
                "success": bool(result)
            })
            if result:
                # For contour detection, create a simplified crop info
                crop_info = {
                    "method": "contour",
                    "original_size": list(Image.open(file_path).size),
                    "cropped_size": list(result.size)
                }
                result = (result, crop_info)
        
        # If all detection methods fail, use original image
        if not result:
            rich_log("warning", f"Using original image as fallback for {file_path.name}")
            original = Image.open(file_path)
            crop_info = {
                "method": "original",
                "original_size": list(original.size),
                "cropped_size": list(original.size)
            }
            result = (original, crop_info)
            attempts.append({
                "method": "original",
                "success": True
            })
        
        # Create output path maintaining directory structure
        output_path = file_manager.get_output_path(
            input_path=rel_input,
            output_folder='crops',
            suffix='.jpg'
        )
        
        # Ensure output directory exists
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as dir_error:
            error_msg = f"Failed to create output directory: {str(dir_error)}"
            rich_log("error", error_msg)
            manifest.mark_error(f"documents/{rel_input}", error_msg)
            return False
        
        # Save image
        try:
            result[0].save(output_path, 'JPEG', quality=95)
            rich_log("info", f"[CROP] Saved output to: {output_path}")
        except Exception as save_error:
            error_msg = f"Error saving output to {output_path}: {str(save_error)}"
            rich_log("error", error_msg)
            manifest.mark_error(f"documents/{rel_input}", error_msg)
            return False
        
        # Get relative path from project root for output
        rel_output = str(file_manager.get_relative_path(output_path, base_prefix="assets"))
        
        rich_log("info", f"[CROP] Relative output path: {rel_output}")
        rich_log("info", f"[CROP] Finished processing: {file_path}")
        
        # Add attempts to the crop info
        crop_info = result[1]
        crop_info["attempts"] = attempts
        
        # Update manifest with success
        try:
            if not manifest.mark_done(
                f"documents/{rel_input}",
                crop_output_path=rel_output,
                crop_confidence=crop_info.get("confidence", 0.0),
                crop_orientation=crop_info.get("orientation", "normal"),
                crop_bbox=crop_info.get("crop_box", {})
            ):
                error_msg = "Failed to update manifest"
                rich_log("error", error_msg)
                return False
        except Exception as manifest_error:
            error_msg = f"Error updating manifest: {str(manifest_error)}"
            rich_log("error", error_msg)
            return False

        rich_log("info", f"Completed: {rel_input}")
        return True
        
    except Exception as e:
        error_msg = f"[CROP] Unexpected error processing {file_path}: {str(e)}"
        rich_log("error", error_msg)
        try:
            manifest.mark_error(f"documents/{rel_input}", error_msg)
        except:
            rich_log("error", f"Failed to update manifest for {rel_input}")
        return False
    finally:
        # Always clear GPU memory after processing
        clear_gpu_memory()

@app.command()
def crop(
    manifest_file: Path = typer.Argument(..., help="Manifest file"),
    project_folder: Path = typer.Argument(..., help="Project folder"),
    model_path: str = typer.Option("models/yolov8s-fichero.pt", help="Path to YOLO model"),
    conf_threshold: float = typer.Option(0.35, help="Confidence threshold"),
    debug: bool = typer.Option(False, help="Enable debug logging")
):
    """Process documents using YOLO for cropping."""
    # Set up logging
    setup_logging(level=logging.DEBUG if debug or os.environ.get('FICHERO_DEBUG') == '1' else logging.INFO)
    
    # Initialize file manager
    global file_manager
    file_manager = FileManager(project_folder)
    
    # Initialize YOLO model
    global yolo_model, device
    yolo_model, device = init_yolo_model(model_path)
    
    # Initialize manifest manager
    manifest = StepManifestManager(manifest_file, "crop")
    rich_log("debug", f"Initialized manifest manager with file: {manifest_file}")
    
    # Process files
    processed = 0
    while True:
        # Get next pending file
        input_path = manifest.get_next_pending()
        if not input_path:
            rich_log("info", "No more files to process")
            break
        
        try:
            rich_log("debug", f"Processing file: {input_path}")
            # Process the file
            if process_document(str(project_folder / input_path), project_folder, manifest):
                processed += 1
                
        except Exception as e:
            error_msg = str(e)
            rich_log("error", f"Error processing {input_path}: {error_msg}")
            if not manifest.mark_error(input_path, error_msg):
                rich_log("error", f"Failed to update manifest error status for {input_path}")
    
    rich_log("info", f"Completed processing {processed} files")

if __name__ == "__main__":
    app()