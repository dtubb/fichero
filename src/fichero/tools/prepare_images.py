import typer
from PIL import Image, ImageOps
from pathlib import Path
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import os
import json
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from dataclasses import dataclass

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
tool_logger = get_tool_logger('prepare_images')

@dataclass
class PrepareInfo:
    """Standardized image preparation information for JSONL output"""
    original_size: list[int]  # [width, height]
    prepared_size: list[int]  # [width, height]
    rotation_applied: dict  # Rotation information
    compression_quality: int
    output_format: str
    original_format: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSONL output"""
        return {
            "original_size": self.original_size,
            "prepared_size": self.prepared_size,
            "rotation_applied": self.rotation_applied,
            "compression_quality": self.compression_quality,
            "output_format": self.output_format,
            "original_format": self.original_format
        }

def create_prepare_info(
    original_size: list[int],
    prepared_size: list[int],
    rotation_applied: dict,
    compression_quality: int,
    output_format: str,
    original_format: str
) -> PrepareInfo:
    """Create standardized prepare info"""
    return PrepareInfo(
        original_size=original_size,
        prepared_size=prepared_size,
        rotation_applied=rotation_applied,
        compression_quality=compression_quality,
        output_format=output_format,
        original_format=original_format
    )

def apply_exif_rotation(image: Image.Image) -> tuple[Image.Image, dict]:
    """
    Apply EXIF rotation to image using PIL's built-in function.
    Based on crop.py implementation.
    """
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

def process_image(
    file_path: Path,
    out_path: Path,
    output_format: str = 'jpg',
    compression_quality: int = 85
) -> dict:
    """
    Process a single image file for preparation (EXIF rotation and compression).

    Handles multi-page documents (PDFs) by creating separate output files for each page:
    - Single-page: document.jpg
    - Multi-page: document_page_001.jpg, document_page_002.jpg, etc.

    Based on crop.py and split.py patterns for multi-page handling.
    """
    try:
        # Get relative path for logging
        rel_path = SegmentHandler.get_relative_path(file_path)
        tool_logger.info(f"Processing {rel_path}")

        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")

        # Load image(s) using the format utility
        # NOTE: For PDFs, this returns a list of images (one per page)
        image_or_images, metadata = load_image(file_path)
        original_format = file_path.suffix.lower()

        # Normalize to list for uniform processing
        is_multipage = isinstance(image_or_images, list)
        images = image_or_images if is_multipage else [image_or_images]

        tool_logger.info(f"Loaded {len(images)} page(s) from {rel_path}")

        # Process each page
        outputs = []
        page_details = []

        for page_num, image in enumerate(images, start=1):
            # Get original size before rotation
            original_size = list(image.size)

            # Apply EXIF rotation
            image, rotation_details = apply_exif_rotation(image)
            prepared_size = list(image.size)

            tool_logger.info(f"Page {page_num}/{len(images)}: {original_size} -> {prepared_size}")

            # Create output filename
            if is_multipage:
                # Multi-page: document_page_001.jpg, document_page_002.jpg
                page_suffix = f"_page_{page_num:03d}"
                output_name = f"{rel_path.stem}{page_suffix}.{output_format}"
            else:
                # Single-page: document.jpg
                output_name = f"{rel_path.stem}.{output_format}"

            output_path = out_path.parent / output_name
            ensure_dirs(output_path)

            # Save the result using the format utility with compression
            if output_format.lower() == 'jpg' or output_format.lower() == 'jpeg':
                final_path, actual_format = save_image(image, output_path, output_format, quality=compression_quality)
            else:
                final_path, actual_format = save_image(image, output_path, output_format)

            # Get the relative path for the output file
            output_rel_path = SegmentHandler.get_relative_path(final_path)
            outputs.append(str(output_rel_path))

            # Track details for this page
            page_details.append({
                "page": page_num,
                "original_size": original_size,
                "prepared_size": prepared_size,
                "rotation_applied": rotation_details
            })

        # Create overall prepare info
        prepare_info = {
            "original_format": original_format,
            "output_format": output_format if not is_multipage else actual_format,
            "compression_quality": compression_quality,
            "total_pages": len(images),
            "is_multipage": is_multipage,
            "pages": page_details
        }

        # Add PDF-specific metadata if available
        if "pdf_info" in metadata:
            prepare_info["pdf_metadata"] = metadata["pdf_info"]

        if is_multipage:
            tool_logger.info(f"✅ Created {len(outputs)} output files from {len(images)} pages")
        else:
            tool_logger.info(f"✅ Created single output file")

        return {
            "outputs": outputs,
            "source": str(rel_path),
            "details": prepare_info
        }

    except Exception as e:
        tool_logger.error(f"Error processing {file_path.name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

def process_document(
    file_path: str, 
    output_folder: Path, 
    output_format: str = 'jpg',
    compression_quality: int = 85
) -> dict:
    """Process a single document file"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        return process_image(Path(f), o, output_format, compression_quality)
    
    # Get supported extensions and create file_types dict
    file_types = {ext: process_fn for ext in get_supported_extensions_list()}
    
    return process_file(
        file_path=str(file_path),
        output_folder=output_folder,
        process_fn=process_fn,
        file_types=file_types
    )

# Importable batch function - NO CLI dependencies
def prepare_images_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    output_format: str = "jpg",
    compression_quality: int = 85,
    parallel_workers: int = 1,
    **kwargs
) -> dict:
    """
    Prepare images (apply EXIF rotation and compress them) - importable function
    
    Returns:
        Processing statistics dictionary
    """
    tool_logger.info(f"Starting image preparation with format: {output_format}, quality: {compression_quality}")
    
    # Create parallel-enabled batch processor using shared utility
    ParallelPrepareProcessor = create_parallel_batch_processor("prepare_images", BatchProcessor, process_image)
    
    processor = ParallelPrepareProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="prepare_images",
        base_folder=source_folder,
        processor_fn=lambda f, o: process_document(
            f, o, output_format, compression_quality
        ),  # Fallback for sequential
        output_format=output_format,
        parallel_workers=parallel_workers,
        add_documents_prefix=kwargs.get('add_documents_prefix', False)
    )
    
    return processor.process()

# CLI wrapper for typer
def prepare_images(
    source_folder: Path = typer.Argument(..., help="Source folder containing documents"),
    source_manifest: Path = typer.Argument(..., help="Manifest file"),
    output_folder: Path = typer.Argument(..., help="Output folder for prepared images"),
    output_format: str = typer.Option("jpg", "--format", "-f", 
                                     help="Output format: png, jxl, or jpg",
                                     callback=validate_format),
    compression_quality: int = typer.Option(85, "--quality", "-q",
                                           help="Compression quality (1-100, JPEG only)",
                                           min=1, max=100),
    parallel_workers: int = typer.Option(1, "--workers", "-w",
                                        help="Number of parallel workers")
):
    """Prepare images (apply EXIF rotation and compress them)"""
    return prepare_images_batch(
        source_folder, source_manifest, output_folder, output_format,
        compression_quality=compression_quality,
        parallel_workers=parallel_workers
    )

if __name__ == "__main__":
    typer.run(prepare_images) 