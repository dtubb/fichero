"""
Image format handling utilities for document processing.
Provides consistent format handling across all processing scripts.
"""

from pathlib import Path
from PIL import Image
import subprocess
import shutil
from typing import Literal, Optional, Tuple, Union, Dict, List
# import rawpy  # REMOVED: Not needed for document processing
# import pillow_heif  # REMOVED: Does not work with Briefcase packaging
import logging
import typer

logger = logging.getLogger(__name__)

# Supported input formats (RAW formats disabled for document processing)
InputFormat = Literal['jpg', 'jpeg', 'png', 'tif', 'tiff', 'heic', 'jxl']  # removed: 'raw', 'cr2', 'nef', 'arw'
# Supported output formats
OutputFormat = Literal['jpg', 'png', 'jxl']
# Type alias for backward compatibility
ImageFormat = OutputFormat

# Define supported extensions as constants
SUPPORTED_EXTENSIONS = {
    '.jpg': 'process_fn',
    '.jpeg': 'process_fn',
    '.png': 'process_fn',
    '.tif': 'process_fn',
    '.tiff': 'process_fn',
    '.heic': 'process_fn',  # requires heif-convert system tool
    '.jxl': 'process_fn',
    # Removed RAW formats for document processing:
    # '.raw': 'process_fn',
    # '.cr2': 'process_fn',
    # '.nef': 'process_fn',
    # '.arw': 'process_fn'
}

SUPPORTED_EXTENSIONS_LIST = list(SUPPORTED_EXTENSIONS.keys())

def get_supported_extensions() -> Dict[str, str]:
    """
    Get dictionary of supported file extensions and their corresponding process function.
    Returns a dict mapping file extensions to process function names.
    """
    return SUPPORTED_EXTENSIONS

def get_supported_extensions_list() -> List[str]:
    """
    Get list of supported file extensions.
    Returns a list of file extensions including the dot.
    """
    return SUPPORTED_EXTENSIONS_LIST

def check_cjxl_installed() -> bool:
    """Check if cjxl (JPEG XL encoder) is installed."""
    return shutil.which('cjxl') is not None

def check_djxl_installed() -> bool:
    """Check if djxl (JPEG XL decoder) is installed."""
    return shutil.which('djxl') is not None

def check_heif_installed() -> bool:
    """Check if heif-convert is installed."""
    return shutil.which('heif-convert') is not None

def load_image(file_path: Union[str, Path]) -> Tuple[Image.Image, dict]:
    """
    Load an image file, handling various formats including HEIC and JXL.
    RAW formats are no longer supported (disabled for document processing).
    Returns (image, metadata) where metadata contains format info and any errors.
    """
    file_path = Path(file_path)
    metadata = {
        "original_format": file_path.suffix.lower()[1:],
        "errors": []
    }
    
    try:
        # Handle RAW formats - COMMENTED OUT: Not needed for document processing
        if file_path.suffix.lower() in ['.raw', '.cr2', '.nef', '.arw']:
            metadata["errors"].append("RAW format support has been disabled for document processing")
            raise ValueError("RAW format support has been disabled for document processing")
            # try:
            #     with rawpy.imread(str(file_path)) as raw:
            #         rgb = raw.postprocess(use_camera_wb=True, half_size=False, 
            #                             no_auto_bright=False, output_bps=8)
            #         image = Image.fromarray(rgb)
            #         metadata["raw_info"] = {
            #             "camera_make": raw.metadata.get('make', ''),
            #             "camera_model": raw.metadata.get('model', ''),
            #             "iso": raw.metadata.get('iso', 0),
            #             "exposure_time": raw.metadata.get('exposure_time', 0)
            #         }
            # except Exception as e:
            #     metadata["errors"].append(f"RAW processing failed: {str(e)}")
            #     # Fall back to PIL
            #     image = Image.open(file_path)
        
        # Handle HEIC format - PARTIALLY DISABLED: pillow_heif removed
        elif file_path.suffix.lower() == '.heic':
            try:
                # First try using heif-convert system tool
                if check_heif_installed():
                    temp_png = file_path.with_suffix('.temp.png')
                    subprocess.run(['heif-convert', str(file_path), str(temp_png)], 
                                capture_output=True, check=True)
                    image = Image.open(temp_png)
                    temp_png.unlink()
                else:
                    # Fallback to pillow_heif if system tool not available - DISABLED
                    metadata["errors"].append("HEIC support requires heif-convert system tool (pillow_heif removed for Briefcase compatibility)")
                    raise ValueError("HEIC support requires heif-convert system tool")
                    # try:
                    #     heif_file = pillow_heif.read_heif(file_path)
                    #     image = Image.frombytes(
                    #         heif_file.mode, 
                    #         heif_file.size, 
                    #         heif_file.data,
                    #         "raw",
                    #     )
                    #     if image.mode == 'RGBA':
                    #         image = image.convert('RGB')
                    # except Exception as e:
                    #     metadata["errors"].append(f"HEIC processing failed: {str(e)}")
                    #     raise
            except Exception as e:
                metadata["errors"].append(f"HEIC processing failed: {str(e)}")
                raise
        
        # Handle JXL format
        elif file_path.suffix.lower() == '.jxl':
            if check_djxl_installed():
                try:
                    temp_png = file_path.with_suffix('.temp.png')
                    subprocess.run(['djxl', str(file_path), str(temp_png)], 
                                capture_output=True, check=True)
                    image = Image.open(temp_png)
                    temp_png.unlink()
                except Exception as e:
                    metadata["errors"].append(f"JXL processing failed: {str(e)}")
                    # Try PIL as fallback
                    image = Image.open(file_path)
            else:
                metadata["errors"].append("djxl not installed, using PIL fallback")
                image = Image.open(file_path)
        
        # Handle standard formats with PIL
        else:
            image = Image.open(file_path)
        
        # Ensure RGB mode
        if image.mode not in ['RGB', 'RGBA']:
            image = image.convert('RGB')
            
        return image, metadata
        
    except Exception as e:
        metadata["errors"].append(f"Image loading failed: {str(e)}")
        raise

