#!/usr/bin/env python3
import logging
import asyncio
from pathlib import Path
import typer
from PIL import Image
import io
from pdf2image import convert_from_path
import aiofiles
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import partial
import tempfile
import os
import psutil
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global process pool for CPU-intensive tasks
process_pool = ProcessPoolExecutor(max_workers=os.cpu_count() or 1)

def convert_pdf_to_images(pdf_path: Path, dpi: int = 300) -> list[Image.Image]:
    """Convert PDF to images using pdf2image."""
    try:
        # Create a temporary directory for pdf2image
        with tempfile.TemporaryDirectory() as temp_dir:
            # Convert PDF to images
            images = convert_from_path(
                pdf_path,
                dpi=dpi,
                output_folder=temp_dir,
                fmt='jpeg',
                thread_count=os.cpu_count() or 1,
                use_pdftocairo=True,
                grayscale=False
            )
            return images
    except Exception as e:
        logger.error(f"Error converting PDF {pdf_path}: {str(e)}")
        return []

def convert_image_to_jpg(input_path: Path, output_path: Path) -> bool:
    """Convert a single image to JPG format."""
    try:
        with Image.open(input_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save as JPG with maximum quality
            img.save(output_path, 'JPEG', quality=100)
            return True
    except Exception as e:
        logger.error(f"Error converting image {input_path}: {str(e)}")
        return False

async def convert_to_jpg(file_path: Path, output_path: Path, dpi: int = 300) -> bool:
    """Convert a file to JPG format asynchronously."""
    try:
        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle PDF files
        if file_path.suffix.lower() == '.pdf':
            # Convert PDF to images in process pool
            loop = asyncio.get_event_loop()
            images = await loop.run_in_executor(
                process_pool, 
                convert_pdf_to_images,
                file_path,
                dpi
            )
            
            if not images:
                logger.error(f"No images extracted from PDF: {file_path}")
                return False
            
            # Save each page as a separate JPG
            for i, image in enumerate(images):
                page_output_path = output_path.parent / f"{output_path.stem}_page{i+1}.jpg"
                image.save(page_output_path, 'JPEG', quality=100)
                logger.info(f"Converted PDF page {i+1} to {page_output_path}")
            
            # Delete original PDF after successful conversion
            try:
                file_path.unlink()
                logger.info(f"Deleted original PDF: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete original PDF {file_path}: {str(e)}")
            
            return True
            
        # Handle other image formats
        elif file_path.suffix.lower() in ['.png', '.tiff', '.tif', '.bmp', '.gif', '.webp']:
            # Convert image in process pool
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                process_pool,
                convert_image_to_jpg,
                file_path,
                output_path
            )
            
            if success:
                # Delete original file after successful conversion
                try:
                    file_path.unlink()
                    logger.info(f"Deleted original file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete original file {file_path}: {str(e)}")
                return True
            return False
            
        else:
            logger.warning(f"Unsupported file format: {file_path}")
            return False
            
    except Exception as e:
        logger.error(f"Error converting {file_path}: {str(e)}")
        return False

async def process_file(file_path: Path, input_folder: Path, output_folder: Path, dpi: int) -> None:
    """Process a single file asynchronously."""
    try:
        # Skip if already a JPG
        if file_path.suffix.lower() == '.jpg':
            return
            
        # Create relative path structure
        rel_path = file_path.relative_to(input_folder)
        output_path = output_folder / rel_path.with_suffix('.jpg')
        
        # Convert file
        success = await convert_to_jpg(file_path, output_path, dpi)
        if not success:
            logger.warning(f"Failed to convert {file_path}")
            
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")

async def monitor_performance():
    """Monitor CPU and memory usage."""
    process = psutil.Process()
    while True:
        cpu_percent = process.cpu_percent()
        memory_percent = process.memory_percent()
        logger.info(f"CPU Usage: {cpu_percent}%, Memory Usage: {memory_percent:.1f}%")
        await asyncio.sleep(5)  # Log every 5 seconds

async def process_folder(input_folder: str, output_folder: str, dpi: int = 300) -> None:
    """Process all files in the input folder asynchronously."""
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    
    # Create output folder if it doesn't exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Get all files
    files = [f for f in input_path.rglob('*') if f.is_file()]
    logger.info(f"Found {len(files)} files to process")
    
    # Start performance monitoring
    monitor_task = asyncio.create_task(monitor_performance())
    
    # Process files concurrently
    tasks = []
    for file_path in files:
        task = process_file(file_path, input_path, output_path, dpi)
        tasks.append(task)
    
    # Wait for all tasks to complete
    await asyncio.gather(*tasks)
    
    # Stop performance monitoring
    monitor_task.cancel()
    
    logger.info("Conversion complete")

def main(
    input_folder: str = typer.Argument(..., help="Input folder containing files to convert"),
    output_folder: str = typer.Argument(..., help="Output folder for converted JPG files"),
    dpi: int = typer.Option(300, help="DPI for PDF conversion")
):
    """Convert various file formats to JPG format."""
    try:
        asyncio.run(process_folder(input_folder, output_folder, dpi))
    finally:
        process_pool.shutdown()

if __name__ == "__main__":
    typer.run(main) 