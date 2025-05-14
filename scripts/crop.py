import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

import typer
from PIL import Image
from pathlib import Path
import numpy as np
import cv2
from pdf2image import convert_from_path
from datetime import datetime
import logging
from typing import Dict, Any, Optional, Tuple, List
import json
import yaml
from scripts.utils.step_manifest import StepManifestManager
from scripts.utils.jsonl_manager import JSONLManager
from rich.console import Console
from PIL import ExifTags
import torch
import time
import platform
import multiprocessing
from ultralytics import YOLO
from scripts.utils.workflow_progress import create_progress_tracker
import multiprocessing as mp
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.live import Live

# Configure console for rich logging
console = Console()

app = typer.Typer()

def rich_log(level, message):
    """Log a message with rich formatting, respecting debug mode."""
    # Get debug mode from environment
    debug_mode = os.environ.get('FICHERO_DEBUG', '0') == '1'
    
    if level == "info":
        if debug_mode:
            console.log(f"[bold cyan][INFO][/bold cyan] {message}")
        else:
            # In non-debug mode, only show important info messages
            if "Processing complete" in message or "Processing " in message and "files" in message:
                console.log(f"[bold cyan][INFO][/bold cyan] {message}")
    elif level == "warning":
        console.log(f"[bold yellow][WARNING][/bold yellow] {message}")
    elif level == "error":
        console.log(f"[bold red][ERROR][/bold red] {message}")
    else:
        if debug_mode:
            console.log(message)

# Determine best device for the system
def get_best_device():
    """Determine the best available device for model inference."""
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        rich_log("info", "Using MPS (Metal Performance Shaders) for GPU acceleration")
        return "mps"
    elif torch.cuda.is_available():
        rich_log("info", "Using CUDA for GPU acceleration")
        return "cuda"
    else:
        rich_log("info", "Using CPU for inference")
        return "cpu"

def get_worker_device(worker_id: int, device: str) -> str:
    """Get the specific device for a worker based on worker ID."""
    if device == "cuda" and torch.cuda.is_available():
        gpu_count = torch.cuda.device_count()
        if gpu_count > 1:
            # Distribute workers across available GPUs
            gpu_id = worker_id % gpu_count
            rich_log("info", f"Worker {worker_id} using CUDA device {gpu_id}")
            return f"cuda:{gpu_id}"
    return device

# Load YOLO model with device optimization
def init_yolo_model(model_path: str = "models/yolov8s-fichero.pt"):
    """Initialize YOLO model with proper device optimization."""
    rich_log("info", "=== Initializing YOLO Model ===")
    
    # Check device availability
    rich_log("info", "Checking device availability:")
    rich_log("info", f"CUDA available: {torch.cuda.is_available()}")
    rich_log("info", f"MPS available: {torch.backends.mps.is_available()}")
    rich_log("info", f"MPS built: {torch.backends.mps.is_built()}")
    
    device = get_best_device()
    rich_log("info", f"Selected device: {device}")
    
    # Load model with detailed logging
    rich_log("info", f"Loading model from: {model_path}")
    try:
        yolo_model = YOLO(model_path)
        rich_log("info", "Model loaded successfully")
    except Exception as e:
        rich_log("error", f"Failed to load model: {e}")
        raise
    
    # Enhanced device optimization with detailed logging
    if device == "mps":
        rich_log("info", "Configuring MPS device")
        # Enable Metal Performance Shaders
        torch.backends.mps.enable_fallback_to_cpu = True  # Allow fallback to CPU if needed
        rich_log("info", "Moving model to MPS device")
        yolo_model.to(device)
        rich_log("info", "MPS configuration complete")
    elif device == "cuda":
        rich_log("info", "Configuring CUDA device:")
        rich_log("info", f"CUDA device count: {torch.cuda.device_count()}")
        rich_log("info", f"Current CUDA device: {torch.cuda.current_device()}")
        rich_log("info", f"CUDA device name: {torch.cuda.get_device_name(0)}")
        rich_log("info", "Moving model to CUDA device")
        yolo_model.to(device)
        rich_log("info", "Enabling half precision")
        yolo_model.model.half()
        rich_log("info", "CUDA configuration complete")
    else:
        rich_log("info", "Using CPU device")
        yolo_model.to(device)
    
    # Set model parameters for better performance
    yolo_model.conf = 0.35  # Confidence threshold
    yolo_model.iou = 0.45   # IoU threshold
    yolo_model.max_det = 1  # Only keep the best detection
    
    rich_log("info", "=== Model Initialization Complete ===")
    return yolo_model, device

