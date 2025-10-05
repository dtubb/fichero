import typer
from PIL import Image, ImageOps
from pathlib import Path
import numpy as np
import cv2
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import os
import json
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError


# Import utilities with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.files import ensure_dirs
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.parallel_batch_processor import create_parallel_batch_processor
except ImportError:
    # Fall back to relative imports (when run standalone)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.files import ensure_dirs
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.parallel_batch_processor import create_parallel_batch_processor


# Configure tool_logger
tool_logger = get_tool_logger('crop')

from dataclasses import dataclass
from typing import Optional as OptionalType

@dataclass
class ContourSettings:
    """Contour detection settings"""
    threshold_method: str = "auto"
    threshold_value: int = 150
    blur_kernel: int = 0
    edge_detection: bool = False
    min_contour_area: float = 0.5
    max_contour_area: float = 0.99
    min_aspect_ratio: float = 0.5
    max_aspect_ratio: float = 2.0
    padding: int = 30
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "threshold_method": self.threshold_method,
            "threshold_value": self.threshold_value,
            "blur_kernel": self.blur_kernel,
            "edge_detection": self.edge_detection,
            "min_contour_area": self.min_contour_area,
            "max_contour_area": self.max_contour_area,
            "min_aspect_ratio": self.min_aspect_ratio,
            "max_aspect_ratio": self.max_aspect_ratio,
            "padding": self.padding
        }