def save_as_jxl(image: Image.Image, output_path: Path, effort: int = 7) -> bool:
    """
    Save image as JPEG XL format using cjxl.
    Uses high-quality archival settings optimized for document images.
    Returns True if successful, False otherwise.
    """
    try:
        # Save as temporary PNG first (cjxl works best with PNG input)
        temp_png = output_path.with_suffix('.temp.png')
        logger.info(f"Saving temporary PNG to {temp_png}")
        image.save(temp_png, "PNG", optimize=True, compress_level=9)
        
        # Verify temp PNG exists and has content
        if not temp_png.exists():
            logger.error("Temporary PNG file was not created")
            return False
        if temp_png.stat().st_size == 0:
            logger.error("Temporary PNG file is empty")
            return False
            
        # Convert to JXL using archival settings
        # -d 0.5: Visually lossless, good for archival
        # -e 7: Balanced encoding effort
        # -m 0: Use varDCT mode (better for photographs)
        # --num_threads 0: Use all available threads
        cmd = [
            'cjxl',
            str(temp_png),
            str(output_path),
            '-d', '0.5',  # Visually lossless, good for archival
            '-e', str(effort),  # Encoding effort (1-10)
            '-m', '0',  # Use varDCT mode (better for photographs)
            '--num_threads', '0'  # Use all available threads
        ]
        logger.info(f"Running cjxl command: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True)
        
        # Log full output for debugging
        if process.stdout:
            logger.info(f"cjxl stdout: {process.stdout}")
        if process.stderr:
            logger.error(f"cjxl stderr: {process.stderr}")
        
        # Clean up temp PNG
        if temp_png.exists():
            temp_png.unlink()
        
        if process.returncode != 0:
            logger.error(f"JXL conversion failed with return code {process.returncode}")
            return False
            
        # Verify the output file exists and has content
        if not output_path.exists():
            logger.error(f"JXL file was not created at {output_path}")
            return False
        if output_path.stat().st_size == 0:
            logger.error("JXL file was created but is empty")
            return False
            
        logger.info(f"Successfully saved JXL to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save as JXL: {str(e)}")
        if temp_png.exists():
            temp_png.unlink()
        return False

def save_image(image: Image.Image, output_path: Path, format: OutputFormat = 'jpg') -> Tuple[Path, OutputFormat]:
    """
    Save image in the specified format with appropriate settings.
    Returns (final_output_path, actual_format_used)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert RGBA to RGB with white background if needed
    if image.mode == 'RGBA':
        white_bg = Image.new('RGB', image.size, 'white')
        white_bg.paste(image, mask=image.split()[3])
        image = white_bg
    
    if format == 'jxl':
        if check_cjxl_installed():
            out_path = output_path.with_suffix('.jxl')
            if save_as_jxl(image, out_path):
                return out_path, 'jxl'
            # Fail if JXL conversion fails
            raise RuntimeError("Failed to convert to JXL format")
        else:
            raise RuntimeError("cjxl is not installed")
    
    if format == 'png':
        out_path = output_path.with_suffix('.png')
        # Use optimal PNG settings for archival quality
        # optimize=True: Use zlib compression
        # compress_level=9: Maximum compression
        # pnginfo: Preserve any existing metadata
        # quantize=True: Reduce color palette if possible
        # colors=256: Use 256 colors for better compression
        pnginfo = None
        if hasattr(image, 'info'):
            pnginfo = image.info.get('pnginfo')
        
        # Try to optimize the image for PNG
        if image.mode == 'RGB':
            # Convert to palette mode if possible (better compression)
            try:
                # First try to convert to palette mode
                image = image.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)
            except Exception:
                # If that fails, keep as RGB
                pass
        
        image.save(out_path, "PNG", 
                  optimize=True, 
                  compress_level=9,
                  pnginfo=pnginfo)
        return out_path, 'png'
    
    # Default to JPG
    out_path = output_path.with_suffix('.jpg')
    # Use high quality JPG settings
    # quality=95: Very high quality
    # optimize=True: Use Huffman optimization
    # subsampling=0: No chroma subsampling (better for text)
    image.save(out_path, "JPEG", quality=95, optimize=True, subsampling=0)
    return out_path, 'jpg'

def validate_format(format_str: str) -> str:
    """
    Validate the output format string.
    Returns the lowercase format if valid, raises BadParameter if invalid.
    """
    valid_formats = ["jpg", "png", "jxl"]
    if format_str.lower() not in valid_formats:
        raise typer.BadParameter(f"Format must be one of: {', '.join(valid_formats)}")
    return format_str.lower() 