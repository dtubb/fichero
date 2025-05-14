"""
Image Splitting Processor for Document Digitization

This script processes scanned document images, with intelligent detection of:
1. Notebooks and spiral-bound documents (detected by vertical patterns and content distribution)
2. Single-page documents (labels, covers, envelopes)
3. Photo albums and photographic content
4. Double-page book spreads

Key Features:
- Multi-stage document type detection:
  * First checks for notebook/spiral binding patterns
  * Then analyzes for labels/covers using text density and filename patterns
  * Finally checks for photos using edge density and variance
- Smart split point detection:
  * Centers splits for notebooks and double pages
  * Prevents splitting of single-page documents
  * Handles both sharp and subtle page divisions
- Comprehensive content analysis:
  * Measures content distribution across page halves
  * Analyzes vertical patterns for binding detection
  * Considers edge density and text patterns
  * Uses filename patterns for first/cover pages
- GPU Acceleration:
  * Uses PyTorch for GPU-accelerated image processing
  * Optimizes pattern detection and content analysis
  * Supports both CUDA and Apple Silicon (MPS) devices

Detection Thresholds:
- Notebooks: aspect ratio > 1.35, width > 2000px, strong vertical patterns
- Labels/Covers: high text density, specific aspect ratios, filename patterns
- Photos: high edge density/variance, balanced content distribution
- General splits: adaptive thresholds based on document characteristics
"""

import typer
from PIL import Image
from pathlib import Path
import numpy as np
import cv2
import torch
from pdf2image import convert_from_path
from rich.console import Console
import json
from typing import Set, Optional, Tuple, List, Dict, Any
import logging
import os
import multiprocessing as mp

from scripts.utils.image_utils import (
    get_image_orientation,
    prepare_image_for_model,
    save_image_with_metadata,
    get_relative_path
)
from scripts.utils.workflow_progress import create_progress_tracker
from scripts.utils.parallel import process_directory

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

console = Console()

# Set up device for GPU acceleration
device = torch.device('mps' if torch.backends.mps.is_available() else 
                     'cuda' if torch.cuda.is_available() else 'cpu')
logger.info(f"Using device: {device}")

def to_tensor(img_array: np.ndarray) -> torch.Tensor:
    """Convert numpy array to PyTorch tensor and move to GPU."""
    return torch.from_numpy(img_array).float().to(device)

def to_numpy(tensor: torch.Tensor) -> np.ndarray:
    """Convert PyTorch tensor to numpy array."""
    return tensor.cpu().numpy()