@dataclass
class CropInfo:
    """Standardized crop information for JSONL output"""
    box: dict  # {"x1": int, "y1": int, "x2": int, "y2": int}
    method: str  # "yolo", "contour", "original"
    confidence: float
    padding: int
    original_size: list[int]  # [width, height]
    cropped_size: list[int]  # [width, height]
    rotation: dict
    contour_settings: Optional[dict] = None  # Only for contour method
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL output"""
        result = {
            "box": self.box,
            "method": self.method,
            "confidence": self.confidence,
            "padding": self.padding,
            "original_size": self.original_size,
            "cropped_size": self.cropped_size,
            "rotation": self.rotation
        }
        if self.contour_settings:
            result["contour_settings"] = self.contour_settings
        return result

# Default contour detection settings
DEFAULT_CONTOUR_SETTINGS = ContourSettings()

def create_crop_info(
    box: dict,
    method: str,
    confidence: float,
    padding: int,
    original_size: list[int],
    cropped_size: list[int],
    rotation: dict,
    contour_settings: Optional[dict] = None
) -> CropInfo:
    """Create standardized crop info"""
    return CropInfo(
        box=box,
        method=method,
        confidence=confidence,
        padding=padding,
        original_size=original_size,
        cropped_size=cropped_size,
        rotation=rotation,
        contour_settings=contour_settings
    )

def validate_threshold_method(value: str) -> str:
    """Validate threshold method parameter"""
    valid_methods = ["auto", "binary", "binary_inverse", "otsu", "adaptive"]
    if value not in valid_methods:
        raise typer.BadParameter(f"Threshold method must be one of: {', '.join(valid_methods)}")
    return value

# Contour detection templates for different document types
CONTOUR_TEMPLATES = {
    "auto": {
        "name": "Auto-Detect",
        "description": "Automatically detects background and chooses best method",
        "settings": DEFAULT_CONTOUR_SETTINGS
    },
    "dark_background": {
        "name": "Dark Background",
        "description": "Optimized for documents on dark surfaces (desk, table)",
        "settings": ContourSettings(
            threshold_method="binary",
            threshold_value=120,
            blur_kernel=1,
            min_contour_area=0.15,
            max_contour_area=0.9,
            min_aspect_ratio=0.6,
            max_aspect_ratio=1.8,
            padding=25
        )
    },
    "light_background": {
        "name": "Light Background", 
        "description": "Optimized for documents on light surfaces (white table, paper)",
        "settings": ContourSettings(
            threshold_method="binary_inverse",
            threshold_value=180,
            blur_kernel=2,
            min_contour_area=0.2,
            max_contour_area=0.85,
            min_aspect_ratio=0.7,
            max_aspect_ratio=1.5,
            padding=20
        )
    },
    "edge_detection": {
        "name": "Edge Detection",
        "description": "Uses edge detection for documents with complex backgrounds",
        "settings": ContourSettings(
            threshold_method="otsu",
            threshold_value=150,
            blur_kernel=3,
            edge_detection=True,
            min_contour_area=0.25,
            max_contour_area=0.8,
            min_aspect_ratio=0.8,
            max_aspect_ratio=1.3,
            padding=15
        )
    },
    "high_contrast": {
        "name": "High Contrast",
        "description": "For documents with strong contrast and clean backgrounds",
        "settings": ContourSettings(
            threshold_method="adaptive",
            threshold_value=150,
            blur_kernel=0,
            min_contour_area=0.3,
            max_contour_area=0.75,
            min_aspect_ratio=0.9,
            max_aspect_ratio=1.2,
            padding=10
        )
    },
    "custom": {
        "name": "Custom Settings",
        "description": "Manually configure all parameters",
        "settings": None  # Will use individual parameters
    }
}

def get_contour_template(template_name: str) -> dict:
    """Get contour detection template settings"""
    if template_name not in CONTOUR_TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}. Available: {list(CONTOUR_TEMPLATES.keys())}")
    return CONTOUR_TEMPLATES[template_name]

def list_contour_templates() -> None:
    """List available contour detection templates"""
    print("Available contour detection templates:")
    print()
    for key, template in CONTOUR_TEMPLATES.items():
        print(f"  {key}: {template['name']}")
        print(f"    {template['description']}")
        if template["settings"]:
            settings = template["settings"]
            print(f"    Settings: {settings['threshold_method']} threshold, "
                  f"blur={settings['blur_kernel']}, edges={settings['edge_detection']}, "
                  f"area={settings['min_contour_area']:.1f}-{settings['max_contour_area']:.1f}, "
                  f"aspect={settings['min_aspect_ratio']:.1f}-{settings['max_aspect_ratio']:.1f}, "
                  f"padding={settings['padding']}")
        print()

# Load YOLO model (optional)
try:
    from ultralytics import YOLO
    yolo_model = None  # Will be initialized with the path from command line
    YOLO_AVAILABLE = True
    tool_logger.info("YOLO model will be loaded with provided path")
except ImportError:
    YOLO_AVAILABLE = False
    tool_logger.warning("YOLO not available - will use contour-based cropping as fallback")
except Exception as e:
    YOLO_AVAILABLE = False
    tool_logger.warning(f"Failed to import YOLO: {e} - will use contour-based cropping as fallback")



def apply_exif_rotation(image: Image.Image) -> tuple[Image.Image, dict]:
    """Apply EXIF rotation to image using PIL's built-in function.
    Returns (rotated_image, details) where details contains rotation information"""
    details = {
        "original_dimensions": list(image.size),
        "reason": None
    }
    
    try:
        # Use PIL's built-in EXIF transpose function
        rotated_image = ImageOps.exif_transpose(image)
        
        if rotated_image.size != image.size:
            details["reason"] = f"EXIF rotation applied: {image.size} -> {rotated_image.size}"
            details["final_dimensions"] = list(rotated_image.size)
        else:
            details["reason"] = "No EXIF rotation needed"
            details["final_dimensions"] = list(image.size)
        
        return rotated_image, details
        
    except Exception as e:
        details["reason"] = f"Error applying EXIF rotation: {str(e)}"
        return image, details

def crop_with_yolo(image: Image.Image, metadata: dict, conf_threshold: float = 0.35) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
    """Crop image using YOLOv8 model
    Returns tuple of (cropped_image, crop_info) where crop_info contains box coordinates and confidence"""
    if not YOLO_AVAILABLE:
        tool_logger.warning("YOLO not available - cannot perform YOLO-based cropping")
        return None
        
    try:
        # Apply EXIF rotation using PIL's built-in function
        original_pil, rotation_details = apply_exif_rotation(image)
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
        
        # Create crop info
        crop_info = create_crop_info(
            box={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            method="yolo",
            confidence=float(conf),
            padding=padding,
            original_size=[orig_width, orig_height],
            cropped_size=[x2 - x1, y2 - y1],
            rotation=rotation_details
        )
            
        tool_logger.info(f"YOLO detection successful with confidence {conf:.3f}")
        return result, crop_info
    except Exception as e:
        tool_logger.error(f"YOLO cropping failed: {e}")
        return None

def crop_with_contours(
    image: Image.Image, 
    metadata: dict,
    settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS
) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
    """Crop image using contour detection with configurable parameters
    
    Args:
        threshold_method: "auto", "binary", "otsu", "adaptive", "inverse"
        threshold_value: Threshold value (0-255) for binary thresholding
        blur_kernel: Gaussian blur kernel size (0 = no blur)
        edge_detection: Whether to use Canny edge detection
        min_contour_area: Minimum contour area as fraction of image (0.0-1.0)
        max_contour_area: Maximum contour area as fraction of image (0.0-1.0)
        min_aspect_ratio: Minimum width/height ratio
        max_aspect_ratio: Maximum width/height ratio
        padding: Padding to add around detected contour
    """
    try:
        # Apply EXIF rotation using PIL's built-in function
        image, rotation_details = apply_exif_rotation(image)
        orig_width, orig_height = image.size
        
        img_array = np.array(image)
        
        # Convert to grayscale
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Apply preprocessing
        if settings.blur_kernel > 0:
            gray = cv2.GaussianBlur(gray, (settings.blur_kernel, settings.blur_kernel), 0)
        
        # Apply thresholding based on method
        if settings.threshold_method == "auto":
            # Auto-detect background and choose appropriate method
            mean_brightness = np.mean(gray)
            if mean_brightness > 127:
                # Light background - use inverse threshold
                _, thresh = cv2.threshold(gray, settings.threshold_value, 255, cv2.THRESH_BINARY_INV)
            else:
                # Dark background - use normal threshold
                _, thresh = cv2.threshold(gray, settings.threshold_value, 255, cv2.THRESH_BINARY)
        elif settings.threshold_method == "binary":
            _, thresh = cv2.threshold(gray, settings.threshold_value, 255, cv2.THRESH_BINARY)
        elif settings.threshold_method == "binary_inverse":
            _, thresh = cv2.threshold(gray, settings.threshold_value, 255, cv2.THRESH_BINARY_INV)
        elif settings.threshold_method == "otsu":
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif settings.threshold_method == "adaptive":
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        else:
            # Default to binary
            _, thresh = cv2.threshold(gray, settings.threshold_value, 255, cv2.THRESH_BINARY)
        
        # Apply edge detection if requested
        if settings.edge_detection:
            edges = cv2.Canny(gray, 50, 150)
            thresh = cv2.dilate(edges, None, iterations=1)
        
        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return None
        
        # Filter contours by area and aspect ratio
        image_area = orig_width * orig_height
        valid_contours = []
        
        for contour in contours:
            area = cv2.contourArea(contour)
            area_ratio = area / image_area
            
            if area_ratio < settings.min_contour_area or area_ratio > settings.max_contour_area:
                continue
                
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h if h > 0 else 0
            
            if aspect_ratio < settings.min_aspect_ratio or aspect_ratio > settings.max_aspect_ratio:
                continue
                
            valid_contours.append(contour)
        
        if not valid_contours:
            return None
            
        # Get the largest valid contour
        largest_contour = max(valid_contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Add padding
        x = max(0, x - settings.padding)
        y = max(0, y - settings.padding)
        w = min(img_array.shape[1] - x, w + settings.padding)
        h = min(img_array.shape[0] - y, h + settings.padding)
        
        # Crop the image
        cropped = img_array[y:y+h, x:x+w]
        
        # Convert to PIL Image
        result = Image.fromarray(cropped)
        
        # Create crop info
        crop_info = create_crop_info(
            box={"x1": x, "y1": y, "x2": x + w, "y2": y + h},
            method="contour",
            confidence=1.0,  # Contour detection doesn't have confidence, but we include it for consistency
            padding=settings.padding,
            original_size=[orig_width, orig_height],
            cropped_size=[w, h],
            rotation=rotation_details,
            contour_settings=settings.to_dict()
        )
        
        tool_logger.info(f"Contour detection successful using {settings.threshold_method} threshold")
        return result, crop_info
    except Exception as e:
        tool_logger.warning(f"Contour detection failed: {e}")
        return None

def crop_with_fallback(image: Image.Image, metadata: dict) -> Tuple[Image.Image, Dict[str, Any]]:
    """Use original image as fallback when all detection methods fail
    Returns tuple of (rotated_image, crop_info)"""
    tool_logger.warning("Using original image as fallback - no document detected")
    
    # Apply EXIF rotation to the original image for consistency
    rotated_image, rotation_details = apply_exif_rotation(image)
    
    crop_info = create_crop_info(
        box={"x1": 0, "y1": 0, "x2": rotated_image.size[0], "y2": rotated_image.size[1]},
        method="original",
        confidence=1.0,  # Original image fallback has full confidence
        padding=0,  # No padding applied to original image
        original_size=list(rotated_image.size),
        cropped_size=list(rotated_image.size),
        rotation=rotation_details
    )
    
    return rotated_image, crop_info

def process_image(
    file_path: Path, 
    out_path: Path, 
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS
) -> dict:
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
    tool_logger.info(f"Attempting YOLO detection with confidence 0.35 for {file_path.name}")
    result = crop_with_yolo(image, metadata, conf_threshold=0.35)
    attempts.append({
        "method": "yolo",
        "confidence": 0.35,
        "success": bool(result)
    })
    
    # If YOLO fails, try with lower confidence
    if not result:
        tool_logger.info(f"YOLO failed, trying with confidence 0.15 for {file_path.name}")
        result = crop_with_yolo(image, metadata, conf_threshold=0.15)
        attempts.append({
            "method": "yolo",
            "confidence": 0.15,
            "success": bool(result)
        })
    
    # If YOLO still fails, try contour detection
    if not result:
        tool_logger.info(f"YOLO failed, trying contour detection for {file_path.name}")
        contour_result = crop_with_contours(image, metadata, contour_settings)
        attempts.append({
            "method": "contour",
            "success": bool(contour_result)
        })
        if contour_result:
            # crop_with_contours returns (image, crop_info) tuple
            result = contour_result
    
    # If all detection methods fail, use original image as fallback
    if not result:
        result = crop_with_fallback(image, metadata)
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
    
    # Convert crop_info to dict and add additional metadata
    crop_info_dict = crop_info.to_dict()
    crop_info_dict["attempts"] = attempts
    crop_info_dict["output_format"] = actual_format  # Store the actual format used
    crop_info_dict["input_metadata"] = metadata
    
    # Get the relative path for the output file
    output_rel_path = SegmentHandler.get_relative_path(final_path)
    
    return {
        "outputs": [str(output_rel_path)],  # Use the new output path
        "source": str(rel_path),
        "details": crop_info_dict
    }

def process_document(
    file_path: str, 
    output_folder: Path, 
    output_format: str = 'jpg',
    contour_settings: ContourSettings = DEFAULT_CONTOUR_SETTINGS
) -> dict:
    """Process a single document file"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        return process_image(Path(f), o, output_format, contour_settings)
    
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
    parallel_workers: int = 1,
    contour_template: str = "auto",
    contour_threshold_method: str = DEFAULT_CONTOUR_SETTINGS.threshold_method,
    contour_threshold_value: int = DEFAULT_CONTOUR_SETTINGS.threshold_value,
    contour_blur_kernel: int = DEFAULT_CONTOUR_SETTINGS.blur_kernel,
    contour_edge_detection: bool = DEFAULT_CONTOUR_SETTINGS.edge_detection,
    contour_min_area: float = DEFAULT_CONTOUR_SETTINGS.min_contour_area,
    contour_max_area: float = DEFAULT_CONTOUR_SETTINGS.max_contour_area,
    contour_min_aspect: float = DEFAULT_CONTOUR_SETTINGS.min_aspect_ratio,
    contour_max_aspect: float = DEFAULT_CONTOUR_SETTINGS.max_aspect_ratio,
    contour_padding: int = DEFAULT_CONTOUR_SETTINGS.padding,
    **kwargs
) -> dict:
    """
    Crop document pages to remove borders - importable function
    
    Returns:
        Processing statistics dictionary
    """
    global yolo_model
    if YOLO_AVAILABLE:
        try:
            yolo_model = YOLO(str(model_path))
            tool_logger.info("YOLO model loaded successfully")
        except Exception as e:
            tool_logger.warning(f"Failed to load YOLO model: {e} - will use contour-based cropping")
            yolo_model = None
    else:
        tool_logger.info("YOLO not available - using contour-based cropping")
        yolo_model = None
    
    # Apply contour template if specified
    if contour_template != "custom":
        try:
            template = get_contour_template(contour_template)
            if template["settings"]:
                tool_logger.info(f"Using contour template: {template['name']} - {template['description']}")
                settings = template["settings"]
                contour_threshold_method = settings.threshold_method
                contour_threshold_value = settings.threshold_value
                contour_blur_kernel = settings.blur_kernel
                contour_edge_detection = settings.edge_detection
                contour_min_area = settings.min_contour_area
                contour_max_area = settings.max_contour_area
                contour_min_aspect = settings.min_aspect_ratio
                contour_max_aspect = settings.max_aspect_ratio
                contour_padding = settings.padding
        except Exception as e:
            tool_logger.warning(f"Failed to apply contour template {contour_template}: {e}")
    
    # Create contour settings from parameters
    contour_settings = ContourSettings(
        threshold_method=contour_threshold_method,
        threshold_value=contour_threshold_value,
        blur_kernel=contour_blur_kernel,
        edge_detection=contour_edge_detection,
        min_contour_area=contour_min_area,
        max_contour_area=contour_max_area,
        min_aspect_ratio=contour_min_aspect,
        max_aspect_ratio=contour_max_aspect,
        padding=contour_padding
    )
    
    # Create parallel-enabled batch processor using shared utility
    ParallelCropProcessor = create_parallel_batch_processor("crop", BatchProcessor, process_image)
    
    processor = ParallelCropProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="crop",
        base_folder=source_folder,
        processor_fn=lambda f, o: process_document(
            f, o, output_format, contour_settings
        ),  # Fallback for sequential
        output_format=output_format,
        parallel_workers=parallel_workers
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
                                     callback=validate_format),
    # Contour detection template
    contour_template: str = typer.Option("auto", "--contour-template", 
                                        help="Contour detection template: auto, dark_background, light_background, edge_detection, high_contrast, custom"),
    # Contour detection parameters (used when template=custom)
    contour_threshold_method: str = typer.Option(DEFAULT_CONTOUR_SETTINGS.threshold_method, "--contour-threshold", 
                                                help="Threshold method: auto, binary, binary_inverse, otsu, adaptive",
                                                callback=validate_threshold_method),
    contour_threshold_value: int = typer.Option(DEFAULT_CONTOUR_SETTINGS.threshold_value, "--contour-threshold-value", 
                                               help="Threshold value (0-255) for binary thresholding"),
    contour_blur_kernel: int = typer.Option(DEFAULT_CONTOUR_SETTINGS.blur_kernel, "--contour-blur", 
                                           help="Gaussian blur kernel size (0 = no blur)"),
    contour_edge_detection: bool = typer.Option(DEFAULT_CONTOUR_SETTINGS.edge_detection, "--contour-edges", 
                                               help="Use Canny edge detection"),
    contour_min_area: float = typer.Option(DEFAULT_CONTOUR_SETTINGS.min_contour_area, "--contour-min-area", 
                                          help="Minimum contour area as fraction of image (0.0-1.0)"),
    contour_max_area: float = typer.Option(DEFAULT_CONTOUR_SETTINGS.max_contour_area, "--contour-max-area", 
                                          help="Maximum contour area as fraction of image (0.0-1.0)"),
    contour_min_aspect: float = typer.Option(DEFAULT_CONTOUR_SETTINGS.min_aspect_ratio, "--contour-min-aspect", 
                                            help="Minimum width/height ratio"),
    contour_max_aspect: float = typer.Option(DEFAULT_CONTOUR_SETTINGS.max_aspect_ratio, "--contour-max-aspect", 
                                            help="Maximum width/height ratio"),
    contour_padding: int = typer.Option(DEFAULT_CONTOUR_SETTINGS.padding, "--contour-padding", 
                                       help="Padding to add around detected contour")
):
    """Crop document pages to remove borders"""
    return crop_batch(
        source_folder, source_manifest, output_folder, model_path, output_format,
        contour_template=contour_template,
        contour_threshold_method=contour_threshold_method,
        contour_threshold_value=contour_threshold_value,
        contour_blur_kernel=contour_blur_kernel,
        contour_edge_detection=contour_edge_detection,
        contour_min_area=contour_min_area,
        contour_max_area=contour_max_area,
        contour_min_aspect=contour_min_aspect,
        contour_max_aspect=contour_max_aspect,
        contour_padding=contour_padding
    )

def list_templates():
    """List available contour detection templates"""
    list_contour_templates()

if __name__ == "__main__":
    typer.run(crop)