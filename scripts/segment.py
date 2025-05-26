import typer
import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
from pathlib import Path
from rich.console import Console
import pytesseract
import logging
from io import BytesIO
import os
import re
import shutil
import subprocess

from utils.batch import BatchProcessor
from utils.processor import process_file
from utils.segment_handler import SegmentHandler
from utils.image_format import (
    ImageFormat, 
    save_image, 
    load_image, 
    get_supported_extensions_list, 
    validate_format
)

console = Console()
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def deskew_image(pil_img: Image.Image, confidence_threshold=0.7) -> tuple[Image.Image, float]:
    """
    Improved deskewing that uses multiple methods and prevents content cutoff.
    Returns (deskewed_image, confidence_score)
    """
    original_img = pil_img.copy()
    
    # Method 1: Try text baseline detection first (most accurate for text documents)
    baseline_angle = get_text_baseline_angle(pil_img)
    baseline_confidence = 0.8 if abs(baseline_angle) > 0.1 else 0.0
    
    # Method 2: Get angle from Hough lines (similar to rotate.py)
    cv_img = np.array(pil_img.convert('L'))
    hough_angle = get_hough_angle(cv_img)
    hough_confidence = 0.9 if abs(hough_angle) > 0.1 else 0.0
    
    # Method 3: Get angle from largest contour
    _, thresh = cv2.threshold(cv_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    contour_angle = 0.0
    contour_confidence = 0.0
    if contours:
        # Filter out very small contours that might be noise
        significant_contours = [c for c in contours if cv2.contourArea(c) > 100]
        if significant_contours:
            largest_contour = max(significant_contours, key=cv2.contourArea)
            rot_rect = cv2.minAreaRect(largest_contour)
            contour_angle = rot_rect[-1]
            
            # Normalize angle to [-45, 45] range
            if contour_angle < -45:
                contour_angle = 90 + contour_angle
            elif contour_angle > 45:
                contour_angle = contour_angle - 90
            
            if abs(contour_angle) > 0.1:
                contour_confidence = 0.6  # Lower confidence for contour method
    
    # Calculate weighted average based on confidence
    total_confidence = baseline_confidence + hough_confidence + contour_confidence
    
    if total_confidence < confidence_threshold:
        # Low confidence - don't rotate
        logging.info("Low confidence in rotation detection, skipping deskew")
        return original_img, 0.0
    
    # Weighted average of angles
    final_angle = (
        (baseline_angle * baseline_confidence + 
         hough_angle * hough_confidence + 
         contour_angle * contour_confidence) / total_confidence
    )
    
    # Check if angles agree (within 1 degree)
    angles_with_confidence = []
    if baseline_confidence > 0:
        angles_with_confidence.append(baseline_angle)
    if hough_confidence > 0:
        angles_with_confidence.append(hough_angle)
    if contour_confidence > 0:
        angles_with_confidence.append(contour_angle)
    
    if len(angles_with_confidence) > 1:
        angle_variance = np.var(angles_with_confidence)
        if angle_variance > 1.0:  # Angles disagree significantly
            logging.info(f"Rotation methods disagree (variance: {angle_variance:.2f}), using conservative approach")
            final_angle = final_angle * 0.5  # Reduce rotation amount
            total_confidence *= 0.5
    
    logging.info(f"Rotation angle: {final_angle:.2f}° (confidence: {total_confidence:.2f})")
    
    # Don't rotate if angle is too small or confidence too low
    if abs(final_angle) < 0.1 or total_confidence < confidence_threshold:
        return original_img, total_confidence
    
    # Limit rotation to reasonable range
    final_angle = max(min(final_angle, 3.0), -3.0)  # More conservative limit
    
    # Rotate with expansion to prevent cutoff
    # Calculate expansion needed
    width, height = pil_img.size
    angle_rad = np.radians(abs(final_angle))
    new_width = int(width * np.cos(angle_rad) + height * np.sin(angle_rad))
    new_height = int(height * np.cos(angle_rad) + width * np.sin(angle_rad))
    
    # Create a larger canvas with extra padding
    padding = 50  # Extra padding to be safe
    expanded_img = Image.new(pil_img.mode, 
                            (new_width + 2*padding, new_height + 2*padding), 
                            'white')
    paste_x = (expanded_img.width - width) // 2
    paste_y = (expanded_img.height - height) // 2
    expanded_img.paste(pil_img, (paste_x, paste_y))
    
    # Rotate the expanded image
    rotated = expanded_img.rotate(-final_angle, resample=Image.BICUBIC, expand=False)
    
    # Crop to remove excess white space while keeping all content
    rotated_array = np.array(rotated.convert('L'))
    _, binary = cv2.threshold(rotated_array, 250, 255, cv2.THRESH_BINARY_INV)
    coords = cv2.findNonZero(binary)
    if coords is not None:
        x, y, w, h = cv2.boundingRect(coords)
        # Add small padding
        padding = 20
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(rotated.width - x, w + 2 * padding)
        h = min(rotated.height - y, h + 2 * padding)
        rotated = rotated.crop((x, y, x + w, y + h))
    
    return rotated, total_confidence

def get_hough_angle(cv_img: np.ndarray) -> float:
    """
    Detect skew angle using Hough line transform.
    Adapted from rotate.py with improvements for text documents.
    """
    try:
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(cv_img, (5, 5), 0)
        
        # Edge detection with Canny
        edges = cv2.Canny(blurred, 50, 150, apertureSize=3)
        
        # Use HoughLinesP for more control (similar to rotate.py)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, 
                               minLineLength=100, maxLineGap=10)
        
        if lines is None:
            return 0.0
        
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            # Calculate angle in degrees
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Focus on near-horizontal lines (within ±15 degrees)
            if -15 <= angle <= 15:
                angles.append(angle)
            # Also check for lines near 90 degrees (vertical text)
            elif 75 <= abs(angle) <= 105:
                # Convert to equivalent horizontal angle
                if angle > 0:
                    angles.append(angle - 90)
                else:
                    angles.append(angle + 90)
        
        if len(angles) < 3:  # Need at least 3 lines for confidence
            return 0.0
        
        # Use median to reduce outlier influence
        median_angle = np.median(angles)
        
        # Only return angle if we have good consensus
        angle_std = np.std(angles)
        if angle_std > 2.0:  # High variance means low confidence
            return 0.0
            
        return median_angle if abs(median_angle) < 5.0 else 0.0
        
    except Exception as e:
        logging.warning(f"Error in Hough angle detection: {e}")
        return 0.0