# Initialize model globally with error handling
try:
    rich_log("info", "=== Starting Global Model Initialization ===")
    yolo_model, device = init_yolo_model()
    rich_log("info", "=== Global Model Initialization Complete ===")
except Exception as e:
    rich_log("error", f"=== Global Model Initialization Failed ===")
    rich_log("error", f"Error: {str(e)}")
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
        if worker_device == "mps":
            rich_log("info", "Clearing MPS cache")
            torch.mps.empty_cache()
        elif "cuda" in worker_device:
            rich_log("info", "Clearing CUDA cache")
            torch.cuda.empty_cache()
        
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
        rich_log("info", f"After padding: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
        
        # Crop original image at full resolution
        cropped = original_img[y1:y2, x1:x2]
        rich_log("info", f"Cropped size: {cropped.shape[1]}x{cropped.shape[0]}")
        
        # Convert to PIL Image and preserve EXIF
        result = Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))
        
        # Try to preserve EXIF data
        try:
            if hasattr(original_pil, '_getexif'):
                exif = original_pil._getexif()
                if exif is not None:
                    result.info['exif'] = exif
        except Exception as e:
            rich_log("warning", f"Could not preserve EXIF data: {e}")
        
        # Create crop info dictionary
        crop_info = {
            "box": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2
            },
            "confidence": float(conf),
            "orientation": {
                "true_orientation": true_orientation,
                "rotation_applied": rotation_angle,
                "details": orientation_details
            },
            "scaling": {
                "original_size": [orig_width, orig_height],
                "model_size": [model_width, model_height],
                "scale_factors": {
                    "x": scale_x,
                    "y": scale_y
                }
            }
        }
        
        rich_log("info", "=== YOLO Processing Complete ===")
        return result, crop_info
        
    except Exception as e:
        rich_log("error", f"=== YOLO Processing Failed ===")
        rich_log("error", f"Error in crop_with_yolo: {str(e)}")
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

def process_image(file_path: Path, out_path: Path) -> dict:
    """Process a single image file"""
    rich_log("info", f"[process_image] Processing {file_path}")
    # Get source folder structure from input path
    if 'documents/' in str(file_path):
        source_dir = Path(*file_path.parts[file_path.parts.index('documents')+1:])
    else:
        source_dir = file_path
    
    # Verify file exists and is readable
    if not file_path.exists():
        rich_log("error", f"File does not exist: {file_path}")
        return {"success": False, "error": "File not found"}
    
    try:
        # Try to open the image to verify it's readable
        with Image.open(file_path) as img:
            rich_log("info", f"Successfully opened image: {file_path.name} (format: {img.format})")
    except Exception as e:
        rich_log("error", f"Failed to open image {file_path.name}: {e}")
        return {"success": False, "error": f"Failed to open image: {e}"}
    
    attempts = []
    
    # Try YOLO with original confidence threshold
    rich_log("info", f"Attempting YOLO detection with confidence 0.35 for {file_path.name}")
    result = crop_with_yolo(file_path, out_path.parent, conf_threshold=0.35)
    attempts.append({
        "method": "yolo",
        "confidence": 0.35,
        "success": bool(result)
    })
    
    # If YOLO fails, try with lower confidence
    if not result:
        rich_log("info", f"Attempting YOLO detection with confidence 0.15 for {file_path.name}")
        result = crop_with_yolo(file_path, out_path.parent, conf_threshold=0.15)
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
    
    # Convert to JPG if needed
    image, crop_info = result
    if image.format != 'JPEG':
        rich_log("info", f"Converting {file_path.name} from {image.format} to JPEG")
        image = image.convert('RGB')

    # Create output path maintaining directory structure
    output_path = out_path / source_dir
    output_path = output_path.with_suffix('.jpg')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    rich_log("info", f"Saving cropped image to: {output_path}")
    image.save(output_path, 'JPEG', quality=95)
    rich_log("info", f"Saved cropped image to {output_path}")
    
    # Build relative path preserving hierarchy
    rel_path = Path('assets/crops') / source_dir.with_suffix('.jpg')
    
    # Add attempts to the crop info
    crop_info["attempts"] = attempts
    
    return {
        "outputs": [str(rel_path)],
        "details": crop_info  # Include the crop info in the details
    }

