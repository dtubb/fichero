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

def init_yolo_model(model_path: str = "models/yolov8s-fichero.pt", worker_id: Optional[int] = None):
    """Initialize YOLO model with proper device optimization."""
    rich_log("info", "=== Initializing YOLO Model ===")
    
    # Check device availability
    rich_log("info", "Checking device availability:")
    rich_log("info", f"CUDA available: {torch.cuda.is_available()}")
    rich_log("info", f"MPS available: {torch.backends.mps.is_available()}")
    rich_log("info", f"MPS built: {torch.backends.mps.is_built()}")
    
    # Check if CPU is forced
    force_cpu = os.environ.get('FICHERO_FORCE_CPU', '0') == '1'
    if force_cpu:
        rich_log("info", "Force CPU mode enabled - using CPU for processing")
        device = "cpu"
    else:
        # Select best device
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
            # Clear MPS cache before moving model
            if hasattr(torch.mps, 'empty_cache'):
                torch.mps.empty_cache()
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
        
        # Get EXIF orientation
        try:
            exif = image._getexif()
            if exif:
                orientation = exif.get(274)  # 274 is the orientation tag
                details["exif_orientation"] = orientation
                
                if orientation == 3:
                    return "rotate_180", 180, details
                elif orientation == 6:
                    return "rotate_270", 270, details
                elif orientation == 8:
                    return "rotate_90", 90, details
        except:
            pass
        
        # If no EXIF or orientation not found, check dimensions
        if width < height:
            details["reason"] = "portrait_dimensions"
            return "rotate_90", 90, details
        
        details["reason"] = "no_rotation_needed"
        return "normal", 0, details
        
    except Exception as e:
        rich_log("error", f"Error getting image orientation: {e}")
        details["reason"] = f"error: {str(e)}"
        return "normal", 0, details

