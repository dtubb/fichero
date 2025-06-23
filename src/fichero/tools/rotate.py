import typer
from PIL import Image
from pathlib import Path
import numpy as np
import cv2

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # When run as standalone script (relative imports work)
    from utils.batch import BatchProcessor
    from utils.processor import process_file
    from utils.segment_handler import SegmentHandler
    from utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from utils.tool_logger import get_tool_logger

tool_logger = get_tool_logger('rotate')

def hough_line_rotate(image: Image.Image, blur_kernel=(5, 5), canny_threshold1=50, canny_threshold2=150) -> tuple[Image.Image, dict]:
    """
    Rotate image based on Hough Line Transform.
    Returns (rotated_image, debug_info)
    """
    img_array = np.array(image)
    img_gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    img_blurred = cv2.GaussianBlur(img_gray, blur_kernel, 0)
    edges = cv2.Canny(img_blurred, canny_threshold1, canny_threshold2)
    
    debug_info = {
        "found_lines": False,
        "rotation_angle": 0,
        "num_lines": 0,
        "edge_points": int(np.sum(edges > 0))
    }
    
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)
    if lines is not None:
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -2 <= angle <= 2:  # Ensure the angle is within a small range
                angles.append(angle)
        
        debug_info["num_lines"] = len(lines)
        
        if angles:
            median_angle = np.median(angles)
            debug_info["found_lines"] = True
            debug_info["rotation_angle"] = float(median_angle)
            debug_info["num_valid_angles"] = len(angles)
            
            center = (img_array.shape[1] // 2, img_array.shape[0] // 2)
            M_rotate = cv2.getRotationMatrix2D(center, median_angle, 1.0)
            rotated = cv2.warpAffine(img_array, M_rotate, (img_array.shape[1], img_array.shape[0]), borderValue=(255, 255, 255))
            
            return Image.fromarray(rotated), debug_info
    
    return image, debug_info

def process_image(file_path: Path, out_path: Path, output_format: str = 'jpg') -> dict:
    """Process a single image file for rotation"""
    # Use SegmentHandler for path handling
    rel_path = SegmentHandler.get_relative_path(file_path)
    
    try:
        # Load image using the format utility
        image, metadata = load_image(file_path)
    except Exception as e:
        tool_logger.error(f"Failed to load image {file_path.name}: {e}")
        return {"success": False, "error": f"Failed to load image: {e}"}
    
    # Rotate image and get debug info
    rotated, debug_info = hough_line_rotate(image)
    
    # Ensure output directory exists
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save the result using the format utility with the specified output format
    final_path, actual_format = save_image(rotated, out_path, output_format)
    
    details = {
        "original_size": list(image.size),
        "rotated_size": list(rotated.size),
        "debug": debug_info,
        "output_format": actual_format,
        "input_metadata": metadata
    }
    
    # Get the relative path for the output file
    output_rel_path = SegmentHandler.get_relative_path(final_path)
    
    return {
        "outputs": [str(output_rel_path)],
        "source": str(rel_path),
        "details": details
    }

def process_document(file_path: str, output_folder: Path, output_format: str = 'jpg') -> dict:
    """Process a single document file"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        return process_image(Path(f), o, output_format)
    
    # Get supported extensions and create file_types dict
    file_types = {ext: process_fn for ext in get_supported_extensions_list()}
    
    return process_file(
        file_path=str(file_path),
        output_folder=output_folder,
        process_fn=process_fn,
        file_types=file_types
    )

def rotate_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    output_format: str = "jpg",
    **kwargs
) -> dict:
    """
    Rotate split document pages - importable function
    
    Args:
        source_folder: Input splits folder
        source_manifest: Input splits manifest file
        output_folder: Output folder for rotated images
        output_format: Output format (jpg, png, jxl)
        
    Returns:
        Processing statistics dictionary
    """
    processor = BatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="rotate",
        base_folder=source_folder,
        processor_fn=lambda f, o: process_document(f, o, output_format)
    )
    return processor.process()

def rotate(
    splits_folder: Path = typer.Argument(..., help="Input splits folder"),
    splits_manifest: Path = typer.Argument(..., help="Input splits manifest file"), 
    rotated_folder: Path = typer.Argument(..., help="Output folder for rotated images"),
    output_format: str = typer.Option("jpg", "--format", "-f", 
                                     help="Output format: png, jxl, or jpg",
                                     callback=validate_format)
):
    """Rotate split document pages"""
    return rotate_batch(splits_folder, splits_manifest, rotated_folder, output_format)

if __name__ == "__main__":
    typer.run(rotate)