def process_pdf(file_path: Path, out_path: Path) -> dict:
    """Process a PDF file"""
    # Get source folder structure from input path
    if 'documents/' in str(file_path):
        source_dir = Path(*file_path.parts[file_path.parts.index('documents')+1:])
    else:
        source_dir = file_path
    
    # Convert and process each page
    images = convert_from_path(file_path, dpi=300)
    outputs = []
    details = {}
    
    # Create directory for PDF pages
    pdf_dir = out_path / source_dir.parent / f"{source_dir.stem}"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    
    for i, image in enumerate(images):
        rich_log("info", f"Processing page {i+1} of {len(images)} from {file_path.name}")
        # Save original page as JPG
        page_path = pdf_dir / f"page_{i + 1}.jpg"
        image.save(page_path, "JPEG", quality=95)
        
        # Process with YOLO
        result = crop_with_yolo(page_path, pdf_dir, conf_threshold=0.35)
        
        if result:
            # Save cropped page as JPG
            cropped_path = pdf_dir / f"page_{i + 1}_cropped.jpg"
            result[0].save(cropped_path, "JPEG", quality=95)
            
            # Build relative path preserving hierarchy
            rel_path = Path('assets/crops') / source_dir.parent / f"{source_dir.stem}" / f"page_{i + 1}_cropped.jpg"
            outputs.append(str(rel_path))
            
            details[f"page_{i + 1}"] = result[1]  # Include the crop info
        else:
            details[f"page_{i + 1}"] = {
                "success": False,
                "error": "No detection",
                "original_size": list(image.size),
                "attempts": [{
                    "method": "yolo",
                    "confidence": 0.35,
                    "success": False
                }]
            }
    
    return {
        "outputs": outputs,
        "details": details
    }

def process_document(file_path: str, output_folder: Path) -> dict:
    """Process a single document file"""
    file_path = Path(file_path)
    
    # Skip directories
    if file_path.is_dir():
        rich_log("info", f"Skipping directory: {file_path}")
        return {"success": True, "details": {"skipped": "directory"}}
    
    try:
        # Ensure output folder exists
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Get the relative path from documents/
        if 'documents/' in str(file_path):
            rel_path = Path(*file_path.parts[file_path.parts.index('documents')+1:])
        else:
            rel_path = file_path
            
        # Process image
        result = process_image(file_path, output_folder)
        
        # Add success flag and ensure outputs are set
        if "outputs" not in result:
            result["outputs"] = []
        if "details" not in result:
            result["details"] = {}
        
        result["success"] = True
        return result
        
    except Exception as e:
        rich_log("error", f"Error processing {file_path}: {e}")
        return {
            "success": False,
            "error": str(e),
            "outputs": [],
            "details": {"error": str(e)}
        }

