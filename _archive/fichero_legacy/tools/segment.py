import typer
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pathlib import Path
import pytesseract
from io import BytesIO
import os
import re
import shutil
import subprocess

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.parallel_batch_processor import create_parallel_batch_processor
except ImportError:
    # When run as standalone script (relative imports work)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.processor import process_file
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.image_format import ImageFormat, save_image, load_image, get_supported_extensions_list, validate_format
    from fichero.tools.utils.tool_logger import get_tool_logger
    from fichero.tools.utils.parallel_batch_processor import create_parallel_batch_processor

tool_logger = get_tool_logger('segment')

def deskew_image(pil_img: Image.Image, confidence_threshold=0.8) -> tuple[Image.Image, float]:
    """
    Improved deskewing that uses multiple methods and prevents content cutoff.
    Returns (deskewed_image, confidence_score)
    """
    original_img = pil_img.copy()
    
    # Method 1: Try text baseline detection first (most accurate for text documents)
    baseline_angle = get_text_baseline_angle(pil_img)
    # More conservative confidence based on actual angle magnitude and consistency
    baseline_confidence = min(0.7, abs(baseline_angle) * 0.2) if abs(baseline_angle) > 0.2 else 0.0
    
    # Method 2: Get angle from Hough lines (similar to rotate.py)
    cv_img = np.array(pil_img.convert('L'))
    hough_angle = get_hough_angle(cv_img)
    # Lower confidence for Hough method as it can be noisy
    hough_confidence = min(0.6, abs(hough_angle) * 0.15) if abs(hough_angle) > 0.2 else 0.0
    
    # Method 3: Get angle from largest contour
    _, thresh = cv2.threshold(cv_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    contour_angle = 0.0
    contour_confidence = 0.0
    if contours:
        # Filter out very small contours that might be noise
        significant_contours = [c for c in contours if cv2.contourArea(c) > 500]  # Increased threshold
        if significant_contours:
            largest_contour = max(significant_contours, key=cv2.contourArea)
            rot_rect = cv2.minAreaRect(largest_contour)
            contour_angle = rot_rect[-1]
            
            # Normalize angle to [-45, 45] range
            if contour_angle < -45:
                contour_angle = 90 + contour_angle
            elif contour_angle > 45:
                contour_angle = contour_angle - 90
            
            # Even lower confidence for contour method
            contour_confidence = min(0.4, abs(contour_angle) * 0.1) if abs(contour_angle) > 0.3 else 0.0
    
    # Collect angles and confidences for analysis
    angles_with_confidence = []
    if baseline_confidence > 0:
        angles_with_confidence.append((baseline_angle, baseline_confidence))
    if hough_confidence > 0:
        angles_with_confidence.append((hough_angle, hough_confidence))
    if contour_confidence > 0:
        angles_with_confidence.append((contour_angle, contour_confidence))
    
    if not angles_with_confidence:
        tool_logger.info("No reliable rotation angles detected, skipping deskew")
        return original_img, 0.0
    
    # Check agreement between methods
    angles_only = [angle for angle, _ in angles_with_confidence]
    if len(angles_only) > 1:
        angle_variance = np.var(angles_only)
        max_diff = max(angles_only) - min(angles_only)
        
        # If methods disagree significantly, be very conservative
        if angle_variance > 0.5 or max_diff > 1.5:
            tool_logger.info(f"Rotation methods disagree significantly (variance: {angle_variance:.2f}, max_diff: {max_diff:.2f})")
            # Only proceed if we have very strong evidence
            if max([conf for _, conf in angles_with_confidence]) < 0.6:
                tool_logger.info("Insufficient confidence with disagreement, skipping rotation")
                return original_img, 0.0
            # Reduce all confidences
            angles_with_confidence = [(angle, conf * 0.3) for angle, conf in angles_with_confidence]
    
    # Calculate weighted average
    total_confidence = sum(conf for _, conf in angles_with_confidence)
    if total_confidence < confidence_threshold:
        tool_logger.info(f"Total confidence {total_confidence:.2f} below threshold {confidence_threshold}, skipping deskew")
        return original_img, 0.0
    
    final_angle = sum(angle * conf for angle, conf in angles_with_confidence) / total_confidence
    
    tool_logger.info(f"Rotation angle: {final_angle:.2f}° (confidence: {total_confidence:.2f})")
    tool_logger.info(f"Individual angles: baseline={baseline_angle:.2f}°({baseline_confidence:.2f}), "
                f"hough={hough_angle:.2f}°({hough_confidence:.2f}), "
                f"contour={contour_angle:.2f}°({contour_confidence:.2f})")
    
    # Much more conservative angle limits
    if abs(final_angle) < 0.2:  # Increased minimum threshold
        tool_logger.info("Angle too small, skipping rotation")
        return original_img, total_confidence
    
    # Limit rotation to very conservative range
    final_angle = max(min(final_angle, 2.0), -2.0)  # Reduced from 3.0 to 2.0
    
    # Additional safety check: if angle is small but we're still rotating, reduce it further
    if abs(final_angle) < 1.0:
        final_angle *= 0.7  # Reduce small angles even more
        tool_logger.info(f"Applied small angle reduction, final angle: {final_angle:.2f}°")
    
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
    
    # Validate that rotation actually improved the image
    if validate_rotation(original_img, rotated):
        tool_logger.info("Rotation validation passed - keeping rotated image")
        return rotated, total_confidence
    else:
        tool_logger.info("Rotation validation failed - keeping original image")
        return original_img, 0.0

def get_hough_angle(cv_img: np.ndarray) -> float:
    """
    Detect skew angle using Hough line transform.
    Adapted from rotate.py with improvements for text documents.
    """
    try:
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(cv_img, (5, 5), 0)
        
        # Edge detection with Canny - more conservative parameters
        edges = cv2.Canny(blurred, 30, 100, apertureSize=3)  # Reduced thresholds
        
        # Use HoughLinesP for more control (similar to rotate.py)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80,  # Reduced threshold
                               minLineLength=150, maxLineGap=15)  # Increased minLineLength
        
        if lines is None:
            return 0.0
        
        angles = []
        line_lengths = []
        
        for line in lines:
            x1, y1, x2, y2 = line[0]
            
            # Calculate line length and angle
            length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            
            # Only consider longer lines (more reliable)
            if length < 100:
                continue
                
            # Focus on near-horizontal lines (within ±10 degrees) - more restrictive
            if -10 <= angle <= 10:
                angles.append(angle)
                line_lengths.append(length)
            # Also check for lines near 90 degrees (vertical text)
            elif 80 <= abs(angle) <= 100:
                # Convert to equivalent horizontal angle
                if angle > 0:
                    angles.append(angle - 90)
                else:
                    angles.append(angle + 90)
                line_lengths.append(length)
        
        if len(angles) < 5:  # Need more lines for confidence
            return 0.0
        
        # Weight angles by line length (longer lines are more reliable)
        if line_lengths:
            weights = np.array(line_lengths)
            weights = weights / np.sum(weights)  # Normalize weights
            weighted_angle = np.average(angles, weights=weights)
        else:
            weighted_angle = np.median(angles)
        
        # Only return angle if we have good consensus
        angle_std = np.std(angles)
        if angle_std > 1.5:  # Reduced variance threshold
            return 0.0
        
        # Additional check: remove outliers and recalculate
        if len(angles) > 7:
            # Remove angles that are more than 1.5 std devs from median
            median_angle = np.median(angles)
            filtered_angles = [a for a in angles if abs(a - median_angle) < 1.5 * angle_std]
            if len(filtered_angles) >= 5:
                weighted_angle = np.median(filtered_angles)
                angle_std = np.std(filtered_angles)
        
        # Final validation
        return weighted_angle if abs(weighted_angle) < 3.0 and angle_std < 1.0 else 0.0
        
    except Exception as e:
        tool_logger.warning(f"Error in Hough angle detection: {e}")
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
            try:
                data = pytesseract.image_to_data(img_array, output_type=pytesseract.Output.DICT)
            except UnicodeDecodeError as e:
                tool_logger.warning(f"Tesseract OCR not available or misconfigured in worker environment: {e}")
                return 0.0
            except pytesseract.TesseractError as e:
                tool_logger.warning(f"Tesseract OCR failed: {e}")
                return 0.0
            except Exception as e:
                tool_logger.warning(f"OCR failed during baseline angle detection: {e}")
                return 0.0
        
        # Group text by lines based on vertical proximity
        line_groups = []
        line_threshold = 25  # Increased threshold for more robust grouping
        
        # Only consider text with higher confidence
        for i in range(len(data['level'])):
            if data['conf'][i] > 50 and data['text'][i].strip() and len(data['text'][i].strip()) > 2:  # Higher confidence and longer text
                x = data['left'][i]
                y = data['top'][i] + data['height'][i] / 2
                w = data['width'][i]
                h = data['height'][i]
                
                # Skip very small text boxes (likely noise)
                if w < 20 or h < 10:
                    continue
                
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
        
        # Calculate angle for each line with sufficient words
        angles = []
        line_qualities = []  # Track quality of each line fit
        
        for group in line_groups:
            if len(group['points']) >= 4:  # Increased minimum points requirement
                points = sorted(group['points'], key=lambda p: p[0])  # Sort by x
                x_coords, y_coords = zip(*points)
                
                # Calculate line span (wider lines are more reliable)
                line_span = max(x_coords) - min(x_coords)
                if line_span < 200:  # Skip short lines
                    continue
                
                # Use RANSAC-like approach for robust line fitting
                if len(points) >= 6:
                    # Try multiple subsets and find consensus
                    subset_angles = []
                    for _ in range(min(15, len(points))):  # More iterations
                        # Random subset of points
                        indices = np.random.choice(len(points), size=min(5, len(points)), replace=False)
                        subset_x = [x_coords[i] for i in indices]
                        subset_y = [y_coords[i] for i in indices]
                        
                        try:
                            coeffs = np.polyfit(subset_x, subset_y, deg=1)
                            angle = np.degrees(np.arctan(coeffs[0]))
                            if abs(angle) < 8.0:  # More restrictive angle range
                                subset_angles.append(angle)
                        except:
                            continue
                    
                    if len(subset_angles) >= 3:
                        # Use median of subset angles
                        angle = np.median(subset_angles)
                        # Calculate quality based on consistency
                        angle_std = np.std(subset_angles)
                        quality = max(0, 1.0 - angle_std / 2.0) * (line_span / 1000.0)  # Weight by span
                    else:
                        continue
                else:
                    # Direct fit for smaller groups
                    try:
                        coeffs = np.polyfit(x_coords, y_coords, deg=1)
                        angle = np.degrees(np.arctan(coeffs[0]))
                        # Calculate R-squared for quality assessment
                        y_pred = np.polyval(coeffs, x_coords)
                        ss_res = np.sum((y_coords - y_pred) ** 2)
                        ss_tot = np.sum((y_coords - np.mean(y_coords)) ** 2)
                        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                        quality = r_squared * (line_span / 1000.0)
                    except:
                        continue
                
                if abs(angle) < 6.0 and quality > 0.1:  # More restrictive
                    angles.append(angle)
                    line_qualities.append(quality)
        
        if len(angles) < 2:  # Need at least 2 good lines
            return 0.0
        
        # Remove outliers using IQR method, but be more aggressive
        if len(angles) > 3:
            q1 = np.percentile(angles, 25)
            q3 = np.percentile(angles, 75)
            iqr = q3 - q1
            lower_bound = q1 - 1.0 * iqr  # More aggressive outlier removal
            upper_bound = q3 + 1.0 * iqr
            
            filtered_data = [(angle, quality) for angle, quality in zip(angles, line_qualities) 
                           if lower_bound <= angle <= upper_bound]
            
            if filtered_data:
                angles, line_qualities = zip(*filtered_data)
            else:
                return 0.0
        
        if not angles:
            return 0.0
        
        # Weight by line quality
        if line_qualities:
            weights = np.array(line_qualities)
            weights = weights / np.sum(weights)
            final_angle = np.average(angles, weights=weights)
        else:
            final_angle = np.median(angles)
        
        # Final consistency check
        angle_std = np.std(angles)
        if angle_std > 1.0:  # Require good consistency
            return 0.0
        
        # Return median angle, capped to very conservative range
        return max(min(final_angle, 3.0), -3.0)  # Reduced from 5.0 to 3.0
        
    except Exception as e:
        tool_logger.warning(f"Error in baseline angle detection: {e}")
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
        tool_logger.info(f"Image dimensions changed from {img.size} to {deskewed_img.size} after deskewing")
    
    width, height = deskewed_img.size
    
    # Adjust thresholds based on whether we deskewed and confidence
    if rotation_confidence < 0.7:
        tool_logger.info(f"Low rotation confidence ({rotation_confidence:.2f}), using conservative segmentation")
        # Increase minimum chunk height to avoid small segments that might be cut off
        MIN_CHUNK_HEIGHT = 200  # Increased from 100
        merge_small_segments = True
    else:
        MIN_CHUNK_HEIGHT = 100
        merge_small_segments = False
    
    if height < 2500:
        try:
            text_in_img = pytesseract.image_to_string(deskewed_img).strip()
        except (UnicodeDecodeError, pytesseract.TesseractError, Exception) as e:
            tool_logger.warning(f"OCR failed for full image: {e}")
            text_in_img = ""
        return [{
            "image": deskewed_img,
            "top": 0,
            "bottom": height,
            "text_len": len(text_in_img),
            "rotation_confidence": rotation_confidence
        }]
    
    # Get Tesseract boxes
    try:
        data = pytesseract.image_to_data(deskewed_img, output_type=pytesseract.Output.DICT)
        tess_boxes = []
        for i in range(len(data["level"])):
            text = data["text"][i].strip()
            if text:
                top = data["top"][i]
                bottom = top + data["height"][i]
                tess_boxes.append((top, bottom))
    except (UnicodeDecodeError, pytesseract.TesseractError, Exception) as e:
        tool_logger.warning(f"OCR failed for text box detection: {e}")
        tess_boxes = []
    
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
                    tool_logger.info(f"Merged small segments: ({seg_top}-{seg_bottom}) + ({next_top}-{next_bottom})")
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
        
        try:
            text_in_segment = pytesseract.image_to_string(roi.convert('L')).strip()
        except (UnicodeDecodeError, pytesseract.TesseractError, Exception) as e:
            tool_logger.warning(f"OCR failed for segment text detection: {e}")
            text_in_segment = ""
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

