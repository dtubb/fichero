import typer
from PIL import Image, ImageEnhance, ImageOps
from pathlib import Path
import numpy as np
import cv2

# Import utilities with fallback for standalone execution
try:
    # Try absolute imports first (when run from app context)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.parallel_batch_processor import create_parallel_batch_processor
except ImportError:
    # Fall back to relative imports (when run standalone)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.parallel_batch_processor import create_parallel_batch_processor

from typing import Literal
import pytesseract
from collections import Counter

tool_logger = get_tool_logger('enhance')



DocumentType = Literal['handwritten', 'typescript', 'mixed']
PaperType = Literal['lined', 'plain']
ContentType = Literal['text', 'diagram', 'mixed']

class DocumentAnalyzer:
    def analyze_image(self, img_array: np.ndarray) -> dict:
        """
        Simplified document analysis.
        Adds fallback morphological heuristic if OCR confidence is inconclusive.
        """
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Document type detection
        doc_type = self._detect_document_type(gray)
        
        # Background color (yellowing) analysis
        is_yellowed = self._detect_yellowing(img_array)
        
        return {
            "document_type": doc_type,
            "is_yellowed": is_yellowed
        }
    
    def _detect_document_type(self, gray: np.ndarray) -> str:
        """
        Detect document type using:
        1) OCR confidence (primary)
        2) Fallback morphological stroke-density heuristic if OCR is inconclusive
        """
        # Binarize for OCR
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Attempt OCR in a try/except block to handle Tesseract errors
        try:
            ocr_data = pytesseract.image_to_data(binary, output_type=pytesseract.Output.DICT)
            confidences = [conf for conf in ocr_data['conf'] if conf != -1]
        except UnicodeDecodeError as e:
            # Tesseract binary error output can't be decoded as UTF-8
            tool_logger.warning(f"Tesseract OCR not available or misconfigured in worker environment: {e}")
            tool_logger.info("Falling back to morphological analysis")
            return self._morphological_heuristic(binary)
        except pytesseract.TesseractError as e:
            # If OCR fails entirely, default to morphological fallback
            tool_logger.warning(f"Tesseract OCR failed: {e}")
            tool_logger.info("Falling back to morphological analysis")
            return self._morphological_heuristic(binary)
        except Exception as e:
            # Any other error with OCR
            tool_logger.warning(f"OCR failed during document type detection: {e}")
            tool_logger.info("Falling back to morphological analysis")
            return self._morphological_heuristic(binary)
        
        if not confidences:
            # If no recognized text, use fallback
            return self._morphological_heuristic(binary)
        
        # Use confidence threshold to determine type
        avg_confidence = sum(confidences) / len(confidences)
        
        if avg_confidence > 60:
            return 'typescript'
        else:
            return 'handwritten'
    
    def _morphological_heuristic(self, binary: np.ndarray) -> str:
        """
        Simple morphological stroke-density approach:
        - If there's a large amount of small connected strokes, assume handwriting
        - Otherwise, assume typescript
        """
        kernel = np.ones((3, 3), np.uint8)
        morph_grad = cv2.morphologyEx(binary, cv2.MORPH_GRADIENT, kernel)
        # Density of 'edges' or strokes
        non_zero = cv2.countNonZero(morph_grad)
        density = (non_zero / (morph_grad.shape[0] * morph_grad.shape[1])) * 100
        
        # Heuristic threshold for stroke density
        return 'handwritten' if density > 0.5 else 'typescript'
    
    def _detect_yellowing(self, img: np.ndarray) -> float:
        """
        Detect yellow cast in document (0 = no yellow cast, 1 = strong yellow cast).
        Consider an extended range and clamp final result to [0,1].
        """
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        _, _, b_channel = cv2.split(lab)
        b_mean = np.mean(b_channel)
        
        # Simple linear scale relative to neutral (128)
        # A slight tweak to the divisor to avoid over-reporting yellow
        raw_yellow = (b_mean - 128) / 30.0
        
        return max(0, min(1, raw_yellow))

class DocumentEnhancer:
    def enhance(self, img: np.ndarray, doc_type: str, is_yellowed: float) -> np.ndarray:
        """
        Core document enhancement logic with gentle color correction
        """
        # Convert to LAB for processing
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        
        # STEP 1: Enhance text contrast using CLAHE
        if doc_type == 'handwritten':
            clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
            l = clahe.apply(l)
            l = cv2.convertScaleAbs(l, alpha=1.1, beta=-5)
        else:
            clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(16, 16))
            l = clahe.apply(l)
        
        # STEP 2: Handle color cast carefully
        if is_yellowed > 0.1:
            # Gentler yellow reduction
            yellow_reduction = min(8, int(3 * is_yellowed))
            b = cv2.subtract(b, yellow_reduction)
            
            # Very subtle a-channel adjustment
            a = cv2.convertScaleAbs(a, alpha=0.98, beta=0)
        
        # Merge corrected channels
        enhanced_lab = cv2.merge([l, a, b])
        enhanced_rgb = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
        
        # STEP 3: Sharpen
        gaussian_blur = cv2.GaussianBlur(enhanced_rgb, (0, 0), 3)
        sharpened = cv2.addWeighted(enhanced_rgb, 1.5, gaussian_blur, -0.5, 0)
        
        return sharpened

def enhance_image(image: Image.Image) -> tuple[Image.Image, dict]:
    """Simplified enhancement pipeline"""
    img_array = np.array(image)
    
    # Analyze document
    analyzer = DocumentAnalyzer()
    analysis = analyzer.analyze_image(img_array)
    
    # Enhance document
    enhancer = DocumentEnhancer()
    enhanced = enhancer.enhance(
        img_array,
        analysis['document_type'],
        analysis['is_yellowed']
    )
    
    return Image.fromarray(enhanced), {"analysis": analysis}