def crop_with_yolo(image_path: Path, output_folder: Path, conf_threshold: float = 0.35) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
    """Crop image using YOLOv8 model with optimized settings"""
    try:
        rich_log("info", f"=== Starting YOLO Processing for {image_path} ===")
        
        # Get worker ID and determine device
        worker_id = int(os.environ.get('WORKER_ID', '0'))
        worker_device = get_worker_device(worker_id, device)
        
        # Ensure model is on the correct device
        global yolo_model
        rich_log("info", "Checking model device placement:")
        
        # Check device by looking at first parameter
        first_param = next(yolo_model.model.parameters())
        current_device = first_param.device
        rich_log("info", f"Current model device: {current_device}")
        rich_log("info", f"Target device: {worker_device}")
        
        if str(current_device) != worker_device:
            rich_log("info", f"Moving model to device: {worker_device}")
            yolo_model.to(worker_device)
            rich_log("info", f"Model moved to device: {worker_device}")
        
        # Enhanced GPU verification at start of processing
        rich_log("info", "=== GPU Status ===")
        rich_log("info", f"Current device: {worker_device}")
        rich_log("info", f"MPS available: {torch.backends.mps.is_available()}")
        rich_log("info", f"MPS built: {torch.backends.mps.is_built()}")
        if "cuda" in worker_device:
            rich_log("info", f"CUDA device: {torch.cuda.current_device()}")
            rich_log("info", f"CUDA device name: {torch.cuda.get_device_name(0)}")
            rich_log("info", f"CUDA memory allocated: {torch.cuda.memory_allocated() / 1024**2:.1f} MB")
        elif worker_device == "mps":
            rich_log("info", "MPS device active")
            if hasattr(torch.mps, 'memory_allocated'):
                rich_log("info", f"MPS memory allocated: {torch.mps.memory_allocated() / 1024**2:.1f} MB")
        
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
        
        # Convert to numpy array for YOLO
        original_img = cv2.cvtColor(np.array(original_pil), cv2.COLOR_RGB2BGR)
        
        # Calculate target size maintaining aspect ratio and divisible by 32
        model_size = 640  # YOLO's preferred input size
        scale = min(model_size / orig_width, model_size / orig_height)
        model_width = int(orig_width * scale)
        model_height = int(orig_height * scale)
        
        # Ensure dimensions are divisible by 32
        model_width = ((model_width + 31) // 32) * 32
        model_height = ((model_height + 31) // 32) * 32
        
        # Resize image maintaining aspect ratio
        model_img = cv2.resize(original_img, (model_width, model_height), 
                             interpolation=cv2.INTER_LINEAR)
        
        rich_log("info", f"Model input size: {model_width}x{model_height} (scale: {scale:.3f})")
        
        # Enhanced GPU tensor conversion with memory optimization
        rich_log("info", "=== Tensor Conversion ===")
        tensor = torch.from_numpy(model_img).float()
        rich_log("info", f"Initial tensor device: {tensor.device}")
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)  # HWC -> BCHW
        rich_log("info", f"Tensor shape after permute: {tensor.shape}")
        
        # Move to device with detailed logging
        rich_log("info", f"Moving tensor to {worker_device}")
        tensor = tensor.to(worker_device)
        rich_log("info", f"Tensor device after move: {tensor.device}")
        
        # Optimize memory format for MPS
        if worker_device == "mps":
            rich_log("info", "Optimizing tensor for MPS")
            try:
                tensor = tensor.contiguous()
                rich_log("info", "Tensor made contiguous")
            except Exception as e:
                rich_log("warning", f"Could not optimize tensor for MPS: {e}")
        
        rich_log("info", f"Final input tensor device: {tensor.device}")
        
        # Run prediction with optimized settings
        rich_log("info", "=== Running YOLO Prediction ===")
        with torch.no_grad():  # Disable gradient calculation
            rich_log("info", "Starting prediction")
            results = list(yolo_model.predict(
                source=tensor,  # Pass the GPU tensor directly
                conf=conf_threshold,
                imgsz=(model_height, model_width),  # Use actual dimensions
                iou=0.45,
                verbose=False,
                stream=True,  # Enable streaming for better memory usage
                device=worker_device  # Explicitly set device
            ))
            rich_log("info", "Prediction complete")
        
        # Clear GPU memory
        clear_gpu_memory()
        
        rich_log("info", f"YOLO prediction results: {results}")
        
        if not results or not results[0].boxes:
            rich_log("warning", "No detections found")
            return None
            
        # Get the best detection (highest confidence)
        box = max(results[0].boxes.data, key=lambda x: x[4])
        x1, y1, x2, y2, conf = map(float, box[:5])
        rich_log("info", f"Detection in model space: x1={x1:.1f}, y1={y1:.1f}, x2={x2:.1f}, y2={y2:.1f}")
        
        # Calculate scale factors
        scale_x = orig_width / model_width
        scale_y = orig_height / model_height
        
        # Scale coordinates back to original image size
        x1 = int(x1 * scale_x)
        y1 = int(y1 * scale_y)
        x2 = int(x2 * scale_x)
        y2 = int(y2 * scale_y)
        rich_log("info", f"Scaled to original size: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
        
        # Apply padding only on left and bottom
        padding = 30
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(orig_width, x2)
        y2 = min(orig_height, y2 + padding)
        
        # Crop image
        cropped_img = original_pil.crop((x1, y1, x2, y2))
        
        # Return cropped image and details
        return cropped_img, {
            "confidence": float(conf),
            "original_size": {"width": orig_width, "height": orig_height},
            "crop_box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "orientation": orientation_details,
            "model_size": {"width": model_width, "height": model_height},
            "scale_factors": {"x": float(scale_x), "y": float(scale_y)}
        }
        
    except Exception as e:
        rich_log("error", f"Error in YOLO processing: {e}")
        return None

def process_batch(images: List[Image.Image], file_paths: List[Path]) -> List[Tuple[List[Image.Image], Dict[str, Any]]]:
    """Process a batch of images using YOLO model."""
    global yolo_model, device
    
    results = []
    for image, file_path in zip(images, file_paths):
        try:
            # Convert PIL image to numpy array
            img_array = np.array(image)
            
            # Convert to BGR for OpenCV
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Calculate target size maintaining aspect ratio and divisible by 32
            model_size = 640  # YOLO's preferred input size
            scale = min(model_size / image.width, model_size / image.height)
            model_width = int(image.width * scale)
            model_height = int(image.height * scale)
            
            # Ensure dimensions are divisible by 32
            model_width = ((model_width + 31) // 32) * 32
            model_height = ((model_height + 31) // 32) * 32
            
            # Resize image maintaining aspect ratio
            model_img = cv2.resize(img_bgr, (model_width, model_height), 
                                 interpolation=cv2.INTER_LINEAR)
            
            # Convert to tensor and move to device
            tensor = torch.from_numpy(model_img).float()
            tensor = tensor.permute(2, 0, 1).unsqueeze(0)  # HWC -> BCHW
            tensor = tensor.to(device)
            
            if device == "mps":
                tensor = tensor.contiguous()
            
            # Run YOLO prediction with error handling
            try:
                with torch.no_grad():
                    results_yolo = yolo_model.predict(
                        source=tensor,
                        conf=0.35,
                        imgsz=(model_height, model_width),
                        iou=0.45,
                        verbose=False,
                        stream=True,
                        device=device
                    )
                    results_yolo = list(results_yolo)
            except Exception as pred_error:
                rich_log("error", f"YOLO prediction failed for {file_path}: {str(pred_error)}")
                results.append(([image], {"error": f"Prediction failed: {str(pred_error)}"}))
                continue
            finally:
                # Clean up tensor
                del tensor
                clear_gpu_memory()
            
            # Process results
            if not results_yolo or not results_yolo[0].boxes:
                rich_log("warning", f"No detections found in {file_path}")
                results.append(([image], {"error": "No detections found"}))
                continue
            
            # Get the best detection (highest confidence)
            boxes = results_yolo[0].boxes
            best_box = boxes[0]  # Already sorted by confidence
            
            # Get coordinates and confidence
            try:
                x1, y1, x2, y2 = map(int, best_box.xyxy[0].tolist())
                conf = float(best_box.conf[0])
            except Exception as box_error:
                rich_log("error", f"Error extracting box coordinates for {file_path}: {str(box_error)}")
                results.append(([image], {"error": f"Box extraction failed: {str(box_error)}"}))
                continue
            
            # Add padding
            padding = 30
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(image.width, x2 + padding)
            y2 = min(image.height, y2 + padding)
            
            # Crop image
            try:
                cropped = image.crop((x1, y1, x2, y2))
                results.append(([cropped], {
                    "confidence": conf,
                    "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "original_size": {"width": image.width, "height": image.height},
                    "model_size": {"width": model_width, "height": model_height},
                    "scale_factors": {"x": float(image.width / model_width), "y": float(image.height / model_height)}
                }))
            except Exception as crop_error:
                rich_log("error", f"Error cropping image {file_path}: {str(crop_error)}")
                results.append(([image], {"error": f"Cropping failed: {str(crop_error)}"}))
            
        except Exception as e:
            rich_log("error", f"Error processing {file_path}: {str(e)}")
            results.append(([image], {"error": str(e)}))
        finally:
            # Clean up any remaining GPU memory
            clear_gpu_memory()
    
    return results

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
            
        try:
            # Process image
            image = Image.open(file_path)
            if image.mode != 'RGB':
                image = image.convert('RGB')
        except Exception as img_error:
            error_msg = f"Failed to open or convert image: {str(img_error)}"
            rich_log("error", error_msg)
            manifest.mark_error(f"documents/{rel_input}", error_msg)
            return False
        
        # Process single image as batch
        try:
            results = process_batch([image], [file_path])[0]
            parts, debug_info = results
        except Exception as batch_error:
            error_msg = f"Failed during batch processing: {str(batch_error)}"
            rich_log("error", error_msg)
            manifest.mark_error(f"documents/{rel_input}", error_msg)
            return False
        finally:
            # Clear GPU memory after processing
            clear_gpu_memory()
        
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
            parts[0].save(output_path, 'JPEG', quality=95)
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
        
        # Update manifest with success
        try:
            if not manifest.mark_done(
                f"documents/{rel_input}",
                crop_output_path=rel_output,
                crop_confidence=debug_info.get("confidence", 0.0),
                crop_orientation=debug_info.get("orientation", "normal"),
                crop_bbox=debug_info.get("box", {})
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