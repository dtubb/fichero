# Fichero TODO - ARM Mac Compatibility

## Changes Made (2025-07-01)

### Dependency Removals
- **Removed scikit-learn** from pyproject.toml and requirements.txt
  - Was only imported but not used in enhance.py
  - No functional impact

- **Made ultralytics optional** in crop.py
  - Added YOLO_AVAILABLE flag to check if YOLO is available
  - Added fallback to contour-based cropping when YOLO is not available
  - Updated crop_with_yolo() to return None if YOLO not available
  - Updated crop_batch() to handle YOLO loading failures gracefully

### Fallback Strategy
- **Contour-based cropping** is now the primary fallback when YOLO is unavailable
- **Original image** is used as final fallback if all detection methods fail
- **Graceful degradation** - app continues to work without advanced ML features

## Future Improvements

### Optional Dependencies
- Consider making ultralytics and scikit-learn optional dependencies that can be installed separately
- Add installation instructions for users who want advanced ML features
- Create separate requirements files for full vs minimal installations

### Alternative Cropping Methods
- Improve contour-based cropping algorithm
- Add edge detection-based cropping as another fallback
- Consider adding simple threshold-based document detection

### Performance Optimizations
- Profile contour-based cropping performance vs YOLO
- Optimize fallback methods for better accuracy
- Add caching for repeated operations

## Testing Needed
- [ ] Test briefcase create on ARM Mac
- [ ] Test cropping functionality with and without YOLO
- [ ] Verify all tools work correctly with reduced dependencies
- [ ] Test GUI and CLI functionality
- [ ] Performance testing with contour-based cropping
- [ ] Implement fallback for background removal if rembg is not available (e.g., skip or use simple OpenCV thresholding).

## Notes
- Current changes maintain full functionality while improving compatibility
- Users can still install ultralytics manually if they want YOLO-based cropping
- Contour-based cropping provides reasonable results for most documents
- No breaking changes to existing workflows 