def analyze_page_content(img_array: np.ndarray) -> tuple[float, float, float]:
    """
    Enhanced content analysis that also detects vertical patterns
    Returns (left_density, right_density, pattern_strength)
    """
    # Convert to tensor for GPU processing
    img_tensor = to_tensor(img_array)
    height, width = img_tensor.shape
    mid = width // 2
    
    # Consider pixels darker than 240 as content
    threshold = 240
    left_content = torch.sum(img_tensor[:, :mid] < threshold)
    right_content = torch.sum(img_tensor[:, mid:] < threshold)
    
    # Calculate vertical pattern strength (for notebook detection)
    center_region = img_tensor[:, mid-100:mid+100]
    vertical_sums = torch.sum(center_region, dim=0)
    pattern_strength = torch.std(torch.diff(vertical_sums))
    
    # Calculate density as percentage
    total_pixels = height * (width // 2)
    return (
        float(left_content / total_pixels),
        float(right_content / total_pixels),
        float(pattern_strength)
    )

def convert_to_serializable(obj):
    """Convert numpy/custom types to JSON serializable Python types"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.float32) or isinstance(obj, np.float64):
        return float(obj)
    if isinstance(obj, np.int32) or isinstance(obj, np.int64):
        return int(obj)
    if isinstance(obj, (list, tuple)):
        return [convert_to_serializable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, bool):
        return bool(obj)  # Ensure booleans are Python native
    return obj

def is_cover_or_label(img_array: np.ndarray, aspect_ratio: float) -> tuple[bool, dict]:
    """
    Detect if image is a cover page or label based on:
    - Content density distribution
    - Edge patterns
    - Text layout patterns
    """
    height, width = img_array.shape
    
    # Calculate text/content regions
    text_mask = img_array < 200  # Threshold for text/content
    
    # Check content distribution
    rows_with_content = np.any(text_mask, axis=1)
    cols_with_content = np.any(text_mask, axis=0)
    
    # Calculate content spread
    content_height = np.sum(rows_with_content) / height
    content_width = np.sum(cols_with_content) / width
    
    # Calculate edge characteristics
    edges = cv2.Canny(img_array, 100, 200)
    edge_density = np.sum(edges > 0) / (width * height)
    
    # Characteristics of cover pages/labels:
    # 1. More spread out content (not concentrated in columns)
    # 2. Lower edge density than notebooks
    # 3. Often have specific aspect ratios
    is_cover = (
        (content_width > 0.7) and  # Content spread across width
        (edge_density < 0.1) and   # Fewer sharp edges than notebooks
        (1.3 < aspect_ratio < 1.9)  # Typical cover aspect ratios
    )
    
    metrics = {
        "content_height": float(content_height),
        "content_width": float(content_width),
        "edge_density": float(edge_density)
    }
    
    return is_cover, metrics

def is_likely_label_from_name(file_path: Path) -> bool:
    """Enhanced label/first page detection from filename"""
    name = file_path.stem.lower()
    parent = file_path.parent.name.lower()
    
    # Common patterns for first/cover pages
    label_patterns = [
        "_001",          # First page in sequence
        "_img_001",      # First image
        "cover",
        "label",
        "title",
        "front",
        "endpaper"
    ]
    
    # Detect photo albums by folder name
    photo_patterns = [
        "photo",
        "album",
        "photograph"
    ]
    
    is_first = any(part.isdigit() and int(part) == 1 for part in name.split('_'))
    is_in_photo_album = any(pattern in parent for pattern in photo_patterns)
    
    return (
        any(pattern in name for pattern in label_patterns) or
        is_first or
        is_in_photo_album
    )

def detect_document_type(img_array: np.ndarray, width: int, height: int, aspect_ratio: float, file_path: Path = None) -> dict:
    """Detect document type and determine if it should be split."""
    # Convert to tensor for GPU processing
    img_tensor = to_tensor(img_array)
    
    # Calculate basic metrics using GPU
    edges = cv2.Canny(img_array, 100, 200)  # Keep CPU for now as cv2.cuda requires special build
    edge_tensor = to_tensor(edges)
    edge_density = float(torch.sum(edge_tensor > 0) / (width * height))
    text_density = float(torch.mean(img_tensor < 200))

    # Calculate content distribution using GPU
    left_half = img_tensor[:, :width//2]
    right_half = img_tensor[:, width//2:]
    left_density = float(torch.mean(left_half < 200))
    right_density = float(torch.mean(right_half < 200))
    content_balance = float(torch.abs(left_density - right_density))
    
    # Check for notebook/spiral binding pattern
    center_width = 100
    center_x = width // 2
    center_region = img_tensor[:, center_x-center_width:center_x+center_width]
    vertical_pattern = float(torch.std(torch.sum(center_region, dim=0)))
    
    # Calculate periodic binding pattern using GPU
    vertical_sums = torch.sum(center_region, dim=0)
    kernel = torch.ones(5, device=device) / 5
    smooth_sums = torch.nn.functional.conv1d(
        vertical_sums.unsqueeze(0).unsqueeze(0),
        kernel.unsqueeze(0).unsqueeze(0),
        padding=2
    ).squeeze()
    
    # Find peaks in smoothed signal
    pattern_peaks = int(torch.sum(
        (smooth_sums[1:-1] < smooth_sums[:-2]) & 
        (smooth_sums[1:-1] < smooth_sums[2:])
    ).item())
    
    # Enhanced double page detection
    is_double_page = (
        width > 2000 and
        aspect_ratio > 1.35 and
        (
            (vertical_pattern > 1500 and edge_density > 0.01) or
            (text_density > 0.9 and content_balance < 0.2) or
            (pattern_peaks >= 2 and edge_density > 0.01) or
            (aspect_ratio > 1.5 and vertical_pattern > 1000)
        )
    )

    # Check for label/first page
    is_likely_first = file_path and any(x in str(file_path).lower() for x in [
        "_001", "_img_001", "cover", "label", "title", "front", "endpaper"
    ])
    
    # Check for photos using GPU
    horizontal_profile = torch.sum(edge_tensor, dim=1) / width
    vertical_profile = torch.sum(edge_tensor, dim=0) / height
    h_var = float(torch.var(horizontal_profile))
    v_var = float(torch.var(vertical_profile))
    
    is_photo = (
        ("photo" in str(file_path).lower() if file_path else False) or
        (
            edge_density > 0.12 and
            (h_var > 1000 or v_var > 1000) and
            text_density < 0.5
        )
    )
    
    return {
        "is_double_page": bool(is_double_page),
        "is_label": bool(is_likely_first),
        "is_photo": bool(is_photo),
        "edge_density": float(edge_density),
        "text_density": float(text_density),
        "content_balance": float(content_balance),
        "vertical_pattern": float(vertical_pattern),
        "pattern_peaks": int(pattern_peaks)
    }

def detect_split_point(image: Image.Image, file_path: Path = None) -> Tuple[bool, Optional[int], float, dict]:
    """Detect if and where an image should be split."""
    width, height = image.size
    aspect_ratio = width / height
    
    # Don't split if image is portrait or too small
    if aspect_ratio < 1.2 or width < 1000:
        return False, None, 0.0, {"aspect_ratio": float(aspect_ratio)}
    
    # Convert to grayscale numpy array and then to tensor
    img_array = np.array(image.convert("L"))
    img_tensor = to_tensor(img_array)
    
    # Detect document type
    doc_type = detect_document_type(img_array, width, height, aspect_ratio, file_path)
    
    # Never split labels, photos, or first pages
    if doc_type["is_label"] or doc_type["is_photo"]:
        return False, None, 0.0, doc_type
    
    # Handle double pages
    if doc_type["is_double_page"]:
        # Find optimal split point near center using GPU
        center_x = width // 2
        search_range = 200
        split_x = center_x
        min_sum = float('inf')
        
        # Process in chunks to avoid memory issues
        chunk_size = 50
        for start_x in range(center_x - search_range, center_x + search_range, chunk_size):
            end_x = min(start_x + chunk_size, center_x + search_range)
            if start_x >= 0 and end_x <= width:
                chunk = img_tensor[:, start_x:end_x]
                vertical_sums = torch.sum(chunk, dim=0)
                min_val, min_idx = torch.min(vertical_sums, dim=0)
                if min_val < min_sum:
                    min_sum = float(min_val)
                    split_x = start_x + int(min_idx)
        
        avg_darkness = min_sum / height
        return True, split_x, avg_darkness, doc_type
    
    # For other images, analyze middle region
    threshold_ratio = 0.20
    mid_region_start = int(width * (0.5 - threshold_ratio))
    mid_region_end = int(width * (0.5 + threshold_ratio))
    
    # Look for darkest vertical line using GPU
    mid_region = img_tensor[:, mid_region_start:mid_region_end]
    vertical_sums = torch.sum(mid_region, dim=0)
    min_val, min_idx = torch.min(vertical_sums, dim=0)
    split_x = mid_region_start + int(min_idx)
    avg_darkness = float(min_val) / height
    
    # Compare surrounding slices using GPU
    slice_values = []
    for offset in range(-3, 4):
        x_check = split_x + offset
        if 0 <= x_check < width:
            slice_sum = float(torch.sum(img_tensor[:, x_check])) / height
            slice_values.append(slice_sum)
    avg_slice_value = float(torch.tensor(slice_values).mean()) if slice_values else float('inf')
    
    # Determine if split is needed
    darkness_diff = avg_slice_value - avg_darkness
    should_split = (avg_darkness < 180) and (darkness_diff > 15)
    
    # For very wide images, be more aggressive
    if aspect_ratio > 1.65 and not should_split:
        should_split = darkness_diff > 5
    
    return should_split, split_x, avg_darkness, {
        **doc_type,
        "aspect_ratio": float(aspect_ratio),
        "mid_region_start": int(mid_region_start),
        "mid_region_end": int(mid_region_end),
        "avg_darkness": float(avg_darkness),
        "split_point": int(split_x) if split_x is not None else None,
        "should_split": bool(should_split),
        "darkness_diff": float(darkness_diff)
    }

def split_image(image: Image.Image, file_path: Path = None) -> Tuple[List[Image.Image], dict]:
    """Split an image into left and right pages if needed."""
    should_split, split_point, avg_darkness, debug_info = detect_split_point(image, file_path)
    
    if not should_split:
        return [image], debug_info
    
    # Split into left and right pages
    width, height = image.size
    left_page = image.crop((0, 0, split_point, height))
    right_page = image.crop((split_point, 0, width, height))
    
    return [left_page, right_page], debug_info

def process_image(
    image_path: Path,
    output_dir: Path,
    batch_size: int = 10,
    max_workers: Optional[int] = None
) -> bool:
    """Process a single image."""
    try:
        # Create output path
        rel_path = get_relative_path(image_path)
        output_path = output_dir / rel_path
        
        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Skip if output exists
        if output_path.exists():
            return True
        
        # Load and process image
        image = Image.open(image_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Split image if needed
        parts, debug_info = split_image(image, file_path=image_path)
        
        # Save parts
        for i, part in enumerate(parts):
            if len(parts) > 1:
                part_name = f"{output_path.stem}_part_{i+1}.jpg"
            else:
                part_name = f"{output_path.stem}.jpg"
            
            part_path = output_path.parent / part_name
            save_image_with_metadata(
                part,
                part_path,
                original_image=image,
                quality=95
            )
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}")
        return False

def main(
    input_dir: Path,
    output_dir: Path,
    batch_size: int = 10,
    max_workers: Optional[int] = None
) -> None:
    """Main function to process all images in directory."""
    # Get worker ID for logging
    worker_id = os.environ.get('WORKER_ID', '0')
    
    # Create progress trackers (will be None if child/worker process)
    workflow_progress, step_progress = create_progress_tracker(
        total_files=len(list(input_dir.glob("**/*.jpg"))),
        step_name="Splitting Documents",
        show_workflow=True,
        total_steps=1
    )
    
    # Show worker status
    logger.info(f"Starting split process with {max_workers or mp.cpu_count()} workers")
    logger.info("Each worker will show its current task in the logs")
    
    # Process images with or without progress tracking
    if workflow_progress and step_progress:
    with workflow_progress, step_progress:
        workflow_progress.start_step("Splitting Documents")
            results = process_directory(
                input_dir,
                lambda p: process_image(p, output_dir, batch_size, max_workers),
                file_pattern="**/*.jpg",
                batch_size=batch_size,
                max_workers=max_workers,
                progress=step_progress
            )
    else:
        # No progress tracking, just logging
        logger.info(f"Worker {worker_id} started")
        results = process_directory(
            input_dir,
            lambda p: process_image(p, output_dir, batch_size, max_workers),
            file_pattern="**/*.jpg",
            batch_size=batch_size,
            max_workers=max_workers,
            progress=None
        )
        logger.info(f"Worker {worker_id} finished")
        
        # Log results
        successful = sum(1 for r in results.values() if r)
        total = len(results)
        logger.info(f"Successfully split {successful}/{total} images")

def split(
    manifest_file: Path = typer.Argument(..., help="Manifest file"),
    project_folder: Path = typer.Argument(..., help="Project folder")
):
    """Split cropped images into individual pages.
    
    Args:
        manifest_file: Path to the manifest file
        project_folder: Path to the project folder
    """
    # Set up paths based on project structure
    input_dir = project_folder / "assets" / "crops"
    output_dir = project_folder / "assets" / "splits"
    
    # Create output folder if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Rest of the function remains the same
    main(input_dir, output_dir)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Split document images into individual pages")
    parser.add_argument("input_dir", type=Path, help="Input directory containing images")
    parser.add_argument("output_dir", type=Path, help="Output directory for split images")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for parallel processing")
    parser.add_argument("--workers", type=int, help="Number of worker processes")
    
    args = parser.parse_args()
    
    main(
        args.input_dir,
        args.output_dir,
        args.batch_size,
        args.workers
    )