def validate_rotation(original_img: Image.Image, rotated_img: Image.Image) -> bool:
    """
    Validate if rotation actually improved the image by comparing text detection quality.
    Returns True if rotation should be kept, False if original is better.
    """
    try:
        # Quick OCR confidence comparison
        try:
            original_data = pytesseract.image_to_data(original_img, output_type=pytesseract.Output.DICT)
            rotated_data = pytesseract.image_to_data(rotated_img, output_type=pytesseract.Output.DICT)
        except (UnicodeDecodeError, pytesseract.TesseractError, Exception) as e:
            tool_logger.warning(f"OCR failed during rotation validation: {e}")
            return False  # Default to not rotating if OCR fails
        
        # Calculate average confidence for text with reasonable confidence
        def get_avg_confidence(data):
            confidences = [data['conf'][i] for i in range(len(data['conf'])) 
                          if data['conf'][i] > 0 and data['text'][i].strip()]
            return np.mean(confidences) if confidences else 0
        
        original_conf = get_avg_confidence(original_data)
        rotated_conf = get_avg_confidence(rotated_data)
        
        # Only keep rotation if it significantly improves confidence
        improvement_threshold = 5.0  # Require at least 5 point improvement
        return rotated_conf > original_conf + improvement_threshold
        
    except Exception as e:
        tool_logger.warning(f"Error in rotation validation: {e}")
        return False  # Default to not rotating if validation fails