def get_text_baseline_angle(img: Image.Image) -> float:
    """
    Improved text baseline angle detection with better handling of multi-column layouts
    and statistical outlier rejection.
    """
    try:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Get text data from OCR
        with BytesIO() as bio:
            img.save(bio, format='PNG')
            bio.seek(0)
            img_array = np.array(Image.open(bio))
            data = pytesseract.image_to_data(img_array, output_type=pytesseract.Output.DICT)
        
        # Group text by lines based on vertical proximity
        line_groups = []
        line_threshold = 20  # pixels
        
        for i in range(len(data['level'])):
            if data['conf'][i] > 30 and data['text'][i].strip():
                x = data['left'][i]
                y = data['top'][i] + data['height'][i] / 2
                w = data['width'][i]
                h = data['height'][i]
                
                # Find which line group this belongs to
                added = False
                for group in line_groups:
                    if abs(y - group['y_mean']) < line_threshold:
                        group['points'].append((x + w/2, y))
                        group['y_mean'] = np.mean([p[1] for p in group['points']])
                        added = True
                        break
                
                if not added:
                    line_groups.append({
                        'points': [(x + w/2, y)],
                        'y_mean': y
                    })
        
        # Calculate angle for each line with at least 3 words
        angles = []
        for group in line_groups:
            if len(group['points']) >= 3:
                points = sorted(group['points'], key=lambda p: p[0])  # Sort by x
                x_coords, y_coords = zip(*points)
                
                # Use RANSAC-like approach for robust line fitting
                if len(points) >= 5:
                    # Try multiple subsets and find consensus
                    subset_angles = []
                    for _ in range(min(10, len(points))):
                        # Random subset of points
                        indices = np.random.choice(len(points), size=min(4, len(points)), replace=False)
                        subset_x = [x_coords[i] for i in indices]
                        subset_y = [y_coords[i] for i in indices]
                        
                        coeffs = np.polyfit(subset_x, subset_y, deg=1)
                        angle = np.degrees(np.arctan(coeffs[0]))
                        subset_angles.append(angle)
                    
                    # Use median of subset angles
                    angle = np.median(subset_angles)
                else:
                    # Direct fit for smaller groups
                    coeffs = np.polyfit(x_coords, y_coords, deg=1)
                    angle = np.degrees(np.arctan(coeffs[0]))
                
                if abs(angle) < 10.0:  # Reasonable angle range
                    angles.append(angle)
        
        if not angles:
            return 0.0
        
        # Remove outliers using IQR method
        if len(angles) > 3:
            q1 = np.percentile(angles, 25)
            q3 = np.percentile(angles, 75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            angles = [a for a in angles if lower_bound <= a <= upper_bound]
        
        if not angles:
            return 0.0
        
        # Return median angle, capped to reasonable range
        median_angle = np.median(angles)
        return max(min(median_angle, 5.0), -5.0)
        
    except Exception as e:
        logging.warning(f"Error in baseline angle detection: {e}")
        return 0.0

def get_connected_component_lines(img: Image.Image, line_threshold=10, min_box_width=10, min_box_height=10) -> list:
    cv_img = np.array(img.convert('L'))
    _, thresh = cv2.threshold(cv_img, 0, 255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    box_info = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w >= min_box_width and h >= min_box_height:
            top = y
            bottom = y + h
            box_info.append((top, bottom))
    box_info.sort(key=lambda x: x[0])
    lines = []
    if box_info:
        current_top, current_bottom = box_info[0]
        for (t, b) in box_info[1:]:
            if t <= current_bottom + line_threshold:
                current_bottom = max(current_bottom, b)
            else:
                lines.append((current_top, current_bottom))
                current_top, current_bottom = t, b
        lines.append((current_top, current_bottom))
    return lines

def find_safe_cut_point(img: Image.Image, start: int, end: int, margin: int = 20) -> int:
    """
    Find a safe point to cut the image between text lines.
    Returns the Y coordinate that appears to be between lines.
    """
    height = end - start
    if height <= margin * 2:
        return start + height // 2
    
    # Look at a slice of the image
    slice_img = img.crop((0, start, img.width, end))
    # Convert to grayscale for analysis
    cv_img = np.array(slice_img.convert('L'))
    
    # Get horizontal projection (sum of dark pixels in each row)
    projection = np.sum(cv_img < 128, axis=1)
    
    # Find the row with the fewest dark pixels (likely between lines)
    min_pixels = float('inf')
    best_cut = start + height // 2  # default to middle if no better point found
    
    # Search in the middle region of the slice
    search_start = height // 3
    search_end = 2 * height // 3
    
    for y in range(search_start, search_end):
        # Look at a small window around this point
        window_sum = sum(projection[max(0, y-2):min(len(projection), y+3)])
        if window_sum < min_pixels:
            min_pixels = window_sum
            best_cut = start + y
    
    return best_cut

def merge_thin_empty_segments(segments, min_height=100, min_text_ratio=0.1):
    """
    Enhanced merge function that:
    1. Merges empty segments with neighbors
    2. Joins segments with very little text
    3. Handles overlaps properly during merging
    """
    if len(segments) <= 1:
        return segments

    # First pass: calculate average text density for normalization
    total_height = sum(segment["bottom"] - segment["top"] for segment in segments)
    avg_text_per_pixel = sum(segment["text_len"] for segment in segments) / total_height if total_height > 0 else 0

    # First merge: Extremely thin segments (less than min_height/3)
    very_thin_merged = []
    i = 0
    while i < len(segments):
        current = segments[i]
        height = current["bottom"] - current["top"]
        
        # If segment is extremely thin, always merge it
        if height < min_height/2:  # Changed from min_height/3 to min_height/2
            # Try to merge with previous segment first
            if very_thin_merged:
                prev_segment = very_thin_merged[-1]
                new_height = current["bottom"] - prev_segment["top"]
                if new_height < min_height * 4:  # Increased from 3 to 4
                    # Create new image and preserve colors
                    new_img = Image.new('RGB', (
                        prev_segment["image"].width,
                        new_height
                    ), color='white')  # Use white background
                    
                    # Paste using original images
                    new_img.paste(prev_segment["image"], (0, 0))
                    curr_paste_y = prev_segment["bottom"] - prev_segment["top"]
                    new_img.paste(current["image"], (0, curr_paste_y))
                    
                    prev_segment["image"] = new_img
                    prev_segment["bottom"] = current["bottom"]
                    prev_segment["text_len"] += current["text_len"]
                    i += 1
                    continue
            # If couldn't merge with previous, try next segment
            if i < len(segments) - 1:
                next_segment = segments[i + 1]
                new_height = next_segment["bottom"] - current["top"]
                if new_height < min_height * 4:  # Increased from 3 to 4
                    # Merge with next segment
                    next_segment["top"] = current["top"]
                    next_segment["text_len"] += current["text_len"]
                    next_segment["image"] = Image.new('RGB', (
                        next_segment["image"].width,
                        next_segment["bottom"] - next_segment["top"]
                    ))
                    i += 1
                    continue
        very_thin_merged.append(current)
        i += 1

    # Second pass: normal thin/empty segment merging
    merged = []
    i = 0
    while i < len(very_thin_merged):
        current = very_thin_merged[i]
        height = current["bottom"] - current["top"]
        text_density = current["text_len"] / height if height > 0 else 0

        should_merge = (
            height < min_height * 1.5 or  # Increased threshold from min_height to min_height * 1.5
            (text_density < avg_text_per_pixel * min_text_ratio and height < min_height * 3)  # Increased from 2 to 3
        )
        
        if should_merge:
            # Try to merge with previous segment first
            if merged:
                prev_segment = merged[-1]
                # Calculate overlap
                overlap = max(0, prev_segment["bottom"] - current["top"])
                new_height = current["bottom"] - prev_segment["top"]
                
                if new_height < min_height * 4:  # Increased from 3 to 4
                    # Create new image with white background
                    new_img = Image.new('RGB', (
                        prev_segment["image"].width,
                        new_height
                    ), color='white')
                    
                    # Paste preserving colors
                    new_img.paste(prev_segment["image"], (0, 0))
                    if overlap > 0:
                        curr_img = current["image"].crop((0, overlap, current["image"].width, current["image"].height))
                        new_img.paste(curr_img, (0, prev_segment["bottom"] - prev_segment["top"] - overlap))
                    else:
                        new_img.paste(current["image"], (0, prev_segment["bottom"] - prev_segment["top"]))
                    
                    prev_segment["image"] = new_img
                    prev_segment["bottom"] = current["bottom"]
                    prev_segment["text_len"] += current["text_len"]
                    i += 1
                    continue
            
            # If couldn't merge with previous, try next segment
            if i < len(very_thin_merged) - 1:
                next_segment = very_thin_merged[i + 1]
                # Calculate overlap
                overlap = max(0, current["bottom"] - next_segment["top"])
                new_height = next_segment["bottom"] - current["top"]
                
                if new_height < min_height * 4:  # Increased from 3 to 4
                    new_img = Image.new('RGB', (
                        next_segment["image"].width,
                        new_height
                    ), color='white')
                    # Paste current segment
                    new_img.paste(current["image"], (0, 0))
                    # Paste next segment, skipping the overlapped region
                    next_img = next_segment["image"].crop((0, overlap, next_segment["image"].width, next_segment["image"].height))
                    new_img.paste(next_img, (0, current["bottom"] - current["top"] - overlap))
                    
                    next_segment["image"] = new_img
                    next_segment["top"] = current["top"]
                    next_segment["text_len"] += current["text_len"]
                    i += 1
                    continue
        
        merged.append(current)
        i += 1
    
    return merged

def adaptive_segment_image(img: Image.Image, min_text_length=10) -> list:
    """
    Segment image into chunks with improved line joining and rotation handling.
    """
    if hasattr(pytesseract, 'set_temp_directory'):
        pytesseract.set_temp_directory(None)
    
    # Store original dimensions
    original_width, original_height = img.size
    rotation_confidence = 1.0  # Default high confidence
    
    # Apply deskewing
    deskewed_img, confidence = deskew_image(img)
    rotation_confidence = confidence
    # Log if dimensions changed significantly
    if deskewed_img.size != img.size:
        logging.info(f"Image dimensions changed from {img.size} to {deskewed_img.size} after deskewing")
    
    width, height = deskewed_img.size
    
    # Adjust thresholds based on whether we deskewed and confidence
    if rotation_confidence < 0.7:
        logging.info(f"Low rotation confidence ({rotation_confidence:.2f}), using conservative segmentation")
        # Increase minimum chunk height to avoid small segments that might be cut off
        MIN_CHUNK_HEIGHT = 200  # Increased from 100
        merge_small_segments = True
    else:
        MIN_CHUNK_HEIGHT = 100
        merge_small_segments = False
    
    if height < 2500:
        text_in_img = pytesseract.image_to_string(deskewed_img).strip()
        return [{
            "image": deskewed_img,
            "top": 0,
            "bottom": height,
            "text_len": len(text_in_img),
            "rotation_confidence": rotation_confidence
        }]
    
    # Get Tesseract boxes
    data = pytesseract.image_to_data(deskewed_img, output_type=pytesseract.Output.DICT)
    tess_boxes = []
    for i in range(len(data["level"])):
        text = data["text"][i].strip()
        if text:
            top = data["top"][i]
            bottom = top + data["height"][i]
            tess_boxes.append((top, bottom))
    
    tess_boxes.sort(key=lambda x: x[0])
    
    # Fallback to connected components if needed
    fallback_needed = (len(tess_boxes) < 3)
    if fallback_needed:
        cc_lines = get_connected_component_lines(deskewed_img, line_threshold=15)
    else:
        cc_lines = []
    
    # Combine and merge boxes
    all_boxes = tess_boxes + cc_lines
    all_boxes.sort(key=lambda x: x[0])
    
    # Merge boxes that are close
    line_threshold = 15
    merged_boxes = []
    for box in all_boxes:
        if not merged_boxes:
            merged_boxes.append(list(box))
        else:
            if box[0] <= merged_boxes[-1][1] + line_threshold:
                merged_boxes[-1][1] = max(merged_boxes[-1][1], box[1])
            else:
                merged_boxes.append(list(box))
    
    # Build segments
    cover_segments = []
    if not merged_boxes:
        cover_segments.append((0, height))
    else:
        if merged_boxes[0][0] > 0:
            cover_segments.append((0, merged_boxes[0][0]))
        for i in range(len(merged_boxes)):
            t_i, b_i = merged_boxes[i]
            cover_segments.append((t_i, b_i))
            if i < len(merged_boxes) - 1:
                next_top = merged_boxes[i+1][0]
                if b_i < next_top:
                    cover_segments.append((b_i, next_top))
        if merged_boxes[-1][1] < height:
            cover_segments.append((merged_boxes[-1][1], height))
    
    # Subdivide large segments
    MAX_CHUNK_HEIGHT = 2000
    subdivided_segments = []
    for seg_top, seg_bottom in cover_segments:
        seg_height = seg_bottom - seg_top
        if seg_height <= MAX_CHUNK_HEIGHT and seg_height >= MIN_CHUNK_HEIGHT:
            subdivided_segments.append((seg_top, seg_bottom))
        elif seg_height < MIN_CHUNK_HEIGHT:
            if subdivided_segments:
                prev_top, prev_bottom = subdivided_segments[-1]
                if seg_bottom - prev_top <= MAX_CHUNK_HEIGHT:
                    subdivided_segments[-1] = (prev_top, seg_bottom)
                else:
                    subdivided_segments.append((seg_top, seg_bottom))
            else:
                subdivided_segments.append((seg_top, seg_bottom))
        else:
            start = seg_top
            while start < seg_bottom:
                if seg_bottom - start <= MAX_CHUNK_HEIGHT:
                    end = seg_bottom
                else:
                    target_end = start + MAX_CHUNK_HEIGHT
                    end = find_safe_cut_point(deskewed_img, target_end - 40, target_end + 40)
                
                if end - start >= MIN_CHUNK_HEIGHT:
                    subdivided_segments.append((start, end))
                start = end
    
    # If low confidence and merge_small_segments is True, merge adjacent small segments
    if merge_small_segments and len(subdivided_segments) > 1:
        merged_segments = []
        i = 0
        while i < len(subdivided_segments):
            seg_top, seg_bottom = subdivided_segments[i]
            seg_height = seg_bottom - seg_top
            
            # If this segment is small and not the last one
            if seg_height < 300 and i < len(subdivided_segments) - 1:
                next_top, next_bottom = subdivided_segments[i + 1]
                combined_height = next_bottom - seg_top
                
                # Merge if combined height is reasonable
                if combined_height <= MAX_CHUNK_HEIGHT:
                    merged_segments.append((seg_top, next_bottom))
                    i += 2  # Skip the next segment since we merged it
                    logging.info(f"Merged small segments: ({seg_top}-{seg_bottom}) + ({next_top}-{next_bottom})")
                    continue
            
            merged_segments.append((seg_top, seg_bottom))
            i += 1
        
        subdivided_segments = merged_segments
    
    # Create final segments
    chunk_overlap = 20
    segments = []
    for i, (seg_top, seg_bottom) in enumerate(subdivided_segments):
        actual_top = seg_top
        actual_bottom = seg_bottom + (chunk_overlap if i < len(subdivided_segments)-1 else 0)
        
        if actual_bottom - actual_top < MIN_CHUNK_HEIGHT:
            continue
            
        roi = deskewed_img.crop((0, actual_top, width, actual_bottom))
        
        # Ensure white background for rotated images
        if rotation_confidence > 0:
            white_bg = Image.new('RGB', roi.size, 'white')
            white_bg.paste(roi, (0, 0))
            roi = white_bg
        
        text_in_segment = pytesseract.image_to_string(roi.convert('L')).strip()
        segments.append({
            "image": roi,
            "top": actual_top,
            "bottom": actual_bottom,
            "text_len": len(text_in_segment),
            "rotation_confidence": rotation_confidence
        })
    
    # Merge thin empty segments
    segments = merge_thin_empty_segments(segments, min_height=MIN_CHUNK_HEIGHT)
    
    return segments

def process_image(file_path: Path, out_path: Path) -> dict:
    """Process a single image file for segmentation"""
    try:
        # Get relative path for logging
        rel_path = SegmentHandler.get_relative_path(file_path)
        logger.info(f"Processing {rel_path}")
            
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        # Load image using the format utility
        image, metadata = load_image(file_path)
        logger.info(f"Loaded image {rel_path}, size: {image.size}")
        
        segments = adaptive_segment_image(image)
        logger.info(f"Created {len(segments)} segments for {rel_path}")
        
        # Get segment paths using SegmentHandler
        segment_paths = SegmentHandler.get_segment_paths(file_path)
        segments_folder = segment_paths["segments_folder"]
        
        # Create the full segments directory path
        full_segments_dir = out_path / segments_folder
        full_segments_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created segments directory: {full_segments_dir}")
        
        segment_paths = []
        segment_info = []
        
        # Process and save segments
        for i, segment_data in enumerate(segments):
            roi = segment_data["image"]
            # Use SegmentHandler for consistent segment naming
            segment_name = SegmentHandler.make_segment_name(file_path.stem, i + 1)
            out_segment_path = full_segments_dir / segment_name
            
            # Save as JPG with high quality
            roi.save(out_segment_path, "JPEG", quality=95, optimize=True, subsampling=0)
            logger.info(f"Saved segment {i+1}/{len(segments)}: {segment_name}")
            
            # Create relative path for segment
            segment_rel_path = segments_folder / segment_name
            segment_paths.append(str(segment_rel_path))
            segment_info.append({
                "index": i,
                "file_path": str(segment_rel_path),
                "bounding_box": [segment_data["top"], segment_data["bottom"]],
                "text_len": segment_data["text_len"],
                "parent_image": str(rel_path),
                "rotation_confidence": segment_data.get("rotation_confidence", 1.0)
            })
        
        logger.info(f"Completed processing {rel_path}")
        return {
            "outputs": segment_paths,
            "source": str(rel_path),
            "parent_image": str(rel_path),
            "details": {
                "num_segments": len(segments),
                "segments": segment_info,
                "parent_info": {
                    "path": str(rel_path),
                    "relative_path": str(rel_path)
                }
            }
        }
    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {str(e)}")
        return {"error": str(e)}

def process_document(file_path: str, output_folder: Path) -> dict:
    """Process a single document file"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        return process_image(Path(f), o)
    
    # Get supported extensions and create file_types dict
    file_types = {ext: process_fn for ext in get_supported_extensions_list()}
    
    return process_file(
        file_path=str(file_path),
        output_folder=output_folder,
        process_fn=process_fn,
        file_types=file_types
    )

def segment(
    source_folder: Path = typer.Argument(..., help="Source folder containing images"),
    source_manifest: Path = typer.Argument(..., help="Manifest file"),
    output_folder: Path = typer.Argument(..., help="Output folder for segmented images")
):
    """Segment images into smaller chunks for better processing"""
    processor = BatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="segment",
        base_folder=source_folder,  # Base folder for finding input files
        processor_fn=lambda f, o: process_document(f, o),
        use_source=False  # Use outputs from previous step
    )
    processor.process()

if __name__ == "__main__":
    typer.run(segment)