@app.command()
def crop(
    manifest_file: Path = typer.Argument(..., help="Manifest file"),
    project_folder: Path = typer.Argument(..., help="Project folder"),
    model_path: str = typer.Option("models/yolov8s-fichero.pt", help="Path to YOLO model"),
    conf_threshold: float = typer.Option(0.35, help="Confidence threshold"),
    batch_size: int = typer.Option(10, help="Batch size for parallel processing"),
    max_workers: Optional[int] = typer.Option(None, help="Number of worker processes"),
    debug: bool = typer.Option(False, help="Enable debug logging")
):
    """Crop documents using computer vision techniques."""
    # Set debug mode in environment
    if debug:
        os.environ['FICHERO_DEBUG'] = '1'
        
        # Log detailed hardware information
        rich_log("info", "=== Hardware Information ===")
        rich_log("info", f"System: {platform.system()} {platform.release()}")
        rich_log("info", f"Machine: {platform.machine()}")
        rich_log("info", f"Processor: {platform.processor()}")
        
        # Log CPU information
        cpu_count = multiprocessing.cpu_count()
        rich_log("info", f"CPU Cores: {cpu_count}")
        
        # Log GPU information
        if torch.cuda.is_available():
            rich_log("info", "=== CUDA Information ===")
            rich_log("info", f"CUDA Available: Yes")
            rich_log("info", f"CUDA Version: {torch.version.cuda}")
            rich_log("info", f"GPU Device: {torch.cuda.get_device_name(0)}")
            rich_log("info", f"GPU Count: {torch.cuda.device_count()}")
        elif torch.backends.mps.is_available():
            rich_log("info", "=== MPS Information ===")
            rich_log("info", "MPS (Metal Performance Shaders) Available: Yes")
            rich_log("info", "Using Apple Silicon GPU")
        else:
            rich_log("info", "No GPU acceleration available - using CPU")
        
        # Log model information
        rich_log("info", "=== Model Information ===")
        rich_log("info", f"Model Path: {model_path}")
        rich_log("info", f"Model Device: {device}")
        rich_log("info", f"Model Parameters: {sum(p.numel() for p in yolo_model.parameters())}")
        rich_log("info", f"Model Half Precision: {device != 'cpu'}")
        
        # Log worker information
        worker_id = os.environ.get('WORKER_ID', None)
        if worker_id is not None:
            rich_log("info", f"Running as Worker {worker_id}")
        else:
            rich_log("info", "Running in single-process mode")
        
        rich_log("info", "========================")
    else:
        os.environ['FICHERO_DEBUG'] = '0'

    # Set up paths based on project structure
    source_folder = project_folder / "documents"
    output_folder = project_folder / "assets" / "crops"
    
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Initialize manifest manager
    manifest = StepManifestManager(manifest_file, "crop")
    
    # Get worker ID
    worker_id = os.environ.get('WORKER_ID', '0')
    rich_log("info", f"Worker {worker_id} started")
    
    # Process files until none are left
    processed = 0
    while True:
        # Get next pending file
        input_path = manifest.get_next_pending()
        if not input_path:
            rich_log("info", f"Worker {worker_id} finished - no more files to process")
            break
        
        try:
            # Remove documents/ prefix from input_path if present
            if input_path.startswith('documents/'):
                input_path = input_path[10:]  # Remove 'documents/' prefix
            
            # Construct full paths
            full_input_path = source_folder / input_path
            full_output_path = output_folder / input_path
            
            # Log current file being processed
            rich_log("info", f"Processing: {input_path}")
            
            # Process the file
            result = process_document(str(full_input_path), output_folder)
            
            if result["success"]:
                processed += 1
                rich_log("info", f"Completed: {input_path}")
                # Update manifest with results
                manifest.mark_done(
                    input_path,
                    crop_outputs=result.get("outputs", []),
                    crop_details=result.get("details", {})
                )
            else:
                rich_log("error", f"Failed to process {input_path}: {result.get('error', 'Unknown error')}")
                manifest.mark_error(input_path, result.get("error", "Unknown error"))
                
        except Exception as e:
            rich_log("error", f"Error processing {input_path}: {e}")
            manifest.mark_error(input_path, str(e))
    
    rich_log("info", f"Worker {worker_id} processed {processed} files")

if __name__ == "__main__":
    app()