def process_image(file_path: Path, out_path: Path) -> dict:
    """Process a single image file for segmentation"""
    try:
        # Get relative path for logging
        rel_path = SegmentHandler.get_relative_path(file_path)
        tool_logger.info(f"Processing {rel_path}")
            
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        # Load image using the format utility
        image, metadata = load_image(file_path)
        # Apply EXIF rotation
        image = ImageOps.exif_transpose(image)
        tool_logger.info(f"Loaded image {rel_path}, size: {image.size}")
        
        segments = adaptive_segment_image(image)
        tool_logger.info(f"Created {len(segments)} segments for {rel_path}")
        
        # Follow the same pattern as crop.py, enhance.py, remove_background.py
        # Create segments folder under the output path
        # Use file_path to determine actual directory structure (handles cases where input is in subdirs)
        segments_folder_name = f"{file_path.stem}_segments"
        # Get the actual parent directory from file_path to preserve directory structure
        rel_input_path = SegmentHandler.get_relative_path(file_path)
        if "/" in str(rel_input_path):
            # Input is in a subdirectory, preserve that structure
            parent_dir = Path(rel_input_path).parent
            segments_dir = out_path.parent.parent / parent_dir / segments_folder_name
        else:
            # Input is flat, use out_path.parent directly
            segments_dir = out_path.parent / segments_folder_name
        segments_dir.mkdir(parents=True, exist_ok=True)
        tool_logger.info(f"Created segments directory: {segments_dir}")
        
        segment_info = []
        segment_paths_list = []
        
        # Process and save segments
        for i, segment_data in enumerate(segments):
            roi = segment_data["image"]
            # Use SegmentHandler for consistent segment naming
            segment_name = SegmentHandler.make_segment_name(file_path.stem, i + 1)
            out_segment_path = segments_dir / segment_name
            
            # Save as JPG with high quality using the format utility
            final_path, actual_format = save_image(roi, out_segment_path, 'jpg')
            tool_logger.info(f"Saved segment {i+1}/{len(segments)}: {segment_name}")
            
            # Follow the same pattern as crop.py - get relative path of the saved file
            segment_rel_path = SegmentHandler.get_relative_path(out_segment_path)
            segment_paths_list.append(str(segment_rel_path))
            segment_info.append({
                "index": i,
                "file_path": str(segment_rel_path),
                "bounding_box": [segment_data["top"], segment_data["bottom"]],
                "text_len": segment_data["text_len"],
                "parent_image": str(rel_path),
                "rotation_confidence": segment_data.get("rotation_confidence", 1.0)
            })
        
        tool_logger.info(f"Completed processing {rel_path}")
        return {
            "outputs": segment_paths_list,
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
        tool_logger.error(f"Error processing {file_path.name}: {str(e)}")
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

def segment_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    parallel_workers: int = 1,
    **kwargs
) -> dict:
    """
    Segment images into text regions - importable function

    Args:
        source_folder: Source folder containing images
        source_manifest: Manifest file
        output_folder: Output folder for segmented images
        parallel_workers: Number of parallel workers

    Returns:
        Processing statistics dictionary
    """
    # Normal processing path
    # Create parallel-enabled batch processor using shared utility
    # Segment doesn't use output_format (always saves as JPG), so ignore the third parameter
    def process_for_parallel(file_path, out_path, output_format):
        return process_image(file_path, out_path)
    
    ParallelSegmentProcessor = create_parallel_batch_processor("segment", BatchProcessor, process_for_parallel)
    
    processor = ParallelSegmentProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name="segment",
        base_folder=source_folder,
        processor_fn=lambda f, o: process_document(f, o),  # Fallback for sequential
        use_source=False,
        parallel_workers=parallel_workers
    )
    return processor.process()

def segment(
    source_folder: Path = typer.Argument(..., help="Source folder containing images"),
    source_manifest: Path = typer.Argument(..., help="Manifest file"),
    output_folder: Path = typer.Argument(..., help="Output folder for segmented images")
):
    """Segment images into smaller chunks for better processing"""
    return segment_batch(source_folder, source_manifest, output_folder)

if __name__ == "__main__":
    typer.run(segment)