def process_image(file_path: Path, out_path: Path, output_format: str = 'jpg') -> dict:
    """Process a single image file for enhancement"""
    tool_logger.info(f"Processing image: {file_path}")
    
    try:
        # Use SegmentHandler for path handling
        rel_path = SegmentHandler.get_relative_path(file_path)
    except Exception as e:
        tool_logger.error(f"Error in path handling: {e}")
        import traceback
        tool_logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"success": False, "error": f"Path handling error: {e}"}
    
    try:
        # Load image using the format utility
        image, metadata = load_image(file_path)
        # Apply EXIF rotation
        image = ImageOps.exif_transpose(image)
        tool_logger.info(f"Image loaded successfully: {image.size}")
    except Exception as e:
        tool_logger.error(f"Failed to load image {file_path.name}: {e}")
        tool_logger.error(f"File exists: {file_path.exists()}")
        tool_logger.error(f"Working directory: {Path.cwd()}")
        import traceback
        tool_logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"success": False, "error": f"Failed to load image: {e}"}
    
    # Enhance image and get parameters
    enhanced, params = enhance_image(image)
    
    # Save enhanced image using the format utility
    final_path, actual_format = save_image(enhanced, out_path, output_format)
    
    details = {
        "original_size": list(image.size),
        "enhanced_size": list(enhanced.size),
        "enhancement_params": params,
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
        tool_logger.info(f"Processing file: {f}")
        try:
            result = process_image(Path(f), o, output_format)
            return result
        except Exception as e:
            tool_logger.error(f"Error in process_fn: {e}")
            import traceback
            tool_logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    # Get supported extensions and create file_types dict
    file_types = {ext: process_fn for ext in get_supported_extensions_list()}
    
    return process_file(
        file_path=str(file_path),
        output_folder=output_folder,
        process_fn=process_fn,
        file_types=file_types
    )

# Importable batch function - NO CLI dependencies
def enhance_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    output_format: str = "jpg",
    parallel_workers: int = 1,
    skip_processing: bool = False,
    **kwargs
) -> dict:
    """
    Enhance image quality of document pages - importable function

    Args:
        source_folder: Source folder containing documents
        source_manifest: Manifest file
        output_folder: Output folder for enhanced images
        output_format: Output format (jpg, png, jxl)
        parallel_workers: Number of parallel workers
        skip_processing: If True, create empty image files for fast testing (default: False)

    Returns:
        Processing statistics dictionary
    """
    if skip_processing:
        tool_logger.info("⚡ SKIP MODE: Creating empty image files for testing")
        from datetime import datetime
        import json
        from PIL import Image

        # Read manifest
        manifest_entries = []
        if Path(source_manifest).exists():
            with open(source_manifest, 'r') as f:
                for line in f:
                    if line.strip():
                        manifest_entries.append(json.loads(line))

        # Create output folder
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)

        # Create output manifest
        output_manifest_path = output_folder / "enhance_manifest.jsonl"

        stats = {
            'total': len(manifest_entries),
            'success': 0,
            'failed': 0,
            'skipped': 0
        }

        with open(output_manifest_path, 'w') as manifest_file:
            for entry in manifest_entries:
                try:
                    # Get source path
                    source = entry.get('source') or (entry.get('outputs', [None])[0] if entry.get('outputs') else None)
                    if not source:
                        continue

                    # Create output path preserving structure
                    source_path = Path(source)
                    output_path = output_folder / source_path.parent / f"{source_path.stem}.{output_format}"
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    # Create empty 1x1 image
                    img = Image.new('RGB', (1, 1), color='white')
                    img.save(str(output_path))

                    # Write manifest entry
                    manifest_entry = {
                        "source": source,
                        "outputs": [str(output_path.relative_to(output_folder))],
                        "processed_at": datetime.now().isoformat(),
                        "success": True,
                        "details": {"skip_processing": True}
                    }
                    manifest_file.write(json.dumps(manifest_entry) + "\n")
                    stats['success'] += 1

                except Exception as e:
                    tool_logger.error(f"Error creating empty image for {source}: {str(e)}")
                    manifest_entry = {
                        "source": source,
                        "outputs": [],
                        "processed_at": datetime.now().isoformat(),
                        "success": False,
                        "error": str(e)
                    }
                    manifest_file.write(json.dumps(manifest_entry) + "\n")
                    stats['failed'] += 1

        tool_logger.success(f"⚡ Skip mode complete: {stats['success']} empty images created")
        return stats

    # Normal processing path
    # Create parallel-enabled batch processor using shared utility
    ParallelEnhanceProcessor = create_parallel_batch_processor("enhance", BatchProcessor, process_image)

    processor = ParallelEnhanceProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="enhance",
        base_folder=source_folder,
        processor_fn=lambda f, o: process_document(f, o, output_format),  # Fallback for sequential
        output_format=output_format,
        parallel_workers=parallel_workers,
        add_documents_prefix=kwargs.get('add_documents_prefix', False)
    )
    return processor.process()

# CLI wrapper for typer
def enhance(
    source_folder: Path = typer.Argument(..., help="Source folder containing documents"),
    source_manifest: Path = typer.Argument(..., help="Manifest file"),
    output_folder: Path = typer.Argument(..., help="Output folder for enhanced images"),
    output_format: str = typer.Option("jpg", "--format", "-f", 
                                     help="Output format: png, jxl, or jpg",
                                     callback=validate_format)
):
    """Enhance image quality of document pages"""
    return enhance_batch(source_folder, source_manifest, output_folder, output_format)

if __name__ == "__main__":
    typer.run(enhance)