"""
Image Splitting Processor for Document Digitization

This script processes scanned document images, with intelligent detection of:
1. Notebooks and spiral-bound documents (detected by vertical patterns and content distribution)
2. Single-page documents (labels, covers, envelopes)
3. Photo albums and photographic content
4. Double-page book spreads

Key Features:
- Multi-stage document type detection
- Smart split point detection
- Comprehensive content analysis
- GPU Acceleration with CUDA and Apple Silicon (MPS) support
- Multi-worker processing with progress tracking
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
import torch.nn.functional as F
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import json
import yaml
import time
import platform
import multiprocessing
import subprocess
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.live import Live

from scripts.utils.step_manifest import StepManifestManager
from scripts.utils.workflow_progress import create_progress_tracker
from scripts.utils.worker_manager import (
    run_worker_process,
    run_main_process,
    get_best_device,
    get_worker_device,
    clear_gpu_memory,
)
from scripts.utils.file_manager import FileManager
from scripts.utils.logging_utils import rich_log, should_show_progress

# Initialize global variables
device = None
edge_detection_kernel = None
gaussian_kernel = None
file_manager = None

app = typer.Typer()

def initialize_kernels():
    """Initialize kernels for edge detection on GPU."""
    global edge_detection_kernel, gaussian_kernel, device
    
    if device is None:
        device = get_best_device()
    
    # Sobel kernels for edge detection
    sobel_x = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=torch.float32, device=device)
    sobel_y = torch.tensor([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=torch.float32, device=device)
    edge_detection_kernel = torch.stack([sobel_x, sobel_y]).unsqueeze(1)
    
    # Gaussian kernel for smoothing
    gaussian = torch.tensor([
        [1, 4, 6, 4, 1],
        [4, 16, 24, 16, 4],
        [6, 24, 36, 24, 6],
        [4, 16, 24, 16, 4],
        [1, 4, 6, 4, 1]
    ], dtype=torch.float32, device=device) / 256
    gaussian_kernel = gaussian.unsqueeze(0).unsqueeze(0)

def edge_detection_gpu(img_tensor: torch.Tensor) -> torch.Tensor:
    """Perform edge detection using GPU tensors."""
    global edge_detection_kernel, gaussian_kernel
    
    if edge_detection_kernel is None:
        initialize_kernels()
    
    # Ensure input is float and normalized
    if img_tensor.dtype != torch.float32:
        img_tensor = img_tensor.float()
    if img_tensor.max() > 1.0:
        img_tensor = img_tensor / 255.0
    
    # Add batch and channel dimensions if needed
    if img_tensor.dim() == 2:
        img_tensor = img_tensor.unsqueeze(0).unsqueeze(0)
    elif img_tensor.dim() == 3:
        img_tensor = img_tensor.unsqueeze(0)
    
    # Apply Gaussian blur
    blurred = F.conv2d(img_tensor, gaussian_kernel, padding=2)
    
    # Apply Sobel filters
    edges = F.conv2d(blurred, edge_detection_kernel, padding=1)
    
    # Calculate magnitude
    magnitude = torch.sqrt(edges[:, 0] ** 2 + edges[:, 1] ** 2)
    
    # Threshold
    threshold = 0.1
    edges_binary = (magnitude > threshold).float()
    
    return edges_binary.squeeze()

def to_tensor(img_array: np.ndarray) -> torch.Tensor:
    """Convert numpy array to PyTorch tensor and move to GPU."""
    global device
    if device is None:
        device = get_best_device()
    return torch.from_numpy(img_array).float().to(device)

def to_numpy(tensor: torch.Tensor) -> np.ndarray:
    """Convert PyTorch tensor to numpy array."""
    return tensor.cpu().numpy()

def process_batch(images: List[Image.Image], file_paths: List[Path] = None) -> List[Tuple[List[Image.Image], dict]]:
    """Process a batch of images on GPU."""
    global device
    
    if device is None:
        device = get_best_device()
    
    # Convert images to tensors
    tensors = []
    sizes = []
    for img in images:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img_array = np.array(img.convert('L'))  # Convert to grayscale
        tensor = to_tensor(img_array)
        tensors.append(tensor)
        sizes.append(img.size)
    
    # Stack tensors into a batch
    batch = torch.stack(tensors)
    
    # Process batch
    results = []
    for i, (tensor, (width, height)) in enumerate(zip(tensors, sizes)):
        file_path = file_paths[i] if file_paths else None
        aspect_ratio = width / height
        
        # Skip if image is portrait or too small
        if aspect_ratio < 1.2 or width < 1000:
            results.append(([images[i]], {"aspect_ratio": float(aspect_ratio)}))
            continue
        
        # Detect document type
        doc_type = detect_document_type(tensor, width, height, aspect_ratio, file_path)
        
        # Never split labels, photos, or first pages
        if doc_type["is_label"] or doc_type["is_photo"]:
            results.append(([images[i]], doc_type))
            continue
        
        # Find split point if needed
        if doc_type["is_double_page"]:
            split_point, avg_darkness = find_split_point_gpu(tensor, width)
            if split_point:
                # Split image
                left_page = images[i].crop((0, 0, split_point, height))
                right_page = images[i].crop((split_point, 0, width, height))
                results.append(([left_page, right_page], {
                    **doc_type,
                    "split_point": split_point,
                    "avg_darkness": float(avg_darkness)
                }))
                continue
        
        # If no split needed or split point not found
        results.append(([images[i]], doc_type))
    
    return results

def find_split_point_gpu(img_tensor: torch.Tensor, width: int) -> Tuple[Optional[int], float]:
    """Find optimal split point using GPU tensors."""
    center_x = width // 2
    search_range = 200
    
    # Get the center region
    start_x = max(0, center_x - search_range)
    end_x = min(width, center_x + search_range)
    center_region = img_tensor[:, start_x:end_x]
    
    # Calculate vertical sums
    vertical_sums = torch.sum(center_region, dim=0)
    
    # Find darkest line
    min_val, min_idx = torch.min(vertical_sums, dim=0)
    split_x = start_x + int(min_idx)
    avg_darkness = float(min_val) / img_tensor.shape[0]
    
    # Check surrounding area
    window = 5
    start_check = max(0, min_idx - window)
    end_check = min(vertical_sums.shape[0], min_idx + window + 1)
    surrounding_avg = torch.mean(vertical_sums[start_check:end_check])
    
    # Verify split point is significantly darker
    if min_val < surrounding_avg * 0.8:
        return split_x, avg_darkness
    return None, avg_darkness

def detect_document_type(img_tensor: torch.Tensor, width: int, height: int, aspect_ratio: float, file_path: Path = None) -> dict:
    """Detect document type using GPU tensors."""
    # Calculate edges using GPU
    edges = edge_detection_gpu(img_tensor)
    edge_density = float(torch.sum(edges) / (width * height))
    text_density = float(torch.mean(img_tensor < 200))

    # Calculate content distribution
    left_half = img_tensor[:, :width//2]
    right_half = img_tensor[:, width//2:]
    left_density = float(torch.mean(left_half < 200))
    right_density = float(torch.mean(right_half < 200))
    content_balance = float(torch.abs(left_density - right_density))
    
    # Check for binding pattern
    center_width = 100
    center_x = width // 2
    center_region = img_tensor[:, center_x-center_width:center_x+center_width]
    vertical_pattern = float(torch.std(torch.sum(center_region, dim=0)))
    
    # Calculate periodic pattern
    vertical_sums = torch.sum(center_region, dim=0)
    kernel = torch.ones(5, device=device) / 5
    smooth_sums = F.conv1d(
        vertical_sums.unsqueeze(0).unsqueeze(0),
        kernel.unsqueeze(0).unsqueeze(0),
        padding=2
    ).squeeze()
    
    # Find peaks
    pattern_peaks = int(torch.sum(
        (smooth_sums[1:-1] < smooth_sums[:-2]) & 
        (smooth_sums[1:-1] < smooth_sums[2:])
    ).item())
    
    # Detect double page
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
    is_likely_first = file_path and is_likely_label_from_name(file_path)
    
    # Check for photos
    horizontal_profile = torch.sum(edges, dim=1) / width
    vertical_profile = torch.sum(edges, dim=0) / height
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
        "pattern_peaks": int(pattern_peaks),
        "aspect_ratio": float(aspect_ratio)
    }

def process_document(file_path: str, output_folder: Path) -> dict:
    """Process a single document file."""
    global file_manager
    
    file_path = Path(file_path)
    output_folder = Path(output_folder)
    
    # Skip directories
    if file_path.is_dir():
        rich_log("info", f"Skipping directory: {file_path}")
        return {"success": True, "details": {"skipped": "directory"}}
    
    try:
        # Ensure output folder exists
        file_manager.ensure_output_path(output_folder)
        
        # Process image
        image = Image.open(file_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Process single image as batch
        results = process_batch([image], [file_path])[0]
        parts, debug_info = results
        
        # Clear GPU memory after processing
        clear_gpu_memory()
        
        outputs = []
        for i, part in enumerate(parts):
            # Create output path using file manager
            output_path = file_manager.get_output_path(
                input_path=file_path,
                output_folder=output_folder,
                suffix='.jpg',
                part_number=i+1 if len(parts) > 1 else None
            )
            
            # Save image
            part.save(output_path, 'JPEG', quality=95)
            
            # Get relative path from project root
            rel_output = file_manager.get_relative_path(output_path)
            outputs.append(str(rel_output))
            
            rich_log("info", f"Saved output to: {output_path}")
            rich_log("info", f"Relative output path: {rel_output}")
        
        return {
            "success": True,
            "outputs": outputs,
            "details": debug_info
        }
        
    except Exception as e:
        rich_log("error", f"Error processing {file_path}: {e}")
        return {
            "success": False,
            "error": str(e),
            "outputs": [],
            "details": {"error": str(e)}
        }
    finally:
        # Always clear GPU memory after processing
        clear_gpu_memory()

def init_worker(worker_id: int):
    """Initialize worker-specific resources."""
    global device, file_manager
    device = get_best_device()
    if worker_id is not None:
        device = get_worker_device(worker_id, device)
    initialize_kernels()
    file_manager = FileManager()

@app.command()
def split(
    manifest_file: Path = typer.Argument(..., help="Manifest file"),
    project_folder: Path = typer.Argument(..., help="Project folder"),
    batch_size: int = typer.Option(10, help="Batch size for parallel processing"),
    max_workers: Optional[int] = typer.Option(None, help="Number of worker processes"),
    debug: bool = typer.Option(False, help="Enable debug logging")
):
    """Split cropped images into individual pages."""
    # Initialize file manager
    global file_manager
    file_manager = FileManager(project_folder)
    
    # Check if this is a worker process
    if os.environ.get('FICHERO_WORKER') == '1':
        run_worker_process(
            manifest_file=manifest_file,
            project_folder=project_folder,
            step="split",
            process_func=process_document,
            source_prefix="crops",
            output_folder=file_manager.get_asset_path('splits')
            )
    else:
        # This is the main process
        run_main_process(
            manifest_file=manifest_file,
            project_folder=project_folder,
            step="split",
            max_workers=max_workers,
            debug=debug,
            source_folder=file_manager.get_asset_path('crops'),
            output_folder=file_manager.get_asset_path('splits')
        )

if __name__ == "__main__":
    app()