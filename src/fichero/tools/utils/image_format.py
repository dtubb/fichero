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
import typer

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # When run as standalone script (relative imports work)
    from tool_logger import get_tool_logger

tool_logger = get_tool_logger('image_format')

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
                    with Image.open(temp_png) as img:
                        image = img.copy()
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
                    with Image.open(temp_png) as img:
                        image = img.copy()
                    temp_png.unlink()
                except Exception as e:
                    metadata["errors"].append(f"JXL processing failed: {str(e)}")
                    # Try PIL as fallback
                    with Image.open(file_path) as img:
                        image = img.copy()
            else:
                metadata["errors"].append("djxl not installed, using PIL fallback")
                with Image.open(file_path) as img:
                    image = img.copy()
        
        # Handle standard formats with PIL
        else:
            with Image.open(file_path) as img:
                # Load the image data completely into memory
                image = img.copy()
        
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
        tool_logger.info(f"Saving temporary PNG to {temp_png}")
        image.save(temp_png, "PNG", optimize=True, compress_level=9)
        
        # Verify temp PNG exists and has content
        if not temp_png.exists():
            tool_logger.error("Temporary PNG file was not created")
            return False
        if temp_png.stat().st_size == 0:
            tool_logger.error("Temporary PNG file is empty")
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
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Clean up temp file
        if temp_png.exists():
            temp_png.unlink()
        
        if result.returncode != 0:
            tool_logger.error(f"cjxl failed: {result.stderr}")
            return False
            
        return True
        
    except Exception as e:
        tool_logger.error(f"Error saving as JXL: {e}")
        # Clean up temp file on error
        temp_png = output_path.with_suffix('.temp.png')
        if temp_png.exists():
            temp_png.unlink()
        return False

def save_image(image: Image.Image, output_path: Path, format: OutputFormat = 'jpg', quality: int = 95) -> Tuple[Path, OutputFormat]:
    """
    Save image in the specified format with optimal settings for document processing.
    Returns (output_path, actual_format_used).
    
    Args:
        image: PIL Image to save
        output_path: Output file path
        format: Output format ('jpg', 'png', 'jxl')
        quality: JPEG quality (1-100, only used for JPEG format)
    """
    output_path = Path(output_path)
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if format == 'jxl':
            output_path = output_path.with_suffix('.jxl')
            # Use specialized JXL saving
            if save_as_jxl(image, output_path):
                return output_path, 'jxl'
            else:
                # Fallback to PNG if JXL fails
                tool_logger.warning(f"JXL save failed, falling back to PNG for {output_path}")
                output_path = output_path.with_suffix('.png')
                image.save(output_path, 'PNG', optimize=True, compress_level=9)
                return output_path, 'png'
        elif format == 'png':
            output_path = output_path.with_suffix('.png')
            image.save(output_path, 'PNG', optimize=True, compress_level=9)
            return output_path, 'png'
        elif format == 'jpg':
            output_path = output_path.with_suffix('.jpg')
            # Convert to RGB if needed for JPEG
            if image.mode in ['RGBA', 'LA', 'P']:
                # Create white background for transparent images
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            image.save(output_path, 'JPEG', quality=quality, optimize=True, progressive=True)
            return output_path, 'jpg'
        else:
            raise ValueError(f"Unsupported output format: {format}")
            
    except Exception as e:
        tool_logger.error(f"Error saving image {output_path}: {e}")
        raise

def validate_format(format_str: str) -> str:
    """
    Validate and normalize format string.
    Returns the normalized format string or raises ValueError.
    """
    format_str = format_str.lower().strip()
    
    # Handle common variations
    if format_str in ['jpg', 'jpeg', 'jpe']:
        return 'jpg'
    elif format_str in ['png']:
        return 'png'
    elif format_str in ['jxl', 'jpegxl']:
        return 'jxl'
    else:
        raise ValueError(f"Unsupported format: {